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

	if (!_planeVisible) {
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
		1400);
}

void Step::paintTakeoff(QPainter &p, int top) {
	static const auto deltaGlyph = QImage(u":/gui/art/app_icon_glyph.png"_q)
		.convertToFormat(QImage::Format_ARGB32_Premultiplied);
	constexpr auto kDeltaSize = 160.0;
	const auto centerX = width() / 2.0;
	const auto startTop = top + 36.0;
	const auto y0 = startTop + kDeltaSize * 0.58;
	const auto t = _a_takeoff.value(1.0);

	auto hq = PainterHighQualityEnabler(p);

	// Bounded aerodynamic flight model strictly inside the application window
	const auto deltaX1 = std::min(72.0, width() * 0.18);
	const auto deltaX2 = std::min(58.0, width() * 0.15);

	float64 curX = centerX;
	float64 curY = y0;
	float64 heading = 0.0; // degrees
	float64 bank = 0.0;    // degrees (roll angle)
	float64 scale = 1.0;
	float64 alpha = 1.0;
	float64 flamePwr = 0.0;
	float64 vaporG = 0.0;
	float64 boom = 0.0;

	if (t < 0.12) {
		// Phase 0: Ignition / Spool-up (stationary at static resting position with micro-vibration)
		const auto u = t / 0.12;
		curX = centerX;
		curY = y0 - std::sin(u * M_PI) * 1.5;
		heading = 0.0;
		bank = 0.0;
		scale = 1.0 + 0.02 * u;
		alpha = 1.0;
		flamePwr = u;
		vaporG = 0.0;
		boom = 0.0;
	} else if (t < 0.48) {
		// Phase 1: Tactical climbing left sweep (sin^2 curve ensures zero velocity jumps)
		const auto u = (t - 0.12) / 0.36;
		const auto sinU = std::sin(M_PI * u);
		curX = centerX - deltaX1 * (sinU * sinU);
		curY = y0 - 32.0 * u;
		const auto dx = -deltaX1 * M_PI * std::sin(2.0 * M_PI * u);
		const auto dy = -32.0;
		heading = std::atan2(dx, -dy) * (180.0 / M_PI);
		bank = -38.0 * std::sin(2.0 * M_PI * u);
		scale = 1.02 + 0.04 * sinU;
		alpha = 1.0;
		flamePwr = 1.0;
		vaporG = std::max(0.0, std::sin(2.0 * M_PI * u)) * 0.6;
		boom = 0.0;
	} else if (t < 0.82) {
		// Phase 2: Counter-bank climbing right sweep
		const auto u = (t - 0.48) / 0.34;
		const auto sinU = std::sin(M_PI * u);
		curX = centerX + deltaX2 * (sinU * sinU);
		curY = y0 - 32.0 - 32.0 * u;
		const auto dx = deltaX2 * M_PI * std::sin(2.0 * M_PI * u);
		const auto dy = -32.0;
		heading = std::atan2(dx, -dy) * (180.0 / M_PI);
		bank = 36.0 * std::sin(2.0 * M_PI * u);
		scale = 1.06 + 0.06 * sinU;
		alpha = 1.0;
		flamePwr = 1.0;
		vaporG = std::max(0.0, std::sin(2.0 * M_PI * u)) * 0.85;
		boom = 0.0;
	} else {
		// Phase 3: Wings level, center alignment, supersonic Mach breakout
		const auto u = (t - 0.82) / 0.18;
		const auto uEase = u * u;
		curX = centerX;
		curY = y0 - 64.0 - 24.0 * uEase;
		heading = 0.0;
		bank = 0.0;
		scale = 1.12 + 0.32 * u;
		alpha = std::max(0.0, 1.0 - u * u * u);
		flamePwr = std::max(0.0, 1.0 - u);
		vaporG = 0.0;
		boom = u;
	}

	const auto curSize = kDeltaSize * scale;
	const auto bankRad = bank * (M_PI / 180.0);
	const auto bankCos = std::max(0.35, std::abs(std::cos(bankRad)));
	const auto headRad = heading * (M_PI / 180.0);
	const auto dirX = std::sin(headRad);
	const auto dirY = -std::cos(headRad);
	const auto normX = -dirY;
	const auto normY = dirX;

	// Dual exhaust nozzles
	const auto nozzleDist = curSize * 0.36;
	const auto nozzleSpread = curSize * 0.14 * bankCos;
	const auto nzLeftX = curX - dirX * nozzleDist - normX * nozzleSpread;
	const auto nzLeftY = curY - dirY * nozzleDist - normY * nozzleSpread;
	const auto nzRightX = curX - dirX * nozzleDist + normX * nozzleSpread;
	const auto nzRightY = curY - dirY * nozzleDist + normY * nozzleSpread;

	// 1. Twin afterburner plumes with supersonic Mach shock diamonds
	if (flamePwr > 0.01) {
		const auto flameLen = (40.0 + 105.0 * flamePwr) * scale;
		const auto flameW = (6.0 + 4.5 * flamePwr) * scale * bankCos;

		const std::pair<float64, float64> nozzles[] = {
			{ nzLeftX, nzLeftY },
			{ nzRightX, nzRightY }
		};
		for (const auto &[nzX, nzY] : nozzles) {
			// Outer plume: Aero Delta signature crimson
			QLinearGradient flameGrad(nzX, nzY, nzX - dirX * flameLen, nzY - dirY * flameLen);
			flameGrad.setColorAt(0.0, QColor(255, 255, 255, int(245 * flamePwr * alpha)));
			flameGrad.setColorAt(0.18, QColor(255, 140, 50, int(220 * flamePwr * alpha)));
			flameGrad.setColorAt(0.60, QColor(218, 48, 24, int(170 * flamePwr * alpha)));
			flameGrad.setColorAt(1.0, QColor(218, 48, 24, 0));

			QPainterPath plume;
			plume.moveTo(nzX - normX * flameW, nzY - normY * flameW);
			plume.lineTo(nzX - dirX * flameLen, nzY - dirY * flameLen);
			plume.lineTo(nzX + normX * flameW, nzY + normY * flameW);
			plume.closeSubpath();

			p.setPen(Qt::NoPen);
			p.setBrush(flameGrad);
			p.drawPath(plume);

			// Pulsing Mach diamond shock nodes
			for (const auto ds : { 0.20, 0.40, 0.60 }) {
				const auto dmX = nzX - dirX * (flameLen * ds);
				const auto dmY = nzY - dirY * (flameLen * ds);
				const auto dmR = (3.2 - ds * 1.8) * scale * bankCos;

				QPolygonF diamond;
				diamond << QPointF(dmX - dirX * (dmR * 1.6), dmY - dirY * (dmR * 1.6))
						<< QPointF(dmX + normX * dmR, dmY + normY * dmR)
						<< QPointF(dmX + dirX * (dmR * 1.6), dmY + dirY * (dmR * 1.6))
						<< QPointF(dmX - normX * dmR, dmY - normY * dmR);

				p.setBrush(QColor(255, 255, 255, int(245 * flamePwr * alpha)));
				p.drawPolygon(diamond);
			}
		}
	}

	// 2. Wingtip condensation vortices (trailing vapor ribbons)
	if (alpha > 0.05) {
		const auto wtY = curSize * 0.22;
		const auto wtSpan = curSize * 0.44 * bankCos;
		const auto wtLeftX = curX - dirX * wtY - normX * wtSpan;
		const auto wtLeftY = curY - dirY * wtY - normY * wtSpan;
		const auto wtRightX = curX - dirX * wtY + normX * wtSpan;
		const auto wtRightY = curY - dirY * wtY + normY * wtSpan;

		const auto ribbonLen = 50.0 * scale;
		p.setPen(QPen(QColor(255, 255, 255, int(75 * alpha)), 1.8));
		p.drawLine(QPointF(wtLeftX, wtLeftY), QPointF(wtLeftX - dirX * ribbonLen + normX * 8, wtLeftY - dirY * ribbonLen + normY * 8));
		p.drawLine(QPointF(wtRightX, wtRightY), QPointF(wtRightX - dirX * ribbonLen - normX * 8, wtRightY - dirY * ribbonLen - normY * 8));
	}

	// 3. Transonic Prandtl-Glauert condensation veil (during high G pull-up)
	if (vaporG > 0.05 && alpha > 0.1) {
		const auto vgAlpha = int(vaporG * 110 * alpha);
		const auto vgW = curSize * 0.65 * bankCos;
		const auto vgH = curSize * 0.28;
		p.setPen(QPen(QColor(255, 255, 255, int(vgAlpha * 0.7)), 1.2));
		p.setBrush(QColor(255, 255, 255, vgAlpha));
		p.drawEllipse(QRectF(curX - vgW / 2.0, curY - vgH / 2.0, vgW, vgH));
	}

	// 4. Delta stealth airframe with 3D perspective banking roll and shading
	if (alpha > 0.005) {
		p.save();
		p.translate(curX, curY);
		p.rotate(heading);
		p.scale(bankCos, 1.0);
		p.setOpacity(alpha);

		p.drawImage(QRectF(-curSize / 2.0, -curSize / 2.0, curSize, curSize), deltaGlyph);

		// 3D aerodynamic roll shadow on the down-banked wing
		if (std::abs(bank) > 5.0) {
			const auto shadowAlpha = int(std::min(1.0, std::abs(bank) / 45.0) * 85);
			p.setPen(Qt::NoPen);
			p.setBrush(QColor(0, 0, 0, shadowAlpha));
			if (bank < 0) {
				p.drawRect(QRectF(-curSize / 2.0, -curSize / 2.0, curSize / 2.0, curSize));
			} else {
				p.drawRect(QRectF(0, -curSize / 2.0, curSize / 2.0, curSize));
			}
		}
		p.restore();
	}

	// 5. Supersonic Mach shockwave breakthrough (Phase 3 climax) - sharp refraction rings
	if (boom > 0.01) {
		const auto shockR = (18.0 + 240.0 * std::pow(boom, 0.65)) * scale;
		const auto shockAlpha = int((1.0 - boom) * 220);

		if (shockAlpha > 5) {
			p.setBrush(Qt::NoBrush);
			// Inner white shockfront
			p.setPen(QPen(QColor(255, 255, 255, shockAlpha), 2.2));
			p.drawEllipse(QPointF(curX, curY), shockR, shockR);

			// Outer crimson aerodynamic expansion wave
			p.setPen(QPen(QColor(218, 48, 24, int(shockAlpha * 0.75)), 1.8));
			p.drawEllipse(QPointF(curX, curY), shockR * 1.14, shockR * 1.14);

			// Anamorphic optical laser streak across shock plane
			const auto flareW = shockR * 1.8;
			p.setPen(QPen(QColor(255, 255, 255, int(shockAlpha * 0.85)), 2.0));
			p.drawLine(QPointF(curX - flareW, curY), QPointF(curX + flareW, curY));
		}
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
