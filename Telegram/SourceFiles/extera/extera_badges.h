#pragma once

class PeerData;

namespace Extera {

enum class BadgeKind {
	None,
	Developer,
	OfficialChannel,
	Supporter,
	Trusted,
	Custom,
	// Compatibility aliases for legacy call sites:
	Porter = Developer,
	PorterChannel = OfficialChannel,
	Bughunter = Supporter,
	Helper = Supporter,
	Donor = Supporter,
};

struct TrustedSource {
	uint64 id = 0;
	QString username;
};

void StartBadges();

[[nodiscard]] BadgeKind BadgeKindFor(not_null<PeerData*> peer);
[[nodiscard]] DocumentId BadgeEmoji(not_null<PeerData*> peer);
[[nodiscard]] QString BadgeCustomText(not_null<PeerData*> peer);
[[nodiscard]] DocumentId BadgeTypeEmoji(const QString &type);
[[nodiscard]] std::optional<std::vector<TrustedSource>> TrustedSources();
[[nodiscard]] bool IsTrustedHash(const QString &sha256);

} // namespace Extera
