import os
import sys
import traceback
import time
import copy
import win32api
from pathlib import Path

import pyperclip

import asyncio
import aiohttp
from aiohttp.client_exceptions import ClientConnectorError
from qasync import asyncClose, asyncSlot
from PyQt5.QtCore import Qt, pyqtSignal, QSize, QEvent, QTimer
from PyQt5.QtGui import QIcon, QImage, QColor
from PyQt5.QtWidgets import QApplication, QSystemTrayIcon

from app.common.qfluentwidgets import (NavigationItemPosition, InfoBar, InfoBarPosition, Action,
                                       FluentWindow, SplashScreen, MessageBox, SmoothScrollArea,
                                       ToolTipFilter, FluentIcon, ToolTipPosition, Flyout, FlyoutAnimationType)

from app.view.start_interface import StartInterface
from app.view.setting_interface import SettingInterface
from app.view.career_interface import CareerInterface
from app.view.search_interface import SearchInterface
from app.view.game_info_interface import GameInfoInterface
from app.view.auxiliary_interface import AuxiliaryInterface
from app.view.opgg_window import OpggWindow
from app.view.hextech_window import HextechWindow, HextechGrabFlyout
from app.common.util import (github, getLolClientPid, getTasklistPath,
                             getLolClientPidSlowly, getLoLPathByRegistry)
from app.components.avatar_widget import NavigationAvatarWidget
from app.components.temp_system_tray_menu import TmpSystemTrayMenu
from app.common.icons import Icon
from app.common.config import cfg, VERSION, BETA
from app.common.logger import logger
from app.common.signals import signalBus
from app.components.message_box import (UpdateMessageBox, NoticeMessageBox,
                                        WaitingForLolMessageBox, ExceptionMessageBox,
                                        ChangeDpiMessageBox)
from app.lol.exceptions import (SummonerGamesNotFound, RetryMaximumAttempts,
                                SummonerNotFound, SummonerNotInGame, SummonerRankInfoNotFound)
from app.lol.listener import (LolProcessExistenceListener, StoppableThread)
from app.lol.connector import connector
from app.lol.tools import (parseAllyGameInfo, parseGameInfoByGameflowSession,
                           getAllyOrderByGameRole, getTeamColor, autoBan, autoPick,
                           autoComplete, autoSwap, autoTrade, ChampionSelection,
                           SERVERS_NAME, SERVERS_SUBSET, showOpggBuild, autoShow,
                           autoSetSummonerSpell, autoBenchGrab)
from app.lol.aram import AramBuff
from app.lol.champions import ChampionAlias
from app.lol.opgg import opgg
from app.lol.static_data import static_data
from app.lol.live_client import liveClient
from app.lol.tools_pure import pickHonorTarget  # noqa: F401  # 保留供测试/外部调用

import threading

TAG = "MainWindow"


