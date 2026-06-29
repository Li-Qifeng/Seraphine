from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QLabel, QHBoxLayout, QGridLayout
from qasync import asyncSlot
from app.common.icons import Icon
from app.common.qfluentwidgets import SettingCard, LineEdit, PushButton, ComboBox, InfoBar, InfoBarPosition, ExpandGroupSettingCard, Flyout, FlyoutAnimationType, MessageBox
from app.components.multi_champion_select import ChampionSelectFlyout, SplashesFlyout
from app.lol.connector import connector


class OnlineStatusCard(ExpandGroupSettingCard):
    def __init__(self, title, content, parent=None):
        super().__init__(Icon.COMMENT, title, content, parent)

        self.inputWidget = QWidget(self.view)
        self.inputLayout = QHBoxLayout(self.inputWidget)
        self.statusLabel = QLabel(
            self.tr("Online status you want to change to:"))
        self.lineEdit = LineEdit()

        self.buttonWidget = QWidget()
        self.buttonLayout = QHBoxLayout(self.buttonWidget)
        self.pushButton = PushButton(self.tr("Apply"), self)

        self.__initLayout()
        self.__initWidget()

    def __initLayout(self):
        self.inputLayout.setSpacing(19)
        self.inputLayout.setAlignment(Qt.AlignTop)
        self.inputLayout.setContentsMargins(48, 18, 44, 18)

        self.inputLayout.addWidget(
            self.statusLabel, alignment=Qt.AlignLeft)
        self.inputLayout.addWidget(self.lineEdit, alignment=Qt.AlignRight)
        self.inputLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.buttonLayout.setContentsMargins(48, 18, 44, 18)
        self.buttonLayout.addWidget(self.pushButton, 0, Qt.AlignRight)
        self.buttonLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.viewLayout.setSpacing(0)
        self.viewLayout.setContentsMargins(0, 0, 0, 0)
        self.addGroupWidget(self.inputWidget)
        self.addGroupWidget(self.buttonWidget)

    def __initWidget(self):
        self.lineEdit.setMinimumWidth(250)
        self.lineEdit.setPlaceholderText(self.tr("Please input your status"))

        self.pushButton.setMinimumWidth(100)
        self.pushButton.clicked.connect(self.__onPushButtonClicked)

    @asyncSlot()
    async def __onPushButtonClicked(self):
        msg = self.lineEdit.text()
        await connector.setOnlineStatus(msg)

    def clear(self):
        self.lineEdit.clear()

