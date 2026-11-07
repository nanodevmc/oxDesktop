import os
import sys
import time
import threading
import gc
import json
import sqlite3
from typing import List, Dict, Any, Tuple, Optional
from base_plugin import BasePlugin, MethodHook, HookResult, HookStrategy
from .methods import (
    set_pg_instance, get_pg_instance, _tr, run_on_ui_thread, post_ui,
    _ACTIVE_GUARD_INSTANCE, _HOOK_LOCK, _stop_spring_waiting_haptic, find_class
)
from .mixins.scanner_mixin import ScannerMixin
from .mixins.ui_mixin import UIMixin
from .mixins.hook_mixin import HookMixin
from .mixins.cache_mixin import CacheMixin
from .mixins.compat_mixin import CompatMixin
from .mixins.model_mixin import ModelMixin
from .mixins.settings_mixin import SettingsMixin

__id__ = 'plugin_guard'
__name__ = 'Plugin Guard'
__description__ = 'Plugin security scanner. Detects hidden and malicious code via static and vector ML analysis. / Сканер безопасности плагинов с многоуровневым статическим и векторным ML-анализом.'
__author__ = '@dekma0091 && @DefinitelyNotDekma'
__version__ = '2.0'
__icon__ = 'pixelcamera/14'
__min_version__ = '12.10.6'

