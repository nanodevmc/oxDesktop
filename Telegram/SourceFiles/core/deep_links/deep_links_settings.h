/*
This file is part of Telegram Desktop,
the official desktop application for the Telegram messaging service.

For license and copyright information please follow this link:
https://github.com/telegramdesktop/tdesktop/blob/master/LEGAL
*/
#pragma once

#include "settings/settings_type.h"

namespace Main {
class Session;
} // namespace Main

namespace Core::DeepLinks {

class Router;

void RegisterSettingsHandlers(Router &router);

[[nodiscard]] QString SettingsDeepLink(
	::Settings::Type section,
	const QString &controlId);

[[nodiscard]] ::Settings::Type ResolveSectionForHighlight(
	not_null<::Main::Session*> session,
	const QString &highlight,
	::Settings::Type fallback);

} // namespace Core::DeepLinks
