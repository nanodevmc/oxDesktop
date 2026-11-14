#include <QtWidgets/QApplication>
#include "extera/extera_menu.h"

#include "api/api_common.h"
#include "apiwrap.h"
#include "base/unixtime.h"
#include "base/event_filter.h"
#include "data/data_chat_participant_status.h"
#include "data/data_document.h"
#include "data/data_media_types.h"
#include "data/data_peer.h"
#include "data/data_session.h"
#include "extera/extera_config.h"
#include "ui/widgets/menu/menu_common.h"
#include "ui/widgets/menu/menu_action.h"
#include "ui/widgets/menu/menu_item_base.h"
#include "ui/painter.h"
#include "ui/abstract_button.h"
#include "styles/style_chat.h"
#include "styles/style_settings.h"
#include "styles/style_widgets.h"
#include <QtCore/QTimer>
#include <QtGui/QClipboard>
#include <QtGui/QGuiApplication>
#include "data/data_file_click_handler.h"
#include "data/data_photo.h"
#include "data/data_photo_media.h"
#include "extera/extera_ip_info.h"
#include "extera/extera_lyrics.h"
#include "extera/extera_platform.h"
#include "extera/extera_utils.h"
#include "extera/extera_plugins_ui.h"
#include "history/history.h"
#include "history/history_item.h"
#include "history/history_item_components.h"
#include "history/view/controls/history_view_draft_options.h"
#include "lang/lang_keys.h"
#include "main/main_session.h"
#include "ui/boxes/confirm_box.h"
#include "ui/text/format_values.h"
#include "ui/widgets/popup_menu.h"
#include "window/window_session_controller.h"
#include "styles/style_menu_icons.h"

namespace Extera {
namespace {

constexpr auto kMaxQuickActions = 5;

class DetailAction final : public Ui::Menu::ItemBase {
public:
	DetailAction(
		not_null<Ui::Menu::Menu*> parent,
		const style::Menu &st,
		const style::icon *icon,
		const QString &title,
		const QString &value);

	bool isEnabled() const override;
	not_null<QAction*> action() const override;

protected:
	int contentHeight() const override;
	void paintEvent(QPaintEvent *e) override;

private:
	const not_null<QAction*> _dummyAction;
	const style::Menu &_st;
	const style::icon *_icon = nullptr;
	const QString _title;
	const QString _value;
	int _height = 0;

};

DetailAction::DetailAction(
	not_null<Ui::Menu::Menu*> parent,
	const style::Menu &st,
	const style::icon *icon,
	const QString &title,
	const QString &value)
: ItemBase(parent, st)
, _dummyAction(Ui::CreateChild<QAction>(parent.get()))
, _st(st)
, _icon(icon)
, _title(title)
, _value(value) {
	_height = _st.itemPadding.top()
		+ _st.itemStyle.font->height
		+ st::normalFont->height
		+ _st.itemPadding.bottom();
	setMinWidth(_st.itemPadding.left()
		+ std::max(
			_st.itemStyle.font->width(_title),
			st::normalFont->width(_value))
		+ _st.itemPadding.right());
	fitToMenuWidth();
	enableMouseSelecting();
	setActionTriggered([=] {
		QGuiApplication::clipboard()->setText(_value);
	});
}

bool DetailAction::isEnabled() const {
	return true;
}

not_null<QAction*> DetailAction::action() const {
	return _dummyAction;
}

int DetailAction::contentHeight() const {
	return _height;
}

void DetailAction::paintEvent(QPaintEvent *e) {
	auto p = Painter(this);
	const auto selected = isSelected();
	p.fillRect(rect(), selected ? _st.itemBgOver : _st.itemBg);
	RippleButton::paintRipple(p, 0, 0);
	if (_icon) {
		_icon->paint(
			p,
			_st.itemIconPosition.x(),
			(_height - _icon->height()) / 2,
			width());
	}
	const auto left = _st.itemPadding.left();
	const auto available = width() - left - _st.itemPadding.right();
	auto top = _st.itemPadding.top();
	p.setFont(_st.itemStyle.font);
	p.setPen(selected ? _st.itemFgOver : _st.itemFg);
	p.drawTextLeft(
		left,
		top,
		width(),
		_st.itemStyle.font->elided(_title, available));
	top += _st.itemStyle.font->height;
	p.setFont(st::normalFont);
	p.setPen(selected ? _st.itemFgShortcutOver : _st.itemFgShortcut);
	p.drawTextLeft(
		left,
		top,
		width(),
		st::normalFont->elided(_value, available));
}

struct QuickEntry {
	QString id;
	std::vector<tr::phrase<>> labels;
	const style::icon *icon = nullptr;
};

[[nodiscard]] const std::vector<QuickEntry> &QuickEntries() {
	static const auto result = std::vector<QuickEntry>{
		{
			u"reply"_q,
			{
				tr::lng_context_reply_msg,
				tr::lng_exd_queue_reply_badge,
				tr::lng_context_quote_and_reply,
			},
			&st::menuIconReply,
		},
		{ u"delete"_q, { tr::lng_context_delete_msg }, &st::menuIconDelete },
		{
			u"copy"_q,
			{
				tr::lng_context_copy_text,
				tr::lng_context_copy_selected,
				tr::lng_context_copy_image,
			},
			&st::menuIconCopy,
		},
		{ u"edit"_q, { tr::lng_context_edit_msg }, &st::menuIconEdit },
		{
			u"forward"_q,
			{ tr::lng_context_forward_msg },
			&st::menuIconForward,
		},
		{
			u"pin"_q,
			{ tr::lng_context_pin_msg, tr::lng_context_unpin_msg },
			&st::menuIconPin,
		},
		{ u"select"_q, { tr::lng_context_select_msg }, &st::menuIconSelect },
	};
	return result;
}

class QuickRow final : public Ui::Menu::ItemBase {
public:
	QuickRow(
		not_null<Ui::Menu::Menu*> parent,
		const style::Menu &st,
		Fn<void()> hide,
		Fn<void()> hideSubmenus);

