import math
import os

try:
    __file__
except NameError:
    try:
        __file__ = file
    except NameError:
        __file__ = ""

BG = 0xFF100F16
FG = 0xFFF4F1F2
SUB = 0xFFB9B2B8
MUTED = 0xFF70666E
LINE = 0xFF2C2830
ACCENT = 0xFFFFB8A6
CARD = 0xFFFFD9CF
CARD_DECO = 0xFFF4C0B3
CARD_INK = 0xFFE59F8F
BADGE = 0xFF2A2128
BADGE_LINE = 0xFF4A3A44

BANNER_W, BANNER_H = 1920, 1080

TITLE_1 = "Wave"
TITLE_2 = "Scroller"
SUBTITLE = ("Алфавитный скроллер", "с упругой волной.")
VERSION = "1.0.0"
FOOT = "kinetic alphabet  ·  exteraGram"
ALPHABET = "ABCDEFGHIJKLM"


def ripple(cx, cy, r, lobes, amp, rot=0.0, n=540):
    pts = []
    for i in range(n):
        t = 2.0 * math.pi * i / n
        rr = r + amp * math.sin(lobes * t + rot)
        pts.append((cx + rr * math.cos(t), cy + rr * math.sin(t)))
    return pts


def arc(cx, cy, r, a0, a1, n=96):
    pts = []
    for i in range(n + 1):
        a = math.radians(a0 + (a1 - a0) * i / float(n))
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def sine(x0, x1, y0, amp, wl, phase=0.0, n=160):
    pts = []
    for i in range(n + 1):
        x = x0 + (x1 - x0) * i / float(n)
        pts.append((x, y0 + amp * math.sin((x - x0) / wl * 2 * math.pi + phase)))
    return pts


def _a(color, alpha):
    return (int(max(0.0, min(1.0, alpha)) * 255) << 24) | (color & 0xFFFFFF)


def gauss(d, sigma):
    return math.exp(-(d * d) / (2.0 * sigma * sigma))


def wave_bars(ops, cx, cy, k, color, bars=5, spacing=62, length=128, thick=22, bulge=58, sigma=0.95,
              finger=True, finger_color=None):
    mid = (bars - 1) / 2.0
    for i in range(bars):
        g = gauss(i - mid, sigma)
        x0 = cx - length * k / 2 - bulge * k * g
        y = cy + (i - mid) * spacing * k
        al = 0.34 + 0.66 * g
        ops.append(("line", [(x0, y), (x0 + length * k * (0.78 + 0.22 * g), y)], thick * k, _a(color, al), True))
    if finger:
        fx = cx + (length / 2 + 46) * k
        ops.append(("circle", fx, cy, 26 * k, _a(finger_color or color, 0.22)))
        ops.append(("circle", fx, cy, 11 * k, finger_color or color))


def banner_scene():
    s = []
    s.append(("rect", 0, 0, BANNER_W, BANNER_H, BG))

    s.append(("text", TITLE_1, 96, 360, 176, FG, "bold", "l", -3))
    s.append(("text", TITLE_2, 96, 540, 176, ACCENT, "bold", "l", -3))
    s.append(("text", SUBTITLE[0], 104, 640, 40, SUB, "light", "l", 0))
    s.append(("text", SUBTITLE[1], 104, 694, 40, SUB, "light", "l", 0))

    s.append(("rrect", 104, 760, 150, 54, 27, 0xFF17151D))
    s.append(("rrect_stroke", 104, 760, 150, 54, 27, 2, 0xFF3C3440))
    s.append(("line", sine(124, 144, 787, 5, 20, 0.0, 24), 3, ACCENT, True))
    s.append(("text", VERSION, 156, 795, 23, FG, "regular", "l", 0))

    s.append(("line", sine(104, 944, 930, 5, 140, 0.0, 200), 2, LINE, False))
    s.append(("line", sine(104, 244, 930, 5, 140, 0.0, 40), 4, ACCENT, True))
    s.append(("text", FOOT, 104, 988, 26, MUTED, "light", "l", 1))

    cx0, cy0, cw, ch, cr = 1008, 48, 864, 984, 104
    s.append(("rrect", cx0, cy0, cw, ch, cr, CARD))
    s.append(("clip_begin", cx0, cy0, cw, ch, cr))
    for i, rad in enumerate((150, 250, 350)):
        s.append(("line", arc(cx0, cy0, rad, 0, 90, 100), 40, _a(CARD_DECO, 1.0 - i * 0.18), False))
    for i in range(3):
        s.append(("line", sine(cx0 - 20, cx0 + cw + 20, cy0 + ch - 140 + i * 62, 40, 520, i * 0.9, 180),
                  34, _a(CARD_DECO, 0.95 - i * 0.2), False))
    ax = cx0 + cw - 70
    fy = 470
    for i, ch_ in enumerate(ALPHABET):
        y = 150 + i * 62
        g = gauss(y - fy, 130)
        s.append(("text", ch_, ax - 84 * g, y + 14, 44 + 20 * g, _a(CARD_INK, 0.55 + 0.45 * g), "light", "c", 0))
    s.append(("clip_end",))

    bx, by = 1388, 540
    s.append(("poly", ripple(bx, by, 268, 6, 20, 0.4), BADGE))
    s.append(("poly", ripple(bx, by, 232, 6, 16, 0.4), _a(BADGE_LINE, 0.55)))
    s.append(("poly", ripple(bx, by, 224, 6, 15, 0.4), BADGE))
    wave_bars(s, bx - 8, by, 1.5, ACCENT, 5, 62, 128, 22, 58)
    return s


