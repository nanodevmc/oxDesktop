#include "extera/extera_demo.h"

#include "core/application.h"
#include "window/window_controller.h"
#include "window/window_session_controller.h"
#include "window/themes/window_theme.h"
#include "settings/sections/settings_extera.h"
#include "settings/settings_common.h"
#include "extera/extera_full_player.h"
#include "base/call_delayed.h"
#include "ui/layers/generic_box.h"
#include "ui/widgets/buttons.h"
#include "ui/widgets/labels.h"
#include "ui/wrap/padding_wrap.h"
#include "ui/wrap/vertical_layout.h"
#include "ui/painter.h"
#include "ui/vertical_list.h"
#include "window/main_window.h"
#include "styles/style_basic.h"
#include "styles/style_boxes.h"
#include "styles/style_layers.h"
#include "styles/style_settings.h"
#include "styles/style_intro.h"

#include <QtGui/QGuiApplication>
#include <QtGui/QPixmap>
#include <QtCore/QDir>
#include <QtCore/QFileInfo>
#include <iostream>

namespace Extera::Demo {
namespace {

bool gEnabled = false;
QString gView = u"settings"_q;
QString gScreenshotPath;
int gDelayMs = 1000;
bool gAutoExit = false;

void ShowDemoSettings(not_null<Window::Controller*> window) {
	window->show(Box([=](not_null<Ui::GenericBox*> box) {
		box->setTitle(u"Настройки oxDesktop"_q);
		box->setWidth(st::boxWideWidth);
		box->addTopButton(st::boxTitleClose, [=] { box->closeBox(); });

		const auto header = box->addRow(
			object_ptr<Ui::FixedHeightWidget>(box, 92),
			style::margins(16, 8, 16, 6));
		header->paintRequest() | rpl::on_next([=] {
			auto p = QPainter(header);
			auto hq = PainterHighQualityEnabler(p);
			const auto rect = QRectF(0, 0, header->width(), header->height()).adjusted(1, 1, -1, -1);
			auto bgGrad = QLinearGradient(0, 0, header->width(), header->height());
			bgGrad.setColorAt(0., QColor(28, 22, 22, 240));
			bgGrad.setColorAt(1., QColor(18, 17, 19, 245));
			p.setPen(QPen(QColor(218, 48, 24, 90), 1.2));
			p.setBrush(bgGrad);
			p.drawRoundedRect(rect, 10, 10);

			const auto &logo = Window::Logo();
			p.drawImage(QRect(16, 11, 70, 70), logo);

			p.setPen(Qt::white);
			p.setFont(st::boxTitleFont);
			p.drawText(98, 38, u"oxDesktop v7.3.3"_q);
			p.setPen(QColor(180, 185, 192));
			p.setFont(st::normalFont);
			p.drawText(98, 62, u"Официальная сборка • Канал обновлений @oxDesktop"_q);
		}, header->lifetime());

		auto container = box->verticalLayout();
		Ui::AddDivider(container);

		Settings::AddButtonWithLabel(
			container,
			rpl::single(u"Встроенный обход блокировок (TgWsProxy)"_q),
			rpl::single(u"Активен (v1.11.4)"_q),
			st::settingsButton);

		Settings::AddButtonWithLabel(
			container,
			rpl::single(u"Режим стримера (защита приватности)"_q),
			rpl::single(u"Отключен"_q),
			st::settingsButton);

		Settings::AddButtonWithLabel(
			container,
			rpl::single(u"Синхронизация текстов песен (Lyrics)"_q),
			rpl::single(u"Включена (Genius / Spotify)"_q),
			st::settingsButton);

		Settings::AddButtonWithLabel(
			container,
			rpl::single(u"Проверка обновлений oxDesktop"_q),
			rpl::single(u"Версия актуальна"_q),
			st::settingsButton);
	}));
}

void ShowDemoAppearance(not_null<Window::Controller*> window) {
	window->show(Box([=](not_null<Ui::GenericBox*> box) {
		box->setTitle(u"Внешний вид oxDesktop"_q);
		box->setWidth(st::boxWideWidth);
		box->addTopButton(st::boxTitleClose, [=] { box->closeBox(); });

		const auto preview = box->addRow(
			object_ptr<Ui::FixedHeightWidget>(box, 118),
			style::margins(16, 8, 16, 6));
		preview->paintRequest() | rpl::on_next([=] {
			auto p = QPainter(preview);
			auto hq = PainterHighQualityEnabler(p);
			const auto w = preview->width();
			const auto h = preview->height();

			const auto cardW = (w - 3 * 10) / 4;
			const struct ThemeCard {
				QString name;
				QColor top;
				QColor bottom;
				bool active;
			} cards[] = {
				{ u"Aero Delta"_q, QColor(218, 48, 24), QColor(24, 20, 22), true },
				{ u"Tinted Night"_q, QColor(36, 44, 52), QColor(22, 26, 31), false },
				{ u"Day Classic"_q, QColor(228, 238, 248), QColor(255, 255, 255), false },
				{ u"OLED Black"_q, QColor(18, 18, 18), QColor(0, 0, 0), false },
			};

			for (int i = 0; i < 4; ++i) {
				const auto x = i * (cardW + 10);
				const auto cardRect = QRectF(x, 2, cardW, h - 4);
				auto grad = QLinearGradient(x, 2, x, h - 2);
				grad.setColorAt(0., cards[i].top);
				grad.setColorAt(1., cards[i].bottom);

				p.setPen(cards[i].active ? QPen(QColor(255, 85, 51), 2.) : QPen(QColor(255, 255, 255, 35), 1.));
				p.setBrush(grad);
				p.drawRoundedRect(cardRect, 8, 8);

				p.setPen(Qt::NoPen);
				p.setBrush(QColor(255, 255, 255, 55));
				p.drawRoundedRect(QRectF(x + 8, 12, cardW - 16, 10), 3, 3);
				p.drawRoundedRect(QRectF(x + 8, 28, cardW * 0.6, 12), 3, 3);
				p.setBrush(cards[i].active ? QColor(255, 85, 51, 180) : QColor(255, 255, 255, 75));
				p.drawRoundedRect(QRectF(x + cardW * 0.32, 48, cardW * 0.58, 12), 3, 3);

				p.setPen(cards[i].active ? QColor(255, 95, 60) : Qt::white);
				p.setFont(cards[i].active ? st::semiboldFont : st::normalFont);
				p.drawText(QRectF(x, h - 24, cardW, 18), Qt::AlignCenter, cards[i].name);
			}
		}, preview->lifetime());

		auto container = box->verticalLayout();
		Ui::AddDivider(container);

		Settings::AddButtonWithLabel(
			container,
			rpl::single(u"Иконка приложения"_q),
			rpl::single(u"Aero Delta (Стелс)"_q),
			st::settingsButton);

		Settings::AddButtonWithLabel(
			container,
			rpl::single(u"Стиль интерфейса"_q),
			rpl::single(u"Liquid Glass + Material Design 3"_q),
			st::settingsButton);

		Settings::AddButtonWithLabel(
			container,
			rpl::single(u"Анимации и эффекты перехода"_q),
			rpl::single(u"Включены (Плавные 60 FPS)"_q),
			st::settingsButton);

		Settings::AddButtonWithLabel(
			container,
			rpl::single(u"Размытие фона и прозрачность"_q),
			rpl::single(u"Акрил (Liquid Glass)"_q),
			st::settingsButton);
	}));
}

void ShowDemoPlugins(not_null<Window::Controller*> window) {
	window->show(Box([=](not_null<Ui::GenericBox*> box) {
		box->setTitle(u"Менеджер плагинов oxDesktop"_q);
		box->setWidth(st::boxWideWidth);
		box->addTopButton(st::boxTitleClose, [=] { box->closeBox(); });

		const auto engine = box->addRow(
			object_ptr<Ui::FixedHeightWidget>(box, 52),
			style::margins(16, 6, 16, 6));
		engine->paintRequest() | rpl::on_next([=] {
			auto p = QPainter(engine);
			auto hq = PainterHighQualityEnabler(p);
			const auto rect = QRectF(0, 0, engine->width(), engine->height()).adjusted(1, 1, -1, -1);
			auto grad = QLinearGradient(0, 0, engine->width(), engine->height());
			grad.setColorAt(0., QColor(24, 28, 25, 230));
			grad.setColorAt(1., QColor(18, 20, 19, 240));
			p.setPen(QPen(QColor(46, 204, 113, 110), 1.2));
			p.setBrush(grad);
			p.drawRoundedRect(rect, 8, 8);

			p.setPen(QColor(46, 204, 113));
			p.setFont(st::semiboldFont);
			p.drawText(16, 24, u"● Движок плагинов активен"_q);
			p.setPen(QColor(180, 190, 185));
			p.setFont(st::normalFont);
			p.drawText(16, 42, u"28 расширений подключено • Встроенная среда Python 3.11"_q);
		}, engine->lifetime());

		auto container = box->verticalLayout();
		Ui::AddDivider(container);

		Settings::AddButtonWithLabel(
			container,
			rpl::single(u"Установленные плагины"_q),
			rpl::single(u"28 активных расширений"_q),
			st::settingsButton);

		Settings::AddButtonWithLabel(
			container,
			rpl::single(u"Синхронизация текстов песен"_q),
			rpl::single(u"Включена (Genius / Spotify)"_q),
			st::settingsButton);

		Settings::AddButtonWithLabel(
			container,
			rpl::single(u"Каталог расширений сообщества"_q),
			rpl::single(u"Доступно в репозитории"_q),
			st::settingsButton);

		Settings::AddButtonWithLabel(
			container,
			rpl::single(u"Безопасная изоляция скриптов"_q),
			rpl::single(u"Песочница активна"_q),
			st::settingsButton);
	}));
}

void ShowDemoChats(not_null<Window::Controller*> window) {
	window->show(Box([=](not_null<Ui::GenericBox*> box) {
		box->setTitle(u"Чаты и сообщения oxDesktop"_q);
		box->setWidth(st::boxWideWidth);
		box->addTopButton(st::boxTitleClose, [=] { box->closeBox(); });

		const auto chatList = box->addRow(
			object_ptr<Ui::FixedHeightWidget>(box, 196),
			style::margins(16, 6, 16, 6));
		chatList->paintRequest() | rpl::on_next([=] {
			auto p = QPainter(chatList);
			auto hq = PainterHighQualityEnabler(p);
			const auto w = chatList->width();
			const auto h = chatList->height();

			p.setPen(QPen(QColor(255, 255, 255, 25), 1.));
			p.setBrush(QColor(20, 22, 24, 235));
			p.drawRoundedRect(QRectF(0, 0, w, h).adjusted(1, 1, -1, -1), 10, 10);

			const struct MockChat {
				QString name;
				QString text;
				QString time;
				bool official;
			} chats[] = {
				{ u"oxDesktop Official"_q, u"Вышел релиз v7.3.3! Новая Delta-эмблема и полная тема Aero Delta"_q, u"18:42"_q, true },
				{ u"Telegram Notifications"_q, u"Вход с нового устройства: Linux x64 oxDesktop"_q, u"16:41"_q, true },
				{ u"NanoDev (Developer)"_q, u"Готово, все тесты и сборки успешно завершены!"_q, u"14:20"_q, false },
			};

			const auto rowH = (h - 8) / 3;
			for (int i = 0; i < 3; ++i) {
				const auto y = 4 + i * rowH;
				if (i > 0) {
					p.setPen(QColor(255, 255, 255, 18));
					p.drawLine(68, y, w - 16, y);
				}

				const auto avRect = QRect(16, y + (rowH - 44) / 2, 44, 44);
				if (chats[i].official) {
					p.drawImage(avRect, Window::Logo());
				} else {
					p.setPen(Qt::NoPen);
					p.setBrush(QColor(46, 204, 113));
					p.drawEllipse(avRect);
					p.setPen(Qt::white);
					p.setFont(st::boxTitleFont);
					p.drawText(avRect, Qt::AlignCenter, u"ND"_q);
				}

				p.setPen(Qt::white);
				p.setFont(st::semiboldFont);
				p.drawText(72, y + 21, chats[i].name);

				p.setPen(QColor(140, 150, 158));
				p.setFont(st::normalFont);
				p.drawText(w - 55, y + 21, chats[i].time);

				p.setPen(QColor(165, 172, 180));
				p.setFont(st::normalFont);
				p.drawText(QRectF(72, y + 29, w - 90, 20), Qt::AlignLeft, chats[i].text);
			}
		}, chatList->lifetime());

		auto container = box->verticalLayout();
		Ui::AddDivider(container);

		Settings::AddButtonWithLabel(
			container,
			rpl::single(u"Режим призрака (Ghost mode)"_q),
			rpl::single(u"Активен (Анонимное чтение)"_q),
			st::settingsButton);

		Settings::AddButtonWithLabel(
			container,
			rpl::single(u"Скрывать статус набора текста"_q),
			rpl::single(u"Включено"_q),
			st::settingsButton);

		Settings::AddButtonWithLabel(
			container,
			rpl::single(u"Не отмечать сообщения прочитанными"_q),
			rpl::single(u"Включено"_q),
			st::settingsButton);

		Settings::AddButtonWithLabel(
			container,
			rpl::single(u"Быстрые реакции по двойному клику"_q),
			rpl::single(u"❤️"_q),
			st::settingsButton);
	}));
}

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
	// Force apply dark Aero Delta theme for screenshot/demo rendering
	Window::Theme::ApplyDefaultWithPath(Window::Theme::NightThemePath());
	Window::Theme::KeepApplied();

