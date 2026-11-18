#include "extera/extera_shot.h"

#include "history/history_item.h"
#include "history/view/history_view_element.h"
#include "window/window_session_controller.h"
#include "ui/chat/chat_style.h"
#include "ui/chat/chat_theme.h"
#include "ui/painter.h"
#include "styles/style_basic.h"

#include <QtGui/QClipboard>
#include <QtGui/QGuiApplication>
#include <QtGui/QPainter>
#include <QtGui/QPainterPath>
#include <QtGui/QLinearGradient>
#include <cmath>
#include <algorithm>

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
	const auto viewW = std::max(view->width(), 120);
	const auto viewH = std::max(view->height(), 32);
	if (viewW <= 0 || viewH <= 0) {
		controller->showToast(u"Не удалось создать снимок сообщения"_q);
		return;
	}

	auto fullImage = QImage(
		viewW * ratio,
		viewH * ratio,
		QImage::Format_ARGB32_Premultiplied);
	fullImage.setDevicePixelRatio(ratio);
	fullImage.fill(Qt::transparent);

	{
		Painter p(&fullImage);
		auto context = controller->preparePaintContext({
			.theme = controller->currentChatTheme(),
			.clip = QRect(0, 0, viewW, viewH),
			.visibleAreaPositionGlobal = QPoint(0, 0),
			.visibleAreaTop = 0,
			.visibleAreaWidth = viewW,
			.visibleAreaHeight = viewH,
		});
		context.outbg = view->hasOutLayout();
		view->draw(p, context);
	}

	const auto imgW = fullImage.width();
	const auto imgH = fullImage.height();
	int minX = imgW;
	int maxX = -1;
	int minY = imgH;
	int maxY = -1;

	for (int y = 0; y < imgH; ++y) {
		const auto *line = reinterpret_cast<const uint32_t*>(fullImage.constScanLine(y));
		for (int x = 0; x < imgW; ++x) {
			if (line[x] & 0xFF000000) {
				if (x < minX) minX = x;
				if (x > maxX) maxX = x;
				if (y < minY) minY = y;
				if (y > maxY) maxY = y;
			}
		}
	}

	QImage contentImage;
	if (minX <= maxX && minY <= maxY) {
		const auto margin = int(std::round(4 * ratio));
		const auto cropLeft = std::max(0, minX - margin);
		const auto cropTop = std::max(0, minY - margin);
		const auto cropRight = std::min(imgW - 1, maxX + margin);
		const auto cropBottom = std::min(imgH - 1, maxY + margin);
		contentImage = fullImage.copy(
			cropLeft,
			cropTop,
			cropRight - cropLeft + 1,
			cropBottom - cropTop + 1);
		contentImage.setDevicePixelRatio(ratio);
	} else {
		contentImage = fullImage;
	}

	const auto contentW = int(std::ceil(contentImage.width() / ratio));
	const auto contentH = int(std::ceil(contentImage.height() / ratio));

	const auto padX = 26;
	const auto padY = 22;
	const auto bottomBarH = 20;
	const auto shotW = contentW + padX * 2;
	const auto shotH = contentH + padY * 2 + bottomBarH;

	auto finalImage = QImage(
		shotW * ratio,
		shotH * ratio,
		QImage::Format_ARGB32_Premultiplied);
	finalImage.setDevicePixelRatio(ratio);
	finalImage.fill(Qt::transparent);

	{
		Painter p(&finalImage);
		p.setRenderHint(QPainter::Antialiasing);
		p.setRenderHint(QPainter::SmoothPixmapTransform);
		p.setRenderHint(QPainter::TextAntialiasing);

		const auto cardRect = QRectF(0.5, 0.5, shotW - 1, shotH - 1);
		auto grad = QLinearGradient(0, 0, shotW, shotH);
		grad.setColorAt(0.0, QColor(24, 26, 31));
		grad.setColorAt(0.5, QColor(18, 19, 23));
		grad.setColorAt(1.0, QColor(12, 13, 16));
		p.setBrush(grad);
		p.setPen(QPen(QColor(255, 255, 255, 24), 1.0));
		p.drawRoundedRect(cardRect, 14.0, 14.0);

		p.drawImage(padX, padY, contentImage);

		p.setFont(st::semiboldFont);
		p.setPen(QColor(255, 255, 255, 80));
		p.drawText(
			QRect(0, shotH - padY - 2, shotW - padX, bottomBarH),
			Qt::AlignRight | Qt::AlignVCenter,
			u"oxDesktop"_q);
	}

	QGuiApplication::clipboard()->setImage(finalImage);
	controller->showToast(u"Снимок сообщения скопирован в буфер обмена"_q);
}

} // namespace Extera
