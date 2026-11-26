#include "extera/extera_regdate.h"

#include <QtCore/QDateTime>
#include <QtCore/QFile>
#include <QtCore/QJsonDocument>
#include <QtCore/QJsonObject>
#include <QtCore/QLocale>
#include <QtCore/QTimeZone>

#include <algorithm>
#include <array>
#include <vector>

namespace Extera::RegDate {
namespace {

struct EpochMarker {
	uint64 id;
	int year;
	int month;
};

struct RegDatePoint {
	uint64 id = 0;
	int64 timestamp = 0;
};

constexpr auto kEpochs = std::array{
	EpochMarker{ 0ULL, 2013, 8 },
	EpochMarker{ 4000000ULL, 2014, 1 },
	EpochMarker{ 45000000ULL, 2015, 1 },
	EpochMarker{ 160000000ULL, 2016, 1 },
	EpochMarker{ 330000000ULL, 2017, 1 },
	EpochMarker{ 530000000ULL, 2018, 1 },
	EpochMarker{ 770000000ULL, 2019, 1 },
	EpochMarker{ 1050000000ULL, 2020, 1 },
	EpochMarker{ 1500000000ULL, 2021, 1 },
	EpochMarker{ 2100000000ULL, 2022, 1 },
	EpochMarker{ 5800000000ULL, 2023, 1 },
	EpochMarker{ 6900000000ULL, 2024, 1 },
	EpochMarker{ 7800000000ULL, 2025, 1 },
	EpochMarker{ 8500000000ULL, 2026, 1 },
};

[[nodiscard]] int AlphabetIndex(char16_t ch) {
	constexpr std::array<char16_t, 11> kAlphabet = {
		0x200A, 0x200B, 0x200C, 0x200F, 0x202F,
		0x206A, 0x206B, 0x206C, 0x206D, 0x206E, 0x206F,
	};
	for (auto i = 0; i < int(kAlphabet.size()); ++i) {
		if (kAlphabet[i] == ch) {
			return i;
		}
	}
	return -1;
}

[[nodiscard]] QByteArray DecodeInvisible(const QByteArray &raw) {
	auto text = QString::fromUtf8(raw);
	const auto prefix = QString(QChar(0x2001)) + QChar(0x2002);
	if (text.startsWith(prefix)) {
		text.remove(0, prefix.size());
	}
	const auto parts = QStringView(text).split(QChar(0x2000));
	QByteArray decoded;
	decoded.reserve(parts.size());
	for (const auto part : parts) {
		auto value = 0;
		for (const auto ch : part) {
			const auto idx = AlphabetIndex(ch.unicode());
			if (idx < 0) {
				return QByteArray();
			}
			value = value * 11 + idx;
		}
		decoded.append(char(value & 0xFF));
	}
	return decoded;
}

[[nodiscard]] std::vector<RegDatePoint> LoadRegDatePoints() {
	QFile file(u":/extera/registration_dates.bin"_q);
	if (!file.open(QIODevice::ReadOnly)) {
		return {};
	}
	const auto jsonBytes = DecodeInvisible(file.readAll());
	if (jsonBytes.isEmpty()) {
		return {};
	}
	const auto doc = QJsonDocument::fromJson(jsonBytes);
	if (!doc.isObject()) {
		return {};
	}
	const auto obj = doc.object();
	std::vector<RegDatePoint> result;
	result.reserve(obj.size());
	for (auto it = obj.begin(); it != obj.end(); ++it) {
		auto ok = false;
		const auto id = it.key().toULongLong(&ok);
		const auto ts = it.value().toInteger();
		if (ok && ts > 0) {
			result.push_back({ id, int64(ts) });
		}
	}
	std::sort(result.begin(), result.end(), [](const auto &a, const auto &b) {
		return a.id < b.id;
	});
	return result;
}

[[nodiscard]] const std::vector<RegDatePoint> &RegDateTable() {
	static const auto kTable = LoadRegDatePoints();
	return kTable;
}

[[nodiscard]] Estimation EstimateFromFallback(uint64 userId) {
	if (userId < 1000ULL) {
		return Estimation{ .year = 2013, .month = 8, .approximate = false };
	}
	for (auto i = size_t(0); i + 1 < kEpochs.size(); ++i) {
		const auto &low = kEpochs[i];
		const auto &high = kEpochs[i + 1];
		if (userId >= low.id && userId < high.id) {
			const auto ratio = double(userId - low.id) / double(high.id - low.id);
			const auto totalMonths = (high.year - low.year) * 12 + (high.month - low.month);
			const auto addMonths = int(ratio * totalMonths);
			auto m = low.month + addMonths;
			auto y = low.year + (m - 1) / 12;
			m = ((m - 1) % 12) + 1;
			return Estimation{ .year = y, .month = m, .approximate = true };
		}
	}
	return Estimation{ .year = 2026, .month = 1, .approximate = true };
}

} // namespace

std::optional<Estimation> Estimate(uint64 userId) {
	if (userId == 0 || userId > 20000000000ULL) {
		return std::nullopt;
	}
	const auto &table = RegDateTable();
	if (table.empty()) {
		return EstimateFromFallback(userId);
	}

	const auto it = std::lower_bound(
		table.begin(),
		table.end(),
		userId,
		[](const RegDatePoint &point, uint64 id) {
			return point.id < id;
		});

	auto timestamp = int64(0);
	auto approximate = true;
	if (it != table.end() && it->id == userId) {
		timestamp = it->timestamp;
		approximate = false;
	} else if (it == table.begin()) {
		timestamp = table.front().timestamp;
	} else if (it == table.end()) {
		timestamp = table.back().timestamp;
	} else {
		const auto &to = *it;
		const auto &from = *std::prev(it);
		const auto spanIds = double(to.id - from.id);
		const auto ratio = (spanIds > 0.0)
			? double(userId - from.id) / spanIds
			: 0.0;
		timestamp = from.timestamp
			+ int64(double(to.timestamp - from.timestamp) * ratio);
	}

	const auto date = QDateTime::fromSecsSinceEpoch(
		timestamp,
		QTimeZone::utc()).date();
	if (!date.isValid()) {
		return EstimateFromFallback(userId);
	}
	return Estimation{
		.year = date.year(),
		.month = date.month(),
		.approximate = approximate,
	};
}

QString FormatEstimation(uint64 userId) {
	const auto est = Estimate(userId);
	if (!est) {
		return QString();
	}
	const auto locale = QLocale();
	const auto monthName = locale.standaloneMonthName(est->month, QLocale::LongFormat);
	return est->approximate
		? QString("~%1 %2").arg(monthName).arg(est->year)
		: QString("%1 %2").arg(monthName).arg(est->year);
}

} // namespace Extera::RegDate
