#include "extera/extera_arrow_3d.h"

#include "logs.h"
#include "styles/style_basic.h"

#include <QOpenGLContext>
#include <QOpenGLShader>
#include <QSurfaceFormat>
#include <QtCore/QDataStream>
#include <QtCore/QFile>
#include <QtGui/QFont>
#include <QtGui/QFontMetricsF>
#include <QtGui/QLinearGradient>
#include <QtGui/QMouseEvent>
#include <QtGui/QPainter>
#include <QtGui/QPainterPath>
#include <QtGui/QVector3D>

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>

namespace Extera {
namespace {

constexpr auto kModelResource = ":/extera/models/extera_arrow.binobj";
constexpr auto kFlecksResource = ":/extera/models/flecks.png";
constexpr auto kVertexShaderResource = ":/extera/shaders/vertex2.glsl";
constexpr auto kFragmentShaderResource = ":/extera/shaders/fragment_extera_arrow.glsl";

constexpr auto kEngravingSize = 1024;
constexpr auto kEngravingCenterX = 0.4976;
constexpr auto kEngravingCenterY = 0.2813;
constexpr auto kEngravingAngle = 19.49;
constexpr auto kEngravingTextSize = 0.058;
constexpr auto kEngravingLetterSpacing = 0.12;

constexpr auto kFieldOfView = 53.13f;
constexpr auto kZNear = 1.0f;
constexpr auto kZFar = 200.0f;
constexpr auto kMaxArrayElements = qint32(4'000'000);
constexpr auto kMaxModelVertices = qint32(2'000'000);

[[nodiscard]] QColor ShiftColor(
		const QColor &color,
		float hueShiftDeg,
		float saturationScale,
		float valueScale) {
	float h = 0.0f;
	float s = 0.0f;
	float v = 0.0f;
	float a = 1.0f;
	color.getHsvF(&h, &s, &v, &a);
	if (h < 0.0f) {
		h = 0.0f;
	}
	h = std::fmod(h + hueShiftDeg / 360.0f + 1.0f, 1.0f);
	s = std::clamp(s * saturationScale, 0.0f, 1.0f);
	v = std::clamp(v * valueScale, 0.0f, 1.0f);
	return QColor::fromHsvF(h, s, v, a);
}

[[nodiscard]] QColor BlendColors(const QColor &a, const QColor &b, float t) {
	const auto clamped = std::clamp(t, 0.0f, 1.0f);
	const auto inv = 1.0f - clamped;
	return QColor::fromRgbF(
		a.redF() * inv + b.redF() * clamped,
		a.greenF() * inv + b.greenF() * clamped,
		a.blueF() * inv + b.blueF() * clamped,
		1.0f);
}

[[nodiscard]] QVector3D ToVec3(const QColor &color) {
	return QVector3D(
		float(color.redF()),
		float(color.greenF()),
		float(color.blueF()));
}

[[nodiscard]] float EaseOutQuint(float t) {
	const auto inv = 1.0f - std::clamp(t, 0.0f, 1.0f);
	return 1.0f - inv * inv * inv * inv * inv;
}

[[nodiscard]] float EaseInOutCubic(float t) {
	const auto x = std::clamp(t, 0.0f, 1.0f);
	return (x < 0.5f)
		? (4.0f * x * x * x)
		: (1.0f - std::pow(-2.0f * x + 2.0f, 3.0f) * 0.5f);
}

[[nodiscard]] float Overshoot(float t, float tension = 1.7f) {
	const auto x = std::clamp(t, 0.0f, 1.0f) - 1.0f;
	return x * x * ((tension + 1.0f) * x + tension) + 1.0f;
}

[[nodiscard]] QString ReadResourceText(const QString &path) {
	QFile file(path);
	if (!file.open(QIODevice::ReadOnly | QIODevice::Text)) {
		return QString();
	}
	return QString::fromUtf8(file.readAll());
}

void BlurAlphaRegion(QImage &alphaImage, const QRect &region) {
	if (alphaImage.format() != QImage::Format_Alpha8) {
		return;
	}
	const auto bounds = region.intersected(alphaImage.rect());
	if (bounds.isEmpty()) {
		return;
	}
	const auto w = bounds.width();
	const auto h = bounds.height();
	std::vector<uint8_t> temp(size_t(w) * size_t(h), 0);

	for (auto pass = 0; pass < 2; ++pass) {
		for (auto y = 0; y < h; ++y) {
			const auto *src = alphaImage.constScanLine(bounds.top() + y)
				+ bounds.left();
			auto *dst = temp.data() + size_t(y) * size_t(w);
			for (auto x = 0; x < w; ++x) {
				const int left = src[std::max(0, x - 1)];
				const int center = src[x];
				const int right = src[std::min(w - 1, x + 1)];
				dst[x] = uint8_t((left + center * 2 + right + 2) >> 2);
			}
		}
		for (auto y = 0; y < h; ++y) {
			const auto yPrev = std::max(0, y - 1);
			const auto yNext = std::min(h - 1, y + 1);
			const auto *rowPrev = temp.data() + size_t(yPrev) * size_t(w);
			const auto *rowCurr = temp.data() + size_t(y) * size_t(w);
			const auto *rowNext = temp.data() + size_t(yNext) * size_t(w);
			auto *dst = alphaImage.scanLine(bounds.top() + y) + bounds.left();
			for (auto x = 0; x < w; ++x) {
				dst[x] = uint8_t(
					(int(rowPrev[x]) + int(rowCurr[x]) * 2 + int(rowNext[x]) + 2) >> 2);
			}
		}
	}
}

[[nodiscard]] std::unique_ptr<QOpenGLTexture> MakeSolidTexture(
		const QColor &color,
		QOpenGLTexture::WrapMode wrapMode) {
	QImage image(4, 4, QImage::Format_RGBA8888);
	image.fill(color);
	auto texture = std::make_unique<QOpenGLTexture>(
		image,
		QOpenGLTexture::DontGenerateMipMaps);
	if (!texture->isCreated()) {
		return nullptr;
	}
	texture->setMinMagFilters(QOpenGLTexture::Linear, QOpenGLTexture::Linear);
	texture->setWrapMode(wrapMode);
	return texture;
}

} // namespace

Arrow3DWidget::Arrow3DWidget(QWidget *parent)
: QOpenGLWidget(parent) {
	auto fmt = format();
	fmt.setAlphaBufferSize(8);
	fmt.setDepthBufferSize(16);
	fmt.setSamples(4);
	setFormat(fmt);

	setAutoFillBackground(false);
	setAttribute(Qt::WA_OpaquePaintEvent, false);
	setCursor(Qt::OpenHandCursor);

	updatePaletteColors();

	style::PaletteChanged(
	) | rpl::on_next([=] {
		if (!_customColors) {
			updatePaletteColors();
			update();
		}
	}, _lifetime);

	_animTimer.setInterval(16);
	connect(&_animTimer, &QTimer::timeout, this, [=] {
		onAnimationTick();
	});
}

Arrow3DWidget::~Arrow3DWidget() {
	_animTimer.stop();
	if (_contextDestroyedConnection) {
		disconnect(_contextDestroyedConnection);
		_contextDestroyedConnection = {};
	}
	if (context() && context()->isValid()) {
		makeCurrent();
		cleanupGL();
		doneCurrent();
	}
}

void Arrow3DWidget::setSupporterNumber(int number) {
	_supporterNumber = number;
	setSupporterText((number > 0) ? QString("#%1").arg(number) : QString());
}

void Arrow3DWidget::setSupporterText(const QString &text) {
	if (_engravingText == text && (!_engravingMask.isNull() || text.isEmpty())) {
		return;
	}
	_engravingText = text;
	if (text.isEmpty()) {
		_engravingMask = QImage();
		_hasEngraving = false;
	} else {
		_engravingMask = createEngravingMask(text);
		_hasEngraving = !_engravingMask.isNull();
	}
	_engravingDirty = true;
	update();
}

int Arrow3DWidget::supporterNumber() const {
	return _supporterNumber;
}

void Arrow3DWidget::setColors(
		const QColor &gradient1,
		const QColor &gradient2,
		const QColor &edgeColor) {
	_customColors = true;
	_gradientColor1 = gradient1;
	_gradientColor2 = gradient2;
	_edgeColor = edgeColor.isValid()
		? edgeColor
		: BlendColors(gradient1, st::boxBg->c, 0.5f);
	_backgroundDirty = true;
	update();
}

void Arrow3DWidget::setAccentColor(
		const QColor &accent,
		const QColor &background) {
	const auto bg = background.isValid() ? background : st::boxBg->c;
	setColors(
		ShiftColor(accent, -10.0f, 0.75f, 1.15f),
		ShiftColor(accent, 18.0f, 0.60f, 1.10f),
		BlendColors(accent, bg, 0.5f));
	setNightMode(bg.lightnessF() < 0.5);
}

void Arrow3DWidget::setIdleAnimationEnabled(bool enabled) {
	_idleEnabled = enabled;
	if (!enabled) {
		_idleMode = IdleMode::None;
		_angleX3 = 0.0f;
	} else {
		_idleWait = 0.8f;
	}
}

bool Arrow3DWidget::isIdleAnimationEnabled() const {
	return _idleEnabled;
}

void Arrow3DWidget::setNightMode(bool night) {
	if (night) {
		_spec1 = 1.0f;
		_spec2 = 0.2f;
	} else {
		_spec1 = 2.0f;
		_spec2 = 0.13f;
	}
	update();
}

void Arrow3DWidget::resetRotation() {
	_idleMode = IdleMode::None;
	_returning = false;
	_angleX = 0.0f;
	_angleY = 0.0f;
	_angleX2 = 0.0f;
	_angleX3 = 0.0f;
	update();
}

bool Arrow3DWidget::isGlActive() const {
	return _glInitialized && !_glFailed;
}

QSize Arrow3DWidget::sizeHint() const {
	return QSize(160, 160);
}

QSize Arrow3DWidget::minimumSizeHint() const {
	return QSize(64, 64);
}

void Arrow3DWidget::updatePaletteColors() {
	const auto accent = st::windowBgActive->c;
	const auto bg = st::boxBg->c;
	_gradientColor1 = ShiftColor(accent, -10.0f, 0.75f, 1.15f);
	_gradientColor2 = ShiftColor(accent, 18.0f, 0.60f, 1.10f);
	_edgeColor = BlendColors(accent, bg, 0.5f);
	_backgroundDirty = true;
	setNightMode(bg.lightnessF() < 0.5);
}

void Arrow3DWidget::initializeGL() {
	_glInitialized = false;
	_glFailed = false;

	if (_contextDestroyedConnection) {
		disconnect(_contextDestroyedConnection);
		_contextDestroyedConnection = {};
	}

	const auto ctx = context();
	if (!ctx || !ctx->isValid()) {
		handleGlFailure(u"OpenGL context is invalid."_q);
		return;
	}
	_contextDestroyedConnection = connect(
		ctx,
		&QOpenGLContext::aboutToBeDestroyed,
		this,
		[this] {
			makeCurrent();
			cleanupGL();
			doneCurrent();
		},
		Qt::DirectConnection);

	initializeOpenGLFunctions();
	cleanupGL();

	std::vector<Vertex> vertices;
	if (!loadBinObj(QString::fromLatin1(kModelResource), vertices)
			|| vertices.empty()) {
		handleGlFailure(u"Failed to parse extera_arrow.binobj."_q);
		return;
	}
	_vertexCount = int(vertices.size());

	_vbo = std::make_unique<QOpenGLBuffer>(QOpenGLBuffer::VertexBuffer);
	_vbo->setUsagePattern(QOpenGLBuffer::StaticDraw);
	if (!_vbo->create() || !_vbo->bind()) {
		handleGlFailure(u"Failed to allocate vertex buffer."_q);
		return;
	}
	_vbo->allocate(
		vertices.data(),
		int(vertices.size() * sizeof(Vertex)));
	_vbo->release();

	if (!initShaders()) {
		handleGlFailure(u"Failed to compile/link arrow shaders."_q);
		return;
	}
	if (!initTextures()) {
		handleGlFailure(u"Failed to initialize arrow textures."_q);
		return;
	}

	_engravingDirty = true;
	_backgroundDirty = true;
	_glInitialized = true;
	glClearColor(0.0f, 0.0f, 0.0f, 0.0f);
}

void Arrow3DWidget::resizeGL(int w, int h) {
	const auto dpr = devicePixelRatioF();
	_viewportWidth = std::max(1, int(std::lround(w * dpr)));
	_viewportHeight = std::max(1, int(std::lround(h * dpr)));
	const auto aspect = float(std::max(1, w)) / float(std::max(1, h));
	_projection.setToIdentity();
	_projection.perspective(kFieldOfView, aspect, kZNear, kZFar);
}

void Arrow3DWidget::paintGL() {
	if (_glFailed
			|| !_glInitialized
			|| !_program
			|| !_program->isLinked()
			|| !_vbo
			|| _vertexCount <= 0) {
		return;
	}

	if (_engravingDirty) {
		uploadEngravingTexture();
	}
	if (_backgroundDirty) {
		uploadBackgroundTexture();
	}

	glViewport(0, 0, _viewportWidth, _viewportHeight);
	glClearColor(0.0f, 0.0f, 0.0f, 0.0f);
	glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
	glEnable(GL_DEPTH_TEST);
	glDisable(GL_BLEND);

	QMatrix4x4 world;
	world.translate(0.0f, _angleX2, 0.0f);
	world.rotate(-_angleY, 1.0f, 0.0f, 0.0f);
	world.rotate(-_angleX - _angleX3, 0.0f, 1.0f, 0.0f);

	QMatrix4x4 view;
	view.lookAt(
		QVector3D(0.0f, 0.0f, 100.0f),
		QVector3D(0.0f, 0.0f, 0.0f),
		QVector3D(0.0f, 1.0f, 0.0f));

	const auto mvp = _projection * view * world;

	if (!_program->bind()) {
		glDisable(GL_DEPTH_TEST);
		return;
	}

	if (_whiteTexture) {
		_whiteTexture->bind(0);
	}
	if (_flecksTexture) {
		_flecksTexture->bind(1);
	}
	if (_backgroundTexture) {
		_backgroundTexture->bind(2);
	}
	if (_engravingTexture) {
		_engravingTexture->bind(3);
	}

	_program->setUniformValue("u_Texture", 0);
	_program->setUniformValue("u_NormalMap", 1);
	_program->setUniformValue("u_BackgroundTexture", 2);
	_program->setUniformValue("u_Engraving", 3);
	_program->setUniformValue("engraving", _hasEngraving ? 1.0f : 0.0f);
	_program->setUniformValue("f_xOffset", _xOffset);
	_program->setUniformValue("f_alpha", _enterAlpha);
	_program->setUniformValue("uMVPMatrix", mvp);
	_program->setUniformValue("world", world);
	_program->setUniformValue("spec1", _spec1);
	_program->setUniformValue("spec2", _spec2);
	_program->setUniformValue("u_diffuse", _diffuse);
	_program->setUniformValue("normalSpec", _normalSpec);
	_program->setUniformValue("gradientColor1", ToVec3(_gradientColor1));
	_program->setUniformValue("gradientColor2", ToVec3(_gradientColor2));
	_program->setUniformValue("normalSpecColor", QVector3D(1.0f, 1.0f, 1.0f));
	_program->setUniformValue("specColor", QVector3D(1.0f, 1.0f, 1.0f));
	_program->setUniformValue(
		"resolution",
		QVector2D(float(_viewportWidth), float(_viewportHeight)));
	_program->setUniformValue(
		"gradientPosition",
		QVector4D(0.0f, 1.0f, 0.0f, 1.0f));

	_vbo->bind();
	const auto posLoc = _program->attributeLocation("vPosition");
	const auto normLoc = _program->attributeLocation("a_Normal");
	const auto uvLoc = _program->attributeLocation("a_TexCoordinate");

	if (posLoc >= 0) {
		_program->enableAttributeArray(posLoc);
		_program->setAttributeBuffer(
			posLoc,
			GL_FLOAT,
			offsetof(Vertex, px),
			3,
			sizeof(Vertex));
	}
	if (normLoc >= 0) {
		_program->enableAttributeArray(normLoc);
		_program->setAttributeBuffer(
			normLoc,
			GL_FLOAT,
			offsetof(Vertex, nx),
			3,
			sizeof(Vertex));
	}
	if (uvLoc >= 0) {
		_program->enableAttributeArray(uvLoc);
		_program->setAttributeBuffer(
			uvLoc,
			GL_FLOAT,
			offsetof(Vertex, u),
			2,
			sizeof(Vertex));
	}

	glDrawArrays(GL_TRIANGLES, 0, _vertexCount);

	if (posLoc >= 0) {
		_program->disableAttributeArray(posLoc);
	}
	if (normLoc >= 0) {
		_program->disableAttributeArray(normLoc);
	}
	if (uvLoc >= 0) {
		_program->disableAttributeArray(uvLoc);
	}

	_vbo->release();
	_program->release();
	glActiveTexture(GL_TEXTURE0);
	glDisable(GL_DEPTH_TEST);
}

void Arrow3DWidget::paintEvent(QPaintEvent *event) {
	if (_glFailed) {
		QPainter painter(this);
		paintFallback2D(painter);
		return;
	}
	QOpenGLWidget::paintEvent(event);
}

void Arrow3DWidget::showEvent(QShowEvent *event) {
	QOpenGLWidget::showEvent(event);
	_frameClock.restart();
	if (!_animTimer.isActive()) {
		_animTimer.start();
	}
}

void Arrow3DWidget::hideEvent(QHideEvent *event) {
	_animTimer.stop();
	QOpenGLWidget::hideEvent(event);
}

void Arrow3DWidget::mousePressEvent(QMouseEvent *event) {
	if (event->button() != Qt::LeftButton) {
		QOpenGLWidget::mousePressEvent(event);
		return;
	}
	_dragging = true;
	_returning = false;
	_idleMode = IdleMode::None;
	_angleX += _angleX3;
	_angleX3 = 0.0f;
	_pressPos = event->position();
	_lastMousePos = _pressPos;
	setCursor(Qt::ClosedHandCursor);
	event->accept();
}

void Arrow3DWidget::mouseMoveEvent(QMouseEvent *event) {
	if (!_dragging) {
		QOpenGLWidget::mouseMoveEvent(event);
		return;
	}
	const auto pos = event->position();
	const auto delta = pos - _lastMousePos;
	_lastMousePos = pos;

	_angleX -= float(delta.x()) * 0.7f;
	_angleY = std::clamp(_angleY - float(delta.y()) * 0.35f, -65.0f, 65.0f);
	update();
	event->accept();
}

void Arrow3DWidget::mouseReleaseEvent(QMouseEvent *event) {
	if (event->button() != Qt::LeftButton || !_dragging) {
		QOpenGLWidget::mouseReleaseEvent(event);
		return;
	}
	_dragging = false;
	setCursor(Qt::OpenHandCursor);

	const auto moved = (event->position() - _pressPos).manhattanLength();
	if (moved < 5.0 && std::abs(_angleX) < 10.0f) {
		const auto half = std::max(1.0f, float(width()) * 0.5f);
		const auto dx = (half - float(event->position().x())) / half;
		const auto dy = (half - float(event->position().y())) / half;
		_angleX = dx * 45.0f;
		_angleY = dy * 25.0f;
	}
	startReturnAnimation();
	event->accept();
}

bool Arrow3DWidget::loadBinObj(
		const QString &resourcePath,
		std::vector<Vertex> &outVertices) {
	QFile file(resourcePath);
	if (!file.open(QIODevice::ReadOnly)) {
		return false;
	}
	QDataStream stream(&file);
	stream.setByteOrder(QDataStream::BigEndian);
	stream.setFloatingPointPrecision(QDataStream::SinglePrecision);

	const auto readFloatArray = [&](std::vector<float> &dest) -> bool {
		qint32 count = 0;
		stream >> count;
		if (stream.status() != QDataStream::Ok
				|| count < 0
				|| count > kMaxArrayElements) {
			return false;
		}
		dest.resize(size_t(count));
		for (qint32 i = 0; i < count; ++i) {
			stream >> dest[size_t(i)];
		}
		return stream.status() == QDataStream::Ok;
	};

	std::vector<float> vertices;
	std::vector<float> textures;
	std::vector<float> normals;
	if (!readFloatArray(vertices)
			|| !readFloatArray(textures)
			|| !readFloatArray(normals)) {
		return false;
	}

	qint32 numFaces = 0;
	stream >> numFaces;
	if (stream.status() != QDataStream::Ok
			|| numFaces <= 0
			|| numFaces > kMaxModelVertices) {
		return false;
	}

	outVertices.resize(size_t(numFaces));
	const auto vSize = qint32(vertices.size());
	const auto tSize = qint32(textures.size());
	const auto nSize = qint32(normals.size());

	for (qint32 i = 0; i < numFaces; ++i) {
		qint32 posIdx = 0;
		qint32 texIdx = 0;
		qint32 normIdx = 0;
		stream >> posIdx >> texIdx >> normIdx;
		if (stream.status() != QDataStream::Ok) {
			return false;
		}

		auto &vtx = outVertices[size_t(i)];
		const auto pOff = posIdx * 3;
		if (pOff >= 0 && pOff + 2 < vSize) {
			vtx.px = vertices[size_t(pOff)];
			vtx.py = vertices[size_t(pOff + 1)];
			vtx.pz = vertices[size_t(pOff + 2)];
		}

		const auto tOff = texIdx * 2;
		if (tOff >= 0 && tOff + 1 < tSize) {
			vtx.u = textures[size_t(tOff)];
			vtx.v = 1.0f - textures[size_t(tOff + 1)];
		}

		const auto nOff = normIdx * 3;
		if (nOff >= 0 && nOff + 2 < nSize) {
			vtx.nx = normals[size_t(nOff)];
			vtx.ny = normals[size_t(nOff + 1)];
			vtx.nz = normals[size_t(nOff + 2)];
		}
	}
	return true;
}

bool Arrow3DWidget::initShaders() {
	const auto rawVs = ReadResourceText(QString::fromLatin1(kVertexShaderResource));
	const auto rawFs = ReadResourceText(QString::fromLatin1(kFragmentShaderResource));
	if (rawVs.isEmpty() || rawFs.isEmpty()) {
		return false;
	}

	const auto isEs = context()
		&& (context()->isOpenGLES()
			|| context()->format().renderableType() == QSurfaceFormat::OpenGLES);

	const auto preamble = QString::fromLatin1(
		"#ifndef GL_ES\n"
		"#define highp\n"
		"#define mediump\n"
		"#define lowp\n"
		"#endif\n");

	auto fsBody = rawFs;
	if (!isEs) {
		fsBody.replace(QStringLiteral("precision highp float;"), QString());
		fsBody.replace(QStringLiteral("precision mediump float;"), QString());
		fsBody.replace(QStringLiteral("precision lowp float;"), QString());
	}

	const auto tryCompile = [&](const QString &versionPrefix) -> bool {
		auto program = std::make_unique<QOpenGLShaderProgram>();
		const auto vsCode = versionPrefix + preamble + rawVs;
		const auto fsCode = versionPrefix + preamble + fsBody;
		if (!program->addShaderFromSourceCode(QOpenGLShader::Vertex, vsCode)) {
			LOG(("Extera Arrow3D VS compile error: %1").arg(program->log()));
			return false;
		}
		if (!program->addShaderFromSourceCode(QOpenGLShader::Fragment, fsCode)) {
			LOG(("Extera Arrow3D FS compile error: %1").arg(program->log()));
			return false;
		}
		if (!program->link()) {
			LOG(("Extera Arrow3D shader link error: %1").arg(program->log()));
			return false;
		}
		_program = std::move(program);
		return true;
	};

	const auto primaryVersion = isEs
		? QStringLiteral("#version 100\n")
		: QStringLiteral("#version 120\n");
	if (tryCompile(primaryVersion)) {
		return true;
	}
	return tryCompile(QString());
}

bool Arrow3DWidget::initTextures() {
	_whiteTexture = MakeSolidTexture(Qt::white, QOpenGLTexture::ClampToEdge);
	if (!_whiteTexture) {
		return false;
	}

	QImage flecksImage(QString::fromLatin1(kFlecksResource));
	if (!flecksImage.isNull()) {
		flecksImage = flecksImage.convertToFormat(QImage::Format_RGBA8888);
		_flecksTexture = std::make_unique<QOpenGLTexture>(
			flecksImage,
			QOpenGLTexture::DontGenerateMipMaps);
		if (_flecksTexture->isCreated()) {
			_flecksTexture->setMinMagFilters(
				QOpenGLTexture::Linear,
				QOpenGLTexture::Linear);
			_flecksTexture->setWrapMode(QOpenGLTexture::Repeat);
		} else {
			_flecksTexture.reset();
		}
	}
	if (!_flecksTexture) {
		_flecksTexture = MakeSolidTexture(
			QColor(128, 128, 255, 255),
			QOpenGLTexture::Repeat);
	}

	_backgroundTexture = MakeSolidTexture(
		_edgeColor,
		QOpenGLTexture::ClampToEdge);
	if (!_backgroundTexture) {
		return false;
	}

	_engravingTexture = MakeSolidTexture(
		QColor(0, 0, 0, 0),
		QOpenGLTexture::ClampToEdge);
	return (_flecksTexture != nullptr) && (_engravingTexture != nullptr);
}

void Arrow3DWidget::uploadEngravingTexture() {
	_engravingDirty = false;
	if (!_hasEngraving || _engravingMask.isNull()) {
		_engravingTexture = MakeSolidTexture(
			QColor(0, 0, 0, 0),
			QOpenGLTexture::ClampToEdge);
		return;
	}
	const auto rgba = _engravingMask.convertToFormat(QImage::Format_RGBA8888);
	_engravingTexture = std::make_unique<QOpenGLTexture>(
		rgba,
		QOpenGLTexture::DontGenerateMipMaps);
	if (_engravingTexture->isCreated()) {
		_engravingTexture->setMinMagFilters(
			QOpenGLTexture::Linear,
			QOpenGLTexture::Linear);
		_engravingTexture->setWrapMode(QOpenGLTexture::ClampToEdge);
	} else {
		_engravingTexture.reset();
		_hasEngraving = false;
	}
}

void Arrow3DWidget::uploadBackgroundTexture() {
	_backgroundDirty = false;
	_backgroundTexture = MakeSolidTexture(
		_edgeColor,
		QOpenGLTexture::ClampToEdge);
}

void Arrow3DWidget::cleanupGL() {
	_program.reset();
	if (_vbo && _vbo->isCreated()) {
		_vbo->destroy();
	}
	_vbo.reset();
	_whiteTexture.reset();
	_flecksTexture.reset();
	_backgroundTexture.reset();
	_engravingTexture.reset();
	_glInitialized = false;
}

void Arrow3DWidget::handleGlFailure(const QString &reason) {
	LOG(("Extera Arrow3DWidget fallback to 2D: %1").arg(reason));
	cleanupGL();
	_glFailed = true;
	update();
}

void Arrow3DWidget::paintFallback2D(QPainter &painter) {
	painter.setRenderHints(
		QPainter::Antialiasing
		| QPainter::TextAntialiasing
		| QPainter::SmoothPixmapTransform);

	const auto w = float(width());
	const auto h = float(height());
	const auto side = std::min(w, h) * 0.72f;
	if (side <= 2.0f) {
		return;
	}

	const auto yawDeg = std::fmod(_angleX + _angleX3, 360.0f);
	const auto yawRad = yawDeg * (3.14159265f / 180.0f);
	const auto cosYaw = std::cos(yawRad);
	const auto scaleX = std::max(0.12f, std::abs(cosYaw));
	const auto backSide = (cosYaw < 0.0f);

	painter.save();
	painter.setOpacity(double(std::clamp(_enterAlpha, 0.25f, 1.0f)));
	painter.translate(w * 0.5, h * 0.5 + double(_angleX2) * 1.5);
	painter.scale(double(scaleX), 1.0);
	painter.rotate(double(_angleY) * 0.2);

	const auto r = side * 0.5;
	QPainterPath arrow;
	arrow.moveTo(0.0, -r * 0.88);
	arrow.lineTo(r * 0.82, r * 0.78);
	arrow.lineTo(0.0, r * 0.34);
	arrow.lineTo(-r * 0.82, r * 0.78);
	arrow.closeSubpath();

	QLinearGradient grad(-r, -r, r, r);
	grad.setColorAt(0.0, _gradientColor1);
	grad.setColorAt(1.0, _gradientColor2);
	painter.setPen(QPen(_edgeColor, 2.0, Qt::SolidLine, Qt::RoundCap, Qt::RoundJoin));
	painter.setBrush(grad);
	painter.drawPath(arrow);

	if (backSide && _hasEngraving && !_engravingText.isEmpty()) {
		auto font = painter.font();
		font.setBold(true);
		font.setPixelSize(std::max(10, int(side * 0.14f)));
		painter.setFont(font);
		painter.setPen(QColor(255, 255, 255, 215));
		painter.drawText(
			QRectF(-r * 0.6, -r * 0.2, r * 1.2, r * 0.6),
			Qt::AlignCenter,
			_engravingText);
	}
	painter.restore();
}

void Arrow3DWidget::onAnimationTick() {
	const auto elapsedMs = _frameClock.restart();
	const auto dt = std::clamp(float(elapsedMs) / 1000.0f, 0.001f, 0.05f);

	if (_enterAlpha < 1.0f) {
		_enterAlpha = std::min(1.0f, _enterAlpha + dt / 0.22f);
	}
	_xOffset = std::fmod(_xOffset + dt * 0.03f, 1.0f);
	_floatPhase += dt * 1.6f;

	if (!_dragging) {
		if (_returning) {
			_returnElapsed += dt;
			const auto t = std::min(1.0f, _returnElapsed / 0.6f);
			const auto k = 1.0f - Overshoot(t, 1.4f);
			_angleX = _returnFromX * k;
			_angleY = _returnFromY * k;
			_angleX2 = _returnFromX2 * k;
			_angleX3 = _returnFromX3 * k;
			if (t >= 1.0f) {
				_returning = false;
				_angleX = 0.0f;
				_angleY = 0.0f;
				_angleX2 = 0.0f;
				_angleX3 = 0.0f;
				_idleWait = 2.0f;
			}
		} else if (_idleEnabled) {
			_angleX2 = std::sin(_floatPhase) * 1.2f;
			if (_idleMode == IdleMode::None) {
				_idleWait -= dt;
				if (_idleWait <= 0.0f) {
					startNextIdleAnimation();
				}
			} else {
				_idleElapsed += dt;
				if (_idleMode == IdleMode::SlowSpin) {
					const auto t = std::min(1.0f, _idleElapsed / 8.0f);
					_angleX3 = 360.0f * EaseInOutCubic(t);
					if (t >= 1.0f) {
						_angleX3 = 0.0f;
						_idleMode = IdleMode::None;
						_idleWait = 2.0f;
					}
				} else if (_idleMode == IdleMode::Flip) {
					if (_idleElapsed < 0.6f) {
						_angleX3 = 180.0f * EaseInOutCubic(_idleElapsed / 0.6f);
					} else if (_idleElapsed < 2.6f) {
						_angleX3 = 180.0f;
					} else if (_idleElapsed < 3.2f) {
						_angleX3 = 180.0f + 180.0f * EaseInOutCubic((_idleElapsed - 2.6f) / 0.6f);
					} else {
						_angleX3 = 0.0f;
						_idleMode = IdleMode::None;
						_idleWait = 2.0f;
					}
				} else if (_idleMode == IdleMode::Tilt) {
					if (_idleElapsed < 2.2f) {
						_angleY = 42.0f * EaseOutQuint(_idleElapsed / 2.2f);
					} else if (_idleElapsed < 2.8f) {
						_angleY = 42.0f * (1.0f - Overshoot((_idleElapsed - 2.2f) / 0.6f));
					} else {
						_angleY = 0.0f;
						_idleMode = IdleMode::None;
						_idleWait = 2.0f;
					}
				}
			}
		}
	}

	update();
}

void Arrow3DWidget::startReturnAnimation() {
	_returning = true;
	_returnElapsed = 0.0f;
	_returnFromX = std::fmod(_angleX, 360.0f);
	if (_returnFromX > 180.0f) {
		_returnFromX -= 360.0f;
	} else if (_returnFromX < -180.0f) {
		_returnFromX += 360.0f;
	}
	_angleX = _returnFromX;
	_returnFromY = _angleY;
	_returnFromX2 = _angleX2;
	_returnFromX3 = _angleX3;
}

void Arrow3DWidget::startNextIdleAnimation() {
	_idleElapsed = 0.0f;
	const auto modeIndex = _idleStep % 3;
	++_idleStep;
	if (modeIndex == 0) {
		_idleMode = IdleMode::SlowSpin;
	} else if (modeIndex == 1) {
		_idleMode = IdleMode::Flip;
	} else {
		_idleMode = IdleMode::Tilt;
	}
}

QImage Arrow3DWidget::createEngravingMask(const QString &text) {
	if (text.isEmpty()) {
		return QImage();
	}
	QImage mask(kEngravingSize, kEngravingSize, QImage::Format_Alpha8);
	mask.fill(0);

	QPainter painter(&mask);
	if (!painter.isActive()) {
		return QImage();
	}
	painter.setRenderHints(
		QPainter::Antialiasing | QPainter::TextAntialiasing);

	QFont font = painter.font();
	font.setBold(true);
	const auto pixelSize = qRound(kEngravingSize * kEngravingTextSize);
	font.setPixelSize(pixelSize);
	font.setLetterSpacing(
		QFont::AbsoluteSpacing,
		kEngravingSize * kEngravingTextSize * kEngravingLetterSpacing);
	painter.setFont(font);
	painter.setPen(QColor(255, 255, 255, 255));

	const auto fm = QFontMetricsF(font);
	const auto textWidth = fm.horizontalAdvance(text);
	const auto baselineY = (fm.ascent() - fm.descent()) * 0.5;
	const auto cx = kEngravingSize * kEngravingCenterX;
	const auto cy = kEngravingSize * kEngravingCenterY;

	painter.translate(cx, cy);
	painter.rotate(kEngravingAngle);
	painter.drawText(QPointF(-textWidth * 0.5, baselineY), text);
	painter.end();

	const auto margin = int(std::ceil(std::max(textWidth, double(pixelSize)) * 0.75)) + 16;
	const auto blurRect = QRect(
		int(std::floor(cx)) - margin,
		int(std::floor(cy)) - margin,
		margin * 2,
		margin * 2);
	BlurAlphaRegion(mask, blurRect);
	return mask;
}

} // namespace Extera
