"""
OPGG 窗口海克斯辅助页。

在 ARAM Mayhem 游戏进行中, 根据当前英雄 + 已选强化 + (若可得) 当前 offer,
结合 OPGG 登场率/评级分与搭配协同规则, 显示强化选择优先级推荐。
"""

import asyncio

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QFrame)
from qasync import asyncSlot

from app.common.logger import logger
from app.common.qfluentwidgets import (SmoothScrollArea, isDarkTheme,
                                       ToolTipFilter, ToolTipPosition,
                                       PushButton)
from app.components.champion_icon_widget import RoundedLabel
from app.lol.connector import connector
from app.lol.opgg import opgg
from app.lol.static_data import safeGetAugmentIcon, safeGetAugmentName
from app.lol.augment_recommender import augmentRecommender

TAG = "HextechAssist"

_TIER_COLORS = {
    'silver': ('#9E9E9E', '#BDBDBD'),
    'gold': ('#FFC107', '#FFD54F'),
    'prismatic': ('#E040FB', '#FF80AB'),
}

_TIER_LABELS = {
    'silver': '银色',
    'gold': '金色',
    'prismatic': '棱彩',
}


class HextechAssistInterface(QWidget):
    """海克斯辅助页: 已选强化 + 推荐列表"""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.championId = None
        self.allAugments = []  # opgg 三档输出 [[silver...], [gold...], [prismatic...]]
        self.selectedIds = []
        self.offerIds = []
        self.recommendations = []

        self.vBoxLayout = QVBoxLayout(self)
        self.scrollArea = SmoothScrollArea()
        self.scrollWidget = QWidget()
        self.scrollLayout = QVBoxLayout()

        # 顶部英雄栏
        self.championBar = QWidget()
        self.championBarLayout = QHBoxLayout(self.championBar)
        self.championIcon = RoundedLabel(borderWidth=0, radius=3.0)
        self.championIcon.setFixedSize(32, 32)
        self.championNameLabel = QLabel(self.tr("No champion"))

        # 已选强化区
        self.selectedSectionLabel = QLabel(self.tr("Selected augments"))
        self.selectedRow = QWidget()
        self.selectedRowLayout = QHBoxLayout(self.selectedRow)
        self.selectedIconLabels = []

        # 推荐区标题
        self.recommendSectionLabel = QLabel(self.tr("Recommended augments"))
        self.recommendListWidget = QWidget()
        self.recommendListLayout = QVBoxLayout(self.recommendListWidget)

        # 状态/提示
        self.statusLabel = QLabel("")
        self.statusLabel.setAlignment(Qt.AlignCenter)

        # 刷新按钮
        self.refreshButton = PushButton(self.tr("Refresh"))
        self.refreshButton.setFixedHeight(30)

        self.__initLayout()
        self.__connectSignals()

    def __initLayout(self):
        self.scrollArea.setObjectName("scrollArea")
        self.scrollWidget.setObjectName("scrollWidget")
        self.scrollLayout.setAlignment(Qt.AlignTop)
        self.scrollWidget.setLayout(self.scrollLayout)
        self.scrollArea.setWidget(self.scrollWidget)
        self.scrollArea.setWidgetResizable(True)

        # 英雄栏
        self.championBarLayout.setContentsMargins(0, 0, 0, 0)
        self.championBarLayout.setSpacing(8)
        self.championBarLayout.addWidget(self.championIcon)
        self.championBarLayout.addWidget(self.championNameLabel)
        self.championBarLayout.addStretch()

        # 已选强化行
        self.selectedRowLayout.setContentsMargins(0, 0, 0, 0)
        self.selectedRowLayout.setSpacing(4)
        for i in range(6):
            label = RoundedLabel(borderWidth=1, radius=3.0)
            label.setFixedSize(28, 28)
            label.setVisible(False)
            self.selectedIconLabels.append(label)
            self.selectedRowLayout.addWidget(label)
        self.selectedRowLayout.addStretch()

        # 组装
        self.scrollLayout.addWidget(self.championBar)
        self.scrollLayout.addSpacing(8)
        self.scrollLayout.addWidget(self.selectedSectionLabel)
        self.scrollLayout.addWidget(self.selectedRow)
        self.scrollLayout.addSpacing(12)
        self.scrollLayout.addWidget(self.recommendSectionLabel)
        self.scrollLayout.addWidget(self.recommendListWidget)
        self.scrollLayout.addWidget(self.statusLabel)
        self.scrollLayout.addStretch()

        bottomBar = QHBoxLayout()
        bottomBar.addStretch()
        bottomBar.addWidget(self.refreshButton)
        self.vBoxLayout.addWidget(self.scrollArea)
        self.vBoxLayout.addLayout(bottomBar)

    def __connectSignals(self):
        self.refreshButton.clicked.connect(self.__onRefreshClicked)

    @asyncSlot()
    async def __onRefreshClicked(self):
        await self.updateForChampion(self.championId)

    async def updateForChampion(self, championId):
        """根据英雄拉取 OPGG 强化数据, 初始展示全量推荐."""
        if not championId or championId <= 0:
            return
        self.championId = championId
        self.statusLabel.setText(self.tr("Loading..."))

        # 更新英雄栏
        try:
            icon_path = await connector.getChampionIcon(championId)
            if icon_path:
                self.championIcon.setPicture(icon_path)
            name = connector.manager.getChampionNameById(championId)
            if name:
                self.championNameLabel.setText(name)
        except Exception:
            pass

        # 拉取 OPGG 海克斯强化数据
        try:
            if not getattr(opgg, 'apiSession', None) or opgg.apiSession.closed:
                await opgg.start()
            build = await opgg.getChampionBuild(
                region='global', mode='aram_mayhem',
                championId=championId, position='none', tier='all')
            self.allAugments = build['data'].get('augments') or []
            if not self.allAugments:
                self.statusLabel.setText(self.tr("No augment data"))
                return
            self.statusLabel.setText("")
            self.__refreshRecommendations()
        except Exception as e:
            logger.warning(f"updateForChampion failed: {e}", TAG)
            self.statusLabel.setText(self.tr("Failed to load"))

    def updateLiveState(self, liveData):
        """接收实时数据 (已选+offer), 刷新已选区和推荐列表.

        Args:
            liveData: {'selected': [augId...], 'offer': [augId...], 'round': int} 或 None
        """
        if not liveData:
            return
        self.selectedIds = liveData.get('selected') or []
        self.offerIds = liveData.get('offer') or []
        self.__updateSelectedRow()
        if self.allAugments:
            self.__refreshRecommendations()

    def __updateSelectedRow(self):
        """刷新已选强化图标行."""
        # 隐藏所有槽位
        for label in self.selectedIconLabels:
            label.setVisible(False)

        async def _loadSelectedIcons():
            for i, aid in enumerate(self.selectedIds[:6]):
                if i >= len(self.selectedIconLabels):
                    break
                label = self.selectedIconLabels[i]
                label.setVisible(True)
                try:
                    icon = await safeGetAugmentIcon(aid)
                    if icon:
                        label.setPicture(icon)
                    name = await safeGetAugmentName(aid)
                    if name:
                        label.setToolTip(name)
                        label.installEventFilter(
                            ToolTipFilter(label, 0, ToolTipPosition.TOP))
                except Exception:
                    pass

        try:
            asyncio.ensure_future(_loadSelectedIcons())
        except RuntimeError:
            pass

        # 更新已选区标题
        count = len(self.selectedIds)
        self.selectedSectionLabel.setText(
            self.tr("Selected augments") + f" ({count}/6)")

    def __refreshRecommendations(self):
        """重算推荐列表并刷新 UI."""
        if not self.allAugments:
            return

        self.recommendations = augmentRecommender.recommend(
            selectedAugIds=self.selectedIds,
            allAugments=self.allAugments,
            offerAugIds=self.offerIds or None,
        )
        self.__renderRecommendList()

    def __renderRecommendList(self):
        """渲染推荐列表 UI."""
        # 清空旧列表
        for i in reversed(range(self.recommendListLayout.count())):
            item = self.recommendListLayout.itemAt(i)
            self.recommendListLayout.removeItem(item)
            if item.widget():
                item.widget().deleteLater()

        if not self.recommendations:
            self.statusLabel.setText(self.tr("No recommendations"))
            return
        self.statusLabel.setText("")

        # 限制显示前 15 项
        for idx, rec in enumerate(self.recommendations[:15]):
            bar = RecommendedAugmentBar(idx + 1, rec)
            self.recommendListLayout.addWidget(bar)

    def clearState(self):
        """清空状态 (游戏结束时调用)."""
        self.selectedIds = []
        self.offerIds = []
        self.recommendations = []
        for label in self.selectedIconLabels:
            label.setVisible(False)
        for i in reversed(range(self.recommendListLayout.count())):
            item = self.recommendListLayout.itemAt(i)
            self.recommendListLayout.removeItem(item)
            if item.widget():
                item.widget().deleteLater()
        self.selectedSectionLabel.setText(self.tr("Selected augments"))
        self.statusLabel.setText("")


