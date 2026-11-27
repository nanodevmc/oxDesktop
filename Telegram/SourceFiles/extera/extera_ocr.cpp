#include "extera/extera_ocr.h"

#include "base/weak_ptr.h"
#include "extera/extera_ai_chat.h"
#include "extera/extera_config.h"
#include "extera/extera_lang.h"
#include "extera/extera_ws_proxy.h"
#include "lang/lang_keys.h"
#include "ui/layers/generic_box.h"
#include "ui/new_badges.h"
#include "ui/painter.h"
#include "ui/widgets/buttons.h"
#include "ui/widgets/fields/input_field.h"
#include "ui/widgets/labels.h"
#include "ui/widgets/menu/menu.h"
#include "ui/widgets/menu/menu_item_base.h"
#include "ui/wrap/padding_wrap.h"
#include "ui/wrap/slide_wrap.h"
#include "ui/wrap/vertical_layout.h"
#include "window/window_session_controller.h"
#include "styles/style_boxes.h"
#include "styles/style_layers.h"
#include "styles/style_settings.h"
#include "styles/style_widgets.h"

#include <QtCore/QBuffer>
#include <QtCore/QCoreApplication>
#include <QtCore/QDir>
#include <QtCore/QFile>
#include <QtCore/QFileInfo>
#include <QtCore/QJsonArray>
#include <QtCore/QJsonDocument>
#include <QtCore/QJsonObject>
#include <QtCore/QLocale>
#include <QtCore/QProcess>
#include <QtCore/QRandomGenerator>
#include <QtCore/QStandardPaths>
#include <QtCore/QTemporaryFile>
#include <QtCore/QTimer>
#include <QtCore/QUrl>
#include <QtCore/QUrlQuery>
#include <QtGui/QAction>
#include <QtGui/QClipboard>
#include <QtGui/QGuiApplication>
#include <QtGui/QPainterPath>
#include <QtNetwork/QNetworkAccessManager>
#include <QtNetwork/QNetworkReply>
#include <QtNetwork/QNetworkRequest>

#ifdef Q_OS_WIN
#include <windows.h>
#endif // Q_OS_WIN

