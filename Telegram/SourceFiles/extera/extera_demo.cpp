#include "extera/extera_demo.h"

#include "core/application.h"
#include "window/window_controller.h"
#include "window/window_session_controller.h"
#include "settings/sections/settings_extera.h"
#include "extera/extera_full_player.h"
#include "base/call_delayed.h"

#include <QtGui/QGuiApplication>
#include <QtGui/QPixmap>
#include <QtCore/QDir>
#include <QtCore/QFileInfo>

namespace Extera::Demo {
namespace {

bool gEnabled = false;
QString gView = u"settings"_q;
QString gScreenshotPath;
int gDelayMs = 1000;
bool gAutoExit = false;

} // namespace

bool IsActive() {
	return gEnabled || !gScreenshotPath.isEmpty();
}

QString View() {
	return gView;
}

QString ScreenshotPath() {
	return gScreenshotPath;
}

int DelayMs() {
	return gDelayMs;
}

bool AutoExit() {
	return gAutoExit;
}

void SetEnabled(bool enabled) {
	gEnabled = enabled;
}

void SetView(const QString &view) {
	gView = view;
	gEnabled = true;
}

void SetScreenshot(const QString &path) {
	gScreenshotPath = path;
	gEnabled = true;
}

void SetDelay(int delayMs) {
	gDelayMs = delayMs;
}

void SetAutoExit(bool exit) {
	gAutoExit = exit;
}

void Start(not_null<Window::Controller*> window) {
	const auto targetView = View().toLower();
	const auto session = window->sessionController();

	if (targetView == u"appearance"_q) {
		if (session) {
			session->showSettings(Settings::ExteraAppearanceId());
		} else {
			window->showSettings();
		}
	} else if (targetView == u"chats"_q) {
		if (session) {
			session->showSettings(Settings::ExteraGeneralId());
		} else {
			window->showSettings();
		}
	} else if (targetView == u"plugins"_q) {
		if (session) {
			session->showSettings(Settings::ExteraPluginsId());
		} else {
			window->showSettings();
		}
	} else if (targetView == u"player"_q) {
		if (session) {
			Extera::FullPlayer::Show(session);
		} else {
			window->showSettings();
		}
	} else if (targetView == u"badges"_q) {
		if (session) {
			Settings::ShowExteraSupportBox(session);
		} else {
			window->showSettings();
		}
	} else if (targetView == u"settings"_q || targetView == u"extera"_q) {
		if (session) {
			session->showSettings(Settings::ExteraId());
		} else {
			window->showSettings();
		}
	}

	const auto path = ScreenshotPath();
	const auto delay = DelayMs();
	const auto exit = AutoExit();

	base::call_delayed(std::chrono::milliseconds(delay), window->widget(), [=] {
		if (!path.isEmpty()) {
			const auto widget = window->widget();
			const auto pixmap = widget->grab();
			const auto file = QFileInfo(path);
			QDir().mkpath(file.absolutePath());
			pixmap.save(path, "PNG");
		}
		if (exit) {
			QGuiApplication::quit();
		}
	});
}

} // namespace Extera::Demo
