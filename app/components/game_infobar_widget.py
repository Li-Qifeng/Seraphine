from PyQt5.QtCore import Qt, QRect, QTimer
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame, QSpacerItem, QSizePolicy)
from PyQt5.QtGui import QPen, QPainter, QColor

import asyncio

from app.common.qfluentwidgets import isDarkTheme, Theme, ToolTipFilter, ToolTipPosition
from app.common.signals import signalBus
from app.common.config import cfg
from app.common.logger import logger
from app.components.champion_icon_widget import RoundIcon, RoundedLabel
from app.components.color_label import ColorLabel, DeathsLabel
from app.components.animation_frame import ColorAnimationFrame


class RoundLevel(QFrame):
    def __init__(self, level, diameter, parent=None):
        super().__init__(parent)
        self.level = str(level)
        self.setFixedSize(diameter, diameter)
        self.setStyleSheet("RoundLevel{border: 1px solid black}")
        self.setStyleSheet("RoundLevel {font: bold 11px 'Segoe UI'}")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHints(
            QPainter.TextAntialiasing | QPainter.Antialiasing)
        if isDarkTheme():
            painter.setPen(QPen(QColor(120, 90, 40), 1, Qt.SolidLine))
            painter.setBrush(QColor(1, 10, 19))
            painter.drawEllipse(0, 0, self.width(), self.height())

            painter.setPen(QColor(153, 148, 135))
            painter.drawText(QRect(0, -1, 22, 22), Qt.AlignCenter, self.level)
        else:
            painter.setPen(QPen(QColor(120, 90, 40), 1, Qt.SolidLine))
            painter.setBrush(QColor(249, 249, 249))
            painter.drawEllipse(0, 0, self.width(), self.height())

            painter.setPen(QColor(1, 10, 19))
            painter.drawText(QRect(0, -1, 22, 22), Qt.AlignCenter, self.level)


class RoundIconWithLevel(QWidget):
    def __init__(self, icon, level, parent=None):
        super().__init__(parent)
        self.icon = RoundIcon(icon, 58, 6, 4, parent=self)
        self.level = RoundLevel(level, 22, self)
        self.level.move(42, 36)

        self.setFixedSize(64, 58)


class ResultModeSpell(QFrame):
    def __init__(self, remake, win, mode, spell1, spell2, rune, parent=None):
        super().__init__(parent)

        self.vBoxLayout = QVBoxLayout(self)
        self.spellsLayout = QHBoxLayout()
        self.resultLabel = ColorLabel()

        if remake:
            self.resultLabel.setText(self.tr("Remake"))
            self.resultLabel.setType('remake')

        elif win:
            self.resultLabel = ColorLabel(self.tr("Win"), 'win')
        else:
            self.resultLabel = ColorLabel(self.tr("Lose"), 'lose')

        self.modeLabel = QLabel(mode)
        self.modeLabel.setStyleSheet("QLabel {font: 12px;}")

        self.spell1 = RoundedLabel(spell1, 0, 2)
        self.spell2 = RoundedLabel(spell2, 0, 2)
        self.spell1.setFixedSize(22, 22)
        self.spell2.setFixedSize(22, 22)

        self.rune = RoundedLabel(rune, 0, 0)
        self.rune.setFixedSize(24, 24)

        self.__initLayout()
        self.vBoxLayout.setContentsMargins(0, 0, 0, 0)
        # self.setStyleSheet("ResultModeSpell {border: 1px solid black;}")

    def __initLayout(self):
        self.setMinimumWidth(100)

        self.spellsLayout.setSpacing(0)
        self.spellsLayout.addWidget(self.spell1)
        self.spellsLayout.addWidget(self.spell2)
        self.spellsLayout.addSpacing(5)
        self.spellsLayout.addWidget(self.rune)
        self.spellsLayout.addSpacerItem(
            QSpacerItem(1, 1, QSizePolicy.Expanding, QSizePolicy.Minimum)
        )

        self.vBoxLayout.setSpacing(0)
        self.vBoxLayout.addWidget(self.resultLabel)
        self.vBoxLayout.addWidget(self.modeLabel)
        self.vBoxLayout.addSpacing(5)
        self.vBoxLayout.addLayout(self.spellsLayout)


