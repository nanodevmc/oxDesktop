#include "extera/extera_badges.h"

#include "extera/extera_ws_proxy.h"
#include "data/data_changes.h"
#include "data/data_peer.h"
#include "data/data_session.h"
#include "data/data_user.h"
#include "main/main_session.h"
#include "settings.h"
#include "version_generated.h"

#include <base/flat_set.h>
#include <QtCore/QDir>
#include <QtCore/QFile>
#include <QtCore/QFileInfo>
#include <QtCore/QJsonArray>
#include <QtCore/QJsonDocument>
#include <QtCore/QJsonObject>
#include <QtCore/QTimer>
#include <QtNetwork/QNetworkAccessManager>
#include <QtNetwork/QNetworkProxy>
#include <QtNetwork/QNetworkReply>
#include <QtNetwork/QNetworkRequest>

#ifdef Q_OS_WIN
#pragma comment(lib, "dnsapi.lib")
#endif

namespace Extera {
namespace {

constexpr auto kDeveloperEmoji = DocumentId(5395339798430919126ULL);
constexpr auto kExteraArrowsEmoji = DocumentId(5391059537102927631ULL);
constexpr auto kBughunterEmoji = DocumentId(5416037430513936515ULL);
constexpr auto kHelperEmoji = DocumentId(5415603784845926997ULL);
constexpr auto kDonorEmoji = DocumentId(5413871448441793380ULL);
constexpr auto kSupporterEmoji = DocumentId(5413871448441793380ULL);
constexpr auto kTrustedEmoji = DocumentId(5420443203671208138ULL);
constexpr auto kCustomLeadDevEmoji = DocumentId(5425060246269736415ULL);
constexpr auto kRefreshInterval = 60 * 60 * 1000;

struct Profile {
	uint64 id = 0;
	QString type;
	QString status;
	DocumentId badgeDocumentId = 0;
	QString badgeText;
	int number = 0;
	bool canChangeBadge = false;
};

struct ProfilesState {
	base::flat_map<uint64, Profile> items;
	base::flat_set<uint64> requestedIds;
	std::vector<TrustedSource> trustedSources;
	base::flat_set<QString> trustedHashes;
	int64 lastSyncTimestamp = 0;
	QByteArray badgesEtag;
	QByteArray hashesEtag;
	QNetworkAccessManager *manager = nullptr;
};

ProfilesState &State() {
	static auto result = ProfilesState();
	return result;
}

[[nodiscard]] QString CachePath() {
	return cWorkingDir() + u"tdata/ox_profiles.json"_q;
}

[[nodiscard]] QString LegacyProfilesPath() {
	return cWorkingDir() + u"tdata/extera_profiles.json"_q;
}

[[nodiscard]] QString LegacyBadgesPath() {
	return cWorkingDir() + u"tdata/extera_badges.json"_q;
}

[[nodiscard]] uint64 ReadId(const QJsonValue &value) {
	return value.isString()
		? value.toString().toULongLong()
		: uint64(value.toInteger());
}

[[nodiscard]] uint64 BareId(not_null<PeerData*> peer) {
	return uint64(peerToBareMTPInt(peer->id).v);
}

bool ApplySingleProfile(const QJsonObject &obj) {
	const auto id = ReadId(obj.value(u"id"_q));
	if (!id) {
		return false;
	}
	auto &state = State();
	if (state.items.contains(id) && state.items[id].status == u"OWNER"_q) {
		auto &existing = state.items[id];
		if (obj.contains(u"number"_q)) {
			existing.number = obj.value(u"number"_q).toInt();
		}
		if (obj.contains(u"badge"_q)) {
			const auto badgeObj = obj.value(u"badge"_q).toObject();
			const auto docId = DocumentId(ReadId(badgeObj.value(u"documentId"_q)));
			if (docId != 0) {
				existing.badgeDocumentId = docId;
			}
			const auto text = badgeObj.value(u"text"_q).toString();
			if (!text.isEmpty()) {
				existing.badgeText = text;
			}
		}
		return true;
	}

	Profile profile;
	profile.id = id;
	profile.type = obj.value(u"type"_q).toString();
	profile.status = obj.value(u"status"_q).toString().toUpper();
	profile.number = obj.value(u"number"_q).toInt();
	profile.canChangeBadge = obj.value(u"canChangeBadge"_q).toBool();
	if (obj.contains(u"badge"_q)) {
		const auto badgeObj = obj.value(u"badge"_q).toObject();
		profile.badgeDocumentId = DocumentId(
			ReadId(badgeObj.value(u"documentId"_q)));
		profile.badgeText = badgeObj.value(u"text"_q).toString();
	}
	if (profile.badgeDocumentId == 0) {
		if (profile.status == u"SUPPORTER"_q
			|| profile.type.compare(u"extera"_q, Qt::CaseInsensitive) == 0
			|| profile.type.compare(u"arrows"_q, Qt::CaseInsensitive) == 0
			|| profile.type.compare(u"user"_q, Qt::CaseInsensitive) == 0) {
			profile.badgeDocumentId = kExteraArrowsEmoji;
		}
	}
	state.items[id] = std::move(profile);
	return true;
}

bool ApplyProfiles(const QByteArray &bytes, bool incremental) {
	const auto document = QJsonDocument::fromJson(bytes);
	QJsonArray array;
	auto &state = State();

	if (document.isObject()) {
		const auto rootObj = document.object();
		if (rootObj.contains(u"id"_q)
			&& (rootObj.contains(u"status"_q) || rootObj.contains(u"badge"_q) || rootObj.contains(u"number"_q))) {
			return ApplySingleProfile(rootObj);
		}
		if (rootObj.contains(u"trusted"_q)) {
			auto list = std::vector<TrustedSource>();
			for (const auto &entry : rootObj.value(u"trusted"_q).toArray()) {
				const auto obj = entry.toObject();
				const auto id = ReadId(obj.value(u"id"_q));
				const auto username = obj.value(u"username"_q).toString();
				if (id != 0 || !username.isEmpty()) {
					list.push_back({ .id = id, .username = username });
				}
			}
			if (!list.empty()) {
				state.trustedSources = std::move(list);
			}
		}

		if (rootObj.contains(u"users"_q) || rootObj.contains(u"channels"_q)) {
			auto typesMap = base::flat_map<QString, DocumentId>();
			if (rootObj.contains(u"types"_q)) {
				const auto typesObj = rootObj.value(u"types"_q).toObject();
				for (auto it = typesObj.begin(); it != typesObj.end(); ++it) {
					if (it.value().isObject()) {
						const auto tObj = it.value().toObject();
						typesMap[it.key()] = DocumentId(ReadId(tObj.value(u"emoji"_q)));
					}
				}
			}
			auto parseList = [&](const QJsonArray &list, bool isChannel) {
				for (const auto &entry : list) {
					const auto obj = entry.toObject();
					const auto id = ReadId(obj.value(u"id"_q));
					if (!id) continue;
					Profile p;
					p.id = id;
					p.type = obj.value(u"type"_q).toString();
					p.status = p.type.toUpper();
					p.badgeText = obj.value(u"text"_q).toString();
					p.number = obj.value(u"number"_q).toInt();
					if (obj.contains(u"emoji"_q)) {
						p.badgeDocumentId = DocumentId(ReadId(obj.value(u"emoji"_q)));
					} else if (typesMap.contains(p.type)) {
						p.badgeDocumentId = typesMap[p.type];
					}
					state.items[id] = std::move(p);
				}
			};
			if (rootObj.contains(u"users"_q)) {
				parseList(rootObj.value(u"users"_q).toArray(), false);
			}
			if (rootObj.contains(u"channels"_q)) {
				parseList(rootObj.value(u"channels"_q).toArray(), true);
			}
			return true;
		} else if (rootObj.contains(u"profiles"_q)) {
			array = rootObj.value(u"profiles"_q).toArray();
		} else if (rootObj.contains(u"id"_q)
			|| rootObj.contains(u"status"_q)
			|| rootObj.contains(u"type"_q)) {
			array.append(rootObj);
		}
	} else if (document.isArray()) {
		array = document.array();
	}

	if (array.isEmpty() && !document.isArray()) {
		return false;
	}

	for (const auto &entry : array) {
		ApplySingleProfile(entry.toObject());
	}
	return true;
}

void SaveToCache() {
	const auto &state = State();
	auto array = QJsonArray();
	for (const auto &[id, profile] : state.items) {
		auto obj = QJsonObject{
			{ u"id"_q, QString::number(profile.id) },
			{ u"type"_q, profile.type },
			{ u"status"_q, profile.status },
			{ u"number"_q, profile.number },
			{ u"canChangeBadge"_q, profile.canChangeBadge },
		};
		if (profile.badgeDocumentId || !profile.badgeText.isEmpty()) {
			obj.insert(u"badge"_q, QJsonObject{
				{ u"documentId"_q, QString::number(profile.badgeDocumentId) },
				{ u"text"_q, profile.badgeText },
			});
		}
		array.append(std::move(obj));
	}
	const auto path = CachePath();
	QDir().mkpath(QFileInfo(path).absolutePath());
	auto file = QFile(path);
	if (file.open(QIODevice::WriteOnly)) {
		file.write(QJsonDocument(array).toJson(QJsonDocument::Compact));
	}
}

void ApplyTrustedHashes(const QByteArray &bytes) {
	const auto doc = QJsonDocument::fromJson(bytes);
	if (!doc.isObject()) {
		return;
	}
	auto &state = State();
	const auto array = doc.object().value(u"hashes"_q).toArray();
	for (const auto &entry : array) {
		const auto hash = entry.toObject().value(u"sha256"_q).toString().toLower();
		if (!hash.isEmpty()) {
			state.trustedHashes.insert(hash);
		}
	}
}

template <typename OnData>
void FetchJsonWithEtag(
		not_null<QNetworkAccessManager*> manager,
		const QString &url,
		QByteArray *etagStorage,
		OnData &&onData) {
	auto request = QNetworkRequest(QUrl(url));
	request.setRawHeader("User-Agent", "oxDesktop/" APP_VERSION);
	request.setRawHeader("Accept", "application/json");
	if (etagStorage && !etagStorage->isEmpty()) {
		request.setRawHeader("If-None-Match", *etagStorage);
	}
	request.setTransferTimeout(10000);
	const auto reply = manager->get(request);
	QObject::connect(reply, &QNetworkReply::finished, [=, onData = std::forward<OnData>(onData)]() mutable {
		reply->deleteLater();
		const auto code = reply->attribute(
			QNetworkRequest::HttpStatusCodeAttribute).toInt();
		if (code == 304) {
			return;
		}
		if (reply->error() == QNetworkReply::NoError) {
			const auto etag = reply->rawHeader("ETag");
			if (etagStorage && !etag.isEmpty()) {
				*etagStorage = etag;
			}
			onData(reply->readAll());
		}
	});
}

void RefreshProfiles(QNetworkAccessManager *manager) {
	FetchJsonWithEtag(
		manager,
		u"https://raw.githubusercontent.com/nanodevmc/oxDesktop/main/badges.json"_q,
		&State().badgesEtag,
		[](const QByteArray &bytes) {
			if (ApplyProfiles(bytes, false)) {
				SaveToCache();
			}
		});
	FetchJsonWithEtag(
		manager,
		u"https://raw.githubusercontent.com/nanodevmc/oxDesktop/main/trusted_hashes.json"_q,
		&State().hashesEtag,
		[](const QByteArray &bytes) {
			ApplyTrustedHashes(bytes);
		});
	FetchJsonWithEtag(
		manager,
		u"https://api.exteragram.app/api/v1/profiles"_q,
		nullptr,
		[](const QByteArray &bytes) {
			if (ApplyProfiles(bytes, true)) {
				SaveToCache();
			}
		});
}

void MaybeFetchProfile(not_null<PeerData*> peer) {
	if (!peer->isUser()) {
		return;
	}
	const auto bare = BareId(peer);
	if (!bare) {
		return;
	}
	auto &state = State();
	if (state.items.contains(bare) || state.requestedIds.contains(bare)) {
		return;
	}
	state.requestedIds.insert(bare);
	if (!state.manager) {
		state.manager = new QNetworkAccessManager(qApp);
	}
	Extera::WsProxy::ApplyHttpProxy(state.manager);
	const auto url = u"https://api.exteragram.app/api/v1/profiles/"_q + QString::number(bare);
	auto request = QNetworkRequest(QUrl(url));
	request.setRawHeader("User-Agent", "oxDesktop/" APP_VERSION);
	request.setRawHeader("Accept", "application/json");
	request.setTransferTimeout(8000);
	Extera::WsProxy::PrepareFrontedRequest(request);
	const auto reply = state.manager->get(request);
	const auto session = &peer->session();
	QObject::connect(reply, &QNetworkReply::finished, [reply, peer, session, bare] {
		reply->deleteLater();
		const auto httpCode = reply->attribute(
			QNetworkRequest::HttpStatusCodeAttribute).toInt();
		auto applied = false;
		if (reply->error() == QNetworkReply::NoError) {
			const auto bytes = reply->readAll();
			if (!bytes.isEmpty() && ApplyProfiles(bytes, true)) {
				SaveToCache();
				applied = true;
			}
		} else if (httpCode == 404) {
			auto &state = State();
			if (!state.items.contains(bare)) {
				Profile profile;
				profile.id = bare;
				profile.status = u"NONE"_q;
				state.items[bare] = std::move(profile);
			}
			applied = true;
		}
		if (!applied) {
			auto &state = State();
			if (!state.items.contains(bare)) {
				Profile profile;
				profile.id = bare;
				profile.status = u"API_ERROR"_q;
				profile.badgeText = u"Ошибка запроса API"_q;
				state.items[bare] = std::move(profile);
			}
		}
		crl::on_main(session, [peer, session] {
			session->changes().peerUpdated(
				peer,
				Data::PeerUpdate::Flag::EmojiStatus);
		});
	});
}

} // namespace

void StartBadges() {
	static auto started = false;
	if (started) {
		return;
	}
	started = true;

	static const auto kBuiltinBadgesJson = R"({
  "types": {
    "owner": { "emoji": "5425060246269736415", "text": "Создатель oxDesktop" },
    "developer": { "emoji": "5395339798430919126", "text": "Разработчик oxDesktop" },
    "extera": { "emoji": "5391059537102927631", "text": "Стрелочки ExteraGram" },
    "bughunter": { "emoji": "5416037430513936515", "text": "Охотник за багами" },
    "helper": { "emoji": "5415603784845926997", "text": "Помощник" },
    "donor": { "emoji": "5413871448441793380", "text": "Поддержка oxDesktop" },
    "trusted": { "emoji": "5420443203671208138", "text": "Доверенный источник" }
  },
  "users": [
    { "id": 6486689289, "type": "owner", "number": 1, "emoji": "5425060246269736415", "text": "Ведущий разработчик oxDesktop" },
    { "id": 6296191170, "type": "developer", "number": 2, "text": "Второй в этой компании, друг разработчика oxDesktop." }
  ],
  "channels": [
    { "id": 1571726392, "type": "extera", "text": "exteraGram — с 5-летием проекта!" },
    { "id": 4364437246, "type": "developer" },
    { "id": 4469639949, "type": "developer" }
  ],
  "trusted": [
    { "id": 4469639949, "username": "oxDesktop", "name": "oxDesktop" }
  ]
})";
	ApplyProfiles(QByteArray(kBuiltinBadgesJson), false);

	for (const auto &p : {
			cWorkingDir() + u"badges.json"_q,
			u":/badges.json"_q,
			CachePath(),
			LegacyProfilesPath(),
			LegacyBadgesPath() }) {
		auto f = QFile(p);
		if (f.open(QIODevice::ReadOnly)) {
			ApplyProfiles(f.readAll(), true);
		}
	}

	for (const auto &p : {
			cWorkingDir() + u"trusted_hashes.json"_q,
			u":/trusted_hashes.json"_q,
			cWorkingDir() + u"tdata/trusted_hashes.json"_q }) {
		auto f = QFile(p);
		if (f.open(QIODevice::ReadOnly)) {
			ApplyTrustedHashes(f.readAll());
		}
	}

	const auto manager = new QNetworkAccessManager(qApp);
	RefreshProfiles(manager);

	const auto timer = new QTimer(manager);
	QObject::connect(timer, &QTimer::timeout, [=] {
		RefreshProfiles(manager);
	});
	timer->start(kRefreshInterval);
}