class ProfileBackgroundCard(ExpandGroupSettingCard):

    def __init__(self, title, content, parent):
        super().__init__(Icon.VIDEO_PERSON, title, content, parent)

        self.inputWidget = QWidget(self.view)
        self.inputLayout = QGridLayout(self.inputWidget)

        self.championLabel = QLabel(self.tr("Champion's name: "))
        self.championButton = PushButton(self.tr("Select champion"), self)

        self.skinLabel = QLabel(self.tr("Skin's name: "))
        self.skinButton = PushButton(self.tr("Select Skin"), self)

        self.buttonWidget = QWidget(self.view)
        self.buttonLayout = QHBoxLayout(self.buttonWidget)
        self.pushButton = PushButton(self.tr("Apply"))

        self.completer = None

        self.chosenSkinId = None
        self.skins = None

        self.__initLayout()
        self.__initWidget()

    def __initLayout(self):
        self.inputLayout.setVerticalSpacing(19)
        self.inputLayout.setAlignment(Qt.AlignTop)
        self.inputLayout.setContentsMargins(48, 18, 44, 18)

        self.inputLayout.addWidget(
            self.championLabel, 0, 0, alignment=Qt.AlignLeft)
        self.inputLayout.addWidget(
            self.championButton, 0, 1, alignment=Qt.AlignRight)

        self.inputLayout.addWidget(
            self.skinLabel, 1, 0, alignment=Qt.AlignLeft)
        self.inputLayout.addWidget(
            self.skinButton, 1, 1, alignment=Qt.AlignRight)

        self.inputLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.buttonLayout.setContentsMargins(48, 18, 44, 18)
        self.buttonLayout.addWidget(self.pushButton, 0, Qt.AlignRight)
        self.buttonLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.viewLayout.setSpacing(0)
        self.viewLayout.setContentsMargins(0, 0, 0, 0)
        self.addGroupWidget(self.inputWidget)
        self.addGroupWidget(self.buttonWidget)

    def __initWidget(self):
        self.championButton.setMinimumWidth(100)
        self.championButton.clicked.connect(self.__onSelectButtonClicked)

        self.skinButton.setMinimumWidth(100)
        self.skinButton.setEnabled(False)
        self.skinButton.clicked.connect(self.__onSkinButtonClicked)

        self.pushButton.setMinimumWidth(100)
        self.pushButton.setEnabled(False)
        self.pushButton.clicked.connect(self.__onApplyButtonClicked)

    def __onSelectButtonClicked(self):
        view = ChampionSelectFlyout(self.champions)
        view.championSelected.connect(self.__onChampionSelected)

        self.w = Flyout.make(view, self.championButton,
                             self, FlyoutAnimationType.SLIDE_RIGHT, True)

    def __onSkinButtonClicked(self):
        view = SplashesFlyout(self.skins, self.chosenSkinId)
        view.skinWidget.selectedChanged.connect(self.__onSkinSelectedChanged)

        Flyout.make(view, self.skinButton, self,
                    FlyoutAnimationType.SLIDE_RIGHT, True)

    def __onSkinSelectedChanged(self, skinId, name):
        self.chosenSkinId = skinId
        self.skinLabel.setText(self.tr("Skin's name: ") + name)

    async def initChampionList(self, champions: dict = None):
        if champions:
            self.champions = champions
        else:
            self.champions = {
                i: [name, await connector.getChampionIcon(i)]
                for i, name in connector.manager.getChampions().items()
                if i != -1
            }

        return self.champions

    def __onChampionSelected(self, championId):
        self.w.fadeOut()
        self.championLabel.setText(self.tr(
            "Champion's name: ") + connector.manager.getChampionNameById(championId))
        self.skinLabel.setText(self.tr("Skin's name: "))
        self.chosenSkinId = None

        name = self.champions[championId][0]
        self.skins = connector.manager.getSkinListByChampionName(name)

        self.skinButton.clicked.emit()

        self.skinButton.setEnabled(True)
        self.pushButton.setEnabled(True)

    @asyncSlot()
    async def __onApplyButtonClicked(self):
        contentId = connector.manager.getSkinAugments(self.chosenSkinId)

        if contentId is None:
            await connector.setProfileBackground(self.chosenSkinId)
            return

        self.skinId = self.chosenSkinId
        self.contentId = contentId

        msg = MessageBox(
            self.tr("This skin has a Signed Version"),
            self.tr("Setting to the signed version will restart the client."),
            self.window())

        msg.accepted.connect(self.__onMsgBoxYesButtonClicked)
        msg.rejected.connect(self.__onMsgBoxNoButtonClicked)

        msg.yesButton.setText(self.tr("Signed Version"))
        msg.cancelButton.setText(self.tr("Unsigned Version"))

        msg.exec_()

        InfoBar.success(title=self.tr("Apply"), content=self.tr("Successfully"),
                        orient=Qt.Vertical, isClosable=True,
                        position=InfoBarPosition.TOP_RIGHT, duration=5000,
                        parent=self.window().auxiliaryFuncInterface)

    @asyncSlot()
    async def __onMsgBoxYesButtonClicked(self):
        await connector.setProfileBackground(self.skinId)
        await connector.setProfileBackgroundAugments(self.contentId)
        await connector.restartClient()

    @asyncSlot()
    async def __onMsgBoxNoButtonClicked(self):
        await connector.setProfileBackground(self.skinId)

