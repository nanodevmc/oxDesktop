from typing import List, Callable, Optional, Any, Union

from base_plugin import MethodHook, XposedHook, BaseHook, MethodReplacement

from java.chaquopy import JavaClass
from java.lang import Object as JObject, Class as JClass
from java.lang.reflect import Member, Method
from com.exteragram.messenger import ExteraConfig
from com.exteragram.messenger.plugins import PluginsController, PluginsConstants
from com.exteragram.messenger.plugins.xposed import PyMethodHook, PyMethodReplacement
from de.robv.android.xposed import XposedBridge, XC_MethodHook

from ..core.meta import __id__, _get_plugin_id_from_stack
from .async_tools import safe_func_call
from .java_utils import _get_type_name, _get_reflection_member_name, _hook_filters_to_arraylist
from .logs import _logger, _hu_logger


def _wrap_hook_callback(
        member: Member,
        callback: Callable[[XC_MethodHook.MethodHookParam], None]
) -> Callable[[XC_MethodHook.MethodHookParam], None]:
    def wrapped_hook_callback(param):
        try:
            return safe_func_call(callback, [param])
        except Exception:
            _hu_logger.error(f"An unexpected error occurred in '{_get_reflection_member_name(member)}' hook:", exc_info=True)
            return None
    return wrapped_hook_callback


