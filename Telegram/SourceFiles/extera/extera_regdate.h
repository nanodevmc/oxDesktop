#pragma once

#include <QtCore/QString>
#include <optional>

namespace Extera::RegDate {

struct Estimation {
	int year = 0;
	int month = 0;
	bool approximate = true;
};

[[nodiscard]] std::optional<Estimation> Estimate(uint64 userId);
[[nodiscard]] QString FormatEstimation(uint64 userId);

} // namespace Extera::RegDate
