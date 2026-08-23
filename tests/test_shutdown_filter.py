"""
ShutdownFilter 回归测试.

契约: WM_QUERYENDSESSION / WM_ENDSESSION 必须被吞掉并答复 TRUE(允许结束会话),
否则 Qt 会把它们翻译成顶层窗口 closeEvent -> 托盘模式 ignore -> 回 FALSE,
导致 Windows 弹出 "应用阻止关机".
"""
import ctypes
from unittest.mock import MagicMock

from app.common.shutdown_filter import ShutdownFilter, _PTR_SIZE


def _msg_ptr(msg_id):
    # MSG(x64): HWND hwnd(8 字节) + UINT message(4 字节), 只需前 12 字节
    buf = (ctypes.c_ubyte * (_PTR_SIZE + 4))()
    ctypes.c_uint.from_buffer(buf, _PTR_SIZE).value = msg_id
    return ctypes.c_void_p(ctypes.addressof(buf))


def _make_filter():
    app = MagicMock()
    return ShutdownFilter(app), app


class TestShutdownFilter:
    def test_queryendsession_swallowed_and_allows(self):
        f, app = _make_filter()
        consumed, result = f.nativeEventFilter(
            b"windows_generic_MSG", _msg_ptr(0x0011))
        assert (consumed, result) == (True, 1)
        app.quit.assert_called_once()

    def test_endsession_swallowed_and_allows(self):
        f, app = _make_filter()
        consumed, result = f.nativeEventFilter(
            b"windows_generic_MSG", _msg_ptr(0x0016))
        assert (consumed, result) == (True, 1)
        app.quit.assert_called_once()

    def test_normal_message_passthrough(self):
        f, app = _make_filter()
        consumed, result = f.nativeEventFilter(
            b"windows_generic_MSG", _msg_ptr(0x0200))  # WM_MOUSEMOVE
        assert (consumed, result) == (False, 0)
        app.quit.assert_not_called()

    def test_other_event_type_passthrough(self):
        f, app = _make_filter()
        assert f.nativeEventFilter(b"other_event", None) == (False, 0)
        app.quit.assert_not_called()
