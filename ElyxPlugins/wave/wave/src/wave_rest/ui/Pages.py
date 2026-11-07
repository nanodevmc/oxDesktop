try:
    __file__
except NameError:
    try:
        __file__ = file
    except NameError:
        __file__ = ""

import os
import re
import threading
import time

from android.view import Gravity, View
from android.widget import FrameLayout, ImageView, LinearLayout, ScrollView, TextView
from android.graphics import Typeface
from java import dynamic_proxy, jarray, jbyte, jclass
from org.telegram.ui.ActionBar import Theme
from org.telegram.messenger import ApplicationLoader
from base_plugin import MethodHook
from hook_utils import find_class
from android_utils import log, run_on_ui_thread, OnClickListener
try:
    from wave_addons.Diag import log
except Exception:
    pass
from client_utils import get_last_fragment

try:
    from wave_addons import Alpha as A
except Exception:
    from ...wave_addons import Alpha as A

FONT_REQ = 7741

EMOJI = ["⭐", "🔥", "❤️", "💙", "💚", "💛", "🧡", "💜", "🖤", "💼", "🏠", "🎮", "🎵", "🎬", "📷", "📚", "💡", "🛒",
         "🚗", "✈️", "🌍", "👪", "👥", "🤝", "💬", "📞", "📌", "🔔", "🎯", "🏆", "💰", "🎁", "🍕", "☕", "🐱", "🐶",
         "🌸", "🌙", "☀️", "⚡", "🧠", "👾", "🤖", "🚀", "🎓", "⚽", "🎧", "🔒", "✅", "❗", "❓", "😀", "😎", "🥳",
         "😴", "🙏", "👍", "💎", "🧾", "🎂"]
SYMBOLS = list("★☆♥♦♣♠●◆■▲✦✿☂☎✉♪✚∞№@&$%*+=!?~^§©®™°•◎☼☾")
LETTERS = list(A.LATIN) + list(A.CYR) + list("0123456789")
THEME_BLUE = 0xFF8AB4F8


class _FontResultHook(MethodHook):
    def __init__(self, plugin):
        self.plugin = plugin

    def after_hooked_method(self, param):
        try:
            if int(param.args[0]) != FONT_REQ:
                return
            if int(param.args[1]) != -1 or param.args[2] is None:
                return
            uri = param.args[2].getData()
            if uri is not None:
                self.plugin._import_font_uri(uri)
        except Exception as e:
            log("[Wave] font result: {0}".format(e))