class PluginGuard(ScannerMixin, UIMixin, HookMixin, CacheMixin, CompatMixin, ModelMixin, SettingsMixin, BasePlugin):

    def __init__(self):
        super().__init__()
        self._installed_hooks = []
        self._current_analyze_btn = None
        self._current_sheet = None
        self._current_chk_box = None
        self.is_model_loaded = False
        self._hash_cache = {}
        self._cache_lock = threading.Lock()
        self._last_scan_stats = {}
        self._cached_ui_classes = None
        self._cached_dex_bridge = None
        self._cached_dex_loader = None
        self._dex_model_loaded_path = None
        self._cached_methods = {}
        self._cached_hook_bridge = None
        self._current_scan_passed = False
        self.is_active = False
        self.is_loading = False
        self.is_stopped = False
        self._dex_lock = threading.Lock()

    def on_plugin_load(self):
        global _ACTIVE_GUARD_INSTANCE
        if _ACTIVE_GUARD_INSTANCE is not None and _ACTIVE_GUARD_INSTANCE is not self:
            try:
                _ACTIVE_GUARD_INSTANCE.on_plugin_unload()
            except Exception:
                pass
        _ACTIVE_GUARD_INSTANCE = self
        with self._dex_lock:
            self.is_stopped = False
            self.is_active = True
        self._timers = []
        self._disable_extera_analysis()
        try:
            from client_utils import run_on_queue
            run_on_queue(self._boot_bg, delay=120)
        except Exception:
            threading.Thread(target=self._boot_bg, daemon=True).start()
        try:
            self.add_on_send_message_hook()
        except Exception as e:
            self.log(f'[PluginGuard DEBUG] add_on_send_message_hook failed: {e}')

    def _boot_bg(self):
        if not getattr(self, 'is_active', False):
            return
        self._preload_resources()
        self._hook_install_ui()

    def _schedule_timer(self, delay, fn):

        def _wrapper():
            if not getattr(self, 'is_active', False):
                return
            post_ui(fn)
        tm = threading.Timer(delay, _wrapper)
        if not hasattr(self, '_timers') or self._timers is None:
            self._timers = []
        self._timers.append(tm)
        tm.start()
        return tm

    def _preload_resources(self):
        if getattr(self, 'is_stopped', False):
            return
        self._check_version_update()
        if getattr(self, 'is_stopped', False):
            return
        self._init_ram_cache()
        if getattr(self, 'is_stopped', False):
            return
        self._ensure_model_downloaded()
        if getattr(self, 'is_stopped', False):
            return
        try:
            self._get_dex_bridge()
        except Exception:
            pass

    def _init_ram_cache(self):
        try:
            db_path = self._get_db_path()
            if os.path.exists(db_path):
                with sqlite3.connect(db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('SELECT sha256, reports_json, stats_json FROM scan_cache ORDER BY timestamp DESC LIMIT 50')
                    loaded = {row[0]: (json.loads(row[1]), json.loads(row[2])) for row in cursor.fetchall()}
                lock = getattr(self, '_cache_lock', None)
                if lock:
                    with lock:
                        self._hash_cache.update(loaded)
                else:
                    self._hash_cache.update(loaded)
        except Exception:
            pass

    def _get_ui_classes(self):
        if not self._cached_ui_classes or not self._cached_ui_classes[0]:
            b_cls = find_class('org.telegram.ui.Stories.recorder.ButtonWithCounterView')
            l_cls = find_class('android.widget.LinearLayout')
            t_cls = find_class('org.telegram.ui.ActionBar.Theme')
            u_cls = find_class('org.telegram.messenger.AndroidUtilities')
            cb_cls = find_class('android.widget.CheckBox')
            comp_cls = find_class('android.widget.CompoundButton')
            self._cached_ui_classes = (b_cls, l_cls, t_cls, u_cls, cb_cls, comp_cls)
        return self._cached_ui_classes

    def _safe_set_text(self, view, text_str: str, animate: bool=False):
        if not view:
            return
        try:
            view.setText(text_str, animate)
        except Exception:
            try:
                view.setText(text_str)
            except Exception:
                pass

    def on_plugin_unload(self):
        with self._dex_lock:
            self.is_stopped = True
            self.is_active = False
        for tm in getattr(self, '_timers', []):
            try:
                tm.cancel()
            except Exception:
                pass
        self._timers.clear()
        _stop_spring_waiting_haptic()
        global _ACTIVE_GUARD_INSTANCE
        try:
            self.remove_on_send_message_hook()
        except Exception:
            pass
        if hasattr(self, '_installed_hooks') and self._installed_hooks:
            for h in self._installed_hooks:
                try:
                    self.unhook_method(h)
                except Exception:
                    pass
            self._installed_hooks.clear()
        try:
            if getattr(self, '_cached_dex_bridge', None):
                self._invoke_dex('unload')
        except Exception:
            pass
        try:
            if getattr(self, '_cached_hook_bridge', None):
                self._cached_hook_bridge.uninstall()
        except Exception:
            pass
        self._cached_dex_bridge = None
        self._cached_dex_loader = None
        self._cached_hook_bridge = None
        self._dex_model_loaded_path = None
        if hasattr(self, '_cached_methods') and self._cached_methods is not None:
            self._cached_methods.clear()
        self._cleanup_sheet_views()
        self._hash_cache.clear()
        self._vector_db = None
        self._vector_names = None
        self._model_metadata = None
        if _ACTIVE_GUARD_INSTANCE is self:
            _ACTIVE_GUARD_INSTANCE = None
        try:
            gc.collect()
        except Exception:
            pass

    def on_send_message_hook(self, account: int, params: Any) -> HookResult:
        if not params or getattr(_HOOK_LOCK, 'in_call', False):
            return HookResult(strategy=HookStrategy.DEFAULT)
        _HOOK_LOCK.in_call = True
        try:
            msg = getattr(params, 'message', None)
            if not msg and hasattr(params, 'text'):
                msg = params.text
            if isinstance(msg, str) and msg and (msg[0] in ('.', '/', '!')):
                text = msg.strip()
                if text.startswith(('./plugguard', '.plugguard', './guard', '.guard', '/guard', '!guard', '!plugguard')):
                    parts = text.split()
                    subcmd = parts[1].lower() if len(parts) > 1 else 'help'
                    arg = parts[2] if len(parts) > 2 else ''
                    post_ui(lambda: self._handle_debug_command(subcmd, arg))
                    return HookResult(strategy=HookStrategy.CANCEL)
        except Exception as e:
            self.log(f'[PluginGuard DEBUG] on_send_message_hook error: {e}')
        finally:
            _HOOK_LOCK.in_call = False
            del params
        return HookResult(strategy=HookStrategy.DEFAULT)
