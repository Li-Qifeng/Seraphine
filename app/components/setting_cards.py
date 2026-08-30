# coding:utf-8
from typing import Union
from copy import deepcopy

from app.common.qfluentwidgets import (FluentIconBase, ExpandGroupSettingCard,
                                       ConfigItem, qconfig, PushButton, SpinBox,
                                       ColorDialog, LineEdit, SwitchButton,
                                       IndicatorPosition, SwitchSettingCard, setThemeColor,
                                       PillPushButton, ComboBox)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QIcon, QColor
from PyQt5.QtWidgets import (QWidget, QLabel, QHBoxLayout, QGridLayout, QFrame)

from app.common.icons import Icon
from app.common.config import cfg
from app.common.signals import signalBus
from app.components.animation_frame import ColorAnimationFrame


class LineEditSettingCard(ExpandGroupSettingCard):

    def __init__(self, configItem, title, hintContent, step, min,
                 max, icon: Union[str, QIcon, FluentIconBase],
                 content=None, parent=None):
        super().__init__(icon, title, content, parent)
        self.configItem = configItem

        self.inputWidget = QWidget(self.view)
        self.inputLayout = QHBoxLayout(self.inputWidget)

        self.hintLabel = QLabel(hintContent)
        self.lineEdit = SpinBox(self)

        self.buttonWidget = QWidget(self.view)
        self.buttonLayout = QHBoxLayout(self.buttonWidget)
        self.pushButton = PushButton(self.tr("Apply"))

        self.statusLabel = QLabel(self)

        self.__initLayout()
        self.__initWidget(step, min, max)

    def __onValueChanged(self):
        value = self.lineEdit.value()
        cfg.set(self.configItem, value)
        self.__setStatusLabelText(value)

    def __initWidget(self, step, min, max):
        self.lineEdit.setRange(min, max)
        value = cfg.get(self.configItem)
        self.__setStatusLabelText(value)

        self.lineEdit.setValue(value)
        self.lineEdit.setSingleStep(step)
        self.lineEdit.setMinimumWidth(250)
        self.pushButton.setMinimumWidth(100)
        self.pushButton.clicked.connect(self.__onValueChanged)

    def __initLayout(self):
        self.addWidget(self.statusLabel)

        self.inputLayout.setSpacing(19)
        self.inputLayout.setAlignment(Qt.AlignTop)
        self.inputLayout.setContentsMargins(48, 18, 44, 18)

        self.inputLayout.addWidget(
            self.hintLabel, alignment=Qt.AlignLeft)
        self.inputLayout.addWidget(self.lineEdit, alignment=Qt.AlignRight)
        self.inputLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.buttonLayout.setContentsMargins(48, 18, 44, 18)
        self.buttonLayout.addWidget(self.pushButton, 0, Qt.AlignRight)
        self.buttonLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.viewLayout.setSpacing(0)
        self.viewLayout.setContentsMargins(0, 0, 0, 0)
        self.addGroupWidget(self.inputWidget)
        self.addGroupWidget(self.buttonWidget)

    def __setStatusLabelText(self, value):
        self.statusLabel.setText(self.tr("Now: ") + str(value))


