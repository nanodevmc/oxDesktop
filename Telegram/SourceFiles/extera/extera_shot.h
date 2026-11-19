#pragma once

#include <vector>

class HistoryItem;

namespace Window {
class SessionController;
} // namespace Window

namespace Extera {

void TakeMessageShot(
	Window::SessionController *controller,
	HistoryItem *item);

void TakeMessagesShot(
	Window::SessionController *controller,
	const std::vector<not_null<HistoryItem*>> &items);

void TakeMessagesShot(
	Window::SessionController *controller,
	const std::vector<HistoryItem*> &items);

} // namespace Extera
