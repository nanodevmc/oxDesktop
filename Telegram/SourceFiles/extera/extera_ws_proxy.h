#pragma once

#include <rpl/producer.h>

namespace MTP {
struct ProxyData;
} // namespace MTP

namespace Extera::WsProxy {

[[nodiscard]] bool Available();
[[nodiscard]] bool Enabled();
[[nodiscard]] QString Version();
[[nodiscard]] int Port();
[[nodiscard]] QString CurrentEndpoint();
[[nodiscard]] rpl::producer<QString> statusTextValue();
[[nodiscard]] bool IsOurs(const MTP::ProxyData &proxy);
void CleanOurProxies();
void Start();
void Stop();
void SetEnabled(bool enabled);

} // namespace Extera::WsProxy