BadgeKind BadgeKindFor(not_null<PeerData*> peer) {
	const auto bare = BareId(peer);
	if (!bare) {
		return BadgeKind::None;
	}
	MaybeFetchProfile(peer);
	const auto &items = State().items;
	const auto it = items.find(bare);
	if (it == end(items)) {
		return BadgeKind::None;
	}
	const auto &profile = it->second;
	if (profile.status == u"OWNER"_q) {
		return BadgeKind::Owner;
	}
	if (profile.badgeDocumentId != 0) {
		return BadgeKind::Custom;
	}
	if (profile.status == u"DEVELOPER"_q) {
		return peer->isUser() ? BadgeKind::Developer : BadgeKind::OfficialChannel;
	} else if (profile.status == u"PORTER"_q) {
		return peer->isUser() ? BadgeKind::Porter : BadgeKind::PorterChannel;
	} else if (profile.status == u"SUPPORTER"_q || profile.status == u"DONOR"_q) {
		return BadgeKind::Supporter;
	} else if (profile.status == u"BUGHUNTER"_q) {
		return BadgeKind::Bughunter;
	} else if (profile.status == u"HELPER"_q) {
		return BadgeKind::Helper;
	} else if (profile.status == u"TRUSTED"_q) {
		return BadgeKind::Trusted;
	}
	return BadgeKind::None;
}

