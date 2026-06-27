# Tests are self-contained and don't need QApplication
# (project dependencies have a runtime incompatibility in this env)
import sys
from unittest.mock import MagicMock

# util.py imports Windows-only modules (winreg/win32api/win32gui); stub them
# so connector (and its util dependency) can be imported on non-Windows CI.
for _win_mod in ("winreg", "win32api", "win32gui"):
    if _win_mod not in sys.modules:
        sys.modules[_win_mod] = MagicMock()
