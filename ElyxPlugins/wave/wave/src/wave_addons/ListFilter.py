import math
import re
import threading
import time

try:
    __file__
except NameError:
    try:
        __file__ = file
    except NameError:
        __file__ = ""

from base_plugin import MethodHook
from hook_utils import find_class
from java import dynamic_proxy, jclass
from android_utils import log, run_on_ui_thread
try:
    from wave_addons.Diag import log
except Exception:
    try:
        from .Diag import log
    except Exception:
        pass

try:
    from wave_addons import Alpha as A
except Exception:
    from . import Alpha as A

LATIN, CYR, OTHER = A.LATIN, A.CYR, A.HASH


class FilterHook(MethodHook):

    def __init__(self, flt):
        self.flt = flt

    def after_hooked_method(self, param):
        f = self.flt
        try:
            keep = f.keep
            if keep is None or f.bypass:
                return
            args = param.args
            if len(args) < 3 or int(args[1]) not in (0, 7, 8):
                return
            if int(args[2]) != 0 and not f.plugin.cfg_bool("wave_in_archive", False):
                return
            res = param.getResult()
            if res is None:
                return
            key = (int(f._sys().identityHashCode(res)), int(res.size()))
            hit = f._cache.get(key)
            if hit is None:
                hit = jclass("java.util.ArrayList")(res)
                hit.retainAll(keep)
                if len(f._cache) > 6:
                    f._cache.clear()
                f._cache[key] = hit
            param.setResult(hit)
        except Exception as e:
            log("[Wave] filter hook: {0}".format(e))


