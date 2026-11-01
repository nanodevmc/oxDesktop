#pragma once

#include <QtCore/QString>
#include <vector>

namespace Window {
class SessionController;
} // namespace Window

namespace Extera::Lyrics {

struct Line {
	int timestampMs = 0;
	QString text;
};

struct Result {
	bool synced = false;
	std::vector<Line> lines;
	QString plain;
};

void Fetch(
	const QString &artist,
	const QString &title,
	int durationSec,
	Fn<void(Result)> callback);

void ShowBox(
	not_null<Window::SessionController*> controller,
	const QString &artist,
	const QString &title,
	int durationSec);

} // namespace Extera::Lyrics
