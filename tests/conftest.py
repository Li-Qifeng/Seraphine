# Tests are self-contained and don't need QApplication
# (project dependencies have a runtime incompatibility in this env)
import logging
import sys
import types
from unittest.mock import MagicMock

# util.py imports Windows-only modules (winreg/win32api/win32gui); stub them
# so connector (and its util dependency) can be imported on non-Windows CI.
for _win_mod in ("winreg", "win32api", "win32gui", "win32con", "win32process"):
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

# PyQt5 stub (app.common.config imports PyQt5.QtCore directly)
if 'PyQt5' not in sys.modules:
    _pyqt5 = types.ModuleType('PyQt5')
    _pyqt5.QtCore = types.ModuleType('PyQt5.QtCore')
    _pyqt5.QtCore.QLocale = MagicMock()
    _pyqt5.QtCore.QSize = MagicMock()
    _pyqt5.QtCore.Qt = MagicMock()
    _pyqt5.QtCore.QObject = MagicMock()
    _pyqt5.QtCore.pyqtSignal = MagicMock()
    _pyqt5.QtCore.QRectF = MagicMock()
    _pyqt5.QtGui = types.ModuleType('PyQt5.QtGui')
    _pyqt5.QtGui.QPixmap = MagicMock()
    _pyqt5.QtGui.QPainter = MagicMock()
    _pyqt5.QtGui.QPainterPath = MagicMock()
    _pyqt5.QtGui.QColor = MagicMock()
    _pyqt5.QtGui.QFont = MagicMock()
    _pyqt5.QtGui.QPen = MagicMock()
    _pyqt5.QtWidgets = types.ModuleType('PyQt5.QtWidgets')
    _pyqt5.QtWidgets.QVBoxLayout = MagicMock()
    _pyqt5.QtWidgets.QHBoxLayout = MagicMock()
    _pyqt5.QtWidgets.QLabel = MagicMock()
    _pyqt5.QtWidgets.QFrame = MagicMock()
    _pyqt5.QtWidgets.QWidget = MagicMock()
    _pyqt5.QtWidgets.QSizePolicy = MagicMock()
    _pyqt5.QtWidgets.QSpacerItem = MagicMock()
    sys.modules['PyQt5'] = _pyqt5
    sys.modules['PyQt5.QtCore'] = _pyqt5.QtCore
    sys.modules['PyQt5.QtGui'] = _pyqt5.QtGui
    sys.modules['PyQt5.QtWidgets'] = _pyqt5.QtWidgets

# Pre-import app.common.config with stubs, then patch cfg.get() so that
# logger.py (imported by connector) doesn't crash on MagicMock return value.
import app.common.config as _cfg_mod  # noqa: E402
_cfg_mod.cfg.get = MagicMock(return_value=logging.INFO)
