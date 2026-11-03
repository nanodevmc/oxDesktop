#pragma once

#include "api/api_messages_search.h"
#include "storage/storage_shared_media.h"

namespace Ui {
class PopupMenu;
} // namespace Ui

namespace Extera::SearchFilter {

enum class FilterType {
	All,
	Photo,
	Video,
	File,
	Music,
	Link,
	Voice,
	RoundVideo,
	GIF,
	Pinned,
};

[[nodiscard]] Api::SearchFilter ToApiFilter(FilterType type);
[[nodiscard]] Storage::SharedMediaType ToSharedMedia(FilterType type);
[[nodiscard]] FilterType FromSharedMedia(Storage::SharedMediaType type);
[[nodiscard]] QString Title(FilterType type);
[[nodiscard]] std::vector<FilterType> AvailableFilters();

void ShowMediaFilterMenu(
	not_null<QWidget*> parent,
	FilterType current,
	Fn<void(FilterType selected)> callback);

} // namespace Extera::SearchFilter