WIDE_W, WIDE_H = 1280, 409


def banner_wide_scene():
    s = []
    s.append(("rect", 0, 0, WIDE_W, WIDE_H, BG))
    s.append(("rrect", 64, 46, 128, 42, 21, 0xFF17151D))
    s.append(("rrect_stroke", 64, 46, 128, 42, 21, 2, 0xFF3C3440))
    s.append(("line", sine(80, 98, 67, 4, 18, 0.0, 24), 3, ACCENT, True))
    s.append(("text", VERSION, 108, 74, 19, FG, "regular", "l", 0))
    s.append(("text", TITLE_1, 60, 208, 124, FG, "bold", "l", -3))
    s.append(("text", TITLE_2, 60, 322, 124, ACCENT, "bold", "l", -3))
    s.append(("text", SUBTITLE[0] + " " + SUBTITLE[1], 66, 372, 25, SUB, "light", "l", 0))
    cx0, cy0, cw, ch, cr = 736, 24, 520, 361, 64
    s.append(("rrect", cx0, cy0, cw, ch, cr, CARD))
    s.append(("clip_begin", cx0, cy0, cw, ch, cr))
    for i, rad in enumerate((90, 150, 210)):
        s.append(("line", arc(cx0, cy0, rad, 0, 90, 80), 24, _a(CARD_DECO, 1.0 - i * 0.18), False))
    for i in range(3):
        s.append(("line", sine(cx0 - 20, cx0 + cw + 20, cy0 + ch - 70 + i * 34, 22, 300, i * 0.9, 140),
                  20, _a(CARD_DECO, 0.95 - i * 0.2), False))
    ax, fy = cx0 + cw - 44, cy0 + 150
    for i, ch_ in enumerate(ALPHABET[:8]):
        y = cy0 + 52 + i * 40
        g = gauss(y - fy, 78)
        s.append(("text", ch_, ax - 50 * g, y + 9, 27 + 12 * g, _a(CARD_INK, 0.55 + 0.45 * g), "light", "c", 0))
    s.append(("clip_end",))
    bx, by = cx0 + 238, cy0 + ch / 2.0
    s.append(("poly", ripple(bx, by, 150, 6, 11, 0.4), BADGE))
    s.append(("poly", ripple(bx, by, 130, 6, 9, 0.4), _a(BADGE_LINE, 0.55)))
    s.append(("poly", ripple(bx, by, 125, 6, 8, 0.4), BADGE))
    wave_bars(s, bx - 4, by, 0.86, ACCENT, 5, 62, 128, 22, 58)
    return s


