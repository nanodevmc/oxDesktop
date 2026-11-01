#pragma once

#include <QtCore/QString>

namespace Window {
class SessionController;
} // namespace Window

namespace Extera::Security {

enum class ActionType {
	SendStars,
	TransferGift,
	EditAdminRights,
};

struct SensitiveAction {
	ActionType type = ActionType::SendStars;
	QString title;
	QString details;
	QString recipient;
	int64 amount = 0;
};

void ConfirmAction(
	not_null<Window::SessionController*> controller,
	const SensitiveAction &action,
	Fn<void(bool confirmed)> callback);

} // namespace Extera::Security
