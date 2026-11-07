import sys
import os

try:
    __file__
except NameError:
    try:
        __file__ = file
    except NameError:
        __file__ = ""

try:
    file
except NameError:
    file = __file__

try:
    src_dir = os.path.dirname(os.path.abspath(__file__)) if __file__ else os.path.abspath(".")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
except Exception:
    pass

PLUGIN_DIR = "wave"


def find_plugin_file(subpath):
    if not subpath:
        return ""
    sub = str(subpath).replace("\\", "/").strip("/")
    candidates = []

    for mod_name in (__name__,):
        try:
            mod = sys.modules.get(mod_name)
            if mod and getattr(mod, "__file__", None):
                curr = os.path.abspath(mod.__file__)
                for _ in range(7):
                    curr = os.path.dirname(curr)
                    candidates.append(os.path.join(curr, sub))
                    candidates.append(os.path.join(curr, PLUGIN_DIR, sub))
        except Exception:
            pass

    try:
        if __file__:
            curr = os.path.abspath(__file__)
            for _ in range(7):
                curr = os.path.dirname(curr)
                candidates.append(os.path.join(curr, sub))
                candidates.append(os.path.join(curr, PLUGIN_DIR, sub))
    except Exception:
        pass

    try:
        cwd = os.getcwd()
        candidates.append(os.path.join(cwd, sub))
        candidates.append(os.path.join(cwd, PLUGIN_DIR, sub))
        candidates.append(os.path.join(cwd, "plugins", PLUGIN_DIR, sub))
        candidates.append(os.path.join(cwd, "plugins", "ElyxPlugins", PLUGIN_DIR, PLUGIN_DIR, sub))
    except Exception:
        pass

    try:
        from org.telegram.messenger import ApplicationLoader
        fdir = str(ApplicationLoader.getFilesDirFixed().getAbsolutePath())
        candidates.append(os.path.join(fdir, "plugins", "ElyxPlugins", PLUGIN_DIR, PLUGIN_DIR, sub))
        candidates.append(os.path.join(fdir, "plugins", "ElyxPlugins", PLUGIN_DIR, sub))
        candidates.append(os.path.join(fdir, "plugins", PLUGIN_DIR, PLUGIN_DIR, sub))
        candidates.append(os.path.join(fdir, "plugins", PLUGIN_DIR, sub))
        candidates.append(os.path.join(fdir, PLUGIN_DIR, sub))
    except Exception:
        pass

    for cand in candidates:
        try:
            if cand and os.path.exists(cand):
                return os.path.abspath(cand)
        except Exception:
            pass
    return sub


try:
    _src_dir = find_plugin_file("src")
    if _src_dir and os.path.isdir(_src_dir) and _src_dir not in sys.path:
        sys.path.insert(0, _src_dir)
except Exception:
    pass


import json
import re
import threading
import time

from base_plugin import BasePlugin, HookResult, HookStrategy, MethodHook, MenuItemData, MenuItemType
from com.exteragram.messenger.plugins import PluginsController
from com.exteragram.messenger.plugins.ui import PluginSettingsActivity
from client_utils import get_last_fragment
import android_utils
from android_utils import run_on_ui_thread, OnClickListener

log = android_utils.log
try:
    from wave_addons.Diag import log
    from wave_addons import Diag
except Exception:
    try:
        from .wave_addons.Diag import log
        from .wave_addons import Diag
    except Exception:
        Diag = None
from hook_utils import find_class
from java import dynamic_proxy, jarray, jbyte, jclass
from ui.settings import Divider, Selector, Switch, Text
from ui.bulletin import BulletinHelper
from ui.alert import AlertDialogBuilder


def _safe_cls(cls):
    name = getattr(cls, "__name__", "item").lower()

    def make(**kw):
        obj = None
        last = None
        for drop in ((), ("on_change",), ("on_change", "subtext"), ("on_change", "subtext", "icon")):
            try:
                obj = cls(**{k: v for k, v in kw.items() if k not in drop})
                break
            except TypeError as e:
                last = e
        if obj is None:
            raise last
        for k, v in kw.items():
            try:
                if not hasattr(obj, k):
                    setattr(obj, k, v)
            except Exception:
                pass
        try:
            obj._wave_kind = name
        except Exception:
            pass
        return obj
    return make


Selector = _safe_cls(Selector)
Switch = _safe_cls(Switch)
Text = _safe_cls(Text)


