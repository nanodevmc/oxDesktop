#include "extera/extera_ws_proxy.h"

#include "extera/extera_config.h"
#include "core/application.h"
#include "core/core_settings.h"
#include "mtproto/mtproto_proxy_data.h"
#include "base/timer.h"

#include <QtCore/QDir>
#include <QtCore/QFileInfo>
#include <QtCore/QProcess>
#include <QtCore/QRandomGenerator>
#include <QtCore/QStandardPaths>
#include <QtNetwork/QTcpServer>

namespace Extera::WsProxy {
namespace {

constexpr auto kDefaultPort = 1443;
constexpr auto kPortAttempts = 20;
constexpr auto kRestartDelay = crl::time(3000);
constexpr auto kMaxRestarts = 5;

struct State {
	QProcess *process = nullptr;
	MTP::ProxyData proxy;
	std::unique_ptr<base::Timer> restartTimer;
	int restarts = 0;
	bool stopping = false;
};

State &Instance() {
	static auto result = State();
	return result;
}

[[nodiscard]] QString PythonDir() {
	for (const auto &cand : {
		cExeDir() + u"python/"_q,
		cWorkingDir() + u"python/"_q,
		cWorkingDir() + u"Telegram/SourceFiles/extera/python/"_q,
		cExeDir() + u"Telegram/SourceFiles/extera/python/"_q,
	}) {
		if (QDir(cand).exists()) {
			return cand;
		}
	}
	return cExeDir() + u"python/"_q;
}

[[nodiscard]] QString Interpreter() {
#ifdef Q_OS_WIN
	const auto localW = PythonDir() + u"pythonw.exe"_q;
	if (QFile::exists(localW)) {
		return localW;
	}
	const auto local = PythonDir() + u"python.exe"_q;
	if (QFile::exists(local)) {
		return local;
	}
	const auto foundW = QStandardPaths::findExecutable(u"pythonw"_q);
	if (!foundW.isEmpty() && QFile::exists(foundW)) {
		return foundW;
	}
	const auto found = QStandardPaths::findExecutable(u"python"_q);
	if (!found.isEmpty() && QFile::exists(found)) {
		return found;
	}
	return localW;
#else
	const auto local3 = PythonDir() + u"bin/python3"_q;
	if (QFile::exists(local3)) {
		return local3;
	}
	const auto local = PythonDir() + u"bin/python"_q;
	if (QFile::exists(local)) {
		return local;
	}
	const auto found3 = QStandardPaths::findExecutable(u"python3"_q);
	if (!found3.isEmpty() && QFile::exists(found3)) {
		return found3;
	}
	const auto found = QStandardPaths::findExecutable(u"python"_q);
	if (!found.isEmpty() && QFile::exists(found)) {
		return found;
	}
	return local3;
#endif
}

[[nodiscard]] QString Script() {
	const auto candidates = {
		PythonDir() + u"extera/tgws/exd_tgws.py"_q,
		PythonDir() + u"tgws/exd_tgws.py"_q,
		cExeDir() + u"python/extera/tgws/exd_tgws.py"_q,
		cExeDir() + u"python/tgws/exd_tgws.py"_q,
		cWorkingDir() + u"python/extera/tgws/exd_tgws.py"_q,
		cWorkingDir() + u"python/tgws/exd_tgws.py"_q,
		cExeDir() + u"Telegram/SourceFiles/extera/python/tgws/exd_tgws.py"_q,
		cWorkingDir() + u"Telegram/SourceFiles/extera/python/tgws/exd_tgws.py"_q,
	};
	for (const auto &candidate : candidates) {
		if (QFile::exists(candidate)) {
			return candidate;
		}
	}
	return PythonDir() + u"extera/tgws/exd_tgws.py"_q;
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
	if (state.process || !Available()) {
		return;
	}
	state.stopping = false;
	CleanOurProxies();
	const auto port = ChoosePort();
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
	const auto scriptFile = Script();
	const auto pyDir = QDir(PythonDir()).exists()
		? PythonDir()
		: QFileInfo(scriptFile).absolutePath();
	process->setWorkingDirectory(pyDir);
	process->setProgram(Interpreter());
	const auto logDir = cWorkingDir() + u"tdata/"_q;
	QDir().mkpath(logDir);
	const auto logFile = logDir + u"tgws.log"_q;
	process->setArguments({
		u"-u"_q,
		scriptFile,
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
}

} // namespace

bool Available() {
	const auto interp = Interpreter();
	const auto script = Script();
	return !interp.isEmpty()
		&& !script.isEmpty()
		&& QFile::exists(interp)
		&& QFile::exists(script);
}

bool Enabled() {
	return Available() && Extera::Bool(u"ws_proxy"_q);
}

QString Version() {
	return u"1.11.4"_q;
}

int Port() {
	return ChoosePort();
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
			settings.removeFromList(p);
			changed = true;
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
	if (state.restartTimer) {
		state.restartTimer->cancel();
	}
	if (const auto process = base::take(state.process)) {
		process->kill();
		process->waitForFinished(1000);
		process->deleteLater();
	}
	const auto &settings = Core::App().settings().proxy();
	if (settings.isEnabled() && IsOurs(settings.selected())) {
		Core::App().setCurrentProxy(
			settings.selected(),
			MTP::ProxyData::Settings::Disabled);
	}
	CleanOurProxies();
	Core::App().saveSettings();
}

void SetEnabled(bool enabled) {
	Extera::Config::Instance().setBool(u"ws_proxy"_q, enabled);
	if (enabled) {
		Start();
	} else {
		Stop();
	}
}

} // namespace Extera::WsProxy
