#include "extera/extera_demo.h"

#include "core/application.h"
#include "window/window_controller.h"
#include "window/window_session_controller.h"
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
			object_ptr<Ui::FixedHeightWidget>(box, 110),
			style::margins(16, 12, 16, 8));
		header->paintRequest() | rpl::on_next([=] {
			auto p = QPainter(header);
			auto hq = PainterHighQualityEnabler(p);
			const auto rect = QRectF(0, 0, header->width(), header->height()).adjusted(1, 1, -1, -1);
			auto bgGrad = QLinearGradient(0, 0, header->width(), header->height());
			bgGrad.setColorAt(0., QColor(26, 32, 28, 230));
			bgGrad.setColorAt(1., QColor(18, 22, 20, 240));
			p.setPen(QPen(QColor(46, 204, 113, 80), 1.));
			p.setBrush(bgGrad);
			p.drawRoundedRect(rect, 12, 12);

			const auto &logo = Window::Logo();
			p.drawImage(QRect(16, 15, 80, 80), logo);

			p.setPen(Qt::white);
			p.setFont(st::boxTitleFont);
			p.drawText(112, 42, u"oxDesktop Release"_q);
			p.setPen(QColor(160, 180, 170));
			p.setFont(st::normalFont);
			p.drawText(112, 64, u"Версия 7.3.3 • C++20 / Qt 6.5.3"_q);
			p.drawText(112, 84, u"Брендовая сборка @oxDesktop / @radoqi"_q);
		}, header->lifetime());

		auto container = box->verticalLayout();
		Ui::AddDivider(container);
		Ui::AddSkip(container);

		Settings::AddButtonWithLabel(
			container,
			rpl::single(u"Встроенный обход DPI (TgWsProxy)"_q),
			rpl::single(u"Активен (ReplayCache 65k)"_q),
			st::settingsButton);

		Settings::AddButtonWithLabel(
			container,
			rpl::single(u"Оформление и темы"_q),
			rpl::single(u"Aero Delta (Тёмная)"_q),
			st::settingsButton);

		Settings::AddButtonWithLabel(
			container,
			rpl::single(u"Плагины и расширения"_q),
			rpl::single(u"Python 3.11 SDK v1.2.0"_q),
			st::settingsButton);

		Settings::AddButtonWithLabel(
			container,
			rpl::single(u"Стримерский режим"_q),
			rpl::single(u"Отключен"_q),
			st::settingsButton);

		Settings::AddButtonWithLabel(
			container,
			rpl::single(u"Синхронизация текста песен"_q),
			rpl::single(u"Включена (Lyrics Sync)"_q),
			st::settingsButton);

		Ui::AddSkip(container);
	}));
}

