#pragma once

#include "base/basic_types.h"

#include <rpl/producer.h>

class QNetworkAccessManager;
class QNetworkRequest;

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
void Restart();
void StartAutoTimer();
void HandleConnectionState(int32 state);
void ApplyHttpProxy(QNetworkAccessManager *manager);
void PrepareFrontedRequest(QNetworkRequest &request);
void SetEnabled(bool enabled);

} // namespace Extera::WsProxy
