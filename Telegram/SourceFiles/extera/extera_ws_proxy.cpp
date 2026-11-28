#include "extera/extera_ws_proxy.h"

#include "extera/extera_config.h"
#include "core/application.h"
#include "core/core_settings.h"
#include "mtproto/facade.h"
#include "mtproto/mtproto_proxy_data.h"
#include "base/timer.h"

#include <atomic>
#include <QtCore/QDir>
#include <QtCore/QFileInfo>
#include <QtCore/QPointer>
#include <QtCore/QProcess>
#include <QtCore/QRandomGenerator>
#include <QtNetwork/QNetworkAccessManager>
#include <QtNetwork/QNetworkProxy>
#include <QtNetwork/QNetworkRequest>
#include <QtNetwork/QTcpServer>

namespace Extera::WsProxy {
namespace {

constexpr auto kDefaultPort = 1443;
constexpr auto kPortAttempts = 20;
constexpr auto kRestartDelay = crl::time(3000);
constexpr auto kAutoEnableDelay = crl::time(7500);
constexpr auto kRestartCooldown = crl::time(2000);
constexpr auto kMaxRestarts = 5;

std::atomic<bool> gProxyActive{ false };
std::atomic<int> gProxyPort{ kDefaultPort };

struct State {
	QPointer<QProcess> process;
	MTP::ProxyData proxy;
	std::unique_ptr<base::Timer> restartTimer;
	std::unique_ptr<base::Timer> autoTimer;
	crl::time lastRestartAt = 0;
	int restarts = 0;
	bool stopping = false;
	bool isConnected = false;

