/*
This file is part of Telegram Desktop,
the official desktop application for the Telegram messaging service.

For license and copyright information please follow this link:
https://github.com/telegramdesktop/tdesktop/blob/master/LEGAL
*/
#include "ui/chat/chat_style_radius.h"
#include "extera/extera_config.h"
#include "ui/chat/chat_style.h"
#include "base/options.h"

#include "ui/chat/chat_theme.h"
#include "ui/painter.h"
#include "ui/ui_utility.h"
#include "styles/style_chat.h"

namespace Ui {
namespace {

base::options::toggle UseSmallMsgBubbleRadius({
	.id = kOptionUseSmallMsgBubbleRadius,
	.name = "Use small message bubble radius",
	.description = "Makes most message bubbles square-ish.",
	.restartRequired = true,
});

} // namespace

const char kOptionUseSmallMsgBubbleRadius[] = "use-small-msg-bubble-radius";

int BubbleRadiusSmall() {
	if (Extera::Bool(u"material_design"_q) && !UseSmallMsgBubbleRadius.value()) {
		return std::max(st::bubbleRadiusSmall, style::ConvertScale(6));
	}
	return st::bubbleRadiusSmall;
}

int BubbleRadiusLarge() {
	if (UseSmallMsgBubbleRadius.value()) {
		return st::bubbleRadiusSmall;
	}
	if (Extera::Bool(u"material_design"_q)) {
		return std::max(st::bubbleRadiusLarge, style::ConvertScale(18));
	}
	return st::bubbleRadiusLarge;
}

int BubbleCornerRadius(BubbleCornerRounding corner) {
	switch (corner) {
	case BubbleCornerRounding::None:
	case BubbleCornerRounding::Tail: return 0;
	case BubbleCornerRounding::Small: return BubbleRadiusSmall();
	case BubbleCornerRounding::Large: return BubbleRadiusLarge();
	}
	Unexpected("Corner in BubbleCornerRadius.");
}

int MsgFileThumbRadiusSmall() {
	return st::msgFileThumbRadiusSmall;
}

int MsgFileThumbRadiusLarge() {
	if (UseSmallMsgBubbleRadius.value()) {
		return st::msgFileThumbRadiusSmall;
	}
	if (Extera::Bool(u"material_design"_q)) {
		return std::max(st::msgFileThumbRadiusLarge, style::ConvertScale(14));
	}
	return st::msgFileThumbRadiusLarge;
}

}
