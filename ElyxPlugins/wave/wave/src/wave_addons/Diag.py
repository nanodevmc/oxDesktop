import time

LINES = []
STATE = {}


def log(msg):
    try:
        LINES.append(time.strftime("%H:%M:%S ") + str(msg))
        del LINES[:-40]
    except Exception:
        pass
    try:
        from android_utils import log as _l
        _l(str(msg))
    except Exception:
        pass


def state(key, value):
    STATE[key] = value


def bump(key):
    STATE[key] = int(STATE.get(key, 0)) + 1


def report():
    out = ["%s: %s" % (k, STATE[k]) for k in sorted(STATE)]
    out.append("--")
    out.extend(LINES[-14:])
    return "\n".join(out)
