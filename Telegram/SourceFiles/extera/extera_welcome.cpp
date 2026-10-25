#include "extera/extera_welcome.h"

#include "base/call_delayed.h"
#include "core/application.h"
#include "core/version.h"
#include "extera/extera_config.h"
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
		u"exteradesktop.xyz"_q,
		u"https://exteradesktop.xyz"_q,
		&st::exteraIconWebsite);
	AddLinkButton(
		container,
		tr::lng_extera_welcome_dev(),
		u"@metawka"_q,
		u"https://t.me/metawka"_q,
		&st::exteraIconDeveloper);
	AddLinkButton(
		container,
		tr::lng_extera_welcome_channel(),
		u"@exDesktop"_q,
		u"https://t.me/exDesktop"_q,
		&st::exteraIconChannel);
}

void ShowWelcomeBox(not_null<Window::SessionController*> controller) {
	controller->show(Box([=](not_null<Ui::GenericBox*> box) {
		box->setWidth(st::boxWideWidth);
		const auto content = box->verticalLayout();
		const auto size = st::exteraHeaderLogoSize;
		const auto logo = content->add(
			object_ptr<Ui::FixedHeightWidget>(content, size),
			st::exteraHeaderLogoPadding);
		logo->paintRequest(
		) | rpl::on_next([=] {
			auto p = QPainter(logo);
			auto hq = PainterHighQualityEnabler(p);
			p.drawImage(
				QRect((logo->width() - size) / 2, 0, size, size),
				Window::Logo());
		}, logo->lifetime());
		content->add(
			object_ptr<Ui::FlatLabel>(
				content,
				rpl::single(AppName.utf16()),
				st::exteraHeaderTitle),
			st::exteraHeaderTitlePadding,
			style::al_top);
		content->add(
			object_ptr<Ui::FlatLabel>(
				content,
				tr::lng_extera_unofficial_title(),
				st::exteraWelcomeBadge),
			st::exteraHeaderVersionPadding,
			style::al_top);
		FillUnofficialInfo(content);
		box->addButton(tr::lng_extera_welcome_continue(), [=] {
			box->closeBox();
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
		if (Bool(u"welcome_shown"_q)) {
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
			Config::Instance().setBool(u"welcome_shown"_q, true);
			ShowWelcomeBox(controller);
		});
	}, Lifetime());
}

} // namespace Extera
