import asyncio
from qasync import asyncSlot
import pyperclip
from PyQt5.QtWidgets import (QHBoxLayout, QLabel, QVBoxLayout, QSpacerItem,
                             QSizePolicy, QTableWidgetItem, QHeaderView,
                             QWidget, QFrame, QStackedWidget)
from PyQt5.QtCore import Qt, pyqtSignal
from ..common.qfluentwidgets import (TableWidget, PushButton, ComboBox,
                                     SmoothScrollArea, ToolTipFilter, setCustomStyleSheet,
                                     ToolTipPosition, ToolButton, IndeterminateProgressRing,
                                     Flyout, FlyoutViewBase, FlyoutAnimationType, InfoBar,
                                     InfoBarPosition)
from app.common.logger import logger

from app.components.game_infobar_widget import GameInfoBar
from app.components.champion_icon_widget import RoundIcon
from app.components.profile_level_icon_widget import RoundLevelAvatar
from app.components.summoner_name_button import SummonerName
from app.components.color_label import ColorLabel
from app.components.animation_frame import ColorAnimationFrame
from app.common.style_sheet import StyleSheet
from app.common.icons import Icon
from app.common.signals import signalBus
from app.common.config import cfg
from app.lol.connector import connector
from app.lol.tools import (parseGames, parseSummonerData,
                           getRecentTeammates, parseDetailRankInfo,
                           getNameTagLineFromGame)
from ..components.seraphine_interface import SeraphineInterface


def _sgpGamesToLcuFormat(sgp_response: dict) -> dict:
    """Convert SGP SUMMARY games response to LCU format for parseSummonerData."""
    games = sgp_response.get("games") or []
    return {
        "gameCount": sgp_response.get("totalGames", len(games)),
        "games": [g["json"] for g in games],
        "gameBeginDate": sgp_response.get("gameBeginDate"),
    }


def _sgpSummonerToLcuFormat(sgp_summoner: dict, puuid: str, first_game: dict) -> dict:
    """Convert SGP summoner response to LCU format for parseSummonerData."""
    name, tagline = "", ""
    if first_game and "json" in first_game:
        result = getNameTagLineFromGame(first_game, puuid)
        if result:
            name, tagline = result
    return {
        "puuid": puuid,
        "gameName": name,
        "displayName": name,
        "tagLine": tagline,
        "summonerLevel": sgp_summoner.get("level", -1),
        "xpSinceLastLevel": sgp_summoner.get("expPoints", 0),
        "xpUntilNextLevel": sgp_summoner.get("expToNextLevel", 0),
        "profileIconId": sgp_summoner.get("profileIconId", 0),
        "privacy": sgp_summoner.get("privacy", "PUBLIC"),
    }


def _sgpRankedToLcuFormat(sgp_ranked: dict) -> dict:
    """Convert SGP ranked stats (queues list) to LCU format (queueMap dict)."""
    if not sgp_ranked or "errorCode" in sgp_ranked:
        return {}
    queue_map = {}
    for q in sgp_ranked.get("queues") or []:
        queue_map[q["queueType"]] = {
            "tier": q.get("tier", ""),
            "division": q.get("rank", "NA"),
            "highestTier": q.get("highestTier", ""),
            "highestDivision": q.get("highestRank", "NA"),
            "previousSeasonEndTier": q.get("previousSeasonEndTier", ""),
            "previousSeasonEndDivision": q.get("previousSeasonEndRank", "NA"),
            "wins": q.get("wins", 0),
            "losses": q.get("losses", 0),
            "leaguePoints": q.get("leaguePoints", 0),
        }
    return {"queueMap": queue_map}


class NameLabel(QLabel):
    def text(self) -> str:
        return super().text().replace("🔒", '')


class TagLineLabel(QLabel):
    def text(self) -> str:
        return super().text().replace(" ", '')