class ProfileTierCard(ExpandGroupSettingCard):

    def __init__(self, title, content, parent):
        super().__init__(Icon.CERTIFICATE, title, content, parent)
        self.inputWidget = QWidget(self.view)
        self.inputLayout = QGridLayout(self.inputWidget)

        self.rankModeLabel = QLabel(self.tr("Game mode:"))
        self.rankModeBox = ComboBox()
        self.tierLabel = QLabel(self.tr("Tier:"))
        self.tierBox = ComboBox()
        self.divisionLabel = QLabel(self.tr("Division:"))
        self.divisionBox = ComboBox()

        self.buttonWidget = QWidget(self.view)
        self.buttonLayout = QHBoxLayout(self.buttonWidget)
        self.pushButton = PushButton(self.tr("Apply"))

        self.__initLayout()
        self.__initWidget()

    def __initLayout(self):
        self.inputLayout.setVerticalSpacing(19)
        self.inputLayout.setAlignment(Qt.AlignTop)
        self.inputLayout.setContentsMargins(48, 18, 44, 18)

        self.inputLayout.addWidget(
            self.rankModeLabel, 0, 0, alignment=Qt.AlignLeft)
        self.inputLayout.addWidget(
            self.rankModeBox, 0, 1, alignment=Qt.AlignRight)

        self.inputLayout.addWidget(
            self.tierLabel, 1, 0, alignment=Qt.AlignLeft)
        self.inputLayout.addWidget(
            self.tierBox, 1, 1, alignment=Qt.AlignRight)

        self.inputLayout.addWidget(
            self.divisionLabel, 2, 0, alignment=Qt.AlignLeft)
        self.inputLayout.addWidget(
            self.divisionBox, 2, 1, alignment=Qt.AlignRight)

        self.inputLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.buttonLayout.setContentsMargins(48, 18, 44, 18)
        self.buttonLayout.addWidget(self.pushButton, 0, Qt.AlignRight)
        self.buttonLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.viewLayout.setSpacing(0)
        self.viewLayout.setContentsMargins(0, 0, 0, 0)
        self.addGroupWidget(self.inputWidget)
        self.addGroupWidget(self.buttonWidget)

    def __initWidget(self):
        self.rankModeBox.addItems([
            self.tr("Teamfight Tactics"),
            self.tr("Ranked solo"),
            self.tr("Ranked flex")
        ])
        self.tierBox.addItems([
            self.tr('Na'),
            self.tr('Iron'),
            self.tr('Bronze'),
            self.tr('Silver'),
            self.tr('Gold'),
            self.tr('Platinum'),
            self.tr('Emerald'),
            self.tr('Diamond'),
            self.tr('Master'),
            self.tr('Grandmaster'),
            self.tr('Challenger')
        ])
        self.divisionBox.addItems(['I', 'II', 'III', 'IV'])

        self.rankModeBox.setPlaceholderText(self.tr("Please select game mode"))
        self.tierBox.setPlaceholderText(self.tr("Please select Tier"))
        self.divisionBox.setPlaceholderText(self.tr("Please select Division"))

        self.pushButton.setEnabled(False)

        self.rankModeBox.setMinimumWidth(250)
        self.tierBox.setMinimumWidth(250)
        self.divisionBox.setMinimumWidth(250)
        self.pushButton.setMinimumWidth(100)

        self.rankModeBox.currentTextChanged.connect(
            self.__onRankModeTextChanged)
        self.tierBox.currentTextChanged.connect(self.__onTierTextChanged)
        self.divisionBox.currentTextChanged.connect(
            self.__setPushButtonAvailability)
        self.pushButton.clicked.connect(self.__onPushButtonClicked)

    def clear(self):
        self.rankModeBox.setCurrentIndex(0)
        self.tierBox.setCurrentIndex(0)
        self.divisionBox.setCurrentIndex(0)

        self.rankModeBox.setPlaceholderText(self.tr("Game mode"))
        self.tierBox.setPlaceholderText(self.tr("Tier"))
        self.divisionBox.setPlaceholderText(self.tr("Division"))

    def __onRankModeTextChanged(self):
        currentText = self.tierBox.currentText()
        self.tierBox.clear()
        if self.rankModeBox.currentIndex() == 0:
            self.tierBox.addItems([
                self.tr('Na'),
                self.tr('Iron'),
                self.tr('Bronze'),
                self.tr('Silver'),
                self.tr('Gold'),
                self.tr('Platinum'),
                self.tr('Diamond'),
                self.tr('Master'),
                self.tr('Grandmaster'),
                self.tr('Challenger')
            ])

            if currentText != self.tr('Emerald'):
                self.tierBox.setCurrentText(currentText)
            else:
                self.tierBox.setPlaceholderText(self.tr("Tier"))
        else:
            self.tierBox.addItems([
                self.tr('Na'),
                self.tr('Iron'),
                self.tr('Bronze'),
                self.tr('Silver'),
                self.tr('Gold'),
                self.tr('Platinum'),
                self.tr('Emerald'),
                self.tr('Diamond'),
                self.tr('Master'),
                self.tr('Grandmaster'),
                self.tr('Challenger')
            ])

            self.tierBox.setCurrentText(currentText)

        self.__setPushButtonAvailability()

    def __onTierTextChanged(self):
        currentTier = self.tierBox.currentText()
        currentDivision = self.divisionBox.currentText()
        self.divisionBox.clear()
        if currentTier in [
            self.tr("Na"),
            self.tr('Master'),
            self.tr('Grandmaster'),
            self.tr('Challenger')
        ]:
            self.divisionBox.addItems(['--'])
            self.divisionBox.setCurrentText('--')
        else:
            self.divisionBox.addItems(['I', 'II', 'III', 'IV'])
            if currentDivision != '--':
                self.divisionBox.setCurrentText(currentDivision)
            else:
                self.divisionBox.setPlaceholderText("Division")

        self.__setPushButtonAvailability()

    def __setPushButtonAvailability(self):
        rankMode = self.rankModeBox.currentText()
        tier = self.tierBox.currentText()
        division = self.divisionBox.currentText()

        enable = rankMode != '' and tier != '' and division != ''
        self.pushButton.setEnabled(enable)

    @asyncSlot()
    async def __onPushButtonClicked(self):
        queue = {
            self.tr("Teamfight Tactics"): "RANKED_TFT",
            self.tr("Ranked solo"): "RANKED_SOLO_5x5",
            self.tr("Ranked flex"): 'RANKED_FLEX_SR'
        }[self.rankModeBox.currentText()]

        tier = {
            self.tr('Na'): 'UNRANKED',
            self.tr('Iron'): 'IRON',
            self.tr('Bronze'): 'BRONZE',
            self.tr('Silver'): 'SILVER',
            self.tr('Gold'): 'GOLD',
            self.tr('Platinum'): 'PLATINUM',
            self.tr('Emerald'): 'EMERALD',
            self.tr('Diamond'): 'DIAMOND',
            self.tr('Master'): 'MASTER',
            self.tr('Grandmaster'): 'GRANDMASTER',
            self.tr('Challenger'): 'CHALLENGER'
        }[self.tierBox.currentText()]

        currentDivision = self.divisionBox.currentText()
        division = currentDivision if currentDivision != '--' else "NA"

        await connector.setTierShowed(queue, tier, division)

