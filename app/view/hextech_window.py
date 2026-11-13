import sys

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QIcon, QPainter, QColor
from PyQt5.QtWidgets import (QVBoxLayout, QHBoxLayout, QGridLayout, QFrame,
                             QLabel, QWidget, QScrollArea, QApplication)

from qasync import asyncSlot

from app.common.style_sheet import StyleSheet
from app.common.signals import signalBus
from app.common.logger import logger
from app.common.util import getLolClientWindowPos, isLolClientForeground
from app.common.icons import Icon
from app.common.side_dock import (QUICK_TOGGLES, dockWidth, orderToggles,
                                  computeDockGeometry, shouldShowDock)
from app.common.qfluentwidgets import (ToolTipFilter, ToolTipPosition,
                                       FlyoutViewBase, StrongBodyLabel,
                                       CaptionLabel, isDarkTheme)
from app.components.champion_icon_widget import RoundIconButton
from app.components.quick_toggle_button import QuickToggleButton
from app.lol.connector import connector
from app.lol.aram import AramBuff
from app.lol.tools import _getLocalChampionId, _getBenchChampionIds
from app.common.config import cfg
from app.view.opgg_window import OpggWindowBase

TAG = 'HextechWindow'


class HextechSelectInterface(QFrame):
    """换英雄界面: 手持 + 备选席 (可点击换). 简洁, 不显示队友."""

    championToggled = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("HextechInterface")

        self.vBoxLayout = QVBoxLayout(self)

        # 顶部: 标题 + 状态
        self.titleLabel = StrongBodyLabel(self.tr("换英雄"))
        self.statusLabel = CaptionLabel("")

        # 手持区
        self.mineLabel = CaptionLabel(self.tr("手持"))
        self.mineWidget = QWidget()
        self.mineLayout = QHBoxLayout(self.mineWidget)
        self.mineLayout.setContentsMargins(0, 0, 0, 0)
        self.mineLayout.setAlignment(Qt.AlignCenter)

        # 备选席区
        self.benchLabel = CaptionLabel(self.tr("备选席（点击换）"))
        self.gridWidget = QWidget()
        self.gridLayout = QGridLayout(self.gridWidget)

        self.scrollArea = QScrollArea()
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setFrameShape(QFrame.NoFrame)
        self.scrollArea.setWidget(self.gridWidget)

        self._buttons = {}       # championId -> RoundIconButton (备选席)
        self._mineButton = None  # 手持头像
        self._selectedId = None
        self._rendering = False  # 防止 _renderSelectInterface 重入

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
        """清空所有头像

        注意: 必须先 setParent(None) 切断 widget 与父级的关联, 再 deleteLater.
        否则在 deleteLater 的延迟期间, Qt 事件循环仍可能向这些 widget 派发
        paintEvent/enterEvent/tooltip 事件, 若此时它们引用了已清理的资源
        (如 _toolTipFilter 被置 None), 会触发原生崩溃 (segfault).
        该问题在抢英雄窗口高频刷新 (WS 每帧触发) 时尤为常见.
        """
        # 先主动隐藏所有 tooltip, 避免 deleteLater 延迟期间 tooltip 堆叠不消失
        for btn in list(self._buttons.values()):
            btn.cleanupToolTip()
            btn.setParent(None)
        if self._mineButton:
            self._mineButton.cleanupToolTip()
            self._mineButton.setParent(None)
        # 清备选席
        while self.gridLayout.count():
            item = self.gridLayout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        self._buttons = {}
        # 清手持
        while self.mineLayout.count():
            item = self.mineLayout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
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

    def restoreSelection(self, championId):
        """重绘后恢复选中态, 不发 championToggled 信号.

        用 selectChampion 恢复会触发 __onChampionToggled → 再发一次真实的
        benchSwap (日志里表现为自动抢到后紧跟一条多余的
        "hextech: target X" / "swapped to X").
        """
        self._selectedId = championId
        for cid, btn in self._buttons.items():
            btn.isSelected = (cid == championId) and not btn.isGrabbed
            btn.update()

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


