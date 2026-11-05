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

void StartBadges();

[[nodiscard]] BadgeKind BadgeKindFor(not_null<PeerData*> peer);
[[nodiscard]] DocumentId BadgeEmoji(not_null<PeerData*> peer);
[[nodiscard]] QString BadgeCustomText(not_null<PeerData*> peer);
[[nodiscard]] int BadgeNumber(not_null<PeerData*> peer);
[[nodiscard]] DocumentId BadgeTypeEmoji(const QString &type);
[[nodiscard]] std::optional<std::vector<TrustedSource>> TrustedSources();
[[nodiscard]] bool IsTrustedHash(const QString &sha256);

} // namespace Extera