	const auto targetView = View().toLower();
	const auto session = window->sessionController();

	if (targetView == u"appearance"_q) {
		if (session) {
			session->showSettings(Settings::ExteraAppearanceId());
		} else {
			ShowDemoAppearance(window);
		}
	} else if (targetView == u"chats"_q) {
		if (session) {
			session->showSettings(Settings::ExteraGeneralId());
		} else {
			ShowDemoChats(window);
		}
	} else if (targetView == u"plugins"_q) {
		if (session) {
			session->showSettings(Settings::ExteraPluginsId());
		} else {
			ShowDemoPlugins(window);
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
			ShowDemoSettings(window);
		}
	}

	const auto path = ScreenshotPath();
	const auto delay = DelayMs();
	const auto exit = AutoExit();

	base::call_delayed(crl::time(delay), [=] {
		if (!path.isEmpty()) {
			const auto widget = window->widget();
			const auto pixmap = widget->grab();
			const auto file = QFileInfo(path);
			QDir().mkpath(file.absolutePath());
			const auto ok = pixmap.save(path, "PNG");
			std::cout << "[Demo] Saving screenshot to " << path.toStdString()
				<< " (" << pixmap.width() << "x" << pixmap.height()
				<< ") result=" << (ok ? "SUCCESS" : "FAILED") << std::endl;
		}
		if (exit) {
			QGuiApplication::quit();
		}
	});
}

} // namespace Extera::Demo
