import html
import importlib.abc
import importlib.machinery
import json
import os
import re
import sys
import tempfile
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple, Union

import _extera

try:
    from tl_runtime import ArrayList
except ImportError:
    try:
        import exd_java
        ArrayList = exd_java.ArrayList
    except Exception:
        class ArrayList(list):
            def add(self, *args: Any) -> bool:
                if len(args) == 1:
                    self.append(args[0])
                else:
                    self.insert(args[0], args[1])
                return True

            def size(self) -> int:
                return len(self)

            def get(self, index: int) -> Any:
                return self[index]

            def set(self, index: int, value: Any) -> Any:
                old = self[index]
                self[index] = value
                return old

            def isEmpty(self) -> bool:
                return len(self) == 0

            def contains(self, value: Any) -> bool:
                return value in self

            def clear(self) -> None:
                del self[:]

            def addAll(self, values: Any) -> bool:
                self.extend(values)
                return True

            def toArray(self) -> List[Any]:
                return list(self)


TERMINAL_METHODS: Dict[str, Any] = {
    "getSuperclass": None,
    "getGenericSuperclass": None,
    "getEnclosingClass": None,
    "getDeclaringClass": None,
    "getParent": None,
    "getNext": None,
    "getCause": None,
    "poll": None,
    "readLine": None,
    "read": -1,
    "hasNext": False,
    "hasMoreElements": False,
    "moveToNext": False,
    "moveToFirst": False,
    "isAlive": False,
    "isAttachedToWindow": False,
    "isShown": False,
}


def lenient(name: str, item: str) -> Any:
    if item in ("getName", "getCanonicalName", "getTypeName"):
        return lambda *args, **kwargs: str(name)
    if item == "getSimpleName":
        return lambda *args, **kwargs: str(name).replace("$", ".").split(".")[-1]
    if item in ("getDeclaredMethod", "getMethod"):
        return lambda method_name="", *args, **kwargs: Missing(f"{name}.{method_name}")
    if item in TERMINAL_METHODS:
        target_val = TERMINAL_METHODS[item]
        return lambda *args, **kwargs: target_val
    return Stub(f"{name}.{item}")


class Stub:
    def __init__(self, name: str = "stub"):
        object.__setattr__(self, "_name", str(name))

    def __getattr__(self, item: str) -> Any:
        if item.startswith("__") and item.endswith("__"):
            raise AttributeError(item)
        return lenient(self._name, item)

    def __setattr__(self, key: str, value: Any) -> None:
        object.__setattr__(self, key, value)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return Stub(f"{self._name}()")

    def __instancecheck__(self, obj: Any) -> bool:
        target_name = str(object.__getattribute__(self, "_name"))
        if target_name in (
            "java.lang.Class",
            "java.chaquopy.JavaClass",
            "java.lang.Object",
            "java.chaquopy.JavaObject",
        ):
            return isinstance(obj, (type, Stub)) or hasattr(obj, "_java_name") or hasattr(obj, "getName")
        other = getattr(obj, "_java_name", None) or getattr(type(obj), "_java_name", None)
        if isinstance(obj, Stub):
            other = object.__getattribute__(obj, "_name")
        return bool(other) and str(other).split("(")[0] == target_name

    def __subclasscheck__(self, cls: type) -> bool:
        other = getattr(cls, "_java_name", None)
        return bool(other) and str(other) == str(object.__getattribute__(self, "_name"))

    def __bool__(self) -> bool:
        return True

    def __iter__(self):
        return iter(())

    def __len__(self) -> int:
        return 0

    def __int__(self) -> int:
        return 0

    def __float__(self) -> float:
        return 0.0

    def __index__(self) -> int:
        return 0

    def _zero_op(self, *args: Any) -> int:
        return 0

    def _union_op(self, other: Any) -> Any:
        if other is None or isinstance(other, (type, Stub, str)) or hasattr(other, "__origin__"):
            return self
        return 0

    __add__ = __radd__ = __sub__ = __rsub__ = _zero_op
    __mul__ = __rmul__ = __truediv__ = __rtruediv__ = _zero_op
    __floordiv__ = __rfloordiv__ = __mod__ = __rmod__ = _zero_op
    __or__ = __ror__ = _union_op
    __and__ = __rand__ = __xor__ = __rxor__ = _zero_op
    __lshift__ = __rlshift__ = __rshift__ = __rrshift__ = _zero_op
    __neg__ = __pos__ = __invert__ = __abs__ = _zero_op

    def __getitem__(self, item: Any) -> Any:
        return Stub(f"{self._name}[]")

    def __setitem__(self, item: Any, value: Any) -> None:
        return None

    def __contains__(self, item: Any) -> bool:
        return False

    def __fspath__(self) -> str:
        folder = os.path.join(tempfile.gettempdir(), "oxdesktop_plugins")
        os.makedirs(folder, exist_ok=True)
        return folder

    __lt__ = __le__ = __gt__ = __ge__ = lambda self, other: False

    def __str__(self) -> str:
        return ""

    def __repr__(self) -> str:
        return f"<stub {self._name}>"

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, Stub)

    def __hash__(self) -> int:
        return hash(self._name)

    def __mro_entries__(self, bases: Any) -> Tuple[type, ...]:
        return (object,)