class ItemsKdaCsGold(QFrame):
    def __init__(self, items, kills, deaths, assists, cs, gold, parent=None):
        super().__init__(parent)
        self.setFixedSize(550, 67)

        self.vBoxLayout = QHBoxLayout(self)
        self.itemsLayout = QHBoxLayout()

        self.kills = QLabel(f"{kills}")
        self.slash1 = QLabel("/")
        self.deaths = DeathsLabel(f"{deaths}")
        self.slash2 = QLabel("/")
        self.assists = QLabel(f"{assists}")

        self.csLabel = QLabel(f"{cs}")
        self.goldLabel = QLabel(format(gold, ","))

        self.kills.setAlignment(Qt.AlignCenter)
        self.kills.setContentsMargins(0, 0, 0, 2)
        self.kills.setFixedWidth(23)
        self.kills.setObjectName("kills")
        self.slash1.setAlignment(Qt.AlignCenter)
        self.slash1.setContentsMargins(0, 0, 0, 2)
        self.slash1.setFixedWidth(9)
        self.slash1.setObjectName("slash1")
        self.deaths.setAlignment(Qt.AlignCenter)
        self.deaths.setContentsMargins(0, 0, 0, 2)
        self.deaths.setFixedWidth(23)
        self.deaths.setObjectName("deaths")
        self.slash2.setAlignment(Qt.AlignCenter)
        self.slash2.setContentsMargins(0, 0, 0, 2)
        self.slash2.setFixedWidth(9)
        self.slash2.setObjectName("slash2")
        self.assists.setAlignment(Qt.AlignCenter)
        self.assists.setContentsMargins(0, 0, 0, 2)
        self.assists.setFixedWidth(23)
        self.assists.setObjectName("assists")

        # self.kills.setStyleSheet("border: 1px solid black;")
        # self.slash1.setStyleSheet("border: 1px solid black;")
        # self.deaths.setStyleSheet("border: 1px solid black;")
        # self.slash2.setStyleSheet("border: 1px solid black;")
        # self.assists.setStyleSheet("border: 1px solid black;")

        self.csLabel.setAlignment(Qt.AlignCenter)
        self.csLabel.setContentsMargins(0, 0, 0, 2)
        self.goldLabel.setAlignment(Qt.AlignCenter)
        self.goldLabel.setContentsMargins(0, 0, 0, 2)
        self.goldLabel.setFixedWidth(55)

        self.csIcon = RoundedLabel(borderWidth=0, radius=0)
        color = "white" if isDarkTheme() else "black"
        self.csIcon.setPicture(f"app/resource/images/Minions_{color}.png")
        self.csIcon.setFixedSize(16, 16)
        self.csIcon.setAlignment(Qt.AlignCenter)

        self.goldIcon = RoundedLabel(borderWidth=0, radius=0)
        self.goldIcon.setPicture(f"app/resource/images/Gold_{color}.png")
        self.goldIcon.setFixedSize(16, 16)
        self.goldIcon.setAlignment(Qt.AlignCenter)

        # self.csLabel.setStyleSheet("QLabel {border: 1px solid black;}")
        # self.goldLabel.setStyleSheet("QLabel {border: 1px solid black;}")

        self.__initLayout(items)
        #  self.setStyleSheet("ItemsKdaCsGold {border: 1px solid black;}")
        cfg.themeChanged.connect(self.__updateIconColor)

    def __initLayout(self, items):
        self.itemsLayout.setSpacing(0)

        for item in items:
            image = RoundedLabel(item, 1)
            image.setFixedSize(34, 34)

            self.itemsLayout.addWidget(image)

        self.csLabel.setFixedWidth(40)

        self.vBoxLayout.setContentsMargins(0, 0, 0, 0)
        self.vBoxLayout.setSpacing(0)
        self.vBoxLayout.addWidget(self.kills)
        self.vBoxLayout.addSpacing(-11)
        self.vBoxLayout.addWidget(self.slash1)
        self.vBoxLayout.addSpacing(-11)
        self.vBoxLayout.addWidget(self.deaths)
        self.vBoxLayout.addSpacing(-11)
        self.vBoxLayout.addWidget(self.slash2)
        self.vBoxLayout.addSpacing(-11)
        self.vBoxLayout.addWidget(self.assists)
        self.vBoxLayout.addSpacing(5)
        self.vBoxLayout.addWidget(self.csLabel)
        self.vBoxLayout.addSpacing(-6)
        self.vBoxLayout.addWidget(self.csIcon)
        self.vBoxLayout.addSpacing(15)
        self.vBoxLayout.addLayout(self.itemsLayout)
        self.vBoxLayout.addSpacing(5)
        self.vBoxLayout.addWidget(self.goldLabel)
        self.vBoxLayout.addSpacing(-3)
        self.vBoxLayout.addWidget(self.goldIcon)

    def __updateIconColor(self, theme: Theme):
        color = "white" if theme == Theme.DARK else "black"
        self.csIcon.setPicture(f"app/resource/images/Minions_{color}.png")
        self.goldIcon.setPicture(f"app/resource/images/Gold_{color}.png")