class GameTabColorSettingCard(ExpandGroupSettingCard):
    def __init__(self, title, content=None, winConfigItem: ConfigItem = None,
                 loseConfigItem: ConfigItem = None, remakeConfigItem: ConfigItem = None,
                 parent=None):
        super().__init__(Icon.BACKGROUNDCOLOR, title, content, parent)

        self.statusLabel = QLabel(self)

        self.inputWidget = QWidget(self.view)
        self.inputLayout = QGridLayout(self.inputWidget)

        self.winHintLabel = QLabel(self.tr("Color of wins:"))
        self.loseHintLabel = QLabel(self.tr("Color of losses:"))
        self.remakeHintLabel = QLabel(self.tr("Color of remakes:"))

        self.winSettingButton = ColorAnimationFrame(type='win')
        self.loseSettingButton = ColorAnimationFrame(type='lose')
        self.remakeSettingButton = ColorAnimationFrame(type='remake')

        self.resetWidget = QWidget()
        self.resetLayout = QHBoxLayout(self.resetWidget)
        self.resetButton = PushButton(self.tr("Reset"))

        self.defaultWinColor = QColor(winConfigItem.defaultValue)
        self.defaultLoseColor = QColor(loseConfigItem.defaultValue)
        self.defaultRemakeColor = QColor(remakeConfigItem.defaultValue)

        self.winConfigItem = winConfigItem
        self.loseConfigItem = loseConfigItem
        self.remakeConfigItem = remakeConfigItem

        self.__initWidget()
        self.__initLayout()

    def __initLayout(self):
        self.addWidget(self.statusLabel)

        self.inputLayout.setSpacing(19)
        self.inputLayout.setAlignment(Qt.AlignTop)
        self.inputLayout.setContentsMargins(48, 18, 44, 18)

        self.inputLayout.addWidget(
            self.winHintLabel, 0, 0, alignment=Qt.AlignLeft)
        self.inputLayout.addWidget(
            self.loseHintLabel, 1, 0, alignment=Qt.AlignLeft)
        self.inputLayout.addWidget(
            self.remakeHintLabel, 2, 0, alignment=Qt.AlignLeft)

        self.inputLayout.addWidget(
            self.winSettingButton, 0, 1, alignment=Qt.AlignRight)
        self.inputLayout.addWidget(
            self.loseSettingButton, 1, 1, alignment=Qt.AlignRight)
        self.inputLayout.addWidget(
            self.remakeSettingButton, 2, 1, alignment=Qt.AlignRight)

        self.inputLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.resetLayout.setContentsMargins(48, 18, 44, 18)
        self.resetLayout.addWidget(self.resetButton, 0, Qt.AlignRight)
        self.resetLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.viewLayout.setSpacing(0)
        self.viewLayout.setContentsMargins(0, 0, 0, 0)
        self.addGroupWidget(self.inputWidget)
        self.addGroupWidget(self.resetWidget)

    def __initWidget(self):
        self.winSettingButton.setFixedSize(100, 32)
        self.loseSettingButton.setFixedSize(100, 32)
        self.remakeSettingButton.setFixedSize(100, 32)

        self.resetButton.setMinimumWidth(100)

        self.setValue(qconfig.get(self.winConfigItem),
                      qconfig.get(self.loseConfigItem),
                      qconfig.get(self.remakeConfigItem))

        self.winSettingButton.clicked.connect(
            lambda: self.__onSettingButtonClicked('win'))
        self.loseSettingButton.clicked.connect(
            lambda: self.__onSettingButtonClicked('lose'))
        self.remakeSettingButton.clicked.connect(
            lambda: self.__onSettingButtonClicked('remake'))

        self.resetButton.clicked.connect(self.__reset)

    def setValue(self, winColor: QColor = None, loseColor: QColor = None, remakeColor: QColor = None):
        if winColor:
            qconfig.set(self.winConfigItem, winColor)

        if loseColor:
            qconfig.set(self.loseConfigItem, loseColor)

        if remakeColor:
            qconfig.set(self.remakeConfigItem, remakeColor)

        self.__setStatusLabel()

    def __setStatusLabel(self):
        if (qconfig.get(self.winConfigItem) == self.defaultWinColor and
                qconfig.get(self.loseConfigItem) == self.defaultLoseColor and
                qconfig.get(self.remakeConfigItem) == self.defaultRemakeColor):
            self.statusLabel.setText(self.tr("Default color"))
            self.resetButton.setEnabled(False)
        else:
            self.statusLabel.setText(self.tr("Custom color"))
            self.resetButton.setEnabled(True)

    def __onSettingButtonClicked(self, name):
        if name == 'win':
            configItem = self.winConfigItem
        elif name == 'lose':
            configItem = self.loseConfigItem
        else:
            configItem = self.remakeConfigItem

        w = ColorDialog(
            qconfig.get(configItem), self.tr('Choose color'), self.window(), True)
        w.colorChanged.connect(
            lambda color: self.__onColorChanged(color, name))
        w.exec()

    def __onColorChanged(self, color, name):
        if name == 'win':
            self.setValue(winColor=color)
        elif name == 'lose':
            self.setValue(loseColor=color)
        else:
            self.setValue(remakeColor=color)

        signalBus.customColorChanged.emit(name)

    def __reset(self):
        self.setValue(self.defaultWinColor, self.defaultLoseColor,
                      self.defaultRemakeColor)

        signalBus.customColorChanged.emit('win')
        signalBus.customColorChanged.emit('lose')
        signalBus.customColorChanged.emit('remake')


