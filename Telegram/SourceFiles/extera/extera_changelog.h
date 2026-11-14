#pragma once

namespace Window {
class SessionController;
} // namespace Window

namespace Ui {
class VerticalLayout;
} // namespace Ui

namespace Extera::Changelog {

void Start();
void Show(not_null<Window::SessionController*> controller);
void ShowUpdate(
	not_null<Window::SessionController*> controller,
	const QString &version,
	const QString &body);

void FillLatestFromChangelog(not_null<Ui::VerticalLayout*> container);

} // namespace Extera::Changelog
