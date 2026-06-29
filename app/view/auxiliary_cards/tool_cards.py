import os
import stat
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QGridLayout
from qasync import asyncSlot
from app.common.config import cfg
from app.common.icons import Icon
from app.common.qfluentwidgets import SettingCard, LineEdit, PushButton, ComboBox, SwitchButton, IndicatorPosition, InfoBar, InfoBarPosition, ExpandGroupSettingCard
from app.lol.connector import connector
from app.lol.exceptions import *
from app.lol.tools import fixLCUWindowViaExe


class FixClientDpiCard(SettingCard):

    def __init__(self, title, content, parent):
        super().__init__(Icon.SCALEFIT, title, content, parent)
        self.pushButton = PushButton(self.tr("Fix"))
        self.pushButton.setMinimumWidth(100)

        self.hBoxLayout.addWidget(self.pushButton)
        self.hBoxLayout.addSpacing(16)

        self.pushButton.clicked.connect(self.__onButtonClicked)

    @asyncSlot()
    async def __onButtonClicked(self):
        await fixLCUWindowViaExe()

class RestartClientCard(SettingCard):

    def __init__(self, title, content, parent):
        super().__init__(Icon.ARROWREPEAT, title, content, parent)
        self.pushButton = PushButton(self.tr("Restart"))
        self.pushButton.setMinimumWidth(100)

        self.hBoxLayout.addWidget(self.pushButton)
        self.hBoxLayout.addSpacing(16)

        self.pushButton.clicked.connect(self.__onButtonClicked)

    @asyncSlot()
    async def __onButtonClicked(self):
        await connector.restartClient()

class CreatePracticeLobbyCard(ExpandGroupSettingCard):

    def __init__(self, title, content, parent):
        super().__init__(Icon.TEXTEDIT, title, content, parent)

        self.inputWidget = QWidget(self.view)
        self.inputLayout = QVBoxLayout(self.inputWidget)

        self.nameLayout = QHBoxLayout()
        self.nameLabel = QLabel(self.tr("Lobby's name: (cannot be empty)"))
        self.nameLineEdit = LineEdit()

        self.passwordLayout = QHBoxLayout()
        self.passwordLabel = QLabel(
            self.tr("Password: (password will NOT be set if it's empty)"))
        self.passwordLineEdit = LineEdit()

        self.pushButtonWidget = QWidget(self.view)
        self.pushButtonLayout = QHBoxLayout(self.pushButtonWidget)

        self.pushButton = PushButton(self.tr("Create"))

        self.__initLayout()
        self.__initWidget()

    def __initLayout(self):
        self.inputLayout.setSpacing(19)
        self.inputLayout.setAlignment(Qt.AlignTop)
        self.inputLayout.setContentsMargins(48, 18, 44, 18)

        self.nameLayout.setContentsMargins(0, 0, 0, 0)
        self.nameLayout.addWidget(self.nameLabel, alignment=Qt.AlignLeft)
        self.nameLayout.addWidget(self.nameLineEdit, alignment=Qt.AlignRight)

        self.passwordLayout.setContentsMargins(0, 0, 0, 0)
        self.passwordLayout.addWidget(
            self.passwordLabel, alignment=Qt.AlignLeft)
        self.passwordLayout.addWidget(
            self.passwordLineEdit, alignment=Qt.AlignRight)

        self.inputLayout.addLayout(self.nameLayout)
        self.inputLayout.addLayout(self.passwordLayout)
        self.inputLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.pushButtonLayout.setContentsMargins(48, 18, 44, 18)
        self.pushButtonLayout.addWidget(self.pushButton, 0, Qt.AlignRight)
        self.pushButtonLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.viewLayout.setSpacing(0)
        self.viewLayout.setContentsMargins(0, 0, 0, 0)
        self.addGroupWidget(self.inputWidget)
        self.addGroupWidget(self.pushButtonWidget)

    def __initWidget(self):
        self.nameLineEdit.setMinimumWidth(250)
        self.nameLineEdit.setClearButtonEnabled(True)
        self.nameLineEdit.setPlaceholderText(
            self.tr("Please input lobby's name"))

        self.passwordLineEdit.setMinimumWidth(250)
        self.passwordLineEdit.setClearButtonEnabled(True)
        self.passwordLineEdit.setPlaceholderText(
            self.tr("Please input password"))

        self.pushButton.setMinimumWidth(100)
        self.pushButton.setEnabled(False)

        self.nameLineEdit.textChanged.connect(self.__onNameLineEditTextChanged)
        self.pushButton.clicked.connect(self.__onPushButtonClicked)

    def clear(self):
        self.nameLineEdit.clear()
        self.passwordLineEdit.clear()

    def __onNameLineEditTextChanged(self):
        enable = self.nameLineEdit.text() != ""
        self.pushButton.setEnabled(enable)

    @asyncSlot()
    async def __onPushButtonClicked(self):
        name = self.nameLineEdit.text()
        password = self.passwordLineEdit.text()

        await connector.create5v5PracticeLobby(name, password)

