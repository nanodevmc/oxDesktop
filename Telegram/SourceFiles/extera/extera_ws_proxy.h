#pragma once

#include <rpl/producer.h>

namespace Extera::WsProxy {

[[nodiscard]] bool Available();
[[nodiscard]] bool Enabled();
[[nodiscard]] QString Version();
[[nodiscard]] int Port();
[[nodiscard]] QString CurrentEndpoint();
[[nodiscard]] rpl::producer<QString> statusTextValue();
void Start();
void Stop();
void SetEnabled(bool enabled);

} // namespace Extera::WsProxy
