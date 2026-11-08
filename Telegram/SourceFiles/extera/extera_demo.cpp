#include "extera/extera_demo.h"

#include "core/application.h"
#include "window/window_controller.h"
#include "window/window_session_controller.h"
#include "window/themes/window_theme.h"
#include "window/themes/window_themes_embedded.h"
#include "settings/sections/settings_extera.h"
#include "settings/settings_common.h"
#include "extera/extera_config.h"
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

#include <QtWidgets/QWidget>
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

[[nodiscard]] QImage DeltaEmblemIcon(int size) {
	static const auto emblem = QImage(u":/gui/art/oxdesktop.png"_q)
		.convertToFormat(QImage::Format_ARGB32_Premultiplied);
	return emblem.scaled(size, size, Qt::IgnoreAspectRatio, Qt::SmoothTransformation);
}

[[nodiscard]] QImage DeltaStealthIcon(int size) {
	auto result = QImage(size, size, QImage::Format_ARGB32_Premultiplied);
	result.fill(Qt::transparent);
	auto p = QPainter(&result);
	auto hq = PainterHighQualityEnabler(p);
	auto grad = QLinearGradient(0, 0, 0, size);
	grad.setColorAt(0., QColor(36, 40, 48));
	grad.setColorAt(1., QColor(18, 20, 24));
	p.setPen(QPen(QColor(218, 48, 24, 180), 1.5));
	p.setBrush(grad);
	p.drawEllipse(QRectF(1, 1, size - 2, size - 2));

	static const auto glyph = QImage(u":/gui/art/app_icon_glyph.png"_q)
		.convertToFormat(QImage::Format_ARGB32_Premultiplied);
	const auto glyphSize = int(size * 0.62);
	const auto glyphRect = QRect(
		(size - glyphSize) / 2,
		(size - glyphSize) / 2,
		glyphSize,
		glyphSize);
	p.drawImage(glyphRect, glyph);
	return result;
}

void AddNeuralVaultPlate(not_null<Ui::GenericBox*> box) {
	const auto vault = box->addRow(
		object_ptr<Ui::FixedHeightWidget>(box, 70),
		style::margins(16, 4, 16, 6));
	vault->paintRequest() | rpl::on_next([=] {
		auto p = QPainter(vault);
		auto hq = PainterHighQualityEnabler(p);
		const auto w = vault->width();
		const auto h = vault->height();
		const auto rect = QRectF(0, 0, w, h).adjusted(1, 1, -1, -1);

		const auto active = NeuralVaultEnabled();

		// Liquid Glass surface: dark obsidian with emerald/neon tinted acrylic feel
		auto bgGrad = QLinearGradient(0, 0, w, h);
		bgGrad.setColorAt(0., QColor(22, 28, 26, 235));
		bgGrad.setColorAt(1., QColor(14, 18, 17, 245));
		p.setPen(QPen(active ? QColor(52, 211, 153, 75) : QColor(255, 255, 255, 30), 1.2));
		p.setBrush(bgGrad);
		p.drawRoundedRect(rect, 8, 8);

		// Subtle glass highlight reflection on top edge
		p.setPen(QPen(QColor(255, 255, 255, 20), 1.0));
		p.drawLine(QPointF(10, 2), QPointF(w - 10, 2));

		// Glowing neon status indicator dot
		p.setPen(Qt::NoPen);
		p.setBrush(active ? QColor(52, 211, 153, 40) : QColor(140, 150, 155, 30));
		p.drawEllipse(QRectF(15, 13, 16, 16));
		p.setBrush(active ? QColor(52, 211, 153) : QColor(140, 150, 155));
		p.drawEllipse(QRectF(19, 17, 8, 8));

		// Title
		p.setPen(Qt::white);
		p.setFont(st::semiboldFont);
		const auto title = u"Нейро-контекст (Neural Vault)"_q;
		p.drawText(39, 23, title);

		// Elegant neon BETA badge [БЕТА] with green-neon outline
		const auto titleW = st::semiboldFont->width(title);
		const auto badgeX = 39 + titleW + 8;
		const auto badgeRect = QRectF(badgeX, 11, 48, 17);
		auto badgeGrad = QLinearGradient(badgeX, 11, badgeX + 48, 28);
		badgeGrad.setColorAt(0., QColor(52, 211, 153, 40));
		badgeGrad.setColorAt(1., QColor(16, 185, 129, 18));
		p.setPen(QPen(QColor(52, 211, 153, 200), 1.0));
		p.setBrush(badgeGrad);
		p.drawRoundedRect(badgeRect, 4, 4);

		p.setPen(QColor(52, 211, 153));
		auto badgeFont = p.font();
		badgeFont.setPixelSize(10);
		badgeFont.setBold(true);
		badgeFont.setLetterSpacing(QFont::AbsoluteSpacing, 0.8);
		p.setFont(badgeFont);
		p.drawText(badgeRect, Qt::AlignCenter, u"БЕТА"_q);

		// Status chip on the right (Whisper Q4)
		const auto statusW = 86;
		const auto statusRect = QRectF(w - statusW - 14, 11, statusW, 20);
		p.setPen(QPen(active ? QColor(52, 211, 153, 90) : QColor(255, 255, 255, 40), 1.0));
		p.setBrush(active ? QColor(20, 36, 30, 210) : QColor(30, 32, 34, 210));
		p.drawRoundedRect(statusRect, 10, 10);
		p.setPen(active ? QColor(52, 211, 153) : QColor(180, 185, 190));
		auto statusFont = p.font();
		statusFont.setPixelSize(11);
		statusFont.setBold(true);
		statusFont.setLetterSpacing(QFont::AbsoluteSpacing, 0.0);
		p.setFont(statusFont);
		p.drawText(statusRect, Qt::AlignCenter, u"Whisper Q4"_q);

		// Subtitle: Local offline transcription & Private semantic search
		p.setPen(QColor(160, 175, 170));
		p.setFont(st::normalFont);
		auto subFont = p.font();
		subFont.setPixelSize(11);
		p.setFont(subFont);
		const auto subRect = QRectF(39, 34, w - 53, 30);
		p.drawText(
			subRect,
			Qt::TextWordWrap | Qt::AlignLeft | Qt::AlignTop,
			u"Локальная оффлайн-расшифровка голосовых сообщений (Whisper Q4) • Приватный семантический поиск"_q);
	}, vault->lifetime());
}

