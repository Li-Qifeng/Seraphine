"""常驻侧边栏纯逻辑 + 注册表契约测试 (不导入 Qt)."""
import ast
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.common.side_dock import (  # noqa: E402
    DOCK_WIDTH_COLLAPSED, DOCK_WIDTH_EXPANDED, QUICK_TOGGLES, QuickToggle,
    computeDockGeometry, dockWidth, orderToggles, shouldShowDock)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAMEFLOW_PHASES = {
    'None', 'Lobby', 'Matchmaking', 'CheckedIntoTournament', 'ReadyCheck',
    'ChampSelect', 'GameStart', 'FailedToLaunch', 'InProgress', 'Reconnect',
    'WaitingForStats', 'PreEndOfGame', 'EndOfGame', 'TerminatedInError',
}


def _configBoolItems():
    tree = ast.parse(open(os.path.join(ROOT, "app", "common", "config.py"),
                          encoding="utf-8").read())
    cfgClass = next(n for n in tree.body
                    if isinstance(n, ast.ClassDef) and n.name == "Config")
    result = {}
    for node in cfgClass.body:
        if (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)
                and isinstance(node.targets[0], ast.Name)):
            usesBool = any(
                isinstance(a, ast.Call) and getattr(a.func, 'id', '') == 'BoolValidator'
                for a in node.value.args)
            result[node.targets[0].id] = usesBool
    return result


def _iconMembers():
    text = open(os.path.join(ROOT, "app", "common", "icons.py"),
                encoding="utf-8").read()
    return set(re.findall(r'^\s+([A-Z][A-Z0-9_]*)\s*=', text, re.M))


class TestRegistryContract:
    def test_keys_are_unique(self):
        keys = [t.key for t in QUICK_TOGGLES]
        assert len(keys) == len(set(keys))

    def test_every_key_is_a_bool_config_item(self):
        items = _configBoolItems()
        for t in QUICK_TOGGLES:
            assert t.key in items, f"cfg 中没有 {t.key}"
            assert items[t.key], f"{t.key} 不是 BoolValidator 配置项"

    def test_every_icon_exists(self):
        members = _iconMembers()
        for t in QUICK_TOGGLES:
            assert t.icon in members, f"Icon 枚举中没有 {t.icon}"

    def test_phases_are_valid_gameflow_phases(self):
        for t in QUICK_TOGGLES:
            assert t.phases and set(t.phases) <= GAMEFLOW_PHASES, t.key

    def test_dock_config_items_exist(self):
        items = _configBoolItems()
        assert items.get("enableSideDock") is True
        assert items.get("sideDockCollapsed") is True


class TestOrderToggles:
    A = QuickToggle("a", "A", "CHECK", ("Lobby",))
    B = QuickToggle("b", "B", "CHECK", ("ChampSelect",))
    C = QuickToggle("c", "C", "CHECK", ("ChampSelect", "Reconnect"))
    ALL = (A, B, C)

    def test_related_first_and_active(self):
        res = orderToggles(self.ALL, "ChampSelect")
        assert [(t.key, a) for t, a in res] == [
            ("b", True), ("c", True), ("a", False)]

    def test_keeps_original_order_inside_groups(self):
        res = orderToggles(self.ALL, "Lobby")
        assert [t.key for t, _ in res] == ["a", "b", "c"]
        assert [a for _, a in res] == [True, False, False]

    def test_unrelated_phase_means_no_dimming(self):
        res = orderToggles(self.ALL, "InProgress")
        assert [(t.key, a) for t, a in res] == [
            ("a", True), ("b", True), ("c", True)]

    def test_none_phase(self):
        res = orderToggles(self.ALL, None)
        assert all(a for _, a in res)

    def test_real_registry_lobby_puts_auto_start_first(self):
        res = orderToggles(QUICK_TOGGLES, "Lobby")
        assert res[0][0].key == "enableAutoStartMatchmaking"
        assert res[0][1] is True


class TestDockGeometry:
    def test_left_of_client(self):
        # 客户端 (1000, 100) 1280x720, dpr=1
        x, y, w, h = computeDockGeometry((1000, 100, 1280, 720), 1.0, 168, 400, 1200)
        assert (x, y, w, h) == (1000 - 168, 100, 168, 720)

    def test_falls_back_to_right_when_no_room(self):
        x, y, w, h = computeDockGeometry((100, 50, 1280, 720), 1.0, 168, 400, 1200)
        assert x == 100 + 1280

    def test_exact_fit_stays_left(self):
        x, *_ = computeDockGeometry((168, 0, 1280, 720), 1.0, 168, 400, 1200)
        assert x == 0

    def test_dpi_scaling(self):
        # 物理像素 2000x1125 @ 1.25 -> 逻辑 1600x900
        x, y, w, h = computeDockGeometry((1250, 250, 2000, 1125), 1.25, 168, 400, 1200)
        assert (x, y, h) == (1000 - 168, 200, 900)

    def test_height_clamped(self):
        assert computeDockGeometry((500, 0, 640, 360), 1.0, 168, 400, 1200)[3] == 400
        assert computeDockGeometry((500, 0, 3840, 2160), 1.0, 168, 400, 1200)[3] == 1200

    def test_zero_dpr_is_safe(self):
        assert computeDockGeometry((500, 0, 1280, 720), 0, 168, 400, 1200)[3] == 720

    def test_collapsed_width(self):
        assert dockWidth(True) == DOCK_WIDTH_COLLAPSED
        assert dockWidth(False) == DOCK_WIDTH_EXPANDED
        assert DOCK_WIDTH_COLLAPSED < DOCK_WIDTH_EXPANDED


class TestShouldShowDock:
    def _call(self, **kw):
        base = dict(enabled=True, clientPresent=True, clientRectValid=True,
                    onTop=False, clientForeground=False, ownActive=False)
        base.update(kw)
        return shouldShowDock(**base)

    def test_not_on_top_shows_whenever_client_visible(self):
        assert self._call()

    def test_disabled_hides(self):
        assert not self._call(enabled=False)

    def test_no_client_hides(self):
        assert not self._call(clientPresent=False)

    def test_minimized_client_hides(self):
        assert not self._call(clientRectValid=False)

    def test_on_top_requires_foreground(self):
        assert not self._call(onTop=True)
        assert self._call(onTop=True, clientForeground=True)
        assert self._call(onTop=True, ownActive=True)
