"""app/chat/domain 层契约测试：rhythm 限流 / keys 冲突拦截 / orchestrator 唯一出口。

domain 层无 Qt/Win32 依赖，全部依赖注入。
"""
import asyncio

import pytest

from app.chat.domain.keys import (
    HotkeyError, parse_hotkey, validate_hotkey, hotkey_to_vk,
)
from app.chat.domain.rhythm import Rhythm
from app.chat.domain.orchestrator import SendOrchestrator


# ---------- keys ----------

class TestParse:
    def test_parse_basic(self):
        mods, key = parse_hotkey("Alt+1")
        assert mods == frozenset({"alt"}) and key == "1"

    def test_parse_case_and_space(self):
        mods, key = parse_hotkey(" alt + F13 ")
        assert mods == frozenset({"alt"}) and key == "f13"

    def test_parse_multi_mod(self):
        mods, key = parse_hotkey("Ctrl+Shift+A")
        assert mods == frozenset({"ctrl", "shift"}) and key == "a"

    def test_parse_invalid(self):
        for bad in ("", "Alt+", "+1", "Alt++1", "NotAKey", "Alt+NotAKey"):
            with pytest.raises(HotkeyError):
                parse_hotkey(bad)


class TestValidate:
    def test_default_bindings_ok(self):
        for i in range(1, 10):
            validate_hotkey(f"Alt+{i}")
        validate_hotkey("Alt+0")

    def test_lol_reserved_combos_blocked(self):
        for hk in ("Alt+Q", "Alt+W", "Alt+E", "Alt+R", "Alt+D", "Alt+F",
                   "Ctrl+Q", "Ctrl+W", "Ctrl+E", "Ctrl+R",
                   "Ctrl+1", "Ctrl+2", "Ctrl+3", "Ctrl+4", "Ctrl+6",
                   "Shift+Q", "Shift+W", "Shift+E", "Shift+R", "Shift+D", "Shift+F"):
            with pytest.raises(HotkeyError):
                validate_hotkey(hk)

    def test_system_combos_blocked(self):
        for hk in ("Alt+Tab", "Alt+F4", "Alt+Space", "Alt+Esc", "Ctrl+Esc"):
            with pytest.raises(HotkeyError):
                validate_hotkey(hk)

    def test_forbidden_single_keys(self):
        for k in ("Q", "W", "E", "R", "D", "F", "1", "7", "B", "A", "X", "S",
                  "H", "P", "C", "G", "V", "T", "Y", "O", "M", "L", "J", "Z",
                  "Enter", "Esc", "Tab", "Space", "`",
                  "Up", "Down", "Left", "Right",
                  "F2", "F3", "F4", "F5", "F12"):
            with pytest.raises(HotkeyError):
                validate_hotkey(k)

    def test_allowed_keys(self):
        for hk in ("F13", "F24", "Insert", "Home", "End", "PageUp", "PageDown",
                   "ScrollLock", "Pause", "Num0", "Num9", "NumDot",
                   "Ctrl+Alt+1", "Alt+`"):
            validate_hotkey(hk)  # 不抛异常即通过

    def test_conflict_with_existing_binding(self):
        with pytest.raises(HotkeyError):
            validate_hotkey("Alt+1", existing={"Alt+1": "g1"})
        # 同一分组改绑自己不算冲突
        validate_hotkey("Alt+1", existing={"Alt+1": "g1"}, self_id="g1")


class TestVk:
    def test_hotkey_to_vk(self):
        mod, vk = hotkey_to_vk("Alt+1")
        assert mod & 0x0001  # MOD_ALT
        assert vk == 0x31    # '1'

    def test_f13_vk(self):
        _, vk = hotkey_to_vk("F13")
        assert vk == 0x7C

    def test_numpad_vk(self):
        _, vk = hotkey_to_vk("Num5")
        assert vk == 0x65


# ---------- rhythm ----------

class TestRhythm:
    def test_first_send_no_wait(self):
        r = Rhythm(min_interval_ms=800, jitter_ratio=0.0, burst_limit=3, burst_cooldown_ms=3000)
        assert r.next_delay(now=1000.0) == 0.0

    def test_min_interval(self):
        r = Rhythm(min_interval_ms=800, jitter_ratio=0.0, burst_limit=3, burst_cooldown_ms=3000)
        r.record(now=1000.0)
        d = r.next_delay(now=1000.5)
        assert abs(d - 0.3) < 1e-6

    def test_burst_cooldown(self):
        r = Rhythm(min_interval_ms=800, jitter_ratio=0.0, burst_limit=3, burst_cooldown_ms=3000)
        r.record(now=1000.0)
        r.record(now=1001.0)
        r.record(now=1002.0)
        # 第 4 条距第 1 条 < 3s → 等到 cooldown 结束
        d = r.next_delay(now=1002.9)
        assert d >= 0.1 - 1e-6

    def test_jitter_within_ratio(self):
        r = Rhythm(min_interval_ms=800, jitter_ratio=0.3, burst_limit=99, burst_cooldown_ms=60000)
        r.record(now=1000.0)
        base = 0.6  # 800ms - 已过的 200ms
        for i in range(50):
            d = r.next_delay(now=1000.2)
            assert base * (1 - 0.3) - 1e-9 <= d <= base * (1 + 0.3) + 1e-9

    def test_min_interval_floor(self):
        with pytest.raises(ValueError):
            Rhythm(min_interval_ms=599)  # 硬下限 600ms


