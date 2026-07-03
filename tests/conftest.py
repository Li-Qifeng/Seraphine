# Tests are self-contained and don't need QApplication
# (project dependencies have a runtime incompatibility in this env)
import logging
import sys
import types
from unittest.mock import MagicMock

# util.py imports Windows-only modules (winreg/win32api/win32gui); stub them
# so connector (and its util dependency) can be imported on non-Windows CI.
for _win_mod in ("winreg", "win32api", "win32gui"):
    if _win_mod not in sys.modules:
        sys.modules[_win_mod] = MagicMock()

# qfluentwidgets C extension (PyQt5) crashes without QApplication.
# Stub the package + all submodules + the directly imported names.

def _make_stub(top_name, sub_modules, names_by_module, top_names):
    for mod_name in [top_name] + sub_modules:
        if mod_name not in sys.modules:
            sys.modules[mod_name] = types.ModuleType(mod_name)

    for mod_name, names in names_by_module.items():
        m = sys.modules.get(mod_name) or types.ModuleType(mod_name)
        for n in names:
            setattr(m, n, MagicMock())
        sys.modules[mod_name] = m

    top = sys.modules[top_name]
    top.__all__ = list(top_names)
    for n in top_names:
        if not hasattr(top, n):
            setattr(top, n, MagicMock())

_qfw_sub = [
    'qfluentwidgets.components',
    'qfluentwidgets.components.widgets',
    'qfluentwidgets.components.widgets.line_edit',
    'qfluentwidgets.components.widgets.frameless_window',
    'qfluentwidgets.common',
    'qfluentwidgets.common.animation',
    'qfluentwidgets.window',
    'qfluentwidgets.window.fluent_window',
    'qfluentwidgets.window.stacked_widget',
]
_qfw_sub_attrs = {
    'qfluentwidgets.components.widgets.line_edit':
        ['CompleterMenu', 'LineEditButton'],
    'qfluentwidgets.common.animation':
        ['BackgroundAnimationWidget', 'BackgroundColorObject'],
    'qfluentwidgets.window.fluent_window':
        ['FluentWindowBase'],
    'qfluentwidgets.window.stacked_widget':
        ['StackedWidget'],
    'qfluentwidgets.components.widgets.frameless_window':
        ['FramelessWindow'],
}
_qfw_top_names = [
    'qconfig', 'QConfig', 'ConfigItem', 'BoolValidator',
    'OptionsConfigItem', 'OptionsValidator', 'ConfigSerializer',
    'RangeConfigItem', 'RangeValidator', 'ColorConfigItem',
    'Theme', 'EnumSerializer',
]
_make_stub('qfluentwidgets', _qfw_sub, _qfw_sub_attrs, _qfw_top_names)

if 'qframelesswindow' not in sys.modules:
    _qfw2 = types.ModuleType('qframelesswindow')
    _qfw2.SvgTitleBarButton = MagicMock()
    sys.modules['qframelesswindow'] = _qfw2

# Pre-import app.common.config with stubs, then patch cfg.get() so that
# logger.py (imported by connector) doesn't crash on MagicMock return value.
import app.common.config as _cfg_mod  # noqa: E402
_cfg_mod.cfg.get = MagicMock(return_value=logging.INFO)
