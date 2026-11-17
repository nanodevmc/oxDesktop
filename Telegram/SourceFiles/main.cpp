/*
This file is part of Telegram Desktop,
the official desktop application for the Telegram messaging service.

For license and copyright information please follow this link:
https://github.com/telegramdesktop/tdesktop/blob/master/LEGAL
*/
#include "core/launcher.h"

extern "C" {
#include <openssl/crypto.h>
} // extern "C"

#if defined(_WIN32)
#include <QtPlugin>
#include <QtCore/QDir>
Q_IMPORT_PLUGIN(QWindowsIntegrationPlugin)
Q_IMPORT_PLUGIN(QWebpPlugin)
Q_IMPORT_PLUGIN(QJpegPlugin)
Q_IMPORT_PLUGIN(QGifPlugin)
#if QT_VERSION >= QT_VERSION_CHECK(6, 0, 0)
Q_IMPORT_PLUGIN(QSchannelBackendPlugin)
#endif
#endif

int main(int argc, char *argv[]) {
#if defined(_WIN32)
	Q_INIT_RESOURCE(gui_shaders);
	Q_INIT_RESOURCE(qpdf);
	Q_INIT_RESOURCE(qstyle);
	Q_INIT_RESOURCE(qstyle_fusion);
	Q_INIT_RESOURCE(qmessagebox);
	Q_INIT_RESOURCE(cursors);
	Q_INIT_RESOURCE(openglblacklists);
#endif
	// OpenSSL's own atexit handler runs OPENSSL_cleanup() on the main thread
	// and frees the library globals while detached background tasks can still
	// be inside OpenSSL, so an ordinary quit can fault on a worker thread.
	// Suppressing that registration leaves the library state alive until the
	// process exits, which is the trade we want: the OS reclaims it anyway.
	OPENSSL_init_crypto(OPENSSL_INIT_NO_ATEXIT, nullptr);

	const auto launcher = Core::Launcher::Create(argc, argv);
	return launcher ? launcher->exec() : 1;
}
