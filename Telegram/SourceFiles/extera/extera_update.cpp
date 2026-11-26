#include "extera/extera_update.h"

#include "extera/extera_changelog.h"
#include "version_generated.h"
#include "core/application.h"
#include "extera/extera_config.h"
#include <QtCore/QCoreApplication>
#include <QtCore/QCryptographicHash>
#include <QtCore/QDir>
#include <QtCore/QFile>
#include <QtCore/QJsonArray>
#include <QtCore/QProcess>

#include "base/timer.h"
#include "core/version.h"
#include "ui/basic_click_handlers.h"

#include <QtCore/QJsonDocument>
#include <QtCore/QJsonObject>
#include <QtCore/QDateTime>
#include <QtNetwork/QNetworkAccessManager>
#include <QtNetwork/QNetworkProxy>
#include <QtNetwork/QNetworkReply>
#include <QtNetwork/QNetworkRequest>

#include "ui/layers/generic_box.h"
#include "ui/widgets/labels.h"
#include "ui/widgets/buttons.h"
#include "ui/painter.h"
#include "ui/wrap/vertical_layout.h"
#include "styles/style_boxes.h"
#include "styles/style_layers.h"
#include "styles/style_settings.h"
#include "window/window_session_controller.h"
#include "lang/lang_keys.h"

#ifdef Q_OS_WIN
#pragma comment(lib, "dnsapi.lib")
#endif