def _open_url(url: Any) -> bool:
    _extera.open_url(str(url))
    return True


class _Toast:
    LENGTH_SHORT = 0
    LENGTH_LONG = 1

    def __init__(self, text: Any):
        self._text = str(text)

    @staticmethod
    def makeText(context: Any, text: Any, duration: int = 0) -> "_Toast":
        return _Toast(text)

    def show(self) -> None:
        _extera.toast(self._text)


class _Uri:
    _java_name = "android.net.Uri"

    def __init__(self, value: Any):
        self._value = str(value)

    @staticmethod
    def parse(value: Any) -> "_Uri":
        return _Uri(value)

    @staticmethod
    def fromFile(file: Any) -> "_Uri":
        path = file.getAbsolutePath() if hasattr(file, "getAbsolutePath") else str(file)
        normalized = str(path).replace("\\", "/").lstrip("/")
        return _Uri(f"file:///{normalized}")

    def getPath(self) -> str:
        import exd_picker
        return exd_picker.uri_path(self)

    def getLastPathSegment(self) -> str:
        return os.path.basename(self.getPath())

    def getScheme(self) -> str:
        return self._value.split(":", 1)[0] if ":" in self._value else ""

    def getHost(self) -> Optional[str]:
        import urllib.parse
        return urllib.parse.urlsplit(self._value).hostname

    def getQueryParameter(self, name: str) -> Optional[str]:
        import urllib.parse
        values = urllib.parse.parse_qs(urllib.parse.urlsplit(self._value).query).get(str(name))
        return values[0] if values else None

    def toString(self) -> str:
        return self._value

    def __str__(self) -> str:
        return self._value


class _Intent(Stub):
    ACTION_VIEW = "android.intent.action.VIEW"
    ACTION_SEND = "android.intent.action.SEND"
    ACTION_SEND_MULTIPLE = "android.intent.action.SEND_MULTIPLE"
    ACTION_GET_CONTENT = "android.intent.action.GET_CONTENT"
    ACTION_OPEN_DOCUMENT = "android.intent.action.OPEN_DOCUMENT"
    ACTION_OPEN_DOCUMENT_TREE = "android.intent.action.OPEN_DOCUMENT_TREE"
    ACTION_CREATE_DOCUMENT = "android.intent.action.CREATE_DOCUMENT"
    ACTION_PICK = "android.intent.action.PICK"
    CATEGORY_OPENABLE = "android.intent.category.OPENABLE"
    EXTRA_ALLOW_MULTIPLE = "android.intent.extra.ALLOW_MULTIPLE"
    EXTRA_MIME_TYPES = "android.intent.extra.MIME_TYPES"
    EXTRA_TEXT = "android.intent.extra.TEXT"
    EXTRA_STREAM = "android.intent.extra.STREAM"
    FLAG_GRANT_READ_URI_PERMISSION = 1
    FLAG_ACTIVITY_NEW_TASK = 0x10000000

    def __init__(self, action: Optional[str] = None, uri: Optional[Any] = None, *args: Any):
        super().__init__("Intent")
        object.__setattr__(self, "action", action)
        object.__setattr__(self, "uri", uri)

    def addFlags(self, flags: int) -> "_Intent":
        return self

    def setFlags(self, flags: int) -> "_Intent":
        return self

    def setData(self, uri: Any) -> "_Intent":
        object.__setattr__(self, "uri", uri)
        return self

    def setAction(self, action: Optional[str]) -> "_Intent":
        object.__setattr__(self, "action", action)
        return self

    def setType(self, mime: str) -> "_Intent":
        object.__setattr__(self, "_type", mime)
        return self

    def addCategory(self, category: str) -> "_Intent":
        return self

    def putExtra(self, key: Any, value: Any = None) -> "_Intent":
        extras = self.__dict__.get("_extras")
        if extras is None:
            extras = {}
            object.__setattr__(self, "_extras", extras)
        extras[str(key)] = value
        return self

    def getData(self) -> Any:
        return self.__dict__.get("uri")

    def getAction(self) -> Optional[str]:
        return self.__dict__.get("action")

    def getClipData(self) -> Optional["_ClipData"]:
        clip = self.__dict__.get("_clip")
        if not clip:
            return None
        return _ClipData(clip)

    def getStringExtra(self, key: Any) -> Optional[str]:
        return (self.__dict__.get("_extras") or {}).get(str(key))


