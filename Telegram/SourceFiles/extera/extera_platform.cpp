#include "extera/extera_platform.h"

#include <QtCore/QFile>

namespace Extera::Platform {

SenderPlatform DetectFromBytes(const QByteArray &bytes) {
	if (bytes.size() < 16) {
		return SenderPlatform::Unknown;
	}

	const auto sample = bytes.mid(0, std::min(bytes.size(), qsizetype(8192)));
	const auto lower = sample.toLower();

	if (bytes.startsWith("\xFF\xD8")) {
		if (sample.contains("Apple") || sample.contains("iPhone") || sample.contains("iPad")) {
			return SenderPlatform::iOS;
		}
		if (sample.contains("Samsung") || sample.contains("Xiaomi") || sample.contains("Pixel") || sample.contains("Android")) {
			return SenderPlatform::Android;
		}
		if (sample.contains("Adobe") || sample.contains("Photoshop") || sample.contains("GIMP")) {
			return SenderPlatform::Desktop;
		}
	} else if (bytes.startsWith("OggS")) {
		if (lower.contains("coreaudio") || lower.contains("avfoundation") || lower.contains("apple")) {
			return SenderPlatform::iOS;
		}
		if (lower.contains("audiorecord") || lower.contains("telegram-android") || lower.contains("android")) {
			return SenderPlatform::Android;
		}
		if (lower.contains("tdesktop") || lower.contains("telegram desktop")) {
			return SenderPlatform::Desktop;
		}
	}

	return SenderPlatform::Unknown;
}

SenderPlatform DetectFromFile(const QString &filePath) {
	auto file = QFile(filePath);
	if (!file.open(QIODevice::ReadOnly)) {
		return SenderPlatform::Unknown;
	}
	const auto bytes = file.read(8192);
	return DetectFromBytes(bytes);
}

QString FormatPlatform(SenderPlatform platform) {
	switch (platform) {
	case SenderPlatform::Android: return u"Android"_q;
	case SenderPlatform::iOS: return u"iOS"_q;
	case SenderPlatform::Desktop: return u"Desktop"_q;
	case SenderPlatform::Web: return u"Web"_q;
	case SenderPlatform::Unknown: return QString();
	}
	return QString();
}

} // namespace Extera::Platform