def hero_scene(w, h, dark=True):
    bg = 0xFF15131B if dark else 0xFFFFE6DF
    deco = 0xFF211D28 if dark else 0xFFFFD0C4
    deco2 = 0xFF2B2532 if dark else 0xFFF6BBAD
    acc = ACCENT if dark else 0xFFD2705A
    s = [("rect", 0, 0, w, h, bg)]
    k = h / 110.0
    for i in range(3):
        s.append(("line", sine(0, w, h * (0.30 + 0.22 * i), 9 * k, 120 * k, i * 1.1, 180), 15 * k,
                  deco2 if i % 2 else deco, False))
    for i in range(7):
        y = h * (0.12 + i * 0.125)
        g = gauss(y - h * 0.5, h * 0.22)
        s.append(("line", [(w - 24 * k - 34 * k * g - 12 * k, y), (w - 24 * k - 34 * k * g + 12 * k + 6 * k * g, y)],
                  4.4 * k, _a(acc, 0.30 + 0.70 * g), True))
    s.append(("circle", w - 22 * k, h * 0.5, 4.4 * k, _a(acc, 0.9)))
    return s


def logo_scene(size=512, with_bg=True):
    S = float(size)
    c = S / 2.0
    k = S / 512.0
    s = []
    s.append(("poly", ripple(c, c, 226 * k, 6, 16 * k, 0.4), BADGE))
    s.append(("poly", ripple(c, c, 200 * k, 6, 13 * k, 0.4), _a(BADGE_LINE, 0.55)))
    s.append(("poly", ripple(c, c, 193 * k, 6, 12 * k, 0.4), BADGE))
    wave_bars(s, c - 8 * k, c, 0.98 * k, ACCENT, 5, 62, 128, 22, 58)
    return s


def glyph_scene(kind, size, color):
    S = float(size)
    k = S / 120.0
    s = []
    if kind == "wave":
        wave_bars(s, S * 0.46, S / 2, 0.52 * k, color, 5, 62, 128, 22, 58, finger=False)
    else:
        wave_bars(s, S * 0.46, S / 2, 0.52 * k, color, 5, 62, 128, 22, 58, finger=True)
    return s


def _signed(c):
    c &= 0xFFFFFFFF
    return c - 0x100000000 if c > 0x7FFFFFFF else c


def render_bitmap(ops, w, h, src_w=None, src_h=None, transparent=True):
    from android.graphics import Bitmap, Canvas, Paint, Path, RectF, Typeface

    w, h = int(w), int(h)
    sw = float(src_w or w)
    sh = float(src_h or h)
    bmp = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
    cv = Canvas(bmp)
    cv.scale(w / sw, h / sh)

    fill = Paint(1)
    fill.setStyle(Paint.Style.FILL)
    stroke = Paint(1)
    stroke.setStyle(Paint.Style.STROKE)

    def _tf(weight):
        try:
            wv = {"light": 300, "regular": 400, "medium": 500, "bold": 700}.get(weight, 400)
            return Typeface.create(Typeface.DEFAULT, wv, False)
        except Exception:
            name = {"light": "sans-serif-light", "medium": "sans-serif-medium"}.get(weight, "sans-serif")
            return Typeface.create(name, Typeface.NORMAL)

    def _path(pts, close=False):
        p = Path()
        first = True
        for x, y in pts:
            if first:
                p.moveTo(float(x), float(y))
                first = False
            else:
                p.lineTo(float(x), float(y))
        if close:
            p.close()
        return p

    def _rr(x, y, rw, rh, r):
        p = Path()
        p.addRoundRect(RectF(float(x), float(y), float(x + rw), float(y + rh)), float(r), float(r), Path.Direction.CW)
        return p

    clips = 0
    for op in ops:
        k = op[0]
        try:
            if k == "rect":
                fill.setColor(_signed(op[5]))
                cv.drawRect(float(op[1]), float(op[2]), float(op[1] + op[3]), float(op[2] + op[4]), fill)
            elif k == "rrect":
                fill.setColor(_signed(op[6]))
                cv.drawRoundRect(RectF(float(op[1]), float(op[2]), float(op[1] + op[3]), float(op[2] + op[4])),
                                 float(op[5]), float(op[5]), fill)
            elif k == "rrect_stroke":
                stroke.setStrokeWidth(float(op[6]))
                stroke.setColor(_signed(op[7]))
                stroke.setStrokeCap(Paint.Cap.BUTT)
                hw = op[6] / 2.0
                cv.drawRoundRect(RectF(float(op[1] + hw), float(op[2] + hw), float(op[1] + op[3] - hw), float(op[2] + op[4] - hw)),
                                 float(op[5] - hw), float(op[5] - hw), stroke)
            elif k == "circle":
                fill.setColor(_signed(op[4]))
                cv.drawCircle(float(op[1]), float(op[2]), float(op[3]), fill)
            elif k == "poly":
                fill.setColor(_signed(op[2]))
                cv.drawPath(_path(op[1], True), fill)
            elif k == "line":
                stroke.setStrokeWidth(float(op[2]))
                stroke.setColor(_signed(op[3]))
                stroke.setStrokeCap(Paint.Cap.ROUND if op[4] else Paint.Cap.BUTT)
                stroke.setStrokeJoin(Paint.Join.ROUND)
                cv.drawPath(_path(op[1], False), stroke)
            elif k == "text":
                _, txt, x, y, size, col, weight, align, spacing = op
                fill.setColor(_signed(col))
                fill.setTextSize(float(size))
                fill.setTypeface(_tf(weight))
                try:
                    fill.setLetterSpacing(float(spacing) / float(size))
                except Exception:
                    pass
                if align == "c":
                    fill.setTextAlign(Paint.Align.CENTER)
                elif align == "r":
                    fill.setTextAlign(Paint.Align.RIGHT)
                else:
                    fill.setTextAlign(Paint.Align.LEFT)
                cv.drawText(str(txt), float(x), float(y), fill)
                fill.setTextAlign(Paint.Align.LEFT)
                try:
                    fill.setLetterSpacing(0.0)
                except Exception:
                    pass
            elif k == "clip_begin":
                cv.save()
                cv.clipPath(_rr(op[1], op[2], op[3], op[4], op[5]))
                clips += 1
            elif k == "clip_end":
                if clips > 0:
                    cv.restore()
                    clips -= 1
        except Exception:
            continue
    while clips > 0:
        cv.restore()
        clips -= 1
    return bmp


