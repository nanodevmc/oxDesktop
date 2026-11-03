#include "extera/extera_lyrics.h"

#include "ui/layers/generic_box.h"
#include "ui/widgets/labels.h"
#include "ui/text/text_utilities.h"
#include "styles/style_boxes.h"
#include "window/window_session_controller.h"
#include "core/application.h"

#include <QtCore/QUrl>
#include <QtCore/QUrlQuery>
#include <QtCore/QRegularExpression>
#include <QtCore/QJsonDocument>
#include <QtCore/QJsonObject>
#include <QtNetwork/QNetworkAccessManager>
#include <QtNetwork/QNetworkReply>
#include <QtNetwork/QNetworkRequest>

namespace Extera::Lyrics {
namespace {

std::vector<Line> ParseLrc(const QString &lrc) {
	static const auto kLineRe = QRegularExpression(
		u"^\\[(\\d{1,2}):(\\d{2})(?:[.:](\\d{2,3}))?\\](.*)$"_q);
	auto result = std::vector<Line>();
	for (const auto &rawLine : lrc.split('\n')) {
		const auto trimmed = rawLine.trimmed();
		const auto m = kLineRe.match(trimmed);
		if (!m.hasMatch()) {
			continue;
		}
		const auto min = m.captured(1).toInt();
		const auto sec = m.captured(2).toInt();
		auto frac = m.captured(3);
		if (frac.size() == 2) {
			frac.append('0');
		}
		const auto ms = frac.toInt();
		const auto text = m.captured(4).trimmed();
		result.push_back({
			.timestampMs = (min * 60 + sec) * 1000 + ms,
			.text = text,
		});
	}
	return result;
}

} // namespace

void Fetch(
		const QString &artist,
		const QString &title,
		int durationSec,
		Fn<void(Result)> callback) {
	if (artist.isEmpty() && title.isEmpty()) {
		callback(Result{});
		return;
	}

	static auto *manager = new QNetworkAccessManager(qApp);

	auto url = QUrl(u"https://lrclib.net/api/get"_q);
	auto query = QUrlQuery();
	query.addQueryItem(u"artist_name"_q, artist);
	query.addQueryItem(u"track_name"_q, title);
	if (durationSec > 0) {
		query.addQueryItem(u"duration"_q, QString::number(durationSec));
	}
	url.setQuery(query);

	auto request = QNetworkRequest(url);
	request.setRawHeader("User-Agent", "oxDesktop-Lyrics/1.0");

	const auto reply = manager->get(request);
	QObject::connect(reply, &QNetworkReply::finished, [=] {
		reply->deleteLater();
		if (reply->error() != QNetworkReply::NoError) {
			callback(Result{});
			return;
		}

		const auto doc = QJsonDocument::fromJson(reply->readAll());
		if (!doc.isObject()) {
			callback(Result{});
			return;
		}
		const auto obj = doc.object();
		const auto synced = obj.value(u"syncedLyrics"_q).toString();
		const auto plain = obj.value(u"plainLyrics"_q).toString();

		if (!synced.isEmpty()) {
			auto lines = ParseLrc(synced);
			callback(Result{
				.synced = true,
				.lines = std::move(lines),
				.plain = plain,
			});
		} else if (!plain.isEmpty()) {
			callback(Result{
				.synced = false,
				.lines = {},
				.plain = plain,
			});
		} else {
			callback(Result{});
		}
	});
}

void ShowBox(
		not_null<Window::SessionController*> controller,
		const QString &artist,
		const QString &title,
		int durationSec) {
	Fetch(artist, title, durationSec, [=](Result result) {
		controller->show(Box([=](not_null<Ui::GenericBox*> box) {
			const auto header = !artist.isEmpty()
				? QString("%1 — %2").arg(artist).arg(title)
				: title;
			box->setTitle(rpl::single(header));
			box->setWidth(st::boxWideWidth * 5 / 4);

			auto contentText = QString();
			if (result.synced && !result.lines.empty()) {
				for (const auto &line : result.lines) {
					if (!line.text.isEmpty()) {
						contentText.append(line.text + '\n');
					}
				}
			} else if (!result.plain.isEmpty()) {
				contentText = result.plain;
			} else {
				contentText = u"Lyrics not found."_q;
			}

			const auto label = box->addRow(object_ptr<Ui::FlatLabel>(
				box,
				contentText.trimmed(),
				st::boxLabel));
			label->setSelectable(true);

			box->addButton(rpl::single(u"Close"_q), [=] { box->closeBox(); });
		}));
	});
}

} // namespace Extera::Lyrics
