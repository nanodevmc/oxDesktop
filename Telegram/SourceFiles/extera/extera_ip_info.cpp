#include "extera/extera_ip_info.h"

#include "ui/layers/generic_box.h"
#include "ui/widgets/labels.h"
#include "ui/text/text_utilities.h"
#include "styles/style_boxes.h"
#include "styles/style_layers.h"
#include "styles/style_settings.h"
#include "window/window_session_controller.h"
#include "core/application.h"

#include <QtCore/QRegularExpression>
#include <QtCore/QJsonDocument>
#include <QtCore/QJsonObject>
#include <QtNetwork/QNetworkAccessManager>
#include <QtNetwork/QNetworkReply>
#include <QtNetwork/QNetworkRequest>

namespace Extera::IpInfo {
namespace {

QString CountryFlag(const QString &code) {
	if (code.size() != 2) {
		return QString();
	}
	const auto c1 = code[0].toUpper().toLatin1();
	const auto c2 = code[1].toUpper().toLatin1();
	if (c1 < 'A' || c1 > 'Z' || c2 < 'A' || c2 > 'Z') {
		return QString();
	}
	const uint32 u1 = 0x1F1E6 + (c1 - 'A');
	const uint32 u2 = 0x1F1E6 + (c2 - 'A');
	return QString::fromUcs4(&u1, 1) + QString::fromUcs4(&u2, 1);
}

} // namespace

QString ExtractIp(const QString &text) {
	static const auto kIpv4Re = QRegularExpression(
		u"\\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\\.){3}"
		u"(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\\b"_q);
	const auto match = kIpv4Re.match(text);
	if (match.hasMatch()) {
		return match.captured(0);
	}
	return text.trimmed();
}

void Inspect(
		not_null<Window::SessionController*> controller,
		const QString &ipOrHost) {
	const auto cleanIp = ExtractIp(ipOrHost);
	if (cleanIp.isEmpty()) {
		return;
	}

	static auto *manager = new QNetworkAccessManager(qApp);
	const auto request = QNetworkRequest(QUrl(
		u"https://ipwho.is/%1"_q.arg(cleanIp)));
	const auto reply = manager->get(request);

	QObject::connect(reply, &QNetworkReply::finished, [=] {
		reply->deleteLater();
		if (reply->error() != QNetworkReply::NoError) {
			controller->show(Box([=](not_null<Ui::GenericBox*> box) {
				box->setTitle(rpl::single(u"IP: "_q + cleanIp));
				box->addRow(object_ptr<Ui::FlatLabel>(
					box,
					u"Failed to fetch GeoIP information."_q,
					st::boxLabel));
				box->addButton(rpl::single(u"Close"_q), [=] { box->closeBox(); });
			}));
			return;
		}

		const auto bytes = reply->readAll();
		const auto doc = QJsonDocument::fromJson(bytes);
		if (!doc.isObject()) {
			return;
		}
		const auto obj = doc.object();
		const auto success = obj.value(u"success"_q).toBool(true);
		if (!success) {
			const auto msg = obj.value(u"message"_q).toString(u"IP lookup failed"_q);
			controller->show(Box([=](not_null<Ui::GenericBox*> box) {
				box->setTitle(rpl::single(u"IP: "_q + cleanIp));
				box->addRow(object_ptr<Ui::FlatLabel>(
					box,
					msg,
					st::boxLabel));
				box->addButton(rpl::single(u"Close"_q), [=] { box->closeBox(); });
			}));
			return;
		}

		const auto country = obj.value(u"country"_q).toString();
		const auto code = obj.value(u"country_code"_q).toString();
		const auto city = obj.value(u"city"_q).toString();
		const auto region = obj.value(u"region"_q).toString();
		const auto flag = CountryFlag(code);

		const auto connObj = obj.value(u"connection"_q).toObject();
		const auto isp = connObj.value(u"isp"_q).toString();
		const auto asn = connObj.value(u"asn"_q).toVariant().toString();
		const auto org = connObj.value(u"org"_q).toString();

		const auto tzObj = obj.value(u"timezone"_q).toObject();
		const auto tzId = tzObj.value(u"id"_q).toString();

		controller->show(Box([=](not_null<Ui::GenericBox*> box) {
			const auto header = flag.isEmpty()
				? QString("%1 (%2)").arg(country).arg(code)
				: QString("%1 %2 (%3)").arg(flag).arg(country).arg(code);
			box->setTitle(rpl::single(header));

			auto details = QString();
			details.append(u"IP: "_q + cleanIp + '\n');
			if (!city.isEmpty() || !region.isEmpty()) {
				details.append(u"Location: "_q + city + u", "_q + region + '\n');
			}
			if (!isp.isEmpty()) {
				details.append(u"ISP: "_q + isp + '\n');
			}
			if (!org.isEmpty() && org != isp) {
				details.append(u"Organization: "_q + org + '\n');
			}
			if (!asn.isEmpty()) {
				details.append(u"ASN: AS"_q + asn + '\n');
			}
			if (!tzId.isEmpty()) {
				details.append(u"Timezone: "_q + tzId + '\n');
			}

			const auto label = box->addRow(object_ptr<Ui::FlatLabel>(
				box,
				details.trimmed(),
				st::boxLabel));
			label->setSelectable(true);

			box->addButton(rpl::single(u"Close"_q), [=] { box->closeBox(); });
		}));
	});
}

} // namespace Extera::IpInfo