class QuickToggleSection(QWidget):
    """快捷开关区: 按 side_dock.QUICK_TOGGLES 注册表生成, 与 cfg 双向绑定.

    绑定 ConfigItem.valueChanged, 因此在辅助功能页修改同一开关时这里会同步,
    不需要额外维护一份开关状态.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.vBoxLayout = QVBoxLayout(self)
        self.vBoxLayout.setContentsMargins(0, 2, 0, 2)
        self.vBoxLayout.setSpacing(2)

        self._buttons = {}   # key -> QuickToggleButton
        self._order = []     # 当前布局顺序 (key 列表)

        for toggle in QUICK_TOGGLES:
            item = getattr(cfg, toggle.key, None)
            icon = getattr(Icon, toggle.icon, None)
            if item is None or icon is None:
                logger.warning(
                    f"quick toggle skipped: {toggle.key}/{toggle.icon}", TAG)
                continue

            btn = QuickToggleButton(icon, toggle.title, toggle.tip)
            btn.setChecked(bool(cfg.get(item)))
            btn.clicked.connect(
                lambda checked, it=item: cfg.set(it, bool(checked)))
            item.valueChanged.connect(
                lambda value, b=btn: self.__syncChecked(b, value))
            self._buttons[toggle.key] = btn
            self.vBoxLayout.addWidget(btn)
            self._order.append(toggle.key)

    @staticmethod
    def __syncChecked(btn, value):
        if btn.isChecked() != bool(value):
            btn.setChecked(bool(value))

    def setCollapsed(self, collapsed):
        for btn in self._buttons.values():
            btn.setCollapsed(collapsed)

    def setPhase(self, phase):
        """当前阶段相关的开关置顶并高亮, 其余淡化."""
        ordered = orderToggles(
            [t for t in QUICK_TOGGLES if t.key in self._buttons], phase)
        newOrder = [t.key for t, _ in ordered]

        if newOrder != self._order:
            for key in self._order:
                self.vBoxLayout.removeWidget(self._buttons[key])
            for key in newOrder:
                self.vBoxLayout.addWidget(self._buttons[key])
            self._order = newOrder

        for toggle, active in ordered:
            self._buttons[toggle.key].setActive(active)


class SideDockWindow(OpggWindowBase):
    """常驻侧边栏: 客户端运行期间贴在客户端左侧.

    ┌ 折叠按钮
    ├ 快捷开关区   (任何阶段都在, 随 gameflow 阶段高亮相关项)
    └ 换英雄区     (仅大乱斗备选席模式显示, 原抢英雄界面)

    显隐/位置由 500ms 定时器跟随客户端窗口; 置顶只在创建/配置变更时设置一次,
    不再随阶段切换 (setWindowFlags 会重建原生窗口).
    """

    SYNC_INTERVAL_MS = 500

    def __init__(self, parent=None):
        super().__init__()

        self.championSelection = None
        self._lastRenderedKey = None
        self._clientPresent = False
        self._benchActive = False
        self._collapsed = bool(cfg.get(cfg.sideDockCollapsed))
        self._lastGeom = None
        self._phase = None

        self.vBoxLayout = QVBoxLayout(self)
        self.collapseButton = QuickToggleButton(
            Icon.CHEVRONLEFT, self.tr("收起"), self.tr("收起侧边栏"),
            checkable=False)
        self.toggleSection = QuickToggleSection()
        self.selectInterface = HextechSelectInterface()

        self.__initWindow()
        self.__initLayout()
        self._applyFlags(bool(cfg.get(cfg.enableHextechWindowOnTop)))
        self._applyLayoutState()

        self.syncTimer = QTimer(self)
        self.syncTimer.setInterval(self.SYNC_INTERVAL_MS)
        self.syncTimer.timeout.connect(self._syncToClient)

        self.collapseButton.clicked.connect(self._toggleCollapsed)
        signalBus.hextechGrabbed.connect(self.__onGrabbed)
        signalBus.hextechSessionUpdated.connect(self.__onSessionUpdated)
        self.selectInterface.championToggled.connect(self.__onChampionToggled)
        cfg.enableSideDock.valueChanged.connect(lambda _: self._syncToClient())
        cfg.enableHextechWindowOnTop.valueChanged.connect(
            lambda v: self._applyFlags(bool(v)))

    def __initWindow(self):
        self.setMinimumHeight(400)
        self.setMaximumHeight(1200)
        self.setWindowIcon(QIcon("app/resource/images/hextech.svg"))
        self.setWindowTitle(self.tr("Seraphine 侧边栏"))
        self.setCustomBackgroundColor("#f3f3f3", "#202020")

        # 位置由客户端决定, 不需要标题栏 (折叠态 48px 也放不下系统按钮) 与缩放
        self.titleBar.hide()
        self.setContentsMargins(0, 0, 0, 0)
        if hasattr(self, 'setResizeEnabled'):
            self.setResizeEnabled(False)

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
        self.vBoxLayout.setContentsMargins(0, 6, 0, 0)
        self.vBoxLayout.setSpacing(0)
        self.vBoxLayout.addWidget(self.collapseButton)
        self.vBoxLayout.addWidget(self.toggleSection)
        self.vBoxLayout.addWidget(self.selectInterface, 1)

    def setChampionSelection(self, selection):
        self.championSelection = selection

    # ----------------------------------------------------------
    # 窗口标志 / 显隐 / 位置
    # ----------------------------------------------------------
    def _applyFlags(self, onTop: bool):
        """一次性设置 Tool (不进任务栏) + 置顶, 并补回重建窗口后丢失的特效."""
        flags = self.windowFlags() | Qt.Tool
        if onTop:
            flags |= Qt.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowStaysOnTopHint
        if flags == self.windowFlags():
            return

        wasVisible = self.isVisible()
        self.setWindowFlags(flags)
        self.windowEffect.enableBlurBehindWindow(self.winId())
        self.windowEffect.addWindowAnimation(self.winId())
        if sys.platform == 'win32' and sys.getwindowsversion().build >= 22000:
            self.windowEffect.addShadowEffect(self.winId())
        if wasVisible:
            self.show()

    def setStaysOnTopEnabled(self, enable: bool):
        self._applyFlags(enable)

    def show(self):
        # 侧边栏自动出现/回到前台时不能抢走客户端的焦点
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setWindowState(self.windowState() & ~Qt.WindowMinimized)
        QWidget.show(self)

    def setClientPresent(self, present: bool):
        """客户端启动/退出时由主窗口调用."""
        self._clientPresent = present
        if present:
            self.syncTimer.start()
            self._syncToClient()
        else:
            self.syncTimer.stop()
            self.setBenchMode(False)
            self._hideDock()

    def shutdown(self):
        self.syncTimer.stop()
        self._clientPresent = False
        self._hideDock()

    def _hideDock(self):
        if self.isVisible():
            self.hide()
        self._lastGeom = None

    def _syncToClient(self):
        pos = getLolClientWindowPos() if self._clientPresent else None
        onTop = bool(cfg.get(cfg.enableHextechWindowOnTop))
        show = shouldShowDock(
            enabled=bool(cfg.get(cfg.enableSideDock)),
            clientPresent=self._clientPresent,
            clientRectValid=pos is not None,
            onTop=onTop,
            clientForeground=isLolClientForeground() if (pos is not None and onTop) else False,
            ownActive=QApplication.activeWindow() is not None)
        if not show:
            self._hideDock()
            return

        geom = computeDockGeometry(
            (pos.left(), pos.top(), pos.width(), pos.height()),
            self.devicePixelRatioF(), dockWidth(self._collapsed),
            self.minimumHeight(), self.maximumHeight())
        if geom != self._lastGeom:
            self.setGeometry(*geom)
            self._lastGeom = geom
        if not self.isVisible():
            self.show()

    # ----------------------------------------------------------
    # 折叠 / 阶段 / 备选席模式
    # ----------------------------------------------------------
    def _toggleCollapsed(self):
        self._setCollapsed(not self._collapsed)

    def _setCollapsed(self, collapsed: bool):
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        cfg.set(cfg.sideDockCollapsed, collapsed)
        self._applyLayoutState()
        self._syncToClient()

    def _applyLayoutState(self):
        collapsed = self._collapsed
        self.setFixedWidth(dockWidth(collapsed))
        self.collapseButton.setCollapsed(collapsed)
        self.collapseButton.setFluentIcon(
            Icon.CHEVRONRIGHT if collapsed else Icon.CHEVRONLEFT)
        self.collapseButton.setTitle(
            self.tr("展开") if collapsed else self.tr("收起"))
        self.toggleSection.setCollapsed(collapsed)
        self.selectInterface.setVisible(self._benchActive and not collapsed)
        self.update()

    def setPhase(self, phase):
        """主窗口 gameflow 阶段变化时调用: 高亮相关开关; 离开选人则收起换英雄区."""
        self._phase = phase
        self.toggleSection.setPhase(phase)
        if phase != 'ChampSelect':
            self.setBenchMode(False)

    def setBenchMode(self, active: bool, expand: bool = False):
        """大乱斗备选席模式开关. expand=True 且当前折叠时自动展开 (autoShowHextechWindow)."""
        changed = active != self._benchActive
        self._benchActive = active
        if not active:
            self._lastRenderedKey = None
            if changed:
                self.selectInterface.clearAll()
                self.selectInterface.setStatus("")
        if active and expand and self._collapsed:
            self._setCollapsed(False)
        else:
            self._applyLayoutState()

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
            if not await connector.benchSwap(championId):
                # 被队友抢先/暂不在备选席: 保留目标, 由 autoBenchGrab 轮询等待释放
                self.selectInterface.setStatus(self.tr("等待备选席..."))
                logger.info(f"hextech: swap {championId} rejected, waiting", TAG)
                return
            # 手动选择代表用户最终意图: 置幂等标志压制本局后续愿望单自动抢,
            # 否则下一帧 autoBenchGrab 会用愿望单英雄换掉刚手动抢到的英雄
            self.championSelection.isHextechGrabbed = True
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
        # 应用在选人途中才启动时没有经过 __onChampionSelectBegin, 从这里补激活;
        # 离开选人后迟到的事件不应重新激活
        if not self._benchActive and self._phase in (None, 'ChampSelect'):
            self.setBenchMode(True)
        if not self._benchActive:
            return
        await self._renderSelectInterface(data)

    async def _renderSelectInterface(self, data):
        """渲染: 手持(顶部) + 备选席(主体, 愿望单金色高亮)

        防竞态: async 方法在 await 网络期间, 可能被新的 session 信号重入,
        或窗口被关闭导致 widget 失效. 通过 _rendering 标志防止重入,
        并在每次 await 后检查窗口是否仍然可见 (isVisible).
        """
        if self.selectInterface._rendering:
            return
        self.selectInterface._rendering = True
        try:
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
                if not self._benchActive:
                    # await 期间选人已结束, 不要把已清空的区域重新填上
                    self._lastRenderedKey = None
                    return
                self.selectInterface.setMine(mine, icon, name)

            # 备选席 (愿望单排前面)
            benchSorted = sorted(bench, key=lambda c: (
                0 if c in wishlistSet else 1,
                wishlist.index(c) if c in wishlistSet else 999))
            for cid in benchSorted:
                name, icon = await self._getChampionNameIcon(cid)
                if not self._benchActive:
                    # await 期间选人已结束, 不要把已清空的区域重新填上
                    self._lastRenderedKey = None
                    return
                isWl = cid in wishlistSet
                self.selectInterface.addBenchChampion(
                    cid, icon, name,
                    isWishlist=isWl,
                    priority=(wishlist.index(cid) + 1) if isWl else 0,
                    buffTip=self._getBuffTip(cid))

            # 恢复选中
            if prevSelected and prevSelected in self.selectInterface._buttons:
                self.selectInterface.restoreSelection(prevSelected)

            # 状态
            hitWl = wishlistSet & set(bench)
            if hitWl and not self.championSelection.manualGrabRequested:
                self.selectInterface.setStatus(self.tr("愿望单命中★"))
            elif not self.championSelection.manualGrabRequested:
                self.selectInterface.setStatus(self.tr("点击备选席抢夺"))
        finally:
            self.selectInterface._rendering = False

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
        except (AttributeError, KeyError, ValueError):
            return str(championId)

    @staticmethod
    def _getBuffTip(championId):
        try:
            info = AramBuff.getInfoByChampionId(championId)
            if not info:
                return ""
            # AramBuff 数据来自 jddld.com, key 为拼音缩写
            buffItems = [
                ('zcsh', '造成伤害', '%', 100),
                ('sdsh', '受到伤害', '%', 100),
                ('zlxl', '治疗增益', '%', 100),
                ('hdxn', '护盾增益', '%', 100),
                ('jnjs', '技能急速', '', 0),
                ('renxing', '韧性', '', 0),
            ]
            parts = []
            for key, label, suffix, default in buffItems:
                v = info.get(key)
                if v is not None and str(v) != str(default) and v != '':
                    parts.append(f"{label}: {v}{suffix}")
            desc = info.get('description', '')
            if desc:
                parts.append(desc.replace('(', '（').replace(')', '）'))
            return "\n".join(parts) if parts else ""
        except (AttributeError, KeyError, TypeError):
            return ""


class HextechGrabFlyout(FlyoutViewBase):
    """换英雄 Flyout (导航栏按钮点击时弹出)"""
    championGrabRequested = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._championButtons = []

        self.vBoxLayout = QVBoxLayout(self)
        self.titleLabel = StrongBodyLabel(self.tr("换英雄"))
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


# 兼容旧名
HextechWindow = SideDockWindow
