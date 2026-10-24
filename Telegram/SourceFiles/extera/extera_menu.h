#pragma once

class HistoryItem;

namespace Ui {
class PopupMenu;
} // namespace Ui

namespace Window {
class SessionController;
} // namespace Window

namespace Extera {

void AddMessageMenuActions(
	not_null<Ui::PopupMenu*> menu,
	not_null<HistoryItem*> item,
	not_null<Window::SessionController*> controller);

} // namespace Extera
