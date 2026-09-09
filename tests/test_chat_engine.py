"""app/chat/engine 层测试：INPUT 构建纯逻辑 + HotkeyManager 登记簿（注入桩）。

真实 SendInput / RegisterHotKey 效果以真机验收为准，此处只验可离线断言的部分。
"""
import ctypes

from app.chat.engine import input_sim
from app.chat.engine.hotkey import _MSG, WM_HOTKEY, HotkeyManager


class TestBuildUnicodeInputs:
    def test_ascii_char_down_up_pair(self):
        events = input_sim.build_unicode_inputs("a")
        assert len(events) == 2
        down, up = events
        assert down.u.ki.wVk == 0 and down.u.ki.wScan == ord("a")
        assert down.u.ki.dwFlags == input_sim.KEYEVENTF_UNICODE
        assert up.u.ki.dwFlags == (
            input_sim.KEYEVENTF_UNICODE | input_sim.KEYEVENTF_KEYUP)

    def test_cjk_char(self):
        events = input_sim.build_unicode_inputs("龙")
        assert len(events) == 2
        assert events[0].u.ki.wScan == ord("龙")

    def test_emoji_surrogate_pair(self):
        events = input_sim.build_unicode_inputs("😀")  # U+1F600 > 0xFFFF
        assert len(events) == 4  # 代理对 2 码元 × down/up
        hi, lo = events[0].u.ki.wScan, events[2].u.ki.wScan
        assert 0xD800 <= hi <= 0xDBFF
        assert 0xDC00 <= lo <= 0xDFFF
        # 还原验证
        assert (hi - 0xD800) * 0x400 + (lo - 0xDC00) + 0x10000 == 0x1F600

    def test_mixed_text_length(self):
        events = input_sim.build_unicode_inputs("集合打龙")  # 4 字
        assert len(events) == 8

    def test_empty(self):
        assert input_sim.build_unicode_inputs("") == []


def _make_manager(register_ok=True):
    calls = {"reg": [], "unreg": []}

    def reg(hotkey_id, mod, vk):
        calls["reg"].append((hotkey_id, mod, vk))
        return register_ok

    def unreg(hotkey_id):
        calls["unreg"].append(hotkey_id)
        return True

    return HotkeyManager(register_fn=reg, unregister_fn=unreg), calls


class TestHotkeyManager:
    def test_register_and_unregister(self):
        mgr, calls = _make_manager()
        assert mgr.registered_hotkeys() == []
        ok = mgr.register_bindings({"Alt+1": "g1", "Alt+2": "g2"})
        assert ok
        assert mgr.registered_hotkeys() == ["Alt+1", "Alt+2"]
        assert len(calls["reg"]) == 2
        # MOD_ALT | MOD_NOREPEAT
        assert calls["reg"][0][1] & 0x0001 and calls["reg"][0][1] & 0x4000
        mgr.unregister_all()
        assert mgr.registered_hotkeys() == []
        assert len(calls["unreg"]) == 2

    def test_reregister_clears_old(self):
        mgr, calls = _make_manager()
        mgr.register_bindings({"Alt+1": "g1"})
        mgr.register_bindings({"Alt+3": "g3"})
        assert mgr.registered_hotkeys() == ["Alt+3"]
        assert len(calls["unreg"]) == 1  # 旧的 Alt+1 被注销

    def test_reserved_combo_rejected(self):
        mgr, calls = _make_manager()
        ok = mgr.register_bindings({"Alt+Q": "g1", "Alt+1": "g2"})
        assert ok  # Alt+1 成功
        assert mgr.registered_hotkeys() == ["Alt+1"]  # Alt+Q 被兜底校验拦截
        assert len(calls["reg"]) == 1

    def test_register_failure_skipped(self):
        mgr, calls = _make_manager(register_ok=False)
        ok = mgr.register_bindings({"Alt+1": "g1"})
        assert not ok
        assert mgr.registered_hotkeys() == []

    def test_native_event_dispatch(self):
        mgr, _ = _make_manager()
        mgr.register_bindings({"Alt+1": "g1"})
        hotkey_id = mgr._ids["Alt+1"]
        msg = _MSG()
        msg.message = WM_HOTKEY
        msg.wParam = hotkey_id
        handled, ret = mgr.nativeEventFilter(
            "windows_generic_MSG", ctypes.addressof(msg))
        assert handled and ret == 0
        # conftest 桩环境下 triggered 是 MagicMock；真实环境为 pyqtSignal 正常 emit
        mgr.triggered.emit.assert_called_once_with("g1")

    def test_native_event_dispatch_bytes_and_dispatcher_msg(self):
        mgr, _ = _make_manager()
        mgr.register_bindings({"Alt+1": "g1"})
        hotkey_id = mgr._ids["Alt+1"]
        msg = _MSG()
        msg.message = WM_HOTKEY
        msg.wParam = hotkey_id

        # 测试 bytes 类型的 windows_dispatcher_MSG
        handled, ret = mgr.nativeEventFilter(
            b"windows_dispatcher_MSG", ctypes.addressof(msg))
        assert handled and ret == 0

    def test_native_event_ignores_other_messages(self):
        mgr, _ = _make_manager()
        msg = _MSG()
        msg.message = 0x9999
        handled, _ = mgr.nativeEventFilter(
            "windows_generic_MSG", ctypes.addressof(msg))
        assert not handled