def _plugin_files_dir(kind: str = "files") -> Any:
    import exd_java
    import file_utils
    try:
        import extera_host
        pid = extera_host.current_plugin_id()
    except Exception:
        pid = None

    if kind == "cache":
        resolved_path = file_utils.get_plugin_cache_dir(pid) if pid else None
    else:
        resolved_path = file_utils.get_plugin_dir(pid) if pid else None

    if not resolved_path:
        resolved_path = os.path.join(tempfile.gettempdir(), "oxdesktop_plugins")
        os.makedirs(resolved_path, exist_ok=True)
    return exd_java.File(resolved_path)


class _ClipItem:
    def __init__(self, uri: Any):
        self._uri = uri

    def getUri(self) -> Any:
        return self._uri


class _ClipData:
    def __init__(self, uris: Any):
        self._uris = list(uris)

    def getItemCount(self) -> int:
        return len(self._uris)

    def getItemAt(self, index: int) -> _ClipItem:
        return _ClipItem(self._uris[int(index)])


class ClassNotFoundException(Exception):
    pass


class _Context(Stub):
    def getContentResolver(self, *args: Any) -> Any:
        import exd_picker
        return exd_picker.ContentResolver()

    def startActivityForResult(self, intent: Any, request_code: int = 0, *args: Any) -> None:
        import exd_picker
        if exd_picker.start_for_result(intent, request_code, self):
            return None
        uri_val = getattr(intent, "uri", None)
        if uri_val is not None:
            _open_url(uri_val)
        return None

    def startActivity(self, intent: Any, *args: Any) -> None:
        import exd_picker
        if exd_picker.start_for_result(intent, 0, self):
            return None
        uri_val = getattr(intent, "uri", None)
        if uri_val is not None:
            _open_url(uri_val)

    def getFilesDir(self, *args: Any) -> Any:
        return _plugin_files_dir()

    def getFilesDirFixed(self, *args: Any) -> Any:
        return _plugin_files_dir()

    def getExternalFilesDir(self, *args: Any) -> Any:
        return _plugin_files_dir()

    def getCacheDir(self, *args: Any) -> Any:
        return _plugin_files_dir("cache")

    def getExternalCacheDir(self, *args: Any) -> Any:
        return _plugin_files_dir("cache")

    def getDataDir(self, *args: Any) -> Any:
        return _plugin_files_dir()

    def getPackageName(self, *args: Any) -> str:
        return "org.oxdesktop.messenger"

    def getClassLoader(self) -> Any:
        class _ClassLoader:
            def loadClass(self, name: str) -> Any:
                import hook_utils
                target = hook_utils.find_class(str(name))
                if target is not None and not isinstance(target, Missing):
                    return target
                raise ClassNotFoundException(str(name))
        return _ClassLoader()

    def getParentActivity(self) -> "_Context":
        return self


_BROWSER_EXTERNAL = [True]


