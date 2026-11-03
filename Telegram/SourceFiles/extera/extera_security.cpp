#include "extera/extera_security.h"

#include "ui/layers/generic_box.h"
#include "ui/widgets/labels.h"
#include "ui/text/text_utilities.h"
#include "styles/style_boxes.h"
#include "styles/style_layers.h"
#include "window/window_session_controller.h"

namespace Extera::Security {

void ConfirmAction(
		not_null<Window::SessionController*> controller,
		const SensitiveAction &action,
		Fn<void(bool confirmed)> callback) {
	auto handled = std::make_shared<bool>(false);

	controller->show(Box([=](not_null<Ui::GenericBox*> box) {
		box->setTitle(rpl::single(
			!action.title.isEmpty()
				? action.title
				: u"Confirm Sensitive Action"_q));

		auto text = QString();
		if (!action.details.isEmpty()) {
			text.append(action.details + u"\n\n"_q);
		}
		if (action.amount > 0) {
			text.append(QString("Amount: %1\n").arg(action.amount));
		}
		if (!action.recipient.isEmpty()) {
			text.append(QString("Recipient: %1\n").arg(action.recipient));
		}
		text.append(u"\nAllow this operation to proceed?"_q);

		box->addRow(object_ptr<Ui::FlatLabel>(
			box,
			text.trimmed(),
			st::boxLabel));

		box->addButton(rpl::single(u"Allow"_q), [=] {
			if (!*handled) {
				*handled = true;
				box->closeBox();
				callback(true);
			}
		});

		box->addCancelButton([=] {
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
	}));
}

} // namespace Extera::Security
