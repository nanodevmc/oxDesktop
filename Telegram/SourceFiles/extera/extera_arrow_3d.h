#pragma once

#include <QOpenGLWidget>
#include <QOpenGLFunctions>
#include <QOpenGLBuffer>
#include <QOpenGLShaderProgram>
#include <QOpenGLTexture>
#include <QtGui/QColor>
#include <QtGui/QImage>
#include <QtGui/QMatrix4x4>
#include <QtCore/QElapsedTimer>
#include <QtCore/QMetaObject>
#include <QtCore/QPointF>
#include <QtCore/QTimer>

#include <rpl/rpl.h>

#include <memory>
#include <vector>

namespace Extera {

class Arrow3DWidget : public QOpenGLWidget, protected QOpenGLFunctions {
public:
	explicit Arrow3DWidget(QWidget *parent = nullptr);
	~Arrow3DWidget() override;

	void setSupporterNumber(int number);
	void setSupporterText(const QString &text);
	[[nodiscard]] int supporterNumber() const;

	void setColors(
		const QColor &gradient1,
		const QColor &gradient2,
		const QColor &edgeColor = QColor());
	void setAccentColor(
		const QColor &accent,
		const QColor &background = QColor());

	void setIdleAnimationEnabled(bool enabled);
	[[nodiscard]] bool isIdleAnimationEnabled() const;

	void setNightMode(bool night);
	void resetRotation();

	[[nodiscard]] bool isGlActive() const;

	[[nodiscard]] QSize sizeHint() const override;
	[[nodiscard]] QSize minimumSizeHint() const override;

protected:
	void initializeGL() override;
	void resizeGL(int w, int h) override;
	void paintGL() override;
	void paintEvent(QPaintEvent *event) override;
	void showEvent(QShowEvent *event) override;
	void hideEvent(QHideEvent *event) override;
	void mousePressEvent(QMouseEvent *event) override;
	void mouseMoveEvent(QMouseEvent *event) override;
	void mouseReleaseEvent(QMouseEvent *event) override;

private:
	struct Vertex {
		float px = 0.0f;
		float py = 0.0f;
		float pz = 0.0f;
		float nx = 0.0f;
		float ny = 0.0f;
		float nz = 0.0f;
		float u = 0.0f;
		float v = 0.0f;
	};

	enum class IdleMode {
		None,
		SlowSpin,
		Flip,
		Tilt,
	};

	[[nodiscard]] bool loadBinObj(
		const QString &resourcePath,
		std::vector<Vertex> &outVertices);
	[[nodiscard]] bool initShaders();
	[[nodiscard]] bool initTextures();
	void uploadEngravingTexture();
	void uploadBackgroundTexture();
	void cleanupGL();
	void handleGlFailure(const QString &reason);
	void paintFallback2D(QPainter &painter);

	void updatePaletteColors();
	void onAnimationTick();
	void startReturnAnimation();
	void startNextIdleAnimation();

	[[nodiscard]] static QImage createEngravingMask(const QString &text);

	std::unique_ptr<QOpenGLShaderProgram> _program;
	std::unique_ptr<QOpenGLBuffer> _vbo;
	std::unique_ptr<QOpenGLTexture> _whiteTexture;
	std::unique_ptr<QOpenGLTexture> _flecksTexture;
	std::unique_ptr<QOpenGLTexture> _backgroundTexture;
	std::unique_ptr<QOpenGLTexture> _engravingTexture;

	QMatrix4x4 _projection;
	int _viewportWidth = 1;
	int _viewportHeight = 1;
	int _vertexCount = 0;

	bool _glInitialized = false;
	bool _glFailed = false;

	int _supporterNumber = 0;
	QString _engravingText;
	QImage _engravingMask;
	bool _engravingDirty = false;
	bool _hasEngraving = false;

	QColor _gradientColor1;
	QColor _gradientColor2;
	QColor _edgeColor;
	bool _customColors = false;
	bool _backgroundDirty = true;

	float _spec1 = 1.0f;
	float _spec2 = 0.2f;
	float _diffuse = 1.0f;
	float _normalSpec = 0.04f;
	float _enterAlpha = 0.0f;
	float _xOffset = 0.0f;

	float _angleX = 0.0f;
	float _angleY = 0.0f;
	float _angleX2 = 0.0f;
	float _angleX3 = 0.0f;

	bool _dragging = false;
	QPointF _pressPos;
	QPointF _lastMousePos;

	bool _returning = false;
	float _returnElapsed = 0.0f;
	float _returnFromX = 0.0f;
	float _returnFromY = 0.0f;
	float _returnFromX2 = 0.0f;
	float _returnFromX3 = 0.0f;

	bool _idleEnabled = true;
	IdleMode _idleMode = IdleMode::None;
	float _idleElapsed = 0.0f;
	float _idleWait = 0.6f;
	int _idleStep = 0;
	float _floatPhase = 0.0f;

	QTimer _animTimer;
	QElapsedTimer _frameClock;
	QMetaObject::Connection _contextDestroyedConnection;
	rpl::lifetime _lifetime;

};

} // namespace Extera