void ShowDemoSettings(not_null<Window::Controller*> window) {
	window->show(Box([=](not_null<Ui::GenericBox*> box) {
		box->setTitle(u"Настройки oxDesktop"_q);
		box->setWidth(st::boxWideWidth);
		box->setNoContentMargin(true);
		box->addTopButton(st::boxTitleClose, [=] { box->closeBox(); });

		const auto header = box->addRow(
			object_ptr<Ui::FixedHeightWidget>(box, 82),
			style::margins(16, 6, 16, 6));
		header->paintRequest() | rpl::on_next([=] {
			auto p = QPainter(header);
			auto hq = PainterHighQualityEnabler(p);
			const auto rect = QRectF(0, 0, header->width(), header->height()).adjusted(1, 1, -1, -1);
			auto bgGrad = QLinearGradient(0, 0, header->width(), header->height());
			bgGrad.setColorAt(0., QColor(28, 22, 22, 240));
			bgGrad.setColorAt(1., QColor(15, 16, 18, 245));
			p.setPen(QPen(QColor(218, 48, 24, 90), 1.2));
			p.setBrush(bgGrad);
			p.drawRoundedRect(rect, 10, 10);

			p.drawImage(QRect(16, 12, 58, 58), DeltaEmblemIcon(58));

			p.setPen(Qt::white);
			auto titleFont = st::semiboldFont->f;
			titleFont.setPixelSize(14);
			titleFont.setBold(true);
			p.setFont(titleFont);
			p.drawText(86, 35, u"oxDesktop v7.3.3"_q);

			p.setPen(QColor(180, 185, 192));
			auto subFont = st::normalFont->f;
			subFont.setPixelSize(12);
			p.setFont(subFont);
			p.drawText(86, 55, u"Официальная сборка • @oxDesktop"_q);
		}, header->lifetime());

		AddNeuralVaultPlate(box);

		auto container = box->verticalLayout();
		Ui::AddDivider(container);

		Settings::AddButtonWithLabel(
			container,
			rpl::single(u"Встроенный обход блокировок (TgWsProxy)"_q),
			rpl::single(u"Активен (v1.11.4)"_q),
			st::settingsButtonNoIcon);

		Settings::AddButtonWithLabel(
			container,
			rpl::single(u"Локальный Whisper & Семантический поиск"_q),
			rpl::single(u"[БЕТА] Активен"_q),
			st::settingsButtonNoIcon);

		Settings::AddButtonWithLabel(
			container,
			rpl::single(u"Режим стримера (защита приватности)"_q),
			rpl::single(u"Отключен"_q),
			st::settingsButtonNoIcon);

		Settings::AddButtonWithLabel(
			container,
			rpl::single(u"Синхронизация текстов песен (Lyrics)"_q),
			rpl::single(u"Включена (Genius / Spotify)"_q),
			st::settingsButtonNoIcon);

		Settings::AddButtonWithLabel(
			container,
			rpl::single(u"Проверка обновлений oxDesktop"_q),
			rpl::single(u"Версия актуальна"_q),
			st::settingsButtonNoIcon);
	}));
}

