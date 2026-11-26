#pragma once

class PeerData;

namespace Extera {

enum class BadgeKind {
	None,
	Owner,
	Porter,
	PorterChannel,
	Developer,
	OfficialChannel,
	Supporter,
	Trusted,
	Custom,
	Bughunter,
	Helper,
	Donor,
};

struct TrustedSource {
	uint64 id = 0;
	QString username;
};

struct NowPlayingInfo {
	bool playing = false;
	QString title;
	QString artist;
};

void StartBadges();

[[nodiscard]] BadgeKind BadgeKindFor(not_null<PeerData*> peer);
[[nodiscard]] bool BadgeApiError(not_null<PeerData*> peer);
[[nodiscard]] DocumentId BadgeEmoji(not_null<PeerData*> peer);
[[nodiscard]] QString BadgeCustomText(not_null<PeerData*> peer);
[[nodiscard]] int BadgeNumber(not_null<PeerData*> peer);
[[nodiscard]] DocumentId BadgeTypeEmoji(const QString &type);
[[nodiscard]] std::optional<std::vector<TrustedSource>> TrustedSources();
[[nodiscard]] bool IsTrustedHash(const QString &sha256);
void RequestNowPlaying(
	not_null<PeerData*> peer,
	Fn<void(NowPlayingInfo)> done);

} // namespace Extera