class ListFilter:
    def __init__(self, plugin):
        self.plugin = plugin
        self.letter = None
        self.keep = None
        self.bypass = False
        self.busy = False
        self.pending = None
        self.has_pending = False
        self._titles = {}
        self.hooks = []
        self._hooked = False
        self._cache = {}
        self._system = None
        self.anim_until = 0.0

    def _sys(self):
        if self._system is None:
            self._system = jclass("java.lang.System")
        return self._system

    def install(self):
        return

    def ensure_hooks(self):
        if self._hooked:
            return
        hook = FilterHook(self)
        for name in ("org.telegram.ui.Adapters.DialogsAdapter", "org.telegram.ui.DialogsActivity"):
            try:
                cls = find_class(name)
                if cls is not None:
                    refs = list(self.plugin.hook_all_methods(cls, "getDialogsArray", hook) or [])
                    self.hooks.extend(refs)
                    self.plugin._hooks.extend(refs)
            except Exception as e:
                log("[Wave] hook {0}: {1}".format(name, e))
        self._hooked = True

    def drop_hooks(self):
        if not self._hooked:
            return
        for h in list(self.hooks):
            try:
                self.plugin.unhook_method(h)
            except Exception:
                pass
            try:
                self.plugin._hooks.remove(h)
            except Exception:
                pass
        self.hooks = []
        self._hooked = False
        self._cache = {}

    def _page(self, frag):
        pages = self.plugin._field(frag, "viewPages")
        if pages is None:
            return None
        for p in pages:
            if p is not None:
                try:
                    if int(p.getVisibility()) == 0:
                        return p
                except Exception:
                    return p
        return None

    def list_view(self, frag):
        p = self._page(frag)
        return self.plugin._field(p, "listView") if p is not None else None

    def raw_dialogs(self, frag):
        page = self._page(frag)
        if page is None:
            return []
        acc = int(self.plugin._field(frag, "currentAccount") or 0)
        dtype = int(self.plugin._field(page, "dialogsType") or 0)
        folder = int(self.plugin._field(frag, "folderId") or 0)
        ad = self.plugin._field(page, "dialogsAdapter")
        self.bypass = True
        lst = None
        try:
            for getter in (
                lambda: jclass("org.telegram.ui.DialogsActivity").getDialogsArray(acc, dtype, folder, False),
                lambda: ad.getDialogsArray(acc, dtype, folder, False),
                lambda: jclass("org.telegram.messenger.MessagesController").getInstance(acc).getDialogs(folder),
            ):
                try:
                    lst = getter()
                    if lst is not None:
                        break
                except Exception:
                    lst = None
        finally:
            self.bypass = False
        if lst is None:
            return []
        out = []
        for i in range(int(lst.size())):
            out.append(lst.get(i))
        return out

    def title(self, did):
        t = self._titles.get(did)
        if t is None:
            t = self.plugin.dialog_title(did)
            self._titles[did] = t
        return t

    def _snapshot(self, frag, max_age=8.0):
        snap = getattr(self, "_snap", None)
        now = time.time()
        try:
            pg = self._page(frag)
            tabkey = (int(self.plugin._field(pg, "dialogsType") or 0), int(self.plugin._field(pg, "selectedType") or 0))
        except Exception:
            tabkey = None
        if snap is not None and now - snap[0] < max_age and getattr(self, "_snap_tab", None) == tabkey:
            return snap[1]
        self._snap_tab = tabkey
        rows = []
        for d in self.raw_dialogs(frag):
            try:
                did = int(d.id)
                rows.append((d, did, self.title(did)))
            except Exception:
                pass
        self._snap = (now, rows)
        return rows

    def _all_rows(self, frag):
        now = time.time()
        c = getattr(self, "_allc", None)
        if c is not None and now - c[0] < 3.0:
            return c[1]
        rows = []
        try:
            from org.telegram.messenger import MessagesController, UserConfig
            lst = MessagesController.getInstance(UserConfig.selectedAccount).getAllDialogs()
            for i in range(int(lst.size())):
                d = lst.get(i)
                did = int(d.id)
                rows.append((d, did, self.title(did)))
        except Exception as e:
            log("[Wave] all rows: {0}".format(e))
        if not rows:
            rows = self._snapshot(frag, 3.0)
        self._allc = (now, rows)
        return rows

    def build_keep(self, frag, letter):
        p = self.plugin
        word = p.cfg_int("wave_match", 0) == 1
        xs = p.cfg_bool("wave_xscript", True)
        letters = A.alphabet_letters(p._alpha_lang())
        keep = jclass("java.util.HashSet")()
        ids = set()
        pin_ids = None
        if str(letter).startswith(A.PIN_PREFIX):
            pins = p._pins()
            k = A.pin_index(letter)
            pin_ids = set(pins[k]["ids"]) if 0 <= k < len(pins) else set()
        for d, did, t in self._all_rows(frag):
            ok = (did in pin_ids) if pin_ids is not None else A.matches(t, letter, letters, xs, word)
            if ok:
                keep.add(d)
                ids.add(did)
        return keep, ids

    def request(self, frag, letter):
        self.pending, self.has_pending = letter, True
        if not self.busy:
            self._cycle(frag)

    def _cycle(self, frag):
        if not self.has_pending:
            return
        letter, self.pending, self.has_pending = self.pending, None, False
        if letter == self.letter:
            return
        self.busy = True
        try:
            keep, ids = (None, None) if letter is None else self.build_keep(frag, letter)
            lv = self.list_view(frag)
            ms = self.plugin.cfg_int("wave_dissolve", 0)
            if ms > 0 and lv is not None and ids is not None:
                self._dissolve(lv, ids, ms)
                run_on_ui_thread(lambda: self._commit(frag, letter, keep), ms + 12)
            else:
                self._commit(frag, letter, keep)
        except Exception as e:
            log("[Wave] cycle: {0}".format(e))
            self.busy = False

    def _dissolve(self, lv, ids, ms):
        for i in range(int(lv.getChildCount())):
            c = lv.getChildAt(i)
            try:
                did = int(c.getDialogId())
            except Exception:
                did = 0
            if did not in ids:
                c.animate().cancel()
                c.animate().alpha(0.0).scaleX(0.92).scaleY(0.92).setDuration(int(ms)).start()

    def _commit(self, frag, letter, keep):
        try:
            self.letter = letter
            self.keep = keep
            self._cache = {}
            if keep is not None:
                self.ensure_hooks()
            lv = self.list_view(frag)
            if lv is not None:
                self.reset_cells(lv)
            self._unstick(frag)
            if lv is not None:
                try:
                    lv.getRecycledViewPool().clear()
                except Exception:
                    pass
            self.notify(frag)
            if keep is None:
                self.drop_hooks()
            if lv is not None:
                try:
                    lv.stopScroll()
                    lv.scrollToPosition(0)
                except Exception:
                    pass
                run_on_ui_thread(lambda: self.reset_cells(lv), 16)
                run_on_ui_thread(lambda: self._enter(lv), 40)
            run_on_ui_thread(lambda: self._unstick(frag), 250)
            ov = self.plugin._overlay_for(frag)
            if ov is not None:
                ov.on_filter_changed(letter)
        except Exception as e:
            log("[Wave] commit: {0}".format(e))
        finally:
            self.busy = False
            if self.has_pending:
                self._cycle(frag)

    def _unstick(self, frag):
        p = self.plugin
        try:
            r1 = p._set_field(frag, "dialogsListFrozen", False)
            r2 = p._set_field(frag, "frozenDialogsList", None)
            try:
                from wave_addons import Diag
                Diag.state("unstick frag fields", "%s/%s" % (r1, r2))
            except Exception:
                pass
            pages = p._field(frag, "viewPages")
            for pg in (pages or []):
                if pg is None:
                    continue
                ad = p._field(pg, "dialogsAdapter")
                if ad is not None:
                    try:
                        ad.setDialogsListFrozen(False)
                    except Exception:
                        pass
                    p._set_field(ad, "dialogsListFrozen", False)
                    p._set_field(ad, "frozenDialogsList", None)
                lv = p._field(pg, "listView")
                if lv is not None:
                    p._set_field(lv, "fastScrollAnimationRunning", False)
                    try:
                        lv.setScrollEnabled(True)
                    except Exception:
                        pass
                    try:
                        lv.setTranslationY(0.0)
                    except Exception:
                        pass
        except Exception as e:
            log("[Wave] unstick: {0}".format(e))

    def notify(self, frag):
        pages = self.plugin._field(frag, "viewPages")
        if pages is None:
            return
        for p in pages:
            if p is None:
                continue
            ad = self.plugin._field(p, "dialogsAdapter")
            if ad is not None:
                ad.notifyDataSetChanged()

    def clear(self, frag=None):
        self.letter = None
        self.keep = None
        self.pending, self.has_pending, self.busy = None, False, False
        self._titles = {}
        self._cache = {}
        self._allc = None
        if frag is not None:
            try:
                lv = self.list_view(frag)
                if lv is not None:
                    self.reset_cells(lv)
                self.notify(frag)
            except Exception:
                pass
        self.drop_hooks()

    def reset_cells(self, lv):
        for i in range(int(lv.getChildCount())):
            c = lv.getChildAt(i)
            c.animate().cancel()
            c.setAlpha(1.0)
            c.setScaleX(1.0)
            c.setScaleY(1.0)
            c.setRotationX(0.0)
            c.setTranslationX(0.0)
            c.setTranslationY(0.0)
            c.setTranslationZ(0.0)

    def _finish_anim(self, lv):
        try:
            if time.time() >= self.anim_until:
                self.reset_cells(lv)
        except Exception:
            pass

    def _enter(self, lv):
        p = self.plugin
        style = p.cfg_int("wave_anim_style", 0)
        angle = float(p.cfg_int("wave_3d_angle", 32))
        depth = float(p.cfg_int("wave_3d_depth", 22)) / 100.0
        stagger = p.cfg_int("wave_stagger", 10)
        dens = float(p._dp(1))
        OI = jclass("android.view.animation.OvershootInterpolator")
        DI = jclass("android.view.animation.DecelerateInterpolator")
        n = int(lv.getChildCount())
        total = (260 if style == 0 else 220) + n * stagger + 60
        self.anim_until = time.time() + total / 1000.0
        run_on_ui_thread(lambda: self._finish_anim(lv), total + 40)
        for i in range(n):
            c = lv.getChildAt(i)
            c.animate().cancel()
            if style == 0:
                c.setCameraDistance(8000.0 * dens)
                c.setPivotX(float(c.getWidth()) / 2.0)
                c.setPivotY(0.0)
                c.setRotationX(angle)
                c.setScaleX(1.0 - depth)
                c.setScaleY(1.0 - depth)
                c.setTranslationY(float(p._dp(28)))
                c.setAlpha(0.0)
                a = c.animate().rotationX(0.0).scaleX(1.0).scaleY(1.0).translationY(0.0).alpha(1.0).setInterpolator(OI(1.6))
                a.setDuration(260).setStartDelay(int(i * stagger)).start()
            elif style == 1:
                c.setTranslationX(float(p._dp(70)) * (1 if i % 2 == 0 else -1))
                c.setAlpha(0.0)
                c.animate().translationX(0.0).alpha(1.0).setInterpolator(DI(1.8)).setDuration(220).setStartDelay(int(i * stagger)).start()
            else:
                c.setAlpha(0.0)
                c.animate().alpha(1.0).setDuration(160).setStartDelay(int(i * stagger)).start()