bool BadgeApiError(not_null<PeerData*> peer) {
	const auto bare = BareId(peer);
	if (!bare) {
		return false;
	}
	const auto &items = State().items;
	const auto it = items.find(bare);
	return (it != end(items)) && (it->second.status == u"API_ERROR"_q);
}

DocumentId BadgeEmoji(not_null<PeerData*> peer) {
	const auto bare = BareId(peer);
	if (!bare) {
		return DocumentId();
	}
	MaybeFetchProfile(peer);
	const auto &items = State().items;
	const auto it = items.find(bare);
	if (it != end(items)) {
		const auto &profile = it->second;
		if (profile.status == u"OWNER"_q) {
			return profile.badgeDocumentId ? profile.badgeDocumentId : kCustomLeadDevEmoji;
		}
		if (profile.badgeDocumentId != 0) {
			return profile.badgeDocumentId;
		}
		if (profile.type == u"extera"_q || profile.type == u"arrows"_q || profile.type == u"exteragram"_q) {
			return kExteraArrowsEmoji;
		}
		if (profile.status == u"DEVELOPER"_q) {
			return kDeveloperEmoji;
		} else if (profile.status == u"SUPPORTER"_q || profile.status == u"DONOR"_q) {
			return kExteraArrowsEmoji;
		} else if (profile.status == u"BUGHUNTER"_q) {
			return kBughunterEmoji;
		} else if (profile.status == u"HELPER"_q) {
			return kHelperEmoji;
		} else if (profile.status == u"TRUSTED"_q) {
			return kTrustedEmoji;
		}
	}
	return DocumentId();
}

