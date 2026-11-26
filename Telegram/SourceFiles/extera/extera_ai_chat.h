#pragma once

#include "base/basic_types.h"

#include <QtCore/QByteArray>
#include <QtCore/QString>

namespace Window {
class SessionController;
} // namespace Window

namespace Extera {

void ShowAiChat(not_null<Window::SessionController*> controller);
void ShowKeyBox(not_null<Window::SessionController*> controller);
void TestAiConnection(not_null<Window::SessionController*> controller);
void SendPrompt(
	const QString &prompt,
	const QByteArray &pngBytes,
	Fn<void(QString text, QString error)> done);

} // namespace Extera
