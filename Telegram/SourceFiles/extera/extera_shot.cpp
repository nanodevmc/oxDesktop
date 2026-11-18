#include "extera/extera_shot.h"

#include "history/history_item.h"
#include "history/view/history_view_element.h"
#include "window/window_session_controller.h"
#include "styles/style_basic.h"

#include <QtGui/QClipboard>
#include <QtGui/QGuiApplication>
#include <QtGui/QPainter>
#include <QtGui/QPainterPath>
#include <QtGui/QLinearGradient>
#include <QtWidgets/QWidget>

namespace Extera {

void TakeMessageShot(
		Window::SessionController *controller,
		HistoryItem *item) {
	if (!controller || !item) {
		return;
	}
	const auto view = item->mainView();
	if (!view) {
		controller->showToast(u"Не удалось создать снимок сообщения"_q);
		return;
	}

	const auto ratio = style::DevicePixelRatio();
	const auto geom = view->innerGeometry();
	const auto viewW = std::max(view->width(), geom.width());
	const auto viewH = std::max(view->height(), geom.height());
	if (viewW <= 0 || viewH <= 0) {
		controller->showToast(u"Не удалось создать снимок сообщения"_q);
		return;
	}

	auto elementPixmap = QPixmap(viewW * ratio, viewH * ratio);
	elementPixmap.setDevicePixelRatio(ratio);
	elementPixmap.fill(Qt::transparent);

	{
		auto p = QPainter(&elementPixmap);
		p.setRenderHint(QPainter::Antialiasing);
		p.setRenderHint(QPainter::SmoothPixmapTransform);
		p.setRenderHint(QPainter::TextAntialiasing);

		if (const auto widget = controller->widget()) {
			widget->render(&p, QPoint(0, 0), QRect(geom.x(), view->y(), viewW, viewH));
		}
	}

	const auto padX = 28;
	const auto padY = 24;
	const auto bottomBarH = 22;
	const auto shotW = viewW + padX * 2;
	const auto shotH = viewH + padY * 2 + bottomBarH;

	auto finalImage = QImage(shotW * ratio, shotH * ratio, QImage::Format_ARGB32_Premultiplied);
	finalImage.setDevicePixelRatio(ratio);
	finalImage.fill(Qt::transparent);

	{
		auto p = QPainter(&finalImage);
		p.setRenderHint(QPainter::Antialiasing);
		p.setRenderHint(QPainter::SmoothPixmapTransform);
		p.setRenderHint(QPainter::TextAntialiasing);

		const auto cardRect = QRectF(0.5, 0.5, shotW - 1, shotH - 1);
		auto grad = QLinearGradient(0, 0, shotW, shotH);
		grad.setColorAt(0.0, QColor(26, 28, 33));
		grad.setColorAt(0.5, QColor(20, 21, 26));
		grad.setColorAt(1.0, QColor(13, 14, 18));
		p.setBrush(grad);
		p.setPen(QPen(QColor(255, 255, 255, 22), 1.0));
		p.drawRoundedRect(cardRect, 14.0, 14.0);

		p.drawPixmap(padX, padY, elementPixmap);

		p.setFont(st::semiboldFont);
		p.setPen(QColor(255, 255, 255, 75));
		p.drawText(QRect(0, shotH - padY - 2, shotW - padX, bottomBarH), Qt::AlignRight | Qt::AlignVCenter, u"oxDesktop"_q);
	}

	QGuiApplication::clipboard()->setImage(finalImage);
	controller->showToast(u"Снимок сообщения скопирован в буфер обмена"_q);
}

} // namespace Extera
