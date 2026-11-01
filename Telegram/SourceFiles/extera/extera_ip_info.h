#pragma once

#include <QtCore/QString>

namespace Window {
class SessionController;
} // namespace Window

namespace Extera::IpInfo {

[[nodiscard]] QString ExtractIp(const QString &text);
void Inspect(
	not_null<Window::SessionController*> controller,
	const QString &ipOrHost);

} // namespace Extera::IpInfo
