from typing import List, Callable, Optional, Any, Union, Dict, Iterable

from typing_extensions import deprecated

from java import dynamic_proxy, jint
from java.util import ArrayList
from java.lang import Runnable as JRunnable
from java.lang.reflect import Method, Constructor
from android.os import Bundle
from org.telegram.messenger import Utilities

from .logs import _logger


class SingletonMeta(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            instance = super().__call__(*args, **kwargs)
            cls._instances[cls] = instance
        return cls._instances[cls]


class Callback1(dynamic_proxy(Utilities.Callback)):
    def __init__(self, fn: Callable[[Any], None]):
        super().__init__()
        self._fn = fn

    def run(self, arg):
        try:
            self._fn(arg)
        except Exception:
            _logger.error("Error in Callback1.", exc_info=True)


def arraylist_to_list(j_array_list: Optional[ArrayList]) -> Optional[List]:
    return j_array_list.toArray() if j_array_list else None


def iterable_to_arraylist(iterable: Optional[Iterable[Any]], int_auto_convert=True) -> Optional[ArrayList]:
    if iterable is None:
        return None

    arraylist = ArrayList()
    for obj in list(iterable):
        if int_auto_convert and isinstance(obj, int):
            try:
                arraylist.add(jint(obj))
                continue
            except OverflowError:
                pass
        arraylist.add(obj)

    return arraylist


@deprecated("Function list_to_arraylist(list[any], bool) is deprecated. Use iterable_to_arraylist(iterable[any], bool) instead")
def list_to_arraylist(python_list: Optional[List], int_auto_convert=True):
    iterable_to_arraylist(python_list, int_auto_convert)


class PyRunnable(dynamic_proxy(JRunnable)):
    def __init__(self, fn: Callable[[Any], None]):
        super().__init__()
        self.fn = fn

    def run(self):
        try:
            self.fn()
        except Exception:
            _logger.error("Error in PyRunnable:", exc_info=True)


def create_bundle(args: Dict[str, Union[bool, int, str, float]]) -> Bundle:
    bundle = Bundle()
    methods = {
        int: bundle.putInt,
        bool: bundle.putBoolean,
        str: bundle.putString,
        float: bundle.putFloat,
    }

    for k, v in args.items():
        if method := methods.get(type(v), None):
            method(k, v)
    return bundle


def _get_type_name(obj) -> str:
    return type(obj).__name__


def _get_reflection_member_name(member: Union[Method, Constructor]) -> str:
    if isinstance(member, Method):
        return member.getName()
    elif isinstance(member, Constructor):
        return f"{member.getDeclaringClass().getName()} ({member.getParameterCount()} args)"
    return "unknown"


def _hook_filters_to_arraylist(filters: Union[Callable, List, None], hook_instance: Any) -> ArrayList:
    if callable(filters):
        filters = filters(hook_instance)
    return iterable_to_arraylist(filters or [], int_auto_convert=False)