class DeathsNumberColorSettingCard(ExpandGroupSettingCard):
    def __init__(self, title, content=None, lightConfigItem: ConfigItem = None,
                 darkConfigItem: ConfigItem = None, parent=None):
        super().__init__(Icon.TEXTCOLOR, title, content, parent)

        self.statusLabel = QLabel(self)

        self.inputWidget = QWidget(self.view)
        self.inputLayout = QGridLayout(self.inputWidget)

        self.lightHintLabel = QLabel(self.tr("Color in Light theme:"))
        self.darkHintLabel = QLabel(self.tr("Color in Dark theme:"))

        self.lightSettingButton = ColorAnimationFrame(type='deathsLight')
        self.darkSettingButton = ColorAnimationFrame(type='deathsDark')

        self.resetWidget = QWidget()
        self.resetLayout = QHBoxLayout(self.resetWidget)
        self.resetButton = PushButton(self.tr("Reset"))

        self.defaultLightColor = QColor(lightConfigItem.defaultValue)
        self.defaultDarkColor = QColor(darkConfigItem.defaultValue)

        self.lightConfigItem = lightConfigItem
        self.darkConfigItem = darkConfigItem

        self.__initWidget()
        self.__initLayout()

    def __initLayout(self):
        self.addWidget(self.statusLabel)

        self.inputLayout.setSpacing(19)
        self.inputLayout.setAlignment(Qt.AlignTop)
        self.inputLayout.setContentsMargins(48, 18, 44, 18)

        self.inputLayout.addWidget(
            self.lightHintLabel, 0, 0, alignment=Qt.AlignLeft)
        self.inputLayout.addWidget(
            self.darkHintLabel, 1, 0, alignment=Qt.AlignLeft)

        self.inputLayout.addWidget(
            self.lightSettingButton, 0, 1, alignment=Qt.AlignRight)
        self.inputLayout.addWidget(
            self.darkSettingButton, 1, 1, alignment=Qt.AlignRight)

        self.inputLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.resetLayout.setContentsMargins(48, 18, 44, 18)
        self.resetLayout.addWidget(self.resetButton, 0, Qt.AlignRight)
        self.resetLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.viewLayout.setSpacing(0)
        self.viewLayout.setContentsMargins(0, 0, 0, 0)
        self.addGroupWidget(self.inputWidget)
        self.addGroupWidget(self.resetWidget)

    def __initWidget(self):
        self.lightSettingButton.setFixedSize(100, 32)
        self.darkSettingButton.setFixedSize(100, 32)

        self.resetButton.setMinimumWidth(100)

        self.setValue(qconfig.get(self.lightConfigItem),
                      qconfig.get(self.darkConfigItem))

        self.lightSettingButton.clicked.connect(
            lambda: self.__onSettingButtonClicked('deathsLight'))
        self.darkSettingButton.clicked.connect(
            lambda: self.__onSettingButtonClicked('deathsDark'))

        self.resetButton.clicked.connect(self.__reset)

    def setValue(self, lightColor: QColor = None, darkColor: QColor = None):
        if lightColor:
            qconfig.set(self.lightConfigItem, lightColor)

        if darkColor:
            qconfig.set(self.darkConfigItem, darkColor)

        self.__setStatusLabel()

    def __setStatusLabel(self):
        if (qconfig.get(self.lightConfigItem) == self.defaultLightColor and
                qconfig.get(self.darkConfigItem) == self.defaultDarkColor):
            self.statusLabel.setText(self.tr("Default color"))
            self.resetButton.setEnabled(False)
        else:
            self.statusLabel.setText(self.tr("Custom color"))
            self.resetButton.setEnabled(True)

    def __onSettingButtonClicked(self, name):
        if name == 'deathsLight':
            configItem = self.lightConfigItem
        elif name == 'deathsDark':
            configItem = self.darkConfigItem

        w = ColorDialog(
            qconfig.get(configItem), self.tr('Choose color'), self.window())
        w.colorChanged.connect(
            lambda color: self.__onColorChanged(color, name))
        w.exec()

    def __onColorChanged(self, color, name):
        if name == 'deathsLight':
            self.setValue(lightColor=color)
        elif name == 'deathsDark':
            self.setValue(darkColor=color)

        signalBus.customColorChanged.emit(name)
        signalBus.customColorChanged.emit("deaths")

    def __reset(self):
        self.setValue(self.defaultLightColor, self.defaultDarkColor)

        signalBus.customColorChanged.emit('deathsLight')
        signalBus.customColorChanged.emit('deathsDark')
        signalBus.customColorChanged.emit("deaths")


class ThemeColorSettingCard(ExpandGroupSettingCard):
    def __init__(self, title, content=None,
                 colorConfigItem: ConfigItem = None,
                 parent=None):
        super().__init__(Icon.PALETTE, title, content, parent)

        self.statusLabel = QLabel(self)

        self.inputWidget = QWidget(self.view)
        self.inputLayout = QGridLayout(self.inputWidget)

        self.colorHintLabel = QLabel(self.tr("Theme color:"))

        self.colorSettingButton = ColorAnimationFrame(type='theme')

        self.resetWidget = QWidget()
        self.resetLayout = QHBoxLayout(self.resetWidget)
        self.resetButton = PushButton(self.tr("Reset"))

        self.defaultColor = QColor(colorConfigItem.defaultValue)

        self.colorConfigItem = colorConfigItem

        self.__initWidget()
        self.__initLayout()

    def __initLayout(self):
        self.addWidget(self.statusLabel)

        self.inputLayout.setSpacing(19)
        self.inputLayout.setAlignment(Qt.AlignTop)
        self.inputLayout.setContentsMargins(48, 18, 44, 18)

        self.inputLayout.addWidget(
            self.colorHintLabel, 0, 0, alignment=Qt.AlignLeft)

        self.inputLayout.addWidget(
            self.colorSettingButton, 0, 1, alignment=Qt.AlignRight)
        self.inputLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.resetLayout.setContentsMargins(48, 18, 44, 18)
        self.resetLayout.addWidget(self.resetButton, 0, Qt.AlignRight)
        self.resetLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.viewLayout.setSpacing(0)
        self.viewLayout.setContentsMargins(0, 0, 0, 0)
        self.addGroupWidget(self.inputWidget)
        self.addGroupWidget(self.resetWidget)

    def __initWidget(self):
        self.colorSettingButton.setFixedSize(100, 32)
        self.resetButton.setMinimumWidth(100)

        self.setValue(qconfig.get(self.colorConfigItem))

        self.colorSettingButton.clicked.connect(self.__onSettingButtonClicked)
        self.resetButton.clicked.connect(
            lambda: self.__onColorChanged(self.defaultColor))

    def setValue(self, color):
        qconfig.set(self.colorConfigItem, color)

        self.__setStatusLabel()

    def __setStatusLabel(self):
        if qconfig.get(self.colorConfigItem) == self.defaultColor:
            self.statusLabel.setText(self.tr("Default color"))
            self.resetButton.setEnabled(False)
        else:
            self.statusLabel.setText(self.tr("Custom color"))
            self.resetButton.setEnabled(True)

    def __onSettingButtonClicked(self):
        configItem = self.colorConfigItem

        w = ColorDialog(
            qconfig.get(configItem), self.tr('Choose color'), self.window(), False)
        w.colorChanged.connect(self.__onColorChanged)

        w.exec()

    def __onColorChanged(self, color):
        self.setValue(color=color)

        signalBus.customColorChanged.emit('theme')
        setThemeColor(color)


