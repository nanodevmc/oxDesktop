/*
This file is part of Telegram Desktop,
the official desktop application for the Telegram messaging service.

For license and copyright information please follow this link:
https://github.com/telegramdesktop/tdesktop/blob/master/LEGAL
*/
#include "ui/new_badges.h"

#include "lang/lang_keys.h"
#include "ui/painter.h"
#include "ui/widgets/labels.h"
#include "styles/style_info.h"
#include "styles/style_window.h"
#include "styles/style_settings.h"

namespace Ui {

Text::PaletteDependentEmoji AttentionMarkEmoji() {
	return {
		.factory = [] {
			const auto s = st::infoSecurityRiskIconSize;
			const auto ratio = style::DevicePixelRatio();
			const auto rect = QRect(0, 0, s, s);
			auto result = QImage(
				rect.size() * ratio,
				QImage::Format_ARGB32_Premultiplied);
			result.setDevicePixelRatio(ratio);
			result.fill(Qt::transparent);

			auto p = QPainter(&result);
			auto hq = PainterHighQualityEnabler(p);
			p.setPen(Qt::NoPen);
			p.setBrush(st::attentionButtonFg);
			p.drawEllipse(rect);

			p.setPen(st::windowFgActive);
			p.setFont(st::semiboldFont);
			p.drawText(rect, u"!"_q, style::al_center);

			p.end();
			return result;
		},
		.margin = st::infoSecurityRiskIconMargin,
	};
}

} // namespace Ui