void ShowDemoAppearance(not_null<Window::Controller*> window) {
	window->show(Box([=](not_null<Ui::GenericBox*> box) {
		box->setTitle(u"Внешний вид oxDesktop"_q);
		box->setWidth(st::boxWideWidth);
		box->setNoContentMargin(true);
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
				{ u"Aero Delta"_q, QColor(218, 48, 24), QColor(20, 21, 23), true },
				{ u"Delta Dark"_q, QColor(28, 30, 34), QColor(15, 16, 18), false },
				{ u"Liquid Glass"_q, QColor(32, 35, 40), QColor(20, 21, 23), false },
				{ u"OLED Black"_q, QColor(18, 18, 18), QColor(0, 0, 0), false },
			};

			for (int i = 0; i < 4; ++i) {
				const auto x = i * (cardW + 10);
				const auto cardRect = QRectF(x, 2, cardW, h - 4);
				auto grad = QLinearGradient(x, 2, x, h - 2);
				grad.setColorAt(0., cards[i].top);
				grad.setColorAt(1., cards[i].bottom);

				p.setPen(cards[i].active ? QPen(QColor(255, 85, 51), 2.) : QPen(QColor(255, 255, 255, 30), 1.));
				p.setBrush(grad);
				p.drawRoundedRect(cardRect, 8, 8);

				p.setPen(Qt::NoPen);
				p.setBrush(QColor(255, 255, 255, 45));
				p.drawRoundedRect(QRectF(x + 8, 12, cardW - 16, 10), 3, 3);
				p.drawRoundedRect(QRectF(x + 8, 28, cardW * 0.6, 12), 3, 3);
				p.setBrush(cards[i].active ? QColor(255, 85, 51, 180) : QColor(255, 255, 255, 60));
				p.drawRoundedRect(QRectF(x + cardW * 0.32, 48, cardW * 0.58, 12), 3, 3);

				p.setPen(cards[i].active ? QColor(255, 95, 60) : QColor(190, 195, 200));
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
			st::settingsButtonNoIcon);

		Settings::AddButtonWithLabel(
			container,
			rpl::single(u"Стиль интерфейса"_q),
			rpl::single(u"Liquid Glass + Material 3"_q),
			st::settingsButtonNoIcon);

		Settings::AddButtonWithLabel(
			container,
			rpl::single(u"Анимации и эффекты перехода"_q),
			rpl::single(u"Включены (Плавные 60 FPS)"_q),
			st::settingsButtonNoIcon);

		Settings::AddButtonWithLabel(
			container,
			rpl::single(u"Размытие фона и прозрачность"_q),
			rpl::single(u"Акрил (Liquid Glass)"_q),
			st::settingsButtonNoIcon);
	}));
}

void ShowDemoPlugins(not_null<Window::Controller*> window) {
	window->show(Box([=](not_null<Ui::GenericBox*> box) {
		box->setTitle(u"Менеджер плагинов oxDesktop"_q);
		box->setWidth(st::boxWideWidth);
		box->setNoContentMargin(true);
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
			grad.setColorAt(1., QColor(15, 16, 18, 240));
			p.setPen(QPen(QColor(46, 204, 113, 110), 1.2));
			p.setBrush(grad);
			p.drawRoundedRect(rect, 8, 8);

			p.setPen(QColor(46, 204, 113));
			p.setFont(st::semiboldFont);
			p.drawText(16, 23, u"● Движок плагинов активен"_q);
			p.setPen(QColor(180, 190, 185));
			p.setFont(st::normalFont);
			p.drawText(16, 41, u"Среда расширений oxDesktop • Python 3.11"_q);
		}, engine->lifetime());

		AddNeuralVaultPlate(box);

		auto container = box->verticalLayout();
		Ui::AddDivider(container);

		Settings::AddButtonWithLabel(
			container,
			rpl::single(u"Каталог расширений"_q),
			rpl::single(u"Доступно в репозитории"_q),
			st::settingsButtonNoIcon);

		Settings::AddButtonWithLabel(
			container,
			rpl::single(u"Песочница скриптов"_q),
			rpl::single(u"Изоляция активна"_q),
			st::settingsButtonNoIcon);

		Settings::AddButtonWithLabel(
			container,
			rpl::single(u"Локальный Whisper & Семантический поиск"_q),
			rpl::single(u"[БЕТА] Whisper Q4"_q),
			st::settingsButtonNoIcon);

		Settings::AddButtonWithLabel(
			container,
			rpl::single(u"Синхронизация текстов песен"_q),
			rpl::single(u"Включена (Genius / Spotify)"_q),
			st::settingsButtonNoIcon);
	}));
}

