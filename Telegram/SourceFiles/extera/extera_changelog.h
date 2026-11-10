#pragma once

namespace Window {
class SessionController;
} // namespace Window

namespace Extera::Changelog {

void Start();
void Show(not_null<Window::SessionController*> controller);
void ShowUpdate(
	not_null<Window::SessionController*> controller,
	const QString &version,
	const QString &body);

} // namespace Extera::Changelog