def _banner_canvas(w=WIDE_W, h=WIDE_H):
    return render_bitmap(banner_wide_scene(), w, h, WIDE_W, WIDE_H)


def _hero_canvas(w_px, h_px, dark=True):
    k = h_px / 110.0
    lw = w_px / k
    return render_bitmap(hero_scene(lw, 110.0, dark), w_px, h_px, lw, 110.0)


def _logo_canvas(px):
    return render_bitmap(logo_scene(512), px, px, 512, 512)


def _glyph_canvas(kind, px, color):
    return render_bitmap(glyph_scene(kind, 120, color), px, px, 120, 120)


def save_png(bitmap, path):
    from android.graphics import Bitmap
    from java.io import FileOutputStream
    fos = FileOutputStream(str(path))
    try:
        bitmap.compress(Bitmap.CompressFormat.PNG, 100, fos)
        fos.flush()
    finally:
        fos.close()
    return str(path)


FINDER = None


def _asset_file(name):
    cands = []
    finders = [FINDER]
    try:
        pass
    except Exception:
        pass
    for fn in finders:
        try:
            if fn is not None:
                cands.append(fn("res/ui/" + name))
        except Exception:
            pass
    try:
        if __file__:
            base = os.path.dirname(os.path.abspath(__file__))
            cands.append(os.path.join(base, "..", "..", "res", "ui", name))
    except Exception:
        pass
    for c in cands:
        try:
            if c and os.path.exists(c):
                return c
        except Exception:
            pass
    return None


def asset_bitmap(name):
    path = _asset_file(name)
    if not path:
        return None
    try:
        from android.graphics import BitmapFactory
        return BitmapFactory.decodeFile(str(path))
    except Exception:
        return None


def banner_bitmap(w=WIDE_W, h=WIDE_H):
    return asset_bitmap("banner.png") or _banner_canvas(w, h)


def hero_bitmap(w_px, h_px, dark=True):
    return asset_bitmap("hero_dark.png" if dark else "hero_light.png") or _hero_canvas(w_px, h_px, dark)


def logo_bitmap(px):
    return asset_bitmap("logo.png") or _logo_canvas(px)


def glyph_bitmap(kind, px, color):
    return asset_bitmap("glyph_%s.png" % kind) or _glyph_canvas(kind, px, color)
