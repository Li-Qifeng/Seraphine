# coding:utf-8
import os

from app.common.qfluentwidgets import (SettingCardGroup, SwitchSettingCard, ComboBoxSettingCard,
                                       PushSettingCard, InfoBar,
                                       setTheme, PrimaryPushSettingCard, HyperlinkCard,
                                       TeachingTip, TeachingTipTailPosition, TeachingTipView, PushButton)
from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QDesktopServices

from app.common.icons import Icon
from app.common.config import (cfg, YEAR, AUTHOR, VERSION, FEEDBACK_URL, GITHUB_URL, isWin11,
                               BETA)
from app.common.style_sheet import StyleSheet
from app.components.seraphine_interface import SeraphineInterface
from app.components.setting_cards import (LineEditSettingCard, GameTabColorSettingCard,
                                          LooseSwitchSettingCard, ProxySettingCard,
                                          DeathsNumberColorSettingCard, ThemeColorSettingCard,
                                          QueueFilterCard, TeamColorSettingCard)
from app.components.message_box import MultiPathSettingMsgBox


class SettingInterface(SeraphineInterface):
    """ Setting interface """

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self._initCommon(self.tr("Settings"), StyleSheet.SETTING_INTERFACE)
        # setting_interface.qss 使用 #settingLabel, 保留兼容
        self.titleLabel.setObjectName('settingLabel')
        self.settingLabel = self.titleLabel

        self.personalizationGroup = SettingCardGroup(
            self.tr("个性化"), self.scrollWidget)

        self.generalGroup = SettingCardGroup(self.tr("通用"),
                                             self.scrollWidget)

        self.gameFuncGroup = SettingCardGroup(self.tr("游戏功能"),
                                              self.scrollWidget)

        self.aboutGroup = SettingCardGroup(self.tr("关于"),
                                           self.scrollWidget)

        # --- 通用组卡片 ---
        self.lolFolderCard = PushSettingCard(self.tr("Choose folder"),
                                             Icon.FOLDER,
                                             self.tr("Client Path"),
                                             self.tr(
                                                 "Set client path and order"),
                                             self.generalGroup)
        self.lolFolderCard.button.setFixedWidth(100)
        self.lolFolderCard.button.setStyleSheet(
            "QPushButton {padding-left: 0; padding-right: 0;}")

        self.enableStartLolWithApp = SwitchSettingCard(
            Icon.CIRCLERIGHT,
            self.tr("Auto-start LOL"),
            self.tr("Launch LOL client upon opening Seraphine automatically"),
            configItem=cfg.enableStartLolWithApp,
            parent=self.generalGroup)

        self.enableCloseToTray = LooseSwitchSettingCard(
            Icon.EXIT,
            self.tr("Minimize to tray on close"),
            self.tr("Minimize to system tray when clicking close"),
            configItem=cfg.enableCloseToTray,
            parent=self.generalGroup)

        self.silentCard = SwitchSettingCard(
            Icon.SNOOZE, self.tr("Silently start"),
            self.tr(
                "Show Seraphine window minimized when it starts"),
            cfg.enableSilent,
            parent=self.generalGroup)

        self.deleteResourceCard = PushSettingCard(
            self.tr("Delete"), Icon.DELETE, self.tr("Delete cache"),
            self.
            tr("Delete all game resources (Apply it when game resources update)"
               ), self.generalGroup)

        self.deleteResourceCard.button.setFixedWidth(100)
        self.deleteResourceCard.button.setStyleSheet(
            "QPushButton {padding-left: 0; padding-right: 0;}")

        self.apiConcurrencyCount = LineEditSettingCard(
            cfg.apiConcurrencyNumber,
            self.tr("LCU API concurrency number"),
            self.tr("Number of concurrency:"),
            1, 1, 20,
            Icon.APPLIST,
            self.tr("Setting the maximum number of API concurrency."),
            self.generalGroup)

        self.careerGamesCount = LineEditSettingCard(
            cfg.careerGamesNumber,
            self.tr("Default games number"),
            self.tr("Number of games:"),
            10, 10, 100,
            Icon.SLIDESEARCH,
            self.tr(
                "Setting the maximum number of games shows in the career interface"),
            self.generalGroup)

        # --- 游戏功能组卡片 ---
        self.queueFilterCard = QueueFilterCard(
            self.tr("Game Infomation filter"),
            self.tr(
                "Show game modes in Game Infomation interface based on your current game mode"),
            cfg.queueFilter,
            parent=self.gameFuncGroup
        )

        self.autoClearGameinfoCard = SwitchSettingCard(
            Icon.ATTACHTEXT, self.tr("Reserve Game Information interface"),
            self.tr(
                "Reserve Game Information interface until the next champion selection starts"),
            cfg.enableReserveGameinfo,
            parent=self.gameFuncGroup
        )

        self.gameInfoShowTierCard = SwitchSettingCard(
            Icon.TROPHY, self.tr("Show tier in game information"),
            self.tr(
                "Show tier icon in game information interface. Enabling this option affects APP's performance"),
            cfg.showTierInGameInfo,
            parent=self.gameFuncGroup)

        self.autoShowOpggCard = SwitchSettingCard(
            Icon.WINDOW, self.tr("Show OP.GG window automatically"),
            self.tr("Show OP.GG window automatically when champion selection starts"),
            cfg.autoShowOpgg,
            parent=self.gameFuncGroup)
        self.opggOnTopCard = SwitchSettingCard(
            Icon.PADDINGTOP, self.tr(
                "Show OP.GG window on top"),
            self.tr(
                "Show OP.GG window in front of other windows while selecting champions"),
            cfg.enableOpggOnTop,
            parent=self.gameFuncGroup)
        self.enableWarCriminalCard = SwitchSettingCard(
            Icon.TROPHY, self.tr("War criminal diagnosis"),
            self.tr(
                "Identify the worst performer on each team (war criminal / carried dog) based on in-game stats"),
            cfg.enableWarCriminal,
            parent=self.gameFuncGroup)
        self.warCriminalSensitivityCard = ComboBoxSettingCard(
            cfg.warCriminalSensitivity,
            Icon.SCALEFIT,
            self.tr("War criminal sensitivity"),
            self.tr(
                "Loose: easier to flag; Normal: balanced; Strict: only obvious cases"),
            texts=[self.tr("Loose"), self.tr("Normal"), self.tr("Strict")],
            parent=self.gameFuncGroup)

        # --- 个性化组卡片 ---
        self.micaCard = SwitchSettingCard(
            Icon.BLUR,
            self.tr('Mica effect'),
            self.tr(
                'Apply semi transparent to windows and surfaces (only available on Win11)'),
            cfg.micaEnabled,
            self.personalizationGroup
        )
        self.themeCard = ComboBoxSettingCard(
            cfg.themeMode,
            Icon.BRUSH,
            self.tr("Application theme"),
            self.tr("Change the appearance of Seraphine"),
            texts=[
                self.tr("Light"),
                self.tr("Dark"),
                self.tr("Use system setting")
            ],
            parent=self.personalizationGroup)
        self.themeColorCard = ThemeColorSettingCard(
            self.tr("Theme color"), self.tr(
                "Change the theme color of Seraphine"),
            cfg.themeColor, self.personalizationGroup)
        self.gameTabColorSettingCard = GameTabColorSettingCard(
            self.tr("Game tabs color"),
            self.tr("Change the color of game tabs"),
            cfg.winCardColor, cfg.loseCardColor, cfg.remakeCardColor,
            self.personalizationGroup
        )
        self.deathNumberColorSettingCard = DeathsNumberColorSettingCard(
            self.tr("Deaths number color"),
            self.tr("Change the color of Deaths number of KDA"),
            cfg.lightDeathsNumberColor, cfg.darkDeathsNumberColor,
            self.personalizationGroup
        )
        self.teamColorSettingCard = TeamColorSettingCard(
            self.tr("Team color"),
            self.tr("Change the highlight color of premade teams in game info"),
            cfg.team1Color, cfg.team2Color,
            self.personalizationGroup
        )
        self.zoomCard = ComboBoxSettingCard(
            cfg.dpiScale,
            Icon.ZOOMFIT,
            self.tr("Interface zoom"),
            self.tr("Change the size of widgets and fonts"),
            texts=[
                "100%", "125%", "150%", "175%", "200%",
                self.tr("Use system setting")
            ],
            parent=self.personalizationGroup)
        self.languageCard = ComboBoxSettingCard(
            cfg.language,
            Icon.LANGUAGE,
            self.tr('Language'),
            self.tr('Set your preferred language for Seraphine'),
            texts=['简体中文', 'English',
                   self.tr('Use system setting')],
            parent=self.personalizationGroup)

        # --- 关于组卡片 ---
        self.checkUpdateCard = SwitchSettingCard(
            Icon.UPDATE, self.tr("Check for updates"),
            self.tr(
                "Automatically check for updates when software starts"),
            cfg.enableCheckUpdate,
            parent=self.aboutGroup)

        self.httpProxyCard = ProxySettingCard(
            self.tr("HTTP proxy"), self.tr(
                "Using a proxy when connecting to GitHub"),
            cfg.enableProxy, cfg.proxyAddr, self.aboutGroup)

        self.logLevelCard = ComboBoxSettingCard(
            cfg.logLevel,
            Icon.LOG,
            self.tr('Log Level'),
            self.tr('The level of logging for Seraphine (take effect after restart)'),
            texts=["Debug", "Info", "Warning", "Error"],
            parent=self.aboutGroup)

        self.viewLogCard = PushSettingCard(
            self.tr("Open"), Icon.DOCUMENT, self.tr("Log file"),
            self.
            tr("Open log directory"),
            self.aboutGroup)
        self.viewLogCard.button.setFixedWidth(100)
        # 这玩意左右 padding 大的离谱，手动给它改了
        self.viewLogCard.button.setStyleSheet(
            "QPushButton {padding-left: 0; padding-right: 0;}")

        self.feedbackCard = PrimaryPushSettingCard(
            self.tr('Provide feedback'), Icon.FEEDBACK,
            self.tr('Provide feedback'),
            self.tr('Help us improve Seraphine by providing feedback'),
            self.aboutGroup)

        # 让它和上面的按钮宽度一样，看起来顺眼点
        self.feedbackCard.button.setFixedWidth(100)

        self.aboutCard = HyperlinkCard(
            GITHUB_URL, self.tr("View GitHub"), Icon.INFO, self.tr('About'),
            self.tr('Copyright') + ' © ' + f"{YEAR}, {AUTHOR}. " +
            self.tr('Version') + f" {BETA or VERSION}", self.aboutGroup)
        self.aboutCard.linkButton.setIcon(Icon.GITHUB)

        self.__initWidget()

    def __initWidget(self):
        self.resize(1000, 800)
        self.micaCard.switchButton.setEnabled(isWin11())
        self.__initLayout()
        self.__connectSignalToSlot()

    def __initLayout(self):
        # 个性化组
        self.personalizationGroup.addSettingCard(self.micaCard)
        self.personalizationGroup.addSettingCard(self.themeCard)
        self.personalizationGroup.addSettingCard(self.themeColorCard)
        self.personalizationGroup.addSettingCard(self.gameTabColorSettingCard)
        self.personalizationGroup.addSettingCard(
            self.deathNumberColorSettingCard)
        self.personalizationGroup.addSettingCard(self.teamColorSettingCard)
        self.personalizationGroup.addSettingCard(self.zoomCard)
        self.personalizationGroup.addSettingCard(self.languageCard)

        # 通用组
        self.generalGroup.addSettingCard(self.lolFolderCard)
        self.generalGroup.addSettingCard(self.enableStartLolWithApp)
        self.generalGroup.addSettingCard(self.enableCloseToTray)
        self.generalGroup.addSettingCard(self.silentCard)
        self.generalGroup.addSettingCard(self.deleteResourceCard)
        self.generalGroup.addSettingCard(self.apiConcurrencyCount)
        self.generalGroup.addSettingCard(self.careerGamesCount)

        # 游戏功能组
        self.gameFuncGroup.addSettingCard(self.queueFilterCard)
        self.gameFuncGroup.addSettingCard(self.autoClearGameinfoCard)
        self.gameFuncGroup.addSettingCard(self.gameInfoShowTierCard)
        self.gameFuncGroup.addSettingCard(self.autoShowOpggCard)
        self.gameFuncGroup.addSettingCard(self.opggOnTopCard)
        self.gameFuncGroup.addSettingCard(self.enableWarCriminalCard)
        self.gameFuncGroup.addSettingCard(self.warCriminalSensitivityCard)

        # 关于组
        self.aboutGroup.addSettingCard(self.checkUpdateCard)
        self.aboutGroup.addSettingCard(self.httpProxyCard)
        self.aboutGroup.addSettingCard(self.logLevelCard)
        self.aboutGroup.addSettingCard(self.viewLogCard)
        self.aboutGroup.addSettingCard(self.feedbackCard)
        self.aboutGroup.addSettingCard(self.aboutCard)

        # add setting card group to layout
        self.expandLayout.setSpacing(30)
        self.expandLayout.setContentsMargins(36, 0, 36, 0)
        self.expandLayout.addWidget(self.personalizationGroup)
        self.expandLayout.addWidget(self.generalGroup)
        self.expandLayout.addWidget(self.gameFuncGroup)
        self.expandLayout.addWidget(self.aboutGroup)

    def __connectSignalToSlot(self):
        self.lolFolderCard.clicked.connect(self.__onLolFolderCardClicked)

        self.themeCard.comboBox.currentIndexChanged.connect(
            lambda: setTheme(cfg.get(cfg.themeMode)))

        cfg.appRestartSig.connect(self.__showRestartToolTip)
        self.careerGamesCount.pushButton.clicked.connect(
            self.__showUpdatedSuccessfullyToolTip)
        self.feedbackCard.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(FEEDBACK_URL)))
        self.deleteResourceCard.clicked.connect(self.__showFlyout)
        self.viewLogCard.clicked.connect(
            lambda: os.system(f'explorer {os.getcwd()}\\log')
        )

    def __onLolFolderCardClicked(self):
        current = cfg.get(cfg.lolFolder)

        msgBox = MultiPathSettingMsgBox(current, self.window())
        msgBox.exec_()

    def __showRestartToolTip(self):
        InfoBar.success(self.tr("Updated successfully"),
                        self.tr("Configuration takes effect after restart"),
                        duration=2000,
                        parent=self)

    def __showUpdatedSuccessfullyToolTip(self):
        InfoBar.success(self.tr("Updated successfully"),
                        self.tr("Settings have been applied"),
                        duration=2000,
                        parent=self)

    def __onDeleteButtonClicked(self):
        folders = [
            'champion icons', 'item icons', 'profile icons', 'rune icons',
            'summoner spell icons', "augment icons"
        ]

        for folder in folders:
            path = f'app/resource/game/{folder}'

            if not os.path.exists(path):
                continue

            for file in os.listdir(path):
                filePath = f"{path}/{file}"

                if not os.path.exists(filePath):
                    continue

                os.remove(filePath)

    def __showFlyout(self):
        view = TeachingTipView(
            title=self.tr("Really?"),
            content=self.
            tr("Game resources will be downloaded again\nwhen they are used by Seraphine, which will cost more time"
               ),
            isClosable=True,
            tailPosition=TeachingTipTailPosition.RIGHT)

        applyButton = PushButton(self.tr('Confirm delete'))

        view.widgetLayout.insertSpacing(1, 10)
        view.widgetLayout.addSpacing(10)
        view.addWidget(applyButton, align=Qt.AlignRight)

        t = TeachingTip.make(
            view,
            self.deleteResourceCard.button,
            -1,
            TeachingTipTailPosition.RIGHT,
            self,
        )

        applyButton.clicked.connect(self.__onDeleteButtonClicked)
        view.closed.connect(t.close)
