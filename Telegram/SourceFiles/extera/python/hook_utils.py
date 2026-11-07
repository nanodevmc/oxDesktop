from typing import Any, Callable, List, Optional, Union
import sys

def find_class(name: str) -> Any:
    import _compat
    import exd_java
    found = exd_java.lookup(str(name))
    if found is not None:
        return found
    return _compat.Missing(str(name))


def _as_class(obj):
    return obj


def get_private_field(obj: Any, name: str) -> Any:
    if obj is None:
        return None
    try:
        return getattr(obj, name, None)
    except Exception:
        return None


def set_private_field(obj: Any, name: str, value: Any) -> bool:
    if obj is None:
        return False
    try:
        setattr(obj, name, value)
        return True
    except Exception:
        return False


def get_static_private_field(clazz: Any, name: str) -> Any:
    if clazz is None:
        return None
    try:
        return getattr(clazz, name, None)
    except Exception:
        return None


def set_static_private_field(clazz: Any, name: str, value: Any) -> bool:
    if clazz is None:
        return False
    try:
        setattr(clazz, name, value)
        return True
    except Exception:
        return False


get_field = get_private_field
set_field = set_private_field


class HookUtils:
    """oxDesktop Xposed Hook Utils with Crash Guard and Security Shield."""

    @classmethod
    def find_class(cls, name: str) -> Any:
        return find_class(name)

    @classmethod
    def get_private_field(cls, obj: Any, name: str) -> Any:
        return get_private_field(obj, name)

    @classmethod
    def set_private_field(cls, obj: Any, name: str, value: Any) -> bool:
        return set_private_field(obj, name, value)

    @classmethod
    def get_static_private_field(cls, clazz: Any, name: str) -> Any:
        return get_static_private_field(clazz, name)

    @classmethod
    def set_static_private_field(cls, clazz: Any, name: str, value: Any) -> bool:
        return set_static_private_field(clazz, name, value)

    @classmethod
    def find_method_by_args_count(cls, clazz: Any, method_name: str, args_count: int = 0) -> Any:
        if not clazz:
            return None
        import exd_java
        return exd_java.ShimMethod(clazz, method_name)

    @classmethod
    def find_method_by_args(cls, clazz: Any, method_name: str, python_arg_types: List[Any]) -> Any:
        if not clazz:
            return None
        import exd_java
        return exd_java.ShimMethod(clazz, method_name)

    @classmethod
    def hook(
        cls,
        plugin_id: str,
        method_or_constructor: Any,
        xposed_hook: Optional[Any] = None,
        priority: Optional[int] = None,
        *,
        before: Optional[Callable] = None,
        after: Optional[Callable] = None,
        before_filters: Optional[List[Any]] = None,
        after_filters: Optional[List[Any]] = None
    ) -> Any:
        import exd_java
        import base_plugin
        import extera_host

        if extera_host._safe_mode:
            extera_host.log(f"[{plugin_id}] Hook skipped in Safe Mode")
            return None

        handler = xposed_hook
        if handler is None and (before or after):
            handler = base_plugin.BaseHook(None, before=before, after=after)

        target_cls = getattr(method_or_constructor, "_class", None) or getattr(method_or_constructor, "declaringClass", None)
        target_name = getattr(method_or_constructor, "_name", None) or getattr(method_or_constructor, "name", None)

        if not target_cls or not target_name:
            if isinstance(method_or_constructor, str):
                target_name = method_or_constructor
                target_cls = getattr(xposed_hook, "__class__", object)

        if target_cls and target_name:
            hook_id = exd_java.hook_shim(target_cls, str(target_name), plugin_id, handler, priority or 50)
            return base_plugin.UnhookId(hook_id)
        return None

    @classmethod
    def unhook(cls, unhook_obj: Any, plugin_id: Optional[str] = None):
        if unhook_obj is None:
            return
        import exd_java
        exd_java.unhook_shim(str(unhook_obj), plugin_id=plugin_id)
