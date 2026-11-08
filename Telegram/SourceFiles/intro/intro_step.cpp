/*
This file is part of Telegram Desktop,
the official desktop application for the Telegram messaging service.

For license and copyright information please follow this link:
https://github.com/telegramdesktop/tdesktop/blob/master/LEGAL
*/
#include "intro/intro_step.h"

#include "intro/intro_widget.h"
#include "intro/intro_signup.h"
#include "storage/localstorage.h"
#include "storage/storage_account.h"
#include "lang/lang_keys.h"
#include "lang/lang_instance.h"
#include "lang/lang_cloud_manager.h"
#include "main/main_account.h"
#include "main/main_app_config.h"
#include "main/main_domain.h"
#include "main/main_session.h"
#include "main/main_session_settings.h"
#include "boxes/abstract_box.h"
#include "core/application.h"
#include "core/core_settings.h"
#include "apiwrap.h"
#include "api/api_peer_photo.h"
#include "mainwindow.h"
#include "ui/boxes/confirm_box.h"
#include "ui/text/text_utilities.h"
#include "ui/widgets/labels.h"
#include "ui/painter.h"
#include "ui/wrap/fade_wrap.h"
#include "ui/effects/slide_animation.h"
#include "ui/ui_utility.h"
#include "data/data_user.h"
#include "data/data_auto_download.h"
#include "data/data_session.h"
#include "data/data_chat_filters.h"
#include "window/window_controller.h"
#include "styles/style_intro.h"
#include "styles/style_window.h"

