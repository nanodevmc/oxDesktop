#pragma once

#include <QtCore/QString>

namespace Window {
class SessionController;
} // namespace Window

namespace Main {
class SessionShow;
} // namespace Main

namespace Extera::Security {

enum class ActionType {
	SendStars,
	BuyGift,
	TransferGift,
	EditAdminRights,
};

struct SensitiveAction {
	ActionType type = ActionType::SendStars;
	QString category = u"Payments"_q;
	QString title;
	QString account;
	QString recipient;
	QString giftId;
	QString requestMethod = u"payments.sendStarsForm"_q;
	QString details;
	int64 amount = 0;
	bool hideSenderName = false;
	bool prepayUpgrade = false;
};

void ConfirmAction(
	not_null<Window::SessionController*> controller,
	const SensitiveAction &action,
	Fn<void(bool confirmed)> callback);

void ConfirmAction(
	std::shared_ptr<Main::SessionShow> show,
	const SensitiveAction &action,
	Fn<void(bool confirmed)> callback);

} // namespace Extera::Security
