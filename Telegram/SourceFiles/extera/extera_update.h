#pragma once

namespace Extera::Update {

void Start();
[[nodiscard]] rpl::producer<bool> AvailableValue();
[[nodiscard]] QString AvailableVersion();
void OpenRelease();

} // namespace Extera::Update