namespace Intro {
namespace details {
namespace {

void PrepareSupportMode(not_null<Main::Session*> session) {
	using ::Data::AutoDownload::Full;

	anim::SetDisabled(true);
	Core::App().settings().setDesktopNotify(false);
	Core::App().settings().setSoundNotify(false);
	Core::App().settings().setFlashBounceNotify(false);
	Core::App().saveSettings();

	session->settings().autoDownload() = Full::FullDisabled();
	session->saveSettings();
}

} // namespace

Step::CoverAnimation::~CoverAnimation() = default;

Step::Step(
	QWidget *parent,
	not_null<Main::Account*> account,
	not_null<Data*> data,
	bool hasCover)
: RpWidget(parent)
, _account(account)
, _data(data)
, _hasCover(hasCover)
, _title(this, _hasCover ? st::introCoverTitle : st::introTitle)
, _description(
	this,
	object_ptr<Ui::FlatLabel>(
		this,
		_hasCover
			? st::introCoverDescription
			: st::introDescription)) {
	hide();
	style::PaletteChanged(
	) | rpl::on_next([=] {
		if (!_coverMask.isNull()) {
			_coverMask = QPixmap();
			prepareCoverMask();
		}
	}, lifetime());

	_errorText.value(
	) | rpl::on_next([=](const QString &text) {
		refreshError(text);
	}, lifetime());

	_titleText.value(
	) | rpl::on_next([=](const QString &text) {
		_title->setText(text);
		accessibilityNameChanged();
		updateLabelsPosition();
	}, lifetime());

	_descriptionText.value(
	) | rpl::on_next([=](const TextWithEntities &text) {
		const auto label = _description->entity();
		const auto hasSpoiler = ranges::contains(
			text.entities,
			EntityType::Spoiler,
			&EntityInText::type);
		label->setMarkedText(text);
		label->setAttribute(Qt::WA_TransparentForMouseEvents, hasSpoiler);
		accessibilityDescriptionChanged();
		updateLabelsPosition();
	}, lifetime());
}

Step::~Step() = default;

MTP::Sender &Step::api() const {
	if (!_api) {
		_api.emplace(&_account->mtp());
	}
	return *_api;
}

void Step::apiClear() {
	_api.reset();
}

rpl::producer<QString> Step::nextButtonText() const {
	return tr::lng_intro_next();
}

rpl::producer<const style::RoundButton*> Step::nextButtonStyle() const {
	return rpl::single((const style::RoundButton*)(nullptr));
}

rpl::producer<> Step::nextButtonFocusRequests() const {
	return rpl::never();
}

void Step::goBack() {
	if (_goCallback) {
		_goCallback(nullptr, StackAction::Back, Animate::Back);
	}
}

void Step::goNext(Step *step) {
	if (_goCallback) {
		_goCallback(step, StackAction::Forward, Animate::Forward);
	}
}

void Step::goReplace(Step *step, Animate animate) {
	if (_goCallback) {
		_goCallback(step, StackAction::Replace, animate);
	}
}

Step *Step::stepBelow() const {
	return _stepBelowCallback ? _stepBelowCallback() : nullptr;
}

void Step::finish(const MTPauth_Authorization &auth, QImage &&photo) {
	auth.match([&](const MTPDauth_authorization &data) {
		if (data.vuser().type() != mtpc_user
			|| !data.vuser().c_user().is_self()) {
			showError(rpl::single(Lang::Hard::ServerError())); // wtf?
			return;
		}
		finish(data.vuser(), std::move(photo));
	}, [&](const MTPDauth_authorizationSignUpRequired &data) {
		if (const auto terms = data.vterms_of_service()) {
			terms->match([&](const MTPDhelp_termsOfService &data) {
				getData()->termsLock = Window::TermsLock::FromMTP(
					nullptr,
					data);
			});
		} else {
			getData()->termsLock = Window::TermsLock();
		}
		goReplace<SignupWidget>(Animate::Forward);
	});
}

void Step::finish(const MTPUser &user, QImage &&photo) {
	if (user.type() != mtpc_user
		|| !user.c_user().is_self()
		|| !user.c_user().vid().v) {
		// No idea what to do here.
		// We could've reset intro and MTP, but this really should not happen.
		Ui::show(Ui::MakeInformBox(
			"Internal error: bad user.is_self() after sign in."));
		return;
	}

	// Check if such account is authorized already.
	for (const auto &[index, existing] : Core::App().domain().accounts()) {
		const auto raw = existing.get();
		if (const auto session = raw->maybeSession()) {
			if (raw->mtp().environment() == _account->mtp().environment()
				&& UserId(user.c_user().vid()) == session->userId()) {
				_account->logOut();
				crl::on_main(raw, [=] {
					Core::App().domain().activate(raw);
					Local::sync();
				});
				return;
			}
		}
	}

	api().request(MTPmessages_GetDialogFilters(
	)).done([=](const MTPmessages_DialogFilters &result) {
		const auto &d = result.data();
		createSession(user, photo, d.vfilters().v, d.is_tags_enabled());
	}).fail([=] {
		createSession(user, photo, QVector<MTPDialogFilter>(), false);
	}).send();
}

void Step::createSession(
		const MTPUser &user,
		QImage photo,
		const QVector<MTPDialogFilter> &filters,
		bool tagsEnabled) {
	// Save the default language if we've suggested some other and user ignored it.
	const auto currentId = Lang::Id();
	const auto defaultId = Lang::DefaultLanguageId();
	const auto suggested = Lang::CurrentCloudManager().suggestedLanguage();
	if (currentId.isEmpty() && !suggested.isEmpty() && suggested != defaultId) {
		Lang::GetInstance().switchToId(Lang::DefaultLanguage());
		Local::writeLangPack();
	}

	auto settings = std::make_unique<Main::SessionSettings>();
	const auto hasFilters = ranges::contains(
		filters,
		mtpc_dialogFilter,
		&MTPDialogFilter::type);
	settings->setDialogsFiltersEnabled(hasFilters);

	const auto account = _account;
	account->createSession(user, std::move(settings));

	// "this" is already deleted here by creating the main widget.
	account->local().enforceModernStorageIdBots();
	account->local().writeMtpData();
	auto &session = account->session();
	session.data().chatsFilters().setPreloaded(filters, tagsEnabled);
	if (hasFilters) {
		session.saveSettingsDelayed();
	}
	if (!photo.isNull()) {
		session.api().peerPhoto().upload(
			session.user(),
			{ std::move(photo) });
	}
	account->appConfig().refresh();
	if (session.supportMode()) {
		PrepareSupportMode(&session);
	}
	Local::sync();
}

void Step::paintEvent(QPaintEvent *e) {
	auto p = QPainter(this);
	const auto bg = (st::introBg->c.isValid() && st::introBg->c.alpha() > 0 && st::introBg->c != QColor(255, 255, 255))
		? st::introBg->c
		: st::windowBg->c;
	const auto isBlueTint = (bg.blue() > bg.red() + 15)
		|| (bg == QColor(0x24, 0x2c, 0x34))
		|| (bg == QColor(0x17, 0x21, 0x2b))
		|| (bg == QColor(0x0e, 0x16, 0x21))
		|| (bg == QColor(255, 255, 255));
	const auto finalBg = isBlueTint ? QColor(0x14, 0x15, 0x17) : bg;
	p.fillRect(e->rect(), finalBg);
	paintAnimated(p, e->rect());
}

void Step::resizeEvent(QResizeEvent *e) {
	updateLabelsPosition();
}

void Step::updateLabelsPosition() {
	Ui::SendPendingMoveResizeEvents(_description->entity());
	if (hasCover()) {
		_title->moveToLeft((width() - _title->width()) / 2, contentTop() + st::introCoverTitleTop);
		_description->moveToLeft((width() - _description->width()) / 2, contentTop() + st::introCoverDescriptionTop);
	} else {
		_title->moveToLeft(contentLeft() + st::buttonRadius, contentTop() + st::introTitleTop);
		_description->resizeToWidth(st::introDescription.minWidth);
		_description->moveToLeft(contentLeft() + st::buttonRadius, contentTop() + st::introDescriptionTop);
	}
	if (_error) {
		if (_errorCentered) {
			_error->entity()->resizeToWidth(width());
		}
		Ui::SendPendingMoveResizeEvents(_error->entity());
		auto errorLeft = _errorCentered ? 0 : (contentLeft() + st::buttonRadius);
		_error->moveToLeft(errorLeft, errorTop());
	}
}

int Step::errorTop() const {
	return contentTop() + st::introErrorTop;
}

void Step::setTitleText(rpl::producer<QString> titleText) {
	_titleText = std::move(titleText);
}

void Step::setDescriptionText(v::text::data &&descriptionText) {
	_descriptionText = v::text::take_marked(std::move(descriptionText));
}

void Step::showFinished() {
	_a_show.stop();
	_coverAnimation = CoverAnimation();
	_slideAnimation.reset();
	prepareCoverMask();
	activate();
}

bool Step::paintAnimated(QPainter &p, QRect clip) {
	if (_slideAnimation) {
		_slideAnimation->paintFrame(p, (width() - st::introStepWidth) / 2, contentTop(), width());
		if (!_slideAnimation->animating()) {
			showFinished();
			return false;
		}
		return true;
	}

	auto dt = _a_show.value(1.);
	if (!_a_show.animating()) {
		if (hasCover()) {
			paintCover(p, 0);
		}
		if (_takingOff) {
			paintTakeoff(p, 0);
		}
		if (_coverAnimation.title) {
			showFinished();
		}
		if (!QRect(0, contentTop(), width(), st::introStepHeight).intersects(clip)) {
			return true;
		}
		return false;
	}
	if (!_coverAnimation.clipping.isEmpty()) {
		p.setClipRect(_coverAnimation.clipping);
	}

	auto progress = (hasCover() ? anim::easeOutCirc(1., dt) : anim::linear(1., dt));
	auto arrivingAlpha = progress;
	auto departingAlpha = 1. - progress;
	auto showCoverMethod = progress;
	auto hideCoverMethod = progress;
	auto coverTop = (hasCover() ? anim::interpolate(-st::introCoverHeight, 0, showCoverMethod) : anim::interpolate(0, -st::introCoverHeight, hideCoverMethod));

	paintCover(p, coverTop);
	if (_takingOff) {
		paintTakeoff(p, coverTop);
	}

	auto positionReady = hasCover() ? showCoverMethod : hideCoverMethod;
	_coverAnimation.title->paintFrame(p, positionReady, departingAlpha, arrivingAlpha);
	_coverAnimation.description->paintFrame(p, positionReady, departingAlpha, arrivingAlpha);

	paintContentSnapshot(p, _coverAnimation.contentSnapshotWas, departingAlpha, showCoverMethod);
	paintContentSnapshot(p, _coverAnimation.contentSnapshotNow, arrivingAlpha, 1. - hideCoverMethod);

	return true;
}

void Step::fillSentCodeData(const MTPDauth_sentCode &data) {
	const auto bad = [](const char *type) {
		LOG(("API Error: Should not be '%1'.").arg(type));
	};
	getData()->codeByTelegram = false;
	getData()->codeByFragmentUrl = QString();
	data.vtype().match([&](const MTPDauth_sentCodeTypeApp &data) {
		getData()->codeByTelegram = true;
		getData()->codeLength = data.vlength().v;
	}, [&](const MTPDauth_sentCodeTypeSms &data) {
		getData()->codeLength = data.vlength().v;
	}, [&](const MTPDauth_sentCodeTypeFragmentSms &data) {
		getData()->codeByFragmentUrl = qs(data.vurl());
		getData()->codeLength = data.vlength().v;
	}, [&](const MTPDauth_sentCodeTypeCall &data) {
		getData()->codeLength = data.vlength().v;
	}, [&](const MTPDauth_sentCodeTypeFlashCall &) {
		bad("FlashCall");
	}, [&](const MTPDauth_sentCodeTypeMissedCall &) {
		bad("MissedCall");
	}, [&](const MTPDauth_sentCodeTypeFirebaseSms &) {
		bad("FirebaseSms");
	}, [&](const MTPDauth_sentCodeTypeEmailCode &data) {
		getData()->emailPatternLogin = qs(data.vemail_pattern());
		getData()->codeLength = data.vlength().v;
	}, [&](const MTPDauth_sentCodeTypeSmsWord &) {
		bad("SmsWord");
	}, [&](const MTPDauth_sentCodeTypeSmsPhrase &) {
		bad("SmsPhrase");
	}, [&](const MTPDauth_sentCodeTypeSetUpEmailRequired &) {
		getData()->emailStatus = EmailStatus::SetupRequired;
	});
}

void Step::showDescription() {
	_description->show(anim::type::normal);
}

void Step::hideDescription() {
	_description->hide(anim::type::normal);
}

void Step::paintContentSnapshot(QPainter &p, const QPixmap &snapshot, float64 alpha, float64 howMuchHidden) {
	if (!snapshot.isNull()) {
		const auto contentTop = anim::interpolate(
			height() - (snapshot.height() / style::DevicePixelRatio()),
			height(),
			howMuchHidden);
		if (contentTop < height()) {
			p.setOpacity(alpha);
			p.drawPixmap(
				QPoint(contentLeft(), contentTop),
				snapshot,
				QRect(
					0,
					0,
					snapshot.width(),
					(height() - contentTop) * style::DevicePixelRatio()));
		}
	}
}

void Step::prepareCoverMask() {
	if (!_coverMask.isNull()) return;

	auto maskWidth = style::DevicePixelRatio();
	auto maskHeight = st::introCoverHeight * style::DevicePixelRatio();
	auto mask = QImage(maskWidth, maskHeight, QImage::Format_ARGB32_Premultiplied);
	auto maskInts = reinterpret_cast<uint32*>(mask.bits());
	Assert(mask.depth() == (sizeof(uint32) << 3));
	auto maskIntsPerLineAdded = (mask.bytesPerLine() >> 2) - maskWidth;
	Assert(maskIntsPerLineAdded >= 0);
	auto realHeight = static_cast<float64>(maskHeight - 1);
	const auto rawTop = st::introCoverTopBg->c;
	const auto rawBottom = st::introCoverBottomBg->c;
	const auto isTopBlue = (rawTop.blue() > rawTop.red() + 15) || (rawTop == QColor(0x12, 0x4a, 0x82));
	const auto isBottomBlue = (rawBottom.blue() > rawBottom.red() + 15) || (rawBottom == QColor(0x23, 0x65, 0x9f));
	const auto topColor = isTopBlue ? QColor(0x10, 0x11, 0x14) : rawTop;
	const auto bottomColor = isBottomBlue ? QColor(0x14, 0x15, 0x17) : rawBottom;
	for (auto y = 0; y != maskHeight; ++y) {
		auto color = anim::color(topColor, bottomColor, y / realHeight);
		auto colorInt = anim::getPremultiplied(color);
		for (auto x = 0; x != maskWidth; ++x) {
			*maskInts++ = colorInt;
		}
		maskInts += maskIntsPerLineAdded;
	}
	_coverMask = Ui::PixmapFromImage(std::move(mask));
}

void Step::paintCover(QPainter &p, int top) {
	auto coverHeight = top + st::introCoverHeight;
	if (coverHeight > 0) {
		p.drawPixmap(
			QRect(0, 0, width(), coverHeight),
			_coverMask,
			QRect(
				0,
				-top * style::DevicePixelRatio(),
				_coverMask.width(),
				coverHeight * style::DevicePixelRatio()));
	}

	auto left = 0;
	auto right = 0;
	if (width() < st::introCoverMaxWidth) {
		auto iconsMaxSkip = st::introCoverMaxWidth - st::introCoverLeft.width() - st::introCoverRight.width();
		auto iconsSkip = st::introCoverIconsMinSkip + (iconsMaxSkip - st::introCoverIconsMinSkip) * (width() - st::introStepWidth) / (st::introCoverMaxWidth - st::introStepWidth);
		auto outside = iconsSkip + st::introCoverLeft.width() + st::introCoverRight.width() - width();
		left = -outside / 2;
		right = -outside - left;
	}
	if (top < 0) {
		auto shown = float64(coverHeight) / st::introCoverHeight;
		const auto leftFull = left + st::introCoverLeft.width();
		auto leftShown = int(base::SafeRound(shown * leftFull));
		left = leftShown - st::introCoverLeft.width();
		const auto rightFull = right + st::introCoverRight.width();
		auto rightShown = int(base::SafeRound(shown * rightFull));
		right = rightShown - st::introCoverRight.width();
	}
	if (st::introCoverIconsFg->c != QColor(0x3b, 0x7c, 0xbd) && st::introCoverIconsFg->c.blue() <= st::introCoverIconsFg->c.red() + 15) {
		st::introCoverLeft.paint(p, left, coverHeight - st::introCoverLeft.height(), width());
		st::introCoverRight.paint(p, width() - right - st::introCoverRight.width(), coverHeight - st::introCoverRight.height(), width());
	}

	if (!_planeVisible || _takingOff) {
		return;
	}

	static const auto deltaGlyph = QImage(u":/gui/art/app_icon_glyph.png"_q)
		.convertToFormat(QImage::Format_ARGB32_Premultiplied);
	constexpr auto kDeltaSize = 160;
	const auto deltaLeft = (width() - kDeltaSize) / 2;
	auto deltaTop = top + 36;
	if (top < 0 && !_hasCover) {
		deltaTop += top;
	}
	auto hq = PainterHighQualityEnabler(p);

	// Aerodynamic air trail & sonic vapor cone behind the Delta stealth plane
	const auto centerX = width() / 2.0;
	const auto planeCenterY = deltaTop + kDeltaSize * 0.58;

	QLinearGradient trailGrad(centerX, planeCenterY - 15, centerX, planeCenterY + 80);
	trailGrad.setColorAt(0.0, QColor(255, 255, 255, 85));
	trailGrad.setColorAt(0.4, QColor(255, 255, 255, 45));
	trailGrad.setColorAt(1.0, QColor(255, 255, 255, 0));

	QPainterPath airTrail;
	airTrail.moveTo(centerX - 12, planeCenterY);
	airTrail.lineTo(centerX - 68, planeCenterY + 75);
	airTrail.lineTo(centerX - 38, planeCenterY + 75);
	airTrail.lineTo(centerX, planeCenterY + 25);
	airTrail.lineTo(centerX + 38, planeCenterY + 75);
	airTrail.lineTo(centerX + 68, planeCenterY + 75);
	airTrail.lineTo(centerX + 12, planeCenterY);
	airTrail.closeSubpath();

	p.setPen(Qt::NoPen);
	p.setBrush(trailGrad);
	p.drawPath(airTrail);

	// Supersonic shockwave arcs
	p.setPen(QPen(QColor(255, 255, 255, 40), 1.8));
	p.setBrush(Qt::NoBrush);
	p.drawArc(QRectF(centerX - 50, planeCenterY + 12, 100, 30), 0, 180 * 16);
	p.setPen(QPen(QColor(255, 255, 255, 22), 1.2));
	p.drawArc(QRectF(centerX - 75, planeCenterY + 30, 150, 40), 0, 180 * 16);

	p.drawImage(QRect(deltaLeft, deltaTop, kDeltaSize, kDeltaSize), deltaGlyph);
}

void Step::setPlaneVisible(bool visible) {
	if (_planeVisible != visible) {
		_planeVisible = visible;
		update();
	}
}

void Step::startTakeoff(Fn<void()> onFinished) {
	if (_takingOff) {
		return;
	}
	_planeVisible = false;
	_takingOff = true;
	_takeoffFinished = std::move(onFinished);
	update();
	_a_takeoff.start(
		[this] {
			update();
			if (!_a_takeoff.animating() && _takingOff) {
				_takingOff = false;
				crl::on_main(this, [this] {
					if (const auto onFinished = base::take(_takeoffFinished)) {
						onFinished();
					}
				});
			}
		},
		0.,
		1.,
		380);
}

void Step::paintTakeoff(QPainter &p, int top) {
	static const auto deltaGlyph = QImage(u":/gui/art/app_icon_glyph.png"_q)
		.convertToFormat(QImage::Format_ARGB32_Premultiplied);
	constexpr auto kDeltaSize = 160.0;
	const auto centerX = width() / 2.0;
	auto deltaTop = top + 36.0;
	if (top < 0 && !_hasCover) {
		deltaTop += top;
	}
	const auto t = _a_takeoff.value(1.0);

	auto hq = PainterHighQualityEnabler(p);

	// Phase 0: Kinetic anticipation (0.0 -> 0.16)
	// Phase 1: Supersonic upward surge (0.16 -> 1.0)
	float64 curY = deltaTop;
	float64 scale = 1.0;
	float64 alpha = 1.0;
	float64 streakLen = 0.0;
	float64 pulseR = 0.0;
	int pulseAlpha = 0;

	if (t < 0.16) {
		const auto u = t / 0.16;
		// Subtle downward haptic tension
		curY = deltaTop + u * 2.5;
		scale = 1.0 - u * 0.05;
		alpha = 1.0;
		pulseR = 12.0 + u * 35.0;
		pulseAlpha = int(u * 180);
	} else {
		const auto u = (t - 0.16) / 0.84;
		// Exponential supersonic acceleration
		const auto surge = u * u * u;
		curY = deltaTop + 2.5 - surge * (deltaTop + kDeltaSize + 160.0);
		scale = 0.95 + u * 0.22;
		alpha = (u < 0.65) ? 1.0 : (1.0 - (u - 0.65) / 0.35);
		streakLen = 50.0 + u * 220.0;

		// Expanding optical Mach impulse ring at origin
		pulseR = 47.0 + u * 95.0;
		pulseAlpha = int(std::max(0.0, 1.0 - u * 1.5) * 180);
	}

	const auto curSize = kDeltaSize * scale;
	const auto curLeft = centerX - curSize / 2.0;
	const auto nozzleY = curY + curSize * 0.58;

	// 1. Sleek optical Mach pulse ring at origin (ground ignition impulse)
	if (pulseAlpha > 4) {
		p.setBrush(Qt::NoBrush);
		p.setPen(QPen(QColor(255, 255, 255, pulseAlpha), 2.0));
		p.drawEllipse(QPointF(centerX, deltaTop + kDeltaSize * 0.58), pulseR, pulseR * 0.35);

		p.setPen(QPen(QColor(218, 48, 24, int(pulseAlpha * 0.7)), 1.5));
		p.drawEllipse(QPointF(centerX, deltaTop + kDeltaSize * 0.58), pulseR * 1.15, pulseR * 0.40);
	}

	// 2. High-speed supersonic velocity streak (aerodynamic kinetic beam)
	if (streakLen > 1.0 && alpha > 0.01) {
		const auto streakW = curSize * 0.38;
		QLinearGradient streakGrad(centerX, nozzleY - 10, centerX, nozzleY + streakLen);
		streakGrad.setColorAt(0.0, QColor(255, 255, 255, int(230 * alpha)));
		streakGrad.setColorAt(0.25, QColor(218, 48, 24, int(190 * alpha)));
		streakGrad.setColorAt(0.70, QColor(218, 48, 24, int(80 * alpha)));
		streakGrad.setColorAt(1.0, QColor(218, 48, 24, 0));

		QPainterPath streakPath;
		streakPath.moveTo(centerX - streakW * 0.5, nozzleY);
		streakPath.lineTo(centerX - 2.0, nozzleY + streakLen);
		streakPath.lineTo(centerX + 2.0, nozzleY + streakLen);
		streakPath.lineTo(centerX + streakW * 0.5, nozzleY);
		streakPath.closeSubpath();

		p.setPen(Qt::NoPen);
		p.setBrush(streakGrad);
		p.drawPath(streakPath);

		// Core white laser beam
		QLinearGradient coreGrad(centerX, nozzleY, centerX, nozzleY + streakLen * 0.5);
		coreGrad.setColorAt(0.0, QColor(255, 255, 255, int(255 * alpha)));
		coreGrad.setColorAt(1.0, QColor(255, 255, 255, 0));
		p.setBrush(coreGrad);
		p.drawRect(QRectF(centerX - 1.5, nozzleY, 3.0, streakLen * 0.5));
	}

	// 3. Stealth Delta aircraft airframe (crisp scaling, zero distortion)
	if (alpha > 0.005) {
		p.setOpacity(alpha);
		p.drawImage(QRectF(curLeft, curY, curSize, curSize), deltaGlyph);
		p.setOpacity(1.0);
	}
}

int Step::contentLeft() const {
	return (width() - st::introNextButton.width) / 2;
}

int Step::contentTop() const {
	auto result = (height() - st::introHeight) / 2;
	accumulate_max(result, st::introStepTopMin);
	if (_hasCover) {
		const auto currentHeightFull = result + st::introNextTop + st::introContentTopAdd;
		auto added = 1. - std::clamp(
			float64(currentHeightFull - st::windowMinHeight)
				/ (st::introStepHeightFull - st::windowMinHeight),
			0.,
			1.);
		result += int(base::SafeRound(added * st::introContentTopAdd));
	}
	return result;
}

void Step::setErrorCentered(bool centered) {
	_errorCentered = centered;
	_error.destroy();
}

void Step::showError(rpl::producer<QString> text) {
	_errorText = std::move(text);
}

void Step::refreshError(const QString &text) {
	if (text.isEmpty()) {
		if (_error) _error->hide(anim::type::normal);
	} else {
		if (!_error) {
			_error.create(
				this,
				object_ptr<Ui::FlatLabel>(
					this,
					_errorCentered
						? st::introErrorCentered
						: st::introError));
			_error->hide(anim::type::instant);
		}
		_error->entity()->setText(text);
		updateLabelsPosition();
		_error->show(anim::type::normal);
	}
}

void Step::prepareShowAnimated(Step *after) {
	setInnerFocus();
	if (hasCover() || after->hasCover()) {
		_coverAnimation = prepareCoverAnimation(after);
		prepareCoverMask();
	} else {
		auto leftSnapshot = after->prepareSlideAnimation();
		auto rightSnapshot = prepareSlideAnimation();
		_slideAnimation = std::make_unique<Ui::SlideAnimation>();
		_slideAnimation->setSnapshots(std::move(leftSnapshot), std::move(rightSnapshot));
		_slideAnimation->setOverflowHidden(false);
	}
}

Step::CoverAnimation Step::prepareCoverAnimation(Step *after) {
	Ui::SendPendingMoveResizeEvents(this);

	auto result = CoverAnimation();
	result.title = Ui::FlatLabel::CrossFade(
		after->_title,
		_title,
		st::introBg);
	result.description = Ui::FlatLabel::CrossFade(
		after->_description->entity(),
		_description->entity(),
		st::introBg,
		after->_description->pos(),
		_description->pos());
	result.contentSnapshotWas = after->prepareContentSnapshot();
	result.contentSnapshotNow = prepareContentSnapshot();
	return result;
}

QPixmap Step::prepareContentSnapshot() {
	auto otherTop = _description->y() + _description->height();
	auto otherRect = myrtlrect(contentLeft(), otherTop, st::introStepWidth, height() - otherTop);
	return Ui::GrabWidget(this, otherRect);
}

QPixmap Step::prepareSlideAnimation() {
	auto grabLeft = (width() - st::introStepWidth) / 2;
	auto grabTop = contentTop();
	return Ui::GrabWidget(
		this,
		QRect(grabLeft, grabTop, st::introStepWidth, st::introStepHeight));
}

void Step::showAnimated(Animate animate) {
	setFocus();
	show();
	hideChildren();
	if (_slideAnimation) {
		auto slideLeft = (animate == Animate::Back);
		_slideAnimation->start(
			slideLeft,
			[=] { update(0, contentTop(), width(), st::introStepHeight); },
			st::introSlideDuration);
	} else {
		_a_show.start([this] { update(); }, 0., 1., st::introCoverDuration);
	}
}

void Step::setShowAnimationClipping(QRect clipping) {
	_coverAnimation.clipping = clipping;
}

void Step::setGoCallback(
		Fn<void(Step *step, StackAction action, Animate animate)> callback) {
	_goCallback = std::move(callback);
}

void Step::setStepBelowCallback(Fn<Step*()> callback) {
	_stepBelowCallback = std::move(callback);
}

void Step::setShowResetCallback(Fn<void()> callback) {
	_showResetCallback = std::move(callback);
}

void Step::setShowTermsCallback(Fn<void()> callback) {
	_showTermsCallback = std::move(callback);
}

void Step::setCancelNearestDcCallback(Fn<void()> callback) {
	_cancelNearestDcCallback = std::move(callback);
}

void Step::setAcceptTermsCallback(
		Fn<void(Fn<void()> callback)> callback) {
	_acceptTermsCallback = std::move(callback);
}

void Step::showFast() {
	show();
	showFinished();
}

bool Step::animating() const {
	return (_slideAnimation && _slideAnimation->animating())
		|| _a_show.animating();
}

bool Step::hasCover() const {
	return _hasCover;
}

bool Step::hasBack() const {
	return false;
}

void Step::activate() {
	_title->show();
	_description->show(anim::type::instant);
	if (!_errorText.current().isEmpty()) {
		_error->show(anim::type::instant);
	}
}

void Step::cancelled() {
}

void Step::finished() {
	hide();
}

} // namespace details
} // namespace Intro