namespace Ui::NewBadge {

not_null<Ui::RpWidget*> CreateNewBadge(
		not_null<Ui::RpWidget*> parent,
		rpl::producer<QString> text) {
	const auto badge = Ui::CreateChild<Ui::PaddingWrap<Ui::FlatLabel>>(
		parent.get(),
		object_ptr<Ui::FlatLabel>(
			parent,
			std::move(text),
			st::settingsPremiumNewBadge),
		st::settingsPremiumNewBadgePadding);
	badge->show();
	badge->setAttribute(Qt::WA_TransparentForMouseEvents);
	badge->paintRequest() | rpl::on_next([=] {
		auto p = QPainter(badge);
		auto hq = PainterHighQualityEnabler(p);
		p.setPen(Qt::NoPen);
		p.setBrush(st::windowBgActive);
		const auto r = st::settingsPremiumNewBadgePadding.left();
		p.drawRoundedRect(badge->rect(), r, r);
	}, badge->lifetime());
	return badge;
}

Tag FeatureTag(const QString &featureId) {
	// Centralized feature badge lifecycle registry.
	// NEW badges are removed on new versions (when requested by user).
	// BETA badges are removed when checks and stability are confirmed.
	if (featureId == u"polls_in_pm"_q) {
		return Tag::Beta;
	} else if (featureId == u"lyrics_quote_card"_q) {
		return Tag::Beta;
	} else if (featureId == u"gapless_playback"_q) {
		return Tag::Beta;
	} else if (featureId == u"media_deduplication"_q) {
		return Tag::Beta;
	} else if (featureId == u"queue_reply"_q) {
		return Tag::New;
	} else if (featureId == u"pinned_messages_viewer"_q) {
		return Tag::New;
	} else if (featureId == u"mini_player_always_on_top"_q) {
		return Tag::New;
	}
	return Tag::None;
}

not_null<Ui::RpWidget*> CreateLiquidPillBadge(
		not_null<Ui::RpWidget*> parent,
	rpl::producer<QString> text,
	QColor bgTint,
	QColor borderTint,
	QColor textTint,
	float radius) {
	const auto label = Ui::CreateChild<Ui::FlatLabel>(
		parent.get(),
		std::move(text),
		st::settingsPremiumNewBadge);
	label->setTextColorOverride(textTint);

	const auto badge = Ui::CreateChild<Ui::PaddingWrap<Ui::FlatLabel>>(
		parent.get(),
		object_ptr<Ui::FlatLabel>::fromRaw(label),
		st::settingsPremiumNewBadgePadding);
	badge->show();
	badge->setAttribute(Qt::WA_TransparentForMouseEvents);
	badge->paintRequest() | rpl::on_next([=] {
		auto p = QPainter(badge);
		auto hq = PainterHighQualityEnabler(p);
		const auto rect = QRectF(badge->rect()).adjusted(0.5, 0.5, -0.5, -0.5);

		QLinearGradient grad(rect.topLeft(), rect.bottomLeft());
		grad.setColorAt(0.0, bgTint);
		grad.setColorAt(1.0, QColor(bgTint.red(), bgTint.green(), bgTint.blue(), bgTint.alpha() / 2));
		p.setPen(QPen(borderTint, 1.0));
		p.setBrush(grad);
		p.drawRoundedRect(rect, radius, radius);
	}, badge->lifetime());
	return badge;
}

not_null<Ui::RpWidget*> CreateTagBadge(
		not_null<Ui::RpWidget*> parent,
		Tag tag) {
	if (tag == Tag::Beta) {
		return CreateLiquidBetaBadge(parent);
	}
	return CreateLiquidPillBadge(
		parent,
		rpl::single(u"NEW"_q),
		QColor(0, 160, 255, 34),
		QColor(0, 210, 255, 95),
		QColor(56, 189, 248),
		3.5f);
}

not_null<Ui::RpWidget*> CreateLiquidBetaBadge(
		not_null<Ui::RpWidget*> parent,
	rpl::producer<QString> text) {
	return CreateLiquidPillBadge(
		parent,
		text ? std::move(text) : rpl::single(u"BETA"_q),
		QColor(0, 160, 255, 30),
		QColor(0, 210, 255, 90),
		QColor(56, 189, 248),
		3.5f);
}

void AddToRight(not_null<Ui::RpWidget*> parent) {
	const auto badge = CreateNewBadge(parent, tr::lng_bot_side_menu_new());

	parent->sizeValue(
	) | rpl::on_next([=](QSize size) {
		badge->moveToRight(
			st::mainMenuButton.padding.right(),
			(size.height() - badge->height()) / 2,
			size.width());
	}, badge->lifetime());
}

void AddAfterLabel(
		not_null<Ui::RpWidget*> parent,
		not_null<Ui::RpWidget*> label) {
	const auto badge = CreateNewBadge(
		parent,
		tr::lng_premium_summary_new_badge());

	label->geometryValue(
	) | rpl::on_next([=](QRect geometry) {
		badge->move(st::settingsPremiumNewBadgePosition
			+ QPoint(label->x() + label->width(), label->y()));
	}, badge->lifetime());
}

void AddAfterButtonText(
		not_null<Ui::RpWidget*> button,
		rpl::producer<QString> text,
		const style::SettingsButton &st) {
	const auto badge = CreateNewBadge(
		button,
		tr::lng_premium_summary_new_badge());
	rpl::combine(
		std::move(text),
		button->widthValue()
	) | rpl::on_next([=, &st](const QString &text, int width) {
		const auto space = st.style.font->spacew;
		const auto left = st.padding.left()
			+ st.style.font->width(text)
			+ space;
		const auto available = width - left - st.padding.right();
		badge->setVisible(available >= badge->width());
		if (!badge->isHidden()) {
			const auto top = st.padding.top()
				+ st.style.font->ascent
				- st::settingsPremiumNewBadge.style.font->ascent
				- st::settingsPremiumNewBadgePadding.top();
			badge->moveToLeft(left, top, width);
		}
	}, badge->lifetime());
}

void AddTagBadgeAfterButtonText(
		not_null<Ui::RpWidget*> button,
		Tag tag,
		rpl::producer<QString> text,
		const style::SettingsButton &st) {
	if (tag == Tag::None) {
		return;
	}
	const auto badge = CreateTagBadge(button, tag);
	rpl::combine(
		std::move(text),
		button->widthValue()
	) | rpl::on_next([=, &st](const QString &text, int width) {
		const auto space = st.style.font->spacew;
		const auto left = st.padding.left()
			+ st.style.font->width(text)
			+ space;
		const auto available = width - left - st.padding.right();
		badge->setVisible(available >= badge->width());
		if (!badge->isHidden()) {
			const auto top = st.padding.top()
				+ st.style.font->ascent
				- st::settingsPremiumNewBadge.style.font->ascent
				- st::settingsPremiumNewBadgePadding.top();
			badge->moveToLeft(left, top, width);
		}
	}, badge->lifetime());
}

} // namespace Ui::NewBadge
