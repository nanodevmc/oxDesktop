#pragma once

class History;
struct TextWithEntities;

namespace Extera {

void ConvertPremiumEmojiForSending(
	TextWithEntities &text,
	not_null<History*> history);
void ApplyLocalPremiumEmoji(TextWithEntities &text);

} // namespace Extera
