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


_user32 = ctypes.windll.user32
_user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
_user32.RegisterHotKey.restype = wintypes.BOOL
_user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.UnregisterHotKey.restype = wintypes.BOOL


class _NativeHotkeyFilter(QAbstractNativeEventFilter):
    """纯 C++ 接口封装（不继承 QObject），规避 PyQt SIP 多重继承虚表分发丢失问题。"""

    def __init__(self, manager):
        super().__init__()
        self._manager = manager

    def nativeEventFilter(self, eventType, message):
        type_bytes = bytes(eventType) if isinstance(eventType, (bytes, bytearray)) else str(eventType).encode("latin1", "ignore")
        if b"windows_generic_MSG" in type_bytes or b"windows_dispatcher_MSG" in type_bytes:
            try:
                msg = _MSG.from_address(int(message))
                if msg.message == WM_HOTKEY:
                    logger.info(f"native WM_HOTKEY message intercepted: wParam={msg.wParam}, hwnd={msg.hwnd}", TAG)
                    self._manager._on_wm_hotkey(msg.wParam)
                    return True, 0
            except Exception as e:
                logger.warning(f"nativeEventFilter parse error: {e}", TAG)
        return False, 0


def _win32_register(hotkey_id: int, mod: int, vk: int, hwnd=None) -> bool:
    h = wintypes.HWND(hwnd) if hwnd else None
    return bool(_user32.RegisterHotKey(h, hotkey_id, mod, vk))


def _win32_unregister(hotkey_id: int, hwnd=None) -> bool:
    h = wintypes.HWND(hwnd) if hwnd else None
    return bool(_user32.UnregisterHotKey(h, hotkey_id))


class HotkeyManager(QObject):
    """登记簿：{hotkey_id: hotkey_str} + {hotkey_id: group_id}。

    收到 WM_HOTKEY 时发 Qt 信号 triggered(group_id)，由 ChatService 消费。
    """

    triggered = pyqtSignal(str)

    def __init__(self, parent=None, register_fn=None, unregister_fn=None, hwnd=None):
        if parent is None:
            super().__init__()  # CI 桩环境下 object.__init__ 不接受 None
        else:
            super().__init__(parent)
        self._hwnd = hwnd
        self._register = register_fn or _win32_register
        self._unregister = unregister_fn or _win32_unregister
        self._ids = {}        # hotkey_str -> hotkey_id
        self._groups = {}     # hotkey_id -> group_id
        self._failed_hotkeys = {}  # hotkey_str -> err_tip
        self._next_id = 1
        self._filter = _NativeHotkeyFilter(self)

    @property
    def event_filter(self) -> QAbstractNativeEventFilter:
        """供 app.installNativeEventFilter() 安装使用。"""
        return self._filter

    def set_hwnd(self, hwnd: int):
        """绑定主窗口 HWND（若为 None 则默认使用线程级消息队列）。"""
        self._hwnd = hwnd

    # ---- 登记簿（纯逻辑，可单测）----

    def register_bindings(self, bindings: dict) -> bool:
        """bindings: {hotkey_str: group_id}。先全部注销再按新清单注册。"""
        self.unregister_all()
        self._failed_hotkeys.clear()
        for hotkey, group_id in bindings.items():
            try:
                # 兜底校验：保存时硬拦截是主闸，注册时再过一遍高危区表
                validate_hotkey(hotkey)
                mod, vk = hotkey_to_vk(hotkey)
            except HotkeyError as e:
                logger.warning(f"skip invalid hotkey {hotkey!r}: {e}", TAG)
                self._failed_hotkeys[hotkey] = str(e)
                continue
            hotkey_id = self._next_id
            self._next_id += 1

            # 兼容 3 参数（单测桩）与 4 参数（带 hwnd）签名
            try:
                ok = self._register(hotkey_id, mod | MOD_NOREPEAT, vk, hwnd=self._hwnd)
            except TypeError:
                ok = self._register(hotkey_id, mod | MOD_NOREPEAT, vk)

            if not ok:
                err = ctypes.windll.kernel32.GetLastError()
                err_tip = "快捷键已被其他程序或旧进程占用" if err == 1409 else f"WinError {err}"
                logger.warning(f"RegisterHotKey failed for {hotkey!r} ({err_tip}) (hwnd={self._hwnd})", TAG)
                self._failed_hotkeys[hotkey] = err_tip
                continue
            self._ids[hotkey] = hotkey_id
            self._groups[hotkey_id] = group_id
        logger.info(f"hotkeys registered: {sorted(self._ids.keys())} (hwnd={self._hwnd})", TAG)
        return bool(self._ids)

    def unregister_all(self):
        for hotkey_id in list(self._groups.keys()):
            try:
                try:
                    self._unregister(hotkey_id, hwnd=self._hwnd)
                except TypeError:
                    self._unregister(hotkey_id)
            except Exception as e:
                logger.debug(f"UnregisterHotKey({hotkey_id}): {e}", TAG)
        self._ids.clear()
        self._groups.clear()

    def registered_hotkeys(self) -> list:
        return sorted(self._ids.keys())

    def failed_hotkeys(self) -> dict:
        return dict(self._failed_hotkeys)

    def _on_wm_hotkey(self, hotkey_id: int):
        group_id = self._groups.get(hotkey_id)
        if group_id:
            logger.info(f"WM_HOTKEY triggered: id={hotkey_id} -> group={group_id}", TAG)
            self.triggered.emit(group_id)
            return True, 0
        logger.debug(f"WM_HOTKEY unmapped: id={hotkey_id}", TAG)
        return False, 0

    # ---- 兼容单测直接调用 ----

    def nativeEventFilter(self, eventType, message):
        return self._filter.nativeEventFilter(eventType, message)

