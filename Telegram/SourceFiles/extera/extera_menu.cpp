#include "extera/extera_menu.h"

#include "api/api_common.h"
#include "apiwrap.h"
#include "base/unixtime.h"
#include "data/data_chat_participant_status.h"
#include "data/data_document.h"
#include "data/data_media_types.h"
#include "data/data_peer.h"
#include "data/data_session.h"
#include "extera/extera_config.h"
#include "ui/widgets/menu/menu_common.h"
#include "ui/widgets/menu/menu_action.h"
#include "extera/extera_utils.h"
#include "extera/extera_plugins_ui.h"
#include "history/history.h"
#include "history/history_item.h"
#include "history/history_item_components.h"
#include "lang/lang_keys.h"
#include "main/main_session.h"
#include "ui/boxes/confirm_box.h"
#include "ui/text/format_values.h"
#include "ui/widgets/popup_menu.h"
#include "window/window_session_controller.h"
#include "styles/style_menu_icons.h"

namespace Extera {
namespace {

[[nodiscard]] QString FormatDate(TimeId date) {
	return QLocale().toString(
		base::unixtime::parse(date),
		QLocale::ShortFormat);
}

[[nodiscard]] TextWithEntities DetailsText(not_null<HistoryItem*> item) {
	auto lines = QStringList();
	const auto add = [&](const QString &label, const QString &value) {
		lines.push_back(label + u": "_q + value);
	};
	add(tr::lng_extera_details_id(tr::now), QString::number(item->id.bare));
	add(
		tr::lng_extera_details_chat(tr::now),
		QString::number(item->history()->peer->id.value & PeerId::kChatTypeMask));
	if (const auto from = item->from()) {
		add(
			tr::lng_extera_details_sender(tr::now),
			QString::number(from->id.value & PeerId::kChatTypeMask));
	}
	add(tr::lng_extera_details_date(tr::now), FormatDate(item->date()));
	if (const auto edited = item->Get<HistoryMessageEdited>()) {
		if (edited->date) {
			add(
				tr::lng_extera_details_edited(tr::now),
				FormatDate(edited->date));
		}
	}
	if (const auto media = item->media()) {
		if (const auto document = media->document()) {
			if (!document->filename().isEmpty()) {
				add(tr::lng_extera_details_file(tr::now), document->filename());
			}
			add(
				tr::lng_extera_details_size(tr::now),
				Ui::FormatSizeText(document->size));
		}
	}
	return TextWithEntities{ lines.join('\n') };
}

} // namespace

void AddMessageMenuActions(
		not_null<Ui::PopupMenu*> menu,
		not_null<HistoryItem*> item,
		not_null<Window::SessionController*> controller) {
	if (!item->isRegular()) {
		return;
	}
	const auto itemId = item->fullId();
	const auto session = &item->history()->session();
	if (const auto edited = item->Get<HistoryMessageEdited>()) {
		if (edited->date > 0) {
			const auto parsed = base::unixtime::parse(edited->date);
			const auto time = FormatTime(parsed.time());
			const auto text = (parsed.date() == QDate::currentDate())
				? tr::lng_extera_edited_at(tr::now, lt_time, time)
				: tr::lng_extera_edited_at_date(
					tr::now,
					lt_date,
					QLocale().toString(parsed.date(), u"dd.MM.yy"_q),
					lt_time,
					time);
			const auto inner = menu->menu();
			menu->insertAction(0, base::make_unique_q<Ui::Menu::Action>(
				inner,
				menu->st().menu,
				Ui::Menu::CreateAction(inner, text, [] {}),
				&st::menuIconSchedule,
				&st::menuIconSchedule));
		}
	}
	if (Bool(u"menu_repeat"_q)
		&& item->allowsForward()
		&& Data::CanSendAnything(item->history())) {
		menu->addAction(tr::lng_extera_menu_repeat(tr::now), [=] {
			if (const auto item = session->data().message(itemId)) {
				session->api().forwardMessages(
					Data::ResolvedForwardDraft{
						.items = { item },
						.options = Data::ForwardOptions::NoSenderNames,
					},
					Api::SendAction(item->history()));
			}
		}, &st::menuIconRestore);
	}
	Plugins::AddMessageMenuItems(menu, item);
	if (Bool(u"menu_details"_q)) {
		menu->addAction(tr::lng_extera_menu_details(tr::now), [=] {
			if (const auto item = session->data().message(itemId)) {
				controller->show(Ui::MakeInformBox(DetailsText(item)));
			}
		}, &st::menuIconInfo);
	}
}

} // namespace Extera
