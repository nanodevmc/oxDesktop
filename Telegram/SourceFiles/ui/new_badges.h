/*
This file is part of Telegram Desktop,
the official desktop application for the Telegram messaging service.

For license and copyright information please follow this link:
https://github.com/telegramdesktop/tdesktop/blob/master/LEGAL
*/
#pragma once

#include "ui/text/custom_emoji_helper.h"

namespace style {
struct SettingsButton;
} // namespace style

namespace Ui {

class RpWidget;

[[nodiscard]] Text::PaletteDependentEmoji AttentionMarkEmoji();

} // namespace Ui

namespace Ui::NewBadge {

enum class Tag {
	None,
	Beta,
	New,
};

[[nodiscard]] Tag FeatureTag(const QString &featureId);

[[nodiscard]] not_null<Ui::RpWidget*> CreateNewBadge(
	not_null<Ui::RpWidget*> parent,
	rpl::producer<QString> text);

[[nodiscard]] not_null<Ui::RpWidget*> CreateTagBadge(
	not_null<Ui::RpWidget*> parent,
	Tag tag);

[[nodiscard]] not_null<Ui::RpWidget*> CreateLiquidBetaBadge(
	not_null<Ui::RpWidget*> parent,
	rpl::producer<QString> text = nullptr);

[[nodiscard]] not_null<Ui::RpWidget*> CreateLiquidPillBadge(
	not_null<Ui::RpWidget*> parent,
	rpl::producer<QString> text,
	QColor bgTint = QColor(0, 160, 255, 32),
	QColor borderTint = QColor(0, 210, 255, 90),
	QColor textTint = QColor(56, 189, 248),
	float radius = 3.5f);

void AddToRight(not_null<Ui::RpWidget*> parent);
void AddAfterLabel(
	not_null<Ui::RpWidget*> parent,
	not_null<Ui::RpWidget*> label);
void AddAfterButtonText(
	not_null<Ui::RpWidget*> button,
	rpl::producer<QString> text,
	const style::SettingsButton &st);
void AddTagBadgeAfterButtonText(
	not_null<Ui::RpWidget*> button,
	Tag tag,
	rpl::producer<QString> text,
	const style::SettingsButton &st);

} // namespace Ui::NewBadge
