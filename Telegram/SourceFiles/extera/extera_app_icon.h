#pragma once

namespace Extera::AppIcon {

struct Variant {
	QString id;
	QString title;
	QColor from;
	QColor to;
	QColor fg;
	QString glyph;
};

[[nodiscard]] std::vector<Variant> Variants();
[[nodiscard]] QImage Render(int size, const QString &id, bool square);
[[nodiscard]] QImage Current(int size);
void ApplyToShortcuts();
void Apply();

} // namespace Extera::AppIcon