namespace Extera::Ocr {
namespace {

constexpr auto kMaxUploadBytes = qsizetype(1024 * 1024);
constexpr auto kPreviewMaxHeight = 160;
constexpr auto kPreviewPadding = 8;
constexpr auto kCardRadius = 14.;
constexpr auto kPreviewRadius = 10.;
constexpr auto kPromptOcr = "Extract all text from this image accurately, "
	"preserving line breaks and structure. Reply with the extracted text "
	"only, without explanations or markdown formatting.";

enum class OcrStatus {
	Recognizing,
	Done,
	Empty,
	Error,
};

enum class OcrProfile {
	Cyrillic,
	Latin,
};

struct UiTexts {
	QString title;
	QString recognizingLocal;
	QString recognizing;
	QString readyLocal;
	QString ready;
	QString empty;
	QString errorPrefix;
	QString noTextToTranslate;
	QString noTextToCopy;
	QString textCopied;
	QString translationCopied;
	QString translate;
	QString copy;
	QString copyTranslation;
	QString close;
	QString translationHeader;
	QString translating;
	QString translationError;
	QString placeholder;
	QString noImageError;
	QString invalidImageError;
	QString badTranslatorReply;
	QString translateFailed;
};

struct RapidOcrConfig {
	QString binaryPath;
	QString workingDir;
	QString recFile;
	QString keysFile;
};

struct State {
	QNetworkAccessManager *manager = nullptr;
};

[[nodiscard]] QNetworkAccessManager *NetworkManager() {
	static auto state = State();
	if (!state.manager) {
		state.manager = new QNetworkAccessManager(qApp);
	}
	Extera::WsProxy::ApplyHttpProxy(state.manager);
	return state.manager;
}

[[nodiscard]] QString TargetLanguageCode() {
	auto code = Lang::Id().trimmed().toLower();
	if (code.isEmpty()) {
		code = QLocale::system().bcp47Name().left(2).toLower();
	}
	if (code.contains(u'-')) {
		code = code.section(u'-', 0, 0);
	}
	if (code.contains(u'_')) {
		code = code.section(u'_', 0, 0);
	}
	if (code.size() > 2) {
		code = code.left(2);
	}
	return code.isEmpty() ? u"en"_q : code;
}

[[nodiscard]] UiTexts Strings() {
	const auto lang = TargetLanguageCode();
	auto tr = [&](std::string_view key, const QString &fallback) -> QString {
		const auto res = Extera::LookupCustom(lang, key);
		if (!res.isEmpty()) {
			return res;
		}
		const auto ru = Extera::LookupRussian(key);
		if (!ru.isEmpty()) {
			return ru;
		}
		return fallback;
	};

	return {
		.title = tr("lng_oxd_ocr_title", u"Text Recognition"_q),
		.recognizingLocal = tr("lng_oxd_ocr_recognizing_local", u"Recognizing..."_q),
		.recognizing = tr("lng_oxd_ocr_recognizing", u"Extracting text..."_q),
		.readyLocal = tr("lng_oxd_ocr_ready_local", u"Done (offline)"_q),
		.ready = tr("lng_oxd_ocr_ready", u"Done"_q),
		.empty = tr("lng_oxd_ocr_empty", u"No text found in image"_q),
		.errorPrefix = tr("lng_oxd_ocr_error_prefix", u"Error: "_q),
		.noTextToTranslate = tr("lng_oxd_ocr_no_text_translate", u"No text to translate"_q),
		.noTextToCopy = tr("lng_oxd_ocr_no_text_copy", u"No text to copy"_q),
		.textCopied = tr("lng_oxd_ocr_text_copied", u"Text copied"_q),
		.translationCopied = tr("lng_oxd_ocr_translation_copied", u"Translation copied"_q),
		.translate = tr("lng_oxd_ocr_translate", u"Translate"_q),
		.copy = tr("lng_oxd_ocr_copy", u"Copy"_q),
		.copyTranslation = tr("lng_oxd_ocr_copy_translation", u"Copy translation"_q),
		.close = tr("lng_oxd_ocr_close", u"Close"_q),
		.translationHeader = tr("lng_oxd_ocr_translation_header", u"Translation"_q),
		.translating = tr("lng_oxd_ocr_translating", u"Translating..."_q),
		.translationError = tr("lng_oxd_ocr_translation_error", u"Translation error"_q),
		.placeholder = tr("lng_oxd_ocr_placeholder", u"Extracted text..."_q),
		.noImageError = tr("lng_oxd_ocr_no_image_error", u"Image is missing."_q),
		.invalidImageError = tr("lng_oxd_ocr_invalid_image_error", u"Failed to prepare image."_q),
		.badTranslatorReply = tr("lng_oxd_ocr_bad_translator_reply", u"Invalid translator response"_q),
		.translateFailed = tr("lng_oxd_ocr_translate_failed", u"Failed to translate text"_q),
	};
}

[[nodiscard]] OcrProfile DefaultProfile() {
	const auto lang = TargetLanguageCode();
	if (lang == u"es"_q
		|| lang == u"de"_q
		|| lang == u"fr"_q
		|| lang == u"pt"_q
		|| lang == u"it"_q
		|| lang == u"nl"_q
		|| lang == u"pl"_q
		|| lang == u"cs"_q
		|| lang == u"tr"_q) {
		return OcrProfile::Latin;
	}
	return OcrProfile::Cyrillic;
}

[[nodiscard]] std::optional<RapidOcrConfig> LocateRapidOcr(OcrProfile profile) {
#ifdef Q_OS_WIN
	const auto binName = u"RapidOcrOnnx.exe"_q;
#else // Q_OS_WIN
	const auto binName = u"RapidOcrOnnx"_q;
#endif // Q_OS_WIN
	const auto recFile = (profile == OcrProfile::Latin)
		? u"latin_rec.onnx"_q
		: u"cyr_rec.onnx"_q;
	const auto keysFile = (profile == OcrProfile::Latin)
		? u"latin_keys.txt"_q
		: u"cyr_keys.txt"_q;

	const auto appDir = QCoreApplication::applicationDirPath();
	const auto candidates = QStringList{
		appDir + u"/ocr"_q,
		appDir + u"/../ocr"_q,
		appDir + u"/ocr_runtime"_q,
		cWorkingDir() + u"ocr"_q,
	};
	for (const auto &dirPath : candidates) {
		const auto cleanDir = QDir::cleanPath(dirPath);
		const auto bin = cleanDir + '/' + binName;
		const auto models = cleanDir + u"/models"_q;
		if (QFileInfo::exists(bin)
			&& QFileInfo::exists(models + u"/det.onnx"_q)
			&& QFileInfo::exists(models + u"/cls.onnx"_q)
			&& QFileInfo::exists(models + '/' + recFile)
			&& QFileInfo::exists(models + '/' + keysFile)) {
			return RapidOcrConfig{
				.binaryPath = bin,
				.workingDir = cleanDir,
				.recFile = recFile,
				.keysFile = keysFile,
			};
		}
	}
	return std::nullopt;
}

[[nodiscard]] QImage PrepareImageForOcr(const QImage &image) {
	if (image.isNull()) {
		return image;
	}
	auto result = (image.format() == QImage::Format_RGB888
		|| image.format() == QImage::Format_ARGB32)
		? image
		: image.convertToFormat(QImage::Format_RGB888);
	const auto minDim = std::min(result.width(), result.height());
	const auto maxDim = std::max(result.width(), result.height());
	if (minDim > 0 && minDim < 280 && maxDim < 500) {
		result = result.scaled(
			result.size() * 2,
			Qt::KeepAspectRatio,
			Qt::SmoothTransformation);
	} else if (maxDim > 1280) {
		result = result.scaled(
			1280,
			1280,
			Qt::KeepAspectRatio,
			Qt::SmoothTransformation);
	}
	return result;
}

[[nodiscard]] QString ProcessSafeFilePath(const QString &filePath) {
#ifdef Q_OS_WIN
	const auto native = QDir::toNativeSeparators(filePath);
	const auto wide = native.toStdWString();
	const auto needed = GetShortPathNameW(wide.c_str(), nullptr, 0);
	if (needed > 0) {
		auto buf = std::wstring(needed, L'\0');
		const auto written = GetShortPathNameW(wide.c_str(), buf.data(), needed);
		if (written > 0 && written < needed) {
			buf.resize(written);
			return QString::fromStdWString(buf);
		}
	}
	return native;
#else // Q_OS_WIN
	return filePath;
#endif // Q_OS_WIN
}

[[nodiscard]] QString ParseRapidOcrOutput(const QString &stdoutText) {
	const auto marker = u"=====End detect====="_q;
	const auto idx = stdoutText.indexOf(marker);
	auto body = (idx >= 0)
		? stdoutText.mid(idx + marker.size())
		: stdoutText;
	body.replace(u"\r\n"_q, u"\n"_q);
	const auto lines = body.split(u'\n');
	auto out = QStringList();
	for (const auto &line : lines) {
		const auto trimmed = line.trimmed();
		if (trimmed.isEmpty() || trimmed.startsWith(u"FullDetectTime("_q)) {
			continue;
		}
		if (trimmed.startsWith(u"textLine["_q)) {
			const auto openParen = trimmed.indexOf(u'(');
			const auto closeParen = trimmed.lastIndexOf(u')');
			if (openParen >= 0 && closeParen > openParen) {
				const auto content = trimmed.mid(openParen + 1, closeParen - openParen - 1).trimmed();
				if (!content.isEmpty()) {
					out.push_back(content);
				}
				continue;
			}
		}
		out.push_back(trimmed);
	}
	if (out.isEmpty() && idx >= 0) {
		const auto allLines = stdoutText.split(u'\n');
		for (const auto &line : allLines) {
			const auto trimmed = line.trimmed();
			if (trimmed.startsWith(u"textLine["_q)) {
				const auto openParen = trimmed.indexOf(u'(');
				const auto closeParen = trimmed.lastIndexOf(u')');
				if (openParen >= 0 && closeParen > openParen) {
					const auto content = trimmed.mid(openParen + 1, closeParen - openParen - 1).trimmed();
					if (!content.isEmpty()) {
						out.push_back(content);
					}
				}
			}
		}
	}
	return out.join(u'\n').trimmed();
}

[[nodiscard]] QString FindTesseractBinary() {
	auto path = QStandardPaths::findExecutable(u"tesseract"_q);
	if (!path.isEmpty()) {
		return path;
	}
#ifdef Q_OS_WIN
	const auto extraPaths = QStringList{
		u"C:/Program Files/Tesseract-OCR"_q,
		u"C:/Program Files (x86)/Tesseract-OCR"_q,
	};
#elif defined(Q_OS_MAC)
	const auto extraPaths = QStringList{
		u"/opt/homebrew/bin"_q,
		u"/usr/local/bin"_q,
	};
#else
	const auto extraPaths = QStringList{
		u"/usr/bin"_q,
		u"/usr/local/bin"_q,
	};
#endif
	return QStandardPaths::findExecutable(u"tesseract"_q, extraPaths);
}

[[nodiscard]] QByteArray EncodePngUnderLimit(
		const QImage &image,
		qsizetype maxBytes) {
	if (image.isNull()) {
		return QByteArray();
	}
	auto current = image;
	for (auto attempt = 0; attempt != 10; ++attempt) {
		auto bytes = QByteArray();
		auto buffer = QBuffer(&bytes);
		buffer.open(QIODevice::WriteOnly);
		if (!current.save(&buffer, "PNG")) {
			return QByteArray();
		}
		if (bytes.size() <= maxBytes
			|| std::max(current.width(), current.height()) <= 256) {
			return bytes;
		}
		const auto nextWidth = std::max(256, int(current.width() * 0.78));
		const auto nextHeight = std::max(256, int(current.height() * 0.78));
		current = current.scaled(
			nextWidth,
			nextHeight,
			Qt::KeepAspectRatio,
			Qt::SmoothTransformation);
	}
	return QByteArray();
}

void ExtractViaOcrSpace(
		const QByteArray &pngBytes,
		Fn<void(QString text, QString error)> done) {
	const auto manager = NetworkManager();
	const auto boundary = QByteArray("----OxDesktopOcrBoundary")
		+ QByteArray::number(QRandomGenerator::global()->generate64(), 16);

	auto body = QByteArray();
	const auto appendField = [&](const QByteArray &name, const QByteArray &value) {
		body.append("--" + boundary + "\r\n");
		body.append("Content-Disposition: form-data; name=\"" + name + "\"\r\n\r\n");
		body.append(value + "\r\n");
	};
	appendField("apikey", "helloworld");
	appendField("OCREngine", "2");
	appendField("language", "auto");

	body.append("--" + boundary + "\r\n");
	body.append(
		"Content-Disposition: form-data; name=\"file\"; filename=\"image.png\"\r\n");
	body.append("Content-Type: image/png\r\n\r\n");
	body.append(pngBytes);
	body.append("\r\n--" + boundary + "--\r\n");

	auto request = QNetworkRequest(QUrl(u"https://api.ocr.space/parse/image"_q));
	request.setHeader(
		QNetworkRequest::ContentTypeHeader,
		QByteArray("multipart/form-data; boundary=" + boundary));
	Extera::WsProxy::PrepareFrontedRequest(request);

	const auto reply = manager->post(request, body);
	QObject::connect(reply, &QNetworkReply::finished, [=] {
		reply->deleteLater();
		const auto doc = QJsonDocument::fromJson(reply->readAll());
		if (!doc.isObject()) {
			done(
				QString(),
				(reply->error() != QNetworkReply::NoError)
					? reply->errorString()
					: u"OCR.space invalid response"_q);
			return;
		}
		const auto obj = doc.object();
		if (obj.value(u"IsErroredOnProcessing"_q).toBool()) {
			auto err = QString();
			const auto msgVal = obj.value(u"ErrorMessage"_q);
			if (msgVal.isArray()) {
				for (const auto &entry : msgVal.toArray()) {
					const auto part = entry.toString().trimmed();
					if (!part.isEmpty()) {
						if (!err.isEmpty()) {
							err.append(u"; "_q);
						}
						err.append(part);
					}
				}
			} else {
				err = msgVal.toString().trimmed();
			}
			if (err.isEmpty()) {
				err = obj.value(u"ErrorDetails"_q).toString().trimmed();
			}
			done(QString(), err.isEmpty() ? u"OCR.space processing error"_q : err);
			return;
		}
		const auto results = obj.value(u"ParsedResults"_q).toArray();
		auto text = QString();
		for (const auto &entry : results) {
			const auto parsed = entry.toObject()
				.value(u"ParsedText"_q)
				.toString();
			if (!parsed.isEmpty()) {
				if (!text.isEmpty() && !text.endsWith(u'\n')) {
					text.append(u'\n');
				}
				text.append(parsed);
			}
		}
		done(text.trimmed(), QString());
	});
}

void ExtractTextCloud(
		const QImage &image,
		Fn<void(QString text, QString error, bool isLocal)> done) {
	const auto pngBytes = EncodePngUnderLimit(image, kMaxUploadBytes);
	if (pngBytes.isEmpty()) {
		done(QString(), Strings().invalidImageError, false);
		return;
	}
	const auto wrapped = [done = std::move(done)](QString text, QString error) {
		done(std::move(text), std::move(error), false);
	};
	const auto key = Extera::String(u"ai_chat_key"_q).trimmed();
	if (!key.isEmpty()) {
		Extera::SendPrompt(
			QString::fromLatin1(kPromptOcr),
			pngBytes,
			wrapped);
		return;
	}
	ExtractViaOcrSpace(pngBytes, wrapped);
}

void RunProcessOcr(
		const QString &program,
		const QString &workingDir,
		const QStringList &args,
		const QImage &originalImage,
		std::shared_ptr<QTemporaryFile> tempFile,
		Fn<QString(const QString &)> parseOutput,
		Fn<void(QString text, QString error, bool isLocal)> done,
		Fn<void()> onFallback) {
	const auto process = new QProcess(qApp);
	if (!workingDir.isEmpty()) {
		process->setWorkingDirectory(workingDir);
	}
	const auto handled = std::make_shared<bool>(false);
	const auto timer = new QTimer(process);
	timer->setSingleShot(true);
	QObject::connect(timer, &QTimer::timeout, [=] {
		if (*handled) {
			return;
		}
		*handled = true;
		(void)tempFile;
		process->kill();
		process->deleteLater();
		onFallback();
	});

	QObject::connect(
		process,
		&QProcess::finished,
		[=](int exitCode, QProcess::ExitStatus exitStatus) {
			timer->stop();
			process->deleteLater();
			if (*handled) {
				return;
			}
			*handled = true;
			(void)tempFile;
			if (exitStatus == QProcess::NormalExit && exitCode == 0) {
				const auto raw = QString::fromUtf8(
					process->readAllStandardOutput());
				done(parseOutput(raw), QString(), true);
				return;
			}
			(void)originalImage;
			onFallback();
		});
	QObject::connect(
		process,
		&QProcess::errorOccurred,
		[=](QProcess::ProcessError) {
			timer->stop();
			if (*handled) {
				return;
			}
			*handled = true;
			(void)tempFile;
			process->deleteLater();
			onFallback();
		});
	timer->start(12000);
	process->start(program, args);
}

void ExtractWithTesseractOrCloud(
		const QImage &image,
		OcrProfile profile,
		Fn<void(QString text, QString error, bool isLocal)> done) {
	const auto tesseract = FindTesseractBinary();
	if (tesseract.isEmpty()) {
		ExtractTextCloud(image, std::move(done));
		return;
	}
	auto tempFile = std::make_shared<QTemporaryFile>(
		QDir::tempPath() + u"/ox_ocr_XXXXXX.png"_q);
	const auto prepared = PrepareImageForOcr(image);
	if (!tempFile->open() || !prepared.save(tempFile.get(), "PNG")) {
		ExtractTextCloud(image, std::move(done));
		return;
	}
	const auto filePath = tempFile->fileName();
	tempFile->flush();
	tempFile->close();

	const auto langs = u"rus+eng+ukr+bel+spa+deu+fra"_q;
	RunProcessOcr(
		tesseract,
		QString(),
		QStringList{
			filePath,
			u"stdout"_q,
			u"--oem"_q,
			u"1"_q,
			u"--psm"_q,
			u"3"_q,
			u"-l"_q,
			langs,
		},
		image,
		tempFile,
		[](const QString &raw) { return raw.trimmed(); },
		done,
		[=] { ExtractTextCloud(image, done); });
}

void ExtractTextInternal(
		const QImage &image,
		OcrProfile profile,
		Fn<void(QString text, QString error, bool isLocal)> done) {
	if (image.isNull()) {
		done(QString(), Strings().noImageError, false);
		return;
	}

	if (const auto rapid = LocateRapidOcr(profile)) {
		auto tempFile = std::make_shared<QTemporaryFile>(
			QDir::tempPath() + u"/ox_ocr_XXXXXX.png"_q);
		const auto prepared = PrepareImageForOcr(image);
		if (tempFile->open() && prepared.save(tempFile.get(), "PNG")) {
			const auto filePath = ProcessSafeFilePath(tempFile->fileName());
			tempFile->flush();
			tempFile->close();

			const auto args = QStringList{
				u"-d"_q, u"models"_q,
				u"-1"_q, u"det.onnx"_q,
				u"-2"_q, u"cls.onnx"_q,
				u"-3"_q, rapid->recFile,
				u"-4"_q, rapid->keysFile,
				u"-i"_q, filePath,
				u"-a"_q, u"0"_q,
				u"-t"_q, u"2"_q,
			};
			RunProcessOcr(
				rapid->binaryPath,
				rapid->workingDir,
				args,
				image,
				tempFile,
				&ParseRapidOcrOutput,
				done,
				[=] { ExtractWithTesseractOrCloud(image, profile, done); });
			return;
		}
	}

	ExtractWithTesseractOrCloud(image, profile, std::move(done));
}

void TranslateText(
		const QString &text,
		const QString &targetLang,
		Fn<void(QString translated, QString detectedLang, QString error)> done) {
	const auto manager = NetworkManager();
	auto url = QUrl(u"https://translate.googleapis.com/translate_a/single"_q);
	auto query = QUrlQuery();
	query.addQueryItem(u"client"_q, u"gtx"_q);
	query.addQueryItem(u"sl"_q, u"auto"_q);
	query.addQueryItem(u"tl"_q, targetLang);
	query.addQueryItem(u"dt"_q, u"t"_q);
	query.addQueryItem(u"q"_q, text);
	url.setQuery(query);

	auto request = QNetworkRequest(url);
	Extera::WsProxy::PrepareFrontedRequest(request);
	const auto reply = manager->get(request);
	QObject::connect(reply, &QNetworkReply::finished, [=] {
		reply->deleteLater();
		if (reply->error() != QNetworkReply::NoError) {
			done(QString(), QString(), reply->errorString());
			return;
		}
		const auto doc = QJsonDocument::fromJson(reply->readAll());
		if (!doc.isArray() || doc.array().isEmpty()) {
			done(QString(), QString(), Strings().badTranslatorReply);
			return;
		}
		const auto root = doc.array();
		const auto segments = root[0].toArray();
		auto translated = QString();
		for (const auto &segment : segments) {
			const auto pair = segment.toArray();
			if (!pair.isEmpty()) {
				translated.append(pair[0].toString());
			}
		}
		const auto detected = (root.size() > 2)
			? root[2].toString().trimmed()
			: QString();
		translated = translated.trimmed();
		if (translated.isEmpty()) {
			done(QString(), detected, Strings().translateFailed);
			return;
		}
		done(translated, detected, QString());
	});
}

void PaintSurfaceCard(not_null<Ui::RpWidget*> widget, float64 radius = kCardRadius) {
	widget->paintRequest() | rpl::on_next([=] {
		auto p = QPainter(widget);
		auto hq = PainterHighQualityEnabler(p);
		p.setPen(Qt::NoPen);
		p.setBrush(st::windowBgOver);
		p.drawRoundedRect(widget->rect(), radius, radius);
	}, widget->lifetime());
}

} // namespace

void AttachNewBadge(not_null<Ui::Menu::Menu*> menu, QAction *action) {
	if (!action) {
		return;
	}
	const auto item = menu->itemForAction(action);
	if (!item) {
		return;
	}
	const auto &st = menu->st();
	const auto rightPad = st.itemPadding.right();
	const auto badge = Ui::NewBadge::CreateNewBadge(
		item,
		tr::lng_bot_side_menu_new());
	const auto badgeWidth = std::max(badge->width(), 36);
	const auto textWidth = st.itemStyle.font->width(action->text());
	const auto neededWidth = std::clamp(
		st.itemPadding.left()
			+ textWidth
			+ st.itemRightSkip
			+ badgeWidth
			+ rightPad,
		st.widthMin,
		st.widthMax);
	item->setMinWidth(std::max(item->minWidth(), neededWidth));
	rpl::combine(
		item->sizeValue(),
		badge->sizeValue()
	) | rpl::on_next([=](QSize itemSize, QSize badgeSize) {
		badge->moveToRight(
			rightPad,
			(itemSize.height() - badgeSize.height()) / 2,
			itemSize.width());
	}, badge->lifetime());
}

void ExtractText(
		const QImage &image,
		Fn<void(QString text, QString error)> done) {
	ExtractTextInternal(
		image,
		DefaultProfile(),
		[done = std::move(done)](QString text, QString error, bool) {
			done(std::move(text), std::move(error));
		});
}

void ExtractAndShowBox(
		not_null<Window::SessionController*> controller,
		const QImage &image) {
	controller->show(Box([=](not_null<Ui::GenericBox*> box) {
		const auto strings = Strings();
		box->setWidth(st::boxWideWidth * 5 / 4);
		box->setTitle(rpl::single(strings.title));
		box->addTopButton(st::boxTitleClose, [=] { box->closeBox(); });

		const auto content = box->verticalLayout();

		if (!image.isNull()) {
			const auto previewHeight = std::clamp(
				image.height() + kPreviewPadding * 2,
				88,
				kPreviewMaxHeight);
			const auto preview = content->add(
				object_ptr<Ui::RpWidget>(content),
				style::margins(16, 4, 16, 10));
			preview->resize(preview->width(), previewHeight);
			preview->paintRequest() | rpl::on_next([=] {
				auto p = QPainter(preview);
				auto hq = PainterHighQualityEnabler(p);
				const auto outer = preview->rect();
				p.setPen(Qt::NoPen);
				p.setBrush(st::windowBgOver);
				p.drawRoundedRect(outer, kCardRadius, kCardRadius);

				const auto inner = outer.adjusted(
					kPreviewPadding,
					kPreviewPadding,
					-kPreviewPadding,
					-kPreviewPadding);
				if (inner.width() <= 0 || inner.height() <= 0) {
					return;
				}
				const auto dpr = preview->devicePixelRatioF();
				const auto scaled = image.scaled(
					inner.size() * dpr,
					Qt::KeepAspectRatio,
					Qt::SmoothTransformation);
				const auto targetSize = QSizeF(scaled.size()) / dpr;
				const auto targetRect = QRectF(
					inner.x() + (inner.width() - targetSize.width()) / 2.,
					inner.y() + (inner.height() - targetSize.height()) / 2.,
					targetSize.width(),
					targetSize.height());
				auto clip = QPainterPath();
				clip.addRoundedRect(targetRect, kPreviewRadius, kPreviewRadius);
				p.setClipPath(clip);
				p.drawImage(targetRect, scaled);
			}, preview->lifetime());
		}

		const auto activeProfile = std::make_shared<OcrProfile>(DefaultProfile());
		const auto requestGen = std::make_shared<int>(0);

		const auto statusState = std::make_shared<OcrStatus>(
			OcrStatus::Recognizing);
		const auto statusCard = content->add(
			object_ptr<Ui::VerticalLayout>(content),
			style::margins(16, 0, 16, 10));
		statusCard->paintRequest() | rpl::on_next([=] {
			auto p = QPainter(statusCard);
			auto hq = PainterHighQualityEnabler(p);
			p.setPen(Qt::NoPen);
			p.setBrush(st::windowBgOver);
			p.drawRoundedRect(statusCard->rect(), 12., 12.);

			auto color = st::windowSubTextFg->c;
			if (*statusState == OcrStatus::Done) {
				color = st::windowActiveTextFg->c;
			} else if (*statusState == OcrStatus::Error) {
				color = QColor(0xe5, 0x53, 0x4b);
			} else if (*statusState == OcrStatus::Recognizing) {
				color = st::windowActiveTextFg->c;
				color.setAlphaF(0.65);
			}
			p.setBrush(color);
			p.drawEllipse(QPointF(18., statusCard->height() / 2.), 4., 4.);
		}, statusCard->lifetime());

		const auto statusLabel = statusCard->add(
			object_ptr<Ui::FlatLabel>(
				statusCard,
				LocateRapidOcr(*activeProfile).has_value()
					? strings.recognizingLocal
					: strings.recognizing,
				st::exteraSubtitle),
			style::margins(30, 10, 14, 10));

		const auto textCard = content->add(
			object_ptr<Ui::VerticalLayout>(content),
			style::margins(16, 0, 16, 10));
		PaintSurfaceCard(textCard);

		const auto field = textCard->add(
			object_ptr<Ui::InputField>(
				textCard,
				st::defaultInputField,
				Ui::InputField::Mode::MultiLine,
				rpl::single(strings.placeholder)),
			style::margins(14, 8, 14, 12));
		field->setMinHeight(92);
		field->setMaxHeight(220);

		const auto translationWrap = content->add(
			object_ptr<Ui::SlideWrap<Ui::VerticalLayout>>(
				content,
				object_ptr<Ui::VerticalLayout>(content),
				style::margins(16, 0, 16, 10)));
		translationWrap->toggle(false, anim::type::instant);
		const auto translationCard = translationWrap->entity();
		PaintSurfaceCard(translationCard);

		const auto translationTitle = translationCard->add(
			object_ptr<Ui::FlatLabel>(
				translationCard,
				strings.translationHeader,
				st::exteraSubtitle),
			style::margins(14, 12, 14, 4));
		const auto translationLabel = translationCard->add(
			object_ptr<Ui::FlatLabel>(
				translationCard,
				QString(),
				st::boxLabel),
			style::margins(14, 0, 14, 8));
		translationLabel->setSelectable(true);

		const auto translatedText = std::make_shared<QString>();
		const auto copyTranslatedBtn = translationCard->add(
			object_ptr<Ui::LinkButton>(
				translationCard,
				strings.copyTranslation,
				st::boxLinkButton),
			style::margins(14, 0, 14, 12));
		copyTranslatedBtn->setClickedCallback([=] {
			if (!translatedText->isEmpty()) {
				QGuiApplication::clipboard()->setText(*translatedText);
				controller->showToast(strings.translationCopied);
			}
		});

		const auto translating = std::make_shared<bool>(false);
		const auto boxWeak = base::make_weak(box.get());

		const auto runOcr = [=](OcrProfile profile) {
			*activeProfile = profile;
			const auto myGen = ++(*requestGen);
			*statusState = OcrStatus::Recognizing;
			statusLabel->setText(LocateRapidOcr(profile).has_value()
				? strings.recognizingLocal
				: strings.recognizing);
			statusCard->update();

			ExtractTextInternal(
				image,
				profile,
				[=](QString text, QString error, bool isLocal) {
					if (!boxWeak || myGen != *requestGen) {
						return;
					}
					if (!error.isEmpty()) {
						*statusState = OcrStatus::Error;
						statusLabel->setText(strings.errorPrefix + error);
						statusCard->update();
						return;
					}
					if (text.isEmpty()) {
						*statusState = OcrStatus::Empty;
						statusLabel->setText(strings.empty);
						field->setText(QString());
						statusCard->update();
						return;
					}
					*statusState = OcrStatus::Done;
					statusLabel->setText(isLocal ? strings.readyLocal : strings.ready);
					statusCard->update();
					field->setText(text);
					field->setFocusFast();
				});
		};

		box->setFocusCallback([=] { field->setFocusFast(); });

		box->addLeftButton(rpl::single(strings.translate), [=] {
			if (*translating) {
				return;
			}
			const auto sourceText = field->getLastText().trimmed();
			if (sourceText.isEmpty()) {
				controller->showToast(strings.noTextToTranslate);
				return;
			}
			*translating = true;
			*translatedText = QString();
			const auto targetLang = TargetLanguageCode();
			translationTitle->setText(
				u"%1 (%2)..."_q.arg(
					strings.translationHeader,
					targetLang.toUpper()));
			translationLabel->setText(strings.translating);
			copyTranslatedBtn->hide();
			translationWrap->toggle(true, anim::type::normal);

			TranslateText(
				sourceText,
				targetLang,
				[=](QString translated, QString detectedLang, QString error) {
					*translating = false;
					if (!boxWeak) {
						return;
					}
					if (!error.isEmpty()) {
						translationTitle->setText(strings.translationError);
						translationLabel->setText(error);
						copyTranslatedBtn->hide();
						return;
					}
					*translatedText = translated;
					const auto header = detectedLang.isEmpty()
						? u"%1 (%2)"_q.arg(
							strings.translationHeader,
							targetLang.toUpper())
						: u"%1 (%2 \u2192 %3)"_q.arg(
							strings.translationHeader,
							detectedLang.toUpper(),
							targetLang.toUpper());
					translationTitle->setText(header);
					translationLabel->setText(translated);
					copyTranslatedBtn->show();
				});
		});

		box->addButton(rpl::single(strings.copy), [=] {
			const auto text = field->getLastText().trimmed();
			if (text.isEmpty()) {
				controller->showToast(strings.noTextToCopy);
				return;
			}
			QGuiApplication::clipboard()->setText(text);
			controller->showToast(strings.textCopied);
		});

		box->addButton(rpl::single(strings.close), [=] { box->closeBox(); });

		runOcr(*activeProfile);
	}));
}

} // namespace Extera::Ocr
