import _extera


def set_style(plugin_id: str, target: str, **props) -> None:
    """Apply a UI style override for a named desktop widget target."""
    _extera.set_ui_override(str(plugin_id), str(target), props)


def clear_style(plugin_id: str, target: str = "") -> None:
    """Clear UI style overrides registered by a plugin."""
    _extera.clear_ui_override(str(plugin_id), str(target))
