#include "extera/extera_utils.h"

#include "extera/extera_config.h"

#include <QtCore/QDateTime>
#include <QtCore/QLocale>
#include <QtCore/QRegularExpression>
#include <QtCore/QTime>
#include <QtCore/QTimeZone>
#include <QtCore/QUrl>
#include <QtCore/QUrlQuery>

#include <cmath>

namespace Extera {
namespace {

[[nodiscard]] QString FormatWithSeconds(QString format) {
	if (format.contains(u"ss"_q)) {
		return format;
	}
	const auto minutes = format.indexOf(u"mm"_q);
	if (minutes < 0) {
		return format;
	}
	format.insert(minutes + 2, u":ss"_q);
	return format;
}

const QRegularExpression &ZalgoPattern() {
	static const auto result = QRegularExpression(
		u"\\p{Mn}{3,}|[\\x{202A}-\\x{202E}\\x{2066}-\\x{2069}"
		"\\x{200E}\\x{200F}\\x{061C}]"_q,
		QRegularExpression::UseUnicodePropertiesOption);
	return result;
}

class MathParser final {
public:
	explicit MathParser(const QString &text) : _text(text) {
	}

	[[nodiscard]] std::optional<double> parse() {
		const auto result = expression();
		skipSpaces();
		if (!result || _position != _text.size()) {
			return std::nullopt;
		}
		return result;
	}

private:
	void skipSpaces() {
		while (_position < _text.size() && _text[_position].isSpace()) {
			++_position;
		}
	}

	[[nodiscard]] bool take(QChar ch) {
		skipSpaces();
		if (_position < _text.size() && _text[_position] == ch) {
			++_position;
			return true;
		}
		return false;
	}

	[[nodiscard]] bool take(const QString &str) {
		skipSpaces();
		if (_text.midRef(_position, str.size()).compare(str, Qt::CaseInsensitive) == 0) {
			_position += str.size();
			return true;
		}
		return false;
	}

	[[nodiscard]] std::optional<double> number() {
		skipSpaces();
		if (_text.midRef(_position, 2).compare(u"0x"_q, Qt::CaseInsensitive) == 0) {
			_position += 2;
			const auto start = _position;
			while (_position < _text.size()) {
				const auto ch = _text[_position];
				if ((ch >= '0' && ch <= '9')
					|| (ch >= 'a' && ch <= 'f')
					|| (ch >= 'A' && ch <= 'F')) {
					++_position;
				} else {
					break;
				}
			}
			if (start == _position) {
				return std::nullopt;
			}
			auto ok = false;
			const auto hexVal = _text.mid(start, _position - start).toULongLong(&ok, 16);
			return ok ? std::make_optional(double(hexVal)) : std::nullopt;
		}

		const auto start = _position;
		while (_position < _text.size()
			&& (_text[_position].isDigit()
				|| _text[_position] == '.'
				|| _text[_position] == ',')) {
			++_position;
		}
		if (start == _position) {
			return std::nullopt;
		}
		auto ok = false;
		auto val = _text.mid(start, _position - start).replace(',', '.').toDouble(&ok);
		if (!ok) {
			return std::nullopt;
		}
		if (_position < _text.size()) {
			const auto ch = _text[_position];
			if (ch == 'k' || ch == 'K' || ch == QChar(0x043A) || ch == QChar(0x041A)) {
				val *= 1000.0;
				++_position;
			} else if (ch == 'm' || ch == 'M' || ch == QChar(0x043C) || ch == QChar(0x041C)) {
				val *= 1000000.0;
				++_position;
			}
		}
		return val;
	}