void ShowDemoAppearance(not_null<Window::Controller*> window) {
	window->show(Box([=](not_null<Ui::GenericBox*> box) {
		box->setTitle(u"Внешний вид oxDesktop"_q);
		box->setWidth(st::boxWideWidth);
		box->addTopButton(st::boxTitleClose, [=] { box->closeBox(); });

		const auto preview = box->addRow(
			object_ptr<Ui::FixedHeightWidget>(box, 130),
			style::margins(16, 12, 16, 8));
		preview->paintRequest() | rpl::on_next([=] {
			auto p = QPainter(preview);
			auto hq = PainterHighQualityEnabler(p);
			const auto w = preview->width();
			const auto h = preview->height();

			const auto cardW = (w - 3 * 12) / 4;
			const struct ThemeCard {
				QString name;
				QColor top;
				QColor bottom;
				bool active;
			} cards[] = {
				{ u"Aero Delta"_q, QColor(218, 48, 24), QColor(28, 34, 30), true },
				{ u"Tinted Night"_q, QColor(36, 44, 52), QColor(24, 30, 36), false },
				{ u"Day Classic"_q, QColor(230, 240, 250), QColor(255, 255, 255), false },
				{ u"OLED Black"_q, QColor(16, 16, 16), QColor(0, 0, 0), false },
			};

			for (int i = 0; i < 4; ++i) {
				const auto x = i * (cardW + 12);
				const auto cardRect = QRectF(x, 4, cardW, h - 8);
				auto grad = QLinearGradient(x, 4, x, h - 4);
				grad.setColorAt(0., cards[i].top);
				grad.setColorAt(1., cards[i].bottom);

				p.setPen(cards[i].active ? QPen(QColor(255, 108, 42), 2.) : QPen(QColor(255, 255, 255, 40), 1.));
				p.setBrush(grad);
				p.drawRoundedRect(cardRect, 10, 10);

				p.setPen(Qt::NoPen);
				p.setBrush(QColor(255, 255, 255, 60));
				p.drawRoundedRect(QRectF(x + 10, 16, cardW - 20, 12), 4, 4);
				p.drawRoundedRect(QRectF(x + 10, 36, cardW * 0.6, 16), 4, 4);
				p.setBrush(cards[i].active ? QColor(255, 108, 42, 180) : QColor(255, 255, 255, 80));
				p.drawRoundedRect(QRectF(x + cardW * 0.3, 60, cardW * 0.6, 16), 4, 4);

				p.setPen(cards[i].active ? QColor(255, 108, 42) : Qt::white);
				p.setFont(cards[i].active ? st::semiboldFont : st::normalFont);
				p.drawText(QRectF(x, h - 28, cardW, 20), Qt::AlignCenter, cards[i].name);
			}
		}, preview->lifetime());

		auto container = box->verticalLayout();
		Ui::AddDivider(container);
		Ui::AddSkip(container);

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
			rpl::single(u"Масштаб интерфейса"_q),
			rpl::single(u"100%"_q),
			st::settingsButton);

		Ui::AddSkip(container);
	}));
}

void ShowDemoPlugins(not_null<Window::Controller*> window) {
	window->show(Box([=](not_null<Ui::GenericBox*> box) {
		box->setTitle(u"Менеджер плагинов oxDesktop"_q);
		box->setWidth(st::boxWideWidth);
		box->addTopButton(st::boxTitleClose, [=] { box->closeBox(); });

		const auto engine = box->addRow(
			object_ptr<Ui::FixedHeightWidget>(box, 60),
			style::margins(16, 8, 16, 8));
		engine->paintRequest() | rpl::on_next([=] {
			auto p = QPainter(engine);
			auto hq = PainterHighQualityEnabler(p);
			const auto rect = QRectF(0, 0, engine->width(), engine->height()).adjusted(1, 1, -1, -1);
			p.setPen(QPen(QColor(46, 204, 113, 140), 1.5));
			p.setBrush(QColor(22, 36, 26, 220));
			p.drawRoundedRect(rect, 10, 10);

			p.setPen(QColor(46, 204, 113));
			p.setFont(st::semiboldFont);
			p.drawText(16, 26, u"● Движок плагинов Python 3.11 Embedded"_q);
			p.setPen(QColor(180, 200, 190));
			p.setFont(st::normalFont);
			p.drawText(16, 46, u"Статус: Активен • Режим изоляции: Включен • API SDK v1.2.0"_q);
		}, engine->lifetime());

		auto container = box->verticalLayout();
		Ui::AddDivider(container);
		Ui::AddSkip(container);

		Settings::AddButtonWithLabel(
			container,
			rpl::single(u"TgWsProxy (Flowseal v1.11.4+)"_q),
			rpl::single(u"Включен • ReplayCache (65k)"_q),
			st::settingsButton);

		Settings::AddButtonWithLabel(
			container,
			rpl::single(u"Lyrics Synchronizer"_q),
			rpl::single(u"Включен • Текст песен в плеере"_q),
			st::settingsButton);

		Settings::AddButtonWithLabel(
			container,
			rpl::single(u"3D Badges Showcase"_q),
			rpl::single(u"Включен • Персональные бейджи"_q),
			st::settingsButton);

		Settings::AddButtonWithLabel(
			container,
			rpl::single(u"Smart Message Translator"_q),
			rpl::single(u"Включен • Авто-переводчик"_q),
			st::settingsButton);

		Ui::AddSkip(container);
		Settings::AddButtonWithLabel(
			container,
			rpl::single(u"Установить плагин из файла (.oxp / .py)"_q),
			rpl::single(u"+"_q),
			st::settingsButton);

		Ui::AddSkip(container);
	}));
}