class MapTime(QFrame):
    def __init__(self, map, position, time, duration, parent=None):
        super().__init__(parent)
        self.vBoxLayout = QVBoxLayout(self)

        self.mapLabel = QLabel(
            f'{map} - {position}' if position is not None else f'{map}')
        self.timeLabel = QLabel(f"{duration} · {time}")

        self.__initLayout()

        # self.setStyleSheet("MapTime {border: 1px solid black}")

    def __initLayout(self):
        self.vBoxLayout.setContentsMargins(0, 5, 0, 0)
        self.mapLabel.setStyleSheet("QLabel {font: 12px;}")
        self.timeLabel.setStyleSheet("QLabel {font: 12px;}")

        self.vBoxLayout.addWidget(self.mapLabel)
        self.vBoxLayout.addWidget(self.timeLabel)
        self.vBoxLayout.addSpacerItem(
            QSpacerItem(1, 1, QSizePolicy.Minimum, QSizePolicy.Expanding)
        )


class AugmentRow(QFrame):
    """海克斯大乱斗强化图标行, 异步加载强化图标 (OPGG 图标本身带稀有度颜色)"""

    # 固定宽度: 4 个图标位 × 22px + 3 间距 × 2px = 94px
    # 用于表头列对齐 (即使该玩家只有 2-3 个强化, 也保留 4 个位置的宽度)
    FIXED_WIDTH = 94

    def __init__(self, augmentIds: list, parent=None, championId=None):
        super().__init__(parent)
        self.augmentIds = augmentIds or []
        self.championId = championId
        self.hBoxLayout = QHBoxLayout(self)
        self.iconLabels = []

        self.__initLayout()
        # 异步加载强化图标
        if self.augmentIds:
            QTimer.singleShot(0, self.__loadAugmentIcons)

    def __initLayout(self):
        self.hBoxLayout.setContentsMargins(0, 0, 0, 0)
        self.hBoxLayout.setSpacing(2)
        # 固定宽度, 保证表头列对齐
        self.setFixedWidth(self.FIXED_WIDTH)

        # 始终创建 4 个图标槽位 (海克斯大乱斗最多 4 个强化)
        # 没有强化的槽位显示为空占位
        for i in range(4):
            label = RoundedLabel(borderWidth=1, radius=3.0)
            label.setFixedSize(22, 22)
            # 无强化数据的槽位设为透明
            if i >= len(self.augmentIds):
                label.setVisible(False)
            self.iconLabels.append(label)
            self.hBoxLayout.addWidget(label)

        # 只对实际有强化 ID 的槽位加载图标
        self._activeLabels = self.iconLabels[:len(self.augmentIds)]

    async def __loadAugmentIconsAsync(self):
        try:
            from app.lol.static_data import (
                safeGetAugmentIcon, safeGetAugmentName)
            # 先确保 OPGG 已拉取当前英雄的强化列表 (会注册 augId -> OPGG 图标路径)
            # OPGG 海克斯图标本身带稀有度颜色, 优于 LCU 默认图标
            await self.__ensureOpggIcons()

            for label, aid in zip(self._activeLabels, self.augmentIds):
                try:
                    icon = await safeGetAugmentIcon(aid)
                    if icon:
                        label.setPicture(icon)
                    # 异步加载强化名称作为 tooltip
                    name = await safeGetAugmentName(aid)
                    if name:
                        label.setToolTip(name)
                        label.installEventFilter(
                            ToolTipFilter(label, 0, ToolTipPosition.TOP))
                except Exception as e:
                    logger.warning(f"[AugmentRow] load aid={aid} failed: {e}")
        except Exception as e:
            logger.warning(f"[AugmentRow] load failed: {e}")

    async def __ensureOpggIcons(self):
        """确保 OPGG 已拉取当前英雄的海克斯强化图标

        OPGG 图标本身带稀有度颜色, 拉取后会注册到 safeGetAugmentIcon 优先返回.
        若本地已有缓存图标则跳过.
        """
        if not self.championId:
            return
        try:
            from app.lol.static_data import getAugmentOpggIconPath
            # 检查是否已有 OPGG 图标缓存, 有则无需拉取
            need_fetch = any(
                not getAugmentOpggIconPath(aid) for aid in self.augmentIds)
            if not need_fetch:
                return
            from app.lol.opgg import opgg
            if not getattr(opgg, 'apiSession', None) or opgg.apiSession.closed:
                await opgg.start()
            await opgg.fetchMayhemAugmentRarities(self.championId)
        except Exception as e:
            logger.warning(f"[AugmentRow] ensure OPGG icons failed: {e}")

    def __loadAugmentIcons(self):
        try:
            asyncio.ensure_future(self.__loadAugmentIconsAsync())
        except RuntimeError:
            pass