QString BadgeCustomText(not_null<PeerData*> peer) {
	const auto bare = BareId(peer);
	if (!bare) {
		return QString();
	}
	MaybeFetchProfile(peer);
	const auto &items = State().items;
	const auto it = items.find(bare);
	if (it != end(items)) {
		const auto &profile = it->second;
		if (!profile.badgeText.isEmpty()) {
			auto text = profile.badgeText;
			return text.replace(u"**"_q, QString());
		}
	}
	if (bare == 1571726392ULL) {
		return u"exteraGram — с 5-летием проекта!"_q;
	}
	return QString();
}

int BadgeNumber(not_null<PeerData*> peer) {
	const auto bare = BareId(peer);
	if (!bare) {
		return 0;
	}
	MaybeFetchProfile(peer);
	const auto &items = State().items;
	const auto it = items.find(bare);
	if (it != end(items)) {
		return it->second.number;
	}
	return 0;
}

DocumentId BadgeTypeEmoji(const QString &type) {
	if (type == u"owner"_q) {
		return kCustomLeadDevEmoji;
	} else if (type == u"developer"_q) {
		return kDeveloperEmoji;
	} else if (type == u"extera"_q || type == u"arrows"_q || type == u"exteragram"_q) {
		return kExteraArrowsEmoji;
	} else if (type == u"bughunter"_q) {
		return kBughunterEmoji;
	} else if (type == u"helper"_q) {
		return kHelperEmoji;
	} else if (type == u"donor"_q || type == u"supporter"_q) {
		return kExteraArrowsEmoji;
	} else if (type == u"trusted"_q) {
		return kTrustedEmoji;
	} else if (type == u"custom"_q) {
		return kCustomLeadDevEmoji;
	}
	return DocumentId();
}