def _guard_page(fn):
    import functools

    @functools.wraps(fn)
    def wrapped(self, *a, **k):
        try:
            return fn(self, *a, **k)
        except Exception as e:
            log("[Wave] page %s: %s" % (fn.__name__, e))
            try:
                self._toast("Wave: %s" % str(e)[:90], error=True)
            except Exception:
                pass
            return [Divider(text=str(e)[:60])]
    return wrapped

try:
    from android.view import Gravity, View
    from android.widget import EditText, FrameLayout, ImageView, LinearLayout, PopupWindow, ScrollView, TextView
    from android.graphics.drawable import GradientDrawable
    from android.graphics import BitmapFactory, PorterDuff, PorterDuffColorFilter
    from android.util import TypedValue
    from org.telegram.messenger import ApplicationLoader, AndroidUtilities, LocaleController
    from org.telegram.ui.ActionBar import BottomSheet, Theme
    from org.telegram.ui.Components import UItem
except Exception:
    pass

try:
    from elyx import strings as elyx_strings
except Exception:
    elyx_strings = None

__id__ = "wave"
__name__ = "Wave"
__description__ = "Alphabet scroller for the chat list"
__author__ = "@lyzos, @LuPlugins"
__version__ = "1.0.0"
__min_version__ = "12.10.6"
__sdk_version__ = "1.4.3.2"

SUPPORT_USERNAME = "LuPlugins"
DEV_USERNAMES = ("lyzos", "LuPlugins")


def _load_locale_strings():
    out = {}
    for lang, filename in (("en", "strings_en.json"), ("ru", "strings_ru.json")):
        try:
            path = find_plugin_file(os.path.join("locales", filename))
            if path and os.path.exists(path):
                with open(path, "r", encoding="utf-8-sig") as fh:
                    data = json.load(fh)
                if isinstance(data, dict):
                    out[lang] = data
        except Exception:
            pass
    return out


LOCALE_STRINGS = _load_locale_strings()


class WaveSettingsHeaderHook(MethodHook):

    SUB_TABS = {
        "create_look_options": 0,
        "create_motion_options": 1,
        "create_alpha_options": 4,
        "create_haptic_options": 2,
        "create_filter_options": 3,
    }

    def __init__(self, plugin):
        self.plugin = plugin

    def after_hooked_method(self, param):
        try:
            activity = param.thisObject
            items = param.args[0]
            if activity is None or items is None:
                return
            plugin_obj = self.plugin._field(activity, "plugin")
            if plugin_obj is None or str(plugin_obj.getId()) != __id__:
                return
            ctx = activity.getContext()
            callback = self.plugin._field(activity, "createSubFragmentCallback")
            if callback is not None:
                self.plugin._replace_sub_page(ctx, items, callback)
                return
            header = self.plugin._settings_profile_header(ctx)
            if header is None:
                return
            for idx, view in ((0, header), (1, self.plugin._settings_status_card(ctx))):
                if view is None:
                    continue
                it = UItem.asCustom(view)
                try:
                    it.setTransparent(True)
                except Exception:
                    pass
                items.add(idx, it)
            footer = self.plugin._settings_footer(ctx)
            if footer:
                f_item = UItem.asCustom(footer)
                try:
                    f_item.setTransparent(True)
                except Exception:
                    pass
                items.add(f_item)
        except Exception as e:
            log("[Wave] Header hook error: " + str(e))


try:
    from wave_rest.core.WaveEngine import WaveEngineCore
    from wave_rest.ui.Home import HomeHeroUI
    from wave_rest.ui.WaveUI import WaveLabUI, LabSlider
except Exception:
    try:
        from .wave_rest.core.WaveEngine import WaveEngineCore
        from .wave_rest.ui.Home import HomeHeroUI
        from .wave_rest.ui.WaveUI import WaveLabUI, LabSlider
    except Exception as _imp_err:
        log("[Wave] core import failed: {0}".format(_imp_err))

        class WaveEngineCore:
            pass

        class HomeHeroUI:
            pass

        class WaveLabUI:
            pass

        class LabSlider:
            pass

try:
    from wave_addons import Alpha as AlphaLogic
except Exception:
    from .wave_addons import Alpha as AlphaLogic

try:
    from wave_addons.ListFilter import ListFilter
except Exception:
    try:
        from .wave_addons.ListFilter import ListFilter
    except Exception:
        ListFilter = None