class MainWindow(FluentWindow):
    mainWindowHide = pyqtSignal(bool)
    showUpdateMessageBox = pyqtSignal(dict)
    showNoticeMessageBox = pyqtSignal(str)
    checkUpdateFailed = pyqtSignal()
    fetchNoticeFailed = pyqtSignal()

    def __init__(self):
        super().__init__()

        logger.critical(f"Seraphine started, version: {BETA or VERSION}", TAG)

        self.windowSize = cfg.get(cfg.windowSize)

        self.__initConfig()
        self.__initWindow()
        self.__initSystemTray()

        # create sub interface
        self.startInterface = StartInterface(self)
        self.careerInterface = CareerInterface(self)
        self.searchInterface = SearchInterface(self)
        self.gameInfoInterface = GameInfoInterface(self)
        self.auxiliaryFuncInterface = AuxiliaryInterface(self)
        self.settingInterface = SettingInterface(self)

        logger.critical("Seraphine interfaces initialized", TAG)

        # create listener
        self.isClientProcessRunning = False
        self.processListener = LolProcessExistenceListener(self)
        self.checkUpdateThread = StoppableThread(
            target=self.checkUpdate, parent=self)
        self.checkNoticeThread = StoppableThread(
            target=lambda: self.checkNotice(False), parent=self)

        logger.critical("Seraphine listerners started", TAG)

        self.currentSummoner = cfg.get(cfg.lastSummoner) or None

        self.isGaming = False
        self.isTrayExit = False
        self.tasklistEnabled = True
        self.championSelection = ChampionSelection()
        self._autoStartTask = None

        # 海克斯辅助: 游戏内 3 秒轮询 Live Client API 采集已选强化
        self.hextechAssistTimer = QTimer(self)
        self.hextechAssistTimer.setInterval(3000)
        self.hextechAssistTimer.timeout.connect(
            lambda: asyncio.ensure_future(self.__onHextechAssistTick()))

        self.lastTipsTime = time.time()
        self.lastTipsType = None

        self.__initInterface()
        self.__initNavigation()
        self.__initListener()

        # Hextech 抢人窗口必须在 __conncetSignalToSlot 之前创建 (接线引用 self.hextechWindow)
        self.hextechWindow = HextechWindow()
        self.hextechWindow.setChampionSelection(self.championSelection)

        self.__conncetSignalToSlot()
        self.__autoStartLolClient()

        self.splashScreen.finish()

        self.opggWindow = OpggWindow()

        logger.critical("Seraphine initialized", TAG)

        QTimer.singleShot(0, lambda: asyncio.ensure_future(self.__initOfflineServices()))

        self.__silentStart()

    async def __initOfflineServices(self):
        try:
            await static_data.ensure_loaded()
        except (OSError, RuntimeError) as e:
            logger.warning(f"static_data load failed: {e}", TAG)
        try:
            await opgg.start()
            # 切换到 tier 界面后再初始化, 否则当前界面仍是 homeInterface,
            # __updateInterface 会因早期返回而不拉取数据 (导致必须连接客户端才能加载)
            self.opggWindow.setHomeInterfaceEnabled(False)
            await self.opggWindow.initWindow()
        except Exception as e:
            logger.warning(f"Failed to pre-start OPGG: {e}", TAG)
        if self.currentSummoner:
            await self.__updateAvatarIconName()
            # 用 lastSummoner 加载生涯页面 (客户端未连接时显示缓存的召唤师信息,
            # 战绩/段位数据因 LCU 不可用而为空, parseSummonerData 已有容错)
            try:
                self.careerInterface.setLoginSummonerPuuid(
                    self.currentSummoner.get('puuid'))
                # 同步设置 loading 状态以立即 UI 反馈
                self.careerInterface.setLoadingPageEnabled(True)
                await self.careerInterface.updateInterface(
                    summoner=self.currentSummoner)
                # 客户端未连接时停留在生涯页面, 而不是启动页
                self.checkAndSwitchTo(self.careerInterface)
            except Exception as e:
                logger.warning(f"Failed to load career with lastSummoner: {e}", TAG)

    def __initConfig(self):
        folder = cfg.get(cfg.lolFolder)

        isEmptyList = folder == []
        isEmptyStr = folder == str(Path("").absolute()).replace(
            "\\", "/") or folder == ""

        if isEmptyList or isEmptyStr:
            path = getLoLPathByRegistry()

            if not path:
                return

            cfg.set(cfg.lolFolder, [path])
            return

        if type(folder) is str:
            cfg.set(cfg.lolFolder, [folder])

    def __initInterface(self):
        self.__lockInterface()

        self.startInterface.setObjectName("startInterface")
        self.careerInterface.setObjectName("careerInterface")
        self.searchInterface.setObjectName("searchInterface")
        self.gameInfoInterface.setObjectName("gameInfoInterface")
        self.auxiliaryFuncInterface.setObjectName("auxiliaryFuncInterface")
        self.settingInterface.setObjectName("settingInterface")

    def __initNavigation(self):
        pos = NavigationItemPosition.SCROLL

        self.navigationInterface.addSeparator(NavigationItemPosition.TOP)

        self.addSubInterface(
            self.startInterface, Icon.HOME, self.tr("Start"), pos)
        self.addSubInterface(
            self.careerInterface, Icon.PERSON, self.tr("Career"), pos)
        self.addSubInterface(
            self.searchInterface, Icon.SEARCH, self.tr("Search 👀"), pos)
        self.addSubInterface(
            self.gameInfoInterface, Icon.GAME, self.tr("Game Information"), pos)
        self.addSubInterface(
            self.auxiliaryFuncInterface, Icon.WRENCH,
            self.tr("Auxiliary Functions"), pos)

        pos = NavigationItemPosition.BOTTOM

        self.navigationInterface.addItem(
            routeKey='HextechGrab',
            icon=QIcon("app/resource/images/hextech.svg"),
            text=self.tr("抢英雄"),
            onClick=self.showHextechWindow,
            selectable=False,
            position=pos,
            tooltip=self.tr("海克斯/大乱斗抢英雄")
        )

        self.navigationInterface.addItem(
            routeKey='Opgg',
            icon=QIcon("app/resource/images/opgg.svg"),
            text="OP.GG",
            onClick=self.showOpggWindow,
            selectable=False,
            position=pos,
            tooltip="OP.GG"
        )

        self.navigationInterface.addItem(
            routeKey='Fix',
            icon=Icon.ARROWCIRCLE,
            text=self.tr("Back to Lobby"),
            onClick=self.__onFixLCUButtonClicked,
            selectable=False,
            position=pos,
            tooltip=self.tr("Back to Lobby"),
        )

        self.navigationInterface.addItem(
            routeKey='Notice',
            icon=Icon.ALERT,
            text=self.tr("Notice"),
            onClick=lambda: threading.Thread(
                target=lambda: self.checkNotice(True)).start(),
            selectable=False,
            position=pos,
            tooltip=self.tr("Notice"),
        )

        self.navigationInterface.insertSeparator(
            3, NavigationItemPosition.BOTTOM)

        self.avatarWidget = NavigationAvatarWidget(
            avatar="app/resource/images/game.png", name=self.tr("Start LOL"))
        self.navigationInterface.addWidget(
            routeKey="avatar",
            widget=self.avatarWidget,
            onClick=self.__onAvatarWidgetClicked,
            position=pos,
        )

        self.addSubInterface(
            self.settingInterface, FluentIcon.SETTING,
            self.tr("Settings"), pos,
        )

        # set the maximum width
        self.navigationInterface.setExpandWidth(250)
        self.navigationInterface.setMinimumExpandWidth(1321)

    def __conncetSignalToSlot(self):
        # From listener:
        signalBus.tasklistNotFound.connect(self.__showWaitingMessageBox)
        signalBus.lolClientStarted.connect(self.__onLolClientStarted)
        signalBus.lolClientEnded.connect(self.__onLolClientEnded)
        signalBus.lolClientChanged.connect(self.__onLolClientChanged)
        signalBus.terminateListeners.connect(self.__terminateListeners)

        # From connector
        signalBus.currentSummonerProfileChanged.connect(
            self.__onCurrentSummonerProfileChanged)
        signalBus.gameStatusChanged.connect(
            self.__onGameStatusChanged)
        signalBus.champSelectChanged.connect(
            self.__onChampSelectChanged)
        signalBus.lcuApiExceptionRaised.connect(
            self.__onShowLcuConnectError)
        signalBus.lcuNotConnected.connect(self.__onLcuNotConnected)
        signalBus.getCmdlineError.connect(
            self.__showNeedAdminMessageBox)

        # From career_interface
        signalBus.careerGameBarClicked.connect(self.__onCareerGameClicked)

        # From search_interface and gameinfo_interface
        signalBus.toSearchInterface.connect(self.__switchToSearchInterface)
        signalBus.toCareerInterface.connect(self.__switchToCareerInterface)

        # From setting_interface
        self.settingInterface.careerGamesCount.pushButton.clicked.connect(
            self.__refreshCareerInterface)
        self.settingInterface.micaCard.checkedChanged.connect(
            self.__cascadeSetMicaEffect)

        # From main_window
        self.showUpdateMessageBox.connect(self.__onShowUpdateMessageBox)
        self.showNoticeMessageBox.connect(self.__onShowNoticeMessageBox)
        self.checkUpdateFailed.connect(self.__onCheckUpdateFailed)
        self.fetchNoticeFailed.connect(self.__onFetchNoticeFailed)
        self.stackedWidget.currentChanged.connect(
            self.__onCurrentStackedChanged)
        self.mainWindowHide.connect(self.__onWindowHide)

        # Hextech/ARAM 抢人窗口 (hextechGrabbed 信号由 HextechWindow 自行 connect, 避免跨类 name mangling)

    def __initWindow(self):
        self.setMinimumSize(1134, 826)
        self.setWindowIcon(QIcon("app/resource/images/logo.png"))
        self.setWindowTitle("Seraphine")

        self.titleBar.titleLabel.setStyleSheet(
            "QLabel {font: 13px 'Segoe UI', 'Microsoft YaHei';}")
        self.titleBar.hBoxLayout.insertSpacing(0, 10)

        self.setMicaEffectEnabled(cfg.get(cfg.micaEnabled))

        self.splashScreen = SplashScreen(self.windowIcon(), self)
        self.splashScreen.setIconSize(QSize(106, 106))
        self.splashScreen.raise_()

        desktop = QApplication.desktop().availableGeometry()
        w, h = desktop.width(), desktop.height()
        self.move(w // 2 - self.width() // 2, h // 2 - self.height() // 2)

        self.show()

        QApplication.processEvents()

        self.oldHook = sys.excepthook
        sys.excepthook = self.exceptHook

    @asyncSlot(str, BaseException)
    async def __onShowLcuConnectError(self, api, obj):
        # 同类错误限制弹出频率(1.5秒每次)
        if time.time() - self.lastTipsTime < 1.5 and self.lastTipsType is type(obj):
            return
        else:
            self.lastTipsTime = time.time()
            self.lastTipsType = type(obj)

        if type(obj) in [SummonerGamesNotFound, SummonerRankInfoNotFound]:
            msg = self.tr(
                "The server returned abnormal content, which may be under maintenance.")
        elif type(obj) is RetryMaximumAttempts:
            msg = self.tr("Exceeded maximum retry attempts.")
        elif type(obj) in [SummonerNotFound, SummonerNotInGame]:
            return
        else:
            msg = repr(obj)

        InfoBar.error(
            self.tr("LCU request error"),
            self.tr("Connect API") + f" {api}: {msg}",
            duration=5000,
            orient=Qt.Vertical,
            parent=self,
            position=InfoBarPosition.BOTTOM_RIGHT
        )

    def __onLcuNotConnected(self):
        # LCU 未就绪仍有请求发送时, 由 @retry 统一拦截 ReferenceError 后发射此信号
        # 复用 lastTipsTime/lastTipsType 限频, 避免短时间内大量请求刷屏
        if time.time() - self.lastTipsTime < 1.5 and self.lastTipsType is ReferenceError:
            return
        self.lastTipsTime = time.time()
        self.lastTipsType = ReferenceError

        InfoBar.warning(
            self.tr("Client not connected"),
            self.tr("League of Legends client is not running. "
                    "Please start the client first."),
            orient=Qt.Vertical,
            duration=4000,
            position=InfoBarPosition.BOTTOM_RIGHT,
            parent=self
        )

    def __onWindowHide(self, hide):
        """

        @param hide: True -> 隐藏, False -> 显示
        @return:
        """
        if hide:
            self.hide()
        else:
            self.showNormal()
            self.activateWindow()

    def checkUpdate(self):
        if not cfg.get(cfg.enableCheckUpdate):
            return

        try:
            releasesInfo = github.checkUpdate()
        except Exception:
            self.checkUpdateFailed.emit()
            return

        if releasesInfo:
            self.showUpdateMessageBox.emit(releasesInfo)

    def checkNotice(self, triggerByUser):
        try:
            noticeInfo = github.getNotice()
            sha = noticeInfo['sha']
            content = noticeInfo['content']
        except Exception:
            self.fetchNoticeFailed.emit()
            return

        # 如果是开启软件时，并且该公告曾经已经展示过，就直接 return 了
        if not triggerByUser and sha == cfg.get(cfg.lastNoticeSha):
            return

        cfg.set(cfg.lastNoticeSha, sha)
        self.showNoticeMessageBox.emit(content)

    def __onCheckUpdateFailed(self):
        InfoBar.warning(
            self.tr("Check Update Failed"),
            self.tr(
                "Failed to check for updates, possibly unable to connect to Github."),
            duration=5000,
            orient=Qt.Vertical,
            parent=self,
            position=InfoBarPosition.BOTTOM_RIGHT
        )

    def __onFetchNoticeFailed(self):
        InfoBar.warning(
            self.tr("Fetch notice Failed"),
            self.tr(
                "Failed to fetch notice, possibly unable to connect to Github."),
            duration=5000,
            orient=Qt.Vertical,
            parent=self,
            position=InfoBarPosition.BOTTOM_RIGHT
        )

    def __onShowUpdateMessageBox(self, info):
        msgBox = UpdateMessageBox(info, self.window())
        msgBox.exec()

    def __onShowNoticeMessageBox(self, msg):
        msgBox = NoticeMessageBox(msg, self.window())
        msgBox.exec()

    def __showWaitingMessageBox(self):
        self.tasklistEnabled = False

        msgBox = WaitingForLolMessageBox(self.window())

        if not msgBox.exec():
            signalBus.terminateListeners.emit()
            sys.exit()

    def __showNeedAdminMessageBox(self):
        msgBox = MessageBox(self.tr("Get cmdline error"), self.tr(
            "Try running Seraphine as an administrator"), self.window())
        msgBox.cancelButton.setVisible(False)
        msgBox.exec()

        signalBus.terminateListeners.emit()
        sys.exit()

    def __initSystemTray(self):
        self.trayIcon = QSystemTrayIcon(self)
        self.trayIcon.setToolTip("Seraphine")
        self.trayIcon.installEventFilter(ToolTipFilter(self.trayIcon))

        self.trayIcon.setIcon(QIcon("app/resource/images/logo.png"))

        careerAction = Action(Icon.PERSON, self.tr("Career"), self)
        searchAction = Action(Icon.SEARCH, self.tr("Search 👀"), self)
        gameInfoAction = Action(Icon.GAME, self.tr("Game Information"), self)
        settingsAction = Action(Icon.SETTING, self.tr("Settings"), self)
        quitAction = Action(Icon.EXIT, self.tr('Quit'), self)

        def showAndSwitch(interface):
            self.show()
            self.checkAndSwitchTo(interface)

        def quit():
            self.isTrayExit = True
            self.close()

        careerAction.triggered.connect(
            lambda: showAndSwitch(self.careerInterface))
        searchAction.triggered.connect(
            lambda: showAndSwitch(self.searchInterface))
        gameInfoAction.triggered.connect(
            lambda: showAndSwitch(self.gameInfoInterface))
        settingsAction.triggered.connect(
            lambda: showAndSwitch(self.settingInterface))
        quitAction.triggered.connect(quit)

        self.trayMenu = TmpSystemTrayMenu(self)

        self.trayMenu.addAction(careerAction)
        self.trayMenu.addAction(searchAction)
        self.trayMenu.addAction(gameInfoAction)
        self.trayMenu.addSeparator()
        self.trayMenu.addAction(settingsAction)
        self.trayMenu.addAction(quitAction)

        self.trayIcon.setContextMenu(self.trayMenu)
        # 双击事件
        self.trayIcon.activated.connect(lambda reason: self.show(
        ) if reason == QSystemTrayIcon.DoubleClick else None)
        self.trayIcon.show()

    def show(self):
        self.activateWindow()
        self.setWindowState(self.windowState() & ~
                            Qt.WindowMinimized | Qt.WindowActive)
        self.showNormal()

    def __initListener(self):
        self.processListener.start()
        self.checkUpdateThread.start()
        self.checkNoticeThread.start()
        # self.minimizeThread.start()  # 该功能不再支持 -- By Hpero4

    async def __changeCareerToCurrentSummoner(self):
        summoner = await connector.getCurrentSummoner()
        # LCU 未就绪时 @retry 拦截 ReferenceError 返回 None
        # (已通过 signalBus.lcuNotConnected 发射统一提示)
        if summoner is None:
            self.careerInterface.setLoadingPageEnabled(False)
            return
        self.currentSummoner = summoner
        name = summoner.get("gameName") or summoner['displayName']
        self.careerInterface.setLoginSummonerPuuid(summoner['puuid'])

        # 同步设置 loading 状态以立即 UI 反馈
        self.careerInterface.setLoadingPageEnabled(True)
        asyncio.create_task(self.careerInterface.updateInterface(
            summoner=summoner))

    @asyncSlot(int)
    async def __onLolClientStarted(self, pid):
        logger.error(f"LoL client started: {pid}, refresh career", TAG)
        res = await self.__startConnector(pid)
        if not res:
            return

        await opgg.start()
        self.checkAndSwitchTo(self.careerInterface)
        self.isClientProcessRunning = True

        await self.__changeCareerToCurrentSummoner()
        await self.__updateAvatarIconName()

        self.startInterface.hideLoadingPage()

        folder, status = await asyncio.gather(connector.getInstallFolder(),
                                              connector.getGameStatus())

        self.__setLolInstallFolder(folder)

        asyncio.create_task(self.auxiliaryFuncInterface.initChampionList())

        self.auxiliaryFuncInterface.lockConfigCard.loadNowMode()

        # 加载大乱斗buff -- By Hpero4
        aramInitT = asyncio.create_task(AramBuff.checkAndUpdate())
        championsInit = asyncio.create_task(ChampionAlias.checkAndUpdate())

        asyncio.create_task(self.opggWindow.initWindow())
        self.opggWindow.setHomeInterfaceEnabled(False)

        # ---- 240413 ---- By Hpero4
        # 如果你希望 self.__onGameStatusChanged(status) 和 self.__unlockInterface() 并行执行, 可以这样使用:
        #     t = self.__onGameStatusChanged(status)
        #     self.__unlockInterface()
        #     await t
        #
        # 如果你希望等待 self.__onGameStatusChanged(status) 返回之后再执行 self.__unlockInterface() 可以这样使用:
        #     await self.__onGameStatusChanged(status)
        #     self.__unlockInterface()
        #
        # 而不是直接调用:
        #     self.__onGameStatusChanged(status)
        #     self.__unlockInterface()
        #
        # 此外 self.__onGameStatusChanged(status) 本身不是一个常规的异步函数, 它是使用 asyncSlot 装饰的槽函数,
        #   内部封装了task的新建过程, 并且会被立即加入到 QEventLoop 等待执行, 并返回一个Task实例;
        #
        # 如果 func a 是一个常规异步函数, func b 是一个常规的同步函数, 你应该这样使用它:
        #     t = asyncio.create_task(a())
        #     b()
        #     await t
        #
        # 项目中还有其他异步函数使用了await进行了额外的等待, 亦或是直接调用异步函数而没有使用await保证竞态的情况,
        # 这可能导致性能或是其他不可预期的问题, 这是只是一个例子;
        # ---- 240413 ---- By Hpero4

        self.__unlockInterface()
        await asyncio.gather(championsInit, aramInitT)
        await self.__onGameStatusChanged(status)

        # Note 如果你希望测试大乱斗的数据弹框, 参考这个 -- By Hpero4
        # self.careerInterface.icon.aramInfo = AramBuff.getInfoByChampionId(75)

    async def __startConnector(self, pid):
        try:
            await connector.start(pid)
            return True
        except RetryMaximumAttempts:
            # 若超出最大尝试次数, 则认为 lcu 未就绪 (如大区排队中),
            # 捕获到该异常时不抛出, 等待下一个 emit
            await connector.close()

            if self.processListener.isRunning():
                self.processListener.runningPid = 0
            else:
                signalBus.tasklistNotFound.emit()

            return False

    @asyncSlot(int)
    async def __onLolClientChanged(self, pid):
        logger.critical(f"League of Legends client changed: {pid}", TAG)
        self.currentSummoner = None
        self.careerInterface.setLoginSummonerPuuid(None)
        await self.__onLolClientEnded()
        self.processListener.runningPid = pid
        await self.__onLolClientStarted(pid)

    @asyncSlot()
    async def __onLolClientEnded(self):
        logger.critical("League of Legends client ended", TAG)

        if self.searchInterface.gameLoadingTask:
            self.searchInterface.gameLoadingTask.cancel()
            self.searchInterface.gameLoadingTask = None

        if self.careerInterface.loadGamesTask and not self.careerInterface.loadGamesTask.done():
            self.careerInterface.loadGamesTask.cancel()
            self.careerInterface.loadGamesTask = None

        # 停止海克斯辅助轮询
        self.hextechAssistTimer.stop()
        self.opggWindow.hextechAssistInterface.clearState()

        await connector.close()

        self.isClientProcessRunning = False

        await self.__updateAvatarIconName()

        # OPGG 数据不依赖 LCU (走 lol-api-champion.op.gg),
        # 客户端断开后保持 tierInterface 可用, 不切回 homeInterface,
        # 避免触发 setComboBoxesEnabled(False) 把所有过滤控件锁死.
        # 与 __initOfflineServices 启动路径保持一致.

        self.setWindowTitle("Seraphine")

        # 有 lastSummoner 时保留在生涯页面 (显示上次召唤师信息), 不切到启动页
        if self.currentSummoner and self.careerInterface.puuid:
            self.checkAndSwitchTo(self.careerInterface)
        else:
            self.startInterface.showLoadingPage()
            self.checkAndSwitchTo(self.startInterface)
            self.__lockInterface()

    async def __updateAvatarIconName(self):
        if self.currentSummoner:
            try:
                iconId = self.currentSummoner['profileIconId']
                try:
                    icon = await connector.getProfileIcon(iconId)
                except Exception:
                    cached_icon = f"app/resource/game/profile icons/{iconId}.jpg"
                    icon = cached_icon if os.path.exists(cached_icon) else "app/resource/images/game.png"
                name = (self.currentSummoner.get("gameName")
                        or self.currentSummoner['displayName'])

                server = (self.currentSummoner.get('server')
                          or (SERVERS_NAME.get(connector.server) or connector.server if getattr(connector, 'server', None) else ''))
                suffix = self.tr(" (") + server + self.tr(")") if server else ""
                if getattr(connector, 'lcuSess', None) is None:
                    suffix = suffix + self.tr(" (offline)") if suffix else self.tr(" (offline)")
                name += suffix

                subset = SERVERS_SUBSET.get(connector.server) if getattr(connector, 'server', None) else None

                if subset and not self.avatarWidget.toolTip():
                    tooltip = self.tr(", ").join(subset)
                    self.avatarWidget.setToolTip(tooltip)
                    self.avatarWidget.installEventFilter(
                        ToolTipFilter(self.avatarWidget, 0,
                                      ToolTipPosition.TOP)
                    )

            except Exception:
                icon = "app/resource/images/game.png"
                name = self.tr("Start LOL")
                self.avatarWidget.setToolTip("")
        else:
            icon = "app/resource/images/game.png"
            name = self.tr("Start LOL")
            self.avatarWidget.setToolTip("")

        img = QImage(icon)
        if img.isNull():
            img = QImage(24, 24, QImage.Format_ARGB32)
            img.fill(QColor(0, 0, 0, 0))
        self.avatarWidget.avatar = img.scaled(
            24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.avatarWidget.name = name

        self.avatarWidget.repaint()

    def __setLolInstallFolder(self, folder: str):
        folder = folder.replace("\\", "/")
        folder = folder.replace("LeagueClient", "TCLS")
        folder = f"{folder[:1].upper()}{folder[1:]}"

        current: list = cfg.get(cfg.lolFolder)

        if folder.lower() not in [item.lower() for item in current]:
            new = copy.deepcopy(current)
            new.append(folder)
            cfg.set(cfg.lolFolder, new)

    @asyncSlot(dict)
    async def __onCurrentSummonerProfileChanged(self, data: dict):
        self.currentSummoner = data
        self.__cacheCurrentSummoner(data)

        await asyncio.gather(self.__updateAvatarIconName(),
                             self.careerInterface.updateNameIconExp(data))

        logger.debug(f"Update Summoner Info : {data}", TAG)

    def __cacheCurrentSummoner(self, data: dict):
        if not data or not data.get('summonerId'):
            return
        try:
            cached = {
                'summonerId': data.get('summonerId'),
                'puuid': data.get('puuid'),
                'displayName': data.get('displayName'),
                'gameName': data.get('gameName'),
                'tagLine': data.get('tagLine'),
                'profileIconId': data.get('profileIconId'),
                'summonerLevel': data.get('summonerLevel'),
                'xpSinceLastLevel': data.get('xpSinceLastLevel'),
                'xpUntilNextLevel': data.get('xpUntilNextLevel'),
                'privacy': data.get('privacy'),
                'server': getattr(connector, 'server', None),
            }
            cfg.set(cfg.lastSummoner, cached)
        except Exception as e:
            logger.warning(f"Failed to cache current summoner: {e}", TAG)

    def __autoStartLolClient(self):
        if self.isClientProcessRunning:
            return

        if not cfg.get(cfg.enableStartLolWithApp):
            return

        if self.tasklistEnabled:
            path = getTasklistPath()
            pid = getLolClientPid(path)
        else:
            pid = getLolClientPidSlowly()

        if pid == 0:
            self.__startLolClient()

    def __startLolClient(self):
        for clientName in ("client.exe", "LeagueClient.exe"):
            path = f'{cfg.get(cfg.lolFolder)[0]}/{clientName}'
            if os.path.exists(path):
                os.popen(f'"{path}"')
                self.__showStartLolSuccessInfo()
                break
        else:
            self.__showLolClientPathErrorInfo()

    def __onAvatarWidgetClicked(self):
        if not self.isClientProcessRunning:
            self.__startLolClient()
        else:
            self.careerInterface.backToMeButton.clicked.emit()
            self.checkAndSwitchTo(self.careerInterface)

    def __showStartLolSuccessInfo(self):
        InfoBar.success(
            title=self.tr("Start LOL successfully"),
            orient=Qt.Vertical,
            content="",
            isClosable=True,
            position=InfoBarPosition.BOTTOM_RIGHT,
            duration=5000,
            parent=self,
        )

    def __showLolClientPathErrorInfo(self):
        InfoBar.error(
            title=self.tr("Invalid path"),
            content=self.tr(
                "Please set the correct directory of the LOL client in the setting page"),
            orient=Qt.Vertical,
            isClosable=True,
            position=InfoBarPosition.BOTTOM_RIGHT,
            duration=5000,
            parent=self,
        )

    def checkAndSwitchTo(self, interface):
        index = self.stackedWidget.indexOf(interface)

        if not self.stackedWidget.currentIndex() == index:
            self.navigationInterface.widget(interface.objectName()).click()

    def __unlockInterface(self):
        self.searchInterface.setEnabled(True)
        self.auxiliaryFuncInterface.setEnabled(True)
        # pass

    def __lockInterface(self):
        self.searchInterface.setEnabled(False)
        self.auxiliaryFuncInterface.setEnabled(False)

    def __terminateListeners(self):
        self.processListener.terminate()
        self.checkUpdateThread.terminate()
        self.checkNoticeThread.terminate()

    @asyncClose
    async def closeEvent(self, a0) -> None:
        # 首次点击 关闭 按钮
        if cfg.get(cfg.enableCloseToTray) is None:
            msgBox = MessageBox(
                self.tr("Do you wish to exit?"),
                self.tr(
                    "Choose action for close button (you can modify it at any time in the settings page)"),
                self
            )

            msgBox.yesButton.setText(self.tr('Minimize'))
            msgBox.cancelButton.setText(self.tr('Exit'))
            self.update()

            cfg.set(cfg.enableCloseToTray, msgBox.exec())

        if not cfg.get(cfg.enableCloseToTray) or self.isTrayExit:
            self.__terminateListeners()
            self.opggWindow.close()
            self.hextechWindow.close()

            cfg.set(cfg.windowSize, self.windowSize)

            return super().closeEvent(a0)
        else:
            a0.ignore()
            self.hide()

    def __silentStart(self):
        if not cfg.get(cfg.enableSilent):
            return

        QTimer.singleShot(0, self.hide)

    @asyncSlot(str)
    async def __switchToSearchInterface(self, name):
        self.searchInterface.searchLineEdit.setText(name)
        self.checkAndSwitchTo(self.searchInterface)

        await self.searchInterface.onSearchButtonClicked()

    @asyncSlot(str)
    async def __switchToCareerInterface(self, puuid):
        if puuid == '00000000-0000-0000-0000-000000000000':
            return

        try:
            self.careerInterface.w.close()
        except (AttributeError, RuntimeError) as e:
            logger.debug(f"careerInterface close skipped: {e}", TAG)

        self.checkAndSwitchTo(self.careerInterface)
        # 同步设置 loading 状态以立即 UI 反馈
        self.careerInterface.setLoadingPageEnabled(True)
        await self.careerInterface.updateInterface(puuid=puuid)

    @asyncSlot(str)
    async def __onGameStatusChanged(self, status):
        title = None
        isGaming = False

        if status == 'None':
            title = self.tr("Home")
            await self.__onGameEnd()
        elif status == 'ChampSelect':
            title = self.tr("Selecting Champions")

            # 在标题添加所处队伍 (getMapSide 偶发失败不应阻断选英雄流程)
            try:
                side = await connector.getMapSide()
                if side:
                    if side == 'blue':
                        mapSide = self.tr("Blue Team")
                    else:
                        mapSide = self.tr("Red Team")

                    title = title + " - " + mapSide
            except Exception as e:
                logger.warning(f"getMapSide failed, skipping: {e}", TAG)

            await self.__onChampionSelectBegin()
        elif status == 'GameStart':
            title = self.tr("Gaming")
            await self.__onGameStart()
            isGaming = True
        elif status == 'InProgress':
            title = self.tr("Gaming")

            # 重连或正常进入游戏 (走 GameStart), 不需要更新数据
            if not self.isGaming:
                await self.__onGameStart()
            isGaming = True
        elif status == 'WaitingForStatus':
            title = self.tr("Waiting for status")
        elif status == 'EndOfGame':
            title = self.tr("End of game")
            asyncio.create_task(self.__autoHonor())
            # 自动再来一局: EndOfGame 阶段调用 playAgain()
            if cfg.get(cfg.enableAutoPlayAgain):
                asyncio.create_task(self.__autoPlayAgain())
        elif status == 'Lobby':
            title = self.tr("Lobby")
            # 战犯诊断必须在生涯刷新前完成, 否则 verdict 缓存还没写入,
            # 战绩卡片渲染时 getVerdict 命中不到, 徽章不会显示
            await self.__onGameEnd()
            # LCU match-history 缓存过期由 connector.getSummonerGamesByPuuid
            # 内部的重试机制处理 (检测到 stale cache 自动等待重试),
            # 这里无需再 sleep
            logger.error("Career: refresh triggered (lobby)", TAG)
            await self.careerInterface.refresh()

            # 同步刷新战绩查询页: 生涯页刷新后, 若搜索页已加载同一召唤师,
            # 强制重新拉取数据, 避免左侧对局列表显示旧数据
            if (self.searchInterface.puuid
                    and self.searchInterface.puuid != 0
                    and self.searchInterface.puuid == self.careerInterface.puuid):
                asyncio.create_task(
                    self.searchInterface.searchAndShowFirstPage(force=True))

            if self.stackedWidget.currentWidget() is self.gameInfoInterface:
                self.switchTo(self.careerInterface)

            self.__scheduleAutoStartMatchmaking()

        elif status == 'ReadyCheck':
            title = self.tr("Ready check")
            await self.__onMatchMade()
        elif status == 'Matchmaking':
            title = self.tr("Match making")
            await self.__onGameEnd()
        elif status == "Reconnect":
            title = self.tr("Waiting reconnect")
            await self.__onReconnect()

        if status != 'Lobby':
            self.__cancelAutoStartMatchmaking()

        self.isGaming = isGaming

        if status != 'ChampSelect':
            self.opggWindow.setStaysOnTopEnabled(False)
            self.hextechWindow.hide()

        if title is not None:
            self.setWindowTitle("Seraphine - " + title)

    async def __onMatchMade(self):
        if not cfg.get(cfg.enableAutoAcceptMatching):
            return

        async def accept():
            timeDelay = cfg.get(cfg.autoAcceptMatchingDelay)
            await asyncio.sleep(timeDelay)
            status = await connector.getReadyCheckStatus()

            if status.get("errorCode"):
                return

            if not status['playerResponse'] == 'Declined':
                await connector.acceptMatchMaking()

        asyncio.create_task(accept())

    async def __onReconnect(self):
        if not cfg.get(cfg.enableAutoReconnect):
            return

        async def reconnect():
            while await connector.getGameStatus() == "Reconnect":
                # 掉线立刻重连会无效
                await asyncio.sleep(.3)
                await connector.reconnect()

        asyncio.create_task(reconnect())

    async def __autoHonor(self):
        """EndOfGame 阶段自动给队友点赞.

        使用 /lol-honor-v2/v1/ballot (GET) 获取可点赞队友候选,
        按策略选一个后 POST /lol-honor-v2/v1/honor-player 提交.
        v2 端点提交后客户端自动记录, 无需 seal ballot.
        策略: friends_first (默认) / friends_only / best_score / random.

        ballot.eligibleAllies 可能因 LCU 时序问题为空 (尤其 ARAM Mayhem),
        最多重试 3 次, 每次间隔 2 秒.
        """
        if not cfg.get(cfg.enableAutoHonor):
            return

        try:
            await asyncio.sleep(cfg.get(cfg.autoHonorDelay))

            strategy = cfg.get(cfg.autoHonorStrategy)

            # ballot.eligibleAllies 可能为空 (LCU 时序), 最多重试 3 次
            ballot = None
            candidates = []
            for attempt in range(3):
                ballot = await connector.getEogStats()
                if not ballot:
                    logger.error(
                        f"Auto honor: no ballot (attempt={attempt})", TAG)
                    await asyncio.sleep(2)
                    continue
                candidates = ballot.get('eligibleAllies') or []
                if candidates:
                    break
                logger.error(
                    f"Auto honor: eligibleAllies empty, "
                    f"retry in 2s (attempt={attempt})",
                    TAG)
                await asyncio.sleep(2)

            if not candidates:
                logger.error(
                    "Auto honor: no eligibleAllies in ballot after retries",
                    TAG)
                return

            # ballot.gameId 用于 v2 honor-player 端点
            gameId = ballot.get("gameId")

            # 拉好友列表
            friends = await connector.getFriends()
            friendsPuuid = {f.get("puuid") for f in friends
                            if isinstance(f, dict) and f.get("puuid")}

            # 按策略选目标
            target = self.__pickHonorFromEligible(
                candidates, friendsPuuid, strategy)
            if not target:
                logger.error(
                    f"Auto honor: no valid target (strategy={strategy}, "
                    f"candidates={len(candidates)}, friends={len(friendsPuuid)})",
                    TAG)
                return

            puuid = target.get("puuid")
            if not puuid:
                logger.error(f"Auto honor: target has no puuid: {target}", TAG)
                return

            # ballot.eligibleAllies 同时含 summonerId 和 puuid;
            # v2 honor-player 端点需要 summonerId + gameId.
            summonerId = target.get("summonerId")

            logger.error(
                f"Auto honor: picked target={target} strategy={strategy}",
                TAG)
            ok = await connector.submitHonor(
                puuid, "HEART", summonerId=summonerId, gameId=gameId)
            name = target.get("summonerName") or puuid
            if ok:
                # submitHonor 内部已二次验证 honoredPlayers
                logger.error(
                    f"Auto honored: {name} (strategy={strategy}, verified)",
                    TAG)
            else:
                logger.error(
                    f"Auto honor failed: {name} "
                    f"(国服 LCU 可能无法联系 honor 服务器)", TAG)
        except Exception as e:
            logger.error(f"Auto honor failed: {e}", TAG)

    async def __autoPlayAgain(self):
        """EndOfGame 阶段自动点击"再来一局".

        调用 POST /lol-lobby/v2/play-again, 让客户端自动回到排队.
        延迟 2 秒执行, 避免与 honor 提交竞争.
        """
        try:
            await asyncio.sleep(2)
            logger.error("Auto play again: calling playAgain()", TAG)
            await connector.playAgain()
            logger.error("Auto play again: done", TAG)
        except Exception as e:
            logger.error(f"Auto play again failed: {e}", TAG)

    def __pickHonorFromEligible(self, candidates: list, friendsPuuid: set,
                                 strategy: str):
        """从 ballot eligibleAllies 选 honor 目标.

        candidates 字段: puuid/summonerId/summonerName/championId/championName 等.
        用 puuid 判断好友.
        """
        import random as _random
        if not candidates:
            return None

        friends = [c for c in candidates
                   if isinstance(c, dict) and c.get('puuid')
                   and c.get('puuid') in friendsPuuid]

        if strategy == 'friends_only':
            return friends[0] if friends else None
        if strategy == 'friends_first':
            return friends[0] if friends else candidates[0]
        if strategy == 'random':
            return _random.choice(candidates)
        # best_score 或未知: 暂无评分数据, 退化为第一个候选
        return candidates[0]

    def __scheduleAutoStartMatchmaking(self):
        if not cfg.get(cfg.enableAutoStartMatchmaking):
            return
        logger.error("Auto-start matchmaking: scheduled (entered lobby)", TAG)
        self.__cancelAutoStartMatchmaking()

        async def autoStart():
            delay = cfg.get(cfg.autoStartMatchmakingDelay)
            await asyncio.sleep(delay)
            try:
                cur_status = await connector.getGameStatus()
                if cur_status != 'Lobby':
                    logger.error(
                        f"Auto-start matchmaking: status changed to {cur_status}, abort", TAG)
                    return
                if not await connector.isLobbyReadyToSearch():
                    logger.error("Auto-start matchmaking: lobby not ready, abort", TAG)
                    return
                search_status = await connector.getMatchmakingStatus()
                if search_status and search_status.get('searchState') in ('Searching', 'Found', 'Accepted'):
                    logger.error(
                        f"Auto-start matchmaking: already in state {search_status.get('searchState')}, abort", TAG)
                    return
                ok = await connector.startMatchmaking()
                if ok:
                    logger.error("Auto-start matchmaking: started successfully", TAG)
                else:
                    logger.error("Auto-start matchmaking: startMatchmaking returned False", TAG)
            except Exception as e:
                logger.error(f"Auto-start matchmaking error: {e}", TAG)
            finally:
                self._autoStartTask = None

        self._autoStartTask = asyncio.create_task(autoStart())

    def __cancelAutoStartMatchmaking(self):
        if self._autoStartTask and not self._autoStartTask.done():
            self._autoStartTask.cancel()
        self._autoStartTask = None

    # 进入英雄选择界面时触发
    async def __onChampionSelectBegin(self):
        self.championSelection.reset()
        cSession, gSession = await asyncio.gather(connector.getChampSelectSession(),
                                                  connector.getGameflowSession())

        try:
            queueId = gSession['gameData']['queue']['id']
        except (KeyError, TypeError):
            queueId = None

        self.championSelection.queueId = queueId

        if cfg.get(cfg.autoShowOpgg):
            self.opggWindow.show()

            if cfg.get(cfg.enableOpggOnTop):
                self.opggWindow.setStaysOnTopEnabled(True)

        # 海克斯/大乱斗抢人窗口: 仅备选席模式 + 自动弹开启时显示
        if cfg.get(cfg.autoShowHextechWindow) and cSession.get('benchEnabled'):
            self.hextechWindow.show()
            if cfg.get(cfg.enableHextechWindowOnTop):
                self.hextechWindow.setStaysOnTopEnabled(True)

        currentSummonerId = self.currentSummoner['summonerId']
        info = await parseAllyGameInfo(cSession, currentSummonerId, queueId, useSGP=True)
        self.gameInfoInterface.updateAllySummoners(info)

        self.checkAndSwitchTo(self.gameInfoInterface)

    # 英雄选择时，英雄改变 / 楼层改变时触发
    @asyncSlot(dict)
    async def __onChampSelectChanged(self, data):
        data = data['data']

        # 诊断: 确认 ARAM 的 timer.phase 值 (不受 logLevel 限制)
        try:
            import os
            import json
            phaseDebug = os.path.join(
                os.environ.get('APPDATA', ''), 'Seraphine',
                'hextech_phase_debug.json')
            with open(phaseDebug, 'w', encoding='utf-8') as f:
                json.dump({
                    'phase': data.get('timer', {}).get('phase'),
                    'benchEnabled': data.get('benchEnabled'),
                    'enableAutoAramBench': cfg.get(cfg.enableAutoAramBench),
                }, f, ensure_ascii=False, indent=2)
        except (OSError, TypeError) as e:
            logger.debug(f"aram session save skipped: {e}", TAG)

        phase = {
            'PLANNING': [autoSetSummonerSpell, autoShow],
            'BAN_PICK': [autoSetSummonerSpell, autoBan, autoPick, autoComplete, autoSwap, showOpggBuild],
            'FINALIZATION': [autoSetSummonerSpell, autoTrade, showOpggBuild],
        }

        for func in phase.get(data['timer']['phase'], []):
            if await func(data, self.championSelection):
                break

        await self.gameInfoInterface.updateAllyIcon(data['myTeam'])

        self.gameInfoInterface.updateAllySummonersOrder(data['myTeam'])

        if data.get('benchEnabled'):
            await autoBenchGrab(data, self.championSelection)

        # 海克斯/大乱斗: 备选席模式时刷新抢人窗口的头像墙
        if data.get('benchEnabled') and self.hextechWindow.isVisible():
            signalBus.hextechSessionUpdated.emit(data)

    # 进入游戏后触发
    async def __onGameStart(self):
        session = await connector.getGameflowSession()
        currentSummonerId = self.currentSummoner['summonerId']

        queueId = session['gameData']['queue']['id']
        if queueId in (1700, 1090, 1100, 1110, 1130, 1160):  # 斗魂 云顶匹配 (排位)
            return

        # 如果是进游戏后开的软件，需要先把友方信息更新上去
        async def paintAllySummonersInfo():
            # 如果已经加载过且数量与当前队伍人数匹配，避免重复加载
            ally_team = None
            for team_key in ('teamOne', 'teamTwo'):
                team = session['gameData'].get(team_key, [])
                if any(p.get('summonerId') == currentSummonerId for p in team):
                    ally_team = team
                    break
            expected_ally_count = len(ally_team) if ally_team else 0

            if self.gameInfoInterface.allyChampions and expected_ally_count > 0 \
                    and len(self.gameInfoInterface.allyChampions) >= expected_ally_count:
                return

            info = await parseGameInfoByGameflowSession(
                session, currentSummonerId, "ally", useSGP=True)

            self.gameInfoInterface.allyChampions = {}
            self.gameInfoInterface.allyOrder = []

            self.gameInfoInterface.summonersView.ally.clear()
            self.gameInfoInterface.allyGamesView.clear()

            self.gameInfoInterface.updateAllySummoners(info)

        # 将敌方的召唤师基本信息绘制上去
        async def paintEnemySummonersInfo():
            info = await parseGameInfoByGameflowSession(
                session, currentSummonerId, 'enemy', useSGP=True)

            # 这个 info 是已经按照游戏位置排序过的了（若排位）
            self.gameInfoInterface.updateEnemySummoners(info)

        # 更新己方召唤师楼层顺序至角色顺序
        async def sortAllySummonersByGameRole():
            order = getAllyOrderByGameRole(session, currentSummonerId)
            if order is None:
                return

            interface = self.gameInfoInterface

            if order == interface.allyOrder or len(order) != len(interface.allyOrder):
                return

            interface.summonersView.ally.updateSummonersOrder(order)
            interface.allyGamesView.updateOrder(order)
            interface.allyOrder = order

        # 绘制提示组队的颜色
        async def paintTeamColor():
            ally, enemy = getTeamColor(session, currentSummonerId)
            self.gameInfoInterface.updateTeamColor(ally, enemy)

        await paintAllySummonersInfo()
        await asyncio.gather(paintEnemySummonersInfo(),
                             sortAllySummonersByGameRole())
        await paintTeamColor()

        self.checkAndSwitchTo(self.gameInfoInterface)

        # ARAM Mayhem: 启动海克斯辅助轮询
        if queueId == 2400 and cfg.get(cfg.enableHextechAssist):
            logger.error(
                f"HextechAssist: starting timer for queueId={queueId}", TAG)
            self.hextechAssistTimer.start()
            # 自动切到 OPGG 海克斯辅助页 (若开启自动显示)
            if cfg.get(cfg.hextechAssistAutoShow):
                try:
                    championId = await self.__getChampionIdFromLiveClient()
                    if championId and championId > 0:
                        logger.error(
                            f"HextechAssist: auto show for championId={championId}", TAG)
                        self.opggWindow.showHextechAssist(championId)
                    else:
                        logger.error(
                            "HextechAssist: no championId from live client", TAG)
                except Exception as e:
                    logger.error(f"Hextech assist auto show failed: {e}", TAG)

    async def __onGameEnd(self):
        # 停止海克斯辅助轮询
        self.hextechAssistTimer.stop()
        self.opggWindow.hextechAssistInterface.clearState()

        if not cfg.get(cfg.enableReserveGameinfo):
            self.gameInfoInterface.clear()

        # 全队 5 档评级: EndOfGame→Lobby 阶段评分并写缓存.
        # 必须 await 完成, 否则紧接着的生涯刷新拿不到评级缓存, 徽章不显示
        if cfg.get(cfg.enableTeamRating):
            logger.info("TeamRating: diagnose triggered (game end)", TAG)
            await self.__diagnoseLastGame()

    async def __diagnoseLastGame(self):
        """诊断上一局, 把 verdict 写入 war_criminal_cache.

        失败不阻塞流程, 仅日志. 海克斯大乱斗 (queueId=2400) 与
        ARAM/排位均参与诊断.
        """
        try:
            from app.lol.war_criminal import diagnoseGameFromParsed
            from app.lol.war_criminal_cache import getVerdict
            from app.lol.tools import parseGameDetailData

            # 拿当前召唤师 puuid, 用于判断嫌疑者
            currentPuuid = None
            if isinstance(self.currentSummoner, dict):
                currentPuuid = self.currentSummoner.get('puuid')
            if not currentPuuid:
                logger.error("WarCriminal: no current puuid", TAG)
                return

            # 取上一局 summary
            # connector.getSummonerGamesByPuuid 返回 dict (含 gameCount/games 等键),
            # 内部 games 字段才是对局列表
            # 游戏刚结束时 LCU API 可能还没更新战绩, 需要重试
            gamesResp = None
            for attempt in range(3):
                gamesResp = await connector.getSummonerGamesByPuuid(
                    currentPuuid, 0, 1)
                games_check = []
                if isinstance(gamesResp, dict):
                    games_check = gamesResp.get("games") or []
                elif isinstance(gamesResp, list):
                    games_check = gamesResp
                if games_check:
                    break
                logger.error(
                    f"WarCriminal: no games yet, retry {attempt + 1}/3", TAG)
                await asyncio.sleep(2)
            logger.error(
                f"WarCriminal: gamesResp type={type(gamesResp).__name__} "
                f"len={len(gamesResp) if hasattr(gamesResp, '__len__') else 'N/A'}",
                TAG)
            if isinstance(gamesResp, dict):
                games = gamesResp.get("games") or []
            elif isinstance(gamesResp, list):
                games = gamesResp
            else:
                games = []
            if not games:
                logger.error("WarCriminal: no recent game", TAG)
                return
            lastGame = games[0] if isinstance(games, list) and games else None
            if not isinstance(lastGame, dict):
                logger.error(f"WarCriminal: invalid lastGame type={type(lastGame)}", TAG)
                return
            gameId = lastGame.get('gameId')
            if not gameId:
                logger.error("WarCriminal: no gameId in lastGame", TAG)
                return

            # 如果缓存已有该局, 跳过
            if getVerdict(gameId):
                logger.error(f"WarCriminal: game {gameId} already diagnosed", TAG)
                return

            # 拿本局详情
            detail = await connector.getGameDetailByGameId(gameId)
            if not detail:
                logger.error(f"WarCriminal: no detail for {gameId}", TAG)
                return

            # 解析双方队伍 (注意签名: parseGameDetailData(puuid, game))
            parsed = await parseGameDetailData(currentPuuid, detail)
            if not parsed:
                logger.error(f"WarCriminal: parseGameDetailData returned None for {gameId}", TAG)
                return

            ratingStyle = cfg.get(cfg.teamRatingStyle)
            await diagnoseGameFromParsed(parsed, currentPuuid, gameId,
                                          ratingStyle=ratingStyle)
        except Exception as e:
            logger.error(f"WarCriminal diagnose failed: {e}", TAG)

    async def __onHextechAssistTick(self):
        """海克斯辅助定时轮询: 采集已选强化并刷新推荐列表"""
        try:
            from app.lol.augment_live import fetchCurrentAugments
            liveData = await fetchCurrentAugments()
            if liveData:
                signalBus.liveGameDataUpdated.emit(liveData)
                self.opggWindow.hextechAssistInterface.updateLiveState(liveData)
        except Exception as e:
            logger.error(f"Hextech assist tick failed: {e}", TAG)

    def __checkWindowSize(self):
        if (dpi := self.devicePixelRatioF()) == 1.0:
            return

        w, h = win32api.GetSystemMetrics(0), win32api.GetSystemMetrics(1)
        size: QSize = self.size() * dpi

        if size.width() < w and size.height() < h:
            return

        for scale in [2.0, 1.75, 1.5, 1.25, 1]:
            if scale * self.width() < w and scale * self.height() < h:
                cfg.set(cfg.dpiScale, scale)
                break

        self.splashScreen.finish()
        msg = ChangeDpiMessageBox(self.window())
        msg.exec()

    @asyncSlot(str)
    async def __onCareerGameClicked(self, gameId):
        name = self.careerInterface.getSummonerName()
        self.searchInterface.searchLineEdit.setText(name)

        # 从生涯页跳过来默认将筛选条件设置为全部 -- By Hpero4
        self.searchInterface.filterComboBox.setCurrentIndex(0)

        # 先加载完再切换, 避免加载过程中换搜索目标导致puuid出错 -- By Hpero4
        await self.searchInterface.searchAndShowFirstPage(self.careerInterface.puuid)
        self.checkAndSwitchTo(self.searchInterface)
        self.searchInterface.loadingGameId = gameId

        # 先画框再加载对局 否则快速切换(如筛选或换人)会导致找不到widget -- By Hpero4
        self.searchInterface.waitingForDrawSelect(gameId)
        await self.searchInterface.updateGameDetailView(gameId, self.careerInterface.puuid)

    @asyncSlot()
    async def showOpggWindow(self):
        self.opggWindow.show()
        self.opggWindow.showNormal()
        self.opggWindow.raise_()

        # 自动获取当前英雄和模式, 切换 OPGG 到对应界面
        if not self.isClientProcessRunning:
            return
        try:
            await self.__autoSyncOpggToCurrentGame()
        except Exception as e:
            logger.warning(f"Auto sync OPGG to current game failed: {e}", TAG)

    async def __autoSyncOpggToCurrentGame(self):
        """根据当前游戏状态自动切换 OPGG 模式和英雄"""
        try:
            status = await connector.getGameStatus()
        except Exception as e:
            logger.error(f"Auto sync OPGG: getGameStatus failed: {e}", TAG)
            return

        # 用 error 级别记录, 确保写入日志文件 (项目日志级别为 ERROR)
        logger.error(f"Auto sync OPGG: status={status}", TAG)

        # 仅在选人或游戏中自动切换
        if status not in ('ChampSelect', 'InProgress', 'Lobby', 'ReadyCheck'):
            return

        championId = 0
        queueId = 0

        if status == 'ChampSelect':
            try:
                session = await connector.getChampSelectSession()
            except (aiohttp.ClientError, OSError) as e:
                logger.debug(f"getChampSelectSession failed: {e}", TAG)
                return
            if not session:
                return
            # 从选人会话提取当前玩家英雄
            cellId = session.get('localPlayerCellId', 0)
            for p in session.get('myTeam', []):
                if p.get('cellId') == cellId:
                    championId = p.get('championId', 0) or p.get(
                        'championPickIntent', 0)
                    break
            # 选人会话本身不含 queueId, 通过 gameflow 获取
            try:
                gf = await connector.getGameflowSession()
                queueId = gf.get('gameData', {}).get(
                    'queue', {}).get('id', 0) if gf else 0
            except Exception:
                queueId = 0
        elif status == 'InProgress':
            # 游戏中: 从 gameflow 获取 queueId
            try:
                session = await connector.getGameflowSession()
                data = session.get('gameData', {}) if session else {}
                queueId = data.get('queue', {}).get('id', 0)
            except Exception as e:
                logger.error(
                    f"Auto sync OPGG: getGameflowSession failed: {e}", TAG)
            # 游戏中: 从 Live Client API 获取当前英雄
            championId = await self.__getChampionIdFromLiveClient()

        mode = self.__queueIdToOpggMode(queueId, status)
        logger.error(
            f"Auto sync OPGG: championId={championId}, queueId={queueId}, mode={mode}", TAG)

        if not mode:
            return

        # ARAM Mayhem 游戏中: 切到海克斯辅助页 (而非 build 页)
        if mode == 'aram_mayhem' and status == 'InProgress' \
                and cfg.get(cfg.enableHextechAssist):
            if championId and championId > 0:
                self.opggWindow.showHextechAssist(championId)
            return

        if championId and championId > 0:
            # 有英雄: 跳转到 build 页 (信号处理会自动设置 mode combobox)
            signalBus.toOpggBuildInterface.emit(championId, mode, "")
        else:
            # 无英雄: 仅切换模式, 刷新当前界面
            self.opggWindow.setModeByData(mode)

    async def __getChampionIdFromLiveClient(self) -> int:
        """从 Live Client API (端口 2999) 获取当前游戏中英雄 ID, 失败返回 0"""
        try:
            active_name = await liveClient.getActivePlayerName()
            data = await liveClient.getAllGameData()
            if not data or not isinstance(data, dict):
                return 0
            all_players = data.get('allPlayers', [])
            if not isinstance(all_players, list):
                return 0
            for p in all_players:
                if not isinstance(p, dict):
                    continue
                # 匹配活跃玩家 (summonerName 或 riotIdName)
                p_name = p.get('summonerName') or p.get('riotIdName') or ''
                if active_name and p_name and (
                        p_name == active_name or active_name.startswith(p_name)):
                    champion_name = p.get('championName', '')
                    if champion_name:
                        try:
                            return connector.manager.getChampionIdByName(champion_name)
                        except (AttributeError, KeyError, ValueError) as e:
                            logger.debug(f"getChampionIdByName failed: {e}", TAG)
                            return 0
                    break
        except Exception as e:
            logger.error(
                f"Auto sync OPGG: Live Client API failed: {e}", TAG)
        return 0

    def __queueIdToOpggMode(self, queueId, status):
        """queueId -> OPGG mode 字符串"""
        if queueId == 450:
            return 'aram'
        if queueId == 2400:
            return 'aram_mayhem'
        if queueId in (1700, 1710):
            return 'arena'
        if queueId == 1300:
            return 'nexus_blitz'
        if queueId in (900, 1900):
            return 'urf'
        # 排位/其他
        return 'ranked' if status in ('ChampSelect', 'InProgress') else ""

    @asyncSlot()
    async def showHextechWindow(self):
        """导航栏按钮: 弹出抢英雄 Flyout 浮层 (不进入独立页面)"""
        if not self.isClientProcessRunning:
            InfoBar.warning(
                self.tr("提示"),
                self.tr("英雄联盟客户端未运行"),
                parent=self, duration=3000, position=InfoBarPosition.TOP)
            return

        # 锚点: 导航栏中点击的按钮
        target = self.sender() or self.navigationInterface

        # 取当前选人会话; 不在选人中则提示
        try:
            data = await connector.getChampSelectSession()
        except Exception:
            data = None

        if not data or not data.get('benchEnabled'):
            InfoBar.warning(
                self.tr("提示"),
                self.tr("当前不在大乱斗/海克斯大乱斗选人中"),
                parent=self, duration=3000, position=InfoBarPosition.TOP)
            return

        # 构建 Flyout
        flyoutView = HextechGrabFlyout(self)

        from app.lol.tools import _getLocalChampionId, _getBenchChampionIds
        bench = set(_getBenchChampionIds(data))
        mine = _getLocalChampionId(data)
        cellId = data.get('localPlayerCellId')
        shown = set()

        # 手持
        if mine:
            name, icon = await self.hextechWindow._getChampionNameIcon(mine)
            flyoutView.addChampion(mine, icon, name, 'mine')
            shown.add(mine)
        # 备选席
        for cid in sorted(bench):
            if cid in shown:
                continue
            name, icon = await self.hextechWindow._getChampionNameIcon(cid)
            flyoutView.addChampion(cid, icon, name, 'bench')
            shown.add(cid)
        # 队友持有
        for player in data.get('myTeam', []):
            cid = player.get('championId', 0) or 0
            if cid in shown or cid == 0 or player.get('cellId') == cellId:
                continue
            name, icon = await self.hextechWindow._getChampionNameIcon(cid)
            flyoutView.addChampion(cid, icon, name, 'ally')
            shown.add(cid)

        flyoutView.connectClicks()
        flyoutView.championGrabRequested.connect(self.__onHextechFlyoutGrab)

        self._hextechFlyout = Flyout.make(
            flyoutView, target, self, FlyoutAnimationType.DROP_DOWN)

    def __onHextechFlyoutGrab(self, championId):
        """Flyout 头像点击: 设为手动抢目标"""
        self.championSelection.hextechTargetId = championId
        self.championSelection.manualGrabRequested = True
        logger.info(f"hextech flyout: manual grab {championId}", TAG)

    @asyncSlot()
    async def __refreshCareerInterface(self):
        if self.isClientProcessRunning:
            self.careerInterface.refreshButton.click()

    @asyncSlot()
    async def __cascadeSetMicaEffect(self):
        isMicaEnabled = cfg.get(cfg.micaEnabled)
        self.setMicaEffectEnabled(isMicaEnabled)
        self.opggWindow.setMicaEffectEnabled(isMicaEnabled)
        self.hextechWindow.setMicaEffectEnabled(isMicaEnabled)

    @asyncSlot()
    async def __onFixLCUButtonClicked(self):
        if self.isClientProcessRunning:
            await connector.playAgain()

    def exceptHook(self, ty, value, tb):
        tracebackFormat = traceback.format_exception(ty, value, tb)
        title = self.tr('Exception occurred 😥')
        content = "".join(tracebackFormat)

        if ty in [ConnectionRefusedError, ClientConnectorError]:
            return

        logger.error(f"Exception occurred:\n{content}", "Crash")

        for call in connector.callStack:
            logger.error(call, "Crash")

        logger.error(str(self.searchInterface), "Crash")
        logger.error(str(self.gameInfoInterface), "Crash")
        logger.error(str(self.careerInterface), "Crash")
        logger.error(str(self.auxiliaryFuncInterface), "Crash")
        logger.error(str(self.settingInterface), "Crash")

        content = f"Seraphine ver.{BETA or VERSION}\n{'-'*5}\n{content}"

        w = ExceptionMessageBox(title, content, self.window())

        if w.exec():
            pyperclip.copy(content)

        self.oldHook(ty, value, tb)
        signalBus.terminateListeners.emit()
        logger.error("Abnormal exit", "Crash")
        sys.exit()

    def __onCurrentStackedChanged(self, index):
        widget: SmoothScrollArea = self.stackedWidget.view.currentWidget()
        widget.delegate.vScrollBar.resetValue(0)

    def eventFilter(self, obj, e: QEvent):
        # Fix #553, #560
        if e.type() == QEvent.Type.Resize:
            self.windowSize = self.size()

        if e.type() == QEvent.Type.Move:
            self.resize(self.windowSize)

        return super().eventFilter(obj, e)