class CareerInterface(SeraphineInterface):
    gameInfoBarClicked = pyqtSignal(str)
    iconLevelExpChanged = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.loginSummonerPuuid = None
        self.puuid = None
        self.showTagLine = False
        self.recentTeammatesInfo = None

        self.vBoxLayout = QVBoxLayout(self)
        self.IconNameHBoxLayout = QHBoxLayout()
        self.nameLevelVLayout = QVBoxLayout()
        self.icon = RoundLevelAvatar('app/resource/images/champion-0.png',
                                     0,
                                     1,
                                     parent=self)
        self.name = NameLabel(self.tr("Connecting..."))
        # self.serviceLabel = QLabel()
        self.tagLineLabel = TagLineLabel()
        self.copyButton = ToolButton(Icon.COPY)
        self.nameButtonLayout = QHBoxLayout()
        self.nameTagLineLayout = QVBoxLayout()
        self.subtitleLayout = QHBoxLayout()

        self.buttonsLayout = QVBoxLayout()
        self.backToMeButton = PushButton(self.tr("Back to me"))
        self.refreshButton = PushButton(self.tr("Refresh"))
        self.searchButton = PushButton(self.tr("Game history"))

        self.tableLayout = QHBoxLayout()
        self.rankInfo = None
        self.rankTable = TableWidget(self)

        self.recentInfoHLayout = QHBoxLayout()
        self.recent20GamesLabel = QLabel(
            self.tr('Recent matches') + " " + self.tr('(Last') + " None " +
            self.tr('games)'))
        self.winsLabel = ColorLabel(self.tr("Wins:") + " None", 'win')
        self.lossesLabel = ColorLabel(self.tr("Losses:") + " None", 'lose')
        self.kdaLabel = QLabel(
            self.tr("KDA:") + " None / None / None" + self.tr("(") + "0" + self.tr(")"))
        self.championsCard = ChampionsCard()
        self.recentTeamButton = PushButton(self.tr("Recent teammates"))
        self.filterComboBox = ComboBox()
        self.recentTeammatesFlyout: Flyout = None

        self.gameInfoAreaLayout = QHBoxLayout()
        self.gameInfoArea = SmoothScrollArea()
        self.gameInfoLayout = QVBoxLayout()
        self.gameInfoWidget = QWidget()

        self.progressRing = IndeterminateProgressRing()

        self.games = []

        self.loadGamesTask = None

        self.__initWidget()
        self.__initLayout()
        self.__connectSignalToSlot()

    def __initWidget(self):
        # self.serviceLabel.setAlignment(Qt.AlignRight)
        # self.serviceLabel.setObjectName("tagLineLabel")
        # self.serviceLabel.setContentsMargins(0, 0, 5, 0)

        self.tagLineLabel.setVisible(False)
        self.tagLineLabel.setAlignment(Qt.AlignCenter)

        self.copyButton.setFixedSize(26, 26)
        self.copyButton.setEnabled(False)
        self.copyButton.setToolTip(self.tr("Copy summoner name to ClipBoard"))
        self.copyButton.installEventFilter(
            ToolTipFilter(self.copyButton, 500, ToolTipPosition.TOP))

        self.name.setObjectName("name")
        self.name.setAlignment(Qt.AlignCenter)
        self.tagLineLabel.setObjectName("tagLineLabel")
        self.nameLevelVLayout.setObjectName("nameLevelVLayout")

        self.recent20GamesLabel.setObjectName('rencent20GamesLabel')
        self.winsLabel.setObjectName('winsLabel')
        self.lossesLabel.setObjectName('lossesLabel')

        self.kdaLabel.setObjectName('kdaLabel')
        self.recentInfoHLayout.setObjectName("recentInfoHLayout")
        self.gameInfoArea.setObjectName('gameInfoArea')
        self.gameInfoWidget.setObjectName("gameInfoWidget")

        self.backToMeButton.setEnabled(False)

        self.recentTeamButton.setEnabled(True)

        self.rankTable.setRowCount(2)
        self.rankTable.setColumnCount(9)
        self.rankTable.verticalHeader().hide()
        self.rankTable.setWordWrap(False)
        self.rankTable.setHorizontalHeaderLabels([
            self.tr('Game Type'),
            self.tr('Total'),
            self.tr('Win Rate'),
            self.tr('Wins'),
            self.tr('Losses'),
            self.tr('Tier'),
            self.tr('LP'),
            self.tr("Highest tier"),
            self.tr("Previous end tier"),
        ])

        self.rankInfo = [[
            self.tr('Ranked Solo'),
        ], [
            self.tr('Ranked Flex'),
        ]]

        self.filterComboBox.addItems([
            self.tr('All'),
            self.tr('Normal'),
            self.tr("大乱斗"),
            self.tr("海克斯大乱斗"),
            self.tr("Ranked Solo"),
            self.tr("Ranked Flex")
        ])
        self.filterComboBox.setCurrentIndex(0)
        self.winsLabel.setToolTip(
            self.tr("Remakes or Customs do not count in statistics"))
        self.winsLabel.installEventFilter(
            ToolTipFilter(self.winsLabel, 500, ToolTipPosition.TOP))
        self.lossesLabel.setToolTip(
            self.tr("Remakes or Customs do not count in statistics"))
        self.lossesLabel.installEventFilter(
            ToolTipFilter(self.lossesLabel, 500, ToolTipPosition.TOP))
        self.kdaLabel.setToolTip(
            self.tr("Remakes or Customs do not count in statistics"))
        self.kdaLabel.installEventFilter(
            ToolTipFilter(self.kdaLabel, 500, ToolTipPosition.TOP))

        self.__updateTable()

        StyleSheet.CAREER_INTERFACE.apply(self)
        self.initTableStyle()

    def __initLayout(self):
        self.subtitleLayout.setContentsMargins(0, 0, 0, 0)
        # self.subtitleLayout.addWidget(self.serviceLabel)
        self.subtitleLayout.addWidget(self.tagLineLabel)

        self.nameTagLineLayout.setContentsMargins(0, 0, 0, 0)
        self.nameTagLineLayout.addWidget(self.name)
        self.nameTagLineLayout.addLayout(self.subtitleLayout)
        self.nameTagLineLayout.setSpacing(0)

        self.nameButtonLayout.setContentsMargins(0, 0, 0, 0)
        self.nameButtonLayout.addLayout(self.nameTagLineLayout)
        self.nameButtonLayout.addSpacing(5)
        self.nameButtonLayout.addWidget(self.copyButton)

        self.nameLevelVLayout.addSpacerItem(
            QSpacerItem(1, 25, QSizePolicy.Minimum, QSizePolicy.Fixed))
        self.nameLevelVLayout.addLayout(self.nameButtonLayout)
        # self.nameLevelVLayout.addWidget(self.level, alignment=Qt.AlignCenter)
        self.nameLevelVLayout.addSpacerItem(
            QSpacerItem(1, 25, QSizePolicy.Minimum, QSizePolicy.Fixed))

        self.recentInfoHLayout.setSpacing(15)
        self.recentInfoHLayout.addWidget(self.recent20GamesLabel,
                                         alignment=Qt.AlignCenter)
        self.recentInfoHLayout.addWidget(self.winsLabel,
                                         alignment=Qt.AlignCenter)
        self.recentInfoHLayout.addWidget(self.lossesLabel,
                                         alignment=Qt.AlignCenter)
        self.recentInfoHLayout.addWidget(self.kdaLabel,
                                         alignment=Qt.AlignCenter)
        self.recentInfoHLayout.addSpacerItem(
            QSpacerItem(1, 1, QSizePolicy.Expanding, QSizePolicy.Minimum))
        self.recentInfoHLayout.addWidget(
            self.championsCard, alignment=Qt.AlignCenter)
        self.recentInfoHLayout.addWidget(
            self.recentTeamButton, alignment=Qt.AlignCenter)
        self.recentInfoHLayout.addWidget(self.filterComboBox,
                                         alignment=Qt.AlignCenter)

        # 这俩玩意的高度居然不一样，看着难受，手动让它俩一样
        # 33 == self.filterComboBox.height()
        self.recentTeamButton.setFixedHeight(33)

        self.IconNameHBoxLayout.addSpacing(
            self.backToMeButton.sizeHint().width())
        self.IconNameHBoxLayout.addItem(
            QSpacerItem(1, 1, QSizePolicy.Expanding, QSizePolicy.Minimum))
        self.IconNameHBoxLayout.addWidget(self.icon)
        self.IconNameHBoxLayout.addSpacing(20)
        self.IconNameHBoxLayout.addLayout(self.nameLevelVLayout)
        self.IconNameHBoxLayout.addItem(
            QSpacerItem(1, 1, QSizePolicy.Expanding, QSizePolicy.Minimum))

        self.buttonsLayout.addWidget(self.backToMeButton)
        self.buttonsLayout.addWidget(self.refreshButton)
        self.buttonsLayout.addWidget(self.searchButton)
        self.IconNameHBoxLayout.addLayout(self.buttonsLayout)

        self.gameInfoWidget.setLayout(self.gameInfoLayout)
        self.gameInfoArea.setWidget(self.gameInfoWidget)
        self.gameInfoArea.setWidgetResizable(True)
        self.gameInfoArea.setViewportMargins(0, 0, 5, 0)

        self.vBoxLayout.addWidget(self.progressRing, alignment=Qt.AlignCenter)

        self.vBoxLayout.addLayout(self.IconNameHBoxLayout)
        self.vBoxLayout.addSpacing(20)
        self.vBoxLayout.addWidget(self.rankTable)
        self.vBoxLayout.addSpacing(5)
        self.vBoxLayout.addLayout(self.recentInfoHLayout)
        self.vBoxLayout.addSpacing(5)
        self.vBoxLayout.addWidget(self.gameInfoArea)
        self.vBoxLayout.addSpacing(10)

        self.vBoxLayout.setContentsMargins(30, 32, 30, 20)

        self.setLoadingPageEnabled(True)

    def setLoadingPageEnabled(self, enable):
        self.gameInfoArea.delegate.vScrollBar.resetValue(0)
        self.gameInfoArea.verticalScrollBar().setSliderPosition(0)

        self.icon.setVisible(not enable)
        self.name.setVisible(not enable)
        self.copyButton.setVisible(not enable)
        self.refreshButton.setVisible(not enable)
        self.backToMeButton.setVisible(not enable)
        self.searchButton.setVisible(not enable)
        self.rankTable.setVisible(not enable)
        self.recent20GamesLabel.setVisible(not enable)
        self.filterComboBox.setVisible(not enable)
        self.championsCard.setVisible(not enable)
        self.recentTeamButton.setVisible(not enable)
        self.winsLabel.setVisible(not enable)
        self.lossesLabel.setVisible(not enable)
        self.kdaLabel.setVisible(not enable)
        self.winsLabel.setVisible(not enable)
        self.lossesLabel.setVisible(not enable)
        self.gameInfoArea.setVisible(not enable)
        self.tagLineLabel.setVisible(not enable and self.showTagLine)

        self.progressRing.setVisible(enable)

    def __updateTable(self):
        for i, line in enumerate(self.rankInfo):
            for j, data in enumerate(line):
                item = QTableWidgetItem(data)
                item.setTextAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.rankTable.setItem(i, j, item)

        self.rankTable.resizeColumnsToContents()
        self.rankTable.resizeRowsToContents()
        # self.table.setFixedWidth(self.table.viewportSizeHint().width())
        self.rankTable.setFixedHeight(
            self.rankTable.viewportSizeHint().height() + 4)
        self.rankTable.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)

    def initTableStyle(self):
        light = '''
            QHeaderView::section:horizontal {
                border: none;
                border-bottom: 1px solid rgba(0, 0, 0, 0.095);
            }

            QTableView {
                border: 1px solid rgba(0, 0, 0, 0.095);
                border-radius: 6px;
                background: rgba(255, 255, 255, 0.667);
            }
        '''

        dark = '''
            QHeaderView::section:horizontal {
                border: none;
                border-bottom: 1px solid rgb(35, 35, 35);
            }

            QTableView {
                border: 1px solid rgb(35, 35, 35);
                border-radius: 6px;
                background: rgba(255, 255, 255, 0.051);
            }
        '''

        setCustomStyleSheet(self.rankTable, light, dark)

    def __connectSignalToSlot(self):
        self.backToMeButton.clicked.connect(self.__changeToCurrentSummoner)
        self.refreshButton.clicked.connect(self.refresh)
        self.searchButton.clicked.connect(
            lambda: signalBus.toSearchInterface.emit(self.getSummonerName()))
        self.filterComboBox.currentIndexChanged.connect(
            self.__onfilterComboBoxChanged)
        self.copyButton.clicked.connect(
            lambda: pyperclip.copy(self.getSummonerName()))

        self.recentTeamButton.clicked.connect(
            self.__onRecentTeammatesButtonClicked)

    async def updateNameIconExp(self, info):
        if not self.isLoginSummoner():
            return

        name = info.get("gameName") or info['displayName']
        name = name if info['privacy'] == 'PUBLIC' else f"{name}🔒"
        icon = await connector.getProfileIcon(info['profileIconId'])
        level = info['summonerLevel']
        xpSinceLastLevel = info['xpSinceLastLevel']
        xpUntilNextLevel = info['xpUntilNextLevel']

        self.name.setText(name)
        levelStr = str(level) if level != -1 else "None"
        self.icon.updateIcon(icon, xpSinceLastLevel,
                             xpUntilNextLevel, levelStr)

        self.repaint()

    @asyncSlot()
    async def __changeToCurrentSummoner(self):
        self.setLoadingPageEnabled(True)
        try:
            summoner = await connector.getCurrentSummoner()
        except Exception:
            InfoBar.warning(
                self.tr("Connection error"),
                self.tr("Cannot connect to LOL client."),
                orient=Qt.Vertical,
                position=InfoBarPosition.BOTTOM_RIGHT,
                duration=3000,
                parent=self.window())
            self.setLoadingPageEnabled(False)
            return
        # LCU 未就绪时 @retry 拦截 ReferenceError 返回 None
        if summoner is None:
            self.setLoadingPageEnabled(False)
            return
        await self.updateInterface(summoner=summoner)

    @asyncSlot()
    async def refresh(self):
        # 三层 puuid 兜底:
        #   1. self.puuid (正常加载后)
        #   2. self.loginSummonerPuuid (初始加载失败的恢复)
        #   3. connector.getCurrentSummoner() (极端边缘情况)
        puuid = self.puuid
        if not puuid:
            puuid = self.loginSummonerPuuid
        if not puuid:
            try:
                s = await connector.getCurrentSummoner()
                puuid = s.get('puuid') if s else None
            except Exception:
                pass
        if not puuid:
            return

        # 同步设置 loading 状态, 确保 UI 立即反馈
        # asyncSlot 创建 task 后会立即返回, 若 loading 状态在 await 内设置,
        # 用户点击刷新按钮后视觉延迟 (按钮不隐藏, loading 动画不显示)
        self.setLoadingPageEnabled(True)

        if self.loadGamesTask and not self.loadGamesTask.done():
            self.loadGamesTask.cancel()

        index = self.filterComboBox.currentIndex()
        await self.updateInterface(puuid=puuid)
        self.filterComboBox.blockSignals(True)
        self.filterComboBox.setCurrentIndex(index)
        self.filterComboBox.blockSignals(False)
        self.__onfilterComboBoxChanged(index)

    async def updateInterface(self, puuid=None, summoner=None):
        '''
        通过 `puuid` 或 `summoner` 更新界面
        '''

        # 不能同时为空
        assert summoner or puuid

        # 调用方若需要立即 UI 反馈 (如 refresh 按钮), 应在 await 前同步设置 loading
        self.recentTeammatesInfo = None

        if self.recentTeammatesFlyout:
            self.recentTeammatesFlyout.close()
            self.recentTeammatesFlyout = None

        sgp_fallback = False
        try:
            if summoner is None:
                try:
                    summoner = await connector.getSummonerByPuuid(puuid)
                except Exception:
                    sgp_fallback = True
                    sgp_summoner, sgp_games, sgp_ranked = await asyncio.gather(
                        connector.getSummonerByPuuidViaSGP(puuid),
                        connector.getSummonerGamesByPuuidViaSGP(puuid, 0, cfg.get(cfg.careerGamesNumber) - 1),
                        connector.getRankedStatsByPuuidViaSGP(puuid),
                    )
                    if sgp_summoner is None:
                        self.setLoadingPageEnabled(False)
                        return
                    if 'errorCode' in sgp_summoner:
                        InfoBar.error(self.tr("Get summoner infomation error"),
                                      self.tr("The server returned abnormal content."),
                                      orient=Qt.Vertical,
                                      position=InfoBarPosition.BOTTOM_RIGHT,
                                      duration=5000,
                                      parent=self.window())
                        self.setLoadingPageEnabled(False)
                        return
                    first_game = (sgp_games.get("games") or [{}])[0]
                    summoner = _sgpSummonerToLcuFormat(sgp_summoner, puuid, first_game)
                    async def _wrap(v):
                        return v
                    self.loadGamesTask = asyncio.create_task(
                        _wrap(_sgpGamesToLcuFormat(sgp_games)))
                    rankTask = asyncio.create_task(
                        _wrap(_sgpRankedToLcuFormat(sgp_ranked)))
        except Exception as e:
            InfoBar.warning(
                self.tr("Connection error"),
                self.tr("Cannot connect to LOL client, displaying cached data."),
                orient=Qt.Vertical,
                position=InfoBarPosition.BOTTOM_RIGHT,
                duration=3000,
                parent=self.window())
            self.setLoadingPageEnabled(False)
            return

        # getSummonerByPuuid 在 LCU 未就绪时被 @retry 拦截返回 None
        # (ReferenceError -> signalBus.lcuNotConnected -> return None)
        if summoner is None:
            self.setLoadingPageEnabled(False)
            return

        if 'errorCode' in summoner:
            InfoBar.error(self.tr("Get summoner infomation error"),
                          self.tr("The server returned abnormal content."),
                          orient=Qt.Vertical,
                          position=InfoBarPosition.BOTTOM_RIGHT,
                          duration=5000,
                          parent=self.window())

            self.setLoadingPageEnabled(False)
            return

        if not sgp_fallback:
            self.loadGamesTask = asyncio.create_task(
                connector.getSummonerGamesByPuuid(summoner['puuid'], 0, cfg.get(cfg.careerGamesNumber) - 1))
            rankTask = asyncio.create_task(
                connector.getRankedStatsByPuuid(summoner['puuid']))

        try:
            info = await parseSummonerData(summoner, rankTask, self.loadGamesTask)
        except Exception as e:
            logger.exception(
                "parseSummonerData raised", e, "CareerInterface")
            InfoBar.warning(
                self.tr("Data load failed"),
                self.tr("Failed to load game data, displaying cached data."),
                orient=Qt.Vertical,
                position=InfoBarPosition.BOTTOM_RIGHT,
                duration=3000,
                parent=self.window())
            self.setLoadingPageEnabled(False)
            return

        await self.repaintInterface(info)

    async def repaintInterface(self, info):
        name = info['name'] if info['isPublic'] else f"{info['name']}🔒"
        icon = info['icon']
        level = info['level']
        xpSinceLastLevel = info['xpSinceLastLevel']
        xpUntilNextLevel = info['xpUntilNextLevel']
        puuid = info['puuid']
        rankInfo = info['rankInfo']
        games = info['games']

        # self.serviceLabel.setText(SERVERS_NAME.get(
        #     connector.server) or connector.server)
        # subset = SERVERS_SUBSET.get(connector.server)
        # if subset:
        #     self.serviceLabel.setToolTip(" ".join(subset))
        #     self.serviceLabel.installEventFilter(
        #         ToolTipFilter(self.serviceLabel, 500, ToolTipPosition.BOTTOM))

        if len(info['tagLine']):
            self.showTagLine = True
            self.tagLineLabel.setText(f"# {info['tagLine']}")
        else:
            self.showTagLine = False
            self.tagLineLabel.setText("")

        levelStr = str(level) if level != -1 else "None"
        self.icon.updateIcon(icon, xpSinceLastLevel,
                             xpUntilNextLevel, levelStr)
        self.name.setText(name)

        self.puuid = puuid

        if 'queueMap' in rankInfo:
            self.rankInfo = parseDetailRankInfo(rankInfo)
            self.copyButton.setEnabled(True)
        else:
            self.rankInfo = [[
                self.tr('Ranked Solo'),
            ], [
                self.tr('Ranked Flex'),
            ]]
            self.copyButton.setEnabled(False)

        if not self.isLoginSummoner():
            for i in range(0, 2):
                for j in [1, 2, 4]:
                    self.rankInfo[i][j] = '--'

        self.__updateTable()

        if 'gameCount' in games:
            self.recent20GamesLabel.setText(
                f"{self.tr('Recent matches')} {self.tr('(Last')} {len(games['games'])} {self.tr('games)')}"
            )
            self.winsLabel.setText(f"{self.tr('Wins:')} {games['wins']}")
            self.lossesLabel.setText(f"{self.tr('Losses:')} {games['losses']}")

            kda = f"{self.tr('KDA:')} {games['kills']} / {games['deaths']} / {games['assists']} "
            kda += self.tr("(")
            kda += f"{(games['kills'] + games['assists']) / (1 if games['deaths'] == 0 else games['deaths']):.1f}"
            kda += self.tr(")")

            self.kdaLabel.setText(kda)

        else:
            self.recent20GamesLabel.setText(
                f"{self.tr('Recent matches')} {self.tr('(Last')} None {self.tr('games)')}"
            )
            self.winsLabel.setText(f"{self.tr('Wins:')} 0")
            self.lossesLabel.setText(f"{self.tr('Losses:')} 0")
            self.kdaLabel.setText(
                f"{self.tr('KDA:')} 0 / 0 / 0 " + self.tr("(") + "0" + self.tr(")"))

        self.games = games

        self.__updateGameInfo()

        self.backToMeButton.setEnabled(not self.isLoginSummoner())

        if 'champions' in info:
            self.championsCard.updateChampions(info['champions'])

        self.setLoadingPageEnabled(False)

        if self.games:
            asyncio.create_task(self.__updateRecentTeammates())

    def __updateGameInfo(self):
        for i in reversed(range(self.gameInfoLayout.count())):
            item = self.gameInfoLayout.itemAt(i)
            self.gameInfoLayout.removeItem(item)

            if item.widget():
                item.widget().deleteLater()

        if 'gameCount' in self.games:

            for bar in [self.__makeGameInfoBar(game)
                        for game in self.games['games']]:
                bar.setMaximumHeight(86)
                self.gameInfoLayout.addWidget(bar)
                self.gameInfoLayout.addSpacing(5)

            self.gameInfoLayout.addSpacerItem(
                QSpacerItem(1, 1, QSizePolicy.Minimum, QSizePolicy.Expanding))

    def __makeGameInfoBar(self, game: dict) -> 'GameInfoBar':
        """创建战绩卡片, 若评级缓存命中则附加当前召唤师的档位徽章."""
        grade = None
        gradeLabel = ''
        gradeEvidence = []
        isCurrent = False
        try:
            if cfg.get(cfg.enableTeamRating):
                from app.lol.war_criminal_cache import getTeamRating
                # 判断当前召唤师所在队是胜方还是败方
                isWin = bool(game.get('win'))
                ratingList = getTeamRating(game.get('gameId'), isWin)
                if not ratingList:
                    # 缓存未命中或胜败方判断错误时尝试另一队
                    ratingList = getTeamRating(game.get('gameId'), not isWin)
                if ratingList:
                    # 找到当前召唤师的评级项
                    currentPuuid = self.puuid
                    for r in ratingList:
                        if r.get('puuid') == currentPuuid:
                            grade = r.get('grade')
                            gradeLabel = r.get('label', '')
                            gradeEvidence = r.get('evidence') or []
                            isCurrent = True
                            break
        except Exception:
            pass

        return GameInfoBar(game, grade=grade, gradeLabel=gradeLabel,
                           gradeEvidence=gradeEvidence, isCurrent=isCurrent)

    def __onfilterComboBoxChanged(self, index):
        self.gameInfoArea.delegate.vScrollBar.resetValue(0)
        self.gameInfoArea.verticalScrollBar().setSliderPosition(0)

        items = list(range(self.gameInfoLayout.count()))
        items.reverse()

        for i in items:
            item = self.gameInfoLayout.itemAt(i)
            self.gameInfoLayout.removeItem(item)

            if item.widget():
                item.widget().deleteLater()

        if index == 1:
            targetId = 430
        elif index == 2:
            targetId = 450
        elif index == 3:
            targetId = 2400
        elif index == 4:
            targetId = 420
        elif index == 5:
            targetId = 440
        else:
            targetId = 0

        hitGames, kills, deaths, assists, wins, losses = parseGames(
            self.games.get("games", []), targetId)

        for game in hitGames:
            bar = self.__makeGameInfoBar(game)
            bar.setMaximumHeight(86)
            self.gameInfoLayout.addWidget(bar)
            self.gameInfoLayout.addSpacing(5)

        self.recent20GamesLabel.setText(
            f"{self.tr('Recent matches')} {self.tr('(Last')} {len(hitGames)} {self.tr('games)')}"
        )
        self.winsLabel.setText(f"{self.tr('Wins:')} {wins}")
        self.lossesLabel.setText(f"{self.tr('Losses:')} {losses}")
        kda = f"{self.tr('KDA:')} {kills} / {deaths} / {assists}"
        kda += self.tr("(")
        kda += f"{(kills + assists) / (1 if deaths == 0 else deaths):.1f}"
        kda += self.tr(")")
        self.kdaLabel.setText(kda)

        self.gameInfoLayout.addSpacerItem(
            QSpacerItem(1, 1, QSizePolicy.Minimum, QSizePolicy.Expanding))

    def setLoginSummonerPuuid(self, name):
        self.loginSummonerPuuid = name

    def getSummonerName(self):
        if self.showTagLine:
            res = f'{self.name.text()}{self.tagLineLabel.text()}'
        else:
            res = self.name.text()

        return res

    def isLoginSummoner(self):
        return self.loginSummonerPuuid is None or self.loginSummonerPuuid == self.puuid

    def __onRecentTeammatesButtonClicked(self):
        view = TeammatesFlyOut()

        if self.recentTeammatesInfo:
            view.setLoadingPageEnabled(False)
            view.updateSummoners(self.recentTeammatesInfo)

        self.recentTeammatesFlyout = Flyout.make(
            view, self.recentTeamButton, self, FlyoutAnimationType.DROP_DOWN)
        self.recentTeammatesFlyout.closed.connect(
            self.__resetRecentTeammatesFlyout)

    def __resetRecentTeammatesFlyout(self):
        self.recentTeammatesFlyout = None

    async def __updateRecentTeammates(self):
        self.recentTeammatesInfo = await getRecentTeammates(self.games['games'], self.puuid)

        if self.recentTeammatesFlyout:
            self.recentTeammatesFlyout.close()
            self.__onRecentTeammatesButtonClicked()