class _Browser:
    @staticmethod
    def openUrl(context: Any, url: Any, *args: Any) -> Any:
        if not _BROWSER_EXTERNAL[0]:
            _BROWSER_EXTERNAL[0] = True
            return None
        target_str = str(getattr(url, "toString", lambda: url)())
        return _open_url(target_str)


class LenientMeta(type):
    def __getattr__(cls, item: str) -> Any:
        if item.startswith("__") and item.endswith("__"):
            raise AttributeError(item)
        return lenient(cls.__name__, item)


class Missing(Stub):
    def __bool__(self) -> bool:
        return False


class _ApplicationLoader(metaclass=LenientMeta):
    applicationContext = _Context("applicationContext")

    @staticmethod
    def getFilesDirFixed(*args: Any) -> Any:
        return _plugin_files_dir()

    @staticmethod
    def getCacheDirFixed(*args: Any) -> Any:
        return _plugin_files_dir("cache")


class _LaunchActivity:
    instance = _Context("LaunchActivity")


class _AndroidUtilities(Stub):
    @staticmethod
    def addToClipboard(text: Any) -> bool:
        _extera.copy(str(text))
        return True

    @staticmethod
    def runOnUIThread(runnable: Any, delay: int = 0) -> None:
        callback = getattr(runnable, "run", runnable)
        _extera.run_on_main(callback, int(delay or 0))

    @staticmethod
    def dp(value: Any) -> float:
        import android_views
        return android_views.dp(value)

    @staticmethod
    def displaySize() -> Any:
        import android_views
        return android_views.displaySize


class _LocaleController(Stub):
    @staticmethod
    def getString(*args: Any) -> str:
        for val in args:
            if isinstance(val, str):
                return val
        return ""

    @staticmethod
    def formatString(*args: Any) -> str:
        return ""


def _dynamic_proxy(*interfaces: Any) -> type:
    return object


def _build_widget_shims() -> Dict[str, Dict[str, Any]]:
    import android_views
    return {
        "android.widget": {
            "LinearLayout": android_views.LinearLayout,
            "FrameLayout": android_views.FrameLayout,
            "ScrollView": android_views.ScrollView,
            "TextView": android_views.TextView,
            "EditText": android_views.EditText,
            "ImageView": android_views.ImageView,
            "Toast": _Toast,
        },
        "android.view": {
            "View": android_views.View,
            "Gravity": android_views.Gravity,
        },
        "android.graphics": {
            "Bitmap": android_views.Bitmap,
            "Canvas": android_views.Canvas,
            "Paint": android_views.Paint,
            "RectF": android_views.RectF,
            "Typeface": android_views.Typeface,
        },
        "android.graphics.drawable": {
            "GradientDrawable": android_views.GradientDrawable,
            "ColorDrawable": android_views.ColorDrawable,
            "BitmapDrawable": android_views.BitmapDrawable,
            "Drawable": android_views.Drawable,
            "LayerDrawable": android_views.LayerDrawable,
        },
        "android.text": {
            "TextWatcher": android_views.TextWatcher,
        },
        "android.view.animation": {
            "DecelerateInterpolator": android_views.DecelerateInterpolator,
            "OvershootInterpolator": android_views.OvershootInterpolator,
        },
        "org.telegram.ui.Components": {
            "LayoutHelper": android_views.LayoutHelper,
        },
        "org.telegram.ui.ActionBar": {
            "BottomSheet": android_views.BottomSheet,
            "AlertDialog": android_views.AlertDialog,
            "Theme": android_views.Theme,
        },
    }


SHIMS: Dict[str, Dict[str, Any]] = {
    "android.widget": {"Toast": _Toast},
    "android.net": {"Uri": _Uri},
    "android.content": {"Intent": _Intent},
    "org.telegram.messenger.browser": {"Browser": _Browser},
    "org.telegram.messenger": {
        "ApplicationLoader": _ApplicationLoader,
        "AndroidUtilities": _AndroidUtilities("AndroidUtilities"),
        "LocaleController": _LocaleController("LocaleController"),
    },
    "org.telegram.ui": {"LaunchActivity": _LaunchActivity},
    "org.telegram.tgnet": {},
    "org.telegram.tgnet.tl": {},
    "java": {
        "jclass": lambda name: Stub(str(name)),
        "dynamic_proxy": _dynamic_proxy,
        "jarray": lambda kind: (lambda values: list(values)),
        "cast": lambda kind, value: value,
        "jint": int,
        "jlong": int,
        "jboolean": bool,
        "jfloat": float,
        "jdouble": float,
    },
}

