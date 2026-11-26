#pragma once

#include "base/basic_types.h"

#include <QtCore/QString>
#include <QtGui/QImage>

class QAction;

namespace Ui::Menu {
class Menu;
} // namespace Ui::Menu

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
void AttachNewBadge(not_null<Ui::Menu::Menu*> menu, QAction *action);

} // namespace Extera::Ocr
