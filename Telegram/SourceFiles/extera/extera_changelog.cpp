#include "extera/extera_changelog.h"

#include "version_generated.h"

#include "base/call_delayed.h"
#include "boxes/translate_box.h"
#include "core/application.h"
#include "core/version.h"
#include "data/data_user.h"
#include "extera/extera_config.h"
#include "extera/extera_update.h"
#include "lang/lang_instance.h"
#include "lang/lang_keys.h"
#include "main/main_domain.h"
#include "main/main_session.h"
#include "settings.h"
#include "ui/layers/generic_box.h"
#include "ui/text/text_utilities.h"
#include "ui/vertical_list.h"
#include "ui/widgets/buttons.h"
#include "ui/widgets/labels.h"
#include "ui/wrap/slide_wrap.h"
#include "ui/wrap/vertical_layout.h"
#include "window/main_window.h"
#include "window/window_controller.h"
#include "window/window_session_controller.h"
#include "styles/style_boxes.h"
#include "styles/style_layers.h"
#include "styles/style_settings.h"

#include <rpl/variable.h>

#include <QtCore/QCoreApplication>
#include <QtCore/QFile>
#include <QtCore/QFileInfo>
#include <QtCore/QJsonArray>
#include <QtCore/QJsonDocument>
#include <QtCore/QJsonObject>
#include <QtNetwork/QNetworkAccessManager>
#include <QtNetwork/QNetworkReply>
#include <QtNetwork/QNetworkRequest>