ROOT_PACKAGES = (
    "java", "android", "androidx", "org", "com", "kotlin", "dalvik",
    "de", "me", "io",
)


class _DynamicStubModule(type(sys)):
    def __getattr__(self, item: str) -> Any:
        if item.startswith("__") and item.endswith("__"):
            raise AttributeError(item)
        val = Stub(f"{self.__name__}.{item}")
        setattr(self, item, val)
        return val


class _CompatImportFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, fullname: str, path: Optional[Any], target: Optional[Any] = None) -> Optional[importlib.machinery.ModuleSpec]:
        root = fullname.split(".")[0]
        if root not in ROOT_PACKAGES:
            return None
        if fullname != root and root in ("com", "io", "me", "de") and not fullname.startswith(
            ("org.oxdesktop", "com.exteragram", "com.google.android", "com.chaquo", "de.robv", "me.", "io.")
        ):
            return None
        return importlib.machinery.ModuleSpec(fullname, self, is_package=True)

    def create_module(self, spec: importlib.machinery.ModuleSpec) -> Any:
        mod = _DynamicStubModule(spec.name)
        mod.__path__ = []
        for k, v in SHIMS.get(spec.name, {}).items():
            setattr(mod, k, v)
        return mod

    def exec_module(self, module: Any) -> None:
        pass


def install() -> None:
    if not any(isinstance(f, _CompatImportFinder) for f in sys.meta_path):
        import android_views
        for mod_name, mappings in _build_widget_shims().items():
            SHIMS.setdefault(mod_name, {}).update(mappings)

        import tgnet_bridge
        tgnet_bridge.install(SHIMS)

        import exd_java
        exd_java.install(SHIMS)

        import exd_android
        exd_android.install(SHIMS)

        SHIMS["java"]["jclass"] = lambda name: exd_java.lookup(str(name)) or Stub(str(name))
        android_util = SHIMS.setdefault("org.telegram.messenger", {})["AndroidUtilities"]
        android_util.displaySize = android_views.displaySize
        android_util.density = android_views.density()

        sys.meta_path.append(_CompatImportFinder())

    if sys.platform == "win32" and "fcntl" not in sys.modules:
        sys.modules["fcntl"] = _create_fcntl_mock()


def _create_fcntl_mock() -> Any:
    mod = type(sys)("fcntl")
    for idx, flag_name in enumerate(
        (
            "LOCK_SH", "LOCK_EX", "LOCK_NB", "LOCK_UN", "F_GETFL", "F_SETFL",
            "F_GETFD", "F_SETFD", "FD_CLOEXEC",
        )
    ):
        setattr(mod, flag_name, 1 << idx)
    mod.flock = lambda *args, **kwargs: None
    mod.lockf = lambda *args, **kwargs: None
    mod.fcntl = lambda *args, **kwargs: 0
    mod.ioctl = lambda *args, **kwargs: 0
    return mod