	void addButton(
		not_null<QAction*> action,
		const style::icon *icon,
		const QString &label);

	bool isEnabled() const override;
	not_null<QAction*> action() const override;

protected:
	int contentHeight() const override;
	void paintEvent(QPaintEvent *e) override;

private:
	void layout();
	void updateHovered();
	[[nodiscard]] int dividerHeight() const;

	const not_null<QAction*> _dummyAction;
	const style::Menu &_st;
	const Fn<void()> _hide;
	const Fn<void()> _hideSubmenus;
	std::vector<not_null<Ui::AbstractButton*>> _buttons;
	std::vector<not_null<QAction*>> _actions;
	int _hovered = -1;
	int _pressed = -1;

};

QuickRow::QuickRow(
	not_null<Ui::Menu::Menu*> parent,
	const style::Menu &st,
	Fn<void()> hide,
	Fn<void()> hideSubmenus)
: ItemBase(parent, st)
, _dummyAction(Ui::CreateChild<QAction>(parent.get()))
, _st(st)
, _hide(std::move(hide))
, _hideSubmenus(std::move(hideSubmenus)) {
	fitToMenuWidth();
	widthValue() | rpl::on_next([=] {
		layout();
	}, lifetime());
	base::install_event_filter(this, qApp, [=](not_null<QEvent*> e) {
		const auto type = e->type();
		if (type == QEvent::MouseMove
			|| type == QEvent::Leave
			|| type == QEvent::Enter) {
			updateHovered();
		} else if (type == QEvent::MouseButtonPress) {
			updateHovered();
			if (_hovered >= 0) {
				_pressed = _hovered;
				_buttons[_pressed]->update();
				return base::EventFilterResult::Cancel;
			}
		} else if (type == QEvent::MouseButtonRelease && _pressed >= 0) {
			updateHovered();
			const auto pressed = std::exchange(_pressed, -1);
			_buttons[pressed]->update();
			if (pressed == _hovered) {
				const auto action = _actions[pressed];
				const auto weak = base::make_weak(this);
				action->trigger();
				if (weak) {
					_hide();
				}
			}
			return base::EventFilterResult::Cancel;
		}
		return base::EventFilterResult::Continue;
	});
}

void QuickRow::updateHovered() {
	const auto local = mapFromGlobal(QCursor::pos());
	auto hovered = -1;
	if (isVisible() && rect().contains(local)) {
		for (auto i = 0; i != int(_buttons.size()); ++i) {
			if (_buttons[i]->geometry().contains(local)) {
				hovered = i;
				break;
			}
		}
	}
	if (_hovered != hovered) {
		_hovered = hovered;
		if (hovered >= 0 && _hideSubmenus) {
			_hideSubmenus();
		}
		for (const auto button : _buttons) {
			button->update();
		}
	}
}

void QuickRow::addButton(
		not_null<QAction*> action,
		const style::icon *icon,
		const QString &label) {
	action->setParent(this);
	const auto button = Ui::CreateChild<Ui::AbstractButton>(this);
	const auto index = int(_buttons.size());
	button->setAccessibleName(label);
	button->setPointerCursor(true);
	button->setAttribute(Qt::WA_TransparentForMouseEvents);
	button->paintRequest() | rpl::on_next([=] {
		auto p = QPainter(button);
		if (_hovered == index || _pressed == index) {
			auto hq = PainterHighQualityEnabler(p);
			p.setPen(QPen(QColor(46, 204, 113, 80), 1.0));
			p.setBrush(_st.itemBgOver);
			const auto radius = st::roundRadiusLarge;
			p.drawRoundedRect(button->rect().adjusted(1, 1, -1, -1), radius, radius);
		}
		icon->paintInCenter(p, button->rect());
	}, button->lifetime());
	_buttons.push_back(button);
	_actions.push_back(action);
	setMinWidth(int(_buttons.size()) * st::exteraQuickButtonWidth
		+ 2 * st::exteraQuickPadding);
	layout();
}

void QuickRow::layout() {
	if (_buttons.empty()) {
		return;
	}
	const auto padding = st::exteraQuickPadding;
	const auto available = width() - 2 * padding;
	const auto count = int(_buttons.size());
	const auto each = available / count;
	for (auto i = 0; i != count; ++i) {
		_buttons[i]->setGeometry(
			padding + i * each,
			dividerHeight() + padding,
			each,
			st::exteraQuickHeight - 2 * padding);
	}
}

bool QuickRow::isEnabled() const {
	return false;
}

not_null<QAction*> QuickRow::action() const {
	return _dummyAction;
}

int QuickRow::dividerHeight() const {
	const auto &divider = st::expandedMenuSeparator;
	return divider.padding.top() + divider.width + divider.padding.bottom();
}

int QuickRow::contentHeight() const {
	return dividerHeight() + st::exteraQuickHeight;
}

void QuickRow::paintEvent(QPaintEvent *e) {
	auto p = QPainter(this);
	const auto &divider = st::expandedMenuSeparator;
	p.fillRect(
		divider.padding.left(),
		divider.padding.top(),
		width() - divider.padding.left() - divider.padding.right(),
		divider.width,
		divider.fg);
}

[[nodiscard]] QString FormatFullDate(TimeId date) {
	const auto parsed = base::unixtime::parse(date);
	return tr::lng_mediaview_date_time(
		tr::now,
		lt_date,
		langDayOfMonthFull(parsed.date()),
		lt_time,
		QLocale().toString(parsed.time(), QLocale::ShortFormat));
}

void FillDetails(
		not_null<Ui::PopupMenu*> menu,
		not_null<HistoryItem*> item) {
	const auto st = menu->st().menu;

	const auto add = [&](
			const style::icon *icon,
			const QString &title,
			const QString &value) {
		if (value.isEmpty()) {
			return;
		}
		menu->addAction(base::make_unique_q<DetailAction>(
			menu->menu(),
			st,
			icon,
			title,
			value));
	};

	add(
		&st::menuIconInfo,
		tr::lng_extera_details_id(tr::now),
		QString::number(item->id.bare));
	add(
		&st::menuIconChatBubble,
		tr::lng_extera_details_chat(tr::now),
		item->history()->peer->name());
	if (const auto from = item->from()) {
		if (from != item->history()->peer) {
			add(
				&st::menuIconProfile,
				tr::lng_extera_details_sender(tr::now),
				from->name());
		}
	}
	add(
		&st::menuIconSchedule,
		tr::lng_extera_details_date(tr::now),
		FormatFullDate(item->date()));
	if (item->hasDirectLink()) {
		if (const auto ms = item->layout()->customSenderTitle()) {
			if (ms->media && ms->media->isEdited()) {
				add(
					&st::menuIconEdit,
					tr::lng_extera_details_edited(tr::now),
					QString::fromUtf8("Yes"));
			}
		}
	}
	if (const auto fwd = item->Get<HistoryMessageForwarded>()) {
		add(
			&st::menuIconForward,
			tr::lng_extera_details_forwarded(tr::now),
			fwd->originalSender ? fwd->originalSender->name() : fwd->originalAuthor);
	}
	if (const auto media = item->media()) {
		if (const auto document = media->document()) {
			const auto name = document->filename();
			if (!name.isEmpty()) {
				add(
					&st::menuIconFile,
					tr::lng_extera_details_file(tr::now),
					name);
			}
			add(
				&st::menuIconInfo,
				tr::lng_extera_details_size(tr::now),
				Ui::FormatSizeText(document->size));
			const auto path = document->filepath(true);
			if (!path.isEmpty()) {
				const auto platform = Extera::Platform::DetectFromFile(path);
				if (platform != Extera::Platform::SenderPlatform::Unknown) {
					add(
						&st::menuIconDevices,
						tr::lng_extera_platform_sender(tr::now),
						Extera::Platform::FormatPlatform(platform));
				}
			}
		}
	}
}

} // namespace

void AddMessageMenuActions(
		not_null<Ui::PopupMenu*> menu,
		not_null<HistoryItem*> item,
		not_null<Window::SessionController*> controller) {
	if (const auto media = item->media()) {
		if (const auto photo = media->photo()) {
			if (const auto image = photo->createMediaView(); image && image->loaded()) {
				const auto pixmap = image->pixmap();
				if (!pixmap.isNull()) {
					menu->addAction(tr::lng_extera_menu_copy_photo(tr::now), [=] {
						QGuiApplication::clipboard()->setPixmap(pixmap);
					}, &st::menuIconCopy);
				}
			}
		}
		if (const auto document = media->document()) {
			const auto path = document->filepath(true);
			if (!path.isEmpty()) {
				menu->addAction(tr::lng_extera_menu_save(tr::now), [=] {
					DocumentOpenClickHandler::Save(
						Data::FileOrigin(),
						document,
						DocumentOpenClickHandler::Mode::ForceSaveAs);
				}, &st::menuIconDownload);
			}
		}
	}

	const auto ip = Extera::IpInfo::ExtractIp(item->originalText().text);
	if (!ip.isEmpty() && Extera::IpInfo::IsAvailable()) {
		menu->addAction(tr::lng_extera_inspect_ip(tr::now) + " (" + ip + ")", [=] {
			Extera::IpInfo::Inspect(controller, ip);
		}, &st::menuIconSearch);
	}

	if (const auto media = item->media()) {
		if (const auto document = media->document()) {
			if (document->isSong()) {
				const auto artist = document->song()->artist;
				const auto title = document->song()->title;
				const auto duration = document->song()->duration;
				menu->addAction(tr::lng_extera_player_lyrics(tr::now), [=] {
					Extera::Lyrics::ShowBox(controller, artist, title, duration);
				}, &st::menuIconMusic);
			}
		}
	}

	const auto text = item->originalText().text;
	if (text.contains(u"://"_q)) {
		const auto cleaned = Extera::CleanTextUrls(text);
		if (cleaned != text) {
			menu->addAction(tr::lng_extera_menu_clean_text(tr::now), [=] {
				QGuiApplication::clipboard()->setText(cleaned);
			}, &st::menuIconCopy);
		}
	}

	if (item->out() && item->isRegular()) {
		menu->addAction(tr::lng_extera_menu_repeat(tr::now), [=] {
			auto action = Api::SendAction(item->history());
			action.replyTo = item->replyTo();
			action.generateLocal = true;
			item->history()->session().api().forwardMessages(
				Data::ForwardDraft{
					.ids = { item->fullId() },
					.action = action,
				},
				[=] {});
		}, &st::menuIconRestart);
	}

	Extera::Plugins::AddMenuActions(menu, item, controller);

	if (Bool(u"menu_message_details"_q)) {
		const auto action = menu->addAction(
			tr::lng_extera_menu_details(tr::now),
			[] {},
			&st::menuIconInfo);
		action->setMenu(Ui::CreateChild<QMenu>(menu->menu().get()));
		FillDetails(
			menu->ensureSubmenu(action, st::popupMenuWithIcons),
			item);
	}
}

QStringList QuickActionIds() {
	auto result = QStringList();
	for (const auto &entry : QuickEntries()) {
		result.push_back(entry.id);
	}
	return result;
}

QString QuickActionTitle(const QString &id) {
	for (const auto &entry : QuickEntries()) {
		if (entry.id == id) {
			return entry.labels.front()(tr::now);
		}
	}
	return id;
}

const style::icon *QuickActionIcon(const QString &id) {
	for (const auto &entry : QuickEntries()) {
		if (entry.id == id) {
			return entry.icon;
		}
	}
	return nullptr;
}

void CloseSubmenusOutside(not_null<Ui::PopupMenu*> menu) {
	const auto weak = base::make_weak(menu.get());
	const auto timer = new QTimer(menu.get());
	QObject::connect(timer, &QTimer::timeout, [=] {
		const auto strong = weak.get();
		if (!strong || !strong->isVisible()) {
			return;
		}
		const auto cursor = QCursor::pos();
		if (!strong->geometry().contains(cursor)) {
			return;
		}
		const auto inner = strong->menu();
		if (QRect(inner->mapToGlobal(QPoint()), inner->size()).contains(cursor)) {
			return;
		}
		auto submenus = std::vector<Ui::PopupMenu*>();
		for (const auto widget : QApplication::topLevelWidgets()) {
			const auto popup = dynamic_cast<Ui::PopupMenu*>(widget);
			if (!popup || popup == strong || !popup->isVisible()) {
				continue;
			}
			if (popup->geometry().contains(cursor)) {
				return;
			}
			submenus.push_back(popup);
		}
		for (const auto popup : submenus) {
			popup->hideMenu(true);
		}
	});
	timer->start(100);
}

void ApplyQuickActions(not_null<Ui::PopupMenu*> menu) {
	CloseSubmenusOutside(menu);
	if (!Bool(u"menu_quick_row"_q)) {
		return;
	}
	const auto ids = String(u"menu_quick_items"_q).split(
		',',
		Qt::SkipEmptyParts);
	struct Found {
		QAction *action = nullptr;
		const style::icon *icon = nullptr;
		QString label;
	};
	auto found = std::vector<Found>();
	for (const auto &id : ids) {
		if (found.size() >= kMaxQuickActions) {
			break;
		}
		const auto entry = ranges::find(QuickEntries(), id, &QuickEntry::id);
		if (entry == end(QuickEntries())) {
			continue;
		}
		for (const auto action : menu->actions()) {
			if (action->isSeparator() || action->menu()) {
				continue;
			}
			const auto text = action->text();
			const auto matches = ranges::any_of(entry->labels, [&](
					const tr::phrase<> &label) {
				return text == label(tr::now);
			});
			if (matches) {
				found.push_back({ action.get(), entry->icon, text });
				break;
			}
		}
	}
	if (found.empty()) {
		return;
	}
	const auto weak = base::make_weak(menu.get());
	auto row = base::make_unique_q<QuickRow>(
		menu->menu(),
		menu->st().menu,
		[=] {
			if (const auto strong = weak.get()) {
				strong->hideMenu();
			}
		},
		[=] {
			const auto strong = weak.get();
			if (!strong) {
				return;
			}
			for (const auto widget : QApplication::topLevelWidgets()) {
				const auto popup = dynamic_cast<Ui::PopupMenu*>(widget);
				if (popup && popup != strong && popup->isVisible()) {
					popup->hideMenu(true);
				}
			}
		});
	for (const auto &entry : found) {
		row->addButton(entry.action, entry.icon, entry.label);
	}
	for (const auto &entry : found) {
		const auto &actions = menu->actions();
		const auto i = ranges::find_if(actions, [&](not_null<QAction*> a) {
			return a.get() == entry.action;
		});
		if (i != end(actions)) {
			menu->removeAction(int(i - begin(actions)));
		}
	}
	auto previousSeparator = true;
	for (auto i = 0; i < int(menu->actions().size());) {
		const auto separator = menu->actions()[i]->isSeparator();
		if (separator && previousSeparator) {
			menu->removeAction(i);
			continue;
		}
		previousSeparator = separator;
		++i;
	}
	while (!menu->empty() && menu->actions().back()->isSeparator()) {
		menu->removeAction(int(menu->actions().size()) - 1);
	}
	auto lastSeparator = -1;
	for (auto i = 0; i != int(menu->actions().size()); ++i) {
		if (menu->actions()[i]->isSeparator()) {
			lastSeparator = i;
		}
	}
	if (lastSeparator > 0) {
		menu->insertAction(lastSeparator, std::move(row));
	} else {
		menu->addAction(std::move(row));
	}
}

} // namespace Extera
