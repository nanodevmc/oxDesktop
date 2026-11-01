#include "extera/extera_search_filter.h"

#include "lang/lang_keys.h"

namespace Extera::SearchFilter {

Storage::SharedMediaType ToSharedMedia(FilterType type) {
	switch (type) {
	case FilterType::Photo: return Storage::SharedMediaType::Photo;
	case FilterType::Video: return Storage::SharedMediaType::Video;
	case FilterType::File: return Storage::SharedMediaType::File;
	case FilterType::Music: return Storage::SharedMediaType::MusicFile;
	case FilterType::Link: return Storage::SharedMediaType::Link;
	case FilterType::Voice: return Storage::SharedMediaType::RoundVoiceFile;
	case FilterType::All:
	default:
		return Storage::SharedMediaType::kCount;
	}
}

FilterType FromSharedMedia(Storage::SharedMediaType type) {
	switch (type) {
	case Storage::SharedMediaType::Photo: return FilterType::Photo;
	case Storage::SharedMediaType::Video: return FilterType::Video;
	case Storage::SharedMediaType::File: return FilterType::File;
	case Storage::SharedMediaType::MusicFile: return FilterType::Music;
	case Storage::SharedMediaType::Link: return FilterType::Link;
	case Storage::SharedMediaType::VoiceFile:
	case Storage::SharedMediaType::RoundVoiceFile: return FilterType::Voice;
	default:
		return FilterType::All;
	}
}

QString Title(FilterType type) {
	switch (type) {
	case FilterType::Photo: return tr::lng_media_type_photos(tr::now);
	case FilterType::Video: return tr::lng_media_type_videos(tr::now);
	case FilterType::File: return tr::lng_media_type_files(tr::now);
	case FilterType::Music: return tr::lng_media_type_songs(tr::now);
	case FilterType::Link: return tr::lng_media_type_links(tr::now);
	case FilterType::Voice: return tr::lng_media_type_audios(tr::now);
	case FilterType::All:
	default:
		return tr::lng_filters_all_short(tr::now);
	}
}

std::vector<FilterType> AvailableFilters() {
	return {
		FilterType::All,
		FilterType::Photo,
		FilterType::Video,
		FilterType::File,
		FilterType::Music,
		FilterType::Link,
		FilterType::Voice,
	};
}

} // namespace Extera::SearchFilter
