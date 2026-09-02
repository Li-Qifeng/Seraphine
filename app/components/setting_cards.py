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
    """评级文案风格设置卡: 头部 ComboBox 选方案, 内置方案(只读) / 用户命名
    方案(可编辑) / 随机(每局从全部方案抽一套) / 新增方案.

    展开区 (view) 承载当前方案的标签(+评语)编辑器:
    - 全队评级 (cfg.teamRatingStyle): 胜方/败方各 5 档标签 + 评语
    - 马评分 (cfg.horseRatingStyle): 按分数 6 档标签 (无胜负/评语)

    内置方案仅代码常量 (不可删改); 用户方案存 cfg.teamRatingSchemes /
    cfg.horseRatingSchemes 命名 space, 可新建/改名/编辑/删除.
    """

    # 下拉特殊项 userData 标记
    _NEW_MARKER = '__new__'

    def __init__(self, configItem, title, content=None, icon=Icon.SCALEFIT,
                 parent=None):
        """Args:
        configItem: 风格 ConfigItem (cfg.teamRatingStyle 或 cfg.horseRatingStyle)
        """
        super().__init__(icon, title, content, parent)
        self.configItem = configItem
        self.isTeam = configItem is cfg.teamRatingStyle
        self.rowCount = 5 if self.isTeam else 6

        self.comboBox = ComboBox(self)
        self.nameEdit = LineEdit(self)
        self.nameHint = QLabel(self.tr("方案名"))
        self.nameHint.setObjectName("ratingViewTitle")
        self.templateCombo = ComboBox(self)
        self.templateHint = QLabel(self.tr("模板"))
        self._pendingNew = False

        if self.isTeam:
            self.winEdits = [LineEdit(self) for _ in range(5)]
            self.lossEdits = [LineEdit(self) for _ in range(5)]
            self.winComEdits = [LineEdit(self) for _ in range(5)]
            self.lossComEdits = [LineEdit(self) for _ in range(5)]
            self.winHints = [QLabel(self.tr("Win %1").replace("%1", str(i + 1)))
                             for i in range(5)]
            self.lossHints = [QLabel(self.tr("Loss %1").replace("%1", str(i + 1)))
                              for i in range(5)]
            self.winComHints = [QLabel(self.tr("评语%1").replace("%1", str(i + 1)))
                                for i in range(5)]
            self.lossComHints = [QLabel(self.tr("评语%1").replace("%1", str(i + 1)))
                                 for i in range(5)]
        else:
            self.labelEdits = [LineEdit(self) for _ in range(6)]
            self.labelHints = [QLabel(self.tr("档%1").replace("%1", str(i + 1)))
                               for i in range(6)]

        self.inputWidget = QWidget(self.view)
        self.inputLayout = QGridLayout(self.inputWidget)

        self.buttonWidget = QWidget(self.view)
        self.buttonLayout = QHBoxLayout(self.buttonWidget)
        self.saveButton = PushButton(self.tr("Save"))
        self.deleteButton = PushButton(self.tr("Delete"))

        self.__initLayout()
        self.__initWidget()

    def __initLayout(self):
        self.nameWidget = QWidget(self.view)
        self.nameLayout = QHBoxLayout(self.nameWidget)
        self.nameLayout.setContentsMargins(48, 18, 44, 0)
        self.nameLayout.addWidget(self.nameHint)
        self.nameLayout.addWidget(self.nameEdit)
        self.nameLayout.addSpacing(12)
        self.nameLayout.addWidget(self.templateHint)
        self.nameLayout.addWidget(self.templateCombo)

        if self.isTeam:
            # 左右两栏: 左=胜方5档(标签+评语), 右=败方5档
            for i in range(5):
                self.inputLayout.addWidget(self.winHints[i], i, 0, Qt.AlignRight)
                self.inputLayout.addWidget(self.winEdits[i], i, 1, Qt.AlignLeft)
                self.inputLayout.addWidget(self.winComHints[i], i, 2, Qt.AlignRight)
                self.inputLayout.addWidget(self.winComEdits[i], i, 3, Qt.AlignLeft)
                self.inputLayout.addWidget(self.lossHints[i], i, 5, Qt.AlignRight)
                self.inputLayout.addWidget(self.lossEdits[i], i, 6, Qt.AlignLeft)
                self.inputLayout.addWidget(self.lossComHints[i], i, 7, Qt.AlignRight)
                self.inputLayout.addWidget(self.lossComEdits[i], i, 8, Qt.AlignLeft)
            self.inputLayout.setColumnMinimumWidth(4, 48)
        else:
            # 赛前评分: 6 组 [档N 提示+输入] 单行横排
            for i in range(6):
                self.inputLayout.addWidget(self.labelHints[i], 0, 2 * i, Qt.AlignRight)
                self.inputLayout.addWidget(self.labelEdits[i], 0, 2 * i + 1, Qt.AlignLeft)

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
        self.addGroupWidget(self.nameWidget)
        self.addGroupWidget(self.inputWidget)
        self.addGroupWidget(self.buttonWidget)

    def __initWidget(self):
        self.__reloadCombo()
        self.comboBox.currentIndexChanged.connect(self.__onCurrentIndexChanged)
        self.__rebuildTemplateCombo()
        self.templateCombo.currentIndexChanged.connect(self.__onTemplateChanged)

        self.saveButton.clicked.connect(self.__onSaveClicked)
        self.deleteButton.clicked.connect(self.__onDeleteClicked)

        self.addWidget(self.comboBox)
        self.__applyState()

    # ------------------------------------------------------------------
    # 方案来源 (按本卡所属系统分派)
    # ------------------------------------------------------------------
    def __isRandom(self, key) -> bool:
        if self.isTeam:
            from app.lol.war_criminal import RANDOM_TEAM_KEY
            return key == RANDOM_TEAM_KEY
        from app.lol.horse_rating import HORSE_RANDOM_KEY
        return key == HORSE_RANDOM_KEY

    def __schemeNames(self) -> list:
        if self.isTeam:
            from app.lol.war_criminal import team_scheme_names
            return team_scheme_names()
        from app.lol.horse_rating import horse_scheme_names
        return horse_scheme_names()

    def __isBuiltin(self, key) -> bool:
        if self.isTeam:
            from app.lol.war_criminal import BUILTIN_TEAM_KEYS
            return key in BUILTIN_TEAM_KEYS
        from app.lol.horse_rating import HORSE_BUILTIN_KEY
        return key == HORSE_BUILTIN_KEY

    def __builtinKeys(self) -> list:
        if self.isTeam:
            from app.lol.war_criminal import BUILTIN_TEAM_KEYS
            return list(BUILTIN_TEAM_KEYS)
        from app.lol.horse_rating import HORSE_BUILTIN_KEY
        return [HORSE_BUILTIN_KEY]

    def __displayName(self, key) -> str:
        if self.isTeam:
            from app.lol.war_criminal import display_name_of
            return display_name_of(key)
        from app.lol.horse_rating import horse_display_name
        return horse_display_name(key)

    def __userSchemes(self) -> dict:
        if self.isTeam:
            from app.lol.war_criminal import _user_team_schemes
            return _user_team_schemes()
        from app.lol.horse_rating import _user_horse_schemes
        return _user_horse_schemes()

    def __styleConfig(self):
        if self.isTeam:
            from app.common.config import cfg
            return cfg, cfg.teamRatingSchemes
        from app.common.config import cfg
        return cfg, cfg.horseRatingSchemes

    def __randomLabel(self) -> str:
        if self.isTeam:
            from app.lol.war_criminal import RANDOM_TEAM_KEY
            return RANDOM_TEAM_KEY
        from app.lol.horse_rating import HORSE_RANDOM_KEY
        return HORSE_RANDOM_KEY

    def __effectiveOption(self) -> str:
        """当前配置风格值; 旧版 'custom' 别名映射为 '自定义' 迁移方案."""
        opt = qconfig.get(self.configItem)
        return '自定义' if opt == 'custom' else opt

    # ------------------------------------------------------------------
    # 下拉构造 / 状态应用
    # ------------------------------------------------------------------
    def __reloadCombo(self):
        self.comboBox.blockSignals(True)
        self.comboBox.clear()
        for key in self.__schemeNames():
            self.comboBox.addItem(self.__displayName(key), userData=key)
        self.comboBox.addItem(self.tr(self.__randomLabel()), userData=self.__randomLabel())
        self.comboBox.addItem(self.tr("新增方案"), userData=self._NEW_MARKER)

        cur = self.__effectiveOption()
        idx = self.__findIndex(cur)
        self.comboBox.setCurrentIndex(idx)
        self.comboBox.blockSignals(False)

    def __findIndex(self, key) -> int:
        for i in range(self.comboBox.count()):
            if self.comboBox.itemData(i) == key:
                return i
        return 0

    def __onCurrentIndexChanged(self, index):
        option = self.comboBox.itemData(index)
        # 新增方案: 进入内嵌创作态 (选中即展开, 保存才落盘)
        if option == self._NEW_MARKER:
            self.__enterNew()
            return
        self._pendingNew = False
        qconfig.set(self.configItem, option)
        self.__applyState()

    def __applyState(self):
        option = self.__effectiveOption()
        isCompose = self._pendingNew
        isEditable = isCompose or option in self.__userSchemes()

        self.card.expandButton.setVisible(isEditable)

        self.nameEdit.setVisible(isEditable)
        self.nameHint.setVisible(isEditable)
        self.templateCombo.setVisible(isEditable)
        self.templateHint.setVisible(isEditable)
        self.__setEditsEnabled(isEditable)
        self.saveButton.setEnabled(isEditable)
        self.deleteButton.setEnabled(isEditable)

        if isCompose:
            self.saveButton.setText(self.tr("创建"))
            self._expandIfVisible()
            return

        self.saveButton.setText(self.tr("保存"))
        if isEditable:
            self.nameEdit.setText(self.__displayName(option))
            self.__loadScheme(option)
            self._expandIfVisible()
        else:
            self.setExpand(False)

    def _expandIfVisible(self):
        if self.isVisible():
            self._adjustViewSize()
            self.setExpand(True)

    def __setEditsEnabled(self, enabled: bool):
        if self.isTeam:
            for e in (self.winEdits + self.lossEdits
                      + self.winComEdits + self.lossComEdits):
                e.setEnabled(enabled)
        else:
            for e in self.labelEdits:
                e.setEnabled(enabled)

    def __enterNew(self):
        """进入内嵌创作态: 自动命名 + 以默认内置方案为基底, 不落盘."""
        self._pendingNew = True
        self.templateCombo.blockSignals(True)
        self.templateCombo.setCurrentIndex(0)
        self.templateCombo.blockSignals(False)
        self.nameEdit.setText(self.__nextNewName())
        self.__loadTemplate(self.__builtinKeys()[0])
        self.__applyState()
        self.nameEdit.setFocus()
        self.nameEdit.selectAll()

    def __nextNewName(self) -> str:
        used = set(self.__schemeNames())
        name = self.tr("自定义")
        i = 0
        while name in used:
            i += 1
            name = f"{self.tr('自定义')}{i}"
        return name

    def __rebuildTemplateCombo(self):
        self.templateCombo.blockSignals(True)
        self.templateCombo.clear()
        for key in self.__builtinKeys():
            self.templateCombo.addItem(self.__displayName(key), userData=key)
        self.templateCombo.setCurrentIndex(0)
        self.templateCombo.blockSignals(False)

    def __onTemplateChanged(self, index):
        key = self.templateCombo.itemData(index)
        if key is not None:
            self.__loadTemplate(key)

    def __loadTemplate(self, key: str):
        """以内置方案为基底填充编辑区 (仅修改表单, 不落盘)."""
        if self.isTeam:
            from app.lol.war_criminal import _builtin_team_scheme
            base = _builtin_team_scheme(key)
            for i in range(5):
                self.winEdits[i].setText(str(base['win'][i]))
                self.lossEdits[i].setText(str(base['loss'][i]))
                self.winComEdits[i].setText(str(base['winComment'][i]))
                self.lossComEdits[i].setText(str(base['lossComment'][i]))
        else:
            from app.lol.horse_rating import _horse_scheme
            for i, label in enumerate(_horse_scheme(key)):
                self.labelEdits[i].setText(str(label))

    # ------------------------------------------------------------------
    # 方案内容读写 (用户方案)
    # ------------------------------------------------------------------
    def __loadScheme(self, name: str):
        schemes = self.__userSchemes()
        s = schemes.get(name) or {}
        if self.isTeam:
            win = s.get('win') or [''] * 5
            loss = s.get('loss') or [''] * 5
            wc = s.get('winComment') or [''] * 5
            lc = s.get('lossComment') or [''] * 5
            for i in range(5):
                self.winEdits[i].setText(str(win[i]) if i < len(win) else '')
                self.lossEdits[i].setText(str(loss[i]) if i < len(loss) else '')
                self.winComEdits[i].setText(str(wc[i]) if i < len(wc) else '')
                self.lossComEdits[i].setText(str(lc[i]) if i < len(lc) else '')
        else:
            labels = s.get('win') or [''] * 6
            for i in range(6):
                self.labelEdits[i].setText(str(labels[i]) if i < len(labels) else '')

    def __gatherScheme(self) -> dict:
        if self.isTeam:
            return {
                'win': [e.text() for e in self.winEdits],
                'loss': [e.text() for e in self.lossEdits],
                'winComment': [e.text() for e in self.winComEdits],
                'lossComment': [e.text() for e in self.lossComEdits],
            }
        return {'win': [e.text() for e in self.labelEdits]}

    def __onSaveClicked(self):
        current = self.__effectiveOption()
        name = (self.nameEdit.text() or "").strip()
        if not name:
            from app.common.qfluentwidgets import InfoBar, InfoBarPosition
            InfoBar.warning(self.tr("方案名为空"), self.tr("请输入方案名后保存"),
                            parent=self, position=InfoBarPosition.BOTTOM_RIGHT)
            return
        if name in self.__schemeNames() and name != current:
            from app.common.qfluentwidgets import InfoBar, InfoBarPosition
            InfoBar.error(self.tr("方案名重复"), self.tr("该名称已被使用"),
                          parent=self, position=InfoBarPosition.BOTTOM_RIGHT)
            return

        _, schemecfg = self.__styleConfig()
        schemes = dict(qconfig.get(schemecfg) or {})
        if not self._pendingNew and name != current:
            schemes.pop(current, None)
        schemes[name] = self.__gatherScheme()
        qconfig.set(schemecfg, schemes)
        qconfig.set(self.configItem, name)
        self._pendingNew = False
        self.__reloadCombo()
        self.comboBox.setCurrentIndex(self.__findIndex(name))

        from app.common.qfluentwidgets import InfoBar, InfoBarPosition
        InfoBar.success(self.tr("已保存"), self.tr("方案已更新"),
                        parent=self, position=InfoBarPosition.BOTTOM_RIGHT)

    def __onDeleteClicked(self):
        if self._pendingNew:
            # 创作态: 放弃 -> 回跳到当前配置方案
            self._pendingNew = False
            self.comboBox.setCurrentIndex(self.__findIndex(self.__effectiveOption()))
            return
        name = self.__effectiveOption()
        if name not in self.__userSchemes():
            return
        _, schemecfg = self.__styleConfig()
        schemes = dict(qconfig.get(schemecfg) or {})
        schemes.pop(name, None)
        qconfig.set(schemecfg, schemes)
        qconfig.set(self.configItem, self.configItem.defaultValue)
        self.__reloadCombo()
        # __reloadCombo 内 blockSignals 已定位到 defaultValue 项;
        # 这里仅刷新按钮/编辑区状态, 不再裸触发 currentIndexChanged
        self.comboBox.blockSignals(True)
        self.comboBox.setCurrentIndex(self.__findIndex(self.__effectiveOption()))
        self.comboBox.blockSignals(False)
        self.__applyState()

    # 保持既有外观/尺寸行为
    def showEvent(self, e):
        super().showEvent(e)
        if self._pendingNew or self.__effectiveOption() in self.__userSchemes():
            self._adjustViewSize()
            self.setExpand(True)

    def toggleExpand(self):
        option = self.__effectiveOption()
        if self._pendingNew or option in self.__userSchemes():
            super().toggleExpand()
        else:
            self.setExpand(False)


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