class WavePlugin(BasePlugin, WaveEngineCore, HomeHeroUI, WaveLabUI):
    def __init__(self):
        super().__init__()
        self._hooks = []
        self._overlays = {}
        self._demos = []
        self._known = {}
        self._settings_header_hook = None
        self._field_cache = {}
        self._filter = ListFilter(self) if ListFilter else None
        self._cur_tab = None

    def on_plugin_load(self):
        try:
            src = os.path.dirname(os.path.abspath(__file__))
            if src not in sys.path:
                sys.path.insert(0, src)
        except Exception:
            pass
        try:
            try:
                from wave_addons import Brand as _Brand
            except Exception:
                from .wave_addons import Brand as _Brand
            _Brand.FINDER = find_plugin_file
        except Exception:
            pass
        try:
            self._setup_settings_header()
        except Exception as e:
            log("[Wave] settings header: {0}".format(e))
        try:
            if str(self.get_setting("wave_ui_v", "")) != "3":
                self.set_setting("wave_dissolve", 0)
                self.set_setting("wave_stagger", 10)
                self.set_setting("wave_ui_v", "3")
        except Exception:
            pass
        self._install_hooks()
        try:
            self._install_font_hook()
        except Exception as e:
            log("[Wave] font hook: {0}".format(e))
        run_on_ui_thread(lambda: self._attach_existing(True), 400)

    def on_plugin_unload(self):
        try:
            self._detach_all()
        except Exception:
            pass
        for hook in list(self._hooks or []):
            try:
                self.unhook_method(hook)
            except Exception:
                pass
        self._hooks = []
        self._settings_header_hook = None

    def on_resume(self, activity):
        try:
            if str(activity.getClass().getName()).endswith("LaunchActivity"):
                if not self._overlays:
                    run_on_ui_thread(self._attach_existing, 150)
        except Exception:
            pass

    def _click(self, fn):
        return OnClickListener(fn)

    def _context(self):
        try:
            return ApplicationLoader.applicationContext
        except Exception:
            return None

    def _s(self, key, fallback=None):
        try:
            lang = self._language_code()
            if not LOCALE_STRINGS:
                LOCALE_STRINGS.update(_load_locale_strings())
            table = LOCALE_STRINGS.get(lang) or LOCALE_STRINGS.get("en") or {}
            if key in table:
                return str(table[key])
            fb = LOCALE_STRINGS.get("en") or {}
            if key in fb:
                return str(fb[key])
        except Exception:
            pass
        try:
            if elyx_strings is not None and hasattr(elyx_strings, key):
                return str(getattr(elyx_strings, key))
        except Exception:
            pass
        return fallback if fallback else key

    def _client_lang(self):
        raw = ""
        try:
            info = LocaleController.getInstance().getCurrentLocaleInfo()
            if info is not None:
                raw = str(getattr(info, "shortName", "") or getattr(info, "pluralLangCode", "") or "").strip().lower()
        except Exception:
            raw = ""
        if not raw:
            try:
                raw = str(LocaleController.getInstance().getCurrentLocale().getLanguage() or "").lower()
            except Exception:
                raw = ""
        return "ru" if raw.replace("-", "_").startswith("ru") else "en"

    def _language_code(self):
        try:
            idx = int(self.get_setting("wave_language", 0) or 0)
        except Exception:
            idx = 0
        if idx == 1:
            return "en"
        if idx == 2:
            return "ru"
        return self._client_lang()

    def _field(self, obj, name):
        try:
            clazz = obj.getClass()
            cache_key = (clazz.getName(), name)
            field = self._field_cache.get(cache_key)
            if field is None:
                curr = clazz
                while curr is not None:
                    try:
                        field = curr.getDeclaredField(name)
                        field.setAccessible(True)
                        self._field_cache[cache_key] = field
                        break
                    except Exception:
                        curr = curr.getSuperclass()
            if field is not None:
                return field.get(obj)
        except Exception:
            pass
        return None

    def _telegram_drawable_id(self, *names):
        try:
            fragment = get_last_fragment()
            ctx = fragment.getParentActivity() if fragment is not None and hasattr(fragment, "getParentActivity") else self._context()
            if ctx is not None:
                for name in names:
                    try:
                        rid = ctx.getResources().getIdentifier(str(name), "drawable", ctx.getPackageName())
                        if rid:
                            return int(rid)
                    except Exception:
                        pass
        except Exception:
            pass
        return 0

    def _icon(self, *names):
        for n in names:
            if self._telegram_drawable_id(n):
                return n
        return names[-1] if names else "msg_settings"

    def _dp(self, value):
        try:
            return int(AndroidUtilities.dp(float(value)))
        except Exception:
            return int(value)

    def _c(self, hex_val):
        hex_val = int(hex_val)
        return hex_val - 0x100000000 if hex_val > 0x7FFFFFFF else hex_val

    def _color(self, hex_val):
        return self._c(hex_val)

    def _theme_color(self, key, fallback):
        try:
            return self._c(Theme.getColor(key))
        except Exception:
            return self._c(fallback)

    def _is_dark_theme(self):
        try:
            bg = self._theme_color(Theme.key_windowBackgroundWhite, 0xFFFFFFFF) & 0xFFFFFF
            r, g, b = (bg >> 16) & 0xFF, (bg >> 8) & 0xFF, bg & 0xFF
            return (r * 299 + g * 587 + b * 114) < 128000
        except Exception:
            return True

    def _bg(self, color, radius=16, stroke_color=None, stroke_width=0):
        try:
            d = GradientDrawable()
            d.setColor(self._color(color))
            d.setCornerRadius(float(self._dp(radius)))
            if stroke_color is not None and int(stroke_width or 0) > 0:
                d.setStroke(self._dp(stroke_width), self._color(stroke_color))
            return d
        except Exception:
            return None

    def _set_bg(self, view, color, radius=16, stroke_color=None, stroke_width=0):
        try:
            bg = self._bg(color, radius, stroke_color, stroke_width)
            if bg is not None:
                view.setBackground(bg)
        except Exception:
            pass

    def _text_view(self, ctx, text, size, color, bold=False):
        try:
            tv = TextView(ctx)
            tv.setText(str(text or ""))
            tv.setTextSize(float(size))
            tv.setTextColor(self._color(color))
            if bold:
                try:
                    tv.getPaint().setFakeBoldText(True)
                except Exception:
                    pass
            return tv
        except Exception:
            return None

    def _steady_custom_text(self, tv, max_lines=1, size=None):
        try:
            if tv is None:
                return tv
            if size is not None:
                tv.setTextSize(TypedValue.COMPLEX_UNIT_DIP, float(size))
            tv.setMaxLines(int(max_lines))
            if int(max_lines) == 1:
                tv.setSingleLine(True)
            tv.setEllipsize(jclass("android.text.TextUtils$TruncateAt").END)
        except Exception:
            pass
        return tv

    def _argb(self, a, r, g, b):
        return (int(a) << 24) | (int(r) << 16) | (int(g) << 8) | int(b)

    def _mix_rgb(self, color, target, amount):
        c = int(color) & 0xFFFFFF
        t = int(target) & 0xFFFFFF
        out = 0
        for sh in (16, 8, 0):
            a = (c >> sh) & 0xFF
            b = (t >> sh) & 0xFF
            out |= int(a + (b - a) * amount) << sh
        return 0xFF000000 | out

    def _set_text_button(self, view, primary=False, danger=False):
        dark = self._is_dark_theme()
        if danger:
            color = self._theme_color(getattr(Theme, "key_text_RedRegular", "text_RedRegular"), 0xFFE85B5B)
            view.setTextColor(color)
            self._set_bg(view, 0x18E85B5B if dark else 0x10E85B5B, 12)
            return
        if primary:
            view.setTextColor(self._color(0xFFFFFFFF))
            self._set_bg(view, self._theme_color(Theme.key_featuredStickers_addButton, 0xFF3F8FE5), 12)
            return
        view.setTextColor(self._theme_color(Theme.key_windowBackgroundWhiteBlackText, 0xFFFFFFFF if dark else 0xFF1D1F24))
        self._set_bg(view, 0x20FFFFFF if dark else 0xFFF1F3F6, 12, 0x1A000000 if not dark else None, 1 if not dark else 0)

    def _setup_settings_header(self):
        if self._settings_header_hook is not None:
            return
        PSA = jclass("com.exteragram.messenger.plugins.ui.PluginSettingsActivity")
        method = PSA.getClass().getDeclaredMethod(
            "fillItems",
            jclass("java.util.ArrayList"),
            jclass("org.telegram.ui.Components.UniversalAdapter"),
        )
        method.setAccessible(True)
        self._settings_header_hook = self.hook_method(method, WaveSettingsHeaderHook(self))
        self._hooks.append(self._settings_header_hook)

    def _replace_sub_page(self, ctx, items, callback):
        tab = None
        try:
            tab = WaveSettingsHeaderHook.SUB_TABS.get(str(getattr(callback, "__name__", "") or ""))
        except Exception:
            tab = None
        if tab is None and self._cur_tab is not None:
            tab = self._cur_tab[0]
        if tab is None:
            log("[Wave] sub page: tab not resolved")
            return
        try:
            wrap = LinearLayout(ctx)
            wrap.setOrientation(LinearLayout.VERTICAL)
            card = self._settings_status_card(ctx)
            if card is not None:
                wrap.addView(card)
            wrap.addView(self._lab_page(ctx, tab))
            it = UItem.asCustom(wrap)
            try:
                it.setTransparent(True)
            except Exception:
                pass
            items.clear()
            items.add(it)
        except Exception as e:
            log("[Wave] sub page: {0}".format(e))

    def _set_and_reload(self, key, value):
        self.set_setting(key, value)
        self.reload_settings()

    def reload_settings(self):
        try:
            from org.telegram.ui import LaunchActivity
            activity = ApplicationLoader.getCurrentActivity()
            if isinstance(activity, LaunchActivity):
                layout = activity.getActionBarLayout()
                fragment = layout.getLastFragment() if layout else None
                if fragment:
                    try:
                        if hasattr(fragment, "rebuildAllItems"):
                            fragment.rebuildAllItems()
                    except Exception:
                        pass
                    try:
                        adapter = self._field(fragment, "listAdapter")
                        if adapter is not None and hasattr(adapter, "notifyDataSetChanged"):
                            adapter.notifyDataSetChanged()
                    except Exception:
                        pass
        except Exception:
            pass

    def _open_settings(self):
        try:
            plugin = PluginsController.getInstance().plugins.get(self.id)
            fragment = get_last_fragment()
            if plugin is not None and fragment is not None:
                fragment.presentFragment(PluginSettingsActivity(plugin))
        except Exception as e:
            log("[Wave] open settings: {0}".format(e))

    def _reopen_settings_after_language_change(self):
        def reopen():
            try:
                plugin = PluginsController.getInstance().plugins.get(self.id)
                fragment = get_last_fragment()
                if plugin is None or fragment is None:
                    return
                try:
                    fragment.finishFragment(False)
                except Exception:
                    pass

                def present_again():
                    try:
                        layout = ApplicationLoader.getCurrentActivity().getActionBarLayout()
                        host = layout.getLastFragment() if layout is not None else None
                        if host is not None:
                            host.presentFragment(PluginSettingsActivity(plugin))
                    except Exception:
                        pass
                run_on_ui_thread(present_again, 80)
            except Exception:
                self.reload_settings()
        run_on_ui_thread(reopen)

    def _show_language_menu(self, anchor):
        if anchor is None:
            return
        try:
            ctx = anchor.getContext()
            dark = self._is_dark_theme()
            root = LinearLayout(ctx)
            root.setOrientation(LinearLayout.VERTICAL)
            root.setPadding(self._dp(8), self._dp(8), self._dp(8), self._dp(8))
            self._set_bg(root, 0xFF1D2733 if dark else 0xFFFFFFFF, 12, 0x22000000 if not dark else None, 1 if not dark else 0)
            popup = PopupWindow(root, self._dp(118), -2, True)
            current = int(self.get_setting("wave_language", 0) or 0)
            for idx, label in enumerate(("Auto", "EN", "RU")):
                item = TextView(ctx)
                item.setText(label)
                item.setTextSize(14)
                item.setGravity(Gravity.CENTER)
                item.setTypeface(None, 1 if idx == current else 0)
                item.setTextColor(self._theme_color(Theme.key_windowBackgroundWhiteBlackText, 0xFFFFFFFF if dark else 0xFF1D1F24))
                item.setPadding(self._dp(12), self._dp(9), self._dp(12), self._dp(9))
                if idx == current:
                    self._set_bg(item, 0x223F8FE5, 8)
                item.setOnClickListener(OnClickListener(lambda v, i=idx: self._set_language_from_menu(i, popup)))
                lp = LinearLayout.LayoutParams(-1, -2)
                if idx:
                    lp.setMargins(0, self._dp(4), 0, 0)
                root.addView(item, lp)
            popup.setOutsideTouchable(True)
            popup.showAsDropDown(anchor, -self._dp(76), self._dp(4))
        except Exception as e:
            log("[Wave] language menu: {0}".format(e))

    def _set_language_from_menu(self, idx, popup=None):
        try:
            self.set_setting("wave_language", int(idx or 0))
            if popup is not None:
                popup.dismiss()
        except Exception:
            pass
        self._reopen_settings_after_language_change()

    def _on_cfg(self, *_):
        self._refresh_overlays()

    def _on_cfg_reload(self, *_):
        self._refresh_overlays()
        self.reload_settings()

    def _guard_item(fn):
        import functools

        @functools.wraps(fn)
        def wrapped(self, *a, **k):
            try:
                return fn(self, *a, **k)
            except Exception as e:
                log("[Wave] item {0}: {1}".format(a[0] if a else "?", e))
                return None
        return wrapped

    @_guard_item
    def _sw(self, key, default, icon, reload=False):
        return Switch(key=key, text=self._s(key), subtext=self._s(key + "_sub"), default=default,
                      icon=self._icon(*icon), on_change=self._on_cfg_reload if reload else self._on_cfg)

    @_guard_item
    def _sel(self, key, default, items, icon, reload=False):
        return Selector(key=key, text=self._s(key), subtext=self._s(key + "_sub"), default=default,
                        items=[self._s(i) for i in items], icon=self._icon(*icon),
                        on_change=self._on_cfg_reload if reload else self._on_cfg)

    @_guard_item
    def _sl(self, key, default, lo, hi, unit, icon, step=1):
        return LabSlider(key, self._s(key), self._s(key + "_sub"), default, lo, hi, unit, self._icon(*icon), step)

    @_guard_item
    def _hex(self, key, icon):
        cur = str(self.get_setting(key, "") or "")
        return Text(text=self._s(key), subtext=cur or self._s("wave_hex_auto"), icon=self._icon(*icon),
                    on_click=lambda v: run_on_ui_thread(lambda: self._show_hex_sheet(key)))

    def _look_items(self):
        items = [
            self._sel("wave_side", 0, ["wave_side_right", "wave_side_left"], ("pip_video_expand", "msg_settings")),
            self._sel("wave_font", 2, [k for k, _, _ in AlphaLogic.FONTS], ("msg_photo_text_framed3", "msg_settings")),
            self._sel("wave_color_mode", 0, ["wave_color_text", "wave_color_accent", "wave_color_custom"],
                      ("msg_blur_radial", "msg_settings"), reload=True),
        ]
        if self.cfg_int("wave_color_mode", 0) == 2:
            items.append(self._hex("wave_color_hex", ("msg_addbio", "msg_settings")))
        items.append(self._hex("wave_active_hex", ("msg_addbio", "msg_settings")))
        items.append(self._sw("wave_letters3d", False, ("msg_photo_text_framed3", "msg_settings")))
        items.append(self._sw("wave_shadow", False, ("gradient_left", "msg_settings")))
        items.append(self._sl("wave_zone", 32, 16, 80, "dp", ("photo_rectangle", "msg_settings")))
        items.append(self._sl("wave_idle", 0, 0, 60, "%", ("msg_stories_views", "msg_settings")))
        items.append(self._sw("wave_auto_inset", True, ("pip_video_expand", "msg_settings"), reload=True))
        if not self.cfg_bool("wave_auto_inset", True):
            items.append(self._sl("wave_inset_top", 120, 0, 260, "dp", ("pip_video_expand", "msg_settings")))
            items.append(self._sl("wave_inset_bottom", 96, 0, 260, "dp", ("pip_video_expand", "msg_settings")))
        return items

    def _alpha_items(self):
        ic = ("msg_photo_text2", "msg_settings")
        items = [
            self._sel("wave_alpha_lang", self._alpha_lang(), ["wave_lang_ru", "wave_lang_en"], ic, reload=True),
            self._sw("wave_xscript", True, ic),
            self._sw("wave_alpha_hash", True, ic, reload=True),
        ]
        if self.cfg_bool("wave_alpha_hash", True):
            items.append(self._sel("wave_hash_pos", 0, ["wave_pos_top", "wave_pos_bottom"], ic))
        items.append(self._sl("wave_size", 15, 10, 26, "sp", ("msg_photo_text_framed3", "msg_settings")))
        return items

    def _motion_items(self):
        return [
            self._sl("wave_amp", 56, 0, 140, "dp", ("media_flip", "msg_settings")),
            self._sl("wave_sigma", 62, 20, 180, "dp", ("msg_blur_radial", "msg_settings")),
            self._sl("wave_scale", 90, 0, 220, "%", ("pip_video_expand", "msg_settings")),
            self._sl("wave_reveal", 160, 50, 320, "%", ("msg_stories_views", "msg_settings")),
            self._sl("wave_stiffness", 320, 80, 1000, "", ("gradient_left", "msg_settings"), 10),
            self._sl("wave_damping", 55, 20, 100, "%", ("msg_played_remix", "msg_settings")),
            self._sl("wave_bounce", 38, 12, 100, "%", ("msg_played_remix", "msg_settings")),
        ]

    def _haptic_items(self):
        items = [
            self._sw("wave_haptic", True, ("msg_vibration", "msg_settings"), reload=True),
            self._sel("wave_haptic_style", 0, ["wave_hs_knock", "wave_hs_ratchet", "wave_hs_heavy"], ("msg_vibration", "msg_settings")),
            self._sl("wave_haptic_strength", 100, 10, 100, "%", ("msg_vibration", "msg_settings")),
            self._sl("wave_haptic_len", 11, 4, 30, "ms", ("msg_vibration", "msg_settings")),
            self._sl("wave_haptic_gap", 20, 6, 60, "ms", ("msg_vibration", "msg_settings")),
            self._sw("wave_haptic_release", False, ("msg_vibration", "msg_settings")),
        ]
        return items

    def _filter_items(self):
        return [
            self._sw("wave_filter", True, ("msg_folder_remix", "msg_settings")),
            self._sel("wave_match", 0, ["wave_match_first", "wave_match_word"], ("msg_photo_text2", "msg_settings")),
            self._sel("wave_anim_style", 0, ["wave_anim_3d", "wave_anim_slide", "wave_anim_fade"], ("media_flip", "msg_settings")),
            self._sl("wave_3d_angle", 32, 0, 70, "°", ("media_flip", "msg_settings")),
            self._sl("wave_3d_depth", 22, 0, 60, "%", ("pip_video_expand", "msg_settings")),
            self._sl("wave_dissolve", 0, 0, 500, "ms", ("msg_played_remix", "msg_settings"), 10),
            self._sl("wave_stagger", 10, 0, 80, "ms", ("msg_played_remix", "msg_settings")),
            self._sw("wave_reset_tap", True, ("msg_inputarrow", "msg_settings")),
            self._sw("wave_reset_swipe", True, ("msg_inputarrow", "msg_settings")),
            self._sw("wave_badge", True, ("msg_stories_views", "msg_settings")),
            self._sw("wave_in_archive", False, ("msg_folder_remix", "msg_settings")),
        ]

    def _native(self, items):
        out = []
        for it in items:
            if it is None:
                continue
            if isinstance(it, LabSlider):
                out.append(Text(text=it.text, subtext="{0} {1}".format(self._slider_value(it), it.unit).strip(),
                                icon=it.icon, on_click=lambda v, i=it: run_on_ui_thread(lambda: self._show_slider_sheet(i))))
            else:
                out.append(it)
        return out

    @_guard_page
    def create_settings(self):
        lang = self._language_code()
        return [
            Switch(key="wave_enabled", text=self._s("wave_enabled"), subtext=self._s("wave_enabled_sub"), default=True,
                   icon=self._icon("msg_noise_on_solar", "msg_settings"), on_change=self._on_cfg),
            Divider(),
            Text(text=self._s("wave_entry_look"), icon=self._icon("msg_photo_text_framed3", "msg_settings"),
                 subtext=self._s("wave_entry_look_sub"), create_sub_fragment=self.create_look_options, link_alias="look_entry_" + lang),
            Text(text=self._s("wave_entry_alpha"), icon=self._icon("msg_photo_text2", "msg_settings"),
                 subtext=self._s("wave_entry_alpha_sub"), create_sub_fragment=self.create_alpha_options, link_alias="alpha_entry_" + lang),
            Text(text=self._s("wave_entry_motion"), icon=self._icon("media_flip", "msg_settings"),
                 subtext=self._s("wave_entry_motion_sub"), create_sub_fragment=self.create_motion_options, link_alias="motion_entry_" + lang),
            Text(text=self._s("wave_entry_haptic"), icon=self._icon("msg_vibration", "msg_settings"),
                 subtext=self._s("wave_entry_haptic_sub"), create_sub_fragment=self.create_haptic_options, link_alias="haptic_entry_" + lang),
            Text(text=self._s("wave_entry_filter"), icon=self._icon("msg_folder_remix", "msg_settings"),
                 subtext=self._s("wave_entry_filter_sub"), create_sub_fragment=self.create_filter_options, link_alias="filter_entry_" + lang),
            Divider(),
            Text(text=self._s("wave_reset_filter"), icon=self._icon("msg_inputarrow", "msg_settings"), subtext=self._s("wave_reset_filter_sub"),
                 accent=True, on_click=lambda v: self._reset_all_filters(True)),
            Text(text=self._s("wave_reset_all"), icon=self._icon("msg_delete", "msg_settings"), subtext=self._s("wave_reset_all_sub"),
                 red=True, on_click=lambda v: run_on_ui_thread(lambda: self._confirm_reset_all())),
            Divider(),
        ]

    @_guard_page
    def create_look_options(self):
        self._cur_tab = (0, time.time())
        return [Divider(text=self._s("wave_section_look"))] + self._native(self._look_items()) + [Divider()]

    @_guard_page
    def create_alpha_options(self):
        self._cur_tab = (4, time.time())
        return [Divider(text=self._s("wave_section_alpha"))] + self._native(self._alpha_items()) + [Divider()]

    @_guard_page
    def create_motion_options(self):
        self._cur_tab = (1, time.time())
        return [Divider(text=self._s("wave_section_motion"))] + self._native(self._motion_items()) + [Divider()]

    @_guard_page
    def create_haptic_options(self):
        self._cur_tab = (2, time.time())
        return [Divider(text=self._s("wave_section_haptic"))] + self._native(self._haptic_items()) + [Divider()]

    @_guard_page
    def create_filter_options(self):
        self._cur_tab = (3, time.time())
        return [Divider(text=self._s("wave_section_filter"))] + self._native(self._filter_items()) + [Divider()]

    def _resolve_ctx(self):
        try:
            fragment = get_last_fragment()
            return fragment.getParentActivity() if fragment is not None else None
        except Exception:
            return None

    def _open_username(self, name):
        try:
            from client_utils import get_messages_controller
            frag = get_last_fragment()
            mc = get_messages_controller()
            if mc is not None and frag is not None:
                run_on_ui_thread(lambda: mc.openByUserName(str(name), frag, 1))
        except Exception as e:
            log("[Wave] open @{0}: {1}".format(name, e))

    def _toast(self, text, error=False):
        try:
            (BulletinHelper.show_error if error else BulletinHelper.show_info)(text)
        except Exception:
            pass

    def _show_diag(self):
        try:
            ctx = self._resolve_ctx()
            if ctx is None:
                return
            frs = self._dialogs_fragments()
            text = "dialogs fragments: {0}\noverlays: {1}\n".format(len(frs), len(self._overlays))
            try:
                text += Diag.report()
            except Exception:
                pass
            b = AlertDialogBuilder(ctx)
            b.set_title(self._s("wave_diag"))
            b.set_message(text)

            def flash(builder, which):
                builder.dismiss()
                for ov in list(self._overlays.values()):
                    ov.flash()
            b.set_positive_button(self._s("wave_flash"), flash)
            b.set_negative_button("OK", lambda builder, which: builder.dismiss())
            b.show()
        except Exception as e:
            log("[Wave] diag: {0}".format(e))

    def _reset_all_filters(self, notify=False):
        def run():
            was = False
            try:
                was = self._filter.letter is not None or self._filter.has_pending
            except Exception:
                pass
            for f in self._dialogs_fragments():
                self._filter.request(f, None)
            if notify:
                if was and self.cfg_bool("wave_haptic", True):
                    try:
                        from wave_addons import Haptics
                        Haptics.ratchet(self._resolve_ctx(), 1, 1, 70, 8, 10)
                    except Exception:
                        pass
                self._toast(self._s("wave_filter_cleared" if was else "wave_filter_none"))
        run_on_ui_thread(run)

    def _confirm_reset_all(self):
        try:
            ctx = self._resolve_ctx()
            if ctx is None:
                return
            b = AlertDialogBuilder(ctx)
            b.set_title(self._s("wave_reset_all"))
            b.set_message(self._s("wave_reset_all_warn"))

            def yes(builder, which):
                try:
                    from wave_rest.ui.WaveUI import DEFAULTS
                except Exception:
                    from .wave_rest.ui.WaveUI import DEFAULTS
                for k, dv in DEFAULTS.items():
                    try:
                        self.set_setting(k, dv)
                    except Exception:
                        pass
                try:
                    self.set_setting("wave_alpha_lang", 0 if self._client_lang() == "ru" else 1)
                except Exception:
                    pass
                builder.dismiss()
                self._on_cfg_reload()
            b.set_positive_button(self._s("wave_yes"), yes)
            b.set_negative_button(self._s("wave_cancel"), lambda builder, which: builder.dismiss())
            b.show()
        except Exception as e:
            log("[Wave] reset dialog: {0}".format(e))