	[[nodiscard]] std::optional<double> factor() {
		if (take('-')) {
			const auto value = factor();
			return value ? std::make_optional(-*value) : std::nullopt;
		} else if (take('+')) {
			return factor();
		} else if (take('(')) {
			const auto value = expression();
			return (value && take(')')) ? value : std::nullopt;
		} else if (take(u"sqrt"_q) || take(QChar(0x221A))) {
			if (take('(')) {
				const auto value = expression();
				return (value && take(')') && *value >= 0.)
					? std::make_optional(std::sqrt(*value))
					: std::nullopt;
			}
			const auto value = factor();
			return (value && *value >= 0.)
				? std::make_optional(std::sqrt(*value))
				: std::nullopt;
		} else if (take(u"sin"_q)) {
			if (take('(')) {
				const auto val = expression();
				return (val && take(')'))
					? std::make_optional(std::sin(*val * M_PI / 180.0))
					: std::nullopt;
			}
		} else if (take(u"cos"_q)) {
			if (take('(')) {
				const auto val = expression();
				return (val && take(')'))
					? std::make_optional(std::cos(*val * M_PI / 180.0))
					: std::nullopt;
			}
		} else if (take(u"tan"_q)) {
			if (take('(')) {
				const auto val = expression();
				return (val && take(')'))
					? std::make_optional(std::tan(*val * M_PI / 180.0))
					: std::nullopt;
			}
		} else if (take(u"abs"_q)) {
			if (take('(')) {
				const auto val = expression();
				return (val && take(')'))
					? std::make_optional(std::abs(*val))
					: std::nullopt;
			}
		} else if (take(u"round"_q)) {
			if (take('(')) {
				const auto val = expression();
				return (val && take(')'))
					? std::make_optional(std::round(*val))
					: std::nullopt;
			}
		} else if (take(u"min"_q)) {
			if (take('(')) {
				auto best = expression();
				while (best && take(',')) {
					const auto next = expression();
					if (!next) return std::nullopt;
					best = std::min(*best, *next);
				}
				return (best && take(')')) ? best : std::nullopt;
			}
		} else if (take(u"max"_q)) {
			if (take('(')) {
				auto best = expression();
				while (best && take(',')) {
					const auto next = expression();
					if (!next) return std::nullopt;
					best = std::max(*best, *next);
				}
				return (best && take(')')) ? best : std::nullopt;
			}
		} else if (take(u"log"_q)) {
			if (take('(')) {
				const auto val = expression();
				return (val && take(')') && *val > 0.)
					? std::make_optional(std::log10(*val))
					: std::nullopt;
			}
		} else if (take(u"ln"_q)) {
			if (take('(')) {
				const auto val = expression();
				return (val && take(')') && *val > 0.)
					? std::make_optional(std::log(*val))
					: std::nullopt;
			}
		} else if (take(u"pi"_q)) {
			return M_PI;
		} else if (take(u"e"_q)) {
			return M_E;
		}
		return number();
	}

	[[nodiscard]] std::optional<double> power() {
		auto left = factor();
		if (left && take('^')) {
			const auto right = power();
			return right
				? std::make_optional(std::pow(*left, *right))
				: std::nullopt;
		}
		return left;
	}

	[[nodiscard]] std::optional<double> term() {
		auto left = power();
		while (left) {
			if (take('*') || take(QChar(0x00D7))) {
				const auto right = power();
				left = right ? std::make_optional(*left * *right) : std::nullopt;
			} else if (take('/') || take(QChar(0x00F7))) {
				const auto right = power();
				left = (right && *right != 0.)
					? std::make_optional(*left / *right)
					: std::nullopt;
			} else {
				break;
			}
		}
		return left;
	}

	[[nodiscard]] std::optional<double> expression() {
		auto left = term();
		while (left) {
			if (take('+')) {
				const auto right = term();
				if (!right) return std::nullopt;
				if (take('%')) {
					left = std::make_optional(*left * (1.0 + *right / 100.0));
				} else {
					left = std::make_optional(*left + *right);
				}
			} else if (take('-')) {
				const auto right = term();
				if (!right) return std::nullopt;
				if (take('%')) {
					left = std::make_optional(*left * (1.0 - *right / 100.0));
				} else {
					left = std::make_optional(*left - *right);
				}
			} else {
				break;
			}
		}
		return left;
	}

