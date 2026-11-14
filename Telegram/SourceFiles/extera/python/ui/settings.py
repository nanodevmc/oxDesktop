"""
oxDesktop Dynamic Settings Components & Descriptors.
Provides UI layout items, category flattening, and serialization for Qt settings screens.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Union

_registered = {}


def _norm_text(text: Optional[str], title: Optional[str]) -> str:
    if text is not None and text != "":
        return str(text)
    if title is not None:
        return str(title)
    return ""


def _norm_subtext(subtext: Optional[str], subtitle: Optional[str], hint: Optional[str]) -> Optional[str]:
    if subtext is not None and subtext != "":
        return str(subtext)
    if subtitle is not None and subtitle != "":
        return str(subtitle)
    if hint is not None and hint != "":
        return str(hint)
    return None


class Header:
    def __init__(self, text: str = "", title: Optional[str] = None, **kwargs):
        self.text = _norm_text(text, title)


class Divider:
    def __init__(self, text: Optional[str] = None, title: Optional[str] = None, **kwargs):
        norm = _norm_text(text, title)
        self.text = norm if norm else None


class Switch:
    def __init__(self, key: str = "", text: str = "", default: bool = False,
                 subtext: Optional[str] = None, icon: Optional[str] = None,
                 on_change: Optional[Callable] = None, on_long_click: Optional[Callable] = None,
                 link_alias: Optional[str] = None, title: Optional[str] = None,
                 subtitle: Optional[str] = None, get_value: Optional[Callable] = None, **kwargs):
        self.key = key or kwargs.get("id", "")
        self.text = _norm_text(text, title)
        self.subtext = _norm_subtext(subtext, subtitle, None)
        self.default = bool(default)
        self.icon = icon
        self.on_change = on_change
        self.on_long_click = on_long_click
        self.link_alias = link_alias
        self.get_value = get_value


class Selector:
    def __init__(self, key: str = "", text: str = "", default: Union[int, str] = 0,
                 items: Optional[List[str]] = None, subtext: Optional[str] = None,
                 icon: Optional[str] = None, on_change: Optional[Callable] = None,
                 on_long_click: Optional[Callable] = None, link_alias: Optional[str] = None,
                 title: Optional[str] = None, subtitle: Optional[str] = None,
                 options: Optional[Union[Dict[str, str], List[str]]] = None,
                 get_value: Optional[Callable] = None, **kwargs):
        self.key = key or kwargs.get("id", "")
        self.text = _norm_text(text, title)
        self.subtext = _norm_subtext(subtext, subtitle, None)
        self.icon = icon
        self.on_change = on_change
        self.on_long_click = on_long_click
        self.link_alias = link_alias
        self.get_value = get_value

        self.options_map: Dict[str, str] = {}
        self.options_keys: List[str] = []
        if isinstance(options, dict):
            self.options_map = dict(options)
            self.items = list(options.values())
            self.options_keys = list(options.keys())
        elif isinstance(options, (list, tuple)):
            self.items = [str(x) for x in options]
            self.options_keys = [str(i) for i in range(len(options))]
        elif items is not None:
            self.items = [str(x) for x in items]
            self.options_keys = [str(i) for i in range(len(items))]
        else:
            self.items = []
            self.options_keys = []

        self.default = default


class Input:
    def __init__(self, key: str = "", text: str = "", default: Optional[str] = None,
                 subtext: Optional[str] = None, icon: Optional[str] = None,
                 on_change: Optional[Callable] = None, on_long_click: Optional[Callable] = None,
                 link_alias: Optional[str] = None, title: Optional[str] = None,
                 subtitle: Optional[str] = None, hint: Optional[str] = None,
                 on_save: Optional[Callable] = None, get_value: Optional[Callable] = None, **kwargs):
        self.key = key or kwargs.get("id", "")
        self.text = _norm_text(text, title or hint)
        self.hint = hint or self.text
        self.subtext = _norm_subtext(subtext, subtitle, hint)
        self.default = str(default) if default is not None else None
        self.icon = icon
        self.on_change = on_save or on_change
        self.on_long_click = on_long_click
        self.link_alias = link_alias
        self.get_value = get_value


class EditText(Input):
    def __init__(self, key: str = "", hint: str = "", default: str = "",
                 multiline: bool = False, max_length: Optional[int] = None,
                 mask: Optional[str] = None, on_change: Optional[Callable] = None,
                 text: Optional[str] = None, title: Optional[str] = None,
                 subtext: Optional[str] = None, subtitle: Optional[str] = None,
                 on_save: Optional[Callable] = None, get_value: Optional[Callable] = None, **kwargs):
        super().__init__(
            key=key,
            text=text or title or hint,
            default=default,
            subtext=subtext,
            hint=hint,
            title=title,
            subtitle=subtitle,
            on_change=on_change,
            on_save=on_save,
            get_value=get_value,
            **kwargs
        )
        self.multiline = bool(multiline)
        self.max_length = max_length
        self.mask = mask


class Text:
    def __init__(self, text: str = "", subtext: Optional[str] = None,
                 icon: Optional[str] = None, accent: bool = False, red: bool = False,
                 on_click: Optional[Callable] = None, on_long_click: Optional[Callable] = None,
                 create_sub_fragment: Optional[Callable[[], list]] = None,
                 link_alias: Optional[str] = None, title: Optional[str] = None,
                 subtitle: Optional[str] = None, **kwargs):
        self.text = _norm_text(text, title)
        self.subtext = _norm_subtext(subtext, subtitle, None)
        self.icon = icon
        self.accent = bool(accent)
        self.red = bool(red)
        self.on_click = on_click
        self.on_long_click = on_long_click
        self.create_sub_fragment = create_sub_fragment
        self.link_alias = link_alias


class Category(Header):
    def __init__(self, text: str = "", title: Optional[str] = None, items: Optional[List[Any]] = None, **kwargs):
        super().__init__(text=text, title=title, **kwargs)
        self.items = list(items or kwargs.get("sub_items") or [])


class Button(Text):
    def __init__(self, text: str = "", title: Optional[str] = None, on_click: Optional[Callable] = None,
                 subtext: Optional[str] = None, icon: Optional[str] = None, **kwargs):
        super().__init__(text=text, title=title, on_click=on_click, subtext=subtext,
                         icon=icon, accent=kwargs.get("accent", True), **kwargs)


class ColorPicker:
    def __init__(self, key: str = "", text: str = "", default: Union[int, str] = "#FFFFFF",
                 subtext: Optional[str] = None, icon: Optional[str] = None,
                 on_change: Optional[Callable] = None, title: Optional[str] = None,
                 subtitle: Optional[str] = None, get_value: Optional[Callable] = None, **kwargs):
        self.key = key or kwargs.get("id", "")
        self.text = _norm_text(text, title)
        self.subtext = _norm_subtext(subtext, subtitle, None)
        self.default = default
        self.icon = icon
        self.on_change = on_change
        self.get_value = get_value


class MultiChoice:
    def __init__(self, key: str = "", text: str = "", items: Optional[List[str]] = None,
                 default: Optional[List[int]] = None, subtext: Optional[str] = None,
                 icon: Optional[str] = None, on_change: Optional[Callable] = None,
                 title: Optional[str] = None, subtitle: Optional[str] = None,
                 get_value: Optional[Callable] = None, **kwargs):
        self.key = key or kwargs.get("id", "")
        self.text = _norm_text(text, title)
        self.subtext = _norm_subtext(subtext, subtitle, None)
        self.items = [str(x) for x in (items or ())]
        self.default = list(default or ())
        self.icon = icon
        self.on_change = on_change
        self.get_value = get_value


class Slider:
    def __init__(self, key: str = "", text: str = "", default: float = 0,
                 min: float = 0, max: float = 100, step: float = 1,
                 subtext: Optional[str] = None, icon: Optional[str] = None,
                 on_change: Optional[Callable] = None, on_long_click: Optional[Callable] = None,
                 link_alias: Optional[str] = None, title: Optional[str] = None,
                 subtitle: Optional[str] = None, get_value: Optional[Callable] = None, **kwargs):
        self.key = key or kwargs.get("id", "")
        self.text = _norm_text(text, title)
        self.subtext = _norm_subtext(subtext, subtitle, None)
        self.default = float(default)
        self.min = float(min)
        self.max = float(max)
        self.step = float(step)
        self.icon = icon
        self.on_change = on_change
        self.on_long_click = on_long_click
        self.link_alias = link_alias
        self.get_value = get_value


class Custom:
    def __init__(self, item: Optional[Any] = None, view: Optional[Any] = None,
                 factory: Optional[Any] = None, factory_args: Optional[tuple] = None,
                 on_click: Optional[Callable] = None, on_long_click: Optional[Callable] = None,
                 create_sub_fragment: Optional[Callable[[], list]] = None,
                 link_alias: Optional[str] = None, **kwargs):
        self.item = item
        self.view = view
        self.factory = factory
        self.factory_args = factory_args
        self.on_click = on_click
        self.on_long_click = on_long_click
        self.create_sub_fragment = create_sub_fragment
        self.link_alias = link_alias


class _FactoryPeer:
    def __init__(self, factory):
        self.java = factory
        self.instance = factory


class SimpleSettingFactory:
    def __init__(self, create_view=None, bind_view=None, is_clickable: bool = False,
                 is_shadow: bool = False, create_item=None, on_click=None,
                 on_long_click=None, attached_view=None, equals=None,
                 content_equals=None):
        self.create_view = create_view
        self.bind_view = bind_view
        self.is_clickable = is_clickable
        self.is_shadow = is_shadow
        self.create_item = create_item
        self.on_click = on_click
        self.on_long_click = on_long_click
        self.attached_view = attached_view
        self.equals = equals
        self.content_equals = content_equals

    @property
    def instance(self):
        return _FactoryPeer(self)

    @property
    def java(self):
        return _FactoryPeer(self)

    @classmethod
    def getInstance(cls):
        return _FactoryPeer(None)

    def __getattr__(self, item):
        return lambda *args, **kwargs: None

    def __call__(self, *factory_args, link_alias: Optional[str] = None) -> Custom:
        return Custom(factory=self,
                      factory_args=factory_args or None,
                      link_alias=link_alias)


PluginItemFactory = SimpleSettingFactory


def _flatten_items(items: List[Any]) -> List[Any]:
    flat = []
    for it in items:
        if type(it).__name__.lower() == "category":
            flat.append(Header(it.text))
            if hasattr(it, "items") and isinstance(it.items, (list, tuple)):
                flat.extend(_flatten_items(it.items))
        else:
            flat.append(it)
    return flat


def register_items(plugin_id: str, items: List[Any]):
    _registered[plugin_id] = _flatten_items(items)


def unregister_items(plugin_id: str):
    _registered.pop(plugin_id, None)


def find_item(plugin_id: str, index: int) -> Optional[Any]:
    items = _registered.get(plugin_id, [])
    if 0 <= index < len(items):
        return items[index]
    return None


def describe(item: Any, index: int) -> Optional[Dict[str, Any]]:
    raw_kind = type(item).__name__.lower()
    if raw_kind == "custom":
        return None

    # Wire-format mapping for C++ Settings UI
    kind = raw_kind
    if raw_kind == "button":
        kind = "text"
    elif raw_kind == "colorpicker":
        kind = "input"
    elif raw_kind == "multichoice":
        kind = "selector"

    data = {"index": index, "kind": kind}
    for key in ("text", "subtext", "key", "default", "items", "hint",
                "multiline", "max_length", "mask", "accent", "red", "icon",
                "min", "max", "step"):
        if not hasattr(item, key):
            continue
        value = getattr(item, key)
        if value is not None and not callable(value):
            data[key] = value

    if raw_kind == "multichoice" and hasattr(item, "options"):
        data["items"] = list(item.options)

    # Dynamic value evaluation via get_value
    get_val = getattr(item, "get_value", None)
    if callable(get_val):
        try:
            val = get_val()
            if val is not None:
                data["value"] = val
                data["default"] = val
        except Exception:
            pass

    # Normalize Selector default/value to integer index for UI
    if kind == "selector":
        cur_val = data.get("value", data.get("default", 0))
        keys = getattr(item, "options_keys", getattr(item, "options", []))
        if keys and isinstance(cur_val, str) and cur_val in keys:
            data["default"] = keys.index(cur_val)
        elif isinstance(cur_val, int):
            data["default"] = cur_val

    data["clickable"] = bool(getattr(item, "on_click", None) or raw_kind == "button")
    data["long_clickable"] = bool(getattr(item, "on_long_click", None))
    return data
