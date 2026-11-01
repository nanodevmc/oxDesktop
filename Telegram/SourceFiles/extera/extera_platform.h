#pragma once

#include <QtCore/QString>
#include <QtCore/QByteArray>

namespace Extera::Platform {

enum class SenderPlatform {
	Unknown,
	Android,
	iOS,
	Desktop,
	Web,
};

[[nodiscard]] SenderPlatform DetectFromBytes(const QByteArray &bytes);
[[nodiscard]] SenderPlatform DetectFromFile(const QString &filePath);
[[nodiscard]] QString FormatPlatform(SenderPlatform platform);

} // namespace Extera::Platform
