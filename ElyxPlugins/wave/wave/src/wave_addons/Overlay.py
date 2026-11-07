import math
import time

try:
    __file__
except NameError:
    try:
        __file__ = file
    except NameError:
        __file__ = ""

from java import dynamic_proxy, jclass
from android.view import Gravity, View
from android.widget import FrameLayout, LinearLayout, TextView
from android.graphics import Typeface
from android.graphics.drawable import GradientDrawable
from android_utils import log, run_on_ui_thread
try:
    from wave_addons.Diag import log
except Exception:
    try:
        from .Diag import log
    except Exception:
        pass
from org.telegram.ui.ActionBar import Theme

try:
    from wave_addons import Haptics, ListFilter as LF, Alpha as A
except Exception:
    from . import Haptics, ListFilter as LF, Alpha as A


def parse_hex(s, default=None):
    s = str(s or "").strip().lstrip("#")
    try:
        if len(s) == 6:
            return 0xFF000000 | int(s, 16)
        if len(s) == 8:
            return int(s, 16)
    except Exception:
        pass
    return default


def _touch_cls():
    return dynamic_proxy(jclass("android.view.View$OnTouchListener"))


def _frame_cls():
    return dynamic_proxy(jclass("android.view.Choreographer$FrameCallback"))


def _layout_cls():
    return dynamic_proxy(jclass("android.view.View$OnLayoutChangeListener"))


class _Letter:
    __slots__ = ("tv", "ch", "key", "y", "x", "vx", "s", "vs", "a", "va", "tx", "ts", "ta", "sx", "ss", "sa")

    def __init__(self, tv, ch, a0, key=None):
        self.tv, self.ch = tv, ch
        self.key = key if key is not None else ch
        self.y = 0.0
        self.x = self.vx = 0.0
        self.s, self.vs = 1.0, 0.0
        self.a, self.va = a0, 0.0
        self.tx, self.ts, self.ta = 0.0, 1.0, a0
        self.sx, self.ss, self.sa = 0.0, 1.0, a0