namespace Extera::Changelog {
namespace {

constexpr auto kMaxReleases = 20;
constexpr auto kShowDelay = 2500;

struct SubBlock {
	QString category;
	QString header;
	std::vector<QString> items;
};

struct LanguageBlock {
	QString lang;
	QString title;
	std::vector<SubBlock> subblocks;
	std::vector<QString> miscItems;
};

struct StructuredRelease {
	QString version;
	QDate date;
	QString rawBody;
	std::vector<LanguageBlock> languages;
};

struct State {
	QNetworkAccessManager *manager = nullptr;
	std::vector<StructuredRelease> releases;
	std::vector<Fn<void()>> waiting;
	bool loading = false;
	bool failed = false;
	rpl::lifetime lifetime;
};

State &Instance() {
	static auto result = State();
	return result;
}

[[nodiscard]] QString CachePath() {
	return cWorkingDir() + u"tdata/ox_releases.json"_q;
}

[[nodiscard]] QString LegacyCachePath() {
	return cWorkingDir() + u"tdata/exd_releases.json"_q;
}

[[nodiscard]] int CurrentKey() {
	return AppVersion * 100 + Extera::Update::Build();
}

[[nodiscard]] TextWithEntities FormatItem(const QString &item) {
	auto result = TextWithEntities();
	result.append(QString::fromUtf8("\xE2\x80\xA2 "));

	auto index = 0;
	while (index < item.size()) {
		const auto linkStart = item.indexOf('[', index);
		if (linkStart < 0) {
			result.append(item.mid(index));
			break;
		}
		if (linkStart > index) {
			result.append(item.mid(index, linkStart - index));
		}
		const auto labelEnd = item.indexOf(u"]("_q, linkStart + 1);
		if (labelEnd < 0) {
			result.append(item.mid(linkStart));
			break;
		}
		const auto urlEnd = item.indexOf(')', labelEnd + 2);
		if (urlEnd < 0) {
			result.append(item.mid(linkStart));
			break;
		}
		const auto label = item.mid(linkStart + 1, labelEnd - linkStart - 1);
		const auto url = item.mid(labelEnd + 2, urlEnd - labelEnd - 2);
		result.append(Ui::Text::Link(label, url));
		index = urlEnd + 1;
	}
	return result;
}

[[nodiscard]] std::vector<StructuredRelease> ParseReleasesFromText(
		const QString &text) {
	auto result = std::vector<StructuredRelease>();
	auto normalized = text;
	normalized.remove('\r');
	const auto lines = normalized.split('\n');

	auto currentRelease = (StructuredRelease*)nullptr;
	auto currentLang = (LanguageBlock*)nullptr;
	auto currentSub = (SubBlock*)nullptr;

	auto ensureRelease = [&](const QString &ver, const QString &dateStr) {
		result.push_back({
			.version = ver,
			.date = QDate::fromString(dateStr, u"dd.MM.yy"_q),
			.rawBody = QString(),
			.languages = {},
		});
		currentRelease = &result.back();
		currentLang = nullptr;
		currentSub = nullptr;
	};

	auto ensureLang = [&](const QString &code, const QString &title) {
		if (!currentRelease) {
			ensureRelease(QString::fromUtf8(AppVersionStr), QString());
		}
		for (auto &l : currentRelease->languages) {
			if (l.lang.compare(code, Qt::CaseInsensitive) == 0) {
				currentLang = &l;
				currentSub = nullptr;
				return;
			}
		}
		currentRelease->languages.push_back({
			.lang = code.toLower(),
			.title = title,
			.subblocks = {},
			.miscItems = {},
		});
		currentLang = &currentRelease->languages.back();
		currentSub = nullptr;
	};

	auto ensureSub = [&](const QString &category, const QString &header) {
		if (!currentLang) {
			const auto isRu = category == u"Added"_q
				? header.contains(QString::fromUtf8("\xD0\x94\xD0\xBE\xD0\xB1\xD0\xB0\xD0\xB2"))
				: (header.contains(QString::fromUtf8("\xD0\x98\xD1\x81\xD0\xBF\xD1\x80\xD0\xB0\xD0\xB2"))
					|| header.contains(QString::fromUtf8("\xD0\x9E\xD0\xB1\xD0\xBD\xD0\xBE\xD0\xB2")));
			ensureLang(
				isRu ? u"ru"_q : u"en"_q,
				isRu ? QString::fromUtf8("\xD0\xA0\xD1\x83\xD1\x81\xD1\x81\xD0\xBA\xD0\xB8\xD0\xB9") : u"English"_q);
		}
		for (auto &s : currentLang->subblocks) {
			if (s.category == category) {
				currentSub = &s;
				return;
			}
		}
		currentLang->subblocks.push_back({
			.category = category,
			.header = header,
			.items = {},
		});
		currentSub = &currentLang->subblocks.back();
	};

	for (auto line : lines) {
		line = line.trimmed();
		if (line.isEmpty()) {
			continue;
		}
		if (line.startsWith(u"<!--"_q) && !line.startsWith(u"<!-- ru"_q)) {
			continue;
		}
		if (line.startsWith(u"<!-- ru"_q)
			|| line.startsWith(u"# Что нового"_q, Qt::CaseInsensitive)
			|| line.compare(u"Ru:"_q, Qt::CaseInsensitive) == 0
			|| line.compare(u"Ru"_q, Qt::CaseInsensitive) == 0) {
			ensureLang(u"ru"_q, QString::fromUtf8("\xD0\xA0\xD1\x83\xD1\x81\xD1\x81\xD0\xBA\xD0\xB8\xD0\xB9"));
			continue;
		}
		if (line.compare(u"En:"_q, Qt::CaseInsensitive) == 0
			|| line.compare(u"En"_q, Qt::CaseInsensitive) == 0) {
			ensureLang(u"en"_q, u"English"_q);
			continue;
		}
		if (line.startsWith('#')) {
			auto rest = line.mid(line.indexOf(' ') + 1).trimmed();
			if (rest.startsWith(u"oxDesktop"_q, Qt::CaseInsensitive)) {
				rest = rest.mid(9).trimmed();
			}
			if (!rest.isEmpty() && rest[0].isDigit()) {
				ensureRelease(rest, QString());
				continue;
			}
		}
		if (line[0].isDigit()) {
			const auto paren = line.indexOf('(');
			auto ver = (paren > 0) ? line.left(paren).trimmed() : line;
			auto dateStr = QString();
			if (paren > 0) {
				const auto closeParen = line.indexOf(')', paren);
				if (closeParen > paren) {
					dateStr = line.mid(paren + 1, closeParen - paren - 1).trimmed();
				}
			}
			if (ver.contains('.')) {
				ensureRelease(ver, dateStr);
				continue;
			}
		}
		const auto clean = line.endsWith(':') ? line.left(line.size() - 1).trimmed() : line;
		if (clean.compare(u"Added"_q, Qt::CaseInsensitive) == 0
			|| clean.compare(QString::fromUtf8("\xD0\x94\xD0\xBE\xD0\xB1\xD0\xB0\xD0\xB2\xD0\xBB\xD0\xB5\xD0\xBD\xD0\xBE"), Qt::CaseInsensitive) == 0) {
			ensureSub(u"Added"_q, line);
			continue;
		}
		if (clean.compare(u"Fixes"_q, Qt::CaseInsensitive) == 0
			|| clean.compare(QString::fromUtf8("\xD0\x98\xD1\x81\xD0\xBF\xD1\x80\xD0\xB0\xD0\xB2\xD0\xBB\xD0\xB5\xD0\xBD\xD0\xBE"), Qt::CaseInsensitive) == 0
			|| clean.compare(QString::fromUtf8("\xD0\x98\xD1\x81\xD0\xBF\xD1\x80\xD0\xB0\xD0\xB2\xD0\xBB\xD0\xB5\xD0\xBD\xD0\xB8\xD1\x8F"), Qt::CaseInsensitive) == 0) {
			ensureSub(u"Fixes"_q, line);
			continue;
		}
		if (clean.compare(u"Updated"_q, Qt::CaseInsensitive) == 0
			|| clean.compare(QString::fromUtf8("\xD0\x9E\xD0\xB1\xD0\xBD\xD0\xBE\xD0\xB2\xD0\xBB\xD0\xB5\xD0\xBD\xD0\xBE"), Qt::CaseInsensitive) == 0) {
			ensureSub(u"Updated"_q, line);
			continue;
		}
		if (line.startsWith(u"- "_q) || line.startsWith(u"* "_q)) {
			const auto item = line.mid(2).trimmed();
			if (currentSub) {
				currentSub->items.push_back(item);
			} else if (currentLang) {
				currentLang->miscItems.push_back(item);
			}
			continue;
		}
	}
	return result;
}

void ApplyFallback() {
	auto &state = Instance();
	if (!state.releases.empty()) {
		return;
	}
	for (const auto &loc : {
		u":/gui/changelog.txt"_q,
		cWorkingDir() + u"changelog.txt"_q,
		QDir::currentPath() + u"/changelog.txt"_q,
		QCoreApplication::applicationDirPath() + u"/changelog.txt"_q,
		u"changelog.txt"_q,
	}) {
		auto file = QFile(loc);
		if (file.open(QIODevice::ReadOnly)) {
			const auto content = QString::fromUtf8(file.readAll());
			file.close();
			if (!content.isEmpty()) {
				state.releases = ParseReleasesFromText(content);
				if (!state.releases.empty()) {
					break;
				}
			}
		}
	}
}

bool Apply(const QByteArray &bytes) {
	const auto document = QJsonDocument::fromJson(bytes);
	if (!document.isArray()) {
		return false;
	}
	auto releases = std::vector<StructuredRelease>();
	for (const auto &entry : document.array()) {
		const auto object = entry.toObject();
		if (object.value(u"draft"_q).toBool()) {
			continue;
		}
		auto version = object.value(u"tag_name"_q).toString();
		if (version.startsWith('v')) {
			version = version.mid(1);
		}
		const auto body = object.value(u"body"_q).toString();
		const auto date = QDateTime::fromString(
			object.value(u"published_at"_q).toString(),
			Qt::ISODate).toLocalTime().date();

		auto parsed = ParseReleasesFromText(body);
		if (!parsed.empty()) {
			for (auto &rel : parsed) {
				if (rel.version.isEmpty()) {
					rel.version = version;
				}
				if (!rel.date.isValid()) {
					rel.date = date;
				}
				releases.push_back(std::move(rel));
			}
		} else {
			releases.push_back({
				.version = version,
				.date = date,
				.rawBody = body,
				.languages = {},
			});
		}
		if (int(releases.size()) >= kMaxReleases) {
			break;
		}
	}
	if (releases.empty()) {
		return false;
	}
	Instance().releases = std::move(releases);
	return true;
}

void Finish(bool ok) {
	auto &state = Instance();
	state.loading = false;
	if (state.releases.empty()) {
		ApplyFallback();
	}
	state.failed = !ok && state.releases.empty();
	for (const auto &callback : base::take(state.waiting)) {
		callback();
	}
}

void Load(Fn<void()> done) {
	auto &state = Instance();
	if (done) {
		state.waiting.push_back(std::move(done));
	}
	if (state.loading) {
		return;
	}
	state.loading = true;
	if (!state.manager) {
		state.manager = new QNetworkAccessManager(qApp);
	}
	auto request = QNetworkRequest(QUrl(
		u"https://api.github.com/repos/nanodevmc/oxDesktop/releases?per_page=%1"_q
			.arg(kMaxReleases)));
	request.setRawHeader("Accept", "application/vnd.github+json");
	request.setRawHeader("User-Agent", "oxDesktop/" APP_VERSION);
	const auto reply = state.manager->get(request);
	QObject::connect(reply, &QNetworkReply::finished, [=] {
		reply->deleteLater();
		if (reply->error() != QNetworkReply::NoError) {
			Finish(false);
		} else {
			const auto bytes = reply->readAll();
			const auto ok = Apply(bytes);
			if (ok) {
				auto file = QFile(CachePath());
				if (file.open(QIODevice::WriteOnly)) {
					file.write(bytes);
				}
			}
			Finish(ok);
		}
	});
}

void FillReleaseContent(
		not_null<Ui::VerticalLayout*> content,
		const StructuredRelease &release,
		bool isUpdate) {
	auto title = Ui::Text::Bold(u"oxDesktop "_q + release.version);
	if (release.date.isValid()) {
		title.append(QString::fromUtf8("  \xC2\xB7  ")).append(
			QLocale().toString(release.date, QLocale::LongFormat));
	}
	content->add(
		object_ptr<Ui::FlatLabel>(
			content,
			rpl::single(title),
			st::boxLabel),
		st::boxRowPadding);
	Ui::AddSkip(content, st::settingsCheckboxesSkip);

	if (release.languages.empty()) {
		return;
	}

	const auto hasMultipleLangs = (release.languages.size() > 1);
	const auto isClientRussian = Lang::Id().startsWith(u"ru"_q);

	for (const auto &lang : release.languages) {
		const auto isRussian = (lang.lang == u"ru"_q);
		const auto isDefaultLang = hasMultipleLangs
			? (isRussian == isClientRussian)
			: true;

		const auto langPrefix = isRussian
			? QString::fromUtf8("\xF0\x9F\x87\xB7\xF0\x9F\x87\xBA  ")
			: QString::fromUtf8("\xF0\x9F\x87\xAC\xF0\x9F\x87\xA7  ");
		const auto langTitle = langPrefix + lang.title;

		const auto langExpanded = content->lifetime().make_state<rpl::variable<bool>>(isDefaultLang);

		const auto langBtn = hasMultipleLangs
			? content->add(
				object_ptr<Ui::SettingsButton>(
					content,
					langExpanded->value() | rpl::map([=](bool toggled) {
						return langTitle + (toggled ? u"  \xE2\x96\xBE"_q : u"  \xE2\x96\xB8"_q);
					}),
					st::settingsButtonNoIcon))
			: nullptr;

		auto langWrap = content->add(
			object_ptr<Ui::SlideWrap<Ui::VerticalLayout>>(
				content,
				object_ptr<Ui::VerticalLayout>(content)));
		const auto langInner = langWrap->entity();

		if (langBtn) {
			langBtn->setClickedCallback([=] {
				const auto toggled = !langWrap->toggled();
				langWrap->toggle(toggled, anim::type::normal);
			});

			langWrap->toggledValue(
			) | rpl::on_next([=](bool toggled) {
				*langExpanded = toggled;
			}, langBtn->lifetime());
		}

		langWrap->toggle(isDefaultLang, anim::type::instant);

		for (const auto &sub : lang.subblocks) {
			if (sub.items.empty()) {
				continue;
			}
			const auto isAdded = (sub.category == u"Added"_q);
			const auto isFixes = (sub.category == u"Fixes"_q);
			const auto countStr = u" ("_q + QString::number(sub.items.size()) + u")"_q;
			const auto icon = isAdded
				? QString::fromUtf8("\xE2\x9C\xA6 ")
				: isFixes
				? QString::fromUtf8("\xE2\x9C\x94 ")
				: QString::fromUtf8("\xE2\x9A\xA1 ");

			const auto baseTitle = icon
				+ (sub.header.endsWith(':') ? sub.header.left(sub.header.size() - 1) : sub.header)
				+ countStr;

			const auto subExpanded = langInner->lifetime().make_state<rpl::variable<bool>>(true);

			const auto subBtn = langInner->add(
				object_ptr<Ui::SettingsButton>(
					langInner,
					subExpanded->value() | rpl::map([=](bool toggled) {
						return baseTitle + (toggled ? u"  \xE2\x96\xBE"_q : u"  \xE2\x96\xB8"_q);
					}),
					st::settingsButtonNoIcon));

			auto subWrap = langInner->add(
				object_ptr<Ui::SlideWrap<Ui::VerticalLayout>>(
					langInner,
					object_ptr<Ui::VerticalLayout>(langInner)));
			const auto subInner = subWrap->entity();

			subBtn->setClickedCallback([=] {
				const auto toggled = !subWrap->toggled();
				subWrap->toggle(toggled, anim::type::normal);
			});

			subWrap->toggledValue(
			) | rpl::on_next([=](bool toggled) {
				*subExpanded = toggled;
			}, subBtn->lifetime());

			subWrap->toggle(true, anim::type::instant);

			for (const auto &item : sub.items) {
				const auto label = subInner->add(
					object_ptr<Ui::FlatLabel>(
						subInner,
						rpl::single(FormatItem(item)),
						st::boxLabel),
					st::boxRowPadding);
				label->setSelectable(true);
			}
			Ui::AddSkip(subInner, st::settingsCheckboxesSkip);
		}

		for (const auto &item : lang.miscItems) {
			const auto label = langInner->add(
				object_ptr<Ui::FlatLabel>(
					langInner,
					rpl::single(FormatItem(item)),
					st::boxLabel),
				st::boxRowPadding);
			label->setSelectable(true);
		}
	}
}

void Fill(
		not_null<Ui::GenericBox*> box,
		not_null<Window::SessionController*> controller) {
	const auto &state = Instance();
	const auto content = box->verticalLayout();
	if (state.releases.empty()) {
		content->add(
			object_ptr<Ui::FlatLabel>(
				content,
				(state.failed
					? tr::lng_exd_changelog_failed()
					: tr::lng_exd_changelog_loading()),
				st::boxLabel),
			st::boxRowPadding);
		return;
	}

	auto first = true;
	for (const auto &release : state.releases) {
		if (!first) {
			Ui::AddSkip(content);
			Ui::AddDivider(content);
			Ui::AddSkip(content);
		}
		first = false;
		FillReleaseContent(content, release, false);
	}
}

[[nodiscard]] TextWithEntities TranslationText() {
	constexpr auto kLimit = 3500;
	auto result = TextWithEntities();
	for (const auto &release : Instance().releases) {
		auto part = Ui::Text::Bold(u"oxDesktop "_q + release.version);
		for (const auto &lang : release.languages) {
			for (const auto &sub : lang.subblocks) {
				part.append(u"\n\n"_q + sub.header);
				for (const auto &item : sub.items) {
					part.append(u"\n- "_q + item);
				}
			}
		}
		if (!result.empty()
			&& result.text.size() + part.text.size() + 2 > kLimit) {
			break;
		}
		if (!result.empty()) {
			result.append(u"\n\n"_q);
		}
		result.append(part);
	}
	return result;
}

void ShowLoaded(not_null<Window::SessionController*> controller) {
	controller->show(Box([=](not_null<Ui::GenericBox*> box) {
		box->setTitle(tr::lng_exd_changelog_title());
		box->setWidth(st::boxWideWidth * 3 / 2);
		box->setMaxHeight(st::boxMaxListHeight);
		Fill(box, controller);
		box->addButton(tr::lng_close(), [=] { box->closeBox(); });
		if (!Instance().releases.empty()) {
			box->addLeftButton(tr::lng_exd_changelog_translate(), [=] {
				controller->show(
					Box(
						Ui::TranslateBox,
						controller->session().user(),
						MsgId(),
						TranslationText(),
						false),
					Ui::LayerOption::KeepOther);
			});
		}
	}));
}

void ShowWhenReady(not_null<Window::SessionController*> controller) {
	const auto weak = base::make_weak(controller);
	Load([=] {
		if (const auto strong = weak.get()) {
			ShowLoaded(strong);
		}
	});
}

} // namespace

void Start() {
	static auto started = false;
	if (started) {
		return;
	}
	started = true;
	auto file = QFile(CachePath());
	if (!file.exists() && QFile::exists(LegacyCachePath())) {
		file.setFileName(LegacyCachePath());
	}
	if (file.open(QIODevice::ReadOnly)) {
		Apply(file.readAll());
	}
	if (Instance().releases.empty()) {
		ApplyFallback();
	}
	Core::App().domain().activeSessionValue(
	) | rpl::filter([](Main::Session *session) {
		return session != nullptr;
	}) | rpl::take(1) | rpl::on_next([](Main::Session *session) {
		const auto seen = Int(u"changelog_seen"_q);
		const auto current = CurrentKey();
		if (seen >= current || (!seen && !Bool(u"wizard_shown"_q))) {
			Config::Instance().setInt(u"changelog_seen"_q, current);
			return;
		}
		base::call_delayed(kShowDelay, [=] {
			const auto window = Core::App().activePrimaryWindow();
			if (const auto controller = window
					? window->sessionController()
					: nullptr) {
				Config::Instance().setInt(u"changelog_seen"_q, current);
				ShowWhenReady(controller);
			}
		});
	}, Instance().lifetime);
}

void Show(not_null<Window::SessionController*> controller) {
	if (Instance().releases.empty()) {
		ShowWhenReady(controller);
	} else {
		ShowLoaded(controller);
		Load(nullptr);
	}
}

void ShowUpdate(
		not_null<Window::SessionController*> controller,
		const QString &version,
		const QString &body) {
	controller->show(Box([=](not_null<Ui::GenericBox*> box) {
		box->setTitle(tr::lng_extera_update());
		box->setWidth(st::boxWideWidth * 3 / 2);
		box->setMaxHeight(st::boxMaxListHeight);

		auto release = StructuredRelease{
			.version = version.startsWith('v') ? version.mid(1) : version,
			.date = QDate::currentDate(),
			.rawBody = body,
			.languages = {},
		};
		const auto parsed = ParseReleasesFromText(body);
		if (!parsed.empty()) {
			release = parsed.front();
			if (release.version.isEmpty()) {
				release.version = version;
			}
		}
		FillReleaseContent(box->verticalLayout(), release, true);

		box->addButton(tr::lng_update_telegram(), [=] {
			box->closeBox();
			Extera::Update::Install();
		});
		box->addButton(tr::lng_close(), [=] {
			box->closeBox();
		});
	}));
}

void FillLatestFromChangelog(not_null<Ui::VerticalLayout*> container) {
	ApplyFallback();
	const auto &releases = Instance().releases;
	if (!releases.empty()) {
		FillReleaseContent(container, releases.front(), false);
	}
}

} // namespace Extera::Changelog
