import sys
import types
import asyncio
import threading
from asyncio import Future
from collections import defaultdict
from typing import List, Callable, Optional, Any, Dict, Coroutine, Set

from ..core.meta import __id__, _ASYNC_SHARED_KEY, _get_plugin_id_from_stack
from .logs import _logger, _async_logger


class _AsyncMarker:
    def __init__(self, obj, success_method: str, error_method: Optional[str] = None):
        self.obj = obj
        self.success_method = success_method
        self.error_method = error_method


def _wrap_callback_methods(marker: _AsyncMarker, future: Future):
    target_obj = marker.obj

    def get_and_save_original(method_name: str) -> Callable:
        original_attr_name = f"__zwy_orig_{method_name}"

        if hasattr(target_obj, original_attr_name):
            return getattr(target_obj, original_attr_name)

        original_method = getattr(target_obj, method_name)
        setattr(target_obj, original_attr_name, original_method)
        return original_method

    pure_success = get_and_save_original(marker.success_method)

    def wrapped_success(*cb_args):
        pure_success(*cb_args)
        res = cb_args[0] if len(cb_args) == 1 else cb_args
        _safe_set_future_result(future, res)

    setattr(target_obj, marker.success_method, wrapped_success)

    if marker.error_method:
        pure_error = get_and_save_original(marker.error_method)

        def wrapped_error(*cb_args):
            pure_error(*cb_args)
            err_msg = "Java error: " + " ".join(map(str, cb_args))
            _safe_set_future_exception(future, Exception(err_msg))

        setattr(target_obj, marker.error_method, wrapped_error)


def _get_async_shared_state():
    state = sys.modules.get(_ASYNC_SHARED_KEY)
    if state is None:
        state = types.ModuleType(_ASYNC_SHARED_KEY)
        state.loop = None
        state.thread = None
        state.lock = threading.Lock()
        state = sys.modules.setdefault(_ASYNC_SHARED_KEY, state)
    return state


class _AsyncManager:
    def __init__(self):
        self._shared = _get_async_shared_state()
        with self._shared.lock:
            loop = self._shared.loop
            if loop is None or loop.is_closed():
                loop = asyncio.new_event_loop()
                self._shared.loop = loop
                self._shared.thread = None
        self.loop = loop
        self.tasks: Dict[str, Set[asyncio.Task]] = defaultdict(set)

    @property
    def thread(self) -> Optional[threading.Thread]:
        return self._shared.thread

    @property
    def started(self) -> bool:
        thread = self._shared.thread
        return thread is not None and thread.is_alive()

    def _run_event_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def start(self):
        with self._shared.lock:
            thread = self._shared.thread
            if thread is not None and thread.is_alive():
                _async_logger.warning("Async thread is already started.")
                return
            thread = threading.Thread(target=self._run_event_loop, daemon=True, name="ZwyAsyncThread")
            self._shared.thread = thread
            thread.start()
        _async_logger.debug("Async thread has been started.")

    def stop(self):
        cancelled = 0
        for plugin_id in list(self.tasks.keys()):
            tasks_to_cancel = self.tasks[plugin_id].copy()
            for task in tasks_to_cancel:
                # noinspection PyTypeChecker
                self.loop.call_soon_threadsafe(task.cancel)
            self.tasks[plugin_id].clear()
            cancelled += len(tasks_to_cancel)
        _async_logger.debug(f"Async manager stopped, cancelled {cancelled} tasks.")

    def run_task(self, coro: Coroutine):
        if not self.started:
            self.start()

        plugin_id = _get_plugin_id_from_stack(__id__)

        async def task_wrapper():
            current_task = asyncio.current_task()
            self.tasks[plugin_id].add(current_task)

            try:
                return await coro
            except asyncio.CancelledError:
                _async_logger.debug(f"One of '{plugin_id}' tasks was cancelled.")
                raise
            except Exception:
                _async_logger.error(f"Error in '{plugin_id}' task:", exc_info=True)
            finally:
                self.tasks[plugin_id].discard(current_task)

        return asyncio.run_coroutine_threadsafe(task_wrapper(), self.loop)

    def cancel_all_tasks(self):
        self.cancel_all_for(_get_plugin_id_from_stack(__id__))

    def cancel_all_for(self, plugin_id: str):
        tasks_to_cancel = self.tasks.get(plugin_id, set()).copy()
        if not tasks_to_cancel:
            return

        for task in tasks_to_cancel:
            # noinspection PyTypeChecker
            self.loop.call_soon_threadsafe(task.cancel)
        self.tasks[plugin_id].clear()

        _async_logger.debug(f"Cancelled {len(tasks_to_cancel)} tasks for '{plugin_id}'.")

    @staticmethod
    def as_callback(callback_obj, success, error=None):
        return _AsyncMarker(callback_obj, success, error)

    async def wrap_java_call(self, java_method, *args, **kwargs):
        loop = asyncio.get_running_loop()
        future = loop.create_future()

        mutable_args = list(args)
        for i, arg in enumerate(mutable_args):
            if isinstance(arg, _AsyncMarker):
                _wrap_callback_methods(arg, future)
                mutable_args[i] = arg.obj
                break

        try:
            java_method(*mutable_args, **kwargs)
        except Exception as e:
            if not future.done():
                future.set_exception(e)

        return await future


def safe_func_call(func: Optional[Callable], args: Optional[List[Any]] = None) -> Any:
    if func is None:
        return None

    args = args or []

    try:
        result = func(*args)
        if asyncio.iscoroutine(result):
            return async_manager.run_task(result)
        return result
    except Exception:
        _logger.error("An error occurred when tried to call func safely:", exc_info=True)
        return None


def _safe_set_future_result(future: Future, result: Any) -> None:
    if future.done():
        return

    try:
        loop = future.get_loop()
        if loop.is_closed():
            return

        loop.call_soon_threadsafe(future.set_result, result)
    except Exception:
        _async_logger.error("Failed to set future result:", exc_info=True)


def _safe_set_future_exception(future: Future, exc: BaseException) -> None:
    if future.done():
        return

    try:
        loop = future.get_loop()
        if loop.is_closed():
            return

        loop.call_soon_threadsafe(future.set_exception, exc)
    except Exception:
        _async_logger.error("Failed to set future exception:", exc_info=True)


async_manager = _AsyncManager()
