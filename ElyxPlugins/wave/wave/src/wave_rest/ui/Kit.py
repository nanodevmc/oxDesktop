try:
    __file__
except NameError:
    try:
        __file__ = file
    except NameError:
        __file__ = ""

from android.view import Gravity, View
from android.widget import FrameLayout, ImageView, LinearLayout, TextView
from android.graphics import PorterDuff, PorterDuffColorFilter, Typeface
from android.graphics.drawable import GradientDrawable
from java import dynamic_proxy, jclass
from org.telegram.ui.ActionBar import BottomSheet, Theme
from org.telegram.messenger import AndroidUtilities
from android_utils import log, run_on_ui_thread, OnClickListener
try:
    from wave_addons.Diag import log
except Exception:
    pass

try:
    from java import jarray, jint
except Exception:
    jarray = jint = None

try:
    from wave_addons import Alpha as A
except Exception:
    from ...wave_addons import Alpha as A

ACC_D, ACC_L = 0xFFFFB8A6, 0xFFC2553B


class OnDismiss(dynamic_proxy(jclass("android.content.DialogInterface$OnDismissListener"))):
    def __init__(self, fn):
        super(OnDismiss, self).__init__()
        self.fn = fn

    def onDismiss(self, d):
        try:
            self.fn()
        except Exception:
            pass


class S3:

    def __init__(self, kit, ctx, lo, hi, step, value, on_change, colors=None, fill=True):
        self.kit = kit
        self.lo, self.hi, self.step = int(lo), int(hi), max(1, int(step))
        self.value = max(self.lo, min(self.hi, int(value)))
        self.on_change = on_change
        p = kit._pal()
        dp = kit._dp
        self.pad = dp(10)
        self.view = FrameLayout(ctx)
        self.track = View(ctx)
        self.view.addView(self.track, FrameLayout.LayoutParams(-1, dp(16), Gravity.CENTER_VERTICAL))
        self.track.setBackground(kit._rr(p["track"], 8))
        self.active = None
        self.colored = bool(colors)
        if fill and not colors:
            self.active = View(ctx)
            self.active.setBackground(kit._rr(p["acc"], 8))
            self.view.addView(self.active, FrameLayout.LayoutParams(dp(16), dp(16), Gravity.CENTER_VERTICAL))
        if colors:
            self.set_track(colors)
        self.hw = dp(6) if colors else dp(4)
        self.handle = View(ctx)
        if colors:
            self.handle.setBackground(kit._rr(0xFFFFFFFF, 3, 0xFF202020, 1.2))
        else:
            self.handle.setBackground(kit._rr(p["acc"], 2))
        self.view.addView(self.handle, FrameLayout.LayoutParams(self.hw, dp(40), Gravity.LEFT | Gravity.CENTER_VERTICAL))
        outer = self

        class _Touch(dynamic_proxy(jclass("android.view.View$OnTouchListener"))):
            def onTouch(self_i, v, e):
                try:
                    return outer._touch(e)
                except Exception as ex:
                    log("[Wave] slider touch: {0}".format(ex))
                    return False
        self.view.setOnTouchListener(_Touch())

        class _Lay(dynamic_proxy(jclass("android.view.View$OnLayoutChangeListener"))):
            def onLayoutChange(self_i, v, l, t, r, b, ol, ot, orr, ob):
                try:
                    if (r - l) != (orr - ol):
                        outer._place()
                except Exception:
                    pass
        self._lay = _Lay()
        self.view.addOnLayoutChangeListener(self._lay)

    def set_track(self, colors):
        try:
            d = GradientDrawable()
            d.setOrientation(GradientDrawable.Orientation.LEFT_RIGHT)
            d.setColors(self.kit._ints([self.kit._c(c) for c in colors]))
            d.setCornerRadius(float(self.kit._dp(8)))
            self.track.setBackground(d)
        except Exception:
            pass

    def _span(self):
        w = int(self.view.getWidth())
        return self.pad, max(self.pad + 1, w - self.pad)

    def _place(self):
        x0, x1 = self._span()
        frac = 0.0 if self.hi == self.lo else (self.value - self.lo) / float(self.hi - self.lo)
        cx = x0 + frac * (x1 - x0)
        self.handle.setTranslationX(float(cx - self.hw / 2.0))
        if self.active is not None:
            lp = self.active.getLayoutParams()
            lp.width = max(self.kit._dp(16), int(cx - self.kit._dp(5)))
            self.active.setLayoutParams(lp)

    def set(self, v):
        self.value = max(self.lo, min(self.hi, int(v)))
        self._place()

    def _touch(self, e):
        act = int(e.getActionMasked())
        if act == 0:
            try:
                self.view.getParent().requestDisallowInterceptTouchEvent(True)
            except Exception:
                pass
            try:
                self.view.performHapticFeedback(1)
            except Exception:
                pass
            self.handle.animate().scaleX(1.5).setDuration(100).start()
        if act in (0, 2):
            x0, x1 = self._span()
            frac = max(0.0, min(1.0, (float(e.getX()) - x0) / float(x1 - x0)))
            raw = self.lo + frac * (self.hi - self.lo)
            v = self.lo + int(round((raw - self.lo) / self.step)) * self.step
            v = max(self.lo, min(self.hi, v))
            if v != self.value:
                self.value = v
                self._place()
                self.on_change(v, False)
            return True
        if act in (1, 3):
            self.handle.animate().scaleX(1.0).setDuration(120).start()
            self.on_change(self.value, True)
            return True
        return False