class TeammatesFlyOut(FlyoutViewBase):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.vBoxLayout = QVBoxLayout(self)
        self.stackedWidget = QStackedWidget()

        self.loadingPageWidget = QWidget()
        self.infoPageWidget = QWidget()

        self.loadingVBoxLayout = QVBoxLayout(self.loadingPageWidget)
        self.infopageVBoxLayout = QVBoxLayout(self.infoPageWidget)

        self.processRing = IndeterminateProgressRing()

        self.__initLayout()

    def __initLayout(self):
        self.vBoxLayout.setContentsMargins(0, 0, 0, 0)
        self.loadingVBoxLayout.addWidget(
            self.processRing, alignment=Qt.AlignCenter)

        self.vBoxLayout.addWidget(self.stackedWidget)

        self.stackedWidget.addWidget(self.loadingPageWidget)
        self.stackedWidget.addWidget(self.infoPageWidget)

        self.stackedWidget.setFixedHeight(352)
        self.stackedWidget.setFixedWidth(490)

    def clear(self):
        for i in reversed(range(self.infopageVBoxLayout.count())):
            item = self.infopageVBoxLayout.itemAt(i)
            self.infopageVBoxLayout.removeItem(item)

            if item.widget():
                item.widget().deleteLater()

    def updateSummoners(self, info):
        for summoner in info['summoners']:
            infoBar = TeammateInfoBar(summoner)
            self.infopageVBoxLayout.addWidget(infoBar, stretch=1)

        length = len(info['summoners'])
        spacing = self.infopageVBoxLayout.spacing()

        if length < 5:
            self.infopageVBoxLayout.addStretch(5 - length)
            self.infopageVBoxLayout.addSpacing(spacing * (5 - length))

    def setLoadingPageEnabled(self, enable):
        index = 0 if enable else 1
        self.stackedWidget.setCurrentIndex(index)