class OnlineAvailabilityCard(ExpandGroupSettingCard):

    def __init__(self, title, content, parent):
        super().__init__(Icon.PERSONAVAILABLE, title, content, parent)

        self.inputWidget = QWidget(self.view)
        self.inputLayout = QHBoxLayout(self.inputWidget)

        self.availabilityLabel = QLabel(
            self.tr("Your online availability will be shown:"))
        self.comboBox = ComboBox()

        self.buttonWidget = QWidget(self.view)
        self.buttonLayout = QHBoxLayout(self.buttonWidget)
        self.pushButton = PushButton(self.tr("Apply"))

        self.__initLayout()
        self.__initWidget()

    def __initWidget(self):
        self.comboBox.setMinimumWidth(130)
        self.pushButton.setMinimumWidth(100)

        self.comboBox.addItems(
            [self.tr("chat"),
             self.tr("away"),
             self.tr("offline")])

        self.comboBox.setPlaceholderText(self.tr("Availability"))
        self.pushButton.setEnabled(False)

        self.comboBox.currentTextChanged.connect(self.__onComboBoxTextChanged)
        self.pushButton.clicked.connect(self.__onPushButttonClicked)

    def __initLayout(self):
        self.inputLayout.setSpacing(19)
        self.inputLayout.setAlignment(Qt.AlignTop)
        self.inputLayout.setContentsMargins(48, 18, 44, 18)

        self.inputLayout.addWidget(
            self.availabilityLabel, alignment=Qt.AlignLeft)
        self.inputLayout.addWidget(self.comboBox, alignment=Qt.AlignRight)
        self.inputLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.buttonLayout.setContentsMargins(48, 18, 44, 18)
        self.buttonLayout.addWidget(self.pushButton, 0, Qt.AlignRight)
        self.buttonLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.viewLayout.setSpacing(0)
        self.viewLayout.setContentsMargins(0, 0, 0, 0)
        self.addGroupWidget(self.inputWidget)
        self.addGroupWidget(self.buttonWidget)

    def clear(self):
        self.comboBox.setPlaceholderText(self.tr("Availability"))
        self.comboBox.setCurrentIndex(0)

    @asyncSlot()
    async def __onPushButttonClicked(self):
        availability = {
            self.tr("chat"): "chat",
            self.tr("away"): "away",
            self.tr("offline"): "offline"
        }[self.comboBox.currentText()]

        await connector.setOnlineAvailability(availability)

    def __onComboBoxTextChanged(self):
        if self.comboBox.currentIndex == -1:
            return

        self.pushButton.setEnabled(True)

class RemoveTokensCard(SettingCard):

    def __init__(self, title, content, parent):
        super().__init__(Icon.STAROFF, title, content, parent)
        self.pushButton = PushButton(self.tr("Remove"))
        self.pushButton.setMinimumWidth(100)

        self.hBoxLayout.addWidget(self.pushButton)
        self.hBoxLayout.addSpacing(16)

        self.pushButton.clicked.connect(self.__onButtonClicked)

    @asyncSlot()
    async def __onButtonClicked(self):
        await connector.removeTokens()

class RemovePrestigeCrestCard(SettingCard):

    def __init__(self, title, content, parent):
        super().__init__(Icon.CIRCLELINE, title, content, parent)
        self.pushButton = PushButton(self.tr("Remove"))
        self.pushButton.setMinimumWidth(100)

        self.hBoxLayout.addWidget(self.pushButton)
        self.hBoxLayout.addSpacing(16)

        self.pushButton.clicked.connect(self.__onButtonClicked)

    @asyncSlot()
    async def __onButtonClicked(self):
        await connector.removePrestigeCrest()
