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

from base_plugin import MethodHook
from hook_utils import find_class
from java import jclass
from android_utils import log, run_on_ui_thread
try:
    from wave_addons.Diag import log
except Exception:
    pass
from client_utils import get_last_fragment


class _CreateViewHook(MethodHook):
    def __init__(self, plugin):
        self.plugin = plugin

    def after_hooked_method(self, param):
        try:
            self.plugin._register_frag(param.thisObject)
            self.plugin._attach_overlay(param.thisObject, param.getResult())
        except Exception as e:
            log("[Wave] createView hook: {0}".format(e))
            try:
                self.plugin._toast("Wave: " + str(e)[:90], error=True)
            except Exception:
                pass


class _ResumeHook(MethodHook):

    def __init__(self, plugin):
        self.plugin = plugin

    def after_hooked_method(self, param):
        try:
            frag = param.thisObject
            self.plugin._register_frag(frag)
            if self.plugin._overlay_for(frag) is None:
                self.plugin._attach_overlay(frag, frag.getFragmentView())
        except Exception as e:
            log("[Wave] resume hook: {0}".format(e))


class _DestroyHook(MethodHook):
    def __init__(self, plugin):
        self.plugin = plugin

    def before_hooked_method(self, param):
        try:
            self.plugin._drop_overlay(param.thisObject)
            try:
                self.plugin._known.pop(int(param.thisObject.hashCode()), None)
            except Exception:
                pass
        except Exception:
            pass


