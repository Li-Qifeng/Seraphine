"""
OPGG 窗口海克斯辅助页。

在 ARAM Mayhem 游戏进行中, 根据当前英雄 + 已选强化 + (若可得) 当前 offer,
结合 OPGG 登场率/评级分与搭配协同规则, 显示强化选择优先级推荐。

由于 Live Client API 不暴露 ARAM Mayhem 强化数据, 已选强化需手动点击推荐项标记。
"""

import asyncio

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QFrame)
from qasync import asyncSlot

from app.common.logger import logger
from app.common.icons import Icon
from app.common.qfluentwidgets import (SmoothScrollArea, isDarkTheme,
                                       ToolTipFilter, ToolTipPosition,
                                       PushButton, TransparentToolButton)
from app.common.style_sheet import StyleSheet
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


class HextechAssistInterface(QFrame):
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
        self.championNameLabel = QLabel(self.tr("未选择英雄"))

        # 已选强化区
        self.selectedHeader = QHBoxLayout()
        self.selectedSectionLabel = QLabel(self.tr("已选强化"))
        self.selectedSectionLabel.setObjectName("sectionLabel")
        self.clearSelectedButton = TransparentToolButton(Icon.DELETE)
        self.clearSelectedButton.setFixedSize(22, 22)
        self.clearSelectedButton.setToolTip(self.tr("清空已选"))
        self.clearSelectedButton.setVisible(False)
        self.selectedHeader.addWidget(self.selectedSectionLabel)
        self.selectedHeader.addWidget(self.clearSelectedButton)
        self.selectedHeader.addStretch()

        self.selectedRow = QWidget()
        self.selectedRowLayout = QHBoxLayout(self.selectedRow)
        self.selectedIconLabels = []

        # 推荐区标题
        self.recommendSectionLabel = QLabel(self.tr("推荐强化 (点击添加为已选)"))
        self.recommendSectionLabel.setObjectName("sectionLabel")
        self.recommendListWidget = QWidget()
        self.recommendListLayout = QVBoxLayout(self.recommendListWidget)

        # 状态/提示
        self.statusLabel = QLabel("")
        self.statusLabel.setObjectName("statusLabel")
        self.statusLabel.setAlignment(Qt.AlignCenter)

        # 刷新按钮
        self.refreshButton = PushButton(self.tr("刷新"))
        self.refreshButton.setFixedHeight(30)

        self.__initLayout()
        self.__connectSignals()
        StyleSheet.OPGG_HEXTECH_ASSIST_INTERFACE.apply(self)

    def __initLayout(self):
        self.scrollArea.setObjectName("scrollArea")
        self.scrollWidget.setObjectName("scrollWidget")
        self.scrollLayout.setAlignment(Qt.AlignTop)
        self.scrollWidget.setLayout(self.scrollLayout)
        self.scrollArea.setWidget(self.scrollWidget)
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setViewportMargins(0, 0, 15, 0)
        self.scrollWidget.setContentsMargins(0, 0, 0, 0)
        self.vBoxLayout.setContentsMargins(0, 0, 0, 0)
        self.scrollLayout.setContentsMargins(0, 0, 0, 0)
        self.scrollLayout.setSpacing(4)

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
        self.scrollLayout.addLayout(self.selectedHeader)
        self.scrollLayout.addWidget(self.selectedRow)
        self.scrollLayout.addSpacing(12)
        self.scrollLayout.addWidget(self.recommendSectionLabel)
        self.scrollLayout.addWidget(self.recommendListWidget)
        self.scrollLayout.addWidget(self.statusLabel)
        self.scrollLayout.addStretch()

        self.recommendListLayout.setContentsMargins(0, 0, 0, 0)
        self.recommendListLayout.setSpacing(4)

        bottomBar = QHBoxLayout()
        bottomBar.setContentsMargins(0, 4, 0, 4)
        bottomBar.addStretch()
        bottomBar.addWidget(self.refreshButton)
        self.vBoxLayout.addWidget(self.scrollArea)
        self.vBoxLayout.addLayout(bottomBar)

    def __connectSignals(self):
        self.refreshButton.clicked.connect(self.__onRefreshClicked)
        self.clearSelectedButton.clicked.connect(self.__onClearSelected)

    @asyncSlot()
    async def __onRefreshClicked(self):
        await self.updateForChampion(self.championId)

    def __onClearSelected(self):
        self.selectedIds = []
        self.__updateSelectedRow()
        if self.allAugments:
            self.__refreshRecommendations()

    async def updateForChampion(self, championId):
        """根据英雄拉取 OPGG 强化数据, 初始展示全量推荐."""
        if not championId or championId <= 0:
            return
        self.championId = championId
        self.statusLabel.setText(self.tr("加载中..."))

        # 更新英雄栏
        try:
            icon_path = await connector.getChampionIcon(championId)
            if icon_path:
                self.championIcon.setPicture(icon_path)
            name = connector.manager.getChampionNameById(championId)
            if name:
                self.championNameLabel.setText(name)
        except (AttributeError, TypeError, KeyError) as e:
            logger.debug(f"hextech champion info load skipped: {e}")

        # 拉取 OPGG 海克斯强化数据
        try:
            if not getattr(opgg, 'apiSession', None) or opgg.apiSession.closed:
                await opgg.start()
            build = await opgg.getChampionBuild(
                region='global', mode='aram_mayhem',
                championId=championId, position='none', tier='all')
            self.allAugments = build['data'].get('augments') or []
            if not self.allAugments:
                self.statusLabel.setText(self.tr("无强化数据"))
                return
            self.statusLabel.setText("")
            self.__refreshRecommendations()
        except Exception as e:
            logger.warning(f"updateForChampion failed: {e}", TAG)
            self.statusLabel.setText(self.tr("加载失败"))

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
                except (AttributeError, TypeError, KeyError) as e:
                    logger.debug(f"augment tooltip load skipped: {e}")

        try:
            asyncio.ensure_future(_loadSelectedIcons())
        except RuntimeError:
            pass

        count = len(self.selectedIds)
        self.selectedSectionLabel.setText(
            self.tr("已选强化") + f" ({count}/6)")
        self.clearSelectedButton.setVisible(count > 0)

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
        for i in reversed(range(self.recommendListLayout.count())):
            item = self.recommendListLayout.itemAt(i)
            self.recommendListLayout.removeItem(item)
            if item.widget():
                item.widget().deleteLater()

        if not self.recommendations:
            self.statusLabel.setText(self.tr("暂无推荐"))
            return
        self.statusLabel.setText("")

        selected_set = set(self.selectedIds)
        for idx, rec in enumerate(self.recommendations[:15]):
            is_selected = rec['aug']['id'] in selected_set
            bar = RecommendedAugmentBar(idx + 1, rec, is_selected)
            bar.clicked.connect(self.__onRecommendClicked)
            self.recommendListLayout.addWidget(bar)

    def __onRecommendClicked(self, augId):
        """点击推荐项: 切换已选状态."""
        if augId in self.selectedIds:
            self.selectedIds.remove(augId)
        else:
            if len(self.selectedIds) >= 6:
                return
            self.selectedIds.append(augId)
        self.__updateSelectedRow()
        self.__refreshRecommendations()

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
        self.selectedSectionLabel.setText(self.tr("已选强化"))
        self.clearSelectedButton.setVisible(False)
        self.statusLabel.setText("")


