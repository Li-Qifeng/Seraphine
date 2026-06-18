from PyQt5.QtCore import Qt, QSize, QRect, pyqtSignal
from PyQt5.QtGui import QIcon, QShowEvent, QPixmap, QPainter, QPainterPath, QColor, QPen
from PyQt5.QtWidgets import (QVBoxLayout, QHBoxLayout, QGridLayout, QFrame,
                             QLabel, QWidget, QScrollArea, QApplication)

from qasync import asyncSlot

from app.common.style_sheet import StyleSheet
from app.common.signals import signalBus
from app.common.logger import logger
from app.common.util import getLolClientWindowPos
from app.common.qfluentwidgets import (ToolTipFilter, ToolTipPosition,
                                       FlyoutViewBase, StrongBodyLabel,
                                       CaptionLabel, isDarkTheme)
from app.components.champion_icon_widget import RoundIconButton, RoundIcon
from app.lol.connector import connector
from app.lol.aram import AramBuff
from app.lol.tools import _getLocalChampionId, _getBenchChampionIds
from app.common.config import cfg
from app.view.opgg_window import OpggWindowBase

TAG = 'HextechWindow'


class HextechSelectInterface(QFrame):
    """抢英雄界面: 手持 + 备选席 (可点击抢). 简洁, 不显示队友."""

    championToggled = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("HextechInterface")

        self.vBoxLayout = QVBoxLayout(self)

        # 顶部: 标题 + 状态
        self.titleLabel = StrongBodyLabel(self.tr("抢英雄"))
        self.statusLabel = CaptionLabel("")

        # 手持区
        self.mineLabel = CaptionLabel(self.tr("手持"))
        self.mineWidget = QWidget()
        self.mineLayout = QHBoxLayout(self.mineWidget)
        self.mineLayout.setContentsMargins(0, 0, 0, 0)
        self.mineLayout.setAlignment(Qt.AlignCenter)

        # 备选席区
        self.benchLabel = CaptionLabel(self.tr("备选席（点击抢）"))
        self.gridWidget = QWidget()
        self.gridLayout = QGridLayout(self.gridWidget)

        self.scrollArea = QScrollArea()
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setFrameShape(QFrame.NoFrame)
        self.scrollArea.setWidget(self.gridWidget)

        self._buttons = {}       # championId -> RoundIconButton (备选席)
        self._mineButton = None  # 手持头像
        self._selectedId = None

        self.__initLayout()
        StyleSheet.HEXTECH_WINDOW.apply(self)
        self.scrollArea.setStyleSheet("background: transparent;")
        self.scrollArea.viewport().setStyleSheet("background: transparent;")
        self.gridWidget.setStyleSheet("background: transparent;")
        self.mineWidget.setStyleSheet("background: transparent;")

    def paintEvent(self, event):
        """跟随主题背景"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        if isDarkTheme():
            painter.setBrush(QColor(32, 32, 32))
        else:
            painter.setBrush(QColor(243, 243, 243))
        painter.drawRect(self.rect())

    def __initLayout(self):
        self.statusLabel.setObjectName("contentLabel")
        self.mineLabel.setObjectName("hintLabel")
        self.benchLabel.setObjectName("hintLabel")

        self.vBoxLayout.setContentsMargins(10, 10, 10, 10)
        self.vBoxLayout.setSpacing(6)

        self.vBoxLayout.addWidget(self.titleLabel, alignment=Qt.AlignCenter)
        self.vBoxLayout.addWidget(self.statusLabel, alignment=Qt.AlignCenter)
        self.vBoxLayout.addSpacing(2)

        self.vBoxLayout.addWidget(self.mineLabel, alignment=Qt.AlignLeft)
        self.vBoxLayout.addWidget(self.mineWidget)
        self.vBoxLayout.addSpacing(2)

        self.vBoxLayout.addWidget(self.benchLabel, alignment=Qt.AlignLeft)
        self.vBoxLayout.addWidget(self.scrollArea)

        self.gridLayout.setSpacing(6)
        self.gridLayout.setContentsMargins(0, 0, 0, 0)
        self.gridLayout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

    def clearAll(self):
        """清空所有头像"""
        # 先主动隐藏所有 tooltip, 避免 deleteLater 延迟期间 tooltip 堆叠不消失
        for btn in list(self._buttons.values()):
            btn.cleanupToolTip()
        if self._mineButton:
            self._mineButton.cleanupToolTip()
        # 清备选席
        while self.gridLayout.count():
            item = self.gridLayout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._buttons = {}
        # 清手持
        while self.mineLayout.count():
            item = self.mineLayout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._mineButton = None
        self._selectedId = None

    def setMine(self, championId, iconPath, name):
        """设置手持英雄"""
        btn = RoundIconButton(iconPath, 56, 4, 2, name, championId, self)
        btn.isWishlist = championId in (cfg.get(cfg.hextechChampions) or [])
        btn.setToolTip(f"{name}（手持）")
        filter = ToolTipFilter(btn, 0, ToolTipPosition.BOTTOM)
        btn.installEventFilter(filter)
        btn.setToolTipFilter(filter)
        # 手持不可点击抢 (它就是你的)
        self.mineLayout.addWidget(btn)
        self._mineButton = btn

    def addBenchChampion(self, championId, iconPath, name,
                         isWishlist=False, priority=0, buffTip=""):
        """添加备选席英雄 (可点击抢)"""
        btn = RoundIconButton(iconPath, 48, 4, 2, name, championId, self)
        btn.isWishlist = isWishlist

        tip = f"{name}（备选席）"
        if isWishlist:
            tip += f" ★愿望单 #{priority}"
        if buffTip:
            tip += f"\n{buffTip}"
        btn.setToolTip(tip)
        filter = ToolTipFilter(btn, 0, ToolTipPosition.BOTTOM)
        btn.installEventFilter(filter)
        btn.setToolTipFilter(filter)

        btn.clicked.connect(lambda cid=championId: self.__onButtonClicked(cid))

        count = self.gridLayout.count()
        self.gridLayout.addWidget(btn, count // 2, count % 2, Qt.AlignCenter)
        self._buttons[championId] = btn

    def __onButtonClicked(self, championId):
        if self._selectedId == championId:
            self.selectChampion(None)
        else:
            self.selectChampion(championId)

    def selectChampion(self, championId):
        self._selectedId = championId
        for cid, btn in self._buttons.items():
            btn.isSelected = (cid == championId) and not btn.isGrabbed
            btn.update()
        self.championToggled.emit(championId)

    def markGrabbed(self, championId):
        """标记抢到: 该头像绿色勾, 清除其他"""
        for cid, btn in self._buttons.items():
            btn.isGrabbed = (cid == championId)
            btn.isSelected = (cid == championId)
            btn.update()
        self._selectedId = championId

    def getSelectedId(self):
        return self._selectedId

    def setStatus(self, text):
        self.statusLabel.setText(text)


class HextechWindow(OpggWindowBase):
    """海克斯/大乱斗抢英雄窗口: 贴客户端左侧长条"""

    def __init__(self, parent=None):
        super().__init__()

        self.championSelection = None
        self._lastRenderedKey = None

        self.vBoxLayout = QVBoxLayout(self)
        self.selectInterface = HextechSelectInterface()

        self.__initWindow()
        self.__initLayout()

        signalBus.hextechGrabbed.connect(self.__onGrabbed)
        signalBus.hextechSessionUpdated.connect(self.__onSessionUpdated)
        self.selectInterface.championToggled.connect(self.__onChampionToggled)

    def __initWindow(self):
        self.setFixedWidth(168)
        self.setMinimumHeight(400)
        self.setMaximumHeight(1200)
        self.setWindowIcon(QIcon("app/resource/images/hextech.svg"))
        self.setWindowTitle(self.tr("抢英雄"))
        self.setCustomBackgroundColor("#f3f3f3", "#202020")

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        if isDarkTheme():
            painter.setBrush(QColor(32, 32, 32))
        else:
            painter.setBrush(QColor(243, 243, 243))
        painter.drawRect(self.rect())

    def __initLayout(self):
        self.vBoxLayout.setContentsMargins(0, 36, 0, 0)
        self.vBoxLayout.addWidget(self.selectInterface)

    def setChampionSelection(self, selection):
        self.championSelection = selection

    def showEvent(self, a0: QShowEvent) -> None:
        """贴客户端左侧, 高度跟随客户端高度"""
        size = self.size()
        pos = getLolClientWindowPos()
        if not pos:
            self.__moveLeftCenter()
            return super().showEvent(a0)

        # pos 是物理像素, 需除以 dpi 转成逻辑坐标
        dpi = self.devicePixelRatioF() or 1.0
        clientLeft = int(pos.left() / dpi)
        clientTop = int(pos.top() / dpi)
        clientH = int(pos.height() / dpi)

        # 高度跟随客户端, 但限制在 min/max 范围内
        h = int(max(self.minimumHeight(), min(self.maximumHeight(), clientH)))

        # 贴左侧: 窗口右边紧贴客户端左边
        x = clientLeft - size.width()
        y = clientTop

        # 若超出屏幕左边界, 则改贴客户端右侧
        if x < 0:
            x = int(pos.right() / dpi)

        self.setGeometry(int(x), int(y), size.width(), h)
        return super().showEvent(a0)

    def __moveLeftCenter(self):
        desktop = QApplication.desktop().availableGeometry()
        self.move(0, desktop.height() // 2 - self.height() // 2)

    def closeEvent(self, e):
        e.ignore()
        self.hide()

    # ----------------------------------------------------------
    # 头像点击 -> 立即抢
    # ----------------------------------------------------------
    @asyncSlot(object)
    async def __onChampionToggled(self, championId):
        if self.championSelection is None:
            return

        if championId is None:
            self.championSelection.hextechTargetId = None
            self.championSelection.manualGrabRequested = False
            self.selectInterface.setStatus(self.tr("已取消"))
            logger.info("hextech: cancelled", TAG)
            return

        self.championSelection.hextechTargetId = championId
        self.championSelection.manualGrabRequested = True
        name = connector.manager.getChampionNameById(championId) \
            if connector.manager else str(championId)
        self.selectInterface.setStatus(self.tr("正在抢：{}").format(name))
        logger.info(f"hextech: target {championId}", TAG)

        try:
            await connector.benchSwap(championId)
            self.selectInterface.markGrabbed(championId)
            self.selectInterface.setStatus(self.tr("已换：{}").format(name))
            logger.info(f"hextech: swapped to {championId}", TAG)
        except Exception as e:
            logger.warning(f"hextech: swap {championId} failed: {e}", TAG)
            self.selectInterface.setStatus(
                self.tr("等待备选席..."))

    # ----------------------------------------------------------
    @asyncSlot(int)
    async def __onGrabbed(self, championId):
        self.selectInterface.markGrabbed(championId)
        name = await self._getChampionName(championId)
        self.selectInterface.setStatus(self.tr("已抢：{}").format(name))

    # ----------------------------------------------------------
    @asyncSlot(dict)
    async def __onSessionUpdated(self, data):
        if self.championSelection is None:
            return
        await self._renderSelectInterface(data)

    async def _renderSelectInterface(self, data):
        """渲染: 手持(顶部) + 备选席(主体, 愿望单金色高亮)"""
        bench = _getBenchChampionIds(data)
        mine = _getLocalChampionId(data)

        fp = (frozenset(bench), mine)
        if fp == self._lastRenderedKey:
            return
        self._lastRenderedKey = fp

        wishlist = cfg.get(cfg.hextechChampions) or []
        wishlistSet = set(wishlist)
        prevSelected = self.selectInterface.getSelectedId()

        self.selectInterface.clearAll()

        # 手持
        if mine:
            name, icon = await self._getChampionNameIcon(mine)
            self.selectInterface.setMine(mine, icon, name)

        # 备选席 (愿望单排前面)
        benchSorted = sorted(bench, key=lambda c: (
            0 if c in wishlistSet else 1,
            wishlist.index(c) if c in wishlistSet else 999))
        for cid in benchSorted:
            name, icon = await self._getChampionNameIcon(cid)
            isWl = cid in wishlistSet
            self.selectInterface.addBenchChampion(
                cid, icon, name,
                isWishlist=isWl,
                priority=(wishlist.index(cid) + 1) if isWl else 0,
                buffTip=self._getBuffTip(cid))

        # 恢复选中
        if prevSelected and prevSelected in self.selectInterface._buttons:
            self.selectInterface.selectChampion(prevSelected)

        # 状态
        hitWl = wishlistSet & set(bench)
        if hitWl and not self.championSelection.manualGrabRequested:
            self.selectInterface.setStatus(self.tr("愿望单命中★"))
        elif not self.championSelection.manualGrabRequested:
            self.selectInterface.setStatus(self.tr("点击备选席抢夺"))

    # ----------------------------------------------------------
    async def _getChampionNameIcon(self, championId):
        try:
            name = connector.manager.getChampionNameById(championId)
            icon = await connector.getChampionIcon(championId)
            return name, icon
        except Exception as e:
            logger.warning(f"get champion {championId} failed: {e}", TAG)
            return str(championId), ""

    async def _getChampionName(self, championId):
        try:
            return connector.manager.getChampionNameById(championId)
        except Exception:
            return str(championId)

    @staticmethod
    def _getBuffTip(championId):
        try:
            info = AramBuff.getInfoByChampionId(championId)
            if not info:
                return ""
            parts = []
            for k in ('damage_dealt', 'damage_taken', 'healing',
                      'shielding', 'ability_haste'):
                v = info.get(k)
                if v is not None and v != 0:
                    parts.append(f"{k}: {v}")
            return "\n".join(parts) if parts else ""
        except Exception:
            return ""


class HextechGrabFlyout(FlyoutViewBase):
    """抢英雄 Flyout (导航栏按钮点击时弹出)"""
    championGrabRequested = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._championButtons = []

        self.vBoxLayout = QVBoxLayout(self)
        self.titleLabel = StrongBodyLabel(self.tr("抢英雄"))
        self.hintLabel = QLabel(self.tr("点击英雄头像抢夺"))
        self.gridWidget = QWidget()
        self.gridLayout = QGridLayout(self.gridWidget)
        self.gridLayout.setSpacing(8)
        self.gridLayout.setContentsMargins(0, 0, 0, 0)
        self.gridLayout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        self.vBoxLayout.setContentsMargins(16, 16, 16, 16)
        self.vBoxLayout.setSpacing(6)
        self.vBoxLayout.addWidget(self.titleLabel)
        self.vBoxLayout.addWidget(self.hintLabel)
        self.vBoxLayout.addSpacing(4)
        self.vBoxLayout.addWidget(self.gridWidget)

    def clearChampions(self):
        for btn in self._championButtons:
            btn.cleanupToolTip()
        while self.gridLayout.count():
            item = self.gridLayout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._championButtons = []

    def addChampion(self, championId, iconPath, name, source):
        btn = RoundIconButton(iconPath, 44, 4, 2, name, championId, self)
        srcMap = {'mine': "手持", 'bench': "备选席", 'ally': "队友"}
        btn.setToolTip(f"{name} ({srcMap.get(source, source)})")
        filter = ToolTipFilter(btn, 0, ToolTipPosition.BOTTOM)
        btn.installEventFilter(filter)
        btn.setToolTipFilter(filter)
        count = self.gridLayout.count()
        self.gridLayout.addWidget(btn, count // 6, count % 6)
        self._championButtons.append(btn)

    def connectClicks(self):
        for btn in self._championButtons:
            try:
                btn.clicked.disconnect()
            except TypeError:
                pass
            btn.clicked.connect(self.__onChampionClicked)

    def __onChampionClicked(self, championId):
        self.championGrabRequested.emit(championId)
