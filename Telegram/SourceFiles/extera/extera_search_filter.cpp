#include "extera/extera_search_filter.h"

#include "lang/lang_keys.h"
#include "ui/widgets/popup_menu.h"
#include "styles/style_widgets.h"

namespace Extera::SearchFilter {

Api::SearchFilter ToApiFilter(FilterType type) {
	switch (type) {
	case FilterType::Photo: return Api::SearchFilter::Photo;
	case FilterType::Video: return Api::SearchFilter::Video;
	case FilterType::File: return Api::SearchFilter::Document;
	case FilterType::Music: return Api::SearchFilter::Music;
	case FilterType::Link: return Api::SearchFilter::Url;
	case FilterType::Voice: return Api::SearchFilter::Voice;
	case FilterType::RoundVideo: return Api::SearchFilter::RoundVideo;
	case FilterType::GIF: return Api::SearchFilter::Gif;
	case FilterType::Pinned: return Api::SearchFilter::Pinned;
	case FilterType::All:
	default:
		return Api::SearchFilter::NoFilter;
	}
}

Storage::SharedMediaType ToSharedMedia(FilterType type) {
	switch (type) {
	case FilterType::Photo: return Storage::SharedMediaType::Photo;
	case FilterType::Video: return Storage::SharedMediaType::Video;
	case FilterType::File: return Storage::SharedMediaType::File;
	case FilterType::Music: return Storage::SharedMediaType::MusicFile;
	case FilterType::Link: return Storage::SharedMediaType::Link;
	case FilterType::Voice: return Storage::SharedMediaType::RoundVoiceFile;
	case FilterType::RoundVideo: return Storage::SharedMediaType::RoundFile;
	case FilterType::GIF: return Storage::SharedMediaType::GIF;
	case FilterType::Pinned: return Storage::SharedMediaType::Pinned;
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
	case Storage::SharedMediaType::VoiceFile: return FilterType::Voice;
	case Storage::SharedMediaType::RoundVoiceFile: return FilterType::Voice;
	case Storage::SharedMediaType::RoundFile: return FilterType::RoundVideo;
	case Storage::SharedMediaType::GIF: return FilterType::GIF;
	case Storage::SharedMediaType::Pinned: return FilterType::Pinned;
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
	case FilterType::RoundVideo: return u"Video Messages"_q;
	case FilterType::GIF: return u"GIFs"_q;
	case FilterType::Pinned: return tr::lng_admin_log_filter_messages_pinned(tr::now);
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
		FilterType::RoundVideo,
		FilterType::GIF,
		FilterType::Pinned,
	};
}

void ShowMediaFilterMenu(
		not_null<QWidget*> parent,
	FilterType current,
	Fn<void(FilterType selected)> callback) {
	const auto menu = Ui::CreateChild<Ui::PopupMenu>(
		parent.get(),
		st::defaultPopupMenu);
	for (const auto type : AvailableFilters()) {
		auto title = Title(type);
		if (type == current) {
			title = QString::fromUtf8("✓ ") + title;
		}
		menu->addAction(title, [=] {
			callback(type);
		});
	}
	menu->popup(QCursor::pos());
}

} // namespace Extera::SearchFilter
