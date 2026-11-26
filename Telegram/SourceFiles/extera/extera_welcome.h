#pragma once

namespace Ui {
class VerticalLayout;
} // namespace Ui

namespace Window {
class SessionController;
} // namespace Window

namespace Extera {

void FillUnofficialInfo(not_null<Ui::VerticalLayout*> container);
void ShowWelcomeBox(not_null<Window::SessionController*> controller);
void ShowExtera5YearsBox(not_null<Window::SessionController*> controller);
void CheckSponsorChannel(not_null<Window::SessionController*> controller);
void StartWelcome();

} // namespace Extera