class TeammateInfoBar(ColorAnimationFrame):
    # closed = pyqtSignal()

    def __init__(self, summoner, parent=None):
        super().__init__(type='default', parent=parent)
        self._pressedBackgroundColor = self._hoverBackgroundColor

        self.hBoxLayout = QHBoxLayout(self)

        self.icon = RoundIcon(summoner['icon'], 40, 4, 4)
        self.name = SummonerName(summoner['name'])

        self.totalTitle = QLabel(self.tr("Total: "))
        self.totalLabel = QLabel(str(summoner["total"]))
        self.winsTitle = QLabel(self.tr("Wins: "))
        self.winsLabel = ColorLabel(str(summoner['wins']), 'win')
        self.lossesTitle = QLabel(self.tr("Losses: "))
        self.lossesLabel = ColorLabel(str(summoner['losses']), 'lose')

        self.__initWidget()
        self.__initLayout()

        self.setFixedHeight(62)

        self.name.clicked.connect(
            lambda: signalBus.toCareerInterface.emit(summoner['puuid']))

    def __initWidget(self):
        self.name.setFixedWidth(180)
        self.totalLabel.setFixedWidth(40)
        self.winsLabel.setFixedWidth(40)
        self.lossesLabel.setFixedWidth(40)

        self.totalLabel.setObjectName('totalLabel')
        self.winsLabel.setObjectName("winsLabel")
        self.lossesLabel.setObjectName("lossesLabel")

        self.totalTitle.setAlignment(Qt.AlignCenter)
        self.totalLabel.setAlignment(Qt.AlignCenter)
        self.winsTitle.setAlignment(Qt.AlignCenter)
        self.winsLabel.setAlignment(Qt.AlignCenter)
        self.lossesTitle.setAlignment(Qt.AlignCenter)
        self.lossesLabel.setAlignment(Qt.AlignCenter)

    def __initLayout(self):
        self.hBoxLayout.addWidget(self.icon)
        self.hBoxLayout.addWidget(self.name)
        self.hBoxLayout.addWidget(self.totalTitle)
        self.hBoxLayout.addWidget(self.totalLabel)
        self.hBoxLayout.addWidget(self.winsTitle)
        self.hBoxLayout.addWidget(self.winsLabel)
        self.hBoxLayout.addWidget(self.lossesTitle)
        self.hBoxLayout.addWidget(self.lossesLabel)


class ChampionsCard(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.hBoxLayout = QHBoxLayout(self)
        self.hBoxLayout.setContentsMargins(0, 0, 0, 0)

        self.setFixedHeight(33)

    def updateChampions(self, champions):
        self.clear()

        for champion in champions:
            icon = RoundIcon(champion['icon'], 28, 2, 2)

            toolTip = self.tr("Total: ") + str(champion['total']) + "   "
            toolTip += self.tr("Wins: ") + str(champion['wins']) + "   "
            toolTip += self.tr("Losses: ") + str(champion['losses']) + "   "
            toolTip += self.tr("Win Rate: ")
            toolTip += ("100" if champion['losses'] == 0 else "{:.2f}".format(
                champion['wins'] * 100 / (champion['wins'] + champion['losses']))) + "%"
            icon.setToolTip(toolTip)
            icon.installEventFilter(
                ToolTipFilter(icon, 0, ToolTipPosition.TOP))

            self.hBoxLayout.addWidget(icon, alignment=Qt.AlignCenter)

    def clear(self):
        for i in reversed(range(self.hBoxLayout.count())):
            item = self.hBoxLayout.itemAt(i)
            self.hBoxLayout.removeItem(item)

            if item.widget():
                item.widget().deleteLater()
