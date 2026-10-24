#pragma once

namespace Extera::Update {

enum class CheckResult {
	Available,
	Latest,
	Failed,
};

void Start();
void CheckNow(Fn<void(CheckResult)> done);
[[nodiscard]] rpl::producer<bool> AvailableValue();
[[nodiscard]] QString AvailableVersion();
void OpenRelease();

} // namespace Extera::Update
