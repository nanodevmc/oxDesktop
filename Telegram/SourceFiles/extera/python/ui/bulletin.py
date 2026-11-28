import _extera


class BulletinHelper:
    DURATION_SHORT = 1500
    DURATION_LONG = 2750
    DURATION_PROLONG = 5000

    @classmethod
    def show_info(cls, message: str, fragment=None):
        _extera.toast(str(message))

    @classmethod
    def show_error(cls, message: str, fragment=None):
        _extera.toast(str(message))

    @classmethod
    def show_success(cls, message: str, fragment=None):
        _extera.toast(str(message))

    @classmethod
    def show_simple(cls, text: str, icon_res_id: int = 0, fragment=None):
        _extera.toast(str(text))

    @classmethod
    def show_two_line(cls, title: str, subtitle: str, icon_res_id: int = 0, fragment=None):
        _extera.toast(f"{title}\n{subtitle}" if subtitle else str(title))