class WaveEngineCore:
    def cfg_bool(self, key, default=False):
        try:
            return bool(self.get_setting(key, default))
        except Exception:
            return bool(default)

    def cfg_int(self, key, default=0):
        try:
            return int(float(self.get_setting(key, default)))
        except Exception:
            return int(default)

    def _set_field(self, obj, name, value):
        try:
            curr = obj.getClass()
            while curr is not None:
                try:
                    f = curr.getDeclaredField(name)
                    f.setAccessible(True)
                    f.set(obj, value)
                    return True
                except Exception:
                    curr = curr.getSuperclass()
        except Exception:
            pass
        return False

    def dialog_title(self, did):
        try:
            from org.telegram.messenger import MessagesController, UserConfig
            mc = MessagesController.getInstance(UserConfig.selectedAccount)
            did = int(did)
            if did > 0:
                u = mc.getUser(did)
                if u is not None:
                    from org.telegram.messenger import UserObject
                    if UserObject.isUserSelf(u):
                        return self._s("wave_saved_messages")
                    return str(UserObject.getUserName(u))
            else:
                c = mc.getChat(-did)
                if c is not None:
                    return str(c.title)
        except Exception:
            pass
        return "#"

    def _overlay_for(self, frag):
        try:
            return self._overlays.get(int(frag.hashCode()))
        except Exception:
            return None

    def _eligible(self, frag):
        try:
            if bool(self._field(frag, "onlySelect")):
                return False
            if int(self._field(frag, "folderId") or 0) != 0 and not self.cfg_bool("wave_in_archive", False):
                return False
            return True
        except Exception:
            return False

    def _attach_overlay(self, frag, view):
        if not self.cfg_bool("wave_enabled", True) or view is None or frag is None:
            return
        if not self._eligible(frag):
            return
        is_frame = self._is_frame(view)
        if not is_frame:
            log("[Wave] dialogs view is not a FrameLayout: {0}".format(view))
            return
        self._drop_overlay(frag)
        try:
            from wave_addons.Overlay import WaveOverlay
        except ImportError:
            from ...wave_addons.Overlay import WaveOverlay
        ov = WaveOverlay(self, frag, view)
        ov.attach()
        self._overlays[int(frag.hashCode())] = ov
        try:
            try:
                from wave_addons import Diag
            except ImportError:
                from ...wave_addons import Diag
            Diag.state("overlays", len(self._overlays))
            Diag.state("attached_to", str(view.getClass().getSimpleName()))
        except Exception:
            pass

    def _drop_overlay(self, frag):
        try:
            key = int(frag.hashCode())
        except Exception:
            return
        ov = self._overlays.pop(key, None)
        if ov is not None:
            try:
                ov.detach()
            except Exception:
                pass
        if not self._overlays:
            self._filter.clear(None)

    @staticmethod
    def _is_frame(view):
        try:
            c = view.getClass()
            while c is not None:
                if str(c.getName()) == "android.widget.FrameLayout":
                    return True
                c = c.getSuperclass()
        except Exception:
            pass
        return False

    def _register_frag(self, frag):
        try:
            if not hasattr(self, "_known") or self._known is None:
                self._known = {}
            self._known[int(frag.hashCode())] = frag
        except Exception:
            pass

    def _nested_dialogs(self, host, allow_search=True):
        try:
            hkey = int(host.hashCode())
        except Exception:
            hkey = id(host)
        cache = self.__dict__.setdefault("_nested_cache", {})
        hit = cache.get(hkey)
        if hit is not None:
            return list(hit)
        if not allow_search:
            return []
        import time as _t
        deadline = _t.time() + 0.35
        budget = [220]
        out, seen = [], set()

        def cname(o):
            try:
                return str(o.getClass().getName())
            except Exception:
                return ""

        def tname(f):
            try:
                return str(f.getType().getName())
            except Exception:
                return ""

        def interesting_type(t):
            if t.startswith("org.telegram.ui.") or t.startswith("com.exteragram."):
                return not (t.endswith("Cell") or ".Cells." in t or ".ActionBar." in t)
            return (t.startswith("java.util.") or t.endswith("SparseArray") or t.startswith("[L")
                    or t == "java.lang.Object")

        def fields_of(o):
            c = o.getClass()
            while c is not None and str(c.getName()) != "java.lang.Object":
                try:
                    for f in c.getDeclaredFields():
                        try:
                            if int(f.getModifiers()) & 0x8:
                                continue
                            t = tname(f)
                            if f.getType().isPrimitive() or not interesting_type(t):
                                continue
                            f.setAccessible(True)
                            yield f.get(o)
                        except Exception:
                            pass
                except Exception:
                    pass
                c = c.getSuperclass()

        def elements(o):
            n = cname(o)
            try:
                if n.startswith("[L"):
                    return [o[i] for i in range(min(len(o), 24))]
                if n.startswith("java.util.") and hasattr(o, "size"):
                    if hasattr(o, "values"):
                        return list(o.values().toArray())[:24]
                    return list(o.toArray())[:24]
                if n.endswith("SparseArray"):
                    return [o.valueAt(i) for i in range(min(int(o.size()), 24))]
            except Exception:
                pass
            return []

        def visit(o, depth):
            if o is None or depth > 2 or budget[0] <= 0 or _t.time() > deadline:
                return
            budget[0] -= 1
            n = cname(o)
            if not n:
                return
            if n.endswith(".DialogsActivity"):
                try:
                    h = int(o.hashCode())
                except Exception:
                    h = id(o)
                if h not in seen:
                    seen.add(h)
                    out.append(o)
                return
            els = elements(o)
            if els:
                for e in els:
                    visit(e, depth + 1)
                return
            if depth == 0 or n.startswith("org.telegram.ui.") or n.startswith("com.exteragram."):
                for v in fields_of(o):
                    if v is not None:
                        visit(v, depth + 1)
        try:
            visit(host, 0)
        except Exception as e:
            log("[Wave] nested search: {0}".format(e))
        if out or _t.time() <= deadline:
            cache[hkey] = list(out)
        return out

    def _dialogs_fragments(self, allow_search=False):
        out, seen = [], set()

        def add(f):
            try:
                h = int(f.hashCode())
            except Exception:
                return
            if h not in seen:
                seen.add(h)
                out.append(f)
        try:
            frag = get_last_fragment()
            layout = frag.getParentLayout() if frag is not None else None
            stack = layout.getFragmentStack() if layout is not None else None
            if stack is not None:
                for i in range(int(stack.size())):
                    f = stack.get(i)
                    name = str(f.getClass().getName())
                    if name.endswith(".DialogsActivity"):
                        add(f)
                    elif name.endswith("MainTabsActivity"):
                        for d in self._nested_dialogs(f, allow_search):
                            add(d)
        except Exception as e:
            log("[Wave] fragments: {0}".format(e))
        for f in list((getattr(self, "_known", None) or {}).values()):
            add(f)
        try:
            from wave_addons import Diag
            Diag.state("dialogs_found", len(out))
        except Exception:
            pass
        return out

    def _attach_existing(self, force=False):
        import threading as _th
        import time as _t
        now = _t.time()
        if getattr(self, "_attach_busy", False):
            return
        if not force and now - getattr(self, "_attach_last", 0.0) < 1.5:
            return
        self._attach_last = now
        self._attach_busy = True

        def apply(frags):
            try:
                for f in frags:
                    try:
                        if self._overlay_for(f) is not None:
                            continue
                        self._attach_overlay(f, f.getFragmentView())
                    except Exception as e:
                        log("[Wave] attach existing: {0}".format(e))
            finally:
                self._attach_busy = False

        def work():
            frags = []
            try:
                frags = self._dialogs_fragments(True)
            except Exception as e:
                log("[Wave] attach search: {0}".format(e))
            run_on_ui_thread(lambda: apply(frags))
        try:
            _th.Thread(target=work, daemon=True).start()
        except Exception:
            self._attach_busy = False

    def _detach_all(self):
        for key in list(self._overlays.keys()):
            ov = self._overlays.pop(key, None)
            try:
                if ov is not None:
                    ov.detach()
            except Exception:
                pass
        for f in self._dialogs_fragments(False):
            try:
                self._filter.clear(f)
            except Exception:
                pass
        self._filter.clear(None)

    def _refresh_overlays(self):
        enabled = self.cfg_bool("wave_enabled", True)

        def run():
            try:
                if not enabled:
                    self._detach_all()
                elif not self._overlays:
                    self._attach_existing()
                for ov in list(self._overlays.values()):
                    ov.apply_settings()
                for ov in list(self._demos):
                    try:
                        if ov.root.isAttachedToWindow():
                            ov.apply_settings()
                        else:
                            self._demos.remove(ov)
                    except Exception:
                        pass
            except Exception as e:
                log("[Wave] refresh: {0}".format(e))
        run_on_ui_thread(run)

    def _install_hooks(self):
        try:
            cls = find_class("org.telegram.ui.DialogsActivity")
            h1 = list(self.hook_all_methods(cls, "createView", _CreateViewHook(self)) or [])
            h2 = list(self.hook_all_methods(cls, "onFragmentDestroy", _DestroyHook(self)) or [])
            h3 = list(self.hook_all_methods(cls, "onResume", _ResumeHook(self)) or [])
            self._hooks.extend(h1 + h2 + h3)
            try:
                try:
                    from wave_addons import Diag
                except ImportError:
                    from ...wave_addons import Diag
                Diag.state("hooks createView/destroy/resume", "%d/%d/%d" % (len(h1), len(h2), len(h3)))
            except Exception:
                pass
        except Exception as e:
            log("[Wave] hooks: {0}".format(e))
        try:
            self._filter.install()
        except Exception as e:
            log("[Wave] filter hooks: {0}".format(e))
