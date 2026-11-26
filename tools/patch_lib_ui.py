from __future__ import annotations

import pathlib
import sys


def patch_file(path: pathlib.Path, replacements: list[tuple[str, str, str]]) -> bool:
    if not path.exists():
        print(f"[patch_lib_ui] Missing file: {path}", file=sys.stderr)
        sys.exit(1)

    text = path.read_text(encoding="utf-8")
    original = text

    for old, new, already_marker in replacements:
        if already_marker in text:
            continue
        count = text.count(old)
        if count != 1:
            print(
                f"[patch_lib_ui] Expected 1 match in {path}, found {count} for:\n{old}",
                file=sys.stderr,
            )
            sys.exit(1)
        text = text.replace(old, new, 1)

    if text != original:
        path.write_text(text, encoding="utf-8")
        print(f"[patch_lib_ui] Patched {path}")
        return True

    print(f"[patch_lib_ui] Already patched: {path}")
    return False


def main() -> int:
    root = pathlib.Path(__file__).resolve().parent.parent
    lib_ui = root / "Telegram" / "lib_ui" / "ui" / "widgets"

    patch_file(
        lib_ui / "checkbox.h",
        [
            (
                "void SetMaterialSwitches(bool enabled);\n"
                "[[nodiscard]] bool MaterialSwitches();\n",
                "void SetMaterialSwitches(bool enabled);\n"
                "[[nodiscard]] bool MaterialSwitches();\n"
                "void SetMaterialDesign(bool enabled);\n"
                "[[nodiscard]] bool MaterialDesign();\n",
                "bool MaterialDesign();",
            ),
        ],
    )

    patch_file(
        lib_ui / "checkbox.cpp",
        [
            (
                "bool MaterialSwitchesEnabled = false;\n",
                "bool MaterialSwitchesEnabled = false;\n"
                "bool MaterialDesignEnabled = true;\n",
                "bool MaterialDesignEnabled =",
            ),
            (
                "bool MaterialSwitches() {\n"
                "\treturn MaterialSwitchesEnabled;\n"
                "}\n",
                "bool MaterialSwitches() {\n"
                "\treturn MaterialSwitchesEnabled;\n"
                "}\n\n"
                "void SetMaterialDesign(bool enabled) {\n"
                "\tMaterialDesignEnabled = enabled;\n"
                "}\n\n"
                "bool MaterialDesign() {\n"
                "\treturn MaterialDesignEnabled;\n"
                "}\n",
                "bool MaterialDesign() {",
            ),
        ],
    )

    patch_file(
        lib_ui / "buttons.cpp",
        [
            (
                "void SettingsButton::paintBg(Painter &p, const QRect &rect, bool over) const {\n"
                "\tp.fillRect(rect, over ? _st.textBgOver : _st.textBg);\n"
                "}\n",
                "void SettingsButton::paintBg(Painter &p, const QRect &rect, bool over) const {\n"
                "\tif (MaterialDesign()) {\n"
                "\t\tp.fillRect(rect, _st.textBg);\n"
                "\t\tif (over) {\n"
                "\t\t\tauto hq = PainterHighQualityEnabler(p);\n"
                "\t\t\tconst auto pill = QRectF(this->rect()).adjusted(8., 2., -8., -2.);\n"
                "\t\t\tconst auto radius = std::min(12., pill.height() / 2.);\n"
                "\t\t\tp.setPen(Qt::NoPen);\n"
                "\t\t\tp.setBrush(_st.textBgOver);\n"
                "\t\t\tp.drawRoundedRect(pill, radius, radius);\n"
                "\t\t}\n"
                "\t\treturn;\n"
                "\t}\n"
                "\tp.fillRect(rect, over ? _st.textBgOver : _st.textBg);\n"
                "}\n",
                "SettingsButton::paintBg(Painter &p, const QRect &rect, bool over) const {\n\tif (MaterialDesign())",
            ),
        ],
    )

    patch_file(
        lib_ui / "side_bar_button.cpp",
        [
            (
                '#include "ui/effects/ripple_animation.h"\n'
                '#include "ui/painter.h"\n',
                '#include "ui/effects/ripple_animation.h"\n'
                '#include "ui/widgets/checkbox.h"\n'
                '#include "ui/painter.h"\n',
                '#include "ui/widgets/checkbox.h"',
            ),
            (
                "\tconst auto &bg = _active ? _st.textBgActive : _st.textBg;\n"
                "\tp.fillRect(clip, bg);\n",
                "\tconst auto &bg = _active ? _st.textBgActive : _st.textBg;\n"
                "\tif (MaterialDesign() && width() > 24 && height() > 24) {\n"
                "\t\tp.fillRect(clip, _st.textBg);\n"
                "\t\tif (_active) {\n"
                "\t\t\tauto hq = PainterHighQualityEnabler(p);\n"
                "\t\t\tconst auto pillRect = QRectF(rect()).adjusted(6.0, 3.0, -6.0, -3.0);\n"
                "\t\t\tp.setPen(QPen(QColor(255, 255, 255, 22), 1.0));\n"
                "\t\t\tp.setBrush(_st.textBgActive);\n"
                "\t\t\tp.drawRoundedRect(pillRect, 14.0, 14.0);\n"
                "\t\t}\n"
                "\t} else {\n"
                "\t\tp.fillRect(clip, bg);\n"
                "\t}\n",
                "if (MaterialDesign() && width() > 24 && height() > 24)",
            ),
        ],
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
