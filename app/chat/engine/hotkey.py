"""全局热键管理：RegisterHotKey(hwnd=NULL) + QAbstractNativeEventFilter 收 WM_HOTKEY。

设计要点：
- hwnd=NULL 注册 → WM_HOTKEY 进线程消息队列 → qApp 原生事件过滤器收到，
  对 MainWindow 零侵入（不改其接线表）。
- RegisterHotKey 成功后会**吞掉**该组合键（游戏收不到），所以 keys.py
  的冲突硬拦截必须先于注册发生。
- MOD_NOREPEAT：按住不重复触发。
- register_fn / unregister_fn 可注入（测试时用桩替代真实 Win32 调用）。
"""
import ctypes
from ctypes import wintypes

from PyQt5.QtCore import QAbstractNativeEventFilter, QObject, pyqtSignal

from app.common.logger import logger
from app.chat.domain.keys import HotkeyError, hotkey_to_vk, validate_hotkey

TAG = "ChatHotkey"
WM_HOTKEY = 0x0312
MOD_NOREPEAT = 0x4000


class _MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
    ]


def _win32_register(hotkey_id: int, mod: int, vk: int) -> bool:
    return bool(ctypes.windll.user32.RegisterHotKey(None, hotkey_id, mod, vk))


def _win32_unregister(hotkey_id: int) -> bool:
    return bool(ctypes.windll.user32.UnregisterHotKey(None, hotkey_id))


class HotkeyManager(QObject, QAbstractNativeEventFilter):
    """登记簿：{hotkey_id: hotkey_str} + {hotkey_id: group_id}。

    收到 WM_HOTKEY 时发 Qt 信号 triggered(group_id)，由 ChatService 消费。
    """

    triggered = pyqtSignal(str)

    def __init__(self, parent=None, register_fn=None, unregister_fn=None):
        if parent is None:
            super().__init__()  # CI 桩环境下 object.__init__ 不接受 None
        else:
            super().__init__(parent)
        self._register = register_fn or _win32_register
        self._unregister = unregister_fn or _win32_unregister
        self._ids = {}        # hotkey_str -> hotkey_id
        self._groups = {}     # hotkey_id -> group_id
        self._next_id = 1

    # ---- 登记簿（纯逻辑，可单测）----

    def register_bindings(self, bindings: dict) -> bool:
        """bindings: {hotkey_str: group_id}。先全部注销再按新清单注册。"""
        self.unregister_all()
        for hotkey, group_id in bindings.items():
            try:
                # 兜底校验：保存时硬拦截是主闸，注册时再过一遍高危区表
                validate_hotkey(hotkey)
                mod, vk = hotkey_to_vk(hotkey)
            except HotkeyError as e:
                logger.warning(f"skip invalid hotkey {hotkey!r}: {e}", TAG)
                continue
            hotkey_id = self._next_id
            self._next_id += 1
            if not self._register(hotkey_id, mod | MOD_NOREPEAT, vk):
                logger.warning(f"RegisterHotKey failed for {hotkey!r}", TAG)
                continue
            self._ids[hotkey] = hotkey_id
            self._groups[hotkey_id] = group_id
        logger.info(f"hotkeys registered: {sorted(self._ids.keys())}", TAG)
        return bool(self._ids)

    def unregister_all(self):
        for hotkey_id in list(self._groups.keys()):
            try:
                self._unregister(hotkey_id)
            except Exception as e:
                logger.debug(f"UnregisterHotKey({hotkey_id}): {e}", TAG)
        self._ids.clear()
        self._groups.clear()

    def registered_hotkeys(self) -> list:
        return sorted(self._ids.keys())

    # ---- Qt 原生事件过滤 ----

    def nativeEventFilter(self, eventType, message):
        if eventType == "windows_generic_MSG":
            msg = _MSG.from_address(int(message))
            if msg.message == WM_HOTKEY:
                group_id = self._groups.get(msg.wParam)
                if group_id:
                    self.triggered.emit(group_id)
                return True, 0
        return False, 0