# ---------- orchestrator ----------

def _make_orch(phase="InProgress", foreground=True, phrases=("第一条", "第二条", "第三条")):
    """构造全注入的 orchestrator，返回 (orch, sent)。"""
    sent = []

    class FakeRepo:
        def __init__(self):
            self._items = list(phrases)
            self._idx = 0
            self.logs = []

        def next_phrase_in_group(self, group_id):
            if not self._items:
                return None
            text = self._items[self._idx % len(self._items)]
            self._idx += 1
            return {"id": f"p{self._idx}", "content": text}

        def add_send_log(self, text, channel, ok, detail="", ts=None):
            self.logs.append((text, channel, ok, detail))

    async def lcu_sender(text):
        sent.append(("lcu", text))
        return True

    def ingame_sender(text):
        sent.append(("ingame", text))
        return True

    repo = FakeRepo()
    orch = SendOrchestrator(
        repo=repo,
        rhythm=Rhythm(min_interval_ms=600, jitter_ratio=0.0,
                      burst_limit=99, burst_cooldown_ms=60000),
        phase_provider=lambda: phase,
        foreground_checker=lambda: foreground,
        lcu_sender=lcu_sender,
        ingame_sender=ingame_sender,
    )
    return orch, sent, repo


class TestOrchestrator:
    def test_ingame_channel(self):
        orch, sent, repo = _make_orch(phase="InProgress", foreground=True)
        res = asyncio.run(orch.send_group("g1"))
        assert res["ok"] and res["channel"] == "ingame" and res["text"] == "第一条"
        assert sent == [("ingame", "第一条")]
        assert repo.logs[0][1] == "ingame" and repo.logs[0][2] is True

    def test_champselect_uses_lcu(self):
        orch, sent, repo = _make_orch(phase="ChampSelect")
        res = asyncio.run(orch.send_group("g1"))
        assert res["ok"] and res["channel"] == "lcu"
        assert sent == [("lcu", "第一条")]

    def test_lobby_uses_lcu(self):
        orch, sent, _ = _make_orch(phase="Lobby")
        res = asyncio.run(orch.send_group("g1"))
        assert res["ok"] and res["channel"] == "lcu"

    def test_gate_blocks_other_phases(self):
        for phase in ("Matchmaking", "ReadyCheck", "EndOfGame", "None", None, "Reconnect"):
            orch, sent, repo = _make_orch(phase=phase)
            res = asyncio.run(orch.send_group("g1"))
            assert not res["ok"] and res["stage"] == "gate", phase
        assert repo.logs == []  # 闸拦截不记日志

    def test_ingame_requires_foreground(self):
        orch, sent, repo = _make_orch(phase="InProgress", foreground=False)
        res = asyncio.run(orch.send_group("g1"))
        assert not res["ok"] and res["stage"] == "gate"
        assert sent == []

    def test_cycle_order_across_calls(self):
        orch, sent, _ = _make_orch()
        for _ in range(4):
            asyncio.run(orch.send_group("g1"))
        texts = [t for _, t in sent]
        assert texts == ["第一条", "第二条", "第三条", "第一条"]

    def test_empty_group(self):
        orch, sent, _ = _make_orch(phrases=())
        res = asyncio.run(orch.send_group("g1"))
        assert not res["ok"] and res["stage"] == "empty"

    def test_busy_drop(self):
        """上一次发送进行中时新触发直接丢弃（stage=busy），不排队。"""
        gate = asyncio.Event()
        sent = []

        class R:
            def next_phrase_in_group(self, gid):
                return {"id": "p1", "content": "x"}

            def add_send_log(self, *a, **k):
                pass

        async def slow_lcu(text):
            await gate.wait()
            sent.append(text)
            return True

        orch = SendOrchestrator(
            repo=R(),
            rhythm=Rhythm(min_interval_ms=600, jitter_ratio=0.0,
                          burst_limit=99, burst_cooldown_ms=60000),
            phase_provider=lambda: "ChampSelect",
            foreground_checker=lambda: True,
            lcu_sender=slow_lcu,
            ingame_sender=lambda t: True,
        )

        async def main():
            t1 = asyncio.ensure_future(orch.send_group("g1"))
            await asyncio.sleep(0.05)  # 让 t1 进入发送中
            r2 = await orch.send_group("g1")  # 应被判 busy
            gate.set()
            r1 = await t1
            return r1, r2

        r1, r2 = asyncio.run(main())
        assert r1["ok"] and not r2["ok"] and r2["stage"] == "busy"

    def test_sender_failure_logged(self):
        async def fail_lcu(text):
            return False

        orch, sent, repo = _make_orch(phase="ChampSelect")
        orch._lcu_sender = fail_lcu
        res = asyncio.run(orch.send_group("g1"))
        assert not res["ok"] and res["stage"] == "send"
        assert repo.logs[0][2] is False
