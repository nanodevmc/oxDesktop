import colorsys
import json
import unicodedata

LATIN = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
CYR = "АБВГДЕЖЗИЙКЛМНОПРСТУФХЦЧШЩЭЮЯ"
HASH = "#"
PIN_PREFIX = "\x01pin:"

XMAP = {
    "А": "A", "Б": "B", "В": "VW", "Г": "GH", "Д": "D", "Е": "E", "Ж": "JZ", "З": "Z", "И": "I",
    "Й": "YJ", "К": "KCQ", "Л": "L", "М": "M", "Н": "N", "О": "O", "П": "P", "Р": "R", "С": "SC",
    "Т": "T", "У": "UY", "Ф": "F", "Х": "HX", "Ц": "C", "Ч": "C", "Ш": "S", "Щ": "S", "Э": "E",
    "Ю": "YU", "Я": "Y", "Ы": "Y",
}
FOLD = {"Ё": "Е", "Є": "Е", "І": "И", "Ї": "И", "Ґ": "Г", "Ы": "И"}

FONTS = [
    ("wave_font_light", "sans-serif-light", 0),
    ("wave_font_regular", "sans-serif", 0),
    ("wave_font_medium", "sans-serif-medium", 0),
    ("wave_font_bold", "sans-serif", 1),
    ("wave_font_cond", "sans-serif-condensed", 0),
    ("wave_font_thin", "sans-serif-thin", 0),
    ("wave_font_black", "sans-serif-black", 0),
    ("wave_font_italic", "sans-serif", 2),
    ("wave_font_serif", "serif", 0),
    ("wave_font_mono", "monospace", 0),
    ("wave_font_casual", "casual", 0),
    ("wave_font_script", "cursive", 0),
]
FONT_CUSTOM = 100


def is_cyr(u):
    return "Ѐ" <= u <= "ӿ"


def fold(ch):
    u = ch.upper()
    if u in FOLD:
        return FOLD[u]
    if ord(u[0]) < 0x250:
        base = unicodedata.normalize("NFD", u)[0]
        if "A" <= base <= "Z":
            return base
    return u


def alphabet_letters(lang):
    return CYR if int(lang) == 0 else LATIN


def first_keys(title, word_mode=False):
    out = []
    new = True
    for ch in str(title or ""):
        if ch.isalnum():
            if new:
                out.append(fold(ch) if ch.isalpha() else "0")
                if not word_mode:
                    return out
            new = False
        else:
            new = True
    return out


def key_hit(u, key, xscript):
    if u == key:
        return True
    if not xscript:
        return False
    if is_cyr(key):
        return u in XMAP.get(key, "")
    if is_cyr(u):
        return key in XMAP.get(u, "")
    return False


def matches(title, key, letters, xscript=True, word_mode=False):
    us = first_keys(title, word_mode)
    if key == HASH:
        if not us:
            return True
        return any(u == "0" or not any(key_hit(u, k, xscript) for k in letters) for u in us)
    return any(u != "0" and key_hit(u, key, xscript) for u in us)


def pins_load(raw):
    try:
        data = json.loads(raw) if raw else []
    except Exception:
        data = []
    out = []
    for p in data if isinstance(data, list) else []:
        try:
            s = str(p.get("s", "")).strip()[:8]
            if not s:
                continue
            ids = []
            for x in p.get("ids", []):
                try:
                    ids.append(int(x))
                except Exception:
                    pass
            out.append({"s": s, "ids": ids, "pos": 1 if int(p.get("pos", 0)) == 1 else 0})
        except Exception:
            pass
    return out[:12]


def pins_dump(pins):
    return json.dumps([{"s": p["s"], "ids": [int(i) for i in p["ids"]], "pos": int(p["pos"])} for p in pins[:12]],
                      ensure_ascii=False)


def pin_index(key):
    try:
        return int(str(key)[len(PIN_PREFIX):])
    except Exception:
        return -1


def build_items(lang, hash_on, hash_pos, pins, lower=False):
    top = [(p["s"], PIN_PREFIX + str(i)) for i, p in enumerate(pins) if p["pos"] == 0]
    bot = [(p["s"], PIN_PREFIX + str(i)) for i, p in enumerate(pins) if p["pos"] == 1]
    letters = [((c.lower() if lower else c), c) for c in alphabet_letters(lang)]
    mid_top = [(HASH, HASH)] if hash_on and int(hash_pos) == 0 else []
    mid_bot = [(HASH, HASH)] if hash_on and int(hash_pos) == 1 else []
    return top + mid_top + letters + mid_bot + bot


def parse_hex(s, default=None):
    s = str(s or "").strip().lstrip("#")
    try:
        if len(s) == 6:
            return 0xFF000000 | int(s, 16)
        if len(s) == 8:
            return int(s, 16)
    except Exception:
        pass
    return default


def hsv_to_rgb_int(h, s, v):
    r, g, b = colorsys.hsv_to_rgb(max(0.0, min(1.0, h)), max(0.0, min(1.0, s)), max(0.0, min(1.0, v)))
    return 0xFF000000 | (int(round(r * 255)) << 16) | (int(round(g * 255)) << 8) | int(round(b * 255))


def rgb_int_to_hsv(c):
    c = int(c)
    return colorsys.rgb_to_hsv(((c >> 16) & 255) / 255.0, ((c >> 8) & 255) / 255.0, (c & 255) / 255.0)


def to_hex(c):
    return "#%06X" % (int(c) & 0xFFFFFF)


def luminance(c):
    c = int(c)
    return ((c >> 16) & 255) * 0.299 + ((c >> 8) & 255) * 0.587 + (c & 255) * 0.114