class SendMessageParams:
    def __init__(self, peer: Any = None, message: str = "", reply_to: int = 0):
        self.peer = peer
        self.message = str(message or "")
        self.caption = None
        self.entities = []
        self.replyToMsg = _ReplyStub(reply_to) if reply_to else None
        self.replyToTopMsg = None
        self.replyQuote = None
        self.replyQuoteOffset = None
        self.replyQuoteLength = None
        self.replyMarkup = None
        self.params = None
        self.notify = True
        self.scheduleDate = 0
        self.searchLinks = True
        self.photo = None
        self.document = None
        self.path = None

    @property
    def text(self) -> str:
        return self.message

    @text.setter
    def text(self, val: Any) -> None:
        self.message = str(val or "")

    @property
    def dialog_id(self) -> int:
        return to_dialog_id(self.peer)

    @dialog_id.setter
    def dialog_id(self, val: Any) -> None:
        self.peer = val

    @property
    def peer_id(self) -> int:
        return self.dialog_id

    @peer_id.setter
    def peer_id(self, val: Any) -> None:
        self.peer = val

    @property
    def reply_to_id(self) -> int:
        if self.replyToMsg is not None:
            return getattr(self.replyToMsg, "id", 0)
        return 0

    def __getitem__(self, key: str) -> Any:
        if key == "text":
            return self.message
        if key in ("dialog_id", "peer_id"):
            return self.dialog_id
        if key == "reply_to_id":
            return self.reply_to_id
        if hasattr(self, key):
            return getattr(self, key)
        raise KeyError(key)

    def __setitem__(self, key: str, value: Any) -> None:
        if key == "text":
            self.message = str(value or "")
        elif key in ("dialog_id", "peer_id"):
            self.peer = value
        elif key == "reply_to_id":
            self.replyToMsg = _ReplyStub(value)
        else:
            setattr(self, key, value)

    def __delitem__(self, key: str) -> None:
        if hasattr(self, key):
            setattr(self, key, None)

    def __contains__(self, key: str) -> bool:
        if key in ("text", "dialog_id", "peer_id", "reply_to_id"):
            return True
        return hasattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def setdefault(self, key: str, default: Any = None) -> Any:
        if key in self:
            return self[key]
        self[key] = default
        return default

    def keys(self) -> List[str]:
        keys_list = [k for k in self.__dict__.keys() if not k.startswith("_")]
        for extra in ("text", "dialog_id", "peer_id", "reply_to_id"):
            if extra not in keys_list:
                keys_list.append(extra)
        return keys_list

    def values(self) -> List[Any]:
        return [self.get(k) for k in self.keys()]

    def items(self) -> List[Tuple[str, Any]]:
        return [(k, self.get(k)) for k in self.keys()]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "peer": self.peer,
            "message": self.message,
            "text": self.text,
            "caption": self.caption,
            "entities": self.entities,
            "reply_to_id": self.reply_to_id,
            "dialog_id": self.dialog_id,
            "notify": self.notify,
            "scheduleDate": self.scheduleDate,
            "searchLinks": self.searchLinks,
            "photo": self.photo,
            "document": self.document,
            "path": self.path,
        }


class _ReplyStub(Stub):
    def __init__(self, msg_id: Any, text: str = "", dialog_id: int = 0, from_id: int = 0):
        super().__init__("replyToMsg")
        parsed_id = int(msg_id or 0)
        object.__setattr__(self, "id", parsed_id)
        object.__setattr__(self, "messageText", str(text or ""))
        object.__setattr__(self, "text", str(text or ""))
        object.__setattr__(self, "message", str(text or ""))
        object.__setattr__(self, "messageOwner", None)
        object.__setattr__(self, "dialog_id", int(dialog_id or 0))
        object.__setattr__(self, "from_id", int(from_id or 0))
        object.__setattr__(self, "date", 0)

    def __int__(self) -> int:
        return int(object.__getattribute__(self, "id") or 0)


def format_text(text: Any, parse_mode: Optional[str]) -> Tuple[str, List[Any]]:
    from text_formatting import parse_text
    mode = (parse_mode or "").lower()
    if mode not in ("html", "markdown"):
        return str(text or ""), []
    parsed = parse_text(str(text or ""), mode, is_caption=False)
    return parsed.get("message", str(text)), parsed.get("entities") or []


def to_dialog_id(peer: Any) -> int:
    if isinstance(peer, Stub):
        return 0
    try:
        return int(peer)
    except Exception:
        val = (
            getattr(peer, "user_id", None)
            or getattr(peer, "channel_id", None)
            or getattr(peer, "chat_id", None)
        )
        return int(val or 0)


def send(peer: Any, text: Any, parse_mode: Optional[str] = None, reply_to: int = 0) -> None:
    plain, entities = format_text(text, parse_mode)
    _extera.send_message(
        to_dialog_id(peer),
        plain,
        json.dumps(entities),
        int(reply_to or 0),
    )


try:
    from markdown_utils import MarkdownEntity, ParsedText, parse_html, parse_markdown
except ImportError:
    pass