	const QString _text;
	int _position = 0;
};

[[nodiscard]] std::optional<QString> EvaluateUnitConversion(const QString &text) {
	const auto lower = text.toLower().trimmed();
	static const auto kConvRe = QRegularExpression(
		u"^([0-9.,]+)\\s*([a-zA-Z\u0430-\u044f\u00b0/]+)\\s*(?:to|\u0432)\\s*([a-zA-Z\u0430-\u044f\u00b0/]+)$"_q);
	const auto m = kConvRe.match(lower);
	if (m.hasMatch()) {
		auto ok = false;
		const auto val = m.captured(1).replace(',', '.').toDouble(&ok);
		if (!ok) return std::nullopt;
		const auto from = m.captured(2);
		const auto to = m.captured(3);

		if ((from == u"km"_q || from == u"\u043a\u043c"_q)
			&& (to == u"mi"_q || to == u"miles"_q || to == u"\u043c\u0438\u043b\u044f\u0445"_q)) {
			return QString::number(val * 0.621371, 'f', 2) + u" mi"_q;
		} else if ((from == u"mi"_q || from == u"miles"_q || from == u"\u043c\u0438\u043b\u044c"_q)
			&& (to == u"km"_q || to == u"\u043a\u043c"_q)) {
			return QString::number(val * 1.60934, 'f', 2) + u" km"_q;
		} else if ((from == u"kg"_q || from == u"\u043a\u0433"_q)
			&& (to == u"lb"_q || to == u"lbs"_q || to.startsWith(u"\u0444\u0443\u043d\u0442"_q))) {
			return QString::number(val * 2.20462, 'f', 2) + u" lb"_q;
		} else if ((from == u"lb"_q || from == u"lbs"_q)
			&& (to == u"kg"_q || to == u"\u043a\u0433"_q)) {
			return QString::number(val * 0.453592, 'f', 2) + u" kg"_q;
		} else if ((from == u"km/h"_q || from == u"\u043a\u043c/\u0447"_q || from == u"kmh"_q)
			&& (to == u"mph"_q || to.startsWith(u"\u043c\u0438\u043b"_q))) {
			return QString::number(val * 0.621371, 'f', 2) + u" mph"_q;
		} else if (from == u"c"_q && to == u"f"_q) {
			return QString::number(val * 9.0 / 5.0 + 32.0, 'f', 1) + u" \u00b0F"_q;
		} else if (from == u"f"_q && to == u"c"_q) {
			return QString::number((val - 32.0) * 5.0 / 9.0, 'f', 1) + u" \u00b0C"_q;
		}
	}

	static const auto kSingleRe = QRegularExpression(
		u"^([0-9.,]+)\\s*(miles|mile|\u043c\u0438\u043b\u044c|\u043c\u0438\u043b\u0438|\u043c\u0438\u043b\u044f|\u00b0?f|\u00b0?c|min|mins|\u043c\u0438\u043d|\u043c\u0438\u043d\u0443\u0442)$"_q);
	const auto sm = kSingleRe.match(lower);
	if (sm.hasMatch()) {
		auto ok = false;
		const auto val = sm.captured(1).replace(',', '.').toDouble(&ok);
		if (!ok) return std::nullopt;
		const auto unit = sm.captured(2);
		if (unit.startsWith(u"mil"_q) || unit.startsWith(u"\u043c\u0438\u043b"_q)) {
			return QString::number(val * 1.60934, 'f', 2) + u" km"_q;
		} else if (unit.endsWith(u"f"_q)) {
			return QString::number((val - 32.0) * 5.0 / 9.0, 'f', 1) + u" \u00b0C"_q;
		} else if (unit.endsWith(u"c"_q)) {
			return QString::number(val * 9.0 / 5.0 + 32.0, 'f', 1) + u" \u00b0F"_q;
		} else if (unit.startsWith(u"min"_q) || unit.startsWith(u"\u043c\u0438\u043d"_q)) {
			const auto totalMin = int(val);
			const auto h = totalMin / 60;
			const auto rem = totalMin % 60;
			return (h > 0)
				? QString("%1h %2m").arg(h).arg(rem)
				: QString("%1 min").arg(totalMin);
		}
	}

	static const auto kTimeSumRe = QRegularExpression(
		u"^(\\d+)\\s*(?:h|hr|\u0447|\u0447\u0430\u0441[a-z\u0430-\u044f]*)\\s*\\+\\s*(\\d+)\\s*(?:min|mins|\u043c\u0438\u043d|\u043c\u0438\u043d\u0443\u0442[a-z\u0430-\u044f]*)$"_q);
	const auto tm = kTimeSumRe.match(lower);
	if (tm.hasMatch()) {
		const auto h = tm.captured(1).toInt();
		const auto mVal = tm.captured(2).toInt();
		const auto total = h * 60 + mVal;
		return QString("%1 min (%2 h)").arg(total).arg(double(total) / 60.0, 0, 'f', 2);
	}
	return std::nullopt;
}

[[nodiscard]] std::optional<QString> EvaluateCurrency(const QString &text) {
	const auto lower = text.toLower().trimmed();

	static const auto kStarsRe = QRegularExpression(
		u"^(\\d+)\\s*(?:stars|\u0437\u0432[\u0435\u0451]\u0437\u0434[a-z\u0430-\u044f]*)$"_q);
	const auto stm = kStarsRe.match(lower);
	if (stm.hasMatch()) {
		const auto count = stm.captured(1).toLongLong();
		const auto usd = count * 0.02;
		const auto rub = usd * 80.5;
		return QString("$%1 (~%2 \u20BD)").arg(usd, 0, 'f', 2).arg(std::round(rub), 0, 'f', 0);
	}

	static const auto kSimpleSymRe = QRegularExpression(
		u"^([0-9.,]+)\\s*([$\u20ac\u20bd\u00a3])$"_q);
	const auto symMatch = kSimpleSymRe.match(lower);
	if (symMatch.hasMatch()) {
		auto ok = false;
		const auto val = symMatch.captured(1).replace(',', '.').toDouble(&ok);
		if (!ok) return std::nullopt;
		const auto sym = symMatch.captured(2);
		if (sym == u"\u20ac"_q) {
			return QString("$%1 (~%2 \u20BD)").arg(val * 1.09, 0, 'f', 2).arg(std::round(val * 89.5), 0, 'f', 0);
		} else if (sym == u"$"_q) {
			return QString("~%1 \u20ac (~%2 \u20BD)").arg(val * 0.89, 0, 'f', 2).arg(std::round(val * 80.5), 0, 'f', 0);
		} else if (sym == u"\u20bd"_q) {
			return QString("$%1 (~%2 \u20ac)").arg(val / 80.5, 0, 'f', 2).arg(val / 89.5, 0, 'f', 2);
		}
	}

	static const auto kCurrPairRe = QRegularExpression(
		u"^([0-9.,]+)\\s*([k\u043a\u043c\u043c])?\\s*([$\u20ac\u20bd\u00a3]|rub|usd|eur|gram|\u0434\u043e\u043b\u043b\u0430\u0440[a-z\u0430-\u044f]*)\\s*(?:to|\u0432)\\s*([$\u20ac\u20bd\u00a3]|rub|usd|eur|gram|\u0435\u0432\u0440\u043e)$"_q);
	const auto cpm = kCurrPairRe.match(lower);
	if (cpm.hasMatch()) {
		auto ok = false;
		auto val = cpm.captured(1).replace(',', '.').toDouble(&ok);
		if (!ok) return std::nullopt;
		const auto mult = cpm.captured(2);
		if (mult == u"k"_q || mult == u"\u043a"_q) val *= 1000.0;
		else if (mult == u"m"_q || mult == u"\u043c"_q) val *= 1000000.0;

		auto from = cpm.captured(3);
		auto to = cpm.captured(4);
		if (from.startsWith(u"\u0434\u043e\u043b\u043b\u0430\u0440"_q)) from = u"usd"_q;
		if (to == u"\u0435\u0432\u0440\u043e"_q) to = u"eur"_q;

		const auto toUsd = [=](const QString &c) {
			if (c == u"$"_q || c == u"usd"_q) return 1.0;
			if (c == u"\u20ac"_q || c == u"eur"_q) return 1.09;
			if (c == u"\u20bd"_q || c == u"rub"_q) return 0.0124;
			if (c == u"gram"_q) return 0.02;
			return 1.0;
		};

		const auto usdVal = val * toUsd(from);
		const auto res = usdVal / toUsd(to);
		const auto outSym = (to == u"$"_q || to == u"usd"_q) ? u"$"_q
			: (to == u"\u20ac"_q || to == u"eur"_q) ? u"EUR"_q
			: (to == u"gram"_q) ? u"GRAM"_q : to.toUpper();
		return QString("%1 %2").arg(res, 0, 'f', 2).arg(outSym);
	}
	return std::nullopt;
}

[[nodiscard]] std::optional<QString> EvaluateTimeZone(const QString &text) {
	const auto lower = text.toLower().trimmed();

	static const auto kNowInRe = QRegularExpression(
		u"^(?:now\\s+in|\u0441\u0435\u0439\u0447\u0430\u0441\\s+\u0432)\\s+([a-z\u0430-\u044f\\s-]+)$"_q);
	const auto nowMatch = kNowInRe.match(lower);
	if (nowMatch.hasMatch()) {
		const auto city = nowMatch.captured(1).trimmed();
		const auto getOffset = [](const QString &c) -> std::optional<int> {
			if (c == u"new york"_q || c == u"nyc"_q || c.startsWith(u"\u043d\u044c\u044e-\u0439\u043e\u0440\u043a"_q)) return -4;
			if (c == u"tokyo"_q || c == u"\u0442\u043e\u043a\u0438\u043e"_q) return 9;
			if (c == u"london"_q || c.startsWith(u"\u043b\u043e\u043d\u0434\u043e\u043d"_q)) return 1;
			if (c == u"moscow"_q || c.startsWith(u"\u043c\u043e\u0441\u043a\u0432"_q) || c == u"\u043c\u0441\u043a"_q) return 3;
			return std::nullopt;
		};
		if (const auto offset = getOffset(city)) {
			const auto nowUtc = QDateTime::currentDateTimeUtc();
			const auto target = nowUtc.addSecs(*offset * 3600);
			return target.toString(u"hh:mm"_q);
		}
	}

	static const auto kTimeInRe = QRegularExpression(
		u"^(\\d{1,2}(?::\\d{2})?)\\s+(?:in|\u0432)\\s+([a-z\u0430-\u044f\\s-]+)$"_q);
	const auto timeMatch = kTimeInRe.match(lower);
	if (timeMatch.hasMatch()) {
		const auto timeStr = timeMatch.captured(1);
		const auto city = timeMatch.captured(2).trimmed();
		auto time = QTime::fromString(timeStr, (timeStr.contains(':') ? u"h:mm"_q : u"h"_q));
		if (!time.isValid()) return std::nullopt;

		const auto getOffset = [](const QString &c) -> std::optional<int> {
			if (c == u"tokyo"_q || c == u"\u0442\u043e\u043a\u0438\u043e"_q) return 9;
			if (c == u"new york"_q || c.startsWith(u"\u043d\u044c\u044e"_q)) return -4;
			if (c == u"london"_q || c.startsWith(u"\u043b\u043e\u043d\u0434\u043e\u043d"_q)) return 1;
			if (c == u"moscow"_q || c == u"\u043c\u0441\u043a"_q) return 3;
			return std::nullopt;
		};
		if (const auto offset = getOffset(city)) {
			const auto diffSec = (3 - *offset) * 3600;
			const auto msk = time.addSecs(diffSec);
			return QString("%1 (%2 MSK)").arg(time.toString(u"hh:mm"_q)).arg(msk.toString(u"hh:mm"_q));
		}
	}

	static const auto kAmPmRe = QRegularExpression(
		u"^(\\d{1,2}(?::\\d{2})?)\\s*(am|pm)?\\s*(est|edt|utc|gmt|msk)$"_q);
	const auto ampmMatch = kAmPmRe.match(lower);
	if (ampmMatch.hasMatch()) {
		const auto timeStr = ampmMatch.captured(1);
		const auto ampm = ampmMatch.captured(2);
		const auto tz = ampmMatch.captured(3);
		auto parts = timeStr.split(':');
		auto h = parts[0].toInt();
		auto m = parts.size() > 1 ? parts[1].toInt() : 0;
		if (ampm == u"pm"_q && h < 12) h += 12;
		else if (ampm == u"am"_q && h == 12) h = 0;

		const auto getOffset = [](const QString &t) {
			if (t == u"est"_q || t == u"edt"_q) return -4;
			if (t == u"utc"_q || t == u"gmt"_q) return 0;
			if (t == u"msk"_q) return 3;
			return 0;
		};
		const auto targetOffset = getOffset(tz);
		const auto mskH = (h + (3 - targetOffset) + 24) % 24;
		return QString("%1:%2 %3 (%4:%5 MSK)")
			.arg(h, 2, 10, QChar('0'))
			.arg(m, 2, 10, QChar('0'))
			.arg(tz.toUpper())
			.arg(mskH, 2, 10, QChar('0'))
			.arg(m, 2, 10, QChar('0'));
	}
	return std::nullopt;
}

} // namespace

QString FormatTime(const QTime &time) {
	const auto locale = QLocale();
	if (!Bool(u"time_with_seconds"_q)) {
		return locale.toString(time, QLocale::ShortFormat);
	}
	return locale.toString(
		time,
		FormatWithSeconds(locale.timeFormat(QLocale::ShortFormat)));
}

bool HasZalgo(const QString &text) {
	return Bool(u"filter_zalgo"_q) && ZalgoPattern().match(text).hasMatch();
}

QString FilterZalgo(QString text) {
	if (HasZalgo(text)) {
		text.remove(ZalgoPattern());
	}
	return text;
}

void FilterZalgo(TextWithEntities &textWithEntities) {
	if (!HasZalgo(textWithEntities.text)) {
		return;
	}
	if (textWithEntities.entities.empty()) {
		textWithEntities.text = FilterZalgo(std::move(textWithEntities.text));
		return;
	}
	const auto &pattern = ZalgoPattern();
	auto match = pattern.match(textWithEntities.text);
	while (match.hasMatch()) {
		const auto start = match.capturedStart();
		const auto len = match.capturedLength();
		textWithEntities.text.remove(start, len);
		for (auto &entity : textWithEntities.entities) {
			if (entity.offset() >= start + len) {
				entity = EntityInText(
					entity.type(),
					entity.offset() - len,
					entity.length(),
					entity.data());
			} else if (entity.offset() >= start) {
				entity = EntityInText(
					entity.type(),
					start,
					std::max(0, entity.length() - (start + len - entity.offset())),
					entity.data());
			} else if (entity.offset() + entity.length() > start) {
				entity = EntityInText(
					entity.type(),
					entity.offset(),
					std::max(0, entity.length() - len),
					entity.data());
			}
		}
		match = pattern.match(textWithEntities.text, start);
	}
}

std::optional<QString> InlineMathValue(const QString &text) {
	if (!Bool(u"inline_math"_q) || !text.endsWith('=')) {
		return std::nullopt;
	}
	const auto body = text.left(text.size() - 1);
	auto start = body.size();
	while (start > 0) {
		const auto ch = body[start - 1];
		if (ch == '\n' || ch == '\r') {
			break;
		}
		--start;
	}
	auto query = body.mid(start).trimmed();
	if (query.isEmpty()) {
		return std::nullopt;
	}

	static const auto kHexRe = QRegularExpression(
		u"^hex\\(\\s*(\\d+)\\s*\\)$"_q,
		QRegularExpression::CaseInsensitiveOption);
	const auto hm = kHexRe.match(query);
	if (hm.hasMatch()) {
		const auto val = hm.captured(1).toULongLong();
		return QString("0x%1").arg(val, 0, 16);
	}

	static const auto kDecRe = QRegularExpression(
		u"^dec\\(\\s*([0-9a-fA-F]+)\\s*,\\s*(\\d+)\\s*\\)$"_q);
	const auto dm = kDecRe.match(query);
	if (dm.hasMatch()) {
		auto ok = false;
		const auto radix = dm.captured(2).toInt();
		const auto val = dm.captured(1).toULongLong(&ok, radix);
		if (ok) {
			return QString::number(val);
		}
	}

	if (const auto tzVal = EvaluateTimeZone(query)) {
		return tzVal;
	}

	if (const auto currVal = EvaluateCurrency(query)) {
		return currVal;
	}

	if (const auto unitVal = EvaluateUnitConversion(query)) {
		return unitVal;
	}

	static const auto kPctOfRe = QRegularExpression(
		u"^([0-9.,]+)\\s*%\\s*(?:of|\u043e\u0442)\\s*([0-9.,]+)$"_q,
		QRegularExpression::CaseInsensitiveOption);
	const auto pm = kPctOfRe.match(query);
	if (pm.hasMatch()) {
		auto ok1 = false;
		auto ok2 = false;
		const auto pct = pm.captured(1).replace(',', '.').toDouble(&ok1);
		const auto baseVal = pm.captured(2).replace(',', '.').toDouble(&ok2);
		if (ok1 && ok2) {
			return QString::number((pct / 100.0) * baseVal, 'g', 15);
		}
	}

	auto mathExpr = query;
	mathExpr.replace(QChar(0x00D7), '*');
	mathExpr.replace(QChar(0x00F7), '/');

	const auto value = MathParser(mathExpr).parse();
	if (!value || !std::isfinite(*value)) {
		return std::nullopt;
	}
	const auto rounded = (std::abs(*value) < 1e9)
		? (std::round(*value * 1e9) / 1e9)
		: *value;
	return QString::number(rounded, 'g', 15);
}

std::optional<QString> InlineMathResult(const QString &text) {
	if (!text.endsWith(u"= "_q)) {
		return std::nullopt;
	}
	const auto withEquals = text.left(text.size() - 1);
	if (const auto value = InlineMathValue(withEquals)) {
		return withEquals + *value + ' ';
	}
	return std::nullopt;
}

QString CleanUrl(const QString &urlString) {
	const auto url = QUrl(urlString);
	if (!url.isValid() || !url.hasQuery()) {
		return urlString;
	}
	const auto query = QUrlQuery(url.query());
	const auto items = query.queryItems();
	auto cleaned = QUrlQuery();
	for (const auto &[key, val] : items) {
		const auto lower = key.toLower();
		if (lower.startsWith(u"utm_"_q)
			|| lower == u"si"_q
			|| lower == u"igshid"_q
			|| lower == u"fbclid"_q
			|| lower == u"gclid"_q
			|| lower == u"ref"_q
			|| lower == u"mc_cid"_q
			|| lower == u"mc_eid"_q) {
			continue;
		}
		cleaned.addQueryItem(key, val);
	}
	auto result = url;
	if (cleaned.isEmpty()) {
		result.setQuery(QString());
	} else {
		result.setQuery(cleaned);
	}
	return result.toString();
}

QString CleanTextUrls(QString text) {
	static const auto urlRe = QRegularExpression(
		u"https?://[^\\s]+"_q,
		QRegularExpression::CaseInsensitiveOption);
	auto i = urlRe.globalMatch(text);
	auto offset = 0;
	while (i.hasNext()) {
		const auto match = i.next();
		const auto original = match.captured(0);
		const auto cleaned = CleanUrl(original);
		if (cleaned != original) {
			text.replace(match.capturedStart(0) + offset, original.size(), cleaned);
			offset += cleaned.size() - original.size();
		}
	}
	return text;
}

} // namespace Extera