def make_item_touch(overlay):
    class _ItemTouch(dynamic_proxy(jclass("androidx.recyclerview.widget.RecyclerView$OnItemTouchListener"))):

        def __init__(self, overlay):
            super(_ItemTouch, self).__init__()
            self.ov = overlay
            self.x = self.y = 0.0
            self.t = 0
            self.on_child = False
            self.fired = False

        def onInterceptTouchEvent(self, rv, e):
            try:
                self._track(rv, e)
            except Exception:
                pass
            return False

        def onTouchEvent(self, rv, e):
            try:
                self._track(rv, e)
            except Exception:
                pass

        def onRequestDisallowInterceptTouchEvent(self, b):
            pass

        def _track(self, rv, e):
            ov = self.ov
            act = int(e.getActionMasked())
            if act == 0 and time.time() < ov.flt.anim_until + 0.15:
                ov.flt.anim_until = 0.0
                ov.flt.reset_cells(rv)
            if ov.flt.letter is None:
                return
            p = ov.plugin
            if act == 0:
                self.x, self.y, self.t = float(e.getX()), float(e.getY()), int(e.getEventTime())
                self.on_child = rv.findChildViewUnder(self.x, self.y) is not None
                self.fired = False
            elif act == 2 and not self.fired and p.cfg_bool("wave_reset_swipe", True):
                dy = float(e.getY()) - self.y
                if dy > p._dp(110) and not rv.canScrollVertically(-1):
                    self.fired = True
                    ov.reset_filter()
            elif act == 1 and not self.fired and p.cfg_bool("wave_reset_tap", True):
                moved = abs(float(e.getX()) - self.x) + abs(float(e.getY()) - self.y)
                if not self.on_child and moved < p._dp(10) and int(e.getEventTime()) - self.t < 350:
                    self.fired = True
                    ov.reset_filter()
    return _ItemTouch(overlay)