class VerdictBadge(QFrame):
    """战犯/躺赢狗徽章: 图标+文本的醒目标签.

    只有两种标签:
    - 战犯 (war_criminal): 红色系
    - 躺赢狗 (carried_dog): 金色系

    子状态:
    - teamUnderperformed=True: 团队整体低迷, 该嫌疑者与队友差距不大
      此时战犯用橙色显示 (降低视觉权重, 表示"不是全怪他")

    样式:
    - isSuspect=True  (当前召唤师是嫌疑者): 实色背景 + 白字, 醒目
    - isSuspect=False (本局有 verdict 但当前召唤师不是嫌疑者):
      保留类型颜色作描边, 背景半透明, 让用户一眼看出类型但不喧宾夺主
    """

    # (light_fg_suspect, light_bg_suspect, light_border_suspect,
    #  light_fg_other, light_bg_other, light_border_other,
    #  dark_fg_suspect, dark_bg_suspect, dark_border_suspect,
    #  dark_fg_other, dark_bg_other, dark_border_other)
    _COLORS = {
        '战犯': ('#fff', '#c0392b', '#922b21',
                 '#c0392b', 'rgba(192,57,43,0.12)', '#e74c3c',
                 '#fff', '#c0392b', '#e74c3c',
                 '#ff6b6b', 'rgba(231,76,60,0.18)', '#ff6b6b'),
        '躺赢狗': ('#fff', '#d4a017', '#a67c00',
                   '#a67c00', 'rgba(212,160,23,0.14)', '#d4a017',
                   '#fff', '#d4a017', '#ffc107',
                   '#ffd54f', 'rgba(255,193,7,0.18)', '#ffc107'),
        # 团队低迷时战犯用橙色 (比红色弱, 表示"不是全怪他")
        '战犯_团队低迷': ('#fff', '#e67e22', '#a05a14',
                          '#e67e22', 'rgba(230,126,34,0.14)', '#e67e22',
                          '#fff', '#d68910', '#f39c12',
                          '#ffb74d', 'rgba(243,156,18,0.18)', '#f39c12'),
    }

    _ICONS = {
        '战犯': '⚠',
        '躺赢狗': '🐶',
    }

    _METRIC_LABELS = {
        'damage': '伤害', 'deaths': '死亡', 'gold': '经济',
        'kda': 'KDA', 'damage_taken': '承伤', 'shield_heal': '护盾治疗',
        'cc': '控制时长', 'vision': '视野',
    }

    def __init__(self, label: str, isSuspect: bool = False,
                 evidence: list = None, teamUnderperformed: bool = False,
                 parent=None):
        super().__init__(parent)
        self.label = label
        self.teamUnderperformed = teamUnderperformed

        self.hBoxLayout = QHBoxLayout(self)
        self.hBoxLayout.setContentsMargins(6, 2, 6, 2)
        self.hBoxLayout.setSpacing(3)

        icon_text = self._ICONS.get(label, '')
        if icon_text:
            self.iconLabel = QLabel(icon_text)
            self.iconLabel.setStyleSheet("font: 12px 'Segoe UI';")
            self.hBoxLayout.addWidget(self.iconLabel)

        self.textLabel = QLabel(label)
        self.textLabel.setStyleSheet("font: bold 11px 'Microsoft YaHei', 'Segoe UI';")
        self.hBoxLayout.addWidget(self.textLabel)

        self.setFixedHeight(26)

        # 团队低迷的战犯用橙色色板
        color_key = label
        if teamUnderperformed and label == '战犯':
            color_key = '战犯_团队低迷'
        palette = self._COLORS.get(color_key)
        if palette is None:
            palette = ('#fff', '#555', '#333',
                       '#555', 'rgba(85,85,85,0.12)', '#555',
                       '#fff', '#555', '#555',
                       '#aaa', 'rgba(85,85,85,0.18)', '#aaa')

        if isDarkTheme():
            if isSuspect:
                fg, bg, border = palette[6], palette[7], palette[8]
            else:
                fg, bg, border = palette[9], palette[10], palette[11]
        else:
            if isSuspect:
                fg, bg, border = palette[0], palette[1], palette[2]
            else:
                fg, bg, border = palette[3], palette[4], palette[5]

        self.setStyleSheet(
            f"VerdictBadge {{ background: {bg}; "
            f"border: 1px solid {border}; border-radius: 6px; }}")
        self.textLabel.setStyleSheet(
            f"QLabel {{ color: {fg}; "
            f"font: bold 11px 'Microsoft YaHei', 'Segoe UI'; }}")
        if icon_text:
            self.iconLabel.setStyleSheet(
                f"QLabel {{ color: {fg}; font: 12px 'Segoe UI'; }}")

        # 设置 evidence tooltip
        if evidence:
            tip = self._formatEvidence(evidence, label, teamUnderperformed)
            if tip:
                self.setToolTip(tip)
                self.installEventFilter(
                    ToolTipFilter(self, 300, ToolTipPosition.BOTTOM))

    def _formatEvidence(self, evidence: list, label: str,
                        teamUnderperformed: bool = False) -> str:
        """将诊断证据列表格式化为 tooltip 文本.

        输出面向普通玩家, 用口语化短句描述偏离情况, 不暴露 z-score 等统计量.
        团队低迷时在标题后追加说明.
        """
        # 标题: 根据标签给出一句通俗解释
        title_map = {
            '战犯': '这把你拖了队伍后腿',
            '躺赢狗': '这把你被队友带飞了',
        }
        title = title_map.get(label, label)
        lines = [f"【{label}】{title}"]

        # 团队低迷子状态标注
        if teamUnderperformed:
            lines.append('  (整队表现都偏低, 不全是你的锅)')

        for item in evidence:
            metric = self._METRIC_LABELS.get(
                item.get('metric', ''), item.get('metric', ''))
            val = item.get('value', 0)
            avg = item.get('teamAvg', 0)
            sev = item.get('severity', 'normal')
            if sev == 'normal':
                continue

            # 偏离程度描述 (基于 severity)
            # high_*: 显著, 普通 pos/neg: 略
            is_high = sev in ('high_pos', 'high_neg')
            degree = '显著' if is_high else '略'

            # metric 是数值型时格式化千分位
            if metric in ('伤害', '承伤', '护盾治疗', '控制时长'):
                val_str = f"{val:,.0f}"
                avg_str = f"{avg:,.0f}"
            else:
                val_str = f"{val}"
                avg_str = f"{avg}"

            # 描述方向: 死亡偏高=坏事, 其他指标偏高=好事
            if metric == '死亡':
                if sev in ('high_pos', 'pos'):
                    comment = f"{degree}偏多 (送得厉害)"
                else:
                    comment = f"{degree}偏少"
            elif sev in ('high_neg', 'neg'):
                comment = f"{degree}垫底"
            else:  # high_pos / pos
                comment = f"{degree}突出"

            lines.append(
                f"· {metric}: {val_str} | 队友平均 {avg_str} — {comment}")

        return '\n'.join(lines) if len(lines) > 1 else ''


