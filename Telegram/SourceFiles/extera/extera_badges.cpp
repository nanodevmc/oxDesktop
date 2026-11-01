#include "extera/extera_badges.h"

#include "data/data_peer.h"
#include "settings.h"

#include <QtCore/QDir>
#include <QtCore/QFile>
#include <QtCore/QFileInfo>
#include <QtCore/QJsonArray>
#include <QtCore/QJsonDocument>
#include <QtCore/QJsonObject>
#include <QtCore/QTimer>
#include <QtNetwork/QNetworkAccessManager>
#include <QtNetwork/QNetworkReply>
#include <QtNetwork/QNetworkRequest>

namespace Extera {
namespace {

constexpr auto kDeveloperEmoji = DocumentId(5359407509327085568ULL);
constexpr auto kSupporterEmoji = DocumentId(5391059537102927631ULL);
constexpr auto kTrustedEmoji = DocumentId(5452008215409629764ULL);
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
	int64 lastSyncTimestamp = 0;
};

ProfilesState &State() {
	static auto result = ProfilesState();
	return result;
}

[[nodiscard]] QString CachePath() {
	return cWorkingDir() + u"tdata/extera_profiles.json"_q;
}

[[nodiscard]] QString LegacyCachePath() {
	return cWorkingDir() + u"tdata/extera_badges.json"_q;
}

[[nodiscard]] uint64 ReadId(const QJsonValue &value) {
	return value.isString()
		? value.toString().toULongLong()
		: uint64(value.toInteger());
}

[[nodiscard]] uint64 BareId(not_null<PeerData*> peer) {
	if (peer->isUser()) {
		return uint64(peerToUser(peer->id).bare);
	} else if (peer->isChannel()) {
		return uint64(peerToChannel(peer->id).bare);
	} else if (peer->isChat()) {
		return uint64(peerToChat(peer->id).bare);
	}
	return 0;
}

bool ApplyProfiles(const QByteArray &bytes, bool incremental) {
	const auto document = QJsonDocument::fromJson(bytes);
	QJsonArray array;
	if (document.isArray()) {
		array = document.array();
	} else if (document.isObject()) {
		const auto obj = document.object();
		if (obj.contains(u"profiles"_q)) {
			array = obj.value(u"profiles"_q).toArray();
		}
	}
	if (array.isEmpty() && !document.isArray()) {
		return false;
	}

	auto &state = State();
	if (!incremental) {
		state.items.clear();
	}

	for (const auto &entry : array) {
		const auto obj = entry.toObject();
		const auto id = ReadId(obj.value(u"id"_q));
		if (!id) {
			continue;
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
		state.items[id] = std::move(profile);
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

void RefreshProfiles(QNetworkAccessManager *manager) {
	auto request = QNetworkRequest(QUrl(
		u"https://api.exteragram.app/api/v1/profiles"_q));
	request.setRawHeader("User-Agent", "exteraGram/13.1.1");
	request.setRawHeader("Accept", "application/json");

	const auto reply = manager->get(request);
	QObject::connect(reply, &QNetworkReply::finished, [=] {
		reply->deleteLater();
		if (reply->error() != QNetworkReply::NoError) {
			return;
		}
		const auto bytes = reply->readAll();
		if (ApplyProfiles(bytes, false)) {
			SaveToCache();
		}
	});
}

} // namespace

void StartBadges() {
	static auto started = false;
	if (started) {
		return;
	}
	started = true;

	auto file = QFile(CachePath());
	if (file.open(QIODevice::ReadOnly)) {
		ApplyProfiles(file.readAll(), false);
	} else {
		auto legacy = QFile(LegacyCachePath());
		if (legacy.open(QIODevice::ReadOnly)) {
			ApplyProfiles(legacy.readAll(), false);
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
	const auto &items = State().items;
	const auto it = items.find(bare);
	if (it == end(items)) {
		return BadgeKind::None;
	}
	const auto &profile = it->second;
	if (profile.badgeDocumentId != 0) {
		return BadgeKind::Custom;
	}
	if (profile.status == u"DEVELOPER"_q) {
		return peer->isUser() ? BadgeKind::Developer : BadgeKind::OfficialChannel;
	} else if (profile.status == u"SUPPORTER"_q) {
		return BadgeKind::Supporter;
	}
	return BadgeKind::None;
}

DocumentId BadgeEmoji(not_null<PeerData*> peer) {
	const auto bare = BareId(peer);
	if (!bare) {
		return DocumentId();
	}
	const auto &items = State().items;
	const auto it = items.find(bare);
	if (it != end(items)) {
		const auto &profile = it->second;
		if (profile.badgeDocumentId != 0) {
			return profile.badgeDocumentId;
		}
		if (profile.status == u"DEVELOPER"_q) {
			return kDeveloperEmoji;
		} else if (profile.status == u"SUPPORTER"_q) {
			return kSupporterEmoji;
		}
	}
	return DocumentId();
}

QString BadgeCustomText(not_null<PeerData*> peer) {
	const auto bare = BareId(peer);
	if (!bare) {
		return QString();
	}
	const auto &items = State().items;
	const auto it = items.find(bare);
	if (it != end(items)) {
		const auto &profile = it->second;
		if (!profile.badgeText.isEmpty()) {
			auto text = profile.badgeText;
			return text.replace(u"**"_q, QString());
		}
	}
	return QString();
}

DocumentId BadgeTypeEmoji(const QString &type) {
	if (type == u"developer"_q) {
		return kDeveloperEmoji;
	} else if (type == u"supporter"_q) {
		return kSupporterEmoji;
	} else if (type == u"trusted"_q) {
		return kTrustedEmoji;
	}
	return DocumentId();
}

std::optional<std::vector<TrustedSource>> TrustedSources() {
	static const auto sources = std::vector<TrustedSource>{
		{ .id = 1588661783ULL, .username = u"exteraPluginRepo"_q },
		{ .id = 1481105943ULL, .username = u"exteraGram"_q },
	};
	return sources;
}

bool IsTrustedHash(const QString &sha256) {
	return !sha256.isEmpty();
}

} // namespace Extera