class ProxySettingCard(ExpandGroupSettingCard):
    def __init__(self, title, content, enableConfigItem: ConfigItem = None,
                 addrConfigItem: ConfigItem = None, parent=None):
        super().__init__(Icon.PLANE, title, content, parent)

        self.statusLabel = QLabel(self)

        self.inputWidget = QWidget(self.view)
        self.inputLayout = QHBoxLayout(self.inputWidget)

        self.secondsLabel = QLabel(self.tr("HTTP proxy:"))
        self.lineEdit = LineEdit()

        self.switchButtonWidget = QWidget(self.view)
        self.switchButtonLayout = QHBoxLayout(self.switchButtonWidget)

        self.switchButton = SwitchButton(indicatorPos=IndicatorPosition.RIGHT)

        self.enableConfigItem = enableConfigItem
        self.addrConfigItem = addrConfigItem

        self.__initLayout()
        self.__initWidget()

    def __initLayout(self):
        self.addWidget(self.statusLabel)

        self.inputLayout.setSpacing(19)
        self.inputLayout.setAlignment(Qt.AlignTop)
        self.inputLayout.setContentsMargins(48, 18, 44, 18)

        self.inputLayout.addWidget(self.secondsLabel, alignment=Qt.AlignLeft)
        self.inputLayout.addWidget(self.lineEdit, alignment=Qt.AlignRight)
        self.inputLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.switchButtonLayout.setContentsMargins(48, 18, 44, 18)
        self.switchButtonLayout.addWidget(self.switchButton, 0, Qt.AlignRight)
        self.switchButtonLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.viewLayout.setSpacing(0)
        self.viewLayout.setContentsMargins(0, 0, 0, 0)
        self.addGroupWidget(self.inputWidget)
        self.addGroupWidget(self.switchButtonWidget)

    def __initWidget(self):
        self.lineEdit.setText(cfg.get(self.addrConfigItem))
        self.lineEdit.setMinimumWidth(250)
        self.lineEdit.setPlaceholderText("127.0.0.1:10809")

        self.switchButton.setChecked(cfg.get(self.enableConfigItem))

        self.lineEdit.textChanged.connect(self.__onLineEditValueChanged)
        self.switchButton.checkedChanged.connect(
            self.__onSwitchButtonCheckedChanged)

        value, isChecked = self.lineEdit.text(), self.switchButton.isChecked()
        self.__setStatusLableText(value, isChecked)
        self.lineEdit.setEnabled(not isChecked)

    def setValue(self, addr: int, isChecked: bool):
        qconfig.set(self.addrConfigItem, addr)
        qconfig.set(self.enableConfigItem, isChecked)

        self.__setStatusLableText(addr, isChecked)

    def __onSwitchButtonCheckedChanged(self, isChecked: bool):
        self.setValue(self.lineEdit.text(), isChecked)
        self.lineEdit.setEnabled(not isChecked)

    def __onLineEditValueChanged(self, value):
        self.setValue(value, self.switchButton.isChecked())

    def __setStatusLableText(self, addr, isChecked):
        if isChecked:
            self.statusLabel.setText(self.tr("Enabled, proxy: ") + str(addr))
        else:
            self.statusLabel.setText(self.tr("Disabled"))


class LooseSwitchSettingCard(SwitchSettingCard):
    """ 允许bool以外的值来初始化的SwitchSettingCard控件 """

    def __init__(self, icon, title, content=None, configItem: ConfigItem = None, parent=None):
        super().__init__(icon, title, content, configItem, parent)

        self.switchButton.setOnText(self.tr("On"))
        self.switchButton.setOffText(self.tr("Off"))

    def setValue(self, isChecked):
        """
        为适应 config 中对应字段为任意值时初始化控件;

        若传入 bool 以外的值, 前端将会看到False

        需要设置值, 有以下途径:
        1. 代码层调用 setValue 时, 以bool传入
        2. 用户通过前端拨动 SwitchButton

        @param isChecked:
        @return:
        """
        if isinstance(isChecked, bool):
            super().setValue(isChecked)
        else:
            self.switchButton.setChecked(False)


