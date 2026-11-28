#pragma once

#include "ui/text/text_entity.h"

#include <QtCore/QJsonValue>
#include <QtCore/QJsonObject>
#include <QtGui/QColor>
#include <optional>
#include <vector>

class History;
class HistoryItem;
class PeerData;

namespace Extera::Plugins {

inline constexpr auto kSdkVersion = "1.4.6.2";

enum class SendStrategy {
	Default,
	Cancel,
	Modify,
};

struct SendResult {
	SendStrategy strategy = SendStrategy::Default;
	QString text;
	EntitiesInText entities;
	bool quote = false;
};

struct MenuItem {
	QString id;
	QString text;
};

void Start();
void Shutdown();
int ExportAll(const QString &folder);

[[nodiscard]] bool Available();
[[nodiscard]] bool Started();
[[nodiscard]] QString RuntimeError();

QJsonValue Call(
	const QString &method,
	const QJsonObject &args = QJsonObject());

[[nodiscard]] bool Bypassing();
[[nodiscard]] SendResult OnSendMessage(
	not_null<History*> history,
	const QString &text,
	int64 replyTo);

[[nodiscard]] std::vector<MenuItem> MenuItems(const QString &type);
void ClickMenuItem(const QString &id, QJsonObject context);

void NotifyNewMessage(not_null<HistoryItem*> item);
void NotifyAppEvent(const QString &name);
[[nodiscard]] bool InterceptLocalUrl(const QString &url);

[[nodiscard]] int64 DialogId(not_null<PeerData*> peer);
[[nodiscard]] bool IsTrustedSource(not_null<PeerData*> peer);

[[nodiscard]] rpl::producer<> listChanges();
[[nodiscard]] rpl::producer<QString> settingsChanges();
void notifyListChanged();

struct UiOverride {
	QString shape;
	float64 widthScale = 1.0;
	float64 heightScale = 1.0;
	float64 cornerRadius = -1.0;
	std::optional<QColor> bgColor;
	std::optional<QColor> borderColor;
	float64 borderWidth = -1.0;
	int alpha = -1;
	bool visible = true;
};

void SetUiOverride(
	const QString &pluginId,
	const QString &target,
	const UiOverride &props);
void ClearUiOverrides(
	const QString &pluginId,
	const QString &target = QString());
[[nodiscard]] std::optional<UiOverride> GetUiOverride(const QString &target);

} // namespace Extera::Plugins