class WaveOverlay:
    def __init__(self, plugin, frag, content):
        self.plugin = plugin
        self.flt = plugin._filter if frag is not None else None
        self._tries = 0
        self.frag = frag
        self.content = content
        self.ctx = content.getContext()
        self.root = None
        self.strip = None
        self.badge = None
        self.cap = None
        self.cap_letter = None
        self.cap_x = None
        self.bubble = None
        self._want = None
        self._tok = 0
        self.t0 = 0.0
        self.letters = []
        self.signature = None
        self.touching = False
        self.fy = 0.0
        self.active = -1
        self.start = 0.0
        self.step = 1.0
        self.last_frame = 0
        self.running = False
        self.zeta_on = 0.55
        self.zeta_off = 0.38
        self.zeta = self.zeta_on
        self._frame_cb = None
        self._layout_cb = None
        self._item_listeners = []
        self._alpha_cache = (0, [])
        self._attached = False
        self._last_geo = None

    def _root_w(self):
        p = self.plugin
        return p._dp(max(16, p.cfg_int("wave_zone", 32))) + p._dp(p.cfg_int("wave_amp", 56)) + p._dp(44)

    def attach(self):
        p = self.plugin
        self.root = FrameLayout(self.ctx)
        self.root.setClipChildren(False)
        self.root.setClipToPadding(False)
        self.strip = FrameLayout(self.ctx)
        self.strip.setClipChildren(False)
        zone0 = p._dp(max(16, p.cfg_int("wave_zone", 32)))
        sgrav = Gravity.LEFT if p.cfg_int("wave_side", 0) == 1 else Gravity.RIGHT
        self.root.addView(self.strip, FrameLayout.LayoutParams(zone0, -1, sgrav))

        outer = self

        class _Touch(_touch_cls()):
            def onTouch(self_i, v, e):
                try:
                    return outer.on_touch(e)
                except Exception as ex:
                    log("[Wave] touch: {0}".format(ex))
                    return False
        self.strip.setOnTouchListener(_Touch())

        self.content.addView(self.root, FrameLayout.LayoutParams(self._root_w(), -1, sgrav))
        if self.frag is not None:
            self._build_capsule()
        self._attached = True
        self._build_bubble()

        class _Lay(_layout_cls()):
            def onLayoutChange(self_i, v, l, t, r, b, ol, ot, orr, ob):
                try:
                    if (r - l, b - t) != (orr - ol, ob - ot):
                        outer.relayout()
                except Exception as ex:
                    log("[Wave] layout: {0}".format(ex))
        self._layout_cb = _Lay()
        self.content.addOnLayoutChangeListener(self._layout_cb)
        if self.frag is not None:
            self.attach_lists()
        run_on_ui_thread(self.rebuild, 30)

    def _build_capsule(self):
        p = self.plugin
        cap = LinearLayout(self.ctx)
        cap.setOrientation(LinearLayout.HORIZONTAL)
        cap.setGravity(Gravity.CENTER_VERTICAL)
        cap.setAlpha(0.0)
        cap.setVisibility(View.GONE)
        try:
            cap.setElevation(float(p._dp(5)))
        except Exception:
            pass
        letter = TextView(self.ctx)
        letter.setGravity(Gravity.CENTER)
        letter.setTextSize(2, 16.0)
        letter.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL))
        letter.setIncludeFontPadding(False)
        letter.setPadding(p._dp(14), 0, p._dp(6), 0)
        cap.addView(letter, LinearLayout.LayoutParams(-2, -1))
        xv = TextView(self.ctx)
        xv.setText("\u2715")
        xv.setGravity(Gravity.CENTER)
        xv.setTextSize(2, 13.0)
        xv.setIncludeFontPadding(False)
        xv.setPadding(p._dp(8), 0, p._dp(13), 0)
        xv.setClickable(True)
        xv.setOnClickListener(p._click(lambda v: self.reset_filter()))
        cap.addView(xv, LinearLayout.LayoutParams(-2, -1))
        self.cap, self.cap_letter, self.cap_x = cap, letter, xv
        self.content.addView(cap, FrameLayout.LayoutParams(-2, p._dp(36), Gravity.LEFT | Gravity.TOP))

    def _build_bubble(self):
        p = self.plugin
        tv = TextView(self.ctx)
        tv.setGravity(Gravity.CENTER)
        tv.setTextSize(2, 28.0)
        tv.setIncludeFontPadding(False)
        tv.setTypeface(Typeface.create("sans-serif-medium", Typeface.BOLD))
        tv.setAlpha(0.0)
        tv.setVisibility(View.GONE)
        try:
            tv.setElevation(float(p._dp(8)))
        except Exception:
            pass
        self.bubble = tv
        self.content.addView(tv, FrameLayout.LayoutParams(p._dp(60), p._dp(60), Gravity.RIGHT | Gravity.TOP))

    def _bubble_show(self, text):
        b = self.bubble
        if b is None:
            return
        p = self.plugin
        left = p.cfg_int("wave_side", 0) == 1
        lp = b.getLayoutParams()
        off = p._dp(max(16, p.cfg_int("wave_zone", 32)) + p.cfg_int("wave_amp", 56) + 14)
        lp.gravity = (Gravity.LEFT if left else Gravity.RIGHT) | Gravity.TOP
        lp.leftMargin = off if left else 0
        lp.rightMargin = 0 if left else off
        b.setLayoutParams(lp)
        col = self._active_color()
        d = GradientDrawable()
        d.setCornerRadius(float(p._dp(22)))
        d.setColor(col)
        b.setBackground(d)
        lum = ((col >> 16) & 255) * 0.299 + ((col >> 8) & 255) * 0.587 + (col & 255) * 0.114
        b.setTextColor(p._c(0xFF101014) if lum > 140 else p._c(0xFFFFFFFF))
        b.setText(str(text))
        self._bubble_move()
        if b.getVisibility() != View.VISIBLE:
            b.setVisibility(View.VISIBLE)
            b.setScaleX(0.7)
            b.setScaleY(0.7)
        b.animate().cancel()
        b.animate().alpha(1.0).scaleX(1.0).scaleY(1.0).setDuration(90).start()

    def _bubble_move(self):
        b = self.bubble
        if b is None:
            return
        y = float(self.root.getTop()) + self.fy - float(self.plugin._dp(30))
        b.setTranslationY(max(0.0, y))

    def _bubble_hide(self):
        b = self.bubble
        if b is None or b.getVisibility() != View.VISIBLE:
            return
        b.animate().cancel()
        b.animate().alpha(0.0).scaleX(0.8).scaleY(0.8).setDuration(120).start()

        def gone():
            if not self.touching:
                b.setVisibility(View.GONE)
        run_on_ui_thread(gone, 140)

    def _filtered(self, L):
        return self.flt is not None and self.flt.letter is not None and self.flt.letter == L.key

    def attach_lists(self):
        pages = self.plugin._field(self.frag, "viewPages")
        if pages is None:
            return
        for page in pages:
            if page is None:
                continue
            lv = self.plugin._field(page, "listView")
            if lv is None or any(x[0] == lv for x in self._item_listeners):
                continue
            try:
                l = LF.make_item_touch(self)
                lv.addOnItemTouchListener(l)
                self._item_listeners.append((lv, l))
            except Exception as e:
                log("[Wave] item touch: {0}".format(e))

    def detach(self):
        self._attached = False
        self.running = False
        for lv, l in self._item_listeners:
            try:
                lv.removeOnItemTouchListener(l)
            except Exception:
                pass
        self._item_listeners = []
        try:
            if self._layout_cb is not None:
                self.content.removeOnLayoutChangeListener(self._layout_cb)
            if self.root is not None and self.root.getParent() is not None:
                self.content.removeView(self.root)
            if self.cap is not None and self.cap.getParent() is not None:
                self.content.removeView(self.cap)
            if self.bubble is not None and self.bubble.getParent() is not None:
                self.content.removeView(self.bubble)
        except Exception:
            pass

    def _base_color(self):
        p = self.plugin
        mode = p.cfg_int("wave_color_mode", 0)
        if mode == 2:
            c = parse_hex(p.get_setting("wave_color_hex", ""), None)
            if c is not None:
                return p._c(c)
        key = Theme.key_windowBackgroundWhiteBlueText if mode == 1 else Theme.key_windowBackgroundWhiteBlackText
        return p._theme_color(key, 0xFF8AB4F8 if mode == 1 else 0xFFFFFFFF)

    def _active_color(self):
        p = self.plugin
        c = parse_hex(p.get_setting("wave_active_hex", ""), None)
        if c is not None:
            return p._c(c)
        return p._theme_color(Theme.key_windowBackgroundWhiteBlueText, 0xFF8AB4F8)

    def _typeface(self):
        p = self.plugin
        f = p.cfg_int("wave_font", 2)
        if f == A.FONT_CUSTOM:
            tf = p._custom_typeface()
            if tf is not None:
                return tf
            f = 2
        if not (0 <= f < len(A.FONTS)):
            f = 2
        _, family, style = A.FONTS[f]
        return Typeface.create(family, style)

    def _alphabet(self):
        p = self.plugin
        return A.build_items(p._alpha_lang(), p.cfg_bool("wave_alpha_hash", True), p.cfg_int("wave_hash_pos", 0),
                             p._pins(), p.cfg_int("wave_alpha_case", 0) == 1)

    def _label_for(self, key):
        for L in self.letters:
            if L.key == key:
                return L.ch
        return key if not str(key).startswith(A.PIN_PREFIX) else ""

    def rebuild(self):
        try:
            self._rebuild()
        except Exception as ex:
            log("[Wave] rebuild: {0}".format(ex))

    def _rebuild(self):
        if not self._attached:
            return
        p = self.plugin
        H = int(self.strip.getHeight())
        if H <= 0:
            self._tries += 1
            if self._tries < 25:
                run_on_ui_thread(self.rebuild, 60)
            return
        letters = self._alphabet()
        try:
            from . import Diag
            Diag.state("strip_h_px", H)
            Diag.state("letters", len(letters))
        except Exception:
            pass
        if not letters:
            return
        size = p.cfg_int("wave_size", 15)
        gap = p.cfg_int("wave_gap", 0)
        pad = p._dp(max(0, p.cfg_int("wave_pad", 10)))
        align = p.cfg_int("wave_align", 0)
        avail = float(H - 2 * pad)
        if avail < p._dp(20):
            avail = float(H)
            pad = 0
        cell = float(p._dp(size * 1.9)) + float(p._dp(1)) * gap
        if cell < 4.0:
            cell = 4.0
        eff = float(size)
        _n = max(1, len(letters))
        _step_dp = (avail / float(_n)) / float(p._dp(1))
        if _step_dp < size * 1.9:
            eff = max(6.0, min(float(size), _step_dp / 1.3))
        sig = (tuple(letters), size, gap, pad, align, round(eff, 1), p.cfg_int("wave_font", 2), p.get_setting("wave_font_file", ""),
               p.cfg_int("wave_color_mode", 0), p.get_setting("wave_color_hex", ""), p.cfg_int("wave_idle", 0),
               p.cfg_int("wave_zone", 32), p.cfg_int("wave_side", 0), H, p.cfg_bool("wave_shadow", False),
               p.cfg_bool("wave_letters3d", False), p.cfg_int("wave_amp", 56))
        if sig == self.signature:
            return
        self.signature = sig
        self.strip.removeAllViews()
        self.letters = []
        zone = p._dp(p.cfg_int("wave_zone", 32))
        side_g = Gravity.LEFT if p.cfg_int("wave_side", 0) == 1 else Gravity.RIGHT
        lp = self.strip.getLayoutParams()
        lp.width = zone
        lp.gravity = side_g
        self.strip.setLayoutParams(lp)
        rlp = self.root.getLayoutParams()
        rlp.width = self._root_w()
        rlp.gravity = side_g
        self.root.setLayoutParams(rlp)
        n = len(letters)
        self.step = max(1.0, min(cell, avail / float(n)))
        total = self.step * n
        if align == 1:
            self.start = float(pad)
        elif align == 2:
            self.start = float(H - pad) - total
        else:
            self.start = (H - total) / 2.0
        idle = p.cfg_int("wave_idle", 0) / 100.0
        tf = self._typeface()
        base = self._base_color()
        for i, (ch, key) in enumerate(letters):
            tv = TextView(self.ctx)
            tv.setText(ch)
            tv.setTextSize(2, float(eff))
            tv.setTypeface(tf)
            tv.setTextColor(base)
            tv.setGravity(Gravity.CENTER)
            tv.setIncludeFontPadding(False)
            if p.cfg_bool("wave_letters3d", False):
                tv.setShadowLayer(float(p._dp(2)), 0.0, float(p._dp(1.6)), p._c(0xAA000000))
            elif p.cfg_bool("wave_shadow", False):
                tv.setShadowLayer(float(p._dp(3)), 0.0, 0.0, base)
            tv.setAlpha(idle)
            flp = FrameLayout.LayoutParams(zone, int(self.step), Gravity.TOP)
            flp.topMargin = int(self.start + i * self.step)
            self.strip.addView(tv, flp)
            L = _Letter(tv, ch, idle, key)
            if self._filtered(L):
                tv.setTextColor(self._active_color())
                tv.setAlpha(1.0)
                L.a = L.ta = L.sa = 1.0
            L.y = self.start + (i + 0.5) * self.step
            self.letters.append(L)
        self.active = -1
        self.relayout()

    def relayout(self):
        if not self._attached or self.frag is None:
            return
        p = self.plugin
        try:
            top = 0
            bottom_edge = int(self.content.getHeight())
            page = self.flt._page(self.frag)
            if page is not None:
                top = max(top, int(page.getTop()))
            ab = self.frag.getActionBar()
            if ab is not None:
                top = max(top, int(ab.getBottom()))
            tabs = p._field(self.frag, "filterTabsView")
            if tabs is not None and int(tabs.getVisibility()) == 0:
                top = max(top, int(tabs.getBottom()))
            if p.cfg_bool("wave_auto_inset", True):
                t_m, b_m = top + p._dp(6), p._dp(96)
            else:
                t_m, b_m = p._dp(p.cfg_int("wave_inset_top", 120)), p._dp(p.cfg_int("wave_inset_bottom", 96))
            geo = (t_m, b_m)
            if geo == self._last_geo:
                return
            self._last_geo = geo
            side = Gravity.LEFT if p.cfg_int("wave_side", 0) == 1 else Gravity.RIGHT
            lp = self.root.getLayoutParams()
            lp.width = self._root_w()
            lp.topMargin, lp.bottomMargin, lp.gravity = t_m, b_m, side
            self.root.setLayoutParams(lp)
            if self.cap is not None:
                cside = Gravity.RIGHT if side == Gravity.LEFT else Gravity.LEFT
                clp = self.cap.getLayoutParams()
                clp.gravity = cside | Gravity.TOP
                clp.topMargin = top + p._dp(14)
                clp.leftMargin = clp.rightMargin = p._dp(14)
                self.cap.setLayoutParams(clp)
            self.signature = None
            run_on_ui_thread(self.rebuild, 20)
        except Exception as e:
            log("[Wave] relayout: {0}".format(e))

    def apply_settings(self):
        self.signature = None
        self._last_geo = None
        self._alpha_cache = (0, [])
        if self.frag is None:
            run_on_ui_thread(self.rebuild, 10)
        else:
            self.relayout()

    def _index(self, y):
        if not self.letters:
            return -1
        i = int((y - self.start) // self.step)
        return max(0, min(len(self.letters) - 1, i))

    def flash(self):
        try:
            self.rebuild()
            for L in self.letters:
                L.tv.setAlpha(1.0)
                L.sa = 1.0
                L.a = L.ta = 1.0

            def back():
                for L in self.letters:
                    L.a = L.ta = L.sa = p_idle = self.plugin.cfg_int("wave_idle", 0) / 100.0
                    L.tv.setAlpha(float(p_idle))
            run_on_ui_thread(back, 3000)
        except Exception as ex:
            log("[Wave] flash: {0}".format(ex))

    def on_touch(self, e):
        try:
            from . import Diag
            Diag.bump("touch_events")
        except Exception:
            pass
        act = int(e.getActionMasked())
        p = self.plugin
        if act == 0:
            try:
                self.strip.getParent().requestDisallowInterceptTouchEvent(True)
            except Exception:
                pass
            self.rebuild()
            if not self.letters:
                return False
            self.touching = True
            self.t0 = time.time()
            self._want = None
            self.zeta = self.zeta_on = max(0.15, p.cfg_int("wave_damping", 55) / 100.0)
            self.fy = float(e.getY())
            self._set_active(self._index(self.fy), True)
            self._kick()
            return True
        if act == 2 and self.touching:
            self.fy = float(e.getY())
            self._set_active(self._index(self.fy), False)
            self._bubble_move()
            self._kick()
            return True
        if act in (1, 3) and self.touching:
            self.touching = False
            self._tok += 1
            if self._want is not None and self.frag is not None and p.cfg_bool("wave_filter", True):
                self.flt.request(self.frag, self._want)
            self._want = None
            self.zeta = max(0.12, p.cfg_int("wave_bounce", 38) / 100.0)
            self._set_active(-1, False)
            if p.cfg_bool("wave_haptic_release", False):
                self._buzz(1)
            self._kick()
            return True
        return False

    def _set_active(self, idx, first):
        if idx == self.active:
            return
        old = self.active
        self.active = idx
        base, act = self._base_color(), self._active_color()
        if 0 <= old < len(self.letters):
            self.letters[old].tv.setTextColor(act if self._filtered(self.letters[old]) else base)
        if idx < 0:
            self._bubble_hide()
            return
        self._bubble_show(self.letters[idx].ch)
        self.letters[idx].tv.setTextColor(act)
        crossings = 1 if old < 0 else abs(idx - old)
        if self.plugin.cfg_bool("wave_haptic", True):
            self._buzz(crossings)
        if self.frag is not None and self.plugin.cfg_bool("wave_filter", True):
            ch = self.letters[idx].key
            self._want = ch
            self._tok += 1
            tok = self._tok

            def go():
                if tok == self._tok and self.touching and self.active == idx:
                    self.flt.request(self.frag, ch)
                    self._want = None
            run_on_ui_thread(go, 30)

    def _buzz(self, crossings):
        p = self.plugin
        Haptics.ratchet(self.ctx, p.cfg_int("wave_haptic_style", 0), crossings, p.cfg_int("wave_haptic_strength", 100),
                        p.cfg_int("wave_haptic_len", 11), p.cfg_int("wave_haptic_gap", 20))

    def _kick(self):
        if self.running or not self._attached:
            return
        self.running = True
        self.last_frame = 0
        if self._frame_cb is None:
            outer = self

            class _Frame(_frame_cls()):
                def doFrame(self_i, nanos):
                    try:
                        outer._frame(int(nanos))
                    except Exception as ex:
                        outer.running = False
                        log("[Wave] frame: {0}".format(ex))
            self._frame_cb = _Frame()
        try:
            jclass("android.view.Choreographer").getInstance().postFrameCallback(self._frame_cb)
        except Exception as ex:
            self.running = False
            log("[Wave] choreographer: {0}".format(ex))

    def _targets(self):
        p = self.plugin
        idle = p.cfg_int("wave_idle", 0) / 100.0
        amp = float(p._dp(p.cfg_int("wave_amp", 56)))
        sig = float(p._dp(p.cfg_int("wave_sigma", 62)))
        gain = p.cfg_int("wave_scale", 90) / 100.0
        reveal = max(0.3, p.cfg_int("wave_reveal", 160) / 100.0)
        sign = 1.0 if p.cfg_int("wave_side", 0) == 1 else -1.0
        for L in self.letters:
            if self.touching:
                d = L.y - self.fy
                g = math.exp(-(d * d) / (2.0 * sig * sig))
                ga = math.exp(-(d * d) / (2.0 * (sig * reveal) ** 2))
                L.tx, L.ts, L.ta = sign * amp * g, 1.0 + gain * g, idle + (1.0 - idle) * ga
            else:
                L.tx, L.ts, L.ta = 0.0, 1.0, idle
            if self._filtered(L):
                L.ta = 1.0

    def _frame(self, nanos):
        if not self._attached:
            self.running = False
            return
        p = self.plugin
        dt = 0.016 if not self.last_frame else min(0.033, max(0.001, (nanos - self.last_frame) / 1e9))
        self.last_frame = nanos
        self._targets()
        k = float(p.cfg_int("wave_stiffness", 320))
        c = 2.0 * self.zeta * math.sqrt(k)
        ka = 260.0
        ca = 2.0 * 0.95 * math.sqrt(ka)
        steps = max(1, int(math.ceil(dt / 0.008)))
        h = dt / steps
        moving = False
        for L in self.letters:
            for _ in range(steps):
                L.vx += (k * (L.tx - L.x) - c * L.vx) * h
                L.x += L.vx * h
                L.vs += (k * (L.ts - L.s) - c * L.vs) * h
                L.s += L.vs * h
                L.va += (ka * (L.ta - L.a) - ca * L.va) * h
                L.a += L.va * h
            if abs(L.x - L.sx) > 0.15:
                L.tv.setTranslationX(float(L.x))
                L.sx = L.x
            if abs(L.s - L.ss) > 0.004:
                L.tv.setScaleX(float(L.s))
                L.tv.setScaleY(float(L.s))
                L.ss = L.s
            if abs(L.a - L.sa) > 0.004:
                L.tv.setAlpha(float(max(0.0, min(1.0, L.a))))
                L.sa = L.a
            if (abs(L.vx) > 0.05 or abs(L.x - L.tx) > 0.1 or abs(L.vs) > 0.002 or abs(L.s - L.ts) > 0.003
                    or abs(L.a - L.ta) > 0.004):
                moving = True
        if moving or self.touching:
            jclass("android.view.Choreographer").getInstance().postFrameCallback(self._frame_cb)
        else:
            self.running = False

    def reset_filter(self):
        try:
            if self.flt is not None and (self.flt.letter is not None or self.flt.has_pending):
                self.flt.request(self.frag, None)
                if self.plugin.cfg_bool("wave_haptic", True):
                    Haptics.ratchet(self.ctx, 1, 1, 70, 8, 10)
        except Exception as e:
            log("[Wave] reset: {0}".format(e))

    def on_filter_changed(self, letter):
        if self._attached:
            try:
                base, act = self._base_color(), self._active_color()
                for L in self.letters:
                    L.tv.setTextColor(act if (letter is not None and L.key == letter) else base)
                self._kick()
            except Exception as ex:
                log("[Wave] recolor: {0}".format(ex))
        if not self._attached or self.cap is None:
            return
        p = self.plugin
        cap = self.cap
        dens = float(p._dp(1))
        cap.animate().cancel()
        if letter is None or not p.cfg_bool("wave_badge", True):
            cap.animate().alpha(0.0).translationX(-14.0 * dens).setDuration(170).start()

            def gone():
                if self.flt.letter is None:
                    cap.setVisibility(View.GONE)
            run_on_ui_thread(gone, 190)
            return
        col = self._active_color()
        lum = ((col >> 16) & 255) * 0.299 + ((col >> 8) & 255) * 0.587 + (col & 255) * 0.114
        ink = p._c(0xFF101014) if lum > 140 else p._c(0xFFFFFFFF)
        d = GradientDrawable()
        d.setCornerRadius(float(p._dp(18)))
        d.setColor(col)
        cap.setBackground(d)
        self.cap_letter.setText(self._label_for(letter) or str(letter))
        self.cap_letter.setTextColor(ink)
        self.cap_x.setTextColor(ink)
        self.cap_x.setAlpha(0.8)
        first = cap.getVisibility() != View.VISIBLE
        cap.setVisibility(View.VISIBLE)
        if first:
            cap.setAlpha(0.0)
            cap.setTranslationX(-16.0 * dens)
        OI = jclass("android.view.animation.OvershootInterpolator")
        cap.animate().alpha(1.0).translationX(0.0).setInterpolator(OI(1.4)).setDuration(260).start()
