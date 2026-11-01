#include "extera/extera_regdate.h"

#include <QtCore/QLocale>
#include <array>

namespace Extera::RegDate {
namespace {

struct EpochMarker {
	uint64 id;
	int year;
	int month;
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

} // namespace

std::optional<Estimation> Estimate(uint64 userId) {
	if (userId == 0 || userId > 20000000000ULL) {
		return std::nullopt;
	}
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

QString FormatEstimation(uint64 userId) {
	const auto est = Estimate(userId);
	if (!est) {
		return QString();
	}
	const auto locale = QLocale();
	const auto monthName = locale.standaloneMonthName(est->month, QLocale::LongFormat);
	return QString("~%1 %2").arg(monthName).arg(est->year);
}

} // namespace Extera::RegDate