std::optional<std::vector<TrustedSource>> TrustedSources() {
	const auto &state = State();
	if (!state.trustedSources.empty()) {
		return state.trustedSources;
	}
	static const auto defaultSources = std::vector<TrustedSource>{
		{ .id = 4469639949ULL, .username = u"oxDesktop"_q },
	};
	return defaultSources;
}

bool IsTrustedHash(const QString &sha256) {
	if (sha256.isEmpty()) {
		return false;
	}
	const auto &state = State();
	return state.trustedHashes.contains(sha256.toLower());
}

void RequestNowPlaying(
		not_null<PeerData*> peer,
		Fn<void(NowPlayingInfo)> done) {
	if (!done) {
		return;
	}
	const auto bare = peer->isUser() ? BareId(peer) : 0ULL;
	if (!bare) {
		done({});
		return;
	}
	auto &state = State();
	if (!state.manager) {
		state.manager = new QNetworkAccessManager(qApp);
	}
	Extera::WsProxy::ApplyHttpProxy(state.manager);
	auto request = QNetworkRequest(QUrl(
		u"https://api.exteragram.app/api/v1/profiles/"_q
		+ QString::number(bare)
		+ u"/now-playing"_q));
	request.setRawHeader("User-Agent", "oxDesktop/" APP_VERSION);
	request.setRawHeader("Accept", "application/json");
	request.setTransferTimeout(6000);
	Extera::WsProxy::PrepareFrontedRequest(request);
	const auto reply = state.manager->get(request);
	QObject::connect(reply, &QNetworkReply::finished, [reply, done = std::move(done)] {
		reply->deleteLater();
		if (reply->error() != QNetworkReply::NoError) {
			done({});
			return;
		}
		const auto doc = QJsonDocument::fromJson(reply->readAll());
		const auto obj = doc.object();
		const auto playing = obj.value(u"is_playing"_q).toBool(
			obj.value(u"playing"_q).toBool(true));
		const auto track = obj.contains(u"track"_q)
			? obj.value(u"track"_q).toObject()
			: obj;
		const auto title = track.value(u"name"_q).toString(
			track.value(u"title"_q).toString());
		auto artist = track.value(u"artist"_q).toString();
		if (artist.isEmpty() && track.value(u"artists"_q).isArray()) {
			QStringList list;
			for (const auto &v : track.value(u"artists"_q).toArray()) {
				const auto name = v.isObject()
					? v.toObject().value(u"name"_q).toString()
					: v.toString();
				if (!name.isEmpty()) {
					list.push_back(name);
				}
			}
			artist = list.join(u", "_q);
		}
		if (!playing || title.isEmpty()) {
			done({});
			return;
		}
		done(NowPlayingInfo{
			.playing = true,
			.title = title,
			.artist = artist,
		});
	});
}

} // namespace Extera
