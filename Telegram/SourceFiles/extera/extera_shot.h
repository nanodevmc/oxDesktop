#pragma once

class HistoryItem;

namespace Window {
class SessionController;
} // namespace Window

namespace Extera {

void TakeMessageShot(
	Window::SessionController *controller,
	HistoryItem *item);

} // namespace Extera