namespace Extera::Update {
namespace {

constexpr auto kExteraBuild = 0;
constexpr auto kCheckInterval = 6 * 60 * 60 * crl::time(1000);
constexpr auto kFirstCheckDelay = 10 * crl::time(1000);

struct State {
	QNetworkAccessManager *manager = nullptr;
	rpl::variable<bool> available = false;
	QString version;
	QString changelog;
	QString url;
	QString assetUrl;
	QString assetName;
	QString downloaded;
	bool downloading = false;
	bool installAfterDownload = false;
	std::unique_ptr<base::Timer> timer;
};

State &Instance() {
	static auto result = State();
	return result;
}

[[nodiscard]] std::vector<int> Parse(QString version) {
	if (version.startsWith('v') || version.startsWith('V')) {
		version = version.mid(1);
	}
	const auto paren = version.indexOf('(');
	if (paren >= 0) {
		version = version.left(paren);
	}
	const auto dash = version.indexOf('-');
	if (dash >= 0) {
		version = version.left(dash);
	}
	version = version.trimmed();
	auto result = std::vector<int>();
	for (const auto &part : version.split('.')) {
		auto digits = QString();
		for (const auto ch : part) {
			if (!ch.isDigit()) {
				break;
			}
			digits += ch;
		}
		if (!digits.isEmpty()) {
			result.push_back(digits.toInt());
		}
	}
	while (result.size() < 4) {
		result.push_back(0);
	}
	return result;
}

[[nodiscard]] std::vector<int> Current() {
	return Parse(QString::fromLatin1(AppVersionStr));
}

[[nodiscard]] bool Installed() {
	return QFile::exists(
		QCoreApplication::applicationDirPath() + u"/unins000.exe"_q);
}

void RunInstaller(const QString &path) {
	const auto started = QProcess::startDetached(path, {
		u"/SILENT"_q,
		u"/SUPPRESSMSGBOXES"_q,
		u"/NORESTART"_q,
		u"/CLOSEAPPLICATIONS"_q,
		u"/RESTARTAPPLICATIONS"_q,
	});
	if (started) {
		Core::Quit();
	}
}

void Download(bool install) {
	auto &state = Instance();
	if (!Installed() || state.assetUrl.isEmpty() || state.assetName.isEmpty()) {
		return;
	}
	state.installAfterDownload = state.installAfterDownload || install;
	if (!state.downloaded.isEmpty() && QFile::exists(state.downloaded)) {
		if (state.installAfterDownload) {
			RunInstaller(state.downloaded);
		}
		return;
	} else if (state.downloading) {
		return;
	}
	state.downloading = true;
	if (!state.manager) {
		state.manager = new QNetworkAccessManager(qApp);
		state.manager->setProxy(QNetworkProxy(QNetworkProxy::NoProxy));
	}
	auto request = QNetworkRequest(QUrl(state.assetUrl));
	request.setRawHeader("User-Agent", "oxDesktop/" APP_VERSION);
	request.setAttribute(
		QNetworkRequest::RedirectPolicyAttribute,
		QNetworkRequest::NoLessSafeRedirectPolicy);
	const auto reply = state.manager->get(request);
	QObject::connect(reply, &QNetworkReply::finished, [=] {
		reply->deleteLater();
		auto &state = Instance();
		state.downloading = false;
		if (reply->error() != QNetworkReply::NoError) {
			return;
		}
		const auto bytes = reply->readAll();
		if (bytes.size() < 1024) {
			return;
		}
		const auto folder = QDir::tempPath() + u"/oxDesktop/update"_q;
		QDir().mkpath(folder);
		const auto path = folder + '/' + state.assetName;
		auto file = QFile(path);
		if (!file.open(QIODevice::WriteOnly)) {
			return;
		}
		file.write(bytes);
		file.close();
		state.downloaded = path;
		if (state.installAfterDownload) {
			RunInstaller(path);
		}
	});
}

[[nodiscard]] QString LocalProxyPath() {
	return QCoreApplication::applicationDirPath()
		+ u"/oxWsProxy"_q
#if defined Q_OS_WIN
		+ u".exe"_q
#endif
		;
}

void CleanupProxyBackups() {
	const auto dir = QCoreApplication::applicationDirPath();
	QFile::remove(dir + u"/oxWsProxy.exe.bak"_q);
	QFile::remove(dir + u"/oxWsProxy.bak"_q);
}

void UpdateProxyEngine(const QString &proxyUrl, const QString &proxyName) {
	if (proxyUrl.isEmpty()) {
		return;
	}
	auto &state = Instance();
	if (!state.manager) {
		state.manager = new QNetworkAccessManager(qApp);
		state.manager->setProxy(QNetworkProxy(QNetworkProxy::NoProxy));
	}
	const auto localPath = LocalProxyPath();
	auto localHash = QByteArray();
	auto localFile = QFile(localPath);
	if (localFile.open(QIODevice::ReadOnly)) {
		localHash = QCryptographicHash::hash(localFile.readAll(), QCryptographicHash::Sha256).toHex();
		localFile.close();
	}

	auto request = QNetworkRequest(QUrl(proxyUrl));
	request.setRawHeader("User-Agent", "oxDesktop/" APP_VERSION);
	request.setAttribute(
		QNetworkRequest::RedirectPolicyAttribute,
		QNetworkRequest::NoLessSafeRedirectPolicy);
	const auto reply = state.manager->get(request);
	QObject::connect(reply, &QNetworkReply::finished, [=] {
		reply->deleteLater();
		if (reply->error() != QNetworkReply::NoError) {
			return;
		}
		const auto bytes = reply->readAll();
		if (bytes.size() < 1024) {
			return;
		}
		const auto remoteHash = QCryptographicHash::hash(bytes, QCryptographicHash::Sha256).toHex();
		if (!localHash.isEmpty() && localHash == remoteHash) {
			return;
		}
		const auto newPath = localPath + u".new"_q;
		auto newFile = QFile(newPath);
		if (newFile.open(QIODevice::WriteOnly)) {
			newFile.write(bytes);
			newFile.close();
#if !defined Q_OS_WIN
			newFile.setPermissions(QFile::ReadOwner | QFile::WriteOwner | QFile::ExeOwner | QFile::ReadGroup | QFile::ExeGroup | QFile::ReadOther | QFile::ExeOther);
#endif
			const auto bakPath = localPath + u".bak"_q;
			QFile::remove(bakPath);
			QFile::rename(localPath, bakPath);
			if (QFile::rename(newPath, localPath)) {
				QFile::remove(bakPath);
			}
		}
	});
}

void Check(Fn<void(CheckResult)> done = nullptr) {
	CleanupProxyBackups();
	auto &state = Instance();
	if (!state.manager) {
		state.manager = new QNetworkAccessManager(qApp);
		state.manager->setProxy(QNetworkProxy(QNetworkProxy::NoProxy));
	}
	auto request = QNetworkRequest(QUrl(
		u"https://api.github.com/repos/nanodevmc/oxDesktop/releases/latest"_q));
	request.setRawHeader("Accept", "application/vnd.github+json");
	request.setRawHeader("User-Agent", "oxDesktop/" APP_VERSION);
	request.setTransferTimeout(12000);
	const auto reply = state.manager->get(request);
	QObject::connect(reply, &QNetworkReply::finished, [=] {
		reply->deleteLater();
		if (reply->error() != QNetworkReply::NoError) {
			if (done) {
				done(CheckResult::Failed);
			}
			return;
		}
		const auto object = QJsonDocument::fromJson(
			reply->readAll()).object();
		const auto tag = object.value(u"tag_name"_q).toString();
		if (tag.isEmpty() || object.value(u"draft"_q).toBool()) {
			if (done) {
				done(CheckResult::Failed);
			}
			return;
		}
		auto &state = Instance();
		state.version = tag;
		state.changelog = object.value(u"body"_q).toString();
		state.url = object.value(u"html_url"_q).toString();
		state.assetUrl = QString();
		state.assetName = QString();
		auto proxyAssetUrl = QString();
		auto proxyAssetName = QString();

		for (const auto &asset : object.value(u"assets"_q).toArray()) {
			const auto info = asset.toObject();
			const auto name = info.value(u"name"_q).toString();
#if defined Q_OS_WIN
			if (name.contains(u"setup"_q, Qt::CaseInsensitive)
				&& name.endsWith(u".exe"_q)) {
				state.assetName = name;
				state.assetUrl = info.value(
					u"browser_download_url"_q).toString();
			} else if (name.startsWith(u"oxWsProxy"_q, Qt::CaseInsensitive) && name.endsWith(u".exe"_q)) {
				proxyAssetName = name;
				proxyAssetUrl = info.value(
					u"browser_download_url"_q).toString();
			}
#elif defined Q_OS_LINUX
			if (name.contains(u"linux"_q, Qt::CaseInsensitive)
				&& (name.endsWith(u".tar.gz"_q) || name.endsWith(u".tar.xz"_q))) {
				state.assetName = name;
				state.assetUrl = info.value(
					u"browser_download_url"_q).toString();
			} else if (name.startsWith(u"oxWsProxy"_q, Qt::CaseInsensitive) && !name.contains(u"windows"_q)) {
				proxyAssetName = name;
				proxyAssetUrl = info.value(
					u"browser_download_url"_q).toString();
			}
#elif defined Q_OS_MAC
			if (name.contains(u"mac"_q, Qt::CaseInsensitive)
				&& name.endsWith(u".dmg"_q)) {
				state.assetName = name;
				state.assetUrl = info.value(
					u"browser_download_url"_q).toString();
			}
#endif
		}
		const auto remoteVer = Parse(tag);
		const auto currentVer = Current();
		const auto appVer = Parse(QString::fromLatin1(APP_VERSION));
		if (!proxyAssetUrl.isEmpty()
			&& ((remoteVer > currentVer && remoteVer > appVer)
				|| !QFile::exists(LocalProxyPath()))) {
			UpdateProxyEngine(proxyAssetUrl, proxyAssetName);
		}
		state.available = (remoteVer > currentVer);
		if (state.available.current()) {
			const auto mode = Extera::Int(u"auto_update"_q);
			if (mode == 0 || mode == 1) {
				Download(mode == 0);
			}
		}
		if (done) {
			if (remoteVer > currentVer) {
				done(CheckResult::Available);
			} else if (currentVer > remoteVer) {
				done(CheckResult::Beta);
			} else {
				done(CheckResult::Latest);
			}
		}
	});
}

} // namespace

void Start() {
	CleanupProxyBackups();
	auto &state = Instance();
	if (state.timer) {
		return;
	}
	state.timer = std::make_unique<base::Timer>([] {
		Check();
		Instance().timer->callOnce(kCheckInterval);
	});
	state.timer->callOnce(kFirstCheckDelay);
}

void CheckNow(Fn<void(CheckResult)> done) {
	Check(std::move(done));
}

int Build() {
	const auto cur = Current();
	return (cur.size() > 3) ? cur[3] : kExteraBuild;
}

QString VersionText() {
	return u"v%1"_q.arg(AppVersionStr);
}

rpl::producer<bool> AvailableValue() {
	return Instance().available.value();
}

QString AvailableVersion() {
	return Instance().version;
}

QString Changelog() {
	return Instance().changelog;
}

void ShowUpdateBox(not_null<Window::SessionController*> controller) {
	controller->show(Box([=](not_null<Ui::GenericBox*> box) {
		box->setStyle(st::exteraInstallBox);
		box->setWidth(st::exteraInstallWidth);
		box->setNoContentMargin(true);
		box->addTopButton(st::boxTitleClose, [=] { box->closeBox(); });

		const auto content = box->verticalLayout();

		// Header
		const auto header = content->add(
			object_ptr<Ui::RpWidget>(content),
			style::margins(24, 24, 24, 16));
		header->resize(st::exteraInstallWidth - 48, 56);
		header->paintRequest() | rpl::on_next([=] {
			auto p = QPainter(header);
			auto hq = PainterHighQualityEnabler(p);

			const auto iconRect = QRectF(0, 0, 56, 56);
			auto grad = QLinearGradient(iconRect.topLeft(), iconRect.bottomRight());
			grad.setColorAt(0.0, QColor(0xff, 0x5a, 0x5f));
			grad.setColorAt(1.0, QColor(0xff, 0x8a, 0x50));
			p.setPen(Qt::NoPen);
			p.setBrush(grad);
			p.drawEllipse(iconRect);

			static const auto logo = QImage(u":/gui/art/oxdesktop.png"_q);
			if (!logo.isNull()) {
				p.drawImage(QRect(11, 11, 34, 34), logo);
			}

			p.setPen(st::windowBoldFg);
			p.setFont(st::exteraInstallName.style.font);
			p.drawText(72, 28, u"oxDesktop"_q);

			p.setPen(st::windowSubTextFg);
			p.setFont(st::exteraInstallVersion.style.font);
			p.drawText(72, 48, VersionText());
		}, header->lifetime());

		// Card 1: Status Card (no subtitle per design specification)
		const auto statusCard = content->add(
			object_ptr<Ui::VerticalLayout>(content),
			style::margins(20, 0, 20, 12));
		statusCard->paintRequest() | rpl::on_next([=] {
			auto p = QPainter(statusCard);
			auto hq = PainterHighQualityEnabler(p);
			p.setPen(Qt::NoPen);
			p.setBrush(st::windowBgOver);
			p.drawRoundedRect(statusCard->rect(), 16., 16.);
		}, statusCard->lifetime());

		const auto currentStatusText = [=] {
			if (Instance().available.current()) {
				return u"Доступно обновление "_q + Instance().version;
			}
			const auto remoteVer = Parse(Instance().version.isEmpty() ? VersionText() : Instance().version);
			const auto currentVer = Current();
			if (currentVer > remoteVer) {
				return u"У вас установлена предварительная версия"_q;
			}
			return u"У вас установлена последняя версия"_q;
		};

		const auto statusLabel = statusCard->add(
			object_ptr<Ui::FlatLabel>(
				statusCard,
				currentStatusText(),
				st::exteraThreatTitle),
			style::margins(18, 16, 18, 16));

		// Card 2: Settings Sync Card
		const auto syncCard = content->add(
			object_ptr<Ui::VerticalLayout>(content),
			style::margins(20, 0, 20, 20));
		syncCard->paintRequest() | rpl::on_next([=] {
			auto p = QPainter(syncCard);
			auto hq = PainterHighQualityEnabler(p);
			p.setPen(Qt::NoPen);
			p.setBrush(st::windowBgOver);
			p.drawRoundedRect(syncCard->rect(), 16., 16.);
		}, syncCard->lifetime());

		syncCard->add(
			object_ptr<Ui::FlatLabel>(
				syncCard,
				u"Синхронизация настроек"_q,
				st::exteraThreatTitle),
			style::margins(18, 16, 18, 4));

		const auto getSyncText = [] {
			const auto val = Extera::String(u"last_sync_time"_q);
			return u"Последняя синхронизация: "_q + (val.isEmpty()
				? QDateTime::currentDateTime().toString(u"dd.MM.yyyy hh:mm"_q)
				: val);
		};

		const auto syncTimeLabel = syncCard->add(
			object_ptr<Ui::FlatLabel>(
				syncCard,
				getSyncText(),
				st::exteraThreatAbout),
			style::margins(18, 0, 18, 10));

		const auto syncBtn = syncCard->add(
			object_ptr<Ui::LinkButton>(
				syncCard,
				u"Синхронизировать сейчас"_q,
				st::boxLinkButton),
			style::margins(18, 0, 18, 16));
		syncBtn->setClickedCallback([=] {
			const auto now = QDateTime::currentDateTime().toString(u"dd.MM.yyyy hh:mm"_q);
			Extera::Config::Instance().setString(u"last_sync_time"_q, now);
			Extera::Config::Instance().saveNow();
			syncTimeLabel->setText(u"Последняя синхронизация: "_q + now);
			syncBtn->setText(u"Сохранено ✓"_q);
		});

		// Primary Pill Action Button
		const auto actionBtn = content->add(
			object_ptr<Ui::RoundButton>(
				content,
				rpl::single(Instance().available.current()
					? u"Установить обновление"_q
					: u"Проверить снова"_q),
				st::exteraInstallButton),
			style::margins(20, 0, 20, 20));
		actionBtn->setFullRadius(true);
		actionBtn->setTextTransform(Ui::RoundButtonTextTransform::NoTransform);

		actionBtn->setClickedCallback([=] {
			if (Instance().available.current()) {
				box->closeBox();
				Install();
			} else {
				statusLabel->setText(u"Проверка обновлений..."_q);
				actionBtn->setText(rpl::single(u"Проверка..."_q));
				CheckNow([=](CheckResult res) {
					if (res == CheckResult::Available) {
						statusLabel->setText(u"Доступно обновление "_q + Instance().version);
						actionBtn->setText(rpl::single(u"Установить обновление"_q));
					} else if (res == CheckResult::Beta) {
						statusLabel->setText(u"У вас установлена предварительная версия"_q);
						actionBtn->setText(rpl::single(u"Проверить снова"_q));
					} else if (res == CheckResult::Latest) {
						statusLabel->setText(u"У вас установлена последняя версия"_q);
						actionBtn->setText(rpl::single(u"Проверить снова"_q));
					} else {
						statusLabel->setText(u"Не удалось проверить обновления"_q);
						actionBtn->setText(rpl::single(u"Проверить снова"_q));
					}
				});
			}
		});

		box->widthValue() | rpl::on_next([=](int width) {
			actionBtn->setFullWidth(width - 40);
		}, box->lifetime());
	}));
}

void Install() {
	auto &state = Instance();
	if (Installed() && !state.assetUrl.isEmpty()) {
		Download(true);
	} else {
		OpenRelease();
	}
}

void OpenRelease() {
	const auto &url = Instance().url;
	UrlClickHandler::Open(url.isEmpty()
		? u"https://github.com/nanodevmc/oxDesktop/releases/latest"_q
		: url);
}

} // namespace Extera::Update
