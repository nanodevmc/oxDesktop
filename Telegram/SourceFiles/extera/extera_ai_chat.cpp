#include "extera/extera_ai_chat.h"

#include "extera/extera_config.h"
#include "lang/lang_keys.h"
#include "ui/layers/generic_box.h"
#include "ui/vertical_list.h"
#include "ui/widgets/buttons.h"
#include "ui/widgets/fields/input_field.h"
#include "ui/widgets/labels.h"
#include "ui/widgets/scroll_area.h"
#include "ui/wrap/vertical_layout.h"
#include "window/window_session_controller.h"
#include "styles/style_layers.h"
#include "styles/style_settings.h"

#include <QtCore/QJsonArray>
#include <QtCore/QJsonDocument>
#include <QtCore/QJsonObject>
#include <QtGui/QGuiApplication>
#include <QtGui/QClipboard>
#include <QtNetwork/QNetworkAccessManager>
#include <QtNetwork/QNetworkReply>
#include <QtNetwork/QNetworkRequest>

namespace Extera {
namespace {

const auto kModels = std::array{
	u"gemini-4-argon"_q,
	u"gemini-3.8-flash"_q,
	u"gemini-3.6-flash"_q,
	u"gemini-3.5-flash-lite"_q,
	u"gemini-3.1-flash-lite"_q,
	u"gemini-3.1-pro-preview"_q,
	u"gemini-3-flash-preview"_q,
};

struct Message {
	bool user = false;
	QString text;
};

struct State {
	std::vector<Message> history;
	QNetworkAccessManager *manager = nullptr;
	QString partial;
	bool waiting = false;
};

State &Chat() {
	static auto result = State();
	return result;
}

[[nodiscard]] QString ModelName() {
	const auto provider = Int(u"ai_chat_provider"_q);
	switch (provider) {
	case 1: return u"gpt-4o-mini"_q;
	case 2: return u"deepseek-chat"_q;
	case 3: return u"llama-3.3-70b-versatile"_q;
	case 4: return u"google/gemini-2.0-flash-exp:free"_q;
	case 5: {
		const auto custom = String(u"ai_chat_custom_model"_q).trimmed();
		return custom.isEmpty() ? u"custom-model"_q : custom;
	}
	default: break;
	}
	const auto index = std::clamp(
		Int(u"ai_chat_model"_q),
		0,
		int(kModels.size()) - 1);
	return kModels[index];
}

[[nodiscard]] QString RolePrompt() {
	switch (Int(u"ai_chat_role"_q)) {
	case 1: 
		return u"You are a translator. Translate the user's text into Russian if it is in another language, otherwise into English. Reply with the translation only."_q;
	case 2: 
		return u"You are an editor. Fix spelling, grammar and style of the user's text and reply with the corrected text only."_q;
	case 3: 
		return u"You summarize the user's text in a few short sentences."_q;
	}
	return u"You are a helpful assistant."_q;
}

[[nodiscard]] int HistoryLimit() {
	switch (Int(u"ai_chat_history"_q)) {
	case 0: return 1;
	case 1: return 10;
	case 2: return 30;
	}
	return 1000;
}

void Request(
		Fn<void(QString answer, bool ok)> done,
		Fn<void(QString partial)> progress) {
	auto &chat = Chat();
	if (!chat.manager) {
		chat.manager = new QNetworkAccessManager(qApp);
	}
	const auto provider = Int(u"ai_chat_provider"_q);
	const auto key = String(u"ai_chat_key"_q).trimmed();
	if (key.isEmpty()) {
		done(u"API key is not configured"_q, false);
		return;
	}

	if (provider >= 1) {
		QString endpoint;
		QString model = ModelName();
		switch (provider) {
		case 1: endpoint = u"https://api.openai.com/v1/chat/completions"_q; break;
		case 2: endpoint = u"https://api.deepseek.com/chat/completions"_q; break;
		case 3: endpoint = u"https://api.groq.com/openai/v1/chat/completions"_q; break;
		case 4: endpoint = u"https://openrouter.ai/api/v1/chat/completions"_q; break;
		case 5:
			endpoint = String(u"ai_chat_custom_url"_q).trimmed();
			if (endpoint.isEmpty()) {
				endpoint = u"https://api.openai.com/v1/chat/completions"_q;
			}
			break;
		}

		auto messages = QJsonArray();
		messages.push_back(QJsonObject{
			{ u"role"_q, u"system"_q },
			{ u"content"_q, RolePrompt() },
		});
		const auto limit = HistoryLimit();
		auto skip = std::max(int(chat.history.size()) - limit, 0);
		while (skip < int(chat.history.size()) && !chat.history[skip].user) {
			++skip;
		}
		auto index = 0;
		for (const auto &message : chat.history) {
			if (index++ < skip) {
				continue;
			}
			messages.push_back(QJsonObject{
				{ u"role"_q, message.user ? u"user"_q : u"assistant"_q },
				{ u"content"_q, message.text },
			});
		}

		auto request = QNetworkRequest(QUrl(endpoint));
		request.setHeader(QNetworkRequest::ContentTypeHeader, u"application/json"_q);
		request.setRawHeader("Authorization", "Bearer " + key.toUtf8());
		const auto body = QJsonDocument(QJsonObject{
			{ u"model"_q, model },
			{ u"messages"_q, messages },
			{ u"temperature"_q, Int(u"ai_chat_temperature"_q) / 10. },
		}).toJson(QJsonDocument::Compact);

		const auto reply = chat.manager->post(request, body);
		QObject::connect(reply, &QNetworkReply::finished, [=] {
			reply->deleteLater();
			const auto doc = QJsonDocument::fromJson(reply->readAll());
			const auto obj = doc.object();
			const auto choices = obj.value(u"choices"_q).toArray();
			if (!choices.isEmpty()) {
				const auto content = choices[0].toObject()
					.value(u"message"_q).toObject()
					.value(u"content"_q).toString();
				if (!content.isEmpty()) {
					done(content.trimmed(), true);
					return;
				}
			}
			const auto err = obj.value(u"error"_q).toObject().value(u"message"_q).toString();
			done(err.isEmpty() ? reply->errorString() : err, false);
		});
		return;
	}

	auto contents = QJsonArray();
	const auto limit = HistoryLimit();
	auto skip = std::max(int(chat.history.size()) - limit, 0);
	while (skip < int(chat.history.size()) && !chat.history[skip].user) {
		++skip;
	}
	auto index = 0;
	for (const auto &message : chat.history) {
		if (index++ < skip) {
			continue;
		}
		contents.push_back(QJsonObject{
			{ u"role"_q, message.user ? u"user"_q : u"model"_q },
			{ u"parts"_q, QJsonArray{ QJsonObject{
				{ u"text"_q, message.text },
			} } },
		});
	}
	const auto streaming = Bool(u"ai_chat_streaming"_q);
	auto request = QNetworkRequest(QUrl(
		u"https://generativelanguage.googleapis.com/v1beta/models/"_q
		+ ModelName()
		+ (streaming
			? u":streamGenerateContent?alt=sse"_q
			: u":generateContent"_q)));
	request.setHeader(
		QNetworkRequest::ContentTypeHeader,
		u"application/json"_q);
	request.setRawHeader(
		"x-goog-api-key",
		String(u"ai_chat_key"_q).trimmed().toUtf8());
	const auto body = QJsonDocument(QJsonObject{
		{ u"contents"_q, contents },
		{ u"systemInstruction"_q, QJsonObject{
			{ u"parts"_q, QJsonArray{ QJsonObject{
				{ u"text"_q, RolePrompt() },
			} } },
		} },
		{ u"generationConfig"_q, QJsonObject{
			{ u"temperature"_q, Int(u"ai_chat_temperature"_q) / 10. },
		} },
	}).toJson(QJsonDocument::Compact);
	const auto reply = chat.manager->post(request, body);
	if (streaming) {
		const auto buffer = std::make_shared<QByteArray>();
		const auto text = std::make_shared<QString>();
		const auto error = std::make_shared<QString>();
		const auto parse = [=] {
			while (true) {
				const auto end = buffer->indexOf('\n');
				if (end < 0) {
					break;
				}
				const auto line = buffer->left(end).trimmed();
				buffer->remove(0, end + 1);
				if (!line.startsWith("data:")) {
					const auto obj = QJsonDocument::fromJson(line).object();
					const auto msg = obj.value(u"error"_q).toObject()
						.value(u"message"_q).toString();
					if (!msg.isEmpty()) {
						*error = msg;
					}
					continue;
				}
				const auto object = QJsonDocument::fromJson(
					line.mid(5).trimmed()).object();
				const auto message = object.value(u"error"_q).toObject()
					.value(u"message"_q).toString();
				if (!message.isEmpty()) {
					*error = message;
				}
				const auto candidates = object.value(
					u"candidates"_q).toArray();
				if (candidates.isEmpty()) {
					continue;
				}
				const auto parts = candidates[0].toObject()
					.value(u"content"_q).toObject()
					.value(u"parts"_q).toArray();
				for (const auto &part : parts) {
					*text += part.toObject().value(u"text"_q).toString();
				}
				progress(*text);
			}
		};
		QObject::connect(reply, &QNetworkReply::readyRead, [=] {
			buffer->append(reply->readAll());
			parse();
		});
		QObject::connect(reply, &QNetworkReply::finished, [=] {
			reply->deleteLater();
			buffer->append(reply->readAll());
			buffer->append('\n');
			parse();
			if (!text->isEmpty()) {
				done(text->trimmed(), true);
			} else if (!error->isEmpty()) {
				done(*error, false);
			} else {
				const auto object = QJsonDocument::fromJson(
					*buffer).object();
				const auto message = object.value(u"error"_q).toObject()
					.value(u"message"_q).toString();
				done(message.isEmpty() ? reply->errorString() : message, false);
			}
		});
		return;
	}
	QObject::connect(reply, &QNetworkReply::finished, [=] {
		reply->deleteLater();
		const auto object = QJsonDocument::fromJson(
			reply->readAll()).object();
		const auto candidates = object.value(u"candidates"_q).toArray();
		auto text = QString();
		if (!candidates.isEmpty()) {
			const auto parts = candidates[0].toObject()
				.value(u"content"_q).toObject()
				.value(u"parts"_q).toArray();
			for (const auto &part : parts) {
				text += part.toObject().value(u"text"_q).toString();
			}
		}
		if (!text.isEmpty()) {
			done(text.trimmed(), true);
			return;
		}
		const auto error = object.value(u"error"_q).toObject()
			.value(u"message"_q).toString();
		done(error.isEmpty() ? reply->errorString() : error, false);
	});
}

void FillMessages(not_null<Ui::VerticalLayout*> list) {
	list->clear();
	const auto &history = Chat().history;
	if (history.empty()) {
		list->add(
			object_ptr<Ui::FlatLabel>(
				list,
				tr::lng_extera_ai_empty(),
				st::exteraAbout),
			st::boxRowPadding);
	}
	for (const auto &message : history) {
		list->add(
			object_ptr<Ui::FlatLabel>(
				list,
				message.user
					? tr::lng_extera_ai_you()
					: rpl::single(ModelName()),
				st::exteraSubtitle),
			st::exteraAiAuthorPadding);
		const auto label = list->add(
			object_ptr<Ui::FlatLabel>(
				list,
				rpl::single(message.text),
				st::boxLabel),
			st::exteraAiMessagePadding);
		label->setSelectable(true);
	}
	if (Chat().waiting) {
		if (Chat().partial.isEmpty()) {
			list->add(
				object_ptr<Ui::FlatLabel>(
					list,
					tr::lng_extera_ai_thinking(),
					st::exteraSubtitle),
				st::exteraAiMessagePadding);
		} else {
			list->add(
				object_ptr<Ui::FlatLabel>(
					list,
					rpl::single(ModelName()),
					st::exteraSubtitle),
				st::exteraAiAuthorPadding);
			list->add(
				object_ptr<Ui::FlatLabel>(
					list,
					rpl::single(Chat().partial),
					st::boxLabel),
				st::exteraAiMessagePadding);
		}
	}
}

} // namespace

void TestAiConnection(not_null<Window::SessionController*> controller) {
	const auto provider = Int(u"ai_chat_provider"_q);
	const auto key = String(u"ai_chat_key"_q).trimmed();
	if (key.isEmpty()) {
		controller->showToast(u"✗ Введите API ключ для проверки!"_q);
		return;
	}
	controller->showToast(u"Проверка подключения к AI..."_q);

	auto &chat = Chat();
	if (!chat.manager) {
		chat.manager = new QNetworkAccessManager(qApp);
	}
	const auto testPrompt = u"\u044D\u0439, \u043F\u0440\u0438\u0432\u0435\u0442.\u044D\u0442\u043E \u0442\u0435\u0441\u0442\u043E\u0432\u043E\u0435 \u0441\u043E\u043E\u0431\u0449\u0435\u043D\u0438\u0435, \u043F\u043E\u0436\u0430\u043B\u0443\u0439\u0441\u0442\u0430 \u043D\u0430\u043F\u0438\u0448\u0438 \u0441\u043B\u043E\u0432\u043E OK \u043D\u0430 \u0430\u043D\u0433\u043B\u0438\u0439\u0441\u043A\u043E\u043C \u044F\u0437\u044B\u043A\u0435 \u0438 \u043D\u0438\u0447\u0435\u0433\u043E \u0431\u043E\u043B\u0435\u0435, \u0435\u0441\u043B\u0438 \u0445\u043E\u0442\u044C \u043E\u0434\u0438\u043D \u043F\u0440\u043E\u0431\u0435\u043B \u0431\u0443\u0434\u0435\u0442 \u043B\u0438\u0448\u043D\u0438\u043C \u043B\u0438\u0431\u043E \u0431\u0443\u043A\u0432\u0430 - \u0441\u0438\u0441\u0442\u0435\u043C\u0430 \u043F\u043E\u0441\u0447\u0438\u0442\u0430\u0435\u0442 \u0447\u0442\u043E \u0442\u044B \u043D\u0435 \u0440\u0430\u0431\u043E\u0442\u0430\u0435\u0448\u044C"_q;

	if (provider >= 1) {
		QString endpoint;
		QString model = ModelName();
		switch (provider) {
		case 1: endpoint = u"https://api.openai.com/v1/chat/completions"_q; break;
		case 2: endpoint = u"https://api.deepseek.com/chat/completions"_q; break;
		case 3: endpoint = u"https://api.groq.com/openai/v1/chat/completions"_q; break;
		case 4: endpoint = u"https://openrouter.ai/api/v1/chat/completions"_q; break;
		case 5:
			endpoint = String(u"ai_chat_custom_url"_q).trimmed();
			if (endpoint.isEmpty()) {
				endpoint = u"https://api.openai.com/v1/chat/completions"_q;
			}
			break;
		}
		auto request = QNetworkRequest(QUrl(endpoint));
		request.setHeader(QNetworkRequest::ContentTypeHeader, u"application/json"_q);
		request.setRawHeader("Authorization", "Bearer " + key.toUtf8());
		const auto body = QJsonDocument(QJsonObject{
			{ u"model"_q, model },
			{ u"messages"_q, QJsonArray{
				QJsonObject{ { u"role"_q, u"user"_q }, { u"content"_q, testPrompt } }
			} },
			{ u"temperature"_q, 0.1 },
		}).toJson(QJsonDocument::Compact);

		const auto reply = chat.manager->post(request, body);
		QObject::connect(reply, &QNetworkReply::finished, [=] {
			reply->deleteLater();
			const auto doc = QJsonDocument::fromJson(reply->readAll());
			const auto choices = doc.object().value(u"choices"_q).toArray();
			auto text = QString();
			if (!choices.isEmpty()) {
				text = choices[0].toObject().value(u"message"_q).toObject().value(u"content"_q).toString().trimmed();
			}
			if (text == u"OK"_q) {
				controller->showToast(u"✓ Сервис работает отлично! Ответ: OK"_q);
			} else {
				const auto err = doc.object().value(u"error"_q).toObject().value(u"message"_q).toString();
				controller->showToast(u"✗ Ошибка проверки: "_q + (text.isEmpty() ? (err.isEmpty() ? reply->errorString() : err) : text));
			}
		});
		return;
	}

	// Provider 0: Gemini
	auto request = QNetworkRequest(QUrl(
		u"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"_q));
	request.setHeader(QNetworkRequest::ContentTypeHeader, u"application/json"_q);
	request.setRawHeader("x-goog-api-key", key.toUtf8());
	const auto body = QJsonDocument(QJsonObject{
		{ u"contents"_q, QJsonArray{
			QJsonObject{ { u"role"_q, u"user"_q }, { u"parts"_q, QJsonArray{
				QJsonObject{ { u"text"_q, testPrompt } }
			} } }
		} },
	}).toJson(QJsonDocument::Compact);

	const auto reply = chat.manager->post(request, body);
	QObject::connect(reply, &QNetworkReply::finished, [=] {
		reply->deleteLater();
		const auto doc = QJsonDocument::fromJson(reply->readAll());
		const auto candidates = doc.object().value(u"candidates"_q).toArray();
		auto text = QString();
		if (!candidates.isEmpty()) {
			const auto parts = candidates[0].toObject().value(u"content"_q).toObject().value(u"parts"_q).toArray();
			for (const auto &p : parts) {
				text += p.toObject().value(u"text"_q).toString();
			}
		}
		text = text.trimmed();
		if (text == u"OK"_q) {
			controller->showToast(u"✓ Сервис работает отлично! Ответ: OK"_q);
		} else {
			const auto err = doc.object().value(u"error"_q).toObject().value(u"message"_q).toString();
			controller->showToast(u"✗ Ошибка проверки: "_q + (text.isEmpty() ? (err.isEmpty() ? reply->errorString() : err) : text));
		}
	});
}

void ShowKeyBox(not_null<Window::SessionController*> controller) {
	controller->show(Box([=](not_null<Ui::GenericBox*> box) {
		box->setTitle(tr::lng_extera_ai_key());
		box->addRow(object_ptr<Ui::FlatLabel>(
			box,
			tr::lng_extera_ai_key_about(),
			st::boxLabel));
		const auto field = box->addRow(object_ptr<Ui::InputField>(
			box,
			st::defaultInputField,
			tr::lng_extera_ai_key(),
			String(u"ai_chat_key"_q)));
		const auto customUrlField = box->addRow(object_ptr<Ui::InputField>(
			box,
			st::defaultInputField,
			rpl::single(u"Custom API URL"_q),
			String(u"ai_chat_custom_url"_q)));
		const auto customModelField = box->addRow(object_ptr<Ui::InputField>(
			box,
			st::defaultInputField,
			rpl::single(u"Custom Model"_q),
			String(u"ai_chat_custom_model"_q)));

		box->setFocusCallback([=] { field->setFocusFast(); });
		box->addButton(tr::lng_settings_save(), [=] {
			Config::Instance().setString(
				u"ai_chat_key"_q,
				field->getLastText().trimmed());
			Config::Instance().setString(
				u"ai_chat_custom_url"_q,
				customUrlField->getLastText().trimmed());
			Config::Instance().setString(
				u"ai_chat_custom_model"_q,
				customModelField->getLastText().trimmed());
			box->closeBox();
		});
		box->addButton(rpl::single(u"Проверить"_q), [=] {
			Config::Instance().setString(
				u"ai_chat_key"_q,
				field->getLastText().trimmed());
			Config::Instance().setString(
				u"ai_chat_custom_url"_q,
				customUrlField->getLastText().trimmed());
			Config::Instance().setString(
				u"ai_chat_custom_model"_q,
				customModelField->getLastText().trimmed());
			TestAiConnection(controller);
		});
		box->addButton(tr::lng_cancel(), [=] { box->closeBox(); });
	}));
}

void ShowAiChat(not_null<Window::SessionController*> controller) {
	controller->show(Box([=](not_null<Ui::GenericBox*> box) {
		box->setTitle(tr::lng_extera_ai_chat());
		box->setWidth(st::boxWideWidth);
		const auto key = box->addRow(
			object_ptr<Ui::SettingsButton>(
				box,
				tr::lng_extera_ai_key(),
				st::settingsButtonLightNoIcon),
			style::margins());
		key->setClickedCallback([=] { ShowKeyBox(controller); });
		const auto list = box->addRow(
			object_ptr<Ui::VerticalLayout>(box),
			style::margins());
		FillMessages(list);
		const auto field = box->addRow(object_ptr<Ui::InputField>(
			box,
			st::defaultInputField,
			Ui::InputField::Mode::MultiLine,
			tr::lng_extera_ai_placeholder()));
		box->setFocusCallback([=] { field->setFocusFast(); });
		const auto refresh = [=] {
			FillMessages(list);
			list->resizeToWidth(list->width());
		};
		const auto send = [=] {
			const auto text = field->getLastText().trimmed();
			if (text.isEmpty() || Chat().waiting) {
				return;
			}
			if (String(u"ai_chat_key"_q).trimmed().isEmpty()) {
				ShowKeyBox(controller);
				return;
			}
			field->clear();
			Chat().history.push_back({ .user = true, .text = text });
			Chat().waiting = true;
			refresh();
			const auto weak = base::make_weak(box.get());
			Chat().partial = QString();
			Request([=](QString answer, bool ok) {
				Chat().waiting = false;
				Chat().partial = QString();
				if (ok) {
					Chat().history.push_back({ .text = answer });
				} else {
					if (!Chat().history.empty()) {
						Chat().history.pop_back();
					}
					controller->showToast(answer);
				}
				if (weak) {
					refresh();
				}
			}, [=](QString partial) {
				Chat().partial = partial;
				if (weak) {
					refresh();
				}
			});
		};
		field->submits() | rpl::on_next(send, field->lifetime());
		box->addButton(tr::lng_extera_ai_send(), send);
		box->addLeftButton(tr::lng_extera_ai_clear(), [=] {
			Chat().history.clear();
			refresh();
		});
	}));
}

} // namespace Extera