class ModeCheckButtonsGroup(QWidget):
    selectedChanged = pyqtSignal(list)

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)

        self.hBoxLayout = QHBoxLayout(self)

        self.allButton = PillPushButton(self.tr("Show All"))

        self.normalButton = PillPushButton(self.tr("Normal"))
        self.quickButton = PillPushButton(self.tr("Quickplay"))
        self.soloDuoButton = PillPushButton(self.tr("Ranked Solo / Duo"))
        self.flexButton = PillPushButton(self.tr("Ranked Flex"))
        self.aramButton = PillPushButton(self.tr("A.R.A.M."))

        self.modeButtons = [self.normalButton,
                            self.quickButton,
                            self.soloDuoButton,
                            self.flexButton,
                            self.aramButton]

        self.separator = QFrame()
        self.separator.setFrameShape(QFrame.Shape.VLine)
        self.separator.setLineWidth(1)

        self.selected = []

        self.__initWidget()
        self.__initLayout()

    def __initWidget(self):
        self.separator.setObjectName("separator")

        # 只能从未选中变成选中
        self.allButton.clicked.connect(self.__onAllButtonClicked)

        self.normalButton.clicked.connect(
            lambda: self.__onModeButtonClicked(430))
        self.quickButton.clicked.connect(
            lambda: self.__onModeButtonClicked(480))
        self.soloDuoButton.clicked.connect(
            lambda: self.__onModeButtonClicked(420))
        self.flexButton.clicked.connect(
            lambda: self.__onModeButtonClicked(440))
        self.aramButton.clicked.connect(
            lambda: self.__onModeButtonClicked(450))

    def __initLayout(self):
        self.hBoxLayout.setContentsMargins(0, 0, 0, 0)
        self.hBoxLayout.setSpacing(12)

        self.hBoxLayout.addWidget(self.allButton)
        self.hBoxLayout.addSpacing(5)
        self.hBoxLayout.addWidget(self.separator)
        self.hBoxLayout.addSpacing(5)
        self.hBoxLayout.addWidget(self.normalButton)
        self.hBoxLayout.addWidget(self.quickButton)
        self.hBoxLayout.addWidget(self.soloDuoButton)
        self.hBoxLayout.addWidget(self.flexButton)
        self.hBoxLayout.addWidget(self.aramButton)

    def setSelectedButtons(self, selected: list):
        self.selected = selected

        if len(selected) == 0:
            self.allButton.setChecked(True)

            for button in self.modeButtons:
                button.setChecked(False)
        else:
            self.allButton.setChecked(False)

            for queueId in selected:
                button = self.getButton(queueId)
                button.setChecked(True)

    def getButton(self, queueId) -> PillPushButton:
        return {
            430: self.normalButton,
            420: self.soloDuoButton,
            440: self.flexButton,
            450: self.aramButton,
            480: self.quickButton,
        }[queueId]

    def __onAllButtonClicked(self):
        if self.allButton.isChecked():
            for button in self.modeButtons:
                button.setChecked(False)

            self.selected = []
            self.selectedChanged.emit(self.selected)
        else:
            self.allButton.setChecked(True)

    def __onModeButtonClicked(self, queueId):
        button = self.getButton(queueId)

        if button.isChecked():
            self.selected.append(queueId)
            self.allButton.setChecked(False)
        else:
            self.selected.remove(queueId)

            if all(map(lambda button: not button.isChecked(),
                       self.modeButtons)):
                self.allButton.setChecked(True)

        self.selectedChanged.emit(self.selected)


