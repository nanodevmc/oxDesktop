#pragma once

#include "storage/storage_shared_media.h"

namespace Extera::SearchFilter {

enum class FilterType {
	All,
	Photo,
	Video,
	File,
	Music,
	Link,
	Voice,
};

[[nodiscard]] Storage::SharedMediaType ToSharedMedia(FilterType type);
[[nodiscard]] FilterType FromSharedMedia(Storage::SharedMediaType type);
[[nodiscard]] QString Title(FilterType type);
[[nodiscard]] std::vector<FilterType> AvailableFilters();

} // namespace Extera::SearchFilter
