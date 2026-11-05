#include "extera/extera_welcome.h"

#include "base/call_delayed.h"
#include "core/application.h"
#include "core/version.h"
#include "extera/extera_config.h"
#include "styles/style_boxes.h"
#include "ui/widgets/checkbox.h"
#include "ui/boxes/confirm_box.h"
#include "extera/extera_ws_proxy.h"
#include "extera/extera_app_icon.h"
#include "lang/lang_keys.h"
#include "main/main_domain.h"
#include "main/main_session.h"
#include "settings/settings_common.h"
#include "ui/basic_click_handlers.h"
#include "ui/layers/generic_box.h"
#include "ui/painter.h"
#include "ui/vertical_list.h"
#include "ui/widgets/buttons.h"
#include "ui/widgets/labels.h"
#include "ui/wrap/padding_wrap.h"
#include "ui/wrap/vertical_layout.h"
#include "window/main_window.h"
#include "window/window_controller.h"
#include "window/window_session_controller.h"
#include "styles/style_layers.h"
#include "styles/style_menu_icons.h"
#include "styles/style_settings.h"

namespace Extera {
namespace {

[[nodiscard]] TextWithEntities ParseMarkdownLinks(const QString &source) {
	auto result = TextWithEntities();
	auto index = 0;
	const auto length = source.size();
	while (index < length) {
		const auto openBracket = source.indexOf('[', index);
		if (openBracket < 0) {
			result.append(source.mid(index));
			break;
		}
		if (openBracket > index) {
			result.append(source.mid(index, openBracket - index));
		}
		const auto closeBracket = source.indexOf(']', openBracket + 1);
		if (closeBracket > openBracket && closeBracket + 1 < length && source[closeBracket + 1] == '(') {
			const auto closeParen = source.indexOf(')', closeBracket + 2);
			if (closeParen > closeBracket + 1) {
				const auto label = source.mid(openBracket + 1, closeBracket - openBracket - 1);
				const auto url = source.mid(closeBracket + 2, closeParen - closeBracket - 2);
				result.append(tr::link(label, url));
				index = closeParen + 1;
				continue;
			}
		}
		result.append(source.mid(openBracket, 1));
		index = openBracket + 1;
	}
	return result;
}

rpl::lifetime &Lifetime() {
	static auto result = rpl::lifetime();
	return result;
}

void AddPoint(
		not_null<Ui::VerticalLayout*> container,
		rpl::producer<QString> text) {
	container->add(
		object_ptr<Ui::FlatLabel>(
			container,
			std::move(text),
			st::boxLabel),
		st::exteraWelcomePointPadding);
}

void AddLinkButton(
		not_null<Ui::VerticalLayout*> container,
		rpl::producer<QString> title,
		const QString &label,
		const QString &url,
		const style::icon *icon) {
	const auto button = container->add(object_ptr<Ui::SettingsButton>(
		container,
		std::move(title),
		st::settingsButton));
	Settings::AddButtonIcon(button, st::settingsButton, { icon });
	Settings::CreateRightLabel(
		button,
		label,
		st::settingsButton,
		rpl::single(QString()));
	button->setClickedCallback([=] { UrlClickHandler::Open(url); });
}

} // namespace

void FillUnofficialInfo(not_null<Ui::VerticalLayout*> container) {
	AddPoint(container, tr::lng_extera_unofficial_text());
	AddPoint(container, tr::lng_extera_welcome_supported());
	AddPoint(container, tr::lng_extera_welcome_features());
	AddPoint(container, tr::lng_extera_welcome_help());
	Ui::AddSkip(container);
	AddLinkButton(
		container,
		tr::lng_extera_welcome_site(),
		u"В разработке..."_q,
		u"https://t.me/oxDesktop"_q,
		&st::exteraIconWebsite);
	AddLinkButton(
		container,
		tr::lng_extera_welcome_dev(),
		u"@radoqi"_q,
		u"https://t.me/radoqi"_q,
		&st::exteraIconDeveloper);
	AddLinkButton(
		container,
		tr::lng_extera_welcome_channel(),
		u"@oxDesktop"_q,
		u"https://t.me/oxDesktop"_q,
		&st::exteraIconChannel);
}

void ShowWelcomeBox(not_null<Window::SessionController*> controller) {
	controller->show(Box([=](not_null<Ui::GenericBox*> box) {
		box->setTitle(rpl::single(AppName.utf16()));
		box->setWidth(st::boxWideWidth);
		struct State {
			int step = 0;
			QString iconId;
			bool square = false;
			QString initialIconId;
			bool initialSquare = false;
		};
		const auto state = box->lifetime().make_state<State>();
		state->iconId = state->initialIconId = String(u"app_icon"_q);
		state->square = state->initialSquare = Bool(u"app_icon_square"_q);
		const auto content = box->verticalLayout();
		const auto rebuild = std::make_shared<Fn<void()>>();
		const auto addTitle = [=](rpl::producer<QString> text) {
			content->add(
				object_ptr<Ui::FlatLabel>(
					content,
					std::move(text),
					st::exteraWelcomeTitle),
				st::exteraWelcomeTitlePadding,
				style::al_top);
		};
		const auto addText = [=](rpl::producer<QString> text) {
			content->add(
				object_ptr<Ui::FlatLabel>(
					content,
					std::move(text),
					st::exteraWelcomeText),
				st::exteraWelcomeTextPadding,
				style::al_top);
		};
		const auto finish = [=] {
			Config::Instance().setBool(u"wizard_shown"_q, true);
			const auto changed = (state->iconId != state->initialIconId)
				|| (state->square != state->initialSquare);
			box->closeBox();
			if (changed) {
				Config::Instance().setString(u"app_icon"_q, state->iconId);
				Config::Instance().setBool(
					u"app_icon_square"_q,
					state->square);
				AppIcon::Apply();
			}
		};
		const auto fillWelcome = [=] {
			const auto size = st::exteraWelcomeLogoSize;
			const auto logo = content->add(
				object_ptr<Ui::FixedHeightWidget>(content, size),
				st::exteraWelcomeLogoPadding);
			logo->paintRequest(
			) | rpl::on_next([=] {
				auto p = QPainter(logo);
				auto hq = PainterHighQualityEnabler(p);
				p.drawImage(
					QRect((logo->width() - size) / 2, 0, size, size),
					Window::Logo());
			}, logo->lifetime());
			addTitle(tr::lng_exd_wizard_welcome());
			addText(tr::lng_exd_wizard_welcome_text());
			AddLinkButton(
				content,
				tr::lng_extera_port_developer(),
				u"@radoqi"_q,
				u"https://t.me/radoqi"_q,
				&st::exteraIconDeveloper);
			AddLinkButton(
				content,
				tr::lng_extera_channel(),
				u"@oxDesktop"_q,
				u"https://t.me/oxDesktop"_q,
				&st::exteraIconChannel);
			AddLinkButton(
				content,
				tr::lng_extera_forum(),
				u"@oxDesktopChat"_q,
				u"https://t.me/oxDesktopChat"_q,
				&st::exteraIconForum);
			AddLinkButton(
				content,
				tr::lng_extera_website(),
				u"В разработке..."_q,
				u"https://t.me/oxDesktop"_q,
				&st::exteraIconWebsite);
			const auto setupBtn = content->add(
				object_ptr<Ui::RoundButton>(
					content,
					tr::lng_exd_wizard_setup(),
					st::defaultBoxButton),
				style::margins(0, 16, 0, 8),
				style::al_top);
			setupBtn->setTextTransform(Ui::RoundButton::TextTransform::NoTransform);
			setupBtn->setClickedCallback([=] {
				crl::on_main(box, [=] {
					state->step = 1;
					(*rebuild)();
				});
			});
		};
		const auto fillIcon = [=] {
			addTitle(tr::lng_exd_wizard_icon());
			const auto variants = AppIcon::Variants();
			const auto count = int(variants.size());
			const auto titleFor = [&](int index) {
				return (index >= 0 && index < count) ? variants[index].title : QString();
			};
			const auto images = std::make_shared<std::vector<QImage>>();
			const auto ratio = style::DevicePixelRatio();
			const auto size = st::exteraAppIconSize;
			const auto render = [=] {
				images->clear();
				for (const auto &variant : variants) {
					auto image = AppIcon::Render(
						size * ratio,
						variant.id,
						state->square);
					image.setDevicePixelRatio(ratio);
					images->push_back(std::move(image));
				}
			};
			render();
			const auto columns = 3;
			const auto cell = st::exteraAppIconCellWidth;
			const auto cellHeight = st::exteraAppIconCellHeight;
			const auto rows = (count + columns - 1) / columns;
			const auto grid = content->add(
				object_ptr<Ui::FixedHeightWidget>(
					content,
					rows * cellHeight),
				st::exteraAppIconGridPadding);
			const auto left = [=] {
				return (grid->width() - columns * cell) / 2;
			};
			const auto selected = [=] {
				for (auto i = 0; i != count; ++i) {
					if (variants[i].id == state->iconId) {
						return i;
					}
				}
				return 0;
			};
			grid->paintRequest() | rpl::on_next([=] {
				auto p = QPainter(grid);
				auto hq = PainterHighQualityEnabler(p);
				for (auto i = 0; i != count; ++i) {
					const auto x = left() + (i % columns) * cell;
					const auto y = (i / columns) * cellHeight + 4;
					const auto rect = QRect(
						x + (cell - size) / 2,
						y,
						size,
						size);
					p.drawImage(rect, (*images)[i]);
					if (i == selected()) {
						p.setBrush(Qt::NoBrush);
						p.setPen(QPen(
							st::windowActiveTextFg,
							st::lineWidth * 2));
						const auto outer = rect.marginsAdded({ 4, 4, 4, 4 });
						if (state->square) {
							const auto radius = outer.width() * 0.25;
							p.drawRoundedRect(outer, radius, radius);
						} else {
							p.drawEllipse(outer);
						}
					}
					p.setPen(st::windowFg);
					p.setFont(st::exteraAppIconCaptionFont);
					p.drawText(
						QRect(
							x,
							y + size + st::exteraAppIconCaptionSkip,
							cell,
							st::exteraAppIconCaptionFont->height),
						Qt::AlignHCenter | Qt::AlignTop,
						st::exteraAppIconCaptionFont->elided(
							titleFor(i),
							cell - 4));
				}
			}, grid->lifetime());
			grid->setCursor(style::cur_pointer);
			grid->events(
			) | rpl::filter([](not_null<QEvent*> e) {
				return e->type() == QEvent::MouseButtonRelease;
			}) | rpl::on_next([=](not_null<QEvent*> e) {
				const auto point = static_cast<QMouseEvent*>(e.get())->pos();
				const auto column = (point.x() - left()) / cell;
				const auto row = point.y() / cellHeight;
				const auto index = row * columns + column;
				if (point.x() < left()
					|| column >= columns
					|| index < 0
					|| index >= count) {
					return;
				}
				state->iconId = variants[index].id;
				grid->update();
			}, grid->lifetime());
			const auto square = content->add(
				object_ptr<Ui::Checkbox>(
					content,
					tr::lng_exd_app_icon_square(tr::now),
					state->square,
					st::defaultBoxCheckbox),
				st::exteraAppIconGridPadding);
			square->checkedChanges() | rpl::on_next([=](bool checked) {
				state->square = checked;
				render();
				grid->update();
			}, square->lifetime());
			box->addButton(tr::lng_exd_wizard_next(), [=] {
				crl::on_main(box, [=] {
					state->step = 2;
					(*rebuild)();
				});
			});
		};
		const auto fillSettings = [=] {
			addTitle(tr::lng_exd_wizard_settings());
			const auto card = content->add(
				object_ptr<Ui::VerticalLayout>(content),
				style::margins(16, 8, 16, 8));
			card->paintRequest() | rpl::on_next([=] {
				auto p = QPainter(card);
				auto hq = PainterHighQualityEnabler(p);
				const auto rect = QRectF(card->rect()).adjusted(0.5, 0.5, -0.5, -0.5);
				p.setPen(QPen(QColor(255, 255, 255, 24), 1.0));
				p.setBrush(QColor(255, 255, 255, 8));
				p.drawRoundedRect(rect, 10.0, 10.0);
			}, card->lifetime());

			const auto toggle = [=](
					const QString &key,
					rpl::producer<QString> title,
					const style::icon *icon,
					Fn<void(bool)> apply) {
				const auto button = card->add(
					object_ptr<Ui::SettingsButton>(
						card,
						std::move(title),
						st::settingsButton));
				if (icon) {
					Settings::AddButtonIcon(button, st::settingsButton, { icon });
				}
				button->toggleOn(rpl::single(Bool(key)));
				button->toggledChanges(
				) | rpl::on_next([=](bool value) {
					if (apply) {
						apply(value);
					} else {
						Config::Instance().setBool(key, value);
					}
				}, button->lifetime());
			};
			if (WsProxy::Available()) {
				toggle(
					u"ws_proxy"_q,
					tr::lng_exd_ws_proxy(),
					&st::menuIconNetwork,
					[](bool v) { WsProxy::SetEnabled(v); });
			}
			toggle(
				u"time_with_seconds"_q,
				tr::lng_extera_time_seconds(),
				&st::menuIconSchedule,
				nullptr);
			toggle(
				u"hide_phone"_q,
				tr::lng_extera_hide_phone(),
				&st::menuIconLock,
				nullptr);
			toggle(
				u"local_premium_emoji"_q,
				tr::lng_extera_local_premium(),
				&st::menuIconPremium,
				nullptr);
			toggle(
				u"chars_counter"_q,
				tr::lng_exd_chars_counter(),
				&st::menuIconEdit,
				nullptr);
			addText(tr::lng_exd_wizard_settings_about());
			box->addButton(rpl::single(u"\u0427\u0442\u043E \u043D\u043E\u0432\u043E\u0433\u043E \u279C"_q), [=] {
				crl::on_main(box, [=] {
					state->step = 3;
					(*rebuild)();
				});
			});
		};
		const auto fillChangelog = [=] {
			addTitle(rpl::single(u"\u0427\u0442\u043E \u043D\u043E\u0432\u043E\u0433\u043E"_q));
			auto contentText = QString();
			for (const auto &loc : {
				u"changelog.txt"_q,
				QCoreApplication::applicationDirPath() + u"/changelog.txt"_q,
				QDir::currentPath() + u"/changelog.txt"_q,
			}) {
				auto f = QFile(loc);
				if (f.open(QIODevice::ReadOnly)) {
					contentText = QString::fromUtf8(f.readAll());
					f.close();
					break;
				}
			}
			if (contentText.isEmpty()) {
				contentText = u"v7.3.3:\nRu:\n- \u041E\u0431\u043D\u043E\u0432\u043B\u0435\u043D\u0438\u0435 oxDesktop \u0443\u0441\u043F\u0435\u0448\u043D\u043E \u043F\u0440\u0438\u043C\u0435\u043D\u0435\u043D\u043E"_q;
			}
			const auto lines = contentText.split('\n');
			Ui::VerticalLayout *currentCard = nullptr;
			for (const auto &line : lines) {
				const auto trimmed = line.trimmed();
				if (trimmed.isEmpty() || trimmed.startsWith(u"v7."_q) || trimmed.startsWith(u"v"_q)) {
					continue;
				}
				if (trimmed.startsWith(u"Ru:"_q) || trimmed.startsWith(u"En:"_q)) {
					currentCard = content->add(
						object_ptr<Ui::VerticalLayout>(content),
						style::margins(16, 6, 16, 6));
					currentCard->paintRequest() | rpl::on_next([=] {
						auto p = QPainter(currentCard);
						auto hq = PainterHighQualityEnabler(p);
						const auto rect = QRectF(currentCard->rect()).adjusted(0.5, 0.5, -0.5, -0.5);
						p.setPen(QPen(QColor(255, 255, 255, 24), 1.0));
						p.setBrush(QColor(255, 255, 255, 8));
						p.drawRoundedRect(rect, 10.0, 10.0);
					}, currentCard->lifetime());

					const auto title = trimmed.startsWith(u"Ru:"_q)
						? u"\u0420\u0443\u0441\u0441\u043A\u0430\u044F \u043B\u043E\u043A\u0430\u043B\u0438\u0437\u0430\u0446\u0438\u044F"_q
						: u"English"_q;
					currentCard->add(
						object_ptr<Ui::FlatLabel>(
							currentCard,
						rpl::single(title),
						st::semiboldFont),
						style::margins(12, 10, 12, 6));
				} else if (currentCard) {
					auto itemText = trimmed;
					if (itemText.startsWith('-')) {
						itemText = u"\u2014 "_q + itemText.mid(1).trimmed();
					}
					const auto label = currentCard->add(
						object_ptr<Ui::FlatLabel>(
							currentCard,
							rpl::single(ParseMarkdownLinks(itemText)),
							st::boxLabel),
						style::margins(16, 2, 12, 4));
					label->setLinksTrusted();
				}
			}
			box->addButton(tr::lng_exd_wizard_finish(), finish);
		};
		*rebuild = [=] {
			box->clearButtons();
			box->addTopButton(st::boxTitleClose, [=] { box->closeBox(); });
			content->clear();
			switch (state->step) {
			case 0: fillWelcome(); break;
			case 1: fillIcon(); break;
			case 2: fillSettings(); break;
			default: fillChangelog(); break;
			}
			content->resizeToWidth(st::boxWideWidth);
		};
		(*rebuild)();
		box->boxClosing() | rpl::on_next([=] {
			Config::Instance().setBool(u"wizard_shown"_q, true);
		}, box->lifetime());
	}));
}

void StartWelcome() {
	static auto started = false;
	if (started) {
		return;
	}
	started = true;
	Core::App().domain().activeSessionValue(
	) | rpl::filter([](Main::Session *session) {
		return session != nullptr;
	}) | rpl::take(1) | rpl::on_next([](Main::Session *session) {
		if (Bool(u"wizard_shown"_q)) {
			return;
		}
		base::call_delayed(1500, [] {
			const auto window = Core::App().activePrimaryWindow();
			const auto controller = window
				? window->sessionController()
				: nullptr;
			if (!controller) {
				return;
			}
			ShowWelcomeBox(controller);
		});
	}, Lifetime());
}

} // namespace Extera
