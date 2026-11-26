#pragma once

#include "base/basic_types.h"

#include <QtCore/QString>
#include <QtGui/QImage>

namespace Window {
class SessionController;
} // namespace Window

namespace Extera::Ocr {

void ExtractAndShowBox(
	not_null<Window::SessionController*> controller,
	const QImage &image);
void ExtractText(
	const QImage &image,
	Fn<void(QString text, QString error)> done);

} // namespace Extera::Ocr
