#pragma once

namespace Window {
class SessionController;
} // namespace Window

namespace Extera::Update {

enum class CheckResult {
	Available,
	Latest,
	Failed,
};

void Start();
[[nodiscard]] int Build();
[[nodiscard]] QString VersionText();
void CheckNow(Fn<void(CheckResult)> done);
[[nodiscard]] rpl::producer<bool> AvailableValue();
[[nodiscard]] QString AvailableVersion();
[[nodiscard]] QString Changelog();
void OpenRelease();
void Install();
void ShowUpdateBox(not_null<Window::SessionController*> controller);

} // namespace Extera::Update