void ShowDemoChats(not_null<Window::Controller*> window) {
	window->show(Box([=](not_null<Ui::GenericBox*> box) {
		box->setTitle(u"Чаты и сообщения oxDesktop"_q);
		box->setWidth(st::boxWideWidth);
		box->addTopButton(st::boxTitleClose, [=] { box->closeBox(); });

		const auto chatList = box->addRow(
			object_ptr<Ui::FixedHeightWidget>(box, 200),
			style::margins(16, 8, 16, 8));
		chatList->paintRequest() | rpl::on_next([=] {
			auto p = QPainter(chatList);
			auto hq = PainterHighQualityEnabler(p);
			const auto w = chatList->width();
			const auto h = chatList->height();

			p.setPen(QPen(QColor(255, 255, 255, 30), 1.));
			p.setBrush(QColor(20, 24, 22, 230));
			p.drawRoundedRect(QRectF(0, 0, w, h).adjusted(1, 1, -1, -1), 12, 12);

			const struct MockChat {
				QString name;
				QString text;
				QString time;
				bool official;
			} chats[] = {
				{ u"oxDesktop Official"_q, u"Вышел релиз v7.3.3! Новая Delta-эмблема и TgWsProxy v1.11.4"_q, u"18:42"_q, true },
				{ u"Telegram Notifications"_q, u"Вход с нового устройства: Linux x64 oxDesktop Client"_q, u"16:41"_q, true },
				{ u"NanoDev (Developer)"_q, u"Готово, все тесты и сборки успешно завершены!"_q, u"14:20"_q, false },
			};

			const auto rowH = (h - 10) / 3;
			for (int i = 0; i < 3; ++i) {
				const auto y = 5 + i * rowH;
				if (i > 0) {
					p.setPen(QColor(255, 255, 255, 20));
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
				p.drawText(72, y + 22, chats[i].name);

				if (chats[i].official) {
					const auto nameW = p.fontMetrics().horizontalAdvance(chats[i].name);
					p.setPen(Qt::NoPen);
					p.setBrush(QColor(255, 108, 42));
					p.drawRoundedRect(QRect(76 + nameW, y + 10, 44, 16), 4, 4);
					p.setPen(Qt::white);
					p.setFont(st::normalFont);
					p.drawText(QRect(76 + nameW, y + 10, 44, 16), Qt::AlignCenter, u"DELTA"_q);
				}

				p.setPen(QColor(140, 155, 150));
				p.setFont(st::normalFont);
				p.drawText(w - 55, y + 22, chats[i].time);

				p.setPen(QColor(160, 175, 170));
				p.setFont(st::normalFont);
				p.drawText(QRectF(72, y + 30, w - 90, 20), Qt::AlignLeft, chats[i].text);
			}
		}, chatList->lifetime());

		auto container = box->verticalLayout();
		Ui::AddDivider(container);
		Ui::AddSkip(container);

		Settings::AddButtonWithLabel(
			container,
			rpl::single(u"Служебный аккаунт 777000"_q),
			rpl::single(u"Аватар Window::Logo() (Активен)"_q),
			st::settingsButton);

		Settings::AddButtonWithLabel(
			container,
			rpl::single(u"Быстрые реакции по двойному клику"_q),
			rpl::single(u"Включено"_q),
			st::settingsButton);

		Ui::AddSkip(container);
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
