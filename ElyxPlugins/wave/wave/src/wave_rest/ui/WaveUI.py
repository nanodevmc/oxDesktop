try:
    __file__
except NameError:
    try:
        __file__ = file
    except NameError:
        __file__ = ""

from android.view import Gravity, View
from android.widget import FrameLayout, LinearLayout, ScrollView, TextView
from org.telegram.ui.ActionBar import BottomSheet, Theme
from org.telegram.messenger import AndroidUtilities
from android_utils import log, run_on_ui_thread, OnClickListener
try:
    from wave_addons.Diag import log
except Exception:
    pass
from client_utils import get_last_fragment

try:
    from wave_rest.ui.Kit import WaveKit
    from wave_rest.ui.Pages import WavePages
except Exception:
    from .Kit import WaveKit
    from .Pages import WavePages

ACC_D, ACC_L = 0xFFFFB8A6, 0xFFC2553B


DEFAULTS = {
    "wave_enabled": True, "wave_side": 0, "wave_zone": 32, "wave_size": 15, "wave_font": 2, "wave_font_file": "",
    "wave_color_mode": 0, "wave_color_hex": "", "wave_active_hex": "", "wave_idle": 0, "wave_shadow": False,
    "wave_letters3d": False,
    "wave_auto_inset": True, "wave_inset_top": 120, "wave_inset_bottom": 96, "wave_amp": 56, "wave_sigma": 62,
    "wave_scale": 90, "wave_reveal": 160, "wave_stiffness": 320, "wave_damping": 55, "wave_bounce": 38,
    "wave_haptic": True, "wave_haptic_style": 0, "wave_haptic_strength": 100, "wave_haptic_len": 11,
    "wave_haptic_gap": 20, "wave_haptic_release": False, "wave_filter": True, "wave_match": 0,
    "wave_anim_style": 0, "wave_3d_angle": 32, "wave_3d_depth": 22, "wave_dissolve": 0, "wave_stagger": 10,
    "wave_reset_tap": True, "wave_reset_swipe": True, "wave_badge": True, "wave_in_archive": False,
    "wave_xscript": True, "wave_alpha_hash": True, "wave_hash_pos": 0, "wave_pins": "[]",
    "wave_alpha_case": 0, "wave_gap": 0, "wave_pad": 10, "wave_fit": 0, "wave_align": 0,
}


class LabSlider:

    def __init__(self, key, text, subtext, default, lo, hi, unit="", icon="", step=1):
        self.key = key
        self.text = text
        self.subtext = subtext
        self.default = default
        self.min = lo
        self.max = hi
        self.unit = unit
        self.icon = icon
        self.step = max(1, int(step))
        self.on_change = None
        self._wave_kind = "labslider"


class WaveLabUI(WaveKit, WavePages):
    def _acc(self):
        return ACC_D if self._is_dark_theme() else ACC_L

    def _txt_color(self):
        return self._theme_color(Theme.key_windowBackgroundWhiteBlackText, 0xFFFFFFFF if self._is_dark_theme() else 0xFF1D1F24)

    def _gray_color(self):
        return self._theme_color(Theme.key_windowBackgroundWhiteGrayText, 0xFF9AA4B2)

    def _build_setting_view(self, context, item, on_done_refresh):
        try:
            kind = getattr(item, "_wave_kind", None) or type(item).__name__.lower()
            wrap = LinearLayout(context)
            wrap.setOrientation(LinearLayout.VERTICAL)
            g = self._sec(context, wrap, None)
            sub = str(getattr(item, "subtext", "") or "") or None
            if kind == "switch":
                cur = bool(self.get_setting(item.key, item.default))

                def toggled(v):
                    self.set_setting(item.key, bool(v))
                    f = getattr(item, "on_change", None)
                    if f:
                        try:
                            f(bool(v))
                        except Exception:
                            pass
                sw, tap = self._switch(context, cur, toggled)
                self._row(context, g, str(getattr(item, "text", "")), sub, getattr(item, "icon", None), sw, lambda v: tap(sw))
            else:
                self._row(context, g, str(getattr(item, "text", "")), sub, getattr(item, "icon", None))
            return wrap
        except Exception as e:
            log("[Wave] setting cell: {0}".format(e))
            return None

    def _show_lab_sheet(self, context, initial_tab=0):
        try:
            p = self._pal()
            names = (self._s("wave_lab_look"), self._s("wave_lab_motion"), self._s("wave_lab_haptic"),
                     self._s("wave_lab_filter"), self._s("wave_lab_alpha"))

            def build(c, close):
                tabs = []
                bar = LinearLayout(context)
                for label in names:
                    t = TextView(context)
                    t.setText(label)
                    t.setTextSize(1, 13.0)
                    t.setGravity(Gravity.CENTER)
                    t.setSingleLine(True)
                    t.setPadding(self._dp(2), self._dp(9), self._dp(2), self._dp(9))
                    bar.addView(t, LinearLayout.LayoutParams(0, -2, 1.0))
                    tabs.append(t)
                c.addView(bar)
                scroll = ScrollView(context)
                holder = LinearLayout(context)
                holder.setOrientation(1)
                scroll.addView(holder)
                c.addView(scroll, LinearLayout.LayoutParams(-1, min(self._dp(520), int(context.getResources().getDisplayMetrics().heightPixels * 0.66))))

                def update(active):
                    for i, t in enumerate(tabs):
                        t.setTextColor(self._c(p["text"] if i == active else p["sub"]))
                        t.setBackground(self._rr(p["sel"], 18) if i == active else None)
                    holder.removeAllViews()
                    holder.addView(self._lab_page(context, active))
                    try:
                        scroll.scrollTo(0, 0)
                    except Exception:
                        pass
                for i, t in enumerate(tabs):
                    t.setOnClickListener(OnClickListener(lambda v, k=i: update(k)))
                update(int(initial_tab))
            self._sheet(context, None, build)
        except Exception as e:
            log("[Wave] lab sheet: {0}".format(e))

    def _slider_value(self, item):
        try:
            v = int(float(self.get_setting(item.key, item.default)))
        except Exception:
            v = int(item.default)
        return max(int(item.min), min(int(item.max), v))

    def _show_slider_sheet(self, item):
        ctx = self._resolve_ctx()
        if ctx is not None:
            self._slider_sheet(ctx, item.key, item.default, int(item.min), int(item.max), item.unit, item.step)

    def _show_alpha_sheet(self):
        ctx = self._resolve_ctx()
        if ctx is not None:
            self._show_lab_sheet(ctx, 4)
