#include "extera/extera_security.h"

#include "lang/lang_keys.h"
#include "main/session/session_show.h"
#include "ui/layers/generic_box.h"
#include "ui/widgets/labels.h"
#include "ui/widgets/buttons.h"
#include "ui/wrap/vertical_layout.h"
#include "ui/painter.h"
#include "styles/style_boxes.h"
#include "styles/style_layers.h"
#include "window/window_session_controller.h"

namespace Extera::Security {
namespace {

void SetupConfirmActionBox(
		not_null<Ui::GenericBox*> box,
		const SensitiveAction &action,
		Fn<void(bool confirmed)> callback) {
	auto handled = std::make_shared<bool>(false);

	box->setWidth(st::boxWideWidth);

	const auto content = box->verticalLayout();

	const auto iconWidget = content->add(
		object_ptr<Ui::RpWidget>(content),
		style::margins(0, st::boxRowPadding.top(), 0, st::boxRowPadding.bottom() / 2));
	iconWidget->resize(st::boxWideWidth, 54);
	iconWidget->paintRequest() | rpl::on_next([=] {
		auto p = QPainter(iconWidget);
		auto hq = PainterHighQualityEnabler(p);
		const auto cx = iconWidget->width() / 2;
		const auto cy = 27;
		p.setPen(Qt::NoPen);
		p.setBrush(st::windowBgActive);
		p.drawEllipse(cx - 24, cy - 24, 48, 48);
		p.setPen(st::white);
		auto font = p.font();
		font.setBold(true);
		font.setPixelSize(22);
		p.setFont(font);
		p.drawText(QRect(cx - 24, cy - 24, 48, 48), Qt::AlignCenter, u"!"_q);
	}, iconWidget->lifetime());

	content->add(
		object_ptr<Ui::FlatLabel>(
			content,
			u"Confirm action"_q,
			st::boxTitle),
		style::margins(st::boxRowPadding.left(), 0, st::boxRowPadding.right(), 2));

	content->add(
		object_ptr<Ui::FlatLabel>(
			content,
			action.category.isEmpty() ? u"Payments"_q : action.category,
			st::boxLabel),
		style::margins(st::boxRowPadding.left(), 0, st::boxRowPadding.right(), st::boxRowPadding.bottom()));

	const auto card = content->add(
		object_ptr<Ui::VerticalLayout>(content),
		style::margins(st::boxRowPadding.left(), 0, st::boxRowPadding.right(), st::boxRowPadding.bottom()));
	card->paintRequest() | rpl::on_next([=] {
		auto p = QPainter(card);
		auto hq = PainterHighQualityEnabler(p);
		p.setPen(Qt::NoPen);
		p.setBrush(st::windowBgOver);
		p.drawRoundedRect(card->rect(), 12., 12.);
	}, card->lifetime());

	const auto addCardRow = [=](const QString &key, const QString &val) {
		if (val.isEmpty()) {
			return;
		}
		const auto row = card->add(
			object_ptr<Ui::RpWidget>(card),
			style::margins(16, 8, 16, 8));
		row->resize(st::boxWideWidth - st::boxRowPadding.left() * 2 - 32, 22);
		row->paintRequest() | rpl::on_next([=] {
			auto p = QPainter(row);
			p.setFont(st::boxLabel.style.font);
			p.setPen(st::windowSubTextFg);
			p.drawText(QRect(0, 0, row->width() / 2, row->height()), Qt::AlignLeft | Qt::AlignVCenter, key);
			p.setPen(st::windowBoldFg);
			p.drawText(QRect(row->width() / 2, 0, row->width() / 2, row->height()), Qt::AlignRight | Qt::AlignVCenter, val);
		}, row->lifetime());
	};

	if (!action.account.isEmpty()) {
		addCardRow(u"Account"_q, action.account);
	}
	if (action.amount > 0) {
		addCardRow(u"To be deducted"_q, QString::fromUtf8("★ ") + QString::number(action.amount));
	} else if (!action.details.isEmpty()) {
		addCardRow(u"To be deducted"_q, action.details);
	}
	if (!action.recipient.isEmpty()) {
		addCardRow(u"Recipient"_q, action.recipient);
	}
	if (!action.giftId.isEmpty()) {
		addCardRow(u"Gift"_q, u"ID "_q + action.giftId);
	}
	addCardRow(u"Hide sender name"_q, action.hideSenderName ? u"Yes"_q : u"No"_q);
	addCardRow(u"Prepay gift upgrade"_q, action.prepayUpgrade ? u"Yes"_q : u"No"_q);
	if (!action.requestMethod.isEmpty()) {
		addCardRow(u"Request"_q, action.requestMethod);
	}

	content->add(
		object_ptr<Ui::FlatLabel>(
			content,
			u"If you didn't start this yourself, tap Decline: it may have been started by a plugin."_q,
			st::boxLabel),
		style::margins(st::boxRowPadding.left(), 4, st::boxRowPadding.right(), st::boxRowPadding.bottom()));

	box->addButton(tr::lng_box_ok(), [=] {
		if (!*handled) {
			*handled = true;
			box->closeBox();
			callback(true);
		}
	});

	box->addButton(tr::lng_cancel(), [=] {
		if (!*handled) {
			*handled = true;
			box->closeBox();
			callback(false);
		}
	});

	box->boxClosing(
	) | rpl::on_next([=] {
		if (!*handled) {
			*handled = true;
			callback(false);
		}
	}, box->lifetime());
}

} // namespace

void ConfirmAction(
		not_null<Window::SessionController*> controller,
		const SensitiveAction &action,
		Fn<void(bool confirmed)> callback) {
	controller->show(Box([=](not_null<Ui::GenericBox*> box) {
		SetupConfirmActionBox(box, action, callback);
	}));
}

void ConfirmAction(
		std::shared_ptr<Main::SessionShow> show,
		const SensitiveAction &action,
		Fn<void(bool confirmed)> callback) {
	show->show(Box([=](not_null<Ui::GenericBox*> box) {
		SetupConfirmActionBox(box, action, callback);
	}));
}

} // namespace Extera::Security
