#pragma once

#include <QtCore/QString>
#include <optional>

namespace Extera::MediaCache {

[[nodiscard]] QString ComputeFileHash(const QString &filePath);
void Put(const QString &hash, uint64 fileId, int parts, const QString &name, const QString &md5Checksum);
[[nodiscard]] bool Has(const QString &hash);
void Invalidate(const QString &hash);
void Clear();

} // namespace Extera::MediaCache