void ShowDemoChats(not_null<Window::Controller*> window) {
	window->show(Box([=](not_null<Ui::GenericBox*> box) {
		box->setTitle(u"Чаты и сообщения oxDesktop"_q);
		box->setWidth(st::boxWideWidth);
		box->setNoContentMargin(true);
		box->addTopButton(st::boxTitleClose, [=] { box->closeBox(); });

		const auto chatList = box->addRow(
			object_ptr<Ui::FixedHeightWidget>(box, 134),
			style::margins(16, 6, 16, 6));
		chatList->paintRequest() | rpl::on_next([=] {
			auto p = QPainter(chatList);
			auto hq = PainterHighQualityEnabler(p);
			const auto w = chatList->width();
			const auto h = chatList->height();

			p.setPen(QPen(QColor(255, 255, 255, 25), 1.));
			p.setBrush(QColor(20, 21, 23, 235));
			p.drawRoundedRect(QRectF(0, 0, w, h).adjusted(1, 1, -1, -1), 10, 10);

			const struct MockChat {
				QString name;
				QString text;
				QString time;
				bool stealth;
			} chats[] = {
				{ u"oxDesktop"_q, u"Официальный релиз oxDesktop v7.3.3"_q, u"18:42"_q, false },
				{ u"oxDesktop | Changelog"_q, u"История версий, патч-ноуты и обновления расширений"_q, u"17:15"_q, true },
			};

			const auto rowH = (h - 8) / 2;
			for (int i = 0; i < 2; ++i) {
				const auto y = 4 + i * rowH;
				if (i > 0) {
					p.setPen(QColor(255, 255, 255, 18));
					p.drawLine(68, y, w - 16, y);
				}

				const auto avRect = QRect(16, y + (rowH - 44) / 2, 44, 44);
				p.drawImage(avRect, chats[i].stealth ? DeltaStealthIcon(44) : DeltaEmblemIcon(44));

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
			rpl::single(u"Включен"_q),
			st::settingsButtonNoIcon);

		Settings::AddButtonWithLabel(
			container,
			rpl::single(u"Скрывать статус набора текста"_q),
			rpl::single(u"Включено"_q),
			st::settingsButtonNoIcon);

		Settings::AddButtonWithLabel(
			container,
			rpl::single(u"Не отмечать сообщения прочитанными"_q),
			rpl::single(u"Включено"_q),
			st::settingsButtonNoIcon);

		Settings::AddButtonWithLabel(
			container,
			rpl::single(u"Быстрые реакции по двойному клику"_q),
			rpl::single(u"❤️"_q),
			st::settingsButtonNoIcon);
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
	if (const auto palette = Window::Theme::PrepareEmbeddedPalette(
			Window::Theme::EmbeddedType::AeroDelta,
			QColor(218, 48, 24))) {
		style::main_palette::apply(*palette);
	}
	Window::Theme::SetNightModeValue(true);
	Window::Theme::ApplyDefaultWithPath(Window::Theme::NightThemePath());
	Window::Theme::KeepApplied();
	style::NotifyPaletteChanged();

	const auto widget = window->widget();
	for (const auto child : widget->findChildren<QWidget*>()) {
		const auto name = QString::fromLatin1(child->metaObject()->className());
		if (name.contains(u"Intro"_q)) {
			child->hide();
		}
	}

	const auto bg = new QWidget(widget);
	bg->setGeometry(widget->rect());
	bg->setStyleSheet(u"background-color: #0f1012;"_q);
	bg->show();
	bg->lower();

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
			for (const auto child : widget->findChildren<QWidget*>()) {
				const auto name = QString::fromLatin1(child->metaObject()->className());
				if (name.contains(u"Intro"_q)) {
					child->hide();
				}
			}
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