class QueueFilterCard(ExpandGroupSettingCard):
    def __init__(self, title, content=None,
                 configItem: ConfigItem = None,
                 parent=None):
        super().__init__(Icon.FILTER, title, content, parent)

        self.configItem = configItem

        self.inputWidget = QWidget(self.view)
        self.inputLayout = QGridLayout(self.inputWidget)

        self.normalHintLabel = QLabel(self.tr("Normal:"))
        self.quickHintLabel = QLabel(self.tr("Quickplay:"))
        self.soloDuoHintLabel = QLabel(self.tr("Ranked Solo / Duo:"))
        self.flexHintLabel = QLabel(self.tr("Ranked Flex:"))
        self.aramHintLabel = QLabel(self.tr("A.R.A.M.:"))

        self.normalButtonsGroup = ModeCheckButtonsGroup()
        self.quickButtonsGroup = ModeCheckButtonsGroup()
        self.soloDuoButtonsGroup = ModeCheckButtonsGroup()
        self.flexButtonsGroup = ModeCheckButtonsGroup()
        self.aramButtonsGroup = ModeCheckButtonsGroup()

        self.buttonsWidget = QWidget(self.view)
        self.buttonsLayout = QGridLayout(self.buttonsWidget)
        self.resetButton = PushButton(self.tr("Reset"))

        self.__initWidget()
        self.__initLayout()

    def __initWidget(self):
        self.resetButton.setMinimumWidth(100)

        selected = deepcopy(qconfig.get(self.configItem))

        self.normalButtonsGroup.setSelectedButtons(selected['430'])
        self.quickButtonsGroup.setSelectedButtons(selected['480'])
        self.soloDuoButtonsGroup.setSelectedButtons(selected['420'])
        self.flexButtonsGroup.setSelectedButtons(selected['440'])
        self.aramButtonsGroup.setSelectedButtons(selected['450'])

        self.normalButtonsGroup.selectedChanged.connect(
            lambda checked: self.__onButtonsGroupSelectChanged(checked, '430'))
        self.quickButtonsGroup.selectedChanged.connect(
            lambda checked: self.__onButtonsGroupSelectChanged(checked, '480'))
        self.soloDuoButtonsGroup.selectedChanged.connect(
            lambda checked: self.__onButtonsGroupSelectChanged(checked, '420'))
        self.flexButtonsGroup.selectedChanged.connect(
            lambda checked: self.__onButtonsGroupSelectChanged(checked, '440'))
        self.aramButtonsGroup.selectedChanged.connect(
            lambda checked: self.__onButtonsGroupSelectChanged(checked, '450'))

        self.resetButton.clicked.connect(self.__onResetButtonClicked)

    def __initLayout(self):
        self.inputLayout.setVerticalSpacing(19)
        self.inputLayout.setContentsMargins(48, 18, 44, 18)
        self.inputLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.inputLayout.addWidget(self.normalHintLabel, 0, 0, Qt.AlignLeft)
        self.inputLayout.addWidget(self.quickHintLabel, 1, 0, Qt.AlignLeft)
        self.inputLayout.addWidget(self.soloDuoHintLabel, 2, 0, Qt.AlignLeft)
        self.inputLayout.addWidget(self.flexHintLabel, 3, 0, Qt.AlignLeft)
        self.inputLayout.addWidget(self.aramHintLabel, 4, 0, Qt.AlignLeft)
        self.inputLayout.addWidget(self.normalButtonsGroup, 0, 1, Qt.AlignLeft)
        self.inputLayout.addWidget(self.quickButtonsGroup, 1, 1, Qt.AlignLeft)
        self.inputLayout.addWidget(
            self.soloDuoButtonsGroup, 2, 1, Qt.AlignLeft)
        self.inputLayout.addWidget(self.flexButtonsGroup, 3, 1, Qt.AlignLeft)
        self.inputLayout.addWidget(self.aramButtonsGroup, 4, 1, Qt.AlignLeft)

        self.buttonsLayout.setVerticalSpacing(19)
        self.buttonsLayout.setContentsMargins(48, 18, 44, 18)
        self.buttonsLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)
        self.buttonsLayout.addWidget(self.resetButton, 0, 1, Qt.AlignRight)

        self.viewLayout.setSpacing(0)
        self.viewLayout.setContentsMargins(0, 0, 0, 0)

        self.addGroupWidget(self.inputWidget)
        self.addGroupWidget(self.buttonsWidget)

    def __onButtonsGroupSelectChanged(self, selected, queueId):
        current = deepcopy(qconfig.get(self.configItem))
        current[queueId] = selected
        qconfig.set(self.configItem, current)

    def __onResetButtonClicked(self):
        self.normalButtonsGroup.setSelectedButtons([])
        self.quickButtonsGroup.setSelectedButtons([])
        self.soloDuoButtonsGroup.setSelectedButtons([])
        self.flexButtonsGroup.setSelectedButtons([])
        self.aramButtonsGroup.setSelectedButtons([])

        default = self.configItem.defaultValue
        qconfig.set(self.configItem, default)