class GameInfoBar(ColorAnimationFrame):
    def __init__(self, game: dict = None, parent: QWidget = None,
                 verdictLabel: str = None, verdictIsSuspect: bool = False,
                 verdictEvidence: list = None):
        if game['remake']:
            type = 'remake'
        elif game['win']:
            type = 'win'
        else:
            type = 'lose'

        self.gameId = game['gameId']
        self.verdictLabel = verdictLabel
        self.verdictIsSuspect = verdictIsSuspect
        self.verdictEvidence = verdictEvidence or []

        super().__init__(type=type, parent=parent)
        self.hBoxLayout = QHBoxLayout(self)

        self.setProperty('pressed', False)

        self.__initWidget(game)
        self.__initLayout()

        self.clicked.connect(
            lambda: signalBus.careerGameBarClicked.emit(str(self.gameId)))

    def __initWidget(self, game):
        self.championIcon = RoundIconWithLevel(
            game["championIcon"], game["champLevel"])
        self.resultModeSpells = ResultModeSpell(
            game["remake"],
            game["win"],
            game["name"],
            game["spell1Icon"],
            game["spell2Icon"],
            game["runeIcon"],
        )
        self.itemsKdaCsGold = ItemsKdaCsGold(
            game["itemIcons"],
            game["kills"],
            game["deaths"],
            game["assists"],
            game["cs"],
            game["gold"],
        )
        self.mapTime = MapTime(
            game["map"], game['position'], game["time"], game["duration"])

        # 海克斯大乱斗: 强化图标行
        augmentIds = game.get("augmentIds") or []
        championId = game.get("championId")
        self.augmentRow = AugmentRow(
            augmentIds, championId=championId) if augmentIds else None

    def __initLayout(self):
        self.hBoxLayout.setContentsMargins(11, 8, 11, 8)
        self.hBoxLayout.addWidget(self.championIcon)
        self.hBoxLayout.addSpacing(5)
        self.hBoxLayout.addWidget(self.resultModeSpells)
        self.hBoxLayout.addSpacerItem(
            QSpacerItem(1, 1, QSizePolicy.Expanding, QSizePolicy.Minimum)
        )
        self.hBoxLayout.addWidget(self.itemsKdaCsGold)
        self.hBoxLayout.addSpacerItem(
            QSpacerItem(1, 1, QSizePolicy.Expanding, QSizePolicy.Minimum)
        )
        # 海克斯强化图标 (仅在海克斯大乱斗时显示)
        if self.augmentRow:
            self.hBoxLayout.addSpacing(10)
            self.hBoxLayout.addWidget(self.augmentRow)
            self.hBoxLayout.addSpacing(10)
        else:
            self.hBoxLayout.addSpacing(15)
        self.hBoxLayout.addWidget(self.mapTime)
        # 战犯/躺赢狗徽章 (仅当本局有 verdict 命中时显示)
        if self.verdictLabel:
            self.hBoxLayout.addSpacing(8)
            self.hBoxLayout.addWidget(
                VerdictBadge(self.verdictLabel, self.verdictIsSuspect,
                             self.verdictEvidence))
