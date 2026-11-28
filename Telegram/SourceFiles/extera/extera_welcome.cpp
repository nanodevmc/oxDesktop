#include "extera/extera_welcome.h"
#include "history/history.h"
#include "extera/extera_changelog.h"

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
#include "data/data_channel.h"
#include "data/data_session.h"
#include "data/data_chat_filters.h"
#include "dialogs/dialogs_key.h"
#include "mtproto/facade.h"
#include "apiwrap.h"
#include "styles/style_layers.h"
#include "styles/style_menu_icons.h"
#include "styles/style_settings.h"

#include <QtCore/QFile>
#include <QtCore/QDir>
#include <QtCore/QCoreApplication>
#include <QtCore/QPointer>
#include <QtGui/QLinearGradient>
#include <QtGui/QPainterPath>

namespace Extera {
namespace {

enum class Step : uint8_t {
	Welcome = 0,
	Icon = 1,
	Settings = 2,
	Changelog = 3,
};

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
		u"https://nanodevmc.github.io/oxDesktop/"_q,
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
		u"https://nanodevmc.github.io/oxDesktop/"_q,
		&st::exteraIconChannel);
}

void ShowWelcomeBox(not_null<Window::SessionController*> controller) {
	controller->show(Box([=](not_null<Ui::GenericBox*> box) {
		box->setTitle(rpl::single(AppName.utf16()));
		box->setWidth(st::boxWideWidth);

		struct State {
			Step step = Step::Welcome;
			QString iconId;
			bool square = false;
			QString initialIconId;
			bool initialSquare = false;
			std::vector<AppIcon::Variant> variants;
		};
		const auto state = box->lifetime().make_state<State>();
		state->iconId = state->initialIconId = String(u"app_icon"_q);
		state->square = state->initialSquare = Bool(u"app_icon_square"_q);
		state->variants = AppIcon::Variants();

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
			addTitle(tr::lng_oxd_wizard_welcome());
			addText(tr::lng_oxd_wizard_welcome_text());
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
				u"https://nanodevmc.github.io/oxDesktop/"_q,
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
				u"https://nanodevmc.github.io/oxDesktop/"_q,
				&st::exteraIconWebsite);
			box->addButton(tr::lng_oxd_wizard_setup(), [=] {
				base::call_delayed(0, box, [=] {
					state->step = Step::Icon;
					(*rebuild)();
				});
			});
		};

		const auto fillIcon = [=] {
			addTitle(tr::lng_oxd_wizard_icon());
			const auto count = int(state->variants.size());
			const auto images = std::make_shared<std::vector<QImage>>();
			const auto ratio = style::DevicePixelRatio();
			const auto size = st::exteraAppIconSize;
			const auto render = [=] {
				images->clear();
				for (const auto &variant : state->variants) {
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
					if (state->variants[i].id == state->iconId) {
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
					const auto title = (i >= 0 && i < count)
						? state->variants[i].title
						: QString();
					p.drawText(
						QRect(
							x,
							y + size + st::exteraAppIconCaptionSkip,
							cell,
							st::exteraAppIconCaptionFont->height),
						Qt::AlignHCenter | Qt::AlignTop,
						st::exteraAppIconCaptionFont->elided(
							title,
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
				state->iconId = state->variants[index].id;
				grid->update();
			}, grid->lifetime());
			const auto square = content->add(
				object_ptr<Ui::Checkbox>(
					content,
					tr::lng_oxd_app_icon_square(tr::now),
					state->square,
					st::defaultBoxCheckbox),
				st::exteraAppIconGridPadding);
			square->checkedChanges() | rpl::on_next([=](bool checked) {
				state->square = checked;
				render();
				grid->update();
			}, square->lifetime());
			box->addButton(tr::lng_oxd_wizard_next(), [=] {
				base::call_delayed(0, box, [=] {
					state->step = Step::Settings;
					(*rebuild)();
				});
			});
		};

		const auto fillSettings = [=] {
			addTitle(tr::lng_oxd_wizard_settings());
			const auto card = content->add(
				object_ptr<Ui::VerticalLayout>(content),
				style::margins(16, 8, 16, 8));
			card->paintRequest() | rpl::on_next([=] {
				auto p = QPainter(card);
				auto hq = PainterHighQualityEnabler(p);
				const auto rect = QRectF(card->rect()).adjusted(0.5, 0.5, -0.5, -0.5);
				p.setPen(QPen(QColor(46, 204, 113, 60), 1.0));
				p.setBrush(QColor(24, 28, 34, 230));
				p.drawRoundedRect(rect, 12.0, 12.0);
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
					tr::lng_oxd_ws_proxy(),
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
				tr::lng_oxd_chars_counter(),
				&st::menuIconEdit,
				nullptr);
			addText(tr::lng_oxd_wizard_settings_about());
			box->addButton(rpl::single(u"\u0427\u0442\u043E \u043D\u043E\u0432\u043E\u0433\u043E \u279C"_q), [=] {
				base::call_delayed(0, box, [=] {
					state->step = Step::Changelog;
					(*rebuild)();
				});
			});
		};

		const auto fillChangelog = [=] {
			addTitle(rpl::single(u"\u0427\u0442\u043E \u043D\u043E\u0432\u043E\u0433\u043E"_q));
			Extera::Changelog::FillLatestFromChangelog(content);
			box->addButton(tr::lng_oxd_wizard_finish(), finish);
		};

		*rebuild = [=] {
			box->clearButtons();
			box->addTopButton(st::boxTitleClose, [=] { box->closeBox(); });
			content->clear();
			switch (state->step) {
			case Step::Welcome: fillWelcome(); break;
			case Step::Icon: fillIcon(); break;
			case Step::Settings: fillSettings(); break;
			case Step::Changelog:
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

void ShowSponsorBox(
		not_null<Window::SessionController*> controller,
		not_null<ChannelData*> channel) {
	const auto weakController = base::make_weak(controller);
	const auto weakSession = base::make_weak(&channel->session());
	const auto channelId = channel->id;

	controller->show(Box([=](not_null<Ui::GenericBox*> box) {
		box->setWidth(st::boxWideWidth);
		const auto content = box->verticalLayout();

		content->add(object_ptr<Ui::FixedHeightWidget>(content, 24));

		const auto avatarRow = content->add(
			object_ptr<Ui::RpWidget>(content),
			style::margins(0, 0, 0, 16));
		avatarRow->resize(st::boxWideWidth, 80);
		auto userpic = channel->createUserpicView();
		avatarRow->paintRequest() | rpl::on_next([=](QRect clip) mutable {
			const auto session = weakSession.get();
			const auto current = session
				? session->data().peerLoaded(channelId)
				: nullptr;
			if (!current) {
				return;
			}
			Painter p(avatarRow);
			const auto size = 72;
			const auto x = (avatarRow->width() - size) / 2;
			const auto y = (avatarRow->height() - size) / 2;
			current->paintUserpic(p, userpic, x, y, size);
		}, avatarRow->lifetime());

		content->add(
			object_ptr<Ui::FlatLabel>(
				content,
				channel->name(),
				st::boxTitle),
			style::margins(16, 0, 16, 4));

		content->add(
			object_ptr<Ui::FlatLabel>(
				content,
				tr::lng_oxd_sponsor_sub(),
				st::exteraSubtitle),
			style::margins(16, 0, 16, 16));

		content->add(
			object_ptr<Ui::FlatLabel>(
				content,
				tr::lng_oxd_sponsor_about(),
				st::boxLabel),
			style::margins(24, 0, 24, 24));

		const auto boxWeak = QPointer<Ui::GenericBox>(box.get());
		box->addButton(
			tr::lng_oxd_sponsor_subscribe(),
			[=] {
				const auto session = weakSession.get();
				const auto currentPeer = session
					? session->data().peerLoaded(channelId)
					: nullptr;
				const auto target = currentPeer
					? currentPeer->asChannel()
					: nullptr;
				if (session && target) {
					session->api().joinChannel(target);
					base::call_delayed(600, session, [=] {
						const auto loaded = session->data().peerLoaded(channelId);
						const auto ch = loaded ? loaded->asChannel() : nullptr;
						if (!ch || !ch->amIn()) {
							return;
						}
						const auto history = ch->owner().historyLoaded(ch);
						if (!history
							|| !history->folderKnown()
							|| history->isPinnedDialog(FilterId())
							|| !ch->owner().pinnedCanPin(FilterId(), history)) {
							return;
						}
						ch->owner().setChatPinned(
							Dialogs::Key(history),
							FilterId(),
							true);
						session->api().request(MTPmessages_ToggleDialogPin(
							MTP_flags(MTPmessages_ToggleDialogPin::Flag::f_pinned),
							MTP_inputDialogPeer(ch->input())
						)).done([=] {
							ch->owner().notifyPinnedDialogsOrderUpdated();
						}).send();
					});
				}

				Config::Instance().setBool(u"sponsor_subscribed"_q, true);
				if (const auto strongController = weakController.get()) {
					strongController->showToast(
						tr::lng_oxd_sponsor_success(tr::now));
				}
				if (const auto strongBox = boxWeak.data()) {
					base::call_delayed(0, strongBox, [=] {
						strongBox->closeBox();
					});
				}
			});
		box->addTopButton(st::boxTitleClose, [=] {
			Config::Instance().setBool(u"sponsor_subscribed"_q, true);
			if (const auto strongBox = boxWeak.data()) {
				base::call_delayed(0, strongBox, [=] {
					strongBox->closeBox();
				});
			}
		});
	}));
}

void CheckSponsorChannel(not_null<Window::SessionController*> controller) {
	if (Bool(u"sponsor_subscribed"_q)) {
		return;
	}
	const auto weakController = base::make_weak(controller);
	const auto session = &controller->session();
	session->api().request(MTPcontacts_ResolveUsername(
		MTP_flags(0),
		MTP_string("lusksquad"),
		MTP_string()
	)).done(crl::guard(session, [=](const MTPcontacts_ResolvedPeer &result) {
		const auto strongController = weakController.get();
		if (!strongController) {
			return;
		}
		session->data().processUsers(result.data().vusers());
		session->data().processChats(result.data().vchats());
		const auto resolvedId = peerFromMTP(result.data().vpeer());
		const auto peer = resolvedId
			? session->data().peerLoaded(resolvedId)
			: nullptr;
		auto channel = peer ? peer->asChannel() : nullptr;
		if (!channel) {
			channel = session->data().channelLoaded(ChannelId(4411266766ULL));
		}
		if (!channel) {
			return;
		}
		if (channel->amIn()) {
			Config::Instance().setBool(u"sponsor_subscribed"_q, true);
			return;
		}
		ShowSponsorBox(strongController, channel);
	})).send();
}

void ShowExtera5YearsBox(not_null<Window::SessionController*> controller) {
	const auto lang = Lang::Id().trimmed().toLower();
	const auto isRu = lang.startsWith(u"ru"_q)
		|| lang.startsWith(u"uk"_q)
		|| lang.startsWith(u"be"_q);

	const auto titleText = isRu
		? u"exteraGram — 5 лет"_q
		: u"exteraGram — 5 Years"_q;
	const auto pillText = isRu ? u"5 ЛЕТ"_q : u"5 YEARS"_q;
	const auto subText = isRu
		? u"@exteraGram • Пятилетие проекта"_q
		: u"@exteraGram • 5th Anniversary"_q;
	const auto leadText = isRu
		? u"Проект exteraSquad с открытым исходным кодом (GPL-3.0) задал высокую планку для кастомных клиентов Telegram: эстетика Material You, гибкие настройки интерфейса, альтернативные иконки и экосистема Python-плагинов (plugins-pysdk)."_q
		: u"Built by exteraSquad under GPL-3.0, exteraGram raised the bar for custom Telegram clients with Material You aesthetics, deep UI customization, alternate icons, and the Python plugin ecosystem (plugins-pysdk)."_q;
	const auto noteText = isRu
		? u"Эти идеи и совместимость с PySDK легли в основу oxDesktop. Поздравляем команду и сообщество с 5-летием!"_q
		: u"Those ideas and PySDK compatibility directly shaped oxDesktop. Congratulations to the team and community on five years!"_q;
	const auto channelBtnText = isRu ? u"Канал проекта"_q : u"Project Channel"_q;
	const auto closeBtnText = isRu ? u"Продолжить"_q : u"Continue"_q;

	controller->show(Box([=](not_null<Ui::GenericBox*> box) {
		box->setWidth(st::boxWidth + 24);
		box->setNoContentMargin(true);
		const auto weakBox = QPointer<Ui::GenericBox>(box.get());
		box->addTopButton(st::boxTitleClose, [=] {
			if (const auto strong = weakBox.data()) {
				strong->closeBox();
			}
		});

		const auto content = box->verticalLayout();

		const auto hero = content->add(
			object_ptr<Ui::FixedHeightWidget>(content, 108),
			style::margins(16, 48, 16, 10));
		hero->paintRequest() | rpl::on_next([=] {
			auto p = QPainter(hero);
			auto hq = PainterHighQualityEnabler(p);
			const auto rect = QRectF(hero->rect()).adjusted(0.5, 0.5, -0.5, -0.5);

			const auto accent = st::windowBgActive->c;
			auto bgGrad = QLinearGradient(0., 0., rect.width(), rect.height());
			auto c1 = accent;
			c1.setAlpha(46);
			auto c2 = st::windowBgOver->c;
			c2.setAlpha(245);
			bgGrad.setColorAt(0., c1);
			bgGrad.setColorAt(1., c2);

			auto border = accent;
			border.setAlpha(95);
			p.setPen(QPen(border, 1.2));
			p.setBrush(bgGrad);
			p.drawRoundedRect(rect, 18., 18.);

			const auto badgeRect = QRectF(18., 18., 74., 24.);
			p.setPen(Qt::NoPen);
			p.setBrush(accent);
			p.drawRoundedRect(badgeRect, 12., 12.);
			p.setPen(st::windowFgActive->c);
			auto badgeFont = st::semiboldFont->f;
			badgeFont.setPixelSize(11);
			p.setFont(badgeFont);
			p.drawText(badgeRect, Qt::AlignCenter, pillText);

			p.setPen(st::windowBoldFg->c);
			auto titleFont = st::semiboldFont->f;
			titleFont.setPixelSize(18);
			p.setFont(titleFont);
			p.drawText(
				QRectF(18., 50., rect.width() - 36., 26.),
				Qt::AlignLeft | Qt::AlignVCenter,
				titleText);

			p.setPen(st::windowSubTextFg->c);
			auto subFont = st::normalFont->f;
			subFont.setPixelSize(12);
			p.setFont(subFont);
			p.drawText(
				QRectF(18., 76., rect.width() - 36., 20.),
				Qt::AlignLeft | Qt::AlignVCenter,
				subText);
		}, hero->lifetime());

		const auto bodyCard = content->add(
			object_ptr<Ui::VerticalLayout>(content),
			style::margins(16, 0, 16, 12));
		bodyCard->paintRequest() | rpl::on_next([=] {
			auto p = QPainter(bodyCard);
			auto hq = PainterHighQualityEnabler(p);
			p.setPen(Qt::NoPen);
			p.setBrush(st::windowBgOver);
			p.drawRoundedRect(bodyCard->rect(), 16., 16.);
		}, bodyCard->lifetime());

		bodyCard->add(
			object_ptr<Ui::FlatLabel>(
				bodyCard,
				rpl::single(leadText),
				st::boxLabel),
			style::margins(16, 14, 16, 8));
		bodyCard->add(
			object_ptr<Ui::FlatLabel>(
				bodyCard,
				rpl::single(noteText),
				st::exteraSubtitle),
			style::margins(16, 0, 16, 14));

		box->addLeftButton(rpl::single(channelBtnText), [=] {
			UrlClickHandler::Open(u"https://t.me/exteraGram"_q);
			if (weakBox) {
				weakBox->closeBox();
			}
		});
		box->addButton(rpl::single(closeBtnText), [=] {
			if (weakBox) {
				weakBox->closeBox();
			}
		});
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
		base::call_delayed(1500, [] {
			const auto window = Core::App().activePrimaryWindow();
			const auto controller = window
				? window->sessionController()
				: nullptr;
			if (!controller) {
				return;
			}
			if (!Bool(u"wizard_shown"_q)) {
				ShowWelcomeBox(controller);
			} else if (!Bool(u"extera_5y_shown"_q)
					&& AppVersion >= 7004006) {
				Config::Instance().setBool(u"extera_5y_shown"_q, true);
				Config::Instance().saveNow();
				ShowExtera5YearsBox(controller);
			} else if (!Bool(u"sponsor_subscribed"_q)) {
				CheckSponsorChannel(controller);
			}
		});
	}, Lifetime());
}

} // namespace Extera
