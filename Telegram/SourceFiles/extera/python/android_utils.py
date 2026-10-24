from typing import Any, Callable

import _extera


def log(data: Any):
    _extera.log(str(data))


def run_on_ui_thread(fn: Callable, delay: int = 0):
    _extera.run_on_main(fn, int(delay or 0))


def copy_to_clipboard(text: str) -> bool:
    _extera.copy(str(text))
    return True


class OnClickListener:
    def __init__(self, fn: Callable):
        self.fn = fn

    def onClick(self, view=None):
        self.fn(view)


class OnLongClickListener:
    def __init__(self, fn: Callable):
        self.fn = fn

    def onLongClick(self, view=None):
        return bool(self.fn(view))


class R:
    def __getattr__(self, item):
        return 0


R = R()