	~State() {
		if (process && !QCoreApplication::closingDown()) {
			if (process->state() != QProcess::NotRunning) {
				process->kill();
				process->waitForFinished(500);
			}
		}
	}
};

State &Instance() {
	static auto result = [] {
		auto s = State();
		if (qApp) {
			QObject::connect(qApp, &QCoreApplication::aboutToQuit, [] {
				Stop();
				auto &st = Instance();
				st.restartTimer.reset();
				st.autoTimer.reset();
			});
		}
		return s;
	}();
	return result;
}

[[nodiscard]] QString NativeBinary() {
#ifdef Q_OS_WIN
	const auto names = { u"oxWsProxy.exe"_q, u"ox_ws_proxy.exe"_q };
#else
	const auto names = { u"oxWsProxy"_q, u"ox_ws_proxy"_q };
#endif
	for (const auto &name : names) {
		for (const auto &cand : {
			cExeDir() + name,
			cWorkingDir() + name,
			cExeDir() + u"proxy/"_q + name,
			cWorkingDir() + u"proxy/"_q + name,
			cExeDir() + u"Telegram/SourceFiles/extera/rust/ox_ws_proxy/target/release/"_q + name,
			cWorkingDir() + u"Telegram/SourceFiles/extera/rust/ox_ws_proxy/target/release/"_q + name,
		}) {
			if (QFile::exists(cand)) {
				return cand;
			}
		}
	}
	return QString();
}

[[nodiscard]] QString Secret() {
	auto secret = Extera::String(u"ws_proxy_secret"_q);
	if (secret.size() != 32) {
		auto bytes = QByteArray(16, Qt::Uninitialized);
		QRandomGenerator::system()->fillRange(
			reinterpret_cast<quint32*>(bytes.data()),
			bytes.size() / int(sizeof(quint32)));
		secret = QString::fromLatin1(bytes.toHex());
		Extera::Config::Instance().setString(u"ws_proxy_secret"_q, secret);
	}
	return secret;
}

[[nodiscard]] bool PortFree(int port) {
	auto server = QTcpServer();
	return server.listen(QHostAddress::LocalHost, port);
}

[[nodiscard]] int ChoosePort() {
	const auto saved = Extera::Int(u"ws_proxy_port"_q);
	const auto start = saved ? saved : kDefaultPort;
	for (auto i = 0; i != kPortAttempts; ++i) {
		if (PortFree(start + i)) {
			Extera::Config::Instance().setInt(u"ws_proxy_port"_q, start + i);
			return start + i;
		}
	}
	return start;
}

void Launch();

void ScheduleRestart() {
	auto &state = Instance();
	if (state.stopping || !Enabled()) {
		return;
	}
	if (state.restarts >= kMaxRestarts) {
		const auto &settings = Core::App().settings().proxy();
		if (settings.isEnabled() && IsOurs(settings.selected())) {
			Core::App().setCurrentProxy(
				settings.selected(),
				MTP::ProxyData::Settings::Disabled);
		}
		return;
	}
	++state.restarts;
	if (!state.restartTimer) {
		state.restartTimer = std::make_unique<base::Timer>([] { Launch(); });
	}
	state.restartTimer->callOnce(kRestartDelay);
}

void Launch() {
	auto &state = Instance();
	if (state.process) {
		return;
	}
	const auto nativeBin = NativeBinary();
	if (nativeBin.isEmpty()) {
		return;
	}
	state.stopping = false;
	CleanOurProxies();
	const auto port = ChoosePort();
	gProxyPort.store(port, std::memory_order_relaxed);
	gProxyActive.store(true, std::memory_order_release);
	const auto secret = Secret();
	state.proxy = MTP::ProxyData();
	state.proxy.type = MTP::ProxyData::Type::Mtproto;
	state.proxy.host = u"127.0.0.1"_q;
	state.proxy.port = uint32(port);
	state.proxy.password = u"dd"_q + secret;

	auto &settings = Core::App().settings().proxy();
	if (settings.indexInList(state.proxy) < 0) {
		settings.addToList(state.proxy);
	}
	Core::App().setCurrentProxy(
		state.proxy,
		MTP::ProxyData::Settings::Enabled);
	Core::App().saveSettings();

	const auto process = new QProcess(qApp);
	state.process = process;
	const auto logDir = cWorkingDir();
	QDir().mkpath(logDir);
	const auto logFile = logDir + u"ox_ws_proxy.log"_q;

	process->setWorkingDirectory(QFileInfo(nativeBin).absolutePath());
	process->setProgram(nativeBin);
	process->setArguments({
		u"--parent-pid"_q,
		QString::number(QCoreApplication::applicationPid()),
		u"--port"_q,
		QString::number(port),
		u"--secret"_q,
		secret,
		u"--log-file"_q,
		logFile,
	});
	process->setStandardOutputFile(QProcess::nullDevice());
	process->setStandardErrorFile(QProcess::nullDevice());
	QObject::connect(process, &QProcess::started, [=] {
		auto &settings = Core::App().settings().proxy();
		if (settings.indexInList(Instance().proxy) < 0) {
			settings.addToList(Instance().proxy);
		}
		Core::App().setCurrentProxy(
			Instance().proxy,
			MTP::ProxyData::Settings::Enabled);
	});
	QObject::connect(
		process,
		&QProcess::finished,
		[=](int, QProcess::ExitStatus) {
			auto &state = Instance();
			if (state.process == process) {
				state.process = nullptr;
				process->deleteLater();
				ScheduleRestart();
			}
		});
	QObject::connect(
		process,
		&QProcess::errorOccurred,
		[=](QProcess::ProcessError error) {
			if (error != QProcess::FailedToStart) {
				return;
			}
			auto &state = Instance();
			if (state.process == process) {
				state.process = nullptr;
				process->deleteLater();
			}
		});
	process->start();
	process->waitForStarted(300);
}

} // namespace

bool Available() {
	return !NativeBinary().isEmpty();
}

bool Enabled() {
	return Available() && Extera::Bool(u"ws_proxy"_q);
}

QString Version() {
	return u"1.11.4"_q;
}

int Port() {
	const auto &state = Instance();
	if (state.process && state.proxy.port > 0) {
		return int(state.proxy.port);
	}
	const auto saved = Extera::Int(u"ws_proxy_port"_q);
	return saved ? saved : kDefaultPort;
}

QString CurrentEndpoint() {
	return u"127.0.0.1:"_q + QString::number(Port());
}

rpl::producer<QString> statusTextValue() {
	return Extera::Config::Instance().boolChanges(u"ws_proxy"_q)
		| rpl::map([](bool enabled) {
			if (!Available()) {
				return u"Недоступен"_q;
			}
			return enabled
				? (u"Включен ("_q + CurrentEndpoint() + u")"_q)
				: u"Отключен"_q;
		});
}

bool IsOurs(const MTP::ProxyData &proxy) {
	return proxy.type == MTP::ProxyData::Type::Mtproto
		&& (proxy.host == u"127.0.0.1"_q || proxy.host == u"localhost"_q)
		&& (proxy.password.endsWith(Secret())
			|| (proxy.port >= kDefaultPort && proxy.port < kDefaultPort + kPortAttempts));
}

void CleanOurProxies() {
	auto &settings = Core::App().settings().proxy();
	const auto list = settings.list();
	auto changed = false;
	for (const auto &p : list) {
		if (IsOurs(p)) {
			if (settings.removeFromList(p)) {
				changed = true;
			}
		}
	}
	if (changed) {
		Core::App().saveSettings();
	}
}

void Start() {
	if (Enabled()) {
		Instance().restarts = 0;
		Launch();
	}
}

void Stop() {
	auto &state = Instance();
	state.stopping = true;
	gProxyActive.store(false, std::memory_order_release);
	if (state.autoTimer) {
		state.autoTimer->cancel();
	}
	if (state.restartTimer) {
		state.restartTimer->cancel();
	}
	if (const auto process = base::take(state.process)) {
		process->kill();
		process->waitForFinished(1000);
		process->deleteLater();
	}
	auto &settings = Core::App().settings().proxy();
	if (IsOurs(settings.selected())) {
		Core::App().setCurrentProxy(
			MTP::ProxyData(),
			MTP::ProxyData::Settings::Disabled);
	}
	CleanOurProxies();
	Core::App().saveSettings();
}

void Restart() {
	auto &state = Instance();
	if (!Available()) {
		return;
	}
	const auto now = crl::now();
	if (state.process
		&& state.process->state() != QProcess::NotRunning
		&& state.lastRestartAt > 0
		&& (now - state.lastRestartAt) < kRestartCooldown) {
		return;
	}
	state.lastRestartAt = now;
	state.stopping = false;
	state.restarts = 0;
	if (state.restartTimer) {
		state.restartTimer->cancel();
	}
	if (const auto process = base::take(state.process)) {
		if (process->state() != QProcess::NotRunning) {
			process->terminate();
			if (!process->waitForFinished(500)) {
				process->kill();
				process->waitForFinished(500);
			}
		}
		process->deleteLater();
	}
	Launch();
}

void StartAutoTimer() {
	auto &state = Instance();
	if (state.isConnected
		|| Enabled()
		|| !Available()
		|| !Extera::Bool(u"ws_proxy_auto"_q)) {
		return;
	}
	if (!state.autoTimer) {
		state.autoTimer = std::make_unique<base::Timer>([] {
			auto &state = Instance();
			if (!state.isConnected && !Enabled() && Available()) {
				SetEnabled(true);
			}
		});
	}
	if (!state.autoTimer->isActive()) {
		state.autoTimer->callOnce(kAutoEnableDelay);
	}
}

void HandleConnectionState(int32 connectionState) {
	auto &state = Instance();
	if (connectionState == MTP::ConnectedState) {
		state.isConnected = true;
		if (state.autoTimer) {
			state.autoTimer->cancel();
		}
		return;
	}
	state.isConnected = false;
	if (!Enabled() && Extera::Bool(u"ws_proxy_auto"_q)) {
		StartAutoTimer();
	}
}

void ApplyHttpProxy(QNetworkAccessManager *manager) {
	if (!manager) {
		return;
	}
	if (gProxyActive.load(std::memory_order_acquire)) {
		manager->setProxy(QNetworkProxy(
			QNetworkProxy::HttpProxy,
			u"127.0.0.1"_q,
			quint16(gProxyPort.load(std::memory_order_relaxed))));
	} else {
		manager->setProxy(QNetworkProxy(QNetworkProxy::NoProxy));
	}
}

void PrepareFrontedRequest(QNetworkRequest &request) {
	if (!gProxyActive.load(std::memory_order_acquire)) {
		return;
	}
	auto url = request.url();
	const auto host = url.host().toLower();
	if (host.isEmpty()
		|| host == u"127.0.0.1"_q
		|| host == u"localhost"_q
		|| host.contains(u"github.com"_q)
		|| host.contains(u"githubusercontent.com"_q)) {
		return;
	}
}

void SetEnabled(bool enabled) {
	Extera::Config::Instance().setBool(u"ws_proxy"_q, enabled);
	if (enabled) {
		auto &state = Instance();
		if (state.autoTimer) {
			state.autoTimer->cancel();
		}
		state.restarts = 0;
		Launch();
	} else {
		Stop();
	}
}

} // namespace Extera::WsProxy