class WaveKit:
    def _ints(self, lst):
        try:
            return jarray(jint)([int(x) for x in lst])
        except Exception:
            return [int(x) for x in lst]

    def _pal(self):
        dark = self._is_dark_theme()
        base = self._theme_color(Theme.key_windowBackgroundWhite, 0xFF1D2733 if dark else 0xFFFFFFFF) & 0xFFFFFF
        acc = ACC_D if dark else ACC_L
        text = self._theme_color(Theme.key_windowBackgroundWhiteBlackText, 0xFFFFFFFF if dark else 0xFF1D1F24)
        mx = self._mix_rgb
        return {
            "dark": dark, "base": 0xFF000000 | base, "acc": acc,
            "ink": 0xFF3A1208 if A.luminance(acc) > 150 else 0xFFFFFFFF,
            "container": mx(base, acc, 0.07 if dark else 0.06),
            "sel": mx(base, acc, 0.26 if dark else 0.20),
            "track": mx(base, acc, 0.22 if dark else 0.20),
            "outline": mx(base, text & 0xFFFFFF, 0.42),
            "line": mx(base, text & 0xFFFFFF, 0.12),
            "text": text,
            "sub": self._theme_color(Theme.key_windowBackgroundWhiteGrayText, 0xFF9AA4B2),
        }

    def _rr(self, color, radius=12, stroke=None, sw=1.0, oval=False):
        d = GradientDrawable()
        d.setColor(self._c(color))
        if oval:
            d.setShape(GradientDrawable.OVAL)
        else:
            d.setCornerRadius(float(self._dp(radius)))
        if stroke is not None:
            d.setStroke(max(1, int(self._dp(sw))), self._c(stroke))
        return d

    def _tv(self, ctx, text, sp, color, medium=False, wrap=True):
        tv = TextView(ctx)
        tv.setText(str(text))
        tv.setTextSize(1, float(sp))
        tv.setTextColor(self._c(color))
        if medium:
            try:
                tv.setTypeface(AndroidUtilities.getTypeface("fonts/rmedium.ttf"))
            except Exception:
                tv.setTypeface(Typeface.create("sans-serif-medium", 0))
        if wrap:
            tv.setSingleLine(False)
            tv.setMaxLines(6)
        return tv

    def _lp(self, w=-1, h=-2, top=0, bottom=0, left=0, right=0, weight=None, gravity=None):
        lp = LinearLayout.LayoutParams(w, h) if weight is None else LinearLayout.LayoutParams(w, h, float(weight))
        lp.setMargins(self._dp(left), self._dp(top), self._dp(right), self._dp(bottom))
        if gravity is not None:
            lp.gravity = gravity
        return lp

    def _sec(self, ctx, parent, title):
        p = self._pal()
        if title:
            parent.addView(self._tv(ctx, title, 13, p["acc"], True, wrap=False), self._lp(top=14, bottom=6, left=16))
        g = LinearLayout(ctx)
        g.setOrientation(LinearLayout.VERTICAL)
        g.setBackground(self._rr(p["container"], 24))
        try:
            g.setClipToOutline(True)
        except Exception:
            pass
        parent.addView(g, self._lp(top=0 if title else 10))
        return g

    def _icon_chip(self, ctx, icon):
        p = self._pal()
        box = FrameLayout(ctx)
        box.setBackground(self._rr(p["sel"], 20, oval=True))
        iv = ImageView(ctx)
        rid = self._telegram_drawable_id(icon) if icon else 0
        if rid:
            iv.setImageResource(rid)
            iv.setColorFilter(PorterDuffColorFilter(self._c(p["acc"]), PorterDuff.Mode.SRC_IN))
        box.addView(iv, FrameLayout.LayoutParams(self._dp(20), self._dp(20), Gravity.CENTER))
        return box

    def _row(self, ctx, group, title, sub=None, icon=None, trailing=None, on_click=None, leading=None):
        p = self._pal()
        if int(group.getChildCount()) > 0:
            line = View(ctx)
            line.setBackgroundColor(self._c(p["line"]))
            group.addView(line, self._lp(-1, 1, left=72 if (icon or leading is not None) else 16))
        row = LinearLayout(ctx)
        row.setGravity(Gravity.CENTER_VERTICAL)
        row.setMinimumHeight(self._dp(60))
        row.setPadding(self._dp(16), self._dp(9), self._dp(16), self._dp(9))
        try:
            row.setBackground(Theme.getSelectorDrawable(False))
        except Exception:
            pass
        lead = leading if leading is not None else (self._icon_chip(ctx, icon) if icon else None)
        if lead is not None:
            row.addView(lead, self._lp(self._dp(40), self._dp(40), right=14))
        col = LinearLayout(ctx)
        col.setOrientation(LinearLayout.VERTICAL)
        col.addView(self._tv(ctx, title, 16, p["text"]))
        subtv = None
        if sub:
            subtv = self._tv(ctx, sub, 13, p["sub"])
            col.addView(subtv, self._lp(top=1))
        row.addView(col, LinearLayout.LayoutParams(0, -2, 1.0))
        if trailing is not None:
            row.addView(trailing, self._lp(-2, -2, left=12))
        if on_click is not None:
            row.setOnClickListener(OnClickListener(lambda v: on_click(v)))
        group.addView(row, self._lp())
        return row, subtv

    def _button(self, ctx, text, on_click, kind="tonal", h=44):
        p = self._pal()
        tv = TextView(ctx)
        tv.setText(str(text))
        tv.setTextSize(1, 14.5)
        tv.setGravity(Gravity.CENTER)
        tv.setSingleLine(False)
        tv.setPadding(self._dp(18), 0, self._dp(18), 0)
        tv.setMinimumHeight(self._dp(h))
        try:
            tv.setTypeface(AndroidUtilities.getTypeface("fonts/rmedium.ttf"))
        except Exception:
            pass
        if kind == "filled":
            tv.setTextColor(self._c(p["ink"]))
            tv.setBackground(self._rr(p["acc"], 22))
        elif kind == "danger":
            tv.setTextColor(self._c(0xFFFF6B6B))
            tv.setBackground(self._rr(self._mix_rgb(p["base"], 0xFF6B6B, 0.14), 22))
        elif kind == "text":
            tv.setTextColor(self._c(p["acc"]))
        else:
            tv.setTextColor(self._c(p["text"]))
            tv.setBackground(self._rr(p["sel"], 22))
        tv.setOnClickListener(OnClickListener(lambda v: on_click(v)))
        return tv

    def _switch(self, ctx, checked, on_toggle):
        p = self._pal()
        dp = self._dp
        W, H = dp(52), dp(32)
        sw = FrameLayout(ctx)
        track = View(ctx)
        sw.addView(track, FrameLayout.LayoutParams(W, H, Gravity.CENTER))
        thumb = View(ctx)
        sw.addView(thumb, FrameLayout.LayoutParams(dp(24), dp(24), Gravity.LEFT | Gravity.CENTER_VERTICAL))
        state = {"on": bool(checked)}
        left, right = dp(4), W - dp(24) - dp(4)

        def paint(anim):
            on = state["on"]
            if on:
                track.setBackground(self._rr(p["acc"], 16))
                thumb.setBackground(self._rr(p["ink"], 12, oval=True))
            else:
                track.setBackground(self._rr(p["track"], 16, p["outline"], 2.0))
                thumb.setBackground(self._rr(p["outline"], 12, oval=True))
            tx = float(right if on else left)
            sc = 1.0 if on else 0.66
            if anim:
                thumb.animate().translationX(tx).scaleX(sc).scaleY(sc).setDuration(170).start()
            else:
                thumb.setTranslationX(tx)
                thumb.setScaleX(sc)
                thumb.setScaleY(sc)
        paint(False)

        def tap(v):
            state["on"] = not state["on"]
            paint(True)
            try:
                v.performHapticFeedback(1)
            except Exception:
                pass
            on_toggle(state["on"])
        sw.setOnClickListener(OnClickListener(tap))
        return sw, tap

    def _slider(self, ctx, lo, hi, step, value, on_change, colors=None, fill=True):
        return S3(self, ctx, lo, hi, step, value, on_change, colors, fill)

    def _segmented(self, ctx, labels, current, on_pick):
        p = self._pal()
        bar = LinearLayout(ctx)
        bar.setGravity(Gravity.CENTER_VERTICAL)
        bar.setPadding(self._dp(3), self._dp(3), self._dp(3), self._dp(3))
        bar.setBackground(self._rr(p["base"], 22, p["outline"], 1.0))
        cells = []

        def paint(cur):
            for i, tv in enumerate(cells):
                tv.setText(("✓ " if i == cur else "") + str(labels[i]))
                if i == cur:
                    tv.setTextColor(self._c(p["text"]))
                    tv.setBackground(self._rr(p["sel"], 19))
                else:
                    tv.setTextColor(self._c(p["sub"]))
                    tv.setBackground(None)
        for i, label in enumerate(labels):
            tv = TextView(ctx)
            tv.setTextSize(1, 14.0)
            tv.setGravity(Gravity.CENTER)
            tv.setSingleLine(False)
            tv.setPadding(self._dp(6), self._dp(9), self._dp(6), self._dp(9))
            try:
                tv.setTypeface(AndroidUtilities.getTypeface("fonts/rmedium.ttf"))
            except Exception:
                pass

            def pick(v, k=i):
                paint(k)
                try:
                    v.performHapticFeedback(1)
                except Exception:
                    pass
                on_pick(k)
            tv.setOnClickListener(OnClickListener(pick))
            bar.addView(tv, LinearLayout.LayoutParams(0, -2, 1.0))
            cells.append(tv)
        paint(int(current))
        return bar

    def _chips(self, ctx, labels, current, on_pick, per_row=3, typefaces=None):
        p = self._pal()
        grid = LinearLayout(ctx)
        grid.setOrientation(LinearLayout.VERTICAL)
        cells = []

        def paint(cur):
            for i, tv in enumerate(cells):
                if i == cur:
                    tv.setTextColor(self._c(p["text"]))
                    tv.setBackground(self._rr(p["sel"], 12))
                else:
                    tv.setTextColor(self._c(p["sub"]))
                    tv.setBackground(self._rr(p["base"], 12, p["outline"], 1.0))
        row = None
        for i, label in enumerate(labels):
            if i % per_row == 0:
                row = LinearLayout(ctx)
                grid.addView(row, self._lp(top=0 if i == 0 else 8))
            tv = TextView(ctx)
            tv.setText(str(label))
            tv.setTextSize(1, 14.5)
            tv.setGravity(Gravity.CENTER)
            tv.setSingleLine(False)
            tv.setPadding(self._dp(6), self._dp(10), self._dp(6), self._dp(10))
            if typefaces is not None and i < len(typefaces) and typefaces[i] is not None:
                tv.setTypeface(typefaces[i])

            def pick(v, k=i):
                paint(k)
                try:
                    v.performHapticFeedback(1)
                except Exception:
                    pass
                on_pick(k)
            tv.setOnClickListener(OnClickListener(pick))
            row.addView(tv, self._lp(0, -2, right=8 if (i % per_row) != per_row - 1 else 0, weight=1.0))
            cells.append(tv)
        for _ in range((-len(labels)) % per_row):
            row.addView(View(ctx), self._lp(0, 1, weight=1.0))
        paint(int(current))
        return grid

    def _paint_swatch(self, v, rgb, size=34, ring=False):
        p = self._pal()
        v.setBackground(self._rr(rgb, size // 2, p["text"] if ring else p["line"], 2.4 if ring else 1.0, oval=True))

    def _sheet(self, ctx, title, build, on_dismiss=None, sub=None):
        try:
            p = self._pal()
            sheet = BottomSheet(ctx, True)
            root = LinearLayout(ctx)
            root.setOrientation(LinearLayout.VERTICAL)
            root.setPadding(self._dp(20), self._dp(10), self._dp(20), self._dp(20))
            handle = View(ctx)
            handle.setBackground(self._rr(p["line"], 2))
            root.addView(handle, self._lp(self._dp(32), self._dp(4), bottom=14, gravity=Gravity.CENTER_HORIZONTAL))
            if title:
                root.addView(self._tv(ctx, title, 20, p["text"], True))
            if sub:
                root.addView(self._tv(ctx, sub, 13, p["sub"]), self._lp(top=2))
            content = LinearLayout(ctx)
            content.setOrientation(LinearLayout.VERTICAL)
            root.addView(content, self._lp(top=14))
            build(content, lambda: sheet.dismiss())
            sheet.setCustomView(root)
            if on_dismiss is not None:
                try:
                    sheet.setOnDismissListener(OnDismiss(on_dismiss))
                except Exception:
                    pass
            sheet.show()
            return sheet
        except Exception as e:
            log("[Wave] sheet: {0}".format(e))
            return None
