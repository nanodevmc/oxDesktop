#pragma once

#include <QtCore/QString>

namespace Window {
class Controller;
} // namespace Window

namespace Extera::Demo {

[[nodiscard]] bool IsActive();
[[nodiscard]] QString View();
[[nodiscard]] QString ScreenshotPath();
[[nodiscard]] int DelayMs();
[[nodiscard]] bool AutoExit();

void SetEnabled(bool enabled);
void SetView(const QString &view);
void SetScreenshot(const QString &path);
void SetDelay(int delayMs);
void SetAutoExit(bool exit);

void Start(not_null<Window::Controller*> window);

} // namespace Extera::Demo
