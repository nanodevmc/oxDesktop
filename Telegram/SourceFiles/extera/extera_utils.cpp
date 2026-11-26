#include "extera/extera_utils.h"

#include "extera/extera_config.h"

#include "ui/text/text_entity.h"

#include <QtCore/QDate>
#include <QtCore/QDateTime>
#include <QtCore/QFile>
#include <QtCore/QJsonDocument>
#include <QtCore/QJsonObject>
#include <QtCore/QLocale>
#include <QtCore/QRegularExpression>
#include <QtCore/QTime>
#include <QtCore/QTimeZone>
#include <QtCore/QUrl>
#include <QtCore/QUrlQuery>

#include <cmath>
#include <map>
#include <utility>

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
		if (QStringView(_text).mid(_position, str.size()).compare(str, Qt::CaseInsensitive) == 0) {
			_position += str.size();
			return true;
		}
		return false;
	}

	[[nodiscard]] std::optional<double> number() {
		skipSpaces();
		if (QStringView(_text).mid(_position, 2).compare(u"0x"_q, Qt::CaseInsensitive) == 0) {
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

	[[nodiscard]] static std::optional<char> FromSuperscript(QChar ch) {
		const auto u = ch.unicode();
		if (u == 0x2070) return '0';
		if (u == 0x00B9) return '1';
		if (u == 0x00B2) return '2';
		if (u == 0x00B3) return '3';
		if (u >= 0x2074 && u <= 0x2079) return char('0' + (u - 0x2070));
		if (u == 0x207A) return '+';
		if (u == 0x207B) return '-';
		if (u == 0x207D) return '(';
		if (u == 0x207E) return ')';
		return std::nullopt;
	}

	[[nodiscard]] std::optional<double> superscriptPower() {
		skipSpaces();
		if (_position >= _text.size() || !FromSuperscript(_text[_position])) {
			return std::nullopt;
		}
		QString subExpr;
		while (_position < _text.size()) {
			if (const auto ch = FromSuperscript(_text[_position])) {
				subExpr.append(QChar(*ch));
				++_position;
			} else {
				break;
			}
		}
		return MathParser(subExpr).parse();
	}

	[[nodiscard]] std::optional<double> power() {
		auto left = factor();
		if (!left) {
			return std::nullopt;
		}
		if (take('^')) {
			const auto right = power();
			return right
				? std::make_optional(std::pow(*left, *right))
				: std::nullopt;
		} else if (const auto superExp = superscriptPower()) {
			auto res = std::pow(*left, *superExp);
			if (take('^')) {
				const auto right = power();
				return right
					? std::make_optional(std::pow(res, *right))
					: std::nullopt;
			}
			return res;
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

struct CurrencyEntry {
	QString code;
	QString outputTag;
	double perUsd = 1.0;
	int exp = 2;
};

struct CurrencyDb {
	std::map<QString, CurrencyEntry> byCode;
	std::map<QString, QString> aliases;
};

[[nodiscard]] const CurrencyDb &GetCurrencyDb() {
	static const auto db = [] {
		CurrencyDb result;
		const auto addEntry = [&](
				const QString &code,
				const QString &outputTag,
				double perUsd,
				int exp) {
			if (perUsd <= 0.0) {
				return;
			}
			const auto upper = code.toUpper();
			result.byCode[upper] = CurrencyEntry{
				.code = upper,
				.outputTag = outputTag,
				.perUsd = perUsd,
				.exp = exp,
			};
			result.aliases[code.toLower()] = upper;
		};

		QFile file(u":/extera/currencies.json"_q);
		if (file.open(QIODevice::ReadOnly)) {
			const auto doc = QJsonDocument::fromJson(file.readAll());
			if (doc.isObject()) {
				const auto obj = doc.object();
				for (auto it = obj.begin(); it != obj.end(); ++it) {
					if (!it.value().isObject()) {
						continue;
					}
					const auto item = it.value().toObject();
					const auto code = item.value(u"code"_q).toString(it.key()).toUpper();
					const auto exp = item.value(u"exp"_q).toInt(2);
					const auto minVal = item.value(u"min_amount"_q);
					auto ok = false;
					const auto minAmount = minVal.isString()
						? minVal.toString().toDouble(&ok)
						: minVal.toDouble();
					if (minVal.isDouble()) {
						ok = true;
					}
					if (!ok || minAmount <= 0.0) {
						continue;
					}
					const auto perUsd = minAmount / std::pow(10.0, exp);
					const auto native = item.value(u"native"_q).toString();
					const auto symbol = item.value(u"symbol"_q).toString(code);
					const auto outputTag = (code == u"USD"_q)
						? u"$"_q
						: (code == u"EUR"_q)
							? u"EUR"_q
							: code;
					addEntry(code, outputTag, perUsd, exp);

					const auto titleLower = item.value(u"title"_q).toString().toLower();
					if (!titleLower.isEmpty()) {
						result.aliases.try_emplace(titleLower, code);
					}
					if (!symbol.isEmpty()
							&& symbol != u"$"_q
							&& symbol != u"kr"_q) {
						result.aliases.try_emplace(symbol.toLower(), code);
					}
					if (!native.isEmpty()
							&& native != u"$"_q
							&& native != u"kr"_q
							&& native != u"\u00a3"_q) {
						result.aliases.try_emplace(native.toLower(), code);
					}
				}
			}
		}

		if (result.byCode.empty()) {
			addEntry(u"USD"_q, u"$"_q, 1.0, 2);
			addEntry(u"EUR"_q, u"EUR"_q, 0.92, 2);
			addEntry(u"RUB"_q, u"RUB"_q, 89.22, 2);
			addEntry(u"GBP"_q, u"GBP"_q, 0.78, 2);
		}
		addEntry(u"GRAM"_q, u"GRAM"_q, 50.0, 2);

		const std::pair<const char*, const char*> kExtraAliases[] = {
			{ "$", "USD" },
			{ "\xe2\x82\xac", "EUR" },
			{ "\xe2\x82\xbd", "RUB" },
			{ "\xc2\xa3", "GBP" },
			{ "\xe2\x82\xb4", "UAH" },
			{ "\xe2\x82\xb8", "KZT" },
			{ "\xe2\x82\xba", "TRY" },
			{ "\xe2\x82\xb9", "INR" },
			{ "\xe2\x82\xa9", "KRW" },
			{ "\xe2\x82\xab", "VND" },
			{ "\xe2\x82\xaa", "ILS" },
			{ "\xe0\xb8\xbf", "THB" },
			{ "\xe2\x82\xb1", "PHP" },
			{ "\xc2\xa5", "JPY" },
			{ "\xef\xbf\xa5", "JPY" },
			{ "z\xc5\x82", "PLN" },
			{ "\xd0\xb4\xd0\xbe\xd0\xbb\xd0\xbb\xd0\xb0\xd1\x80", "USD" },
			{ "\xd0\xb4\xd0\xbe\xd0\xbb\xd0\xbb\xd0\xb0\xd1\x80\xd0\xb0", "USD" },
			{ "\xd0\xb4\xd0\xbe\xd0\xbb\xd0\xbb\xd0\xb0\xd1\x80\xd0\xbe\xd0\xb2", "USD" },
			{ "\xd0\xb4\xd0\xbe\xd0\xbb\xd0\xbb\xd0\xb0\xd1\x80\xd1\x8b", "USD" },
			{ "dollar", "USD" },
			{ "dollars", "USD" },
			{ "\xd0\xb5\xd0\xb2\xd1\x80\xd0\xbe", "EUR" },
			{ "euro", "EUR" },
			{ "euros", "EUR" },
			{ "\xd1\x80\xd1\x83\xd0\xb1", "RUB" },
			{ "\xd1\x80\xd1\x83\xd0\xb1\xd0\xbb\xd1\x8c", "RUB" },
			{ "\xd1\x80\xd1\x83\xd0\xb1\xd0\xbb\xd1\x8f", "RUB" },
			{ "\xd1\x80\xd1\x83\xd0\xb1\xd0\xbb\xd0\xb5\xd0\xb9", "RUB" },
			{ "\xd1\x80\xd1\x83\xd0\xb1\xd0\xbb\xd0\xb8", "RUB" },
			{ "\xd1\x84\xd1\x83\xd0\xbd\xd1\x82", "GBP" },
			{ "\xd1\x84\xd1\x83\xd0\xbd\xd1\x82\xd0\xb0", "GBP" },
			{ "\xd1\x84\xd1\x83\xd0\xbd\xd1\x82\xd0\xbe\xd0\xb2", "GBP" },
			{ "pound", "GBP" },
			{ "pounds", "GBP" },
			{ "\xd0\xb3\xd1\x80\xd0\xb8\xd0\xb2\xd0\xbd\xd0\xb0", "UAH" },
			{ "\xd0\xb3\xd1\x80\xd0\xb8\xd0\xb2\xd0\xb5\xd0\xbd", "UAH" },
			{ "\xd0\xb3\xd1\x80\xd0\xb8\xd0\xb2\xd0\xbd\xd1\x8b", "UAH" },
			{ "\xd1\x82\xd0\xb5\xd0\xbd\xd0\xb3\xd0\xb5", "KZT" },
			{ "\xd0\xbb\xd0\xb8\xd1\x80", "TRY" },
			{ "\xd0\xbb\xd0\xb8\xd1\x80\xd0\xb0", "TRY" },
			{ "\xd0\xbb\xd0\xb8\xd1\x80\xd1\x8b", "TRY" },
			{ "\xd1\x8e\xd0\xb0\xd0\xbd\xd1\x8c", "CNY" },
			{ "\xd1\x8e\xd0\xb0\xd0\xbd\xd0\xb5\xd0\xb9", "CNY" },
			{ "\xd0\xb8\xd0\xb5\xd0\xbd", "JPY" },
			{ "\xd0\xb9\xd0\xb5\xd0\xbd", "JPY" },
			{ "\xd1\x84\xd1\x80\xd0\xb0\xd0\xbd\xd0\xba", "CHF" },
			{ "\xd0\xb7\xd0\xbb\xd0\xbe\xd1\x82\xd1\x8b\xd0\xb9", "PLN" },
			{ "\xd0\xb7\xd0\xbb\xd0\xbe\xd1\x82\xd1\x8b\xd1\x85", "PLN" },
			{ "\xd0\xbb\xd0\xb0\xd1\x80\xd0\xb8", "GEL" },
			{ "\xd0\xb4\xd0\xb8\xd1\x80\xd1\x85\xd0\xb0\xd0\xbc", "AED" },
			{ "\xd0\xb4\xd0\xb8\xd1\x80\xd1\x85\xd0\xb0\xd0\xbc\xd0\xbe\xd0\xb2", "AED" },
			{ "\xd1\x81\xd1\x83\xd0\xbc", "UZS" },
			{ "\xd1\x81\xd0\xbe\xd0\xbc", "KGS" },
			{ "\xd0\xbc\xd0\xb0\xd0\xbd\xd0\xb0\xd1\x82", "AZN" },
			{ "ton", "GRAM" },
		};
		for (const auto &[alias, code] : kExtraAliases) {
			const auto upper = QString::fromLatin1(code);
			if (result.byCode.contains(upper)) {
				result.aliases[QString::fromUtf8(alias)] = upper;
			}
		}
		return result;
	}();
	return db;
}

[[nodiscard]] std::optional<CurrencyEntry> FindCurrency(const QString &token) {
	const auto &db = GetCurrencyDb();
	const auto key = token.trimmed().toLower();
	if (const auto it = db.aliases.find(key); it != db.aliases.end()) {
		if (const auto entry = db.byCode.find(it->second); entry != db.byCode.end()) {
			return entry->second;
		}
	}
	if (const auto entry = db.byCode.find(key.toUpper()); entry != db.byCode.end()) {
		return entry->second;
	}
	return std::nullopt;
}

[[nodiscard]] QString FormatCurrencyAmount(double value, int exp) {
	if (value > 0.0 && value < 0.01) {
		return QString::number(value, 'g', 4);
	}
	const auto decimals = (exp <= 0) ? 0 : std::min(exp, 3);
	return QString::number(value, 'f', decimals);
}

[[nodiscard]] std::optional<QString> EvaluateCurrency(const QString &text) {
	const auto lower = text.toLower().trimmed();
	const auto &db = GetCurrencyDb();
	const auto rubPerUsd = db.byCode.contains(u"RUB"_q)
		? db.byCode.at(u"RUB"_q).perUsd
		: 89.22;
	const auto eurPerUsd = db.byCode.contains(u"EUR"_q)
		? db.byCode.at(u"EUR"_q).perUsd
		: 0.92;

	static const auto kStarsRe = QRegularExpression(
		u"^(\\d+)\\s*(?:stars|\u0437\u0432[\u0435\u0451]\u0437\u0434[a-z\u0430-\u044f]*)$"_q);
	const auto stm = kStarsRe.match(lower);
	if (stm.hasMatch()) {
		const auto count = stm.captured(1).toLongLong();
		const auto usd = double(count) * 0.02;
		const auto rub = usd * rubPerUsd;
		return QString("$%1 (~%2 \u20BD)")
			.arg(usd, 0, 'f', 2)
			.arg(std::round(rub), 0, 'f', 0);
	}

	static const auto kSimpleSymRe = QRegularExpression(
		u"^([0-9.,]+)\\s*([$\u20ac\u20bd\u00a3\u20b4\u20b8\u20ba\u20b9\u20a9\u20ab\u20aa\u0e3f\u20b1\u00a5\uffe5]|[a-z]{3})$"_q);
	const auto symMatch = kSimpleSymRe.match(lower);
	if (symMatch.hasMatch()) {
		auto ok = false;
		const auto val = symMatch.captured(1).replace(',', '.').toDouble(&ok);
		if (!ok) {
			return std::nullopt;
		}
		if (const auto src = FindCurrency(symMatch.captured(2))) {
			const auto usdVal = val / src->perUsd;
			if (src->code == u"EUR"_q) {
				return QString("$%1 (~%2 \u20BD)")
					.arg(usdVal, 0, 'f', 2)
					.arg(std::round(usdVal * rubPerUsd), 0, 'f', 0);
			} else if (src->code == u"USD"_q) {
				return QString("~%1 \u20AC (~%2 \u20BD)")
					.arg(usdVal * eurPerUsd, 0, 'f', 2)
					.arg(std::round(usdVal * rubPerUsd), 0, 'f', 0);
			} else if (src->code == u"RUB"_q) {
				return QString("$%1 (~%2 \u20AC)")
					.arg(usdVal, 0, 'f', 2)
					.arg(usdVal * eurPerUsd, 0, 'f', 2);
			}
			return QString("$%1 (~%2 \u20BD)")
				.arg(usdVal, 0, 'f', 2)
				.arg(std::round(usdVal * rubPerUsd), 0, 'f', 0);
		}
	}

	static const auto kCurrPairRe = QRegularExpression(
		u"^([0-9.,]+)\\s*([k\u043a\u043cm](?![a-z\u0430-\u044f]))?\\s*([^\\s0-9]+)\\s+(?:to|\u0432)\\s+([^\\s0-9]+)$"_q);
	const auto cpm = kCurrPairRe.match(lower);
	if (cpm.hasMatch()) {
		auto ok = false;
		auto val = cpm.captured(1).replace(',', '.').toDouble(&ok);
		if (!ok) {
			return std::nullopt;
		}
		const auto mult = cpm.captured(2);
		if (mult == u"k"_q || mult == u"\u043a"_q) {
			val *= 1000.0;
		} else if (mult == u"m"_q || mult == u"\u043c"_q) {
			val *= 1000000.0;
		}

		const auto from = FindCurrency(cpm.captured(3));
		const auto to = FindCurrency(cpm.captured(4));
		if (from && to) {
			const auto usdVal = val / from->perUsd;
			const auto res = usdVal * to->perUsd;
			return QString("%1 %2")
				.arg(FormatCurrencyAmount(res, to->exp), to->outputTag);
		}
	}
	return std::nullopt;
}

[[nodiscard]] QTimeZone ResolveCityTimeZone(const QString &rawName) {
	auto clean = rawName.trimmed().toLower();
	if (clean.isEmpty()) {
		return QTimeZone();
	}

	const auto tryIana = [](const QByteArray &id) -> QTimeZone {
		auto tz = QTimeZone(id);
		return tz.isValid() ? tz : QTimeZone();
	};

	if (const auto direct = tryIana(rawName.trimmed().toUtf8()); direct.isValid()) {
		return direct;
	}

	static const std::pair<const char*, const char*> kCityAliases[] = {
		{ "new york", "America/New_York" },
		{ "nyc", "America/New_York" },
		{ "\xd0\xbd\xd1\x8c\xd1\x8e-\xd0\xb9\xd0\xbe\xd1\x80\xd0\xba", "America/New_York" },
		{ "\xd0\xbd\xd1\x8c\xd1\x8e \xd0\xb9\xd0\xbe\xd1\x80\xd0\xba", "America/New_York" },
		{ "miami", "America/New_York" },
		{ "\xd0\xbc\xd0\xb0\xd0\xb9\xd0\xb0\xd0\xbc\xd0\xb8", "America/New_York" },
		{ "boston", "America/New_York" },
		{ "washington", "America/New_York" },
		{ "\xd0\xb2\xd0\xb0\xd1\x88\xd0\xb8\xd0\xbd\xd0\xb3\xd1\x82\xd0\xbe\xd0\xbd", "America/New_York" },
		{ "la", "America/Los_Angeles" },
		{ "sf", "America/Los_Angeles" },
		{ "san francisco", "America/Los_Angeles" },
		{ "\xd1\x81\xd0\xb0\xd0\xbd-\xd1\x84\xd1\x80\xd0\xb0\xd0\xbd\xd1\x86\xd0\xb8\xd1\x81\xd0\xba\xd0\xbe", "America/Los_Angeles" },
		{ "\xd0\xbb\xd0\xbe\xd1\x81-\xd0\xb0\xd0\xbd\xd0\xb4\xd0\xb6\xd0\xb5\xd0\xbb\xd0\xb5\xd1\x81", "America/Los_Angeles" },
		{ "\xd1\x87\xd0\xb8\xd0\xba\xd0\xb0\xd0\xb3\xd0\xbe", "America/Chicago" },
		{ "\xd1\x82\xd0\xbe\xd1\x80\xd0\xbe\xd0\xbd\xd1\x82\xd0\xbe", "America/Toronto" },
		{ "\xd1\x80\xd0\xb8\xd0\xbe", "America/Sao_Paulo" },
		{ "london", "Europe/London" },
		{ "uk", "Europe/London" },
		{ "\xd0\xbb\xd0\xbe\xd0\xbd\xd0\xb4\xd0\xbe\xd0\xbd", "Europe/London" },
		{ "moscow", "Europe/Moscow" },
		{ "msk", "Europe/Moscow" },
		{ "\xd0\xbc\xd0\xbe\xd1\x81\xd0\xba\xd0\xb2\xd0\xb0", "Europe/Moscow" },
		{ "\xd0\xbc\xd1\x81\xd0\xba", "Europe/Moscow" },
		{ "\xd0\xbf\xd0\xb8\xd1\x82\xd0\xb5\xd1\x80", "Europe/Moscow" },
		{ "\xd1\x81\xd0\xb0\xd0\xbd\xd0\xba\xd1\x82-\xd0\xbf\xd0\xb5\xd1\x82\xd0\xb5\xd1\x80\xd0\xb1\xd1\x83\xd1\x80\xd0\xb3", "Europe/Moscow" },
		{ "\xd1\x81\xd0\xbf\xd0\xb1", "Europe/Moscow" },
		{ "\xd0\xba\xd0\xb0\xd0\xb7\xd0\xb0\xd0\xbd\xd1\x8c", "Europe/Moscow" },
		{ "\xd0\xba\xd0\xb0\xd0\xbb\xd0\xb8\xd0\xbd\xd0\xb8\xd0\xbd\xd0\xb3\xd1\x80\xd0\xb0\xd0\xb4", "Europe/Kaliningrad" },
		{ "\xd1\x81\xd0\xb0\xd0\xbc\xd0\xb0\xd1\x80\xd0\xb0", "Europe/Samara" },
		{ "\xd0\xb5\xd0\xba\xd0\xb0\xd1\x82\xd0\xb5\xd1\x80\xd0\xb8\xd0\xbd\xd0\xb1\xd1\x83\xd1\x80\xd0\xb3", "Asia/Yekaterinburg" },
		{ "\xd0\xb5\xd0\xba\xd0\xb1", "Asia/Yekaterinburg" },
		{ "\xd0\xbe\xd0\xbc\xd1\x81\xd0\xba", "Asia/Omsk" },
		{ "\xd0\xbd\xd0\xbe\xd0\xb2\xd0\xbe\xd1\x81\xd0\xb8\xd0\xb1\xd0\xb8\xd1\x80\xd1\x81\xd0\xba", "Asia/Novosibirsk" },
		{ "\xd0\xbd\xd1\x81\xd0\xba", "Asia/Novosibirsk" },
		{ "\xd0\xba\xd1\x80\xd0\xb0\xd1\x81\xd0\xbd\xd0\xbe\xd1\x8f\xd1\x80\xd1\x81\xd0\xba", "Asia/Krasnoyarsk" },
		{ "\xd0\xb8\xd1\x80\xd0\xba\xd1\x83\xd1\x82\xd1\x81\xd0\xba", "Asia/Irkutsk" },
		{ "\xd0\xb2\xd0\xbb\xd0\xb0\xd0\xb4\xd0\xb8\xd0\xb2\xd0\xbe\xd1\x81\xd1\x82\xd0\xbe\xd0\xba", "Asia/Vladivostok" },
		{ "\xd1\x85\xd0\xb0\xd0\xb1\xd0\xb0\xd1\x80\xd0\xbe\xd0\xb2\xd1\x81\xd0\xba", "Asia/Vladivostok" },
		{ "\xd0\xbc\xd0\xb8\xd0\xbd\xd1\x81\xd0\xba", "Europe/Minsk" },
		{ "kyiv", "Europe/Kyiv" },
		{ "kiev", "Europe/Kyiv" },
		{ "\xd0\xba\xd0\xb8\xd0\xb5\xd0\xb2", "Europe/Kyiv" },
		{ "\xd0\xb1\xd0\xb5\xd1\x80\xd0\xbb\xd0\xb8\xd0\xbd", "Europe/Berlin" },
		{ "\xd0\xbf\xd0\xb0\xd1\x80\xd0\xb8\xd0\xb6", "Europe/Paris" },
		{ "\xd0\xb2\xd0\xb0\xd1\x80\xd1\x88\xd0\xb0\xd0\xb2\xd0\xb0", "Europe/Warsaw" },
		{ "\xd0\xbf\xd1\x80\xd0\xb0\xd0\xb3\xd0\xb0", "Europe/Prague" },
		{ "\xd1\x80\xd0\xb8\xd0\xbc", "Europe/Rome" },
		{ "\xd0\xbc\xd0\xb0\xd0\xb4\xd1\x80\xd0\xb8\xd0\xb4", "Europe/Madrid" },
		{ "\xd0\xb0\xd0\xbc\xd1\x81\xd1\x82\xd0\xb5\xd1\x80\xd0\xb4\xd0\xb0\xd0\xbc", "Europe/Amsterdam" },
		{ "\xd1\x81\xd1\x82\xd0\xb0\xd0\xbc\xd0\xb1\xd1\x83\xd0\xbb", "Europe/Istanbul" },
		{ "\xd1\x82\xd0\xb1\xd0\xb8\xd0\xbb\xd0\xb8\xd1\x81\xd0\xb8", "Asia/Tbilisi" },
		{ "\xd0\xb5\xd1\x80\xd0\xb5\xd0\xb2\xd0\xb0\xd0\xbd", "Asia/Yerevan" },
		{ "\xd0\xb1\xd0\xb0\xd0\xba\xd1\x83", "Asia/Baku" },
		{ "\xd0\xb0\xd0\xbb\xd0\xbc\xd0\xb0\xd1\x82\xd1\x8b", "Asia/Almaty" },
		{ "astana", "Asia/Almaty" },
		{ "\xd0\xb0\xd1\x81\xd1\x82\xd0\xb0\xd0\xbd\xd0\xb0", "Asia/Almaty" },
		{ "\xd1\x82\xd0\xb0\xd1\x88\xd0\xba\xd0\xb5\xd0\xbd\xd1\x82", "Asia/Tashkent" },
		{ "\xd0\xb1\xd0\xb8\xd1\x88\xd0\xba\xd0\xb5\xd0\xba", "Asia/Bishkek" },
		{ "\xd0\xb4\xd1\x83\xd0\xb1\xd0\xb0\xd0\xb9", "Asia/Dubai" },
		{ "tokyo", "Asia/Tokyo" },
		{ "\xd1\x82\xd0\xbe\xd0\xba\xd0\xb8\xd0\xbe", "Asia/Tokyo" },
		{ "beijing", "Asia/Shanghai" },
		{ "\xd0\xbf\xd0\xb5\xd0\xba\xd0\xb8\xd0\xbd", "Asia/Shanghai" },
		{ "\xd1\x88\xd0\xb0\xd0\xbd\xd1\x85\xd0\xb0\xd0\xb9", "Asia/Shanghai" },
		{ "\xd1\x81\xd0\xb5\xd1\x83\xd0\xbb", "Asia/Seoul" },
		{ "\xd1\x81\xd0\xb8\xd0\xbd\xd0\xb3\xd0\xb0\xd0\xbf\xd1\x83\xd1\x80", "Asia/Singapore" },
		{ "\xd0\xb1\xd0\xb0\xd0\xbd\xd0\xb3\xd0\xba\xd0\xbe\xd0\xba", "Asia/Bangkok" },
		{ "delhi", "Asia/Kolkata" },
		{ "mumbai", "Asia/Kolkata" },
		{ "\xd0\xb4\xd0\xb5\xd0\xbb\xd0\xb8", "Asia/Kolkata" },
		{ "\xd1\x81\xd0\xb8\xd0\xb4\xd0\xbd\xd0\xb5\xd0\xb9", "Australia/Sydney" },
		{ "\xd0\xba\xd0\xb0\xd0\xb8\xd1\x80", "Africa/Cairo" },
	};

	const auto lookupAlias = [&](const QString &candidate) -> QTimeZone {
		for (const auto &[alias, iana] : kCityAliases) {
			if (candidate == QString::fromUtf8(alias)) {
				if (const auto tz = tryIana(iana); tz.isValid()) {
					return tz;
				}
				if (QByteArray(iana) == "Europe/Kyiv") {
					if (const auto tz = tryIana("Europe/Kiev"); tz.isValid()) {
						return tz;
					}
				}
			}
		}
		return QTimeZone();
	};

	if (const auto tz = lookupAlias(clean); tz.isValid()) {
		return tz;
	}
	if (clean.endsWith(QChar(0x0435)) && clean.size() > 3) {
		// Russian prepositional case ("в Берлине" -> "Берлин", "в Москве" -> "Москва").
		const auto stem = clean.left(clean.size() - 1);
		if (const auto tz = lookupAlias(stem); tz.isValid()) {
			return tz;
		}
		if (const auto tz = lookupAlias(stem + QChar(0x0430)); tz.isValid()) {
			return tz;
		}
		if (const auto tz = lookupAlias(stem + QChar(0x0439)); tz.isValid()) {
			return tz;
		}
	}

	static const auto kAllZones = QTimeZone::availableTimeZoneIds();
	auto normalized = clean;
	normalized.replace(' ', '_');
	for (const auto &id : kAllZones) {
		const auto lowerId = QString::fromLatin1(id).toLower();
		if (lowerId == normalized) {
			return tryIana(id);
		}
		const auto slash = lowerId.lastIndexOf('/');
		if (slash >= 0 && lowerId.mid(slash + 1) == normalized) {
			return tryIana(id);
		}
	}
	return QTimeZone();
}

[[nodiscard]] QTimeZone ResolveZoneToken(const QString &token) {
	const auto lower = token.trimmed().toLower();
	if (lower.isEmpty()) {
		return QTimeZone();
	}

	static const auto kOffsetRe = QRegularExpression(
		u"^(?:utc|gmt)([+-])(\\d{1,2})(?::?(\\d{2}))?$"_q);
	const auto om = kOffsetRe.match(lower);
	if (om.hasMatch()) {
		const auto sign = (om.captured(1) == u"-"_q) ? -1 : 1;
		const auto hours = om.captured(2).toInt();
		const auto mins = om.captured(3).isEmpty() ? 0 : om.captured(3).toInt();
		if (hours <= 14 && mins < 60) {
			return QTimeZone(sign * (hours * 3600 + mins * 60));
		}
	}

	static const std::pair<const char*, int> kFixedAbbr[] = {
		{ "utc", 0 },
		{ "gmt", 0 },
		{ "wet", 0 },
		{ "west", 3600 },
		{ "bst", 3600 },
		{ "cet", 3600 },
		{ "cest", 2 * 3600 },
		{ "eet", 2 * 3600 },
		{ "eest", 3 * 3600 },
		{ "msk", 3 * 3600 },
		{ "\xd0\xbc\xd1\x81\xd0\xba", 3 * 3600 },
		{ "ist", 5 * 3600 + 1800 },
		{ "jst", 9 * 3600 },
		{ "kst", 9 * 3600 },
		{ "aest", 10 * 3600 },
		{ "aedt", 11 * 3600 },
		{ "est", -5 * 3600 },
		{ "edt", -4 * 3600 },
		{ "cst", -6 * 3600 },
		{ "cdt", -5 * 3600 },
		{ "mst", -7 * 3600 },
		{ "mdt", -6 * 3600 },
		{ "pst", -8 * 3600 },
		{ "pdt", -7 * 3600 },
		{ "akst", -9 * 3600 },
		{ "akdt", -8 * 3600 },
		{ "hst", -10 * 3600 },
	};
	for (const auto &[abbr, offset] : kFixedAbbr) {
		if (lower == QString::fromUtf8(abbr)) {
			return QTimeZone(offset);
		}
	}
	return ResolveCityTimeZone(token);
}

[[nodiscard]] QString ZoneDisplayLabel(const QTimeZone &tz, const QDateTime &at) {
	if (!tz.isValid()) {
		return QString();
	}
	if (tz.id() == QByteArray("Europe/Moscow")) {
		return u"MSK"_q;
	}
	const auto abbr = tz.abbreviation(at);
	if (!abbr.isEmpty() && abbr.size() <= 8 && !abbr.contains(' ')) {
		return abbr;
	}
	const auto offsetSec = tz.offsetFromUtc(at);
	const auto sign = (offsetSec >= 0) ? '+' : '-';
	const auto absMin = std::abs(offsetSec) / 60;
	const auto h = absMin / 60;
	const auto m = absMin % 60;
	return (m == 0)
		? QString("UTC%1%2").arg(sign).arg(h)
		: QString("UTC%1%2:%3").arg(sign).arg(h).arg(m, 2, 10, QChar('0'));
}

[[nodiscard]] std::optional<QString> EvaluateTimeZone(const QString &text) {
	const auto lower = text.toLower().trimmed();

	static const auto kNowInRe = QRegularExpression(
		u"^(?:now\\s+in|time\\s+in|\u0441\u0435\u0439\u0447\u0430\u0441\\s+\u0432|\u0432\u0440\u0435\u043c\u044f\\s+\u0432)\\s+([a-z\u0430-\u044f0-9_/+:\\s-]+)$"_q);
	const auto nowMatch = kNowInRe.match(lower);
	if (nowMatch.hasMatch()) {
		const auto tz = ResolveZoneToken(nowMatch.captured(1));
		if (tz.isValid()) {
			const auto target = QDateTime::currentDateTimeUtc().toTimeZone(tz);
			return QString("%1 (%2)")
				.arg(target.toString(u"hh:mm"_q), ZoneDisplayLabel(tz, target));
		}
	}

	static const auto kTimeConvertRe = QRegularExpression(
		u"^(\\d{1,2}(?::\\d{2})?)\\s*(am|pm)?\\s*([a-z\u0430-\u044f0-9_/+:\\s-]+?)\\s+(?:to|\u0432)\\s+([a-z\u0430-\u044f0-9_/+:\\s-]+)$"_q);
	const auto convMatch = kTimeConvertRe.match(lower);
	if (convMatch.hasMatch()) {
		const auto srcTz = ResolveZoneToken(convMatch.captured(3));
		const auto dstTz = ResolveZoneToken(convMatch.captured(4));
		if (srcTz.isValid() && dstTz.isValid()) {
			const auto timeStr = convMatch.captured(1);
			const auto ampm = convMatch.captured(2);
			auto parts = timeStr.split(':');
			auto h = parts[0].toInt();
			auto m = (parts.size() > 1) ? parts[1].toInt() : 0;
			if (ampm == u"pm"_q && h < 12) h += 12;
			else if (ampm == u"am"_q && h == 12) h = 0;
			const auto t = QTime(h, m);
			if (t.isValid()) {
				const auto srcDt = QDateTime(QDate::currentDate(), t, srcTz);
				const auto dstDt = srcDt.toTimeZone(dstTz);
				return QString("%1 %2 (%3 %4)")
					.arg(srcDt.toString(u"hh:mm"_q), ZoneDisplayLabel(srcTz, srcDt))
					.arg(dstDt.toString(u"hh:mm"_q), ZoneDisplayLabel(dstTz, dstDt));
			}
		}
	}

	static const auto kTimeInRe = QRegularExpression(
		u"^(\\d{1,2}(?::\\d{2})?)\\s*(am|pm)?\\s+(?:in|\u0432)\\s+([a-z\u0430-\u044f0-9_/+:\\s-]+)$"_q);
	const auto timeMatch = kTimeInRe.match(lower);
	if (timeMatch.hasMatch()) {
		const auto timeStr = timeMatch.captured(1);
		const auto ampm = timeMatch.captured(2);
		auto parts = timeStr.split(':');
		auto h = parts[0].toInt();
		auto m = (parts.size() > 1) ? parts[1].toInt() : 0;
		if (ampm == u"pm"_q && h < 12) h += 12;
		else if (ampm == u"am"_q && h == 12) h = 0;
		const auto time = QTime(h, m);
		if (!time.isValid()) {
			return std::nullopt;
		}
		const auto srcTz = ResolveZoneToken(timeMatch.captured(3));
		if (srcTz.isValid()) {
			const auto localTz = QTimeZone::systemTimeZone();
			const auto srcDt = QDateTime(QDate::currentDate(), time, srcTz);
			const auto localDt = srcDt.toTimeZone(localTz);
			return QString("%1 (%2 %3)")
				.arg(srcDt.toString(u"hh:mm"_q))
				.arg(localDt.toString(u"hh:mm"_q), ZoneDisplayLabel(localTz, localDt));
		}
	}

	static const auto kAmPmRe = QRegularExpression(
		u"^(\\d{1,2}(?::\\d{2})?)\\s*(am|pm)?\\s*([a-z\u0430-\u044f]+(?:[+-]\\d{1,2}(?::?\\d{2})?)?)$"_q);
	const auto ampmMatch = kAmPmRe.match(lower);
	if (ampmMatch.hasMatch()) {
		const auto tzToken = ampmMatch.captured(3);
		const auto srcTz = ResolveZoneToken(tzToken);
		if (srcTz.isValid()) {
			const auto timeStr = ampmMatch.captured(1);
			const auto ampm = ampmMatch.captured(2);
			auto parts = timeStr.split(':');
			auto h = parts[0].toInt();
			auto m = (parts.size() > 1) ? parts[1].toInt() : 0;
			if (ampm == u"pm"_q && h < 12) h += 12;
			else if (ampm == u"am"_q && h == 12) h = 0;
			const auto time = QTime(h, m);
			if (time.isValid()) {
				const auto localTz = QTimeZone::systemTimeZone();
				const auto srcDt = QDateTime(QDate::currentDate(), time, srcTz);
				const auto localDt = srcDt.toTimeZone(localTz);
				return QString("%1 %2 (%3 %4)")
					.arg(srcDt.toString(u"hh:mm"_q), ZoneDisplayLabel(srcTz, srcDt))
					.arg(localDt.toString(u"hh:mm"_q), ZoneDisplayLabel(localTz, localDt));
			}
		}
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
		const auto start = int(match.capturedStart());
		const auto len = int(match.capturedLength());
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
