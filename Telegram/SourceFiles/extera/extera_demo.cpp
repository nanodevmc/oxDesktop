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
#include "ui/new_badges.h"
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

[[nodiscard]] QImage ChangelogAvatarIcon(int size) {
	auto result = QImage(size, size, QImage::Format_ARGB32_Premultiplied);
	result.fill(Qt::transparent);
	auto p = QPainter(&result);
	auto hq = PainterHighQualityEnabler(p);

	// Radiant rich gradient: Indigo to Cyan/Azure
	auto grad = QLinearGradient(0, 0, size, size);
	grad.setColorAt(0., QColor(30, 64, 175));
	grad.setColorAt(0.55, QColor(37, 99, 235));
	grad.setColorAt(1., QColor(6, 182, 212));
	p.setPen(QPen(QColor(125, 211, 252, 160), 1.2));
	p.setBrush(grad);
	p.drawEllipse(QRectF(1, 1, size - 2, size - 2));

	// Document notebook plate
	p.setPen(Qt::NoPen);
	p.setBrush(QColor(255, 255, 255, 235));
	const auto docW = int(size * 0.44);
	const auto docH = int(size * 0.52);
	const auto docX = (size - docW) / 2;
	const auto docY = (size - docH) / 2;
	const auto docRect = QRectF(docX, docY, docW, docH);
	p.drawRoundedRect(docRect, 3.5, 3.5);

	// 3 list items: colored bullet dots + text lines
	const auto lineH = 2.0;
	const auto dotR = 1.3;
	const auto leftPad = docX + 3.5;
	const auto textLeft = leftPad + 4.5;
	const auto textW = docW - 10.5;

	for (int i = 0; i < 3; ++i) {
		const auto rowY = docY + 5.0 + i * 5.8;
		p.setPen(Qt::NoPen);
		p.setBrush(i == 0 ? QColor(239, 68, 68) : (i == 1 ? QColor(16, 185, 129) : QColor(37, 99, 235)));
		p.drawEllipse(QPointF(leftPad + dotR, rowY + lineH / 2.0), dotR, dotR);

		p.setBrush(QColor(100, 116, 139, 210));
		const auto currLineW = (i == 2) ? (textW * 0.65) : textW;
		p.drawRoundedRect(QRectF(textLeft, rowY, currLineW, lineH), 1.0, 1.0);
	}

	// Golden sparkle badge on top-right corner of document
	p.setPen(Qt::NoPen);
	p.setBrush(QColor(251, 191, 36));
	const auto sparkCx = docX + docW - 2.0;
	const auto sparkCy = docY + 2.0;
	QPolygonF star;
	const auto sR = 3.2;
	star << QPointF(sparkCx, sparkCy - sR)
	     << QPointF(sparkCx + sR * 0.35, sparkCy - sR * 0.35)
	     << QPointF(sparkCx + sR, sparkCy)
	     << QPointF(sparkCx + sR * 0.35, sparkCy + sR * 0.35)
	     << QPointF(sparkCx, sparkCy + sR)
	     << QPointF(sparkCx - sR * 0.35, sparkCy + sR * 0.35)
	     << QPointF(sparkCx - sR, sparkCy)
	     << QPointF(sparkCx - sR * 0.35, sparkCy - sR * 0.35);
	p.drawPolygon(star);

	return result;
}

void ShowDemoSettings(not_null<Window::Controller*> window) {
	window->show(Box([=](not_null<Ui::GenericBox*> box) {
		box->setStyle(st::exteraPlayerBox);
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

		auto container = box->verticalLayout();
		Ui::AddDivider(container);

		const auto vaultBtn = Settings::AddButtonWithLabel(
			container,
			rpl::single(u"Нейро-контекст (Neural Vault)"_q),
			rpl::single(u"Whisper Q4"_q),
			st::settingsButtonNoIcon);
		Ui::NewBadge::AddTagBadgeAfterButtonText(
			vaultBtn,
			Ui::NewBadge::Tag::Beta,
			rpl::single(u"Нейро-контекст (Neural Vault)"_q),
			st::settingsButtonNoIcon);

		Settings::AddButtonWithLabel(
			container,
			rpl::single(u"Встроенный обход блокировок (TgWsProxy)"_q),
			rpl::single(u"Активен (v1.11.4)"_q),
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

		Ui::AddSkip(container, 8);
	}));
}

void ShowDemoAppearance(not_null<Window::Controller*> window) {
	window->show(Box([=](not_null<Ui::GenericBox*> box) {
		box->setStyle(st::exteraPlayerBox);
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

		Ui::AddSkip(container, 8);
	}));
}

void ShowDemoPlugins(not_null<Window::Controller*> window) {
	window->show(Box([=](not_null<Ui::GenericBox*> box) {
		box->setStyle(st::exteraPlayerBox);
		box->setTitle(u"Менеджер плагинов oxDesktop"_q);
		box->setWidth(st::boxWideWidth);
		box->setNoContentMargin(true);
		box->addTopButton(st::boxTitleClose, [=] { box->closeBox(); });

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

		const auto vaultBtn = Settings::AddButtonWithLabel(
			container,
			rpl::single(u"Нейро-контекст (Neural Vault)"_q),
			rpl::single(u"Whisper Q4"_q),
			st::settingsButtonNoIcon);
		Ui::NewBadge::AddTagBadgeAfterButtonText(
			vaultBtn,
			Ui::NewBadge::Tag::Beta,
			rpl::single(u"Нейро-контекст (Neural Vault)"_q),
			st::settingsButtonNoIcon);

		Settings::AddButtonWithLabel(
			container,
			rpl::single(u"Синхронизация текстов песен"_q),
			rpl::single(u"Включена (Genius / Spotify)"_q),
			st::settingsButtonNoIcon);

		Ui::AddDividerText(
			container,
			rpl::single(u"Подключайте расширения и скрипты для автоматизации чатов и кастомизации oxDesktop."_q));

		Ui::AddSkip(container, 8);
	}));
}

void ShowDemoChats(not_null<Window::Controller*> window) {
	window->show(Box([=](not_null<Ui::GenericBox*> box) {
		box->setStyle(st::exteraPlayerBox);
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
				bool changelog;
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
				p.drawImage(avRect, chats[i].changelog ? ChangelogAvatarIcon(44) : DeltaEmblemIcon(44));

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
			rpl::single(u"Нечиталка"_q),
			rpl::single(u"Включено"_q),
			st::settingsButtonNoIcon);

		Settings::AddButtonWithLabel(
			container,
			rpl::single(u"Быстрые реакции по двойному клику"_q),
			rpl::single(u"❤️"_q),
			st::settingsButtonNoIcon);

		Ui::AddSkip(container, 8);
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