class HookUtils:
    @classmethod
    def __get_java_callback_instance(
            cls,
            plugin_id: str,
            xposed_hook: Optional[Any] = None,
            priority: Optional[int] = None,
            *,
            before: Optional[Callable] = None,
            after: Optional[Callable] = None,
            before_filters: Optional[List[Any]] = None,
            after_filters: Optional[List[Any]] = None
    ):
        if xposed_hook is None and before is None and after is None:
            raise TypeError("xposed_hook or before or after cannot be None")

        if ExteraConfig.pluginsSafeMode:
            return None

        java_callback_instance = None

        if xposed_hook:
            if isinstance(xposed_hook, MethodReplacement):
                if priority is not None:
                    java_callback_instance = PyMethodReplacement(plugin_id, xposed_hook, priority)
                else:
                    java_callback_instance = PyMethodReplacement(plugin_id, xposed_hook)
            elif isinstance(xposed_hook, MethodHook):
                if priority is not None:
                    java_callback_instance = PyMethodHook(plugin_id, xposed_hook, priority)
                else:
                    java_callback_instance = PyMethodHook(plugin_id, xposed_hook)

                if hasattr(method := getattr(xposed_hook, PluginsConstants.Xposed.BEFORE_HOOKED_METHOD, None), PluginsConstants.Xposed.HOOK_FILTERS):
                    java_callback_instance.setBeforeHookedFilters(_hook_filters_to_arraylist(getattr(method, PluginsConstants.Xposed.HOOK_FILTERS), xposed_hook))
                if hasattr(method := getattr(xposed_hook, PluginsConstants.Xposed.AFTER_HOOKED_METHOD, None), PluginsConstants.Xposed.HOOK_FILTERS):
                    java_callback_instance.setAfterHookedFilters(_hook_filters_to_arraylist(getattr(method, PluginsConstants.Xposed.HOOK_FILTERS), xposed_hook))
            elif hasattr(xposed_hook, PluginsConstants.Xposed.REPLACE_HOOKED_METHOD):
                if priority is not None:
                    java_callback_instance = PyMethodReplacement(plugin_id, xposed_hook, priority)
                else:
                    java_callback_instance = PyMethodReplacement(plugin_id, xposed_hook)
            elif hasattr(xposed_hook, PluginsConstants.Xposed.BEFORE_HOOKED_METHOD) or hasattr(xposed_hook, PluginsConstants.Xposed.AFTER_HOOKED_METHOD):
                if priority is not None:
                    java_callback_instance = PyMethodHook(plugin_id, xposed_hook, priority)
                else:
                    java_callback_instance = PyMethodHook(plugin_id, xposed_hook)

                if hasattr(method := getattr(xposed_hook, PluginsConstants.Xposed.BEFORE_HOOKED_METHOD, None), PluginsConstants.Xposed.HOOK_FILTERS):
                    java_callback_instance.setBeforeHookedFilters(_hook_filters_to_arraylist(getattr(method, PluginsConstants.Xposed.HOOK_FILTERS), xposed_hook))
                if hasattr(method := getattr(xposed_hook, PluginsConstants.Xposed.AFTER_HOOKED_METHOD, None), PluginsConstants.Xposed.HOOK_FILTERS):
                    java_callback_instance.setAfterHookedFilters(_hook_filters_to_arraylist(getattr(method, PluginsConstants.Xposed.HOOK_FILTERS), xposed_hook))
        elif (before or after) and (not before or isinstance(before, Callable)) and (not after or isinstance(after, Callable)):
            base_hook = BaseHook(None, before=before, after=after, before_filters=before_filters, after_filters=after_filters)
            args = [base_hook]
            if priority is not None:
                args.append(priority)

            java_callback_instance = PyMethodHook(plugin_id, *args)

            if before_filters:
                java_callback_instance.setBeforeHookedFilters(_hook_filters_to_arraylist(getattr(base_hook.before_hooked_method, PluginsConstants.Xposed.HOOK_FILTERS), base_hook))
            if after_filters:
                java_callback_instance.setAfterHookedFilters(_hook_filters_to_arraylist(getattr(base_hook.after_hooked_method, PluginsConstants.Xposed.HOOK_FILTERS), base_hook))
        else:
            raise TypeError("xposed_hook or before or after cannot be None")

        return java_callback_instance

    @classmethod
    def hook(
            cls,
            plugin_id: str,
            method_or_constructor: Member,
            xposed_hook: Optional[Any] = None,
            priority: Optional[int] = None,
            *,
            before: Optional[Callable] = None,
            after: Optional[Callable] = None,
            before_filters: Optional[List[Any]] = None,
            after_filters: Optional[List[Any]] = None
    ) -> Optional[XC_MethodHook.Unhook]:
        if xposed_hook is None and before is None and after is None:
            raise TypeError("xposed_hook or before or after cannot be None")

        if ExteraConfig.pluginsSafeMode:
            return None

        unhook = None
        try:
            java_callback_instance = cls.__get_java_callback_instance(
                plugin_id, xposed_hook, priority, before=before, after=after,
                before_filters=before_filters, after_filters=after_filters
            )
            if java_callback_instance is not None:
                unhook = XposedBridge.hookMethod(method_or_constructor, java_callback_instance)
                PluginsController.getInstance().addXposedHook(plugin_id, unhook)
                return unhook
            else:
                _logger.error(f"Could not determine hook type for {type(xposed_hook or before or after).__name__}.")
                return None

        except Exception as e:
            _logger.error(f"Error while hooking method {method_or_constructor.getName()}: {e}")
            if unhook is not None:
                _logger.error("An error occurred after the hook was created, attempting to unhook it immediately.")
                unhook.unhook()
            return None

    @classmethod
    def unhook(cls, unhook: XC_MethodHook.Unhook, plugin_id: Optional[str] = None):
        plugin_id = plugin_id or _get_plugin_id_from_stack(__id__)
        PluginsController.getInstance().removeXposedHook(plugin_id, unhook)

    @classmethod
    def get_private_field(cls, obj: JObject, field_name: str) -> Optional[Any]:
        if not isinstance(obj, JObject) or not isinstance(field_name, str):
            return None

        try:
            field = None

            current_class = obj.getClass()
            while current_class is not None:
                try:
                    field = current_class.getDeclaredField(field_name)
                    break
                except Exception:
                    current_class = current_class.getSuperclass()

            if field is None:
                return None

            field.setAccessible(True)
            value = field.get(obj)
            return value
        except Exception:
            _logger.error(f"Error accessing field '{field_name}' on {obj}:", exc_info=True)
            return None

    @classmethod
    def find_method_by_args_count(cls, clazz: Union[JClass, JavaClass], method_name: str, args_count: int = 0) -> Optional[Method]:
        if not clazz or not isinstance(clazz, (JClass, JavaClass)):
            _hu_logger.warning(f"Error: got {_get_type_name(clazz)} instead of Class object")
            return None

        if isinstance(clazz, JavaClass):
            clazz = clazz.getClass()

        method = next((
            i for i in clazz.getDeclaredMethods()
            if i.getName() == method_name and i.getParameterCount() == args_count
        ), None)

        if not method:
            _hu_logger.warning(f"Cannot find method '{method_name}' for class '{clazz.getName()}' ({args_count} args).")
            return None

        method.setAccessible(True)
        return method

    @classmethod
    def find_method_by_args(cls, clazz: Union[JClass, JavaClass], method_name: str, python_arg_types: List[JClass]) -> Optional[Method]:
        if not clazz or not isinstance(clazz, (JClass, JavaClass)):
            _hu_logger.warning(f"Error: got {_get_type_name(clazz)} instead of Class object")
            return None

        if isinstance(clazz, JavaClass):
            clazz = clazz.getClass()

        def do_args_types_match(java_arg_types: List[JClass]):
            for py_arg, j_arg in zip(python_arg_types, list(java_arg_types)):
                if j_arg != py_arg:
                    return False
            return True

        method = next((
            i for i in clazz.getDeclaredMethods()
            if i.getName() == method_name and do_args_types_match(list(i.getParameterTypes()))
        ), None)

        if not method:
            _hu_logger.warning(f"Cannot find method '{method_name}' for class '{clazz.getName()}' ({python_arg_types}).")
            return None

        method.setAccessible(True)
        return method

    @classmethod
    def find_max_args_method(cls, clazz: Union[JClass, JavaClass], method_name: str):
        if not clazz or not isinstance(clazz, (JClass, JavaClass)):
            _hu_logger.warning(f"Error: got {_get_type_name(clazz)} instead of Class object")
            return None

        if isinstance(clazz, JavaClass):
            clazz = clazz.getClass()

        method = max(
            [i for i in clazz.getDeclaredMethods() if i.getName() == method_name],
            key=lambda i: i.getParameterCount(),
            default=None
        )

        if not method:
            _hu_logger.warning(f"Cannot find method '{method_name}' for class '{clazz.getName()}'.")
            return None

        method.setAccessible(True)
        return method

    @classmethod
    def hook_before(cls, member: Member, callback: Callable[[XC_MethodHook.MethodHookParam], None], **kwargs):
        if not isinstance(member, Member):
            _hu_logger.warning(f"Invalid 'member' parameter: expected Member instance, got {_get_type_name(member)}")
            return None

        if not callable(callback):
            _hu_logger.warning(f"Invalid 'callback' parameter: expected callable, got {_get_type_name(callback)}")
            return None

        kwargs.pop("before", None)
        return cls.hook(
            plugin_id=_get_plugin_id_from_stack(__id__),
            method_or_constructor=member,
            before=_wrap_hook_callback(member, callback),
            **kwargs
        )

    @classmethod
    def hook_after(cls, member: Member, callback: Callable[[XC_MethodHook.MethodHookParam], None], **kwargs):
        if not isinstance(member, Member):
            _hu_logger.warning(f"Invalid 'member' parameter: expected Member instance, got {_get_type_name(member)}")
            return None

        if not callable(callback):
            _hu_logger.warning(f"Invalid 'callback' parameter: expected callable, got {_get_type_name(callback)}")
            return None

        kwargs.pop("after", None)
        return cls.hook(
            plugin_id=_get_plugin_id_from_stack(__id__),
            method_or_constructor=member,
            after=_wrap_hook_callback(member, callback),
            **kwargs
        )

    @classmethod
    def hook_replace(cls, member: Member, callback: Callable[[XC_MethodHook.MethodHookParam], None], **kwargs):
        if not isinstance(member, Member):
            _hu_logger.warning(f"Invalid 'member' parameter: expected Member instance, got {_get_type_name(member)}")
            return None

        if not callable(callback):
            _hu_logger.warning(f"Invalid 'callback' parameter: expected callable, got {_get_type_name(callback)}")
            return None

        callback = _wrap_hook_callback(member, callback)

        class ReplaceHook(MethodReplacement):
            def replace_hooked_method(self, param):
                return callback(param)

        kwargs.pop("xposed_hook", None)
        return cls.hook(
            plugin_id=_get_plugin_id_from_stack(__id__),
            method_or_constructor=member,
            xposed_hook=ReplaceHook(),
            **kwargs
        )


# compatibility for plugins using zwylib <2.0.6
def hook_max_args_method(clazz: JClass, method_name: str, hook_instance: XposedHook):
    method = HookUtils.find_max_args_method(clazz, method_name)
    if not method:
        _hu_logger.warning(f"Failed to hook {method_name}.")
        return

    HookUtils.hook(
        _get_plugin_id_from_stack(__id__),
        method, hook_instance
    )
