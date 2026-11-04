#include "extera/extera_media_cache.h"
#include "extera/extera_config.h"

#include <QtCore/QCryptographicHash>
#include <QtCore/QFile>
#include <QtCore/QFileInfo>
#include <QtCore/QDir>
#include <QtCore/QJsonObject>
#include <QtCore/QJsonDocument>
#include <QtCore/QDateTime>
#include <mutex>
#include <unordered_map>

namespace Extera::MediaCache {
namespace {

struct CacheEntry {
	uint64 fileId = 0;
	int parts = 0;
	QString name;
	QString md5Checksum;
	qint64 timestamp = 0;
};

std::mutex gMutex;
std::unordered_map<QString, CacheEntry> gCache;
bool gLoaded = false;

QString CachePath() {
	return cWorkingDir() + u"tdata/ox_media_dedup.json"_q;
}

void Load() {
	if (gLoaded) return;
	gLoaded = true;

	QFile file(CachePath());
	if (!file.open(QIODevice::ReadOnly)) return;

	const auto doc = QJsonDocument::fromJson(file.readAll());
	if (!doc.isObject()) return;

	const auto root = doc.object();
	const auto now = QDateTime::currentSecsSinceEpoch();
	// Valid for 24 hours
	constexpr qint64 kMaxAge = 24 * 3600;

	for (auto it = root.begin(); it != root.end(); ++it) {
		if (it.value().isObject()) {
			const auto obj = it.value().toObject();
			const auto ts = obj.value(u"ts"_q).toInteger();
			if (now - ts < kMaxAge) {
				gCache[it.key()] = CacheEntry{
					.fileId = static_cast<uint64>(obj.value(u"id"_q).toInteger()),
					.parts = obj.value(u"parts"_q).toInt(),
					.name = obj.value(u"name"_q).toString(),
					.md5Checksum = obj.value(u"md5"_q).toString(),
					.timestamp = ts,
				};
			}
		}
	}
}

void Save() {
	QJsonObject root;
	for (const auto &[hash, entry] : gCache) {
		QJsonObject item;
		item[u"id"_q] = static_cast<qint64>(entry.fileId);
		item[u"parts"_q] = entry.parts;
		item[u"name"_q] = entry.name;
		item[u"md5"_q] = entry.md5Checksum;
		item[u"ts"_q] = entry.timestamp;
		root[hash] = item;
	}

	QFile file(CachePath());
	if (file.open(QIODevice::WriteOnly)) {
		file.write(QJsonDocument(root).toJson(QJsonDocument::Compact));
	}
}

} // namespace

QString ComputeFileHash(const QString &filePath) {
	QFile file(filePath);
	if (!file.open(QIODevice::ReadOnly)) {
		return QString();
	}

	QCryptographicHash hash(QCryptographicHash::Sha256);
	constexpr qint64 kChunkSize = 512 * 1024;
	qint64 read = 0;
	// Fast sampling: first 2MB, middle 512KB, last 512KB + file size
	const auto size = file.size();
	if (size <= 4 * 1024 * 1024) {
		if (hash.addData(&file)) {
			return QString::fromLatin1(hash.result().toHex()) + '_' + QString::number(size);
		}
	} else {
		QByteArray buf = file.read(2 * 1024 * 1024);
		hash.addData(buf);
		file.seek(size / 2);
		hash.addData(file.read(kChunkSize));
		file.seek(std::max<qint64>(0, size - kChunkSize));
		hash.addData(file.read(kChunkSize));
		return QString::fromLatin1(hash.result().toHex()) + '_' + QString::number(size);
	}
	return QString();
}

void Put(const QString &hash, uint64 fileId, int parts, const QString &name, const QString &md5Checksum) {
	if (hash.isEmpty() || !Extera::Bool(u"media_deduplication"_q)) return;

	std::lock_guard<std::mutex> lock(gMutex);
	Load();
	gCache[hash] = CacheEntry{
		.fileId = fileId,
		.parts = parts,
		.name = name,
		.md5Checksum = md5Checksum,
		.timestamp = QDateTime::currentSecsSinceEpoch(),
	};
	Save();
}

bool Has(const QString &hash) {
	if (hash.isEmpty() || !Extera::Bool(u"media_deduplication"_q)) return false;

	std::lock_guard<std::mutex> lock(gMutex);
	Load();
	return gCache.find(hash) != gCache.end();
}

void Invalidate(const QString &hash) {
	if (hash.isEmpty()) return;

	std::lock_guard<std::mutex> lock(gMutex);
	Load();
	gCache.erase(hash);
	Save();
}

void Clear() {
	std::lock_guard<std::mutex> lock(gMutex);
	gCache.clear();
	QFile::remove(CachePath());
}

} // namespace Extera::MediaCache
