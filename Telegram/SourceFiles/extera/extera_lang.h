#pragma once

#include <QtCore/QByteArray>
#include <QtCore/QString>
#include <string_view>

namespace Extera {

void ApplyRussian(Fn<void(const QByteArray&, const QByteArray&)> apply);
[[nodiscard]] QString LookupRussian(std::string_view key);

} // namespace Extera