class SpectateCard(ExpandGroupSettingCard):
    def __init__(self, title, content=None, parent=None):
        super().__init__(Icon.EYES, title, content, parent)

        self.inputWidget = QWidget(self.view)
        self.inputLayout = QGridLayout(self.inputWidget)

        self.summonerNameLabel = QLabel(
            self.tr("Summoner's name you want to spectate:"))
        self.lineEdit = LineEdit()

        self.spectateTypeLabel = QLabel(self.tr("Method:"))
        self.spectateTypeComboBox = ComboBox()

        self.buttonWidget = QWidget(self.view)
        self.buttonLayout = QHBoxLayout(self.buttonWidget)
        self.button = PushButton(self.tr("Spectate"))

        self.__initLayout()
        self.__initWidget()

    def __initLayout(self):
        self.inputLayout.setVerticalSpacing(19)
        self.inputLayout.setAlignment(Qt.AlignTop)
        self.inputLayout.setContentsMargins(48, 18, 44, 18)

        self.inputLayout.addWidget(
            self.summonerNameLabel, 0, 0, alignment=Qt.AlignLeft)
        self.inputLayout.addWidget(
            self.lineEdit, 0, 1, alignment=Qt.AlignRight)
        self.inputLayout.addWidget(
            self.spectateTypeLabel, 1, 0, alignment=Qt.AlignLeft)
        self.inputLayout.addWidget(
            self.spectateTypeComboBox, 1, 1, alignment=Qt.AlignRight)

        self.inputLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.buttonLayout.setContentsMargins(48, 18, 44, 18)
        self.buttonLayout.addWidget(self.button, 0, Qt.AlignRight)
        self.buttonLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.viewLayout.setSpacing(0)
        self.viewLayout.setContentsMargins(0, 0, 0, 0)
        self.addGroupWidget(self.inputWidget)
        self.addGroupWidget(self.buttonWidget)

    def __initWidget(self):
        self.lineEdit.setPlaceholderText(
            self.tr("Please input summoner's name"))
        self.lineEdit.setMinimumWidth(250)
        self.lineEdit.setClearButtonEnabled(True)

        self.button.setMinimumWidth(100)
        self.button.setEnabled(False)

        self.spectateTypeComboBox.addItem("LCU API", userData="LCU")
        self.spectateTypeComboBox.addItem(self.tr("CMD"), userData="CMD")
        self.spectateTypeComboBox.setMinimumWidth(100)

        self.lineEdit.textChanged.connect(self.__onLineEditTextChanged)
        self.button.clicked.connect(self.__onButtonClicked)

    def __onLineEditTextChanged(self):
        enable = self.lineEdit.text() != ""
        self.button.setEnabled(enable)

    @asyncSlot()
    async def __onButtonClicked(self):
        def info(type, title, content):
            f = InfoBar.error if type == 'error' else InfoBar.success

            f(title=title, content=content, orient=Qt.Vertical, isClosable=True,
              position=InfoBarPosition.TOP_RIGHT, duration=5000,
              parent=self.window().auxiliaryFuncInterface)

        try:
            text = self.lineEdit.text()
            text = text.replace('\u2066', '').replace('\u2069', '')

            if self.spectateTypeComboBox.currentData() == 'LCU':
                await connector.spectate(text)
            else:
                await connector.spectateDirectly(text)

        except SummonerNotFound:
            info('error', self.tr("Summoner not found"),
                 self.tr("Please check the summoner's name and retry"))
        except SummonerNotInGame:
            info('error', self.tr("Summoner isn't in game"), "")
        else:
            info('success', self.tr("Spectate successfully"),
                 self.tr("Please wait"), )

class LockConfigCard(SettingCard):
    def __init__(self, title, content, parent):
        super().__init__(Icon.LOCK, title, content, parent)

        self.switchButton = SwitchButton(indicatorPos=IndicatorPosition.RIGHT)

        self.hBoxLayout.addWidget(self.switchButton)
        self.hBoxLayout.addSpacing(16)

        self.switchButton.checkedChanged.connect(self.__onCheckedChanged)

    def loadNowMode(self):
        path = f"{cfg.get(cfg.lolFolder)[0]}/../Game/Config/PersistedSettings.json"

        if not os.path.exists(path):
            self.switchButton.setChecked(False)
            self.switchButton.setEnabled(False)

            return

        try:
            currentMode = stat.S_IMODE(os.lstat(path).st_mode)
            if currentMode == 0o444:
                self.switchButton.setChecked(True)
        except OSError:
            self.switchButton.setEnabled(False)
            pass

    def __onCheckedChanged(self, isChecked: bool):
        if not self.setConfigFileReadOnlyEnabled(isChecked):
            InfoBar.error(
                title=self.tr("Error"),
                content=self.tr("Failed to set file permissions"),
                orient=Qt.Vertical,
                isClosable=True,
                position=InfoBarPosition.BOTTOM_RIGHT,
                duration=5000,
                parent=self.window(),
            )

            self.switchButton.checkedChanged.disconnect()
            self.switchButton.setChecked(not isChecked)
            self.switchButton.checkedChanged.connect(self.__onCheckedChanged)

    def setConfigFileReadOnlyEnabled(self, enable):
        path = f"{cfg.get(cfg.lolFolder)[0]}/../Game/Config/PersistedSettings.json"

        if not os.path.exists(path):
            return False

        mode = 0o444 if enable else 0o666
        try:
            os.chmod(path, mode)
            currentMode = stat.S_IMODE(os.lstat(path).st_mode)

            if currentMode != mode:
                return False
        except OSError:
            self.switchButton.setEnabled(False)
            return False

        return True