class RecommendedAugmentBar(QFrame):
    """推荐强化项: 排名 + 图标 + 名称 + 稀有度 + 评分 + 推荐理由

    可点击切换已选状态。
    """
    clicked = pyqtSignal(int)

    def __init__(self, rank: int, rec: dict, isSelected: bool = False,
                 parent=None):
        super().__init__(parent)
        self.augId = rec['aug'].get('id')
        self.isSelected = isSelected
        aug = rec['aug']
        tier = rec.get('tier', 'silver')

        self.setFixedHeight(42)
        self.setCursor(Qt.PointingHandCursor)
        self.hBoxLayout = QHBoxLayout(self)
        self.hBoxLayout.setContentsMargins(6, 4, 6, 4)
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
        self.__updateSelectedStyle()

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
                if icon:
                    self.iconLabel.setPicture(icon)
                else:
                    local = await safeGetAugmentIcon(aid)
                    if local:
                        self.iconLabel.setPicture(local)
            except (AttributeError, TypeError, KeyError, ValueError) as e:
                logger.debug(f"augment icon load skipped: {e}")

        try:
            asyncio.ensure_future(_load())
        except RuntimeError:
            pass

    def __updateSelectedStyle(self):
        if self.isSelected:
            self.setStyleSheet(
                "RecommendedAugmentBar { border: 2px solid #4CAF50; "
                "border-radius: 4px; background-color: rgba(76, 175, 80, 0.12); }")
        else:
            self.setStyleSheet("")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.augId)
        super().mousePressEvent(event)