class WavePages:
    def _s_opt(self, key):
        v = self._s(key, "\x00")
        return None if v in ("\x00", key, "") else v

    def _alpha_lang(self):
        v = self.cfg_int("wave_alpha_lang", -1)
        if v in (0, 1):
            return v
        return 0 if self._client_lang() == "ru" else 1

    def _anchor(self):
        try:
            return get_last_fragment().getFragmentView()
        except Exception:
            return None

    def _install_font_hook(self):
        try:
            cls = find_class("org.telegram.ui.LaunchActivity")
            refs = list(self.hook_all_methods(cls, "onActivityResult", _FontResultHook(self)) or [])
            self._hooks.extend(refs)
        except Exception as e:
            log("[Wave] font hook: {0}".format(e))

    def _rerender_page(self):
        fn = getattr(self, "_lab_rerender", None)
        if fn is not None:
            try:
                run_on_ui_thread(fn)
            except Exception:
                pass

    def _fmt(self, v, unit):
        return "{0}{1}{2}".format(v, " " if unit and unit not in ("%", "°") else "", unit)

    def _r_switch(self, ctx, g, key, default, icon, on=None):
        def toggled(v):
            self.set_setting(key, bool(v))
            self._refresh_overlays()
            if on:
                run_on_ui_thread(lambda: on(v), 180)
        sw, tap = self._switch(ctx, self.cfg_bool(key, default), toggled)
        self._row(ctx, g, self._s(key), self._s_opt(key + "_sub"), self._icon(*icon), sw, lambda v: tap(sw))

    def _r_slider(self, ctx, g, key, default, lo, hi, unit, icon, step=1):
        try:
            cur = int(float(self.get_setting(key, default)))
        except Exception:
            cur = int(default)
        cur = max(lo, min(hi, cur))
        self._row(ctx, g, self._s(key), self._fmt(cur, unit), self._icon(*icon), None,
                  lambda v: self._slider_sheet(ctx, key, default, lo, hi, unit, step))

    def _slider_sheet(self, ctx, key, default, lo, hi, unit, step=1):
        p = self._pal()
        try:
            cur = int(float(self.get_setting(key, default)))
        except Exception:
            cur = int(default)
        cur = max(lo, min(hi, cur))
        state = {"t": 0.0}

        def build(c, close):
            val = self._tv(ctx, self._fmt(cur, unit), 30, p["acc"], True, wrap=False)
            val.setGravity(Gravity.CENTER)
            c.addView(val, self._lp(bottom=4))

            def changed(v, final):
                self.set_setting(key, int(v))
                val.setText(self._fmt(v, unit))
                now = time.time()
                if final or now - state["t"] > 0.08:
                    state["t"] = now
                    self._refresh_overlays()
            s = self._slider(ctx, lo, hi, step, cur, changed)
            c.addView(s.view, self._lp(-1, self._dp(44)))

            def reset(v):
                self.set_setting(key, int(default))
                s.set(int(default))
                val.setText(self._fmt(int(default), unit))
                self._refresh_overlays()
            btns = LinearLayout(ctx)
            btns.addView(self._button(ctx, self._s("wave_default"), reset, "text"), self._lp(0, -2, right=10, weight=1.0))
            btns.addView(self._button(ctx, self._s("wave_done"), lambda v: close(), "filled"), self._lp(0, -2, weight=1.0))
            c.addView(btns, self._lp(top=14))
        self._sheet(ctx, self._s(key), build, self._rerender_page, self._s_opt(key + "_sub"))

    def _r_choice(self, ctx, g, key, default, label_keys, icon, on=None, per_row=2, seg_max=3, get=None, put=None):
        labels = [self._s(k) for k in label_keys]
        cur = get() if get else self.cfg_int(key, default)
        cur = max(0, min(len(labels) - 1, int(cur)))

        def pick(k, close):
            if put:
                put(k)
            else:
                self.set_setting(key, int(k))
            self._refresh_overlays()
            run_on_ui_thread(close, 140)
            if on:
                run_on_ui_thread(lambda: on(k), 260)

        def build(c, close):
            if len(labels) <= seg_max:
                c.addView(self._segmented(ctx, labels, cur, lambda k: pick(k, close)))
            else:
                c.addView(self._chips(ctx, labels, cur, lambda k: pick(k, close), per_row))
        self._row(ctx, g, self._s(key), labels[cur], self._icon(*icon), None,
                  lambda v: self._sheet(ctx, self._s(key), build, self._rerender_page, self._s_opt(key + "_sub")))

    def _r_color(self, ctx, g, key, icon, allow_auto, default_rgb=None):
        p = self._pal()
        cur = A.parse_hex(self.get_setting(key, ""), None)
        shown = cur if cur is not None else (default_rgb if default_rgb is not None else p["acc"])
        dot = View(ctx)
        self._paint_swatch(dot, shown, 32)
        sw = FrameLayout(ctx)
        sw.addView(dot, FrameLayout.LayoutParams(self._dp(32), self._dp(32), Gravity.CENTER))
        sub = A.to_hex(cur) if cur is not None else self._s("wave_hex_auto")
        self._row(ctx, g, self._s(key), sub, self._icon(*icon), sw,
                  lambda v: self._palette_sheet(ctx, key, self._s(key), allow_auto, default_rgb))

    def _palette_sheet(self, ctx, key, title, allow_auto=True, default_rgb=None):
        def build(c, close):
            self._palette_content(ctx, c, key, allow_auto, default_rgb)
            c.addView(self._button(ctx, self._s("wave_done"), lambda v: close(), "filled"), self._lp(top=14))
        self._sheet(ctx, title, build, lambda: (self._refresh_overlays(), self._rerender_page()))

    def _palette_content(self, ctx, box, key, allow_auto=True, default_rgb=None):
        p = self._pal()
        cur = A.parse_hex(self.get_setting(key, ""), None)
        base = cur if cur is not None else (default_rgb if default_rgb is not None else p["acc"])
        h, s, v = A.rgb_int_to_hsv(base)
        st = {"h": h, "s": s, "v": v, "auto": cur is None and allow_auto, "t": 0.0}
        prev = TextView(ctx)
        prev.setGravity(Gravity.CENTER)
        prev.setTextSize(1, 14.0)
        box.addView(prev, self._lp(-1, self._dp(48)))
        sw_views, sliders = [], {}
        hues = [0, 24, 48, 100, 165, 205, 260, 320]
        rows = [[A.hsv_to_rgb_int(0, 0, x) for x in (1.0, 0.86, 0.72, 0.58, 0.44, 0.3, 0.16, 0.0)]]
        for sat, val in ((0.38, 1.0), (0.78, 1.0), (0.9, 0.68)):
            rows.append([A.hsv_to_rgb_int(hh / 360.0, sat, val) for hh in hues])

        def refresh(apply):
            rgb = A.hsv_to_rgb_int(st["h"], st["s"], st["v"])
            auto = st["auto"]
            shown = (default_rgb if default_rgb is not None else p["acc"]) if auto else rgb
            prev.setBackground(self._rr(shown, 16))
            prev.setTextColor(self._c(0xFF111111 if A.luminance(shown) > 150 else 0xFFFFFFFF))
            prev.setText(self._s("wave_hex_auto") if auto else A.to_hex(rgb))
            try:
                sliders["s"].set_track([A.hsv_to_rgb_int(st["h"], 0, st["v"]), A.hsv_to_rgb_int(st["h"], 1, st["v"])])
                sliders["v"].set_track([A.hsv_to_rgb_int(st["h"], st["s"], 0), A.hsv_to_rgb_int(st["h"], st["s"], 1)])
            except Exception:
                pass
            for view, col in sw_views:
                self._paint_swatch(view, col, 28, ring=(not auto and col == rgb))
            if apply:
                self.set_setting(key, "" if auto else A.to_hex(rgb))
                now = time.time()
                if now - st["t"] > 0.08:
                    st["t"] = now
                    self._refresh_overlays()

        def pick_rgb(col):
            st["h"], st["s"], st["v"] = A.rgb_int_to_hsv(col)
            st["auto"] = False
            sliders["h"].set(int(st["h"] * 359))
            sliders["s"].set(int(st["s"] * 100))
            sliders["v"].set(int(st["v"] * 100))
            refresh(True)
        grid = LinearLayout(ctx)
        grid.setOrientation(LinearLayout.VERTICAL)
        for r in rows:
            line = LinearLayout(ctx)
            for col in r:
                cell = FrameLayout(ctx)
                sv = View(ctx)
                cell.addView(sv, FrameLayout.LayoutParams(self._dp(28), self._dp(28), Gravity.CENTER))
                cell.setOnClickListener(OnClickListener(lambda x, cc=col: pick_rgb(cc)))
                line.addView(cell, LinearLayout.LayoutParams(0, self._dp(34), 1.0))
                sw_views.append((sv, col))
            grid.addView(line)
        box.addView(grid, self._lp(top=8))

        def mk(name, lo, hi, val, colors):
            row = LinearLayout(ctx)
            row.setGravity(Gravity.CENTER_VERTICAL)
            row.addView(self._tv(ctx, self._s(name), 13, p["sub"], False, wrap=False), self._lp(self._dp(96), -2))

            def ch(x, final, nm=name):
                if nm == "wave_pal_h":
                    st["h"] = x / 359.0
                elif nm == "wave_pal_s":
                    st["s"] = x / 100.0
                else:
                    st["v"] = x / 100.0
                st["auto"] = False
                refresh(True)
            sl = self._slider(ctx, lo, hi, 1, val, ch, colors=colors, fill=False)
            row.addView(sl.view, LinearLayout.LayoutParams(0, self._dp(40), 1.0))
            box.addView(row, self._lp(top=2))
            return sl
        rainbow = [A.hsv_to_rgb_int(i / 6.0, 1, 1) for i in range(7)]
        sliders["h"] = mk("wave_pal_h", 0, 359, int(h * 359), rainbow)
        sliders["s"] = mk("wave_pal_s", 0, 100, int(s * 100), [0xFFFFFFFF, base])
        sliders["v"] = mk("wave_pal_v", 0, 100, int(v * 100), [0xFF000000, base])
        refresh(False)
        if allow_auto:
            def auto_click(x):
                st["auto"] = True
                refresh(True)
            box.addView(self._button(ctx, self._s("wave_hex_auto"), auto_click, "text"), self._lp(top=4, gravity=Gravity.RIGHT))

    def _show_hex_sheet(self, key):
        a = self._anchor()
        if a is not None:
            self._palette_sheet(a.getContext(), key, self._s(key), key != "wave_color_hex")

    def _letter_color_sheet(self, ctx):
        def build(c, close):
            holder = LinearLayout(ctx)
            holder.setOrientation(LinearLayout.VERTICAL)

            def fill():
                holder.removeAllViews()
                if self.cfg_int("wave_color_mode", 0) == 2:
                    self._palette_content(ctx, holder, "wave_color_hex", False)

            def pick(k):
                self.set_setting("wave_color_mode", int(k))
                self._refresh_overlays()
                fill()
            c.addView(self._segmented(ctx, [self._s("wave_color_text"), self._s("wave_color_accent"), self._s("wave_color_custom")],
                                      self.cfg_int("wave_color_mode", 0), pick))
            c.addView(holder, self._lp(top=12))
            fill()
            c.addView(self._button(ctx, self._s("wave_done"), lambda v: close(), "filled"), self._lp(top=14))
        self._sheet(ctx, self._s("wave_color_mode"), build, self._rerender_page)

    def _custom_typeface(self):
        path = str(self.get_setting("wave_font_file", "") or "")
        if path and os.path.exists(path):
            try:
                return Typeface.createFromFile(path)
            except Exception:
                return None
        return None

    def _font_name(self):
        f = self.cfg_int("wave_font", 2)
        if f == A.FONT_CUSTOM:
            return os.path.basename(str(self.get_setting("wave_font_file", "") or "")) or self._s("wave_font_file")
        return self._s(A.FONTS[f if 0 <= f < len(A.FONTS) else 2][0])

    def _current_typeface(self):
        f = self.cfg_int("wave_font", 2)
        if f == A.FONT_CUSTOM:
            tf = self._custom_typeface()
            if tf is not None:
                return tf
            f = 2
        _, fam, st = A.FONTS[f if 0 <= f < len(A.FONTS) else 2]
        return Typeface.create(fam, st)

    def _r_font(self, ctx, g):
        aa = self._tv(ctx, "Aa", 22, self._pal()["text"], False, wrap=False)
        try:
            aa.setTypeface(self._current_typeface())
        except Exception:
            pass
        self._row(ctx, g, self._s("wave_font"), self._font_name(), self._icon("msg_photo_text_framed3", "msg_settings"), aa,
                  lambda v: self._font_sheet(ctx))

    def _font_sheet(self, ctx):
        p = self._pal()

        def build(c, close):
            n = len(A.FONTS)
            cur = self.cfg_int("wave_font", 2)
            cur = n if cur == A.FONT_CUSTOM else max(0, min(n - 1, cur))
            fname = os.path.basename(str(self.get_setting("wave_font_file", "") or ""))
            labels = [self._s(k) for k, _, _ in A.FONTS] + [(fname[:16] if fname else self._s("wave_font_file"))]
            tfs = [Typeface.create(fam, st) for _, fam, st in A.FONTS] + [self._custom_typeface()]
            preview = self._tv(ctx, "АБВГ ABCD #★ 123", 24, p["text"], False, wrap=False)
            preview.setGravity(Gravity.CENTER)
            preview.setPadding(self._dp(10), self._dp(12), self._dp(10), self._dp(12))
            preview.setBackground(self._rr(p["container"], 16))
            try:
                preview.setTypeface(tfs[cur] if tfs[cur] is not None else tfs[2])
            except Exception:
                pass
            c.addView(preview, self._lp(bottom=12))

            def pick(k):
                if k == n:
                    close()
                    run_on_ui_thread(lambda: self._font_file_sheet(ctx), 200)
                    return
                self.set_setting("wave_font", int(k))
                try:
                    preview.setTypeface(tfs[k])
                except Exception:
                    pass
                self._refresh_overlays()
            c.addView(self._chips(ctx, labels, cur, pick, 3, tfs))
            c.addView(self._button(ctx, self._s("wave_done"), lambda v: close(), "filled"), self._lp(top=14))
        self._sheet(ctx, self._s("wave_font"), build, self._rerender_page)

    def _font_dirs(self):
        dirs = []
        try:
            dirs.append(os.path.join(str(ApplicationLoader.getFilesDirFixed().getAbsolutePath()), "wave_fonts"))
        except Exception:
            pass
        for d in ("Download", "Fonts", "Documents", "Telegram/Telegram Documents"):
            dirs.append(os.path.join("/storage/emulated/0", d))
        return dirs

    def _scan_fonts(self):
        out, seen = [], set()
        for d in self._font_dirs():
            try:
                for name in sorted(os.listdir(d)):
                    if name.lower().endswith((".ttf", ".otf")) and name not in seen:
                        seen.add(name)
                        out.append(os.path.join(d, name))
            except Exception:
                pass
        return out[:40]

    def _font_file_sheet(self, ctx):
        p = self._pal()

        def build(c, close):
            c.addView(self._button(ctx, self._s("wave_font_pick"), lambda v: (close(), self._pick_font_file()), "filled"))
            files = self._scan_fonts()
            if files:
                c.addView(self._tv(ctx, self._s("wave_font_found"), 12, p["acc"], True, wrap=False), self._lp(top=14, bottom=6))
                sc = ScrollView(ctx)
                sc.setClipToPadding(True)
                col = LinearLayout(ctx)
                col.setOrientation(LinearLayout.VERTICAL)
                for path in files:
                    row = self._tv(ctx, os.path.basename(path), 15, p["text"], False, wrap=False)
                    row.setPadding(self._dp(14), self._dp(12), self._dp(14), self._dp(12))
                    row.setBackground(self._rr(p["container"], 14))
                    try:
                        row.setTypeface(Typeface.createFromFile(path))
                    except Exception:
                        pass
                    row.setOnClickListener(OnClickListener(lambda v, pp=path: (close(), self._use_font_file(pp))))
                    col.addView(row, self._lp(bottom=6))
                sc.addView(col)
                c.addView(sc, self._lp(-1, self._dp(190)))
            else:
                c.addView(self._tv(ctx, self._s("wave_font_none"), 13, p["sub"]), self._lp(top=10))
            c.addView(self._button(ctx, self._s("wave_font_system"), lambda v: (close(), self._use_system_font()), "text"),
                      self._lp(top=8))
        self._sheet(ctx, self._s("wave_font_file"), build, self._rerender_page, self._s("wave_font_file_hint"))

    def _use_system_font(self):
        self.set_setting("wave_font", 2)
        self.set_setting("wave_font_file", "")
        self._refresh_overlays()
        self._rerender_page()

    def _use_font_file(self, path):
        try:
            Typeface.createFromFile(path)
        except Exception:
            self._toast(self._s("wave_font_bad"), error=True)
            return
        dst = path
        try:
            d = os.path.join(str(ApplicationLoader.getFilesDirFixed().getAbsolutePath()), "wave_fonts")
            if not path.startswith(d):
                os.makedirs(d, exist_ok=True)
                dst = os.path.join(d, os.path.basename(path))
                with open(path, "rb") as a, open(dst, "wb") as b:
                    b.write(a.read())
        except Exception:
            dst = path
        self.set_setting("wave_font_file", dst)
        self.set_setting("wave_font", A.FONT_CUSTOM)
        self._refresh_overlays()
        self._rerender_page()

    def _pick_font_file(self):
        try:
            act = get_last_fragment().getParentActivity()
            Intent = jclass("android.content.Intent")
            it = Intent("android.intent.action.OPEN_DOCUMENT")
            it.addCategory("android.intent.category.OPENABLE")
            it.setType("*/*")
            mimes = ["font/ttf", "font/otf", "font/sfnt", "application/x-font-ttf", "application/x-font-otf",
                     "application/x-font-opentype", "application/octet-stream"]
            it.putExtra("android.intent.extra.MIME_TYPES", jarray(jclass("java.lang.String"))(mimes))
            act.startActivityForResult(it, FONT_REQ)
        except Exception as e:
            log("[Wave] font picker: {0}".format(e))
            self._toast(self._s("wave_font_bad"), error=True)

    def _import_font_uri(self, uri):
        def work():
            try:
                ctx = ApplicationLoader.applicationContext
                cr = ctx.getContentResolver()
                name = "font.ttf"
                try:
                    cur = cr.query(uri, None, None, None, None)
                    if cur is not None:
                        try:
                            if cur.moveToFirst():
                                i = int(cur.getColumnIndex("_display_name"))
                                if i >= 0:
                                    name = str(cur.getString(i))
                        finally:
                            cur.close()
                except Exception:
                    pass
                name = re.sub(r"[^\w.\- ]", "_", name)[:60]
                if not name.lower().endswith((".ttf", ".otf")):
                    name += ".ttf"
                d = os.path.join(str(ApplicationLoader.getFilesDirFixed().getAbsolutePath()), "wave_fonts")
                os.makedirs(d, exist_ok=True)
                dst = os.path.join(d, name)
                ins = cr.openInputStream(uri)
                out = jclass("java.io.FileOutputStream")(dst)
                buf = jarray(jbyte)(65536)
                while True:
                    n = int(ins.read(buf))
                    if n <= 0:
                        break
                    out.write(buf, 0, n)
                out.close()
                ins.close()
                Typeface.createFromFile(dst)
                run_on_ui_thread(lambda: self._use_font_file(dst))
            except Exception as e:
                log("[Wave] font import: {0}".format(e))
                run_on_ui_thread(lambda: self._toast(self._s("wave_font_bad"), error=True))
        threading.Thread(target=work, daemon=True).start()

    def _pins(self):
        return A.pins_load(str(self.get_setting("wave_pins", "[]") or "[]"))

    def _save_pins(self, pins):
        self.set_setting("wave_pins", A.pins_dump(pins))
        try:
            self._reset_all_filters()
        except Exception:
            pass
        self._refresh_overlays()

    def _r_pins(self, ctx, c):
        p = self._pal()
        pins = self._pins()
        g = self._sec(ctx, c, self._s("wave_sec_pins"))
        for i, pin in enumerate(pins):
            sym = self._tv(ctx, pin["s"], 22, p["text"], False, wrap=False)
            sym.setGravity(Gravity.CENTER)
            sym.setBackground(self._rr(p["sel"], 20, oval=True))
            pos = self._s("wave_pos_top") if pin["pos"] == 0 else self._s("wave_pos_bottom")
            self._row(ctx, g, self._s("wave_pin_chats").format(len(pin["ids"])), pos, None, None,
                      lambda v, k=i: self._pin_editor(ctx, k, None), sym)
        add = self._tv(ctx, "＋", 22, p["acc"], True, wrap=False)
        add.setGravity(Gravity.CENTER)
        add.setBackground(self._rr(p["sel"], 20, oval=True))
        self._row(ctx, g, self._s("wave_pin_add"), self._s_opt("wave_sec_pins_sub") if not pins else None, None, None,
                  lambda v: self._pin_editor(ctx, None, None), add)

    def _pin_editor(self, ctx, idx, state):
        p = self._pal()
        pins = self._pins()
        if state is None:
            if idx is not None and 0 <= idx < len(pins):
                state = {"s": pins[idx]["s"], "ids": list(pins[idx]["ids"]), "pos": pins[idx]["pos"]}
            else:
                state = {"s": "⭐", "ids": [], "pos": 0}

        def build(c, close):
            top = LinearLayout(ctx)
            top.setGravity(Gravity.CENTER_VERTICAL)
            big = self._tv(ctx, state["s"], 30, p["text"], False, wrap=False)
            big.setGravity(Gravity.CENTER)
            big.setBackground(self._rr(p["sel"], 20))
            top.addView(big, self._lp(self._dp(64), self._dp(64), right=14))
            top.addView(self._tv(ctx, self._s("wave_pin_pos"), 12, p["sub"], True, wrap=False), self._lp(0, -2, weight=1.0))
            c.addView(top)
            cat_state = {"c": 0}
            holder = LinearLayout(ctx)
            holder.setOrientation(LinearLayout.VERTICAL)

            def fill(cat):
                holder.removeAllViews()
                items = (EMOJI, SYMBOLS, LETTERS)[cat]
                line = None
                for i, sy in enumerate(items):
                    if i % 7 == 0:
                        line = LinearLayout(ctx)
                        holder.addView(line)
                    cell = FrameLayout(ctx)
                    t = self._tv(ctx, sy, 20, p["text"], False, wrap=False)
                    t.setGravity(Gravity.CENTER)
                    if sy == state["s"]:
                        t.setBackground(self._rr(p["sel"], 12))

                    def choose(v, s2=sy):
                        state["s"] = s2
                        big.setText(s2)
                        fill(cat_state["c"])
                    t.setOnClickListener(OnClickListener(choose))
                    cell.addView(t, FrameLayout.LayoutParams(self._dp(38), self._dp(38), Gravity.CENTER))
                    line.addView(cell, LinearLayout.LayoutParams(0, self._dp(42), 1.0))
                for _ in range((-len(items)) % 7):
                    line.addView(View(ctx), LinearLayout.LayoutParams(0, self._dp(42), 1.0))

            def set_cat(k):
                cat_state["c"] = k
                fill(k)
            c.addView(self._segmented(ctx, [self._s("wave_pin_cat_emoji"), self._s("wave_pin_cat_sym"), self._s("wave_pin_cat_abc")], 0, set_cat),
                      self._lp(top=12))
            fill(0)
            sc = ScrollView(ctx)
            sc.setClipToPadding(True)
            sc.addView(holder)
            c.addView(sc, self._lp(-1, self._dp(170), top=8))

            def put_pos(k):
                state["pos"] = int(k)
            c.addView(self._segmented(ctx, [self._s("wave_pos_top"), self._s("wave_pos_bottom")], state["pos"], put_pos), self._lp(top=10))

            def open_chats(v):
                close()
                run_on_ui_thread(lambda: self._chat_picker(ctx, state["ids"], lambda ids: (
                    state.__setitem__("ids", ids), run_on_ui_thread(lambda: self._pin_editor(ctx, idx, state), 200))), 220)
            c.addView(self._button(ctx, self._s("wave_pin_pick").format(len(state["ids"])), open_chats), self._lp(top=10))

            def save(v):
                cur = self._pins()
                item = {"s": state["s"], "ids": state["ids"], "pos": state["pos"]}
                if idx is not None and 0 <= idx < len(cur):
                    cur[idx] = item
                else:
                    cur.append(item)
                self._save_pins(cur)
                close()

            def delete(v):
                cur = self._pins()
                if idx is not None and 0 <= idx < len(cur):
                    cur.pop(idx)
                    self._save_pins(cur)
                close()
            btns = LinearLayout(ctx)
            if idx is not None:
                btns.addView(self._button(ctx, self._s("wave_pin_delete"), delete, "danger"), self._lp(0, -2, right=10, weight=1.0))
            btns.addView(self._button(ctx, self._s("wave_done"), save, "filled"), self._lp(0, -2, weight=1.0))
            c.addView(btns, self._lp(top=12))
        self._sheet(ctx, self._s("wave_pin_title"), build, self._rerender_page)

    def _all_chats(self):
        rows = []
        try:
            from org.telegram.messenger import MessagesController, UserConfig
            mc = MessagesController.getInstance(UserConfig.selectedAccount)
            lst = mc.getAllDialogs()
            for i in range(min(int(lst.size()), 800)):
                did = int(lst.get(i).id)
                t = self.dialog_title(did)
                if t and t != "#":
                    rows.append((did, t))
        except Exception as e:
            log("[Wave] all chats: {0}".format(e))
        if not rows:
            try:
                for f in self._dialogs_fragments():
                    for _d, did, t in self._filter._snapshot(f):
                        if t and t != "#":
                            rows.append((did, t))
                    if rows:
                        break
            except Exception:
                pass
        rows.sort(key=lambda r: r[1].casefold())
        return rows

    def _avatar(self, ctx, did, title, palette):
        try:
            from org.telegram.messenger import MessagesController, UserConfig
            from org.telegram.ui.Components import AvatarDrawable, BackupImageView
            mc = MessagesController.getInstance(UserConfig.selectedAccount)
            obj = mc.getUser(int(did)) if int(did) > 0 else mc.getChat(-int(did))
            if obj is not None:
                iv = BackupImageView(ctx)
                iv.setRoundRadius(self._dp(20))
                ad = AvatarDrawable()
                ad.setInfo(obj)
                iv.setForUserOrChat(obj, ad)
                return iv
        except Exception:
            pass
        av = TextView(ctx)
        av.setText(title[:1].upper())
        av.setGravity(Gravity.CENTER)
        av.setTextColor(self._c(0xFFFFFFFF))
        av.setTextSize(1, 16.0)
        av.setBackground(self._rr(palette[abs(did) % len(palette)], 20, oval=True))
        return av

    def _chat_picker(self, ctx, selected, on_done):
        try:
            p = self._pal()
            rows = self._all_chats()
            if not rows:
                self._toast(self._s("wave_pin_nochats"), error=True)
                on_done(list(selected))
                return
            chosen = set(int(x) for x in selected)
            result = {"done": False}

            def finish():
                if not result["done"]:
                    result["done"] = True
                    on_done(sorted(chosen))
            palette = [0xFFE57373, 0xFFF06292, 0xFFBA68C8, 0xFF7986CB, 0xFF4FC3F7, 0xFF4DB6AC, 0xFF81C784, 0xFFFFB74D, 0xFFA1887F]

            def build(c, close):
                counter = self._tv(ctx, "", 13, p["sub"])
                c.addView(counter, self._lp(bottom=8))
                sc = ScrollView(ctx)
                sc.setClipToPadding(True)
                col = LinearLayout(ctx)
                col.setOrientation(LinearLayout.VERTICAL)
                sc.addView(col)
                hmax = min(self._dp(420), int(ctx.getResources().getDisplayMetrics().heightPixels * 0.5))
                c.addView(sc, LinearLayout.LayoutParams(-1, hmax))

                def upd():
                    counter.setText(self._s("wave_pin_chats").format(len(chosen)))
                for did, title in rows:
                    row = LinearLayout(ctx)
                    row.setGravity(Gravity.CENTER_VERTICAL)
                    row.setPadding(self._dp(4), self._dp(6), self._dp(4), self._dp(6))
                    av = self._avatar(ctx, did, title, palette)
                    row.addView(av, self._lp(self._dp(40), self._dp(40), right=12))
                    t = self._tv(ctx, title, 15.5, p["text"], False, wrap=False)
                    t.setSingleLine(True)
                    t.setEllipsize(jclass("android.text.TextUtils$TruncateAt").END)
                    row.addView(t, LinearLayout.LayoutParams(0, -2, 1.0))
                    chk = TextView(ctx)
                    chk.setGravity(Gravity.CENTER)
                    chk.setTextSize(1, 14.0)
                    row.addView(chk, self._lp(self._dp(24), self._dp(24), left=8))

                    def paint(cv, on):
                        if on:
                            cv.setText("✓")
                            cv.setTextColor(self._c(p["ink"]))
                            cv.setBackground(self._rr(p["acc"], 12, oval=True))
                        else:
                            cv.setText("")
                            cv.setBackground(self._rr(p["base"], 12, p["outline"], 2.0, oval=True))
                    paint(chk, did in chosen)

                    def tap(v, d=did, cv=chk):
                        if d in chosen:
                            chosen.discard(d)
                        else:
                            chosen.add(d)
                        paint(cv, d in chosen)
                        upd()
                    row.setOnClickListener(OnClickListener(tap))
                    col.addView(row)
                upd()

                def clear(v):
                    chosen.clear()
                    close()
                btns = LinearLayout(ctx)
                btns.addView(self._button(ctx, self._s("wave_pin_clear"), clear, "text"), self._lp(0, -2, right=10, weight=1.0))
                btns.addView(self._button(ctx, self._s("wave_done"), lambda v: close(), "filled"), self._lp(0, -2, weight=1.0))
                c.addView(btns, self._lp(top=10))
            self._sheet(ctx, self._s("wave_pin_pick_title"), build, finish)
        except Exception as e:
            log("[Wave] chat picker: {0}".format(e))
            on_done(list(selected))

    def _resolve_username(self, username, done):
        try:
            from org.telegram.messenger import MessagesController, UserConfig
            res = MessagesController.getInstance(UserConfig.selectedAccount).getUserNameResolver()
        except Exception:
            return
        for iface in ("java.util.function.Consumer", "org.telegram.messenger.Utilities$Callback"):
            try:
                base = dynamic_proxy(jclass(iface))
                if iface.endswith("Consumer"):
                    class _CB(base):
                        def accept(self_i, v):
                            done(v)
                else:
                    class _CB(base):
                        def run(self_i, v):
                            done(v)
                res.resolve(username, _CB())
                return
            except Exception:
                continue

    def _avatar_user(self, ctx, username, letter, size):
        p = self._pal()
        box = FrameLayout(ctx)
        fb = TextView(ctx)
        fb.setText(letter)
        fb.setGravity(Gravity.CENTER)
        fb.setTextSize(1, size * 0.4)
        fb.setTextColor(self._c(p["ink"]))
        fb.setBackground(self._rr(p["acc"], size // 2, oval=True))
        box.addView(fb, FrameLayout.LayoutParams(-1, -1))

        def apply(user):
            try:
                from org.telegram.ui.Components import AvatarDrawable, BackupImageView
                iv = BackupImageView(ctx)
                iv.setRoundRadius(self._dp(size // 2))
                ad = AvatarDrawable()
                ad.setInfo(user)
                iv.setForUserOrChat(user, ad)
                box.addView(iv, FrameLayout.LayoutParams(-1, -1))
            except Exception as e:
                log("[Wave] author avatar: {0}".format(e))
        try:
            from org.telegram.messenger import MessagesController, UserConfig
            mc = MessagesController.getInstance(UserConfig.selectedAccount)
            obj = None
            try:
                obj = mc.getUserOrChat(username)
            except Exception:
                obj = None
            if obj is not None:
                apply(obj)
            else:
                def got(uid):
                    try:
                        u = mc.getUser(int(uid))
                        if u is not None:
                            run_on_ui_thread(lambda: apply(u))
                    except Exception:
                        pass
                self._resolve_username(username, got)
        except Exception as e:
            log("[Wave] author avatar: {0}".format(e))
        return box

    def _author_card(self, ctx, username, name, role, letter):
        p = self._pal()
        card = LinearLayout(ctx)
        card.setGravity(Gravity.CENTER_VERTICAL)
        card.setPadding(self._dp(16), self._dp(14), self._dp(16), self._dp(14))
        card.setBackground(self._rr(p["container"], 24))
        card.addView(self._avatar_user(ctx, username, letter, 56), self._lp(self._dp(56), self._dp(56), right=14))
        col = LinearLayout(ctx)
        col.setOrientation(LinearLayout.VERTICAL)
        col.addView(self._tv(ctx, name, 18, p["text"], True))
        col.addView(self._tv(ctx, role, 13, p["sub"]), self._lp(top=1))
        col.addView(self._tv(ctx, "@" + username, 12, p["acc"], True, wrap=False), self._lp(top=3))
        card.addView(col, LinearLayout.LayoutParams(0, -2, 1.0))
        card.addView(self._tv(ctx, "›", 22, p["sub"], False, wrap=False), self._lp(-2, -2, left=8))
        card.setClickable(True)
        card.setOnClickListener(OnClickListener(lambda v: self._open_username(username)))
        return card

    def _heart_drawable(self, color, size=34):
        from android.graphics import Path, Paint, Canvas, Bitmap
        n = self._dp(size)
        bmp = Bitmap.createBitmap(n, n, jclass("android.graphics.Bitmap$Config").ARGB_8888)
        cv = Canvas(bmp)
        pt = Paint(1)
        pt.setStyle(jclass("android.graphics.Paint$Style").STROKE)
        pt.setStrokeWidth(n / 24.0 * 1.7)
        pt.setStrokeJoin(jclass("android.graphics.Paint$Join").ROUND)
        pt.setStrokeCap(jclass("android.graphics.Paint$Cap").ROUND)
        pt.setColor(self._c(color))
        k = n / 24.0
        path = Path()
        path.moveTo(12 * k, 20.5 * k)
        path.cubicTo(5.5 * k, 15 * k, 2.6 * k, 12 * k, 2.6 * k, 8.4 * k)
        path.cubicTo(2.6 * k, 5.6 * k, 4.8 * k, 3.5 * k, 7.5 * k, 3.5 * k)
        path.cubicTo(9.4 * k, 3.5 * k, 11 * k, 4.5 * k, 12 * k, 6 * k)
        path.cubicTo(13 * k, 4.5 * k, 14.6 * k, 3.5 * k, 16.5 * k, 3.5 * k)
        path.cubicTo(19.2 * k, 3.5 * k, 21.4 * k, 5.6 * k, 21.4 * k, 8.4 * k)
        path.cubicTo(21.4 * k, 12 * k, 18.5 * k, 15 * k, 12 * k, 20.5 * k)
        path.close()
        cv.drawPath(path, pt)
        return bmp

    def _heart_view(self, ctx, color, size):
        try:
            rid = self._telegram_drawable_id("msg_fave", "input_like")
            if rid:
                iv = ImageView(ctx)
                iv.setImageResource(rid)
                iv.setColorFilter(self._c(color))
                iv.setScaleType(ImageView.ScaleType.FIT_CENTER)
                return iv
        except Exception as e:
            log("[Wave] heart res: {0}".format(e))
        try:
            iv = ImageView(ctx)
            iv.setImageBitmap(self._heart_drawable(color, size))
            return iv
        except Exception as e:
            log("[Wave] heart bmp: {0}".format(e))
        tv = self._tv(ctx, "\u2661", 30, color, False, wrap=False)
        tv.setGravity(Gravity.CENTER)
        return tv

    def _authors_block(self, ctx):
        p = self._pal()
        block = LinearLayout(ctx)
        block.setOrientation(LinearLayout.VERTICAL)
        block.setPadding(self._dp(16), self._dp(4), self._dp(16), self._dp(6))
        block.addView(self._author_card(ctx, "LuPlugins", self._s("wave_author_name"), self._s("wave_author_role"), "Г"))
        link = LinearLayout(ctx)
        link.setOrientation(LinearLayout.VERTICAL)
        link.setGravity(Gravity.CENTER_HORIZONTAL)

        def bar():
            b = View(ctx)
            try:
                b.setBackground(self._rr(p["acc"], 2))
            except Exception:
                b.setBackgroundColor(self._c(p["acc"]))
            link.addView(b, self._lp(self._dp(2), self._dp(10)))

        bar()
        link.addView(self._heart_view(ctx, p["acc"], 34), self._lp(self._dp(34), self._dp(34), top=3, bottom=3))
        bar()
        block.addView(link, self._lp(-1, -2))
        block.addView(self._author_card(ctx, "optimist_opti", self._s("wave_opti_name"), self._s("wave_opti_role"), "О"))
        return block

    def _lab_page(self, ctx, tab):
        c = LinearLayout(ctx)
        c.setOrientation(LinearLayout.VERTICAL)
        c.setPadding(self._dp(12), self._dp(2), self._dp(12), self._dp(24))

        def rr():
            try:
                c.removeAllViews()
                self._fill_tab(ctx, int(tab), c, rr)
            except Exception as e:
                log("[Wave] page fill: {0}".format(e))
        self._lab_rerender = rr
        rr()
        return c

    def _fill_tab(self, ctx, tab, c, rr):
        (self._tab_look, self._tab_motion, self._tab_haptic, self._tab_filter, self._tab_alpha)[tab](ctx, c, rr)

    def _tab_look(self, ctx, c, rr):
        ic = ("pip_video_expand", "msg_settings")
        g = self._sec(ctx, c, self._s("wave_sec_pos"))
        self._r_choice(ctx, g, "wave_side", 0, ["wave_side_right", "wave_side_left"], ic)
        self._r_slider(ctx, g, "wave_zone", 32, 16, 80, "dp", ("photo_rectangle", "msg_settings"))
        self._r_slider(ctx, g, "wave_idle", 0, 0, 60, "%", ("msg_stories_views", "msg_settings"))
        self._r_switch(ctx, g, "wave_auto_inset", True, ic, on=lambda v: rr())
        if not self.cfg_bool("wave_auto_inset", True):
            self._r_slider(ctx, g, "wave_inset_top", 120, 0, 260, "dp", ic)
            self._r_slider(ctx, g, "wave_inset_bottom", 96, 0, 260, "dp", ic)
        g = self._sec(ctx, c, self._s("wave_sec_color"))
        mode = self.cfg_int("wave_color_mode", 0)
        cur = A.parse_hex(self.get_setting("wave_color_hex", ""), None)
        names = [self._s("wave_color_text"), self._s("wave_color_accent"), (A.to_hex(cur) if cur is not None else self._s("wave_color_custom"))]
        self._row(ctx, g, self._s("wave_color_mode"), names[mode if 0 <= mode < 3 else 0], self._icon("msg_blur_radial", "msg_settings"),
                  None, lambda v: self._letter_color_sheet(ctx))
        self._r_color(ctx, g, "wave_active_hex", ("msg_addbio", "msg_settings"), True,
                      self._theme_color(Theme.key_windowBackgroundWhiteBlueText, THEME_BLUE))
        g = self._sec(ctx, c, self._s("wave_sec_font"))
        self._r_font(ctx, g)
        self._r_switch(ctx, g, "wave_letters3d", False, ("msg_photo_text_framed3", "msg_settings"))
        self._r_switch(ctx, g, "wave_shadow", False, ("gradient_left", "msg_settings"))

    def _tab_motion(self, ctx, c, rr):
        g = self._sec(ctx, c, self._s("wave_section_motion"))
        for key, d, lo, hi, unit, ic, st in (
                ("wave_amp", 56, 0, 140, "dp", "media_flip", 1), ("wave_sigma", 62, 20, 180, "dp", "msg_blur_radial", 1),
                ("wave_scale", 90, 0, 220, "%", "pip_video_expand", 1), ("wave_reveal", 160, 50, 320, "%", "msg_stories_views", 1),
                ("wave_stiffness", 320, 80, 1000, "", "gradient_left", 10), ("wave_damping", 55, 20, 100, "%", "msg_played_remix", 1),
                ("wave_bounce", 38, 12, 100, "%", "msg_played_remix", 1)):
            self._r_slider(ctx, g, key, d, lo, hi, unit, (ic, "msg_settings"), st)

    def _tab_haptic(self, ctx, c, rr):
        ic = ("msg_vibration", "msg_settings")
        g = self._sec(ctx, c, self._s("wave_section_haptic"))
        self._r_switch(ctx, g, "wave_haptic", True, ic)
        self._r_choice(ctx, g, "wave_haptic_style", 0, ["wave_hs_knock", "wave_hs_ratchet", "wave_hs_heavy"], ic)
        self._r_slider(ctx, g, "wave_haptic_strength", 100, 10, 100, "%", ic)
        self._r_slider(ctx, g, "wave_haptic_len", 11, 4, 30, "ms", ic)
        self._r_slider(ctx, g, "wave_haptic_gap", 20, 6, 60, "ms", ic)
        self._r_switch(ctx, g, "wave_haptic_release", False, ic)

    def _tab_filter(self, ctx, c, rr):
        ic = ("msg_folder_remix", "msg_settings")
        g = self._sec(ctx, c, self._s("wave_section_filter"))
        self._r_switch(ctx, g, "wave_filter", True, ic)
        self._r_choice(ctx, g, "wave_match", 0, ["wave_match_first", "wave_match_word"], ("msg_photo_text2", "msg_settings"))
        self._r_switch(ctx, g, "wave_badge", True, ("msg_stories_views", "msg_settings"))
        self._r_switch(ctx, g, "wave_in_archive", False, ic)
        g = self._sec(ctx, c, self._s("wave_lab_filter") + " · " + self._s("wave_anim_style"))
        self._r_choice(ctx, g, "wave_anim_style", 0, ["wave_anim_3d", "wave_anim_slide", "wave_anim_fade"], ("media_flip", "msg_settings"))
        self._r_slider(ctx, g, "wave_3d_angle", 32, 0, 70, "°", ("media_flip", "msg_settings"))
        self._r_slider(ctx, g, "wave_3d_depth", 22, 0, 60, "%", ("pip_video_expand", "msg_settings"))
        self._r_slider(ctx, g, "wave_dissolve", 0, 0, 500, "ms", ("msg_played_remix", "msg_settings"), 10)
        self._r_slider(ctx, g, "wave_stagger", 10, 0, 80, "ms", ("msg_played_remix", "msg_settings"))
        g = self._sec(ctx, c, None)
        ri = ("msg_inputarrow", "msg_settings")
        self._r_switch(ctx, g, "wave_reset_tap", True, ri)
        self._r_switch(ctx, g, "wave_reset_swipe", True, ri)

    def _tab_alpha(self, ctx, c, rr):
        p = self._pal()
        ic = ("msg_photo_text2", "msg_settings")
        lang = self._alpha_lang()
        xs = self.cfg_bool("wave_xscript", True)
        if lang == 0:
            letter, names = "Б", (["Брат", "Бро", "Britan"] if xs else ["Брат", "Бро"])
        else:
            letter, names = "B", (["Britan", "Брат", "Бро"] if xs else ["Britan"])
        big = self._tv(ctx, letter, 26, p["ink"], True, wrap=False)
        big.setGravity(Gravity.CENTER)
        big.setBackground(self._rr(p["acc"], 16))
        g = self._sec(ctx, c, None)
        self._row(ctx, g, "  ·  ".join(names), self._s("wave_alpha_demo"), None, None, None, big)
        g = self._sec(ctx, c, self._s("wave_sec_alpha"))
        self._r_choice(ctx, g, "wave_alpha_lang", 0, ["wave_lang_ru", "wave_lang_en"], ic, on=lambda k: rr(),
                       get=self._alpha_lang, put=lambda k: self.set_setting("wave_alpha_lang", int(k)))
        self._r_switch(ctx, g, "wave_xscript", True, ic, on=lambda v: rr())
        self._r_switch(ctx, g, "wave_alpha_hash", True, ic, on=lambda v: rr())
        if self.cfg_bool("wave_alpha_hash", True):
            self._r_choice(ctx, g, "wave_hash_pos", 0, ["wave_pos_top", "wave_pos_bottom"], ic)
        self._r_slider(ctx, g, "wave_size", 15, 10, 26, "sp", ("msg_photo_text_framed3", "msg_settings"))
        self._r_pins(ctx, c)
        opened = bool(getattr(self, "_adv_open", False))
        g = self._sec(ctx, c, None)

        def toggle(v):
            self._adv_open = not opened
            rr()
        self._row(ctx, g, self._s("wave_adv"), None, None, self._tv(ctx, "▴" if opened else "▾", 16, p["sub"], False, wrap=False), toggle)
        if opened:
            self._r_choice(ctx, g, "wave_alpha_case", 0, ["wave_case_upper", "wave_case_lower"], ic)
            self._r_slider(ctx, g, "wave_gap", 0, -6, 60, "dp", ic)
            self._r_slider(ctx, g, "wave_pad", 10, 0, 80, "dp", ic)
            self._r_choice(ctx, g, "wave_align", 0, ["wave_align_center", "wave_align_top", "wave_align_bottom"], ic)