class RecommendedAugmentBar(QFrame):
    """推荐强化项: 排名 + 图标 + 名称 + 稀有度 + 评分 + 推荐理由"""

    def __init__(self, rank: int, rec: dict, parent=None):
        super().__init__(parent)
        self.rank = rank
        self.rec = rec
        aug = rec['aug']
        tier = rec.get('tier', 'silver')

        self.hBoxLayout = QHBoxLayout(self)
        self.hBoxLayout.setContentsMargins(4, 4, 4, 4)
        self.hBoxLayout.setSpacing(8)

        # 排名
        self.rankLabel = QLabel(f"#{rank}")
        self.rankLabel.setFixedWidth(24)
        self.rankLabel.setAlignment(Qt.AlignCenter)
        self.rankLabel.setStyleSheet("font: bold 12px 'Segoe UI';")

        # 图标
        tier_colors = _TIER_COLORS.get(tier, _TIER_COLORS['silver'])
        border_color = tier_colors[0] if not isDarkTheme() else tier_colors[1]
        self.iconLabel = RoundedLabel(borderWidth=2, radius=3.0)
        self.iconLabel.setFixedSize(32, 32)
        # 边框颜色通过 borderColor 属性设置 (RoundedLabel.paintEvent 读取此属性)
        from PyQt5.QtGui import QColor
        self.iconLabel.borderColor = QColor(border_color)

        # 名称+理由
        self.nameLayout = QVBoxLayout()
        self.nameLayout.setContentsMargins(0, 0, 0, 0)
        self.nameLayout.setSpacing(0)
        self.nameLabel = QLabel(aug.get('name', ''))
        self.nameLabel.setStyleSheet("font: 12px 'Segoe UI';")
        self.reasonLabel = QLabel(rec.get('reason', ''))
        self.reasonLabel.setStyleSheet(
            "font: 10px 'Segoe UI'; color: #888;" if not isDarkTheme()
            else "font: 10px 'Segoe UI'; color: #aaa;")
        self.nameLayout.addWidget(self.nameLabel)
        if rec.get('reason'):
            self.nameLayout.addWidget(self.reasonLabel)

        # 稀有度标签
        self.tierLabel = QLabel(_TIER_LABELS.get(tier, ''))
        self.tierLabel.setFixedWidth(36)
        self.tierLabel.setAlignment(Qt.AlignCenter)
        self.tierLabel.setStyleSheet(
            f"color: {border_color}; font: 11px 'Segoe UI';")

        # 评分
        score = rec.get('score', 0)
        self.scoreLabel = QLabel(f"{score:.2f}")
        self.scoreLabel.setFixedWidth(36)
        self.scoreLabel.setAlignment(Qt.AlignCenter)
        self.scoreLabel.setStyleSheet("font: bold 11px 'Segoe UI';")

        # tooltip: 强化描述
        desc = aug.get('desc') or aug.get('tooltip') or ''
        if desc:
            import re
            desc = re.sub(r'<[^>]+>', '', desc)
            desc = re.sub(r'\s+', ' ', desc).strip()
            if desc:
                self.setToolTip(desc[:200])
                self.installEventFilter(ToolTipFilter(self, 200))

        self.__initLayout()
        self.__loadIcon(aug)

    def __initLayout(self):
        self.hBoxLayout.addWidget(self.rankLabel)
        self.hBoxLayout.addWidget(self.iconLabel)
        self.hBoxLayout.addLayout(self.nameLayout, stretch=1)
        self.hBoxLayout.addWidget(self.tierLabel)
        self.hBoxLayout.addWidget(self.scoreLabel)

    def __loadIcon(self, aug):
        """异步加载强化图标."""
        aid = aug.get('id')
        icon = aug.get('icon')

        async def _load():
            try:
                # 优先用 OPGG 提供的图标路径
                if icon:
                    self.iconLabel.setPicture(icon)
                else:
                    local = await safeGetAugmentIcon(aid)
                    if local:
                        self.iconLabel.setPicture(local)
            except Exception:
                pass

        try:
            asyncio.ensure_future(_load())
        except RuntimeError:
            pass
