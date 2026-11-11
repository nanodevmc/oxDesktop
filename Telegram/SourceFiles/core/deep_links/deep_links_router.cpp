/*
This file is part of Telegram Desktop,
the official desktop application for the Telegram messaging service.

For license and copyright information please follow this link:
https://github.com/telegramdesktop/tdesktop/blob/master/LEGAL
*/
#include "core/deep_links/deep_links_router.h"

#include "base/qthelp_url.h"
#include "core/deep_links/deep_links_chats.h"
#include "core/deep_links/deep_links_contacts.h"
#include "core/deep_links/deep_links_new.h"
#include "core/deep_links/deep_links_settings.h"
#include "core/application.h"
#include "main/main_session.h"
#include "ui/toast/toast.h"
#include "window/window_controller.h"
#include "window/window_session_controller.h"

namespace Core::DeepLinks {
namespace {

Context ParseCommand(
		Window::SessionController *controller,
		const QString &command) {
	auto result = Context{ .controller = controller };

	auto path = command.trimmed();
	const auto queryStart = path.indexOf('?');
	if (queryStart >= 0) {
		const auto query = path.mid(queryStart + 1);
		path = path.left(queryStart).trimmed();

		const auto unwrapParens = [](QString str) {
			str = str.trimmed();
			if (str.startsWith('(') && str.endsWith(')') && str.size() >= 2) {
				str = str.mid(1, str.size() - 2).trimmed();
			}
			return str;
		};

		for (const auto &pair : query.split('&')) {
			const auto eq = pair.indexOf('=');
			if (eq == 0) {
				const auto val = unwrapParens(qthelp::url_decode(pair.mid(1)));
				if (!val.isEmpty()) {
					result.params[u"highlight"_q] = val;
				}
			} else if (eq > 0) {
				const auto key = pair.left(eq).toLower();
				const auto val = unwrapParens(qthelp::url_decode(pair.mid(eq + 1)));
				result.params[key] = val;
				if (key == u"highlight"_q || key == u"param"_q || key == u"id"_q) {
					result.params[u"highlight"_q] = val;
				}
			} else if (!pair.isEmpty()) {
				const auto bare = unwrapParens(qthelp::url_decode(pair));
				result.params[pair.toLower()] = QString();
				if (!result.params.contains(u"highlight"_q) && !bare.isEmpty()) {
					result.params[u"highlight"_q] = bare;
				}
			}
		}
	}

	while (path.startsWith('/')) {
		path = path.mid(1);
	}
	while (path.endsWith('/')) {
		path.chop(1);
	}
	path = path.trimmed();
	if (path.startsWith('(') && path.endsWith(')') && path.size() >= 2) {
		path = path.mid(1, path.size() - 2).trimmed();
		while (path.startsWith('/')) {
			path = path.mid(1);
		}
		while (path.endsWith('/')) {
			path.chop(1);
		}
	}

	const auto slash = path.indexOf('/');
	if (slash > 0) {
		result.section = path.left(slash).toLower();
		result.path = path.mid(slash + 1);
	} else {
		result.section = path.toLower();
	}

	return result;
}

} // namespace

Router &Router::Instance() {
	static auto instance = Router();
	return instance;
}

Router::Router() {
	RegisterSettingsHandlers(*this);
	RegisterContactsHandlers(*this);
	RegisterChatsHandlers(*this);
	RegisterNewHandlers(*this);
}

void Router::add(const QString &section, Entry entry) {
	_handlers[section].push_back(std::move(entry));
}

std::optional<QString> Router::findPath(
		const QString &section,
		Fn<bool(const Action &)> matches) const {
	const auto i = _handlers.find(section);
	if (i != _handlers.end()) {
		for (const auto &entry : i->second) {
			if (matches(entry.action)) {
				return entry.path;
			}
		}
	}
	return std::nullopt;
}

bool Router::tryHandle(
		Window::SessionController *controller,
		const QString &command) {
	const auto ctx = ParseCommand(controller, command);
	const auto [result, skipActivation] = dispatch(ctx);

	switch (result) {
	case Result::Handled:
		if (controller && !skipActivation) {
			controller->window().activate();
		}
		return true;
	case Result::NeedsAuth:
		return false;
	case Result::Unsupported:
		showUnsupportedMessage(controller, command);
		return true;
	case Result::NotFound:
		return false;
	}
	return false;
}

Router::DispatchResult Router::dispatch(const Context &ctx) {
	if (ctx.section.isEmpty()) {
		return { Result::NotFound };
	}
	return handleSection(ctx.section, ctx);
}

Router::DispatchResult Router::handleSection(
		const QString &section,
		const Context &ctx) {
	auto it = _handlers.find(section);
	if (it == _handlers.end()) {
		if (section != u"settings"_q) {
			const auto settingsIt = _handlers.find(u"settings"_q);
			if (settingsIt != _handlers.end()) {
				const auto candidate = ctx.path.isEmpty()
					? section
					: (section + '/' + ctx.path);
				for (const auto &entry : settingsIt->second) {
					if (entry.path == candidate || entry.path.startsWith(candidate + '/')) {
						auto aliasCtx = ctx;
						aliasCtx.section = u"settings"_q;
						aliasCtx.path = candidate;
						return handleSection(u"settings"_q, aliasCtx);
					}
				}
			}
		}
		return { Result::NotFound };
	}

	const auto &entries = it->second;
	const auto path = ctx.path.toLower();

	for (const auto &entry : entries) {
		if (entry.path == path || (entry.path.isEmpty() && path.isEmpty())) {
			if (entry.requiresAuth && !ctx.controller) {
				return { Result::NeedsAuth };
			}
			return {
				executeAction(entry.action, ctx),
				entry.skipActivation,
			};
		}
	}

	for (const auto &entry : entries) {
		if (!entry.path.isEmpty() && path.startsWith(entry.path + '/')) {
			if (entry.requiresAuth && !ctx.controller) {
				return { Result::NeedsAuth };
			}
			return {
				executeAction(entry.action, ctx),
				entry.skipActivation,
			};
		}
	}

	return { Result::Unsupported };
}

Result Router::executeAction(const Action &action, const Context &ctx) {
	return v::match(action, [&](const SettingsSection &s) {
		if (!ctx.controller) {
			return Result::NeedsAuth;
		}
		const auto highlight = ctx.params.value(u"highlight"_q);
		if (!highlight.isEmpty()) {
			ctx.controller->setHighlightControlId(highlight);
		}
		const auto targetSection = ResolveSectionForHighlight(
			&ctx.controller->session(),
			highlight,
			s.sectionId);
		ctx.controller->showSettings(targetSection);
		return Result::Handled;
	}, [&](const SettingsControl &s) {
		if (!ctx.controller) {
			return Result::NeedsAuth;
		}
		if (!s.controlId.isEmpty()) {
			ctx.controller->setHighlightControlId(s.controlId);
		}
		ctx.controller->showSettings(s.sectionId);
		return Result::Handled;
	}, [&](const CodeBlock &c) {
		return c.handler(ctx);
	}, [&](const AliasTo &a) {
		auto aliasCtx = ctx;
		aliasCtx.section = a.section;
		aliasCtx.path = a.path;
		return handleSection(a.section, aliasCtx).result;
	});
}

void Router::showUnsupportedMessage(
		Window::SessionController *controller,
		const QString &url) {
	const auto text = u"This link is not supported on Desktop."_q;
	if (controller) {
		controller->showToast(text);
	} else if (const auto window = Core::App().activeWindow()) {
		window->showToast(text);
	}
}

} // namespace Core::DeepLinks