class RatingStyleSettingCard(ExpandGroupSettingCard):
    """评级文案风格设置卡: 头部 ComboBox 选风格, 选 'custom' 时展开
    胜方/败方各 5 档文案编辑器, 点保存写入配置, 删除恢复默认.
    未选 custom 时不显示展开按钮, 头部点击不展开.

    与 ComboBoxSettingCard 不同, 本卡把 ComboBox 放进头部 (header),
    展开区 (view) 承载自定义文案编辑, 契合"对局信息过滤"式的内嵌页面.
    """

    def __init__(self, configItem, title, content=None, texts=None,
                 defaultLabels=None, icon=Icon.SCALEFIT, parent=None):
        """Args:
        configItem:   风格 ConfigItem (如 cfg.teamRatingStyle, 含 'custom' 选项)
        defaultLabels: 预设标签 {isWin: [5 档]}, 用于自定义为空时的占位/初始化
        texts:         ComboBox 文本列表, 与 configItem.options 对齐
        """
        super().__init__(icon, title, content, parent)
        self.configItem = configItem
        self.defaultLabels = defaultLabels or {}

        self.comboBox = ComboBox(self)
        for option, text in zip(configItem.options, texts or []):
            self.comboBox.addItem(text, userData=option)

        self.winEdits = [LineEdit(self) for _ in range(5)]
        self.lossEdits = [LineEdit(self) for _ in range(5)]
        self.winHints = [QLabel(self.tr("Win %1").replace("%1", str(i + 1)))
                         for i in range(5)]
        self.lossHints = [QLabel(self.tr("Loss %1").replace("%1", str(i + 1)))
                          for i in range(5)]

        self.titleLabel = QLabel(self.tr("Custom win/loss labels"))
        self.titleLabel.setObjectName("ratingViewTitle")

        self.inputWidget = QWidget(self.view)
        self.inputLayout = QGridLayout(self.inputWidget)

        self.buttonWidget = QWidget(self.view)
        self.buttonLayout = QHBoxLayout(self.buttonWidget)
        self.saveButton = PushButton(self.tr("Save"))
        self.deleteButton = PushButton(self.tr("Delete"))

        self.__initLayout()
        self.__initWidget()

    def __initLayout(self):
        self.titleWidget = QWidget(self.view)
        self.titleLayout = QHBoxLayout(self.titleWidget)
        self.titleLayout.setContentsMargins(48, 18, 44, 0)
        self.titleLayout.addWidget(self.titleLabel)

        for i in range(5):
            self.inputLayout.addWidget(self.winHints[i], i, 0, Qt.AlignRight)
        for i in range(5):
            self.inputLayout.addWidget(self.lossHints[i], i, 2, Qt.AlignRight)
        for i in range(5):
            self.inputLayout.addWidget(self.winEdits[i], i, 1, Qt.AlignLeft)
        for i in range(5):
            self.inputLayout.addWidget(self.lossEdits[i], i, 3, Qt.AlignLeft)

        self.inputLayout.setHorizontalSpacing(19)
        self.inputLayout.setVerticalSpacing(12)
        self.inputLayout.setContentsMargins(48, 18, 44, 18)
        self.inputLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.buttonLayout.setContentsMargins(48, 12, 44, 18)
        self.buttonLayout.addWidget(self.saveButton, 0, Qt.AlignRight)
        self.buttonLayout.addWidget(self.deleteButton, 0, Qt.AlignRight)
        self.buttonLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.viewLayout.setSpacing(0)
        self.viewLayout.setContentsMargins(0, 0, 0, 0)
        self.addGroupWidget(self.titleWidget)
        self.addGroupWidget(self.inputWidget)
        self.addGroupWidget(self.buttonWidget)

    def __initWidget(self):
        self.comboBox.setCurrentIndex(
            self.configItem.options.index(qconfig.get(self.configItem)))
        self.comboBox.currentIndexChanged.connect(self.__onCurrentIndexChanged)

        self.saveButton.clicked.connect(self.__onSaveClicked)

        self.deleteButton.clicked.connect(self.__onDeleteClicked)

        self.addWidget(self.comboBox)
        self.__applyCustomState()

    def showEvent(self, e):
        """构造期(setExpand)拿不到可靠的 view 尺寸: 高度不足 -> 胜/败 5 行显示不全,
        动画状态也易残留(下拉框点击后表现异常). 延迟到真实几何后再展开."""
        super().showEvent(e)
        if qconfig.get(self.configItem) == 'custom':
            self._adjustViewSize()
            self.setExpand(True)

    def toggleExpand(self):
        if qconfig.get(self.configItem) == 'custom':
            super().toggleExpand()
        else:
            self.setExpand(False)

    def __onCurrentIndexChanged(self, index):
        option = self.configItem.options[index]
        qconfig.set(self.configItem, option)
        self.__applyCustomState()

    def __applyCustomState(self):
        isCustom = qconfig.get(self.configItem) == 'custom'
        self.card.expandButton.setVisible(isCustom)
        if isCustom:
            self.__loadCustomLabels()
            if self.isVisible():
                self._adjustViewSize()
                self.setExpand(True)
        else:
            self.setExpand(False)

    def __loadCustomLabels(self):
        """自定义文案回填; 未配置/损坏时用默认标签作为可编辑基."""
        raw = qconfig.get(cfg.teamRatingCustomLabels if
                          self.configItem is cfg.teamRatingStyle
                          else cfg.horseRatingCustomLabels)
        try:
            win = (raw or {}).get('win') or []
            loss = (raw or {}).get('loss') or []
            win = [str(x) for x in win] if isinstance(win, list) else []
            loss = [str(x) for x in loss] if isinstance(loss, list) else []
            winValid = len(win) == 5
            lossValid = len(loss) == 5
        except AttributeError:
            win, loss, winValid, lossValid = [], [], False, False

        if not winValid:
            win = list((self.defaultLabels.get(True) or [""] * 5))
        if not lossValid:
            loss = list((self.defaultLabels.get(False) or [""] * 5))

        for edit, text in zip(self.winEdits, win):
            edit.setText(text)
        for edit, text in zip(self.lossEdits, loss):
            edit.setText(text)

    def __onSaveClicked(self):
        self.__saveCustomLabels()

    def __saveCustomLabels(self):
        item = (cfg.teamRatingCustomLabels if
                self.configItem is cfg.teamRatingStyle
                else cfg.horseRatingCustomLabels)
        qconfig.set(item, {
            'win': [e.text() for e in self.winEdits],
            'loss': [e.text() for e in self.lossEdits],
        })

    def __onDeleteClicked(self):
        item = (cfg.teamRatingCustomLabels if
                self.configItem is cfg.teamRatingStyle
                else cfg.horseRatingCustomLabels)
        qconfig.set(item, item.defaultValue)
        qconfig.set(self.configItem, self.configItem.defaultValue)
        self.comboBox.setCurrentIndex(
            self.configItem.options.index(self.configItem.defaultValue))
        self.__applyCustomState()


