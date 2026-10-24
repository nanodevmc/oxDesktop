#pragma once

namespace Ui {
class VerticalLayout;
} // namespace Ui

namespace Extera::Navigation {

void ApplyMenuLayout(
	not_null<Ui::VerticalLayout*> menu,
	not_null<QWidget*> holder);
void FillSettings(not_null<Ui::VerticalLayout*> container);

} // namespace Extera::Navigation
