"""常驻侧边栏 (SideDock) 的纯逻辑: 开关注册表 / 阶段排序 / 几何 / 显隐判定.

不导入任何 Qt 模块, 便于在无 QApplication 的环境下单测.
"""
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

DOCK_WIDTH_EXPANDED = 168
DOCK_WIDTH_COLLAPSED = 48

# 对局进行中的阶段: 侧边栏只在客户端位于前台时显示, 不能浮在游戏上
IN_GAME_PHASES = ('GameStart', 'InProgress', 'Reconnect')


@dataclass(frozen=True)
class QuickToggle:
    key: str                    # app.common.config.Config 上的 ConfigItem 属性名
    title: str
    icon: str                   # app.common.icons.Icon 的成员名
    phases: Tuple[str, ...]     # 相关的 gameflow 阶段, 用于高亮/置顶
    tip: str = ""


# 注册表: 新增快捷开关只需在这里加一行 (ConfigItem 必须是布尔项)
QUICK_TOGGLES: Tuple[QuickToggle, ...] = (
    QuickToggle("enableAutoStartMatchmaking", "自动开始匹配", "SEARCH",
                ("Lobby",), "进入大厅后自动开始匹配"),
    QuickToggle("enableAutoAcceptMatching", "自动接受对局", "CHECK",
                ("Matchmaking", "ReadyCheck"), "匹配成功后自动接受"),
    QuickToggle("enableAutoAramBench", "自动抢英雄", "ARROWCIRCLE",
                ("ChampSelect",), "大乱斗备选席命中愿望单时自动换英雄"),
    QuickToggle("enableAutoSelectChampion", "自动选英雄", "PERSONAVAILABLE",
                ("ChampSelect",), "轮到自己时自动选择英雄"),
    QuickToggle("enableAutoBanChampion", "自动禁用英雄", "SQUARECROSS",
                ("ChampSelect",), "轮到自己时自动禁用英雄"),
    QuickToggle("enableAutoHonor", "自动点赞", "TROPHY",
                ("PreEndOfGame", "WaitingForStats"), "对局结束后自动给队友点赞"),
    QuickToggle("enableAutoPlayAgain", "自动再来一局", "ARROWREPEAT",
                ("PreEndOfGame", "EndOfGame"), "结算后自动回到房间, 队友未就绪时会持续重试"),
    QuickToggle("enableAutoReconnect", "自动重连", "CONNECTION",
                ("InProgress", "Reconnect"), "掉线后自动重新连接对局"),
)


def dockWidth(collapsed: bool) -> int:
    return DOCK_WIDTH_COLLAPSED if collapsed else DOCK_WIDTH_EXPANDED


def orderToggles(toggles: Sequence[QuickToggle],
                 phase: Optional[str]) -> list:
    """按当前阶段排序, 返回 [(toggle, active)].

    与阶段相关的开关置顶并标记 active; 其余保持原顺序且 active=False.
    当前阶段没有任何相关开关时 (如游戏中), 不做区分: 全部 active, 原顺序.
    """
    related = [t for t in toggles if phase in t.phases]
    if not related:
        return [(t, True) for t in toggles]
    rest = [t for t in toggles if phase not in t.phases]
    return [(t, True) for t in related] + [(t, False) for t in rest]


def computeDockGeometry(client: Tuple[float, float, float, float],
                        dpr: float, width: int,
                        minHeight: int, maxHeight: int) -> Tuple[int, int, int, int]:
    """贴客户端左侧; 左侧放不下 (x<0) 时改贴右侧. 返回逻辑坐标 (x, y, w, h).

    client 是物理像素 (left, top, width, height), 需除以 dpr 转逻辑坐标.
    """
    left, top, w, h = client
    dpr = dpr or 1.0
    clientLeft = int(left / dpr)
    clientTop = int(top / dpr)
    clientRight = int((left + w) / dpr)
    clientH = int(h / dpr)

    height = int(max(minHeight, min(maxHeight, clientH)))
    x = clientLeft - width
    if x < 0:
        x = clientRight
    return x, clientTop, width, height


def shouldShowDock(enabled: bool, clientPresent: bool, clientRectValid: bool,
                   onTop: bool, clientForeground: bool,
                   ownActive: bool, inGame: bool = False) -> bool:
    """是否应显示侧边栏.

    置顶时窗口会浮在所有程序之上, 对局中也一样, 因此这两种情况下只在
    客户端前台或侧边栏自己处于活动状态 (用户正在点它) 时显示.
    ownActive 必须是"侧边栏自己"是否活动, 不能是任意 Seraphine 窗口:
    否则游戏中切到 Seraphine 主窗口就会让侧边栏浮到游戏上.
    """
    if not (enabled and clientPresent and clientRectValid):
        return False
    if onTop or inGame:
        return clientForeground or ownActive
    return True