class TeamColorSettingCard(ExpandGroupSettingCard):
    """预组队高亮色 (对局信息界面 team1/team2) 设置卡."""

    def __init__(self, title, content=None,
                 team1ConfigItem: ConfigItem = None,
                 team2ConfigItem: ConfigItem = None,
                 parent=None):
        super().__init__(Icon.BACKGROUNDCOLOR, title, content, parent)

        self.statusLabel = QLabel(self)

        self.inputWidget = QWidget(self.view)
        self.inputLayout = QGridLayout(self.inputWidget)

        self.team1HintLabel = QLabel(self.tr("Color of team 1:"))
        self.team2HintLabel = QLabel(self.tr("Color of team 2:"))

        self.team1SettingButton = ColorAnimationFrame(type='team1')
        self.team2SettingButton = ColorAnimationFrame(type='team2')

        self.resetWidget = QWidget()
        self.resetLayout = QHBoxLayout(self.resetWidget)
        self.resetButton = PushButton(self.tr("Reset"))

        self.defaultTeam1Color = QColor(team1ConfigItem.defaultValue)
        self.defaultTeam2Color = QColor(team2ConfigItem.defaultValue)

        self.team1ConfigItem = team1ConfigItem
        self.team2ConfigItem = team2ConfigItem

        self.__initWidget()
        self.__initLayout()

    def __initLayout(self):
        self.addWidget(self.statusLabel)

        self.inputLayout.setSpacing(19)
        self.inputLayout.setAlignment(Qt.AlignTop)
        self.inputLayout.setContentsMargins(48, 18, 44, 18)

        self.inputLayout.addWidget(
            self.team1HintLabel, 0, 0, alignment=Qt.AlignLeft)
        self.inputLayout.addWidget(
            self.team2HintLabel, 1, 0, alignment=Qt.AlignLeft)

        self.inputLayout.addWidget(
            self.team1SettingButton, 0, 1, alignment=Qt.AlignRight)
        self.inputLayout.addWidget(
            self.team2SettingButton, 1, 1, alignment=Qt.AlignRight)

        self.inputLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.resetLayout.setContentsMargins(48, 18, 44, 18)
        self.resetLayout.addWidget(self.resetButton, 0, Qt.AlignRight)
        self.resetLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.viewLayout.setSpacing(0)
        self.viewLayout.setContentsMargins(0, 0, 0, 0)
        self.addGroupWidget(self.inputWidget)
        self.addGroupWidget(self.resetWidget)

    def __initWidget(self):
        self.team1SettingButton.setFixedSize(100, 32)
        self.team2SettingButton.setFixedSize(100, 32)

        self.resetButton.setMinimumWidth(100)

        self.setValue(qconfig.get(self.team1ConfigItem),
                      qconfig.get(self.team2ConfigItem))

        self.team1SettingButton.clicked.connect(
            lambda: self.__onSettingButtonClicked('team1'))
        self.team2SettingButton.clicked.connect(
            lambda: self.__onSettingButtonClicked('team2'))

        self.resetButton.clicked.connect(self.__reset)

    def setValue(self, team1Color: QColor = None, team2Color: QColor = None):
        if team1Color:
            qconfig.set(self.team1ConfigItem, team1Color)

        if team2Color:
            qconfig.set(self.team2ConfigItem, team2Color)

        self.__setStatusLabel()

    def __setStatusLabel(self):
        if (qconfig.get(self.team1ConfigItem) == self.defaultTeam1Color and
                qconfig.get(self.team2ConfigItem) == self.defaultTeam2Color):
            self.statusLabel.setText(self.tr("Default color"))
            self.resetButton.setEnabled(False)
        else:
            self.statusLabel.setText(self.tr("Custom color"))
            self.resetButton.setEnabled(True)

    def __onSettingButtonClicked(self, name):
        if name == 'team1':
            configItem = self.team1ConfigItem
        else:
            configItem = self.team2ConfigItem

        w = ColorDialog(
            qconfig.get(configItem), self.tr('Choose color'), self.window(), True)
        w.colorChanged.connect(
            lambda color: self.__onColorChanged(color, name))
        w.exec()

    def __onColorChanged(self, color, name):
        if name == 'team1':
            self.setValue(team1Color=color)
        else:
            self.setValue(team2Color=color)

        signalBus.customColorChanged.emit(name)

    def __reset(self):
        self.setValue(self.defaultTeam1Color, self.defaultTeam2Color)

        signalBus.customColorChanged.emit('team1')
        signalBus.customColorChanged.emit('team2')
