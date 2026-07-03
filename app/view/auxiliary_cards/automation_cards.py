from PyQt5.QtCore import Qt, QSize, QObject
from PyQt5.QtWidgets import QWidget, QLabel, QHBoxLayout, QGridLayout
from app.common.config import cfg
from app.common.icons import Icon
from app.common.qfluentwidgets import PushButton, setCustomStyleSheet, ComboBox, SwitchButton, ConfigItem, qconfig, IndicatorPosition, SpinBox, ExpandGroupSettingCard, TransparentToolButton, FluentIcon, Flyout, FlyoutAnimationType, ToolTipFilter, ToolTipPosition
from app.components.champion_icon_widget import SummonerSpellButton
from app.components.message_box import MultiChampionSelectMsgBox
from app.components.summoner_spell_widget import SummonerSpellSelectFlyout
from app.lol.connector import connector
from app.view.auxiliary_cards.hextech_cards import ChampionsCard


class AutoAcceptMatchingCard(ExpandGroupSettingCard):
    def __init__(self, title, content, enableConfigItem: ConfigItem = None,
                 delayConfigItem: ConfigItem = None, parent=None, delayRange=(0, 11),
                 delayLabelText=None):
        super().__init__(Icon.CIRCLEMARK, title, content, parent)

        self.statusLabel = QLabel(self)

        self.inputWidget = QWidget(self.view)
        self.inputLayout = QHBoxLayout(self.inputWidget)

        self.secondsLabel = QLabel(self)
        self._delayLabelText = delayLabelText
        self.lineEdit = SpinBox()

        self.switchButtonWidget = QWidget(self.view)
        self.switchButtonLayout = QHBoxLayout(self.switchButtonWidget)

        self.switchButton = SwitchButton(indicatorPos=IndicatorPosition.RIGHT)

        self.enableConfigItem = enableConfigItem
        self.delayConfigItem = delayConfigItem
        self._delayRange = delayRange

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
        self.secondsLabel.setText(
            self._delayLabelText or self.tr("Delay seconds after match made:"))
        self.lineEdit.setRange(*self._delayRange)
        self.lineEdit.setValue(cfg.get(self.delayConfigItem))
        self.lineEdit.setSingleStep(1)
        self.lineEdit.setMinimumWidth(250)

        self.switchButton.setChecked(cfg.get(self.enableConfigItem))

        self.lineEdit.valueChanged.connect(self.__onLineEditValueChanged)
        self.switchButton.checkedChanged.connect(
            self.__onSwitchButtonCheckedChanged)

        value, isChecked = self.lineEdit.value(), self.switchButton.isChecked()
        self.__setStatusLableText(value, isChecked)

    def setValue(self, delay: int, isChecked: bool):
        qconfig.set(self.delayConfigItem, delay)
        qconfig.set(self.enableConfigItem, isChecked)

        self.__setStatusLableText(delay, isChecked)

    def __onSwitchButtonCheckedChanged(self, isChecked: bool):
        self.setValue(self.lineEdit.value(), isChecked)

    def __onLineEditValueChanged(self, value):
        self.setValue(value, self.switchButton.isChecked())

    def __setStatusLableText(self, delay, isChecked):
        if isChecked:
            self.statusLabel.setText(self.tr("Enabled, delay: ") + str(delay) +
                                     self.tr(" seconds"))
        else:
            self.statusLabel.setText(self.tr("Disabled"))

class AutoHonorCard(ExpandGroupSettingCard):
    """EndOfGame 自动点赞设置卡片: 开关 + 延迟 + 策略选择."""

    # 策略值到本地化文案的映射 (显示文案 -> config 值, 反向用 _strategyValueMap)
    _STRATEGY_ITEMS = [
        ("friends_first", "好友优先"),
        ("friends_only", "仅好友"),
        ("best_score", "最高评分"),
        ("random", "随机"),
    ]

    def __init__(self, title, content,
                 enableConfigItem: ConfigItem = None,
                 delayConfigItem: ConfigItem = None,
                 strategyConfigItem: ConfigItem = None,
                 parent=None):
        super().__init__(FluentIcon.HEART, title, content, parent)

        self.statusLabel = QLabel(self)

        self.inputWidget = QWidget(self.view)
        self.inputLayout = QHBoxLayout(self.inputWidget)

        self.delayLabel = QLabel(self)
        self.lineEdit = SpinBox()

        self.strategyLabel = QLabel(self)
        self.strategyComboBox = ComboBox()

        self.switchButtonWidget = QWidget(self.view)
        self.switchButtonLayout = QHBoxLayout(self.switchButtonWidget)
        self.switchButton = SwitchButton(indicatorPos=IndicatorPosition.RIGHT)

        self.enableConfigItem = enableConfigItem
        self.delayConfigItem = delayConfigItem
        self.strategyConfigItem = strategyConfigItem

        # 反向映射: 本地化文案 -> config 值
        self._strategyValueMap = {}
        for value, text in self._STRATEGY_ITEMS:
            self._strategyValueMap[self.tr(text)] = value

        self.__initLayout()
        self.__initWidget()

    def __initLayout(self):
        self.addWidget(self.statusLabel)

        self.inputLayout.setSpacing(19)
        self.inputLayout.setAlignment(Qt.AlignTop)
        self.inputLayout.setContentsMargins(48, 18, 44, 18)

        self.inputLayout.addWidget(self.delayLabel, alignment=Qt.AlignLeft)
        self.inputLayout.addWidget(self.lineEdit, alignment=Qt.AlignLeft)
        self.inputLayout.addSpacing(20)
        self.inputLayout.addWidget(self.strategyLabel, alignment=Qt.AlignLeft)
        self.inputLayout.addWidget(self.strategyComboBox, alignment=Qt.AlignRight)
        self.inputLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.switchButtonLayout.setContentsMargins(48, 18, 44, 18)
        self.switchButtonLayout.addWidget(self.switchButton, 0, Qt.AlignRight)
        self.switchButtonLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.viewLayout.setSpacing(0)
        self.viewLayout.setContentsMargins(0, 0, 0, 0)
        self.addGroupWidget(self.inputWidget)
        self.addGroupWidget(self.switchButtonWidget)

    def __initWidget(self):
        self.delayLabel.setText(self.tr("游戏结束后延迟秒数："))
        self.lineEdit.setRange(0, 5)
        self.lineEdit.setValue(cfg.get(self.delayConfigItem))
        self.lineEdit.setSingleStep(1)
        self.lineEdit.setMinimumWidth(120)

        self.strategyLabel.setText(self.tr("点赞策略："))
        for value, text in self._STRATEGY_ITEMS:
            self.strategyComboBox.addItem(self.tr(text), userData=value)
        # 选中当前 config 值
        currentStrategy = cfg.get(self.strategyConfigItem)
        for i in range(self.strategyComboBox.count()):
            if self.strategyComboBox.itemData(i) == currentStrategy:
                self.strategyComboBox.setCurrentIndex(i)
                break
        self.strategyComboBox.setMinimumWidth(160)

        self.switchButton.setChecked(cfg.get(self.enableConfigItem))

        self.lineEdit.valueChanged.connect(self.__onLineEditValueChanged)
        self.switchButton.checkedChanged.connect(
            self.__onSwitchButtonCheckedChanged)
        self.strategyComboBox.currentIndexChanged.connect(
            self.__onStrategyChanged)

        self.__setStatusLabelText()

    def __onLineEditValueChanged(self, value):
        qconfig.set(self.delayConfigItem, value)
        self.__setStatusLabelText()

    def __onSwitchButtonCheckedChanged(self, isChecked: bool):
        qconfig.set(self.enableConfigItem, isChecked)
        self.__setStatusLabelText()

    def __onStrategyChanged(self, index: int):
        value = self.strategyComboBox.itemData(index)
        if value:
            qconfig.set(self.strategyConfigItem, value)

    def __setStatusLabelText(self):
        if self.switchButton.isChecked():
            self.statusLabel.setText(
                self.tr("已启用，延迟：") + str(self.lineEdit.value()) +
                self.tr(" 秒，策略：") +
                self.strategyComboBox.currentText())
        else:
            self.statusLabel.setText(self.tr("已禁用"))

class AutoAcceptMsCard(ExpandGroupSettingCard):
    """自动接受对局 (毫秒随机延迟 + 反悔权限)."""

    def __init__(self, title, content,
                 enableConfigItem=None,
                 minMsConfigItem=None,
                 maxMsConfigItem=None,
                 declineEnabledConfigItem=None,
                 parent=None):
        super().__init__(Icon.CIRCLEMARK, title, content, parent)

        self.statusLabel = QLabel(self)

        self.inputWidget = QWidget(self.view)
        self.inputLayout = QHBoxLayout(self.inputWidget)

        self.minLabel = QLabel(self)
        self.minSpinBox = SpinBox()
        self.maxLabel = QLabel(self)
        self.maxSpinBox = SpinBox()

        self.declineWidget = QWidget(self.view)
        self.declineLayout = QHBoxLayout(self.declineWidget)
        self.declineLabel = QLabel(self)
        self.declineSwitch = SwitchButton(indicatorPos=IndicatorPosition.RIGHT)

        self.switchButtonWidget = QWidget(self.view)
        self.switchButtonLayout = QHBoxLayout(self.switchButtonWidget)
        self.switchButton = SwitchButton(indicatorPos=IndicatorPosition.RIGHT)

        self.enableConfigItem = enableConfigItem
        self.minMsConfigItem = minMsConfigItem
        self.maxMsConfigItem = maxMsConfigItem
        self.declineEnabledConfigItem = declineEnabledConfigItem

        self.__initLayout()
        self.__initWidget()

    def __initLayout(self):
        self.addWidget(self.statusLabel)

        self.inputLayout.setSpacing(19)
        self.inputLayout.setAlignment(Qt.AlignTop)
        self.inputLayout.setContentsMargins(48, 18, 44, 18)
        self.inputLayout.addWidget(self.minLabel, alignment=Qt.AlignLeft)
        self.inputLayout.addWidget(self.minSpinBox, alignment=Qt.AlignLeft)
        self.inputLayout.addSpacing(8)
        self.inputLayout.addWidget(self.maxLabel, alignment=Qt.AlignLeft)
        self.inputLayout.addWidget(self.maxSpinBox, alignment=Qt.AlignRight)
        self.inputLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.declineLayout.setContentsMargins(48, 18, 44, 18)
        self.declineLayout.addWidget(self.declineLabel, 0, Qt.AlignLeft)
        self.declineLayout.addWidget(self.declineSwitch, 0, Qt.AlignRight)
        self.declineLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.switchButtonLayout.setContentsMargins(48, 18, 44, 18)
        self.switchButtonLayout.addWidget(self.switchButton, 0, Qt.AlignRight)
        self.switchButtonLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.viewLayout.setSpacing(0)
        self.viewLayout.setContentsMargins(0, 0, 0, 0)
        self.addGroupWidget(self.inputWidget)
        self.addGroupWidget(self.declineWidget)
        self.addGroupWidget(self.switchButtonWidget)

    def __initWidget(self):
        self.minLabel.setText(self.tr("Min delay (ms):"))
        self.minSpinBox.setRange(0, 15000)
        self.minSpinBox.setValue(cfg.get(self.minMsConfigItem))
        self.minSpinBox.setSingleStep(100)
        self.minSpinBox.setMinimumWidth(120)

        self.maxLabel.setText(self.tr("Max delay (ms):"))
        self.maxSpinBox.setRange(0, 15000)
        self.maxSpinBox.setValue(cfg.get(self.maxMsConfigItem))
        self.maxSpinBox.setSingleStep(100)
        self.maxSpinBox.setMinimumWidth(120)

        self.declineLabel.setText(self.tr("Allow declining after auto-accept:"))
        self.declineSwitch.setChecked(cfg.get(self.declineEnabledConfigItem))

        self.switchButton.setChecked(cfg.get(self.enableConfigItem))

        self.minSpinBox.valueChanged.connect(self.__save)
        self.maxSpinBox.valueChanged.connect(self.__save)
        self.declineSwitch.checkedChanged.connect(self.__save)
        self.switchButton.checkedChanged.connect(self.__save)

        self.__updateStatus()

    def __save(self):
        qconfig.set(self.minMsConfigItem, self.minSpinBox.value())
        qconfig.set(self.maxMsConfigItem, self.maxSpinBox.value())
        qconfig.set(self.declineEnabledConfigItem, self.declineSwitch.isChecked())
        qconfig.set(self.enableConfigItem, self.switchButton.isChecked())
        self.__updateStatus()

    def __updateStatus(self):
        if self.switchButton.isChecked():
            self.statusLabel.setText(
                self.tr("Enabled, delay: ") +
                f"{self.minSpinBox.value()}~{self.maxSpinBox.value()}ms" +
                (self.tr(", decline allowed") if self.declineSwitch.isChecked()
                 else self.tr(", decline disabled")))
        else:
            self.statusLabel.setText(self.tr("Disabled"))


class AutoAcceptSwapingCard(ExpandGroupSettingCard):
    def __init__(self, title, content, enableCeilSwapItem: ConfigItem = None,
                 enableChampSwapItem: ConfigItem = None, parent=None):
        super().__init__(Icon.TEXTCHECK, title, content, parent)

        self.statusLabel = QLabel(self)

        self.switchButtonWidget = QWidget(self.view)
        self.switchButtonLayout = QGridLayout(self.switchButtonWidget)

        self.label1 = QLabel(self.tr("Enable auto accept cail swap request:"))
        self.label2 = QLabel(
            self.tr("Enable auto accept champion trade request:"))

        self.switchButton1 = SwitchButton(indicatorPos=IndicatorPosition.RIGHT)
        self.switchButton2 = SwitchButton(indicatorPos=IndicatorPosition.RIGHT)

        self.enableCeilSwapItem = enableCeilSwapItem
        self.enableChampSwapItem = enableChampSwapItem

        self.__initLayout()
        self.__initWidget()

    def __initLayout(self):
        self.addWidget(self.statusLabel)

        self.switchButtonLayout.setVerticalSpacing(19)
        self.switchButtonLayout.addWidget(self.label1, 0, 0, Qt.AlignLeft)
        self.switchButtonLayout.addWidget(
            self.switchButton1, 0, 1, Qt.AlignRight)
        self.switchButtonLayout.addWidget(
            self.label2, 1, 0, Qt.AlignLeft)
        self.switchButtonLayout.addWidget(
            self.switchButton2, 1, 1, Qt.AlignRight)

        self.switchButtonLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)
        self.switchButtonLayout.setContentsMargins(48, 24, 44, 28)

        self.viewLayout.setSpacing(0)
        self.viewLayout.setContentsMargins(0, 0, 0, 0)
        self.addGroupWidget(self.switchButtonWidget)

    def __initWidget(self):
        ceilSwap = cfg.get(cfg.autoAcceptCeilSwap)
        champTrade = cfg.get(cfg.autoAcceptChampTrade)

        self.switchButton1.setChecked(ceilSwap)
        self.switchButton2.setChecked(champTrade)

        self.__setStatusLableText()

        self.switchButton1.checkedChanged.connect(
            self.__onSwichButton1CheckedChanged)
        self.switchButton2.checkedChanged.connect(
            self.__onSwichButton2CheckedChanged)

    def __onSwichButton1CheckedChanged(self, isChecked: bool):
        cfg.set(cfg.autoAcceptCeilSwap, isChecked)
        self.__setStatusLableText()

    def __onSwichButton2CheckedChanged(self, isChecked: bool):
        cfg.set(cfg.autoAcceptChampTrade, isChecked)
        self.__setStatusLableText()

    def __setStatusLableText(self):
        ceilSwap = self.switchButton1.isChecked()
        champTrade = self.switchButton2.isChecked()

        if any([ceilSwap, champTrade]):
            self.statusLabel.setText(self.tr("Enabled"))
        else:
            self.statusLabel.setText(self.tr("Disabled"))

class AutoSelectChampionCard(ExpandGroupSettingCard):
    def __init__(self, title, content=None,
                 enableConfigItem: ConfigItem = None,
                 championsConfigItem: ConfigItem = None,
                 topChampionsConfigItem: ConfigItem = None,
                 jugChampionsConfigItem: ConfigItem = None,
                 midChampionsConfigItem: ConfigItem = None,
                 botChampionsConfigItem: ConfigItem = None,
                 supChampionsConfigItem: ConfigItem = None,
                 enableTimeoutCompleteCfgItem: ConfigItem = None,
                 parent=None):
        super().__init__(Icon.CHECK, title, content, parent)

        self.champions = {}

        self.enableConfigItem = enableConfigItem
        self.defaultChampionsConfigItem = championsConfigItem
        self.topChampionsConfigItem = topChampionsConfigItem
        self.jugChampionsConfigItem = jugChampionsConfigItem
        self.midChampionsConfigItem = midChampionsConfigItem
        self.botChampionsConfigItem = botChampionsConfigItem
        self.supChampionsConfigItem = supChampionsConfigItem
        self.enableTimeoutCompleteCfgItem = enableTimeoutCompleteCfgItem

        self.statusLabel = QLabel()

        self.defaultCfgWidget = QWidget(self.view)
        self.defaultCfgLayout = QGridLayout(self.defaultCfgWidget)
        self.defaultHintLabel = QLabel(self.tr("Default Configurations"))
        self.helpLayout = QHBoxLayout()
        self.helpButotn = TransparentToolButton(Icon.QUESTION_CIRCLE)

        self.defaultLabel = QLabel(self.tr("Default champions: "))
        self.defaultChampions = ChampionsCard()
        self.defaultSelectButton = PushButton(self.tr("Choose"))

        self.rankCfgWidget = QWidget(self.view)
        self.rankCfgLayout = QGridLayout(self.rankCfgWidget)
        self.rankLabel = QLabel(self.tr("Rank Configurations"))

        self.topLabel = QLabel(self.tr("Top: "))
        self.jugLabel = QLabel(self.tr("Juggle: "))
        self.midLabel = QLabel(self.tr("Mid: "))
        self.botLabel = QLabel(self.tr("Bottom: "))
        self.supLabel = QLabel(self.tr("Support: "))
        self.topChampions = ChampionsCard()
        self.jugChampions = ChampionsCard()
        self.midChampions = ChampionsCard()
        self.botChampions = ChampionsCard()
        self.supChampions = ChampionsCard()
        self.topSelectButton = PushButton(self.tr("Choose"))
        self.jugSelectButton = PushButton(self.tr("Choose"))
        self.midSelectButton = PushButton(self.tr("Choose"))
        self.botSelectButton = PushButton(self.tr("Choose"))
        self.supSelectButton = PushButton(self.tr("Choose"))

        self.buttonsWidget = QWidget(self.view)
        self.buttonsLayout = QGridLayout(self.buttonsWidget)
        self.enableLabel = QLabel(self.tr("Enable:"))
        self.enableSwitchButton = SwitchButton(
            indicatorPos=IndicatorPosition.RIGHT)
        self.enableTimeoutCompleteLabel = QLabel(
            self.tr("Completed before timeout:"))
        self.enableTimeoutSwtichButton = SwitchButton(
            indicatorPos=IndicatorPosition.RIGHT)
        self.resetButton = PushButton(self.tr("Reset"))

        self.__initWidget()
        self.__initLayout()

    def __initWidget(self):
        self.defaultHintLabel.setStyleSheet("font: bold")
        self.rankLabel.setStyleSheet("font: bold")

        self.helpButotn.setFixedSize(QSize(26, 26))
        self.helpButotn.setIconSize(QSize(16, 16))

        self.helpButotn.setToolTip(self.tr(
            "Default settings must be set.\n\nIf champions set by lane are not available, default settings will be used."))
        self.helpButotn.installEventFilter(ToolTipFilter(
            self.helpButotn, 0, ToolTipPosition.RIGHT))

        # 逻辑是，必须要设置默认，才能设置具体分路和启动功能
        selected = qconfig.get(self.defaultChampionsConfigItem) != []
        checked = qconfig.get(self.enableConfigItem)
        timeoutChecked = qconfig.get(self.enableTimeoutCompleteCfgItem)

        for ty in ['default', 'top', 'jug', 'mid', 'bot', 'sup']:
            button: PushButton = getattr(self, f"{ty}SelectButton")
            button.setMinimumWidth(100)
            button.clicked.connect(lambda _, t=ty: self.__onButtonClicked(t))

            if ty != 'default':
                button.setEnabled(selected)

        self.enableSwitchButton.checkedChanged.connect(
            self.__onEnableSelectChanged)
        self.enableSwitchButton.setEnabled(selected)
        self.enableSwitchButton.setChecked(checked)

        self.enableTimeoutSwtichButton.checkedChanged.connect(
            self.__onEnableTimeoutCompleteChanged)
        self.enableTimeoutSwtichButton.setEnabled(checked)
        self.enableTimeoutSwtichButton.setChecked(timeoutChecked)

        self.resetButton.clicked.connect(self.__onResetButtonClicked)
        self.resetButton.setMinimumWidth(100)

        self.__updateStatusLabel()

    def __initLayout(self):
        self.addWidget(self.statusLabel)

        self.defaultCfgLayout.setVerticalSpacing(19)
        self.defaultCfgLayout.setContentsMargins(48, 18, 44, 18)
        self.defaultCfgLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.helpLayout.setContentsMargins(0, 0, 0, 0)
        self.helpLayout.setSpacing(10)
        self.helpLayout.addWidget(self.defaultHintLabel)
        self.helpLayout.addWidget(self.helpButotn)

        self.defaultCfgLayout.addLayout(
            self.helpLayout, 0, 0, Qt.AlignLeft)

        self.defaultCfgLayout.addWidget(
            self.defaultLabel, 1, 0, Qt.AlignLeft)
        self.defaultCfgLayout.addWidget(
            self.defaultChampions, 1, 1, Qt.AlignHCenter)
        self.defaultCfgLayout.addWidget(
            self.defaultSelectButton, 1, 2, Qt.AlignRight)

        self.rankCfgLayout.setVerticalSpacing(19)
        self.rankCfgLayout.setContentsMargins(48, 18, 44, 18)
        self.rankCfgLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.rankCfgLayout.addWidget(self.rankLabel, 0, 0, Qt.AlignLeft)

        for i, ty in enumerate(['top', 'jug', 'mid', 'bot', 'sup']):
            label = getattr(self, f"{ty}Label")
            champions = getattr(self, f"{ty}Champions")
            button = getattr(self, f"{ty}SelectButton")

            self.rankCfgLayout.addWidget(label, i + 1, 0, Qt.AlignLeft)
            self.rankCfgLayout.addWidget(champions, i + 1, 1, Qt.AlignHCenter)
            self.rankCfgLayout.addWidget(button, i + 1, 2, Qt.AlignRight)

        self.buttonsLayout.setVerticalSpacing(19)
        self.buttonsLayout.setContentsMargins(48, 18, 44, 18)
        self.buttonsLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.buttonsLayout.addWidget(
            self.enableLabel, 0, 0, Qt.AlignLeft)
        self.buttonsLayout.addWidget(
            self.enableSwitchButton, 0, 1, Qt.AlignRight)
        self.buttonsLayout.addWidget(
            self.enableTimeoutCompleteLabel, 1, 0, Qt.AlignLeft)
        self.buttonsLayout.addWidget(
            self.enableTimeoutSwtichButton, 1, 1, Qt.AlignRight)
        self.buttonsLayout.addWidget(
            self.resetButton, 2, 1, Qt.AlignRight)

        self.viewLayout.setSpacing(0)
        self.viewLayout.setContentsMargins(0, 0, 0, 0)

        self.addGroupWidget(self.defaultCfgWidget)
        self.addGroupWidget(self.rankCfgWidget)
        self.addGroupWidget(self.buttonsWidget)

    async def initChampionList(self, champions: dict = None):
        if champions:
            self.champions = champions
        else:
            self.champions = {
                i: [name, await connector.getChampionIcon(i)]
                for i, name in connector.manager.getChampions().items()
                if i != -1
            }

        for ty in ['default', 'top', 'jug', 'mid', 'bot', 'sup']:
            configItem = getattr(self, f"{ty}ChampionsConfigItem")
            champions: ChampionsCard = getattr(self, f"{ty}Champions")
            selected = qconfig.get(configItem)

            champions.clearRequested.connect(
                lambda t=ty: self.__onChampionsChanged([], t))

            if not (type(selected) is list and all(type(s) is int for s in selected)):
                selected = []
                qconfig.set(configItem, selected)

            if len(selected) == 0:
                continue

            champions.updateChampions(
                [self.champions[id][1] for id in selected])

        return self.champions

    def __onButtonClicked(self, type: str):
        configItem: ConfigItem = getattr(self, f"{type}ChampionsConfigItem")
        selected = qconfig.get(configItem)

        box = MultiChampionSelectMsgBox(
            self.champions, selected, self.window())
        box.completed.connect(
            lambda champions, t=type: self.__onChampionsChanged(champions, t))
        box.exec()

    def __onChampionsChanged(self, champions: list, type: str):
        configItem = getattr(self, f"{type}ChampionsConfigItem")
        qconfig.set(configItem, champions)

        card: ChampionsCard = getattr(self, f"{type}Champions")
        card.updateChampions(
            [self.champions[id][1] for id in champions])

        if type != 'default':
            return

        if len(champions) == 0:
            self.enableSwitchButton.setChecked(False)
            self.enableSwitchButton.setEnabled(False)
            self.enableTimeoutSwtichButton.setChecked(False)
            self.enableTimeoutSwtichButton.setEnabled(False)
            buttonEnable = False
        else:
            self.enableSwitchButton.setEnabled(True)
            buttonEnable = True

        for ty in ['top', 'jug', 'mid', 'bot', 'sup']:
            button: PushButton = getattr(self, f"{ty}SelectButton")
            button.setEnabled(buttonEnable)

    def __onEnableSelectChanged(self, checked):
        qconfig.set(self.enableConfigItem, checked)

        for ty in ['default', 'top', 'jug', 'mid', 'bot', 'sup']:
            button: PushButton = getattr(self, f"{ty}SelectButton")
            button.setEnabled(not checked)

        self.enableTimeoutSwtichButton.setEnabled(checked)

        if not checked:
            self.enableTimeoutSwtichButton.setChecked(False)

        self.__updateStatusLabel()

    def __onEnableTimeoutCompleteChanged(self, checked):
        qconfig.set(self.enableTimeoutCompleteCfgItem, checked)

    def __updateStatusLabel(self):
        checked = self.enableSwitchButton.isChecked()

        text = self.tr("Enabled") if checked else self.tr("Disabled")
        self.statusLabel.setText(text)

    def __onResetButtonClicked(self):
        for ty in ['default', 'top', 'jug', 'mid', 'bot', 'sup']:
            self.__onChampionsChanged([], ty)

class AutoBanChampionCard(ExpandGroupSettingCard):
    def __init__(self, title, content=None,
                 enableConfigItem: ConfigItem = None,
                 championsConfigItem: ConfigItem = None,
                 topChampionsConfigItem: ConfigItem = None,
                 jugChampionsConfigItem: ConfigItem = None,
                 midChampionsConfigItem: ConfigItem = None,
                 botChampionsConfigItem: ConfigItem = None,
                 supChampionsConfigItem: ConfigItem = None,
                 friendlyConfigItem: ConfigItem = None,
                 delayTimeConfigItem: ConfigItem = None, parent=None):
        super().__init__(Icon.SQUARECROSS, title, content, parent)

        self.champions = {}

        self.enableConfigItem = enableConfigItem
        self.defaultChampionsConfigItem = championsConfigItem
        self.topChampionsConfigItem = topChampionsConfigItem
        self.jugChampionsConfigItem = jugChampionsConfigItem
        self.midChampionsConfigItem = midChampionsConfigItem
        self.botChampionsConfigItem = botChampionsConfigItem
        self.supChampionsConfigItem = supChampionsConfigItem

        self.friendlyConfigItem = friendlyConfigItem
        self.delayTimeConfigItem = delayTimeConfigItem

        self.statusLabel = QLabel()

        self.defaultCfgWidget = QWidget(self.view)
        self.defaultCfgLayout = QGridLayout(self.defaultCfgWidget)
        self.defaultHintLabel = QLabel(self.tr("Default Configurations"))
        self.helpLayout = QHBoxLayout()
        self.helpButotn = TransparentToolButton(Icon.QUESTION_CIRCLE)

        self.defaultLabel = QLabel(self.tr("Default champions: "))
        self.defaultChampions = ChampionsCard()
        self.defaultSelectButton = PushButton(self.tr("Choose"))

        self.rankCfgWidget = QWidget(self.view)
        self.rankCfgLayout = QGridLayout(self.rankCfgWidget)
        self.rankLabel = QLabel(self.tr("Rank Configurations"))

        self.topLabel = QLabel(self.tr("Top: "))
        self.jugLabel = QLabel(self.tr("Juggle: "))
        self.midLabel = QLabel(self.tr("Mid: "))
        self.botLabel = QLabel(self.tr("Bottom: "))
        self.supLabel = QLabel(self.tr("Support: "))
        self.topChampions = ChampionsCard()
        self.jugChampions = ChampionsCard()
        self.midChampions = ChampionsCard()
        self.botChampions = ChampionsCard()
        self.supChampions = ChampionsCard()
        self.topSelectButton = PushButton(self.tr("Choose"))
        self.jugSelectButton = PushButton(self.tr("Choose"))
        self.midSelectButton = PushButton(self.tr("Choose"))
        self.botSelectButton = PushButton(self.tr("Choose"))
        self.supSelectButton = PushButton(self.tr("Choose"))

        self.buttonsCfgWidget = QWidget(self.view)
        self.buttonsCfgLayout = QGridLayout(self.buttonsCfgWidget)
        self.delayLabel = QLabel(self.tr("Ban after a delay of seconds:"))
        self.delaySpinBox = SpinBox()
        self.enableLabel = QLabel(self.tr("Enable:"))
        self.enableSwitchButton = SwitchButton(
            indicatorPos=IndicatorPosition.RIGHT)
        self.friendlyLabel = QLabel(
            self.tr("Prevent banning champions picked by teammates:"))
        self.friendlySwitchButton = SwitchButton(
            indicatorPos=IndicatorPosition.RIGHT)

        self.resetButton = PushButton(self.tr("Reset"))

        self.__initWidget()
        self.__initLayout()

    def __initWidget(self):
        self.defaultHintLabel.setStyleSheet("font: bold")
        self.rankLabel.setStyleSheet("font: bold")

        haveDefault = qconfig.get(self.defaultChampionsConfigItem) != []
        enabled = qconfig.get(self.enableConfigItem)
        delayTime = qconfig.get(self.delayTimeConfigItem)
        friendlyEnabled = qconfig.get(self.friendlyConfigItem)

        self.helpButotn.setFixedSize(QSize(26, 26))
        self.helpButotn.setIconSize(QSize(16, 16))

        self.helpButotn.setToolTip(self.tr(
            "Default settings must be set.\n\nIf champions set by lane are not available, default settings will be used."))
        self.helpButotn.installEventFilter(ToolTipFilter(
            self.helpButotn, 0, ToolTipPosition.RIGHT))

        for ty in ['default', 'top', 'jug', 'mid', 'bot', 'sup']:
            button: PushButton = getattr(self, f"{ty}SelectButton")
            button.setMinimumWidth(100)
            button.clicked.connect(lambda _, t=ty: self.__onButtonClicked(t))

            if ty != 'default':
                button.setEnabled(haveDefault)

        self.enableSwitchButton.checkedChanged.connect(
            self.__onEnableSwitchButtonClicked)
        self.delaySpinBox.valueChanged.connect(
            self.__onDelaySpinBoxValueChanged)
        self.friendlySwitchButton.checkedChanged.connect(
            self.__onFriendlySwitchButtonClicked)
        self.resetButton.clicked.connect(self.__onResetButtonClicked)

        self.delaySpinBox.setMinimumWidth(250)
        self.delaySpinBox.setSingleStep(1)
        self.delaySpinBox.setRange(0, 25)
        self.delaySpinBox.setEnabled(haveDefault and not enabled)
        self.delaySpinBox.setValue(delayTime)
        self.enableSwitchButton.setEnabled(haveDefault)
        self.enableSwitchButton.setChecked(enabled)
        self.friendlySwitchButton.setEnabled(enabled)
        self.friendlySwitchButton.setChecked(friendlyEnabled)
        self.resetButton.setMinimumWidth(100)

        self.__updateStatusLabel()
        self.__fixStyleSheetOfSpinBox()

    def __initLayout(self):
        self.addWidget(self.statusLabel)

        self.defaultCfgLayout.setVerticalSpacing(19)
        self.defaultCfgLayout.setContentsMargins(48, 18, 44, 18)
        self.defaultCfgLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.helpLayout.setContentsMargins(0, 0, 0, 0)
        self.helpLayout.setSpacing(10)
        self.helpLayout.addWidget(self.defaultHintLabel)
        self.helpLayout.addWidget(self.helpButotn)

        self.defaultCfgLayout.addLayout(
            self.helpLayout, 0, 0, Qt.AlignLeft)

        self.defaultCfgLayout.addWidget(
            self.defaultLabel, 1, 0, Qt.AlignLeft)
        self.defaultCfgLayout.addWidget(
            self.defaultChampions, 1, 1, Qt.AlignHCenter)
        self.defaultCfgLayout.addWidget(
            self.defaultSelectButton, 1, 2, Qt.AlignRight)

        self.rankCfgLayout.setVerticalSpacing(19)
        self.rankCfgLayout.setContentsMargins(48, 18, 44, 18)
        self.rankCfgLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.rankCfgLayout.addWidget(self.rankLabel, 0, 0, Qt.AlignLeft)

        for i, ty in enumerate(['top', 'jug', 'mid', 'bot', 'sup']):
            label = getattr(self, f"{ty}Label")
            champions = getattr(self, f"{ty}Champions")
            button = getattr(self, f"{ty}SelectButton")

            self.rankCfgLayout.addWidget(label, i + 1, 0, Qt.AlignLeft)
            self.rankCfgLayout.addWidget(champions, i + 1, 1, Qt.AlignHCenter)
            self.rankCfgLayout.addWidget(button, i + 1, 2, Qt.AlignRight)

        self.buttonsCfgLayout.setVerticalSpacing(19)
        self.buttonsCfgLayout.setContentsMargins(48, 18, 44, 18)
        self.buttonsCfgLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.buttonsCfgLayout.addWidget(
            self.delayLabel, 0, 0, Qt.AlignLeft)
        self.buttonsCfgLayout.addWidget(
            self.delaySpinBox, 0, 1, Qt.AlignRight)
        self.buttonsCfgLayout.addWidget(
            self.enableLabel, 1, 0, Qt.AlignLeft)
        self.buttonsCfgLayout.addWidget(
            self.enableSwitchButton, 1, 1, Qt.AlignRight)
        self.buttonsCfgLayout.addWidget(
            self.friendlyLabel, 2, 0, Qt.AlignLeft)
        self.buttonsCfgLayout.addWidget(
            self.friendlySwitchButton, 2, 1, Qt.AlignRight)
        self.buttonsCfgLayout.addWidget(
            self.resetButton, 3, 1, Qt.AlignRight)

        self.viewLayout.setSpacing(0)
        self.viewLayout.setContentsMargins(0, 0, 0, 0)

        self.addGroupWidget(self.defaultCfgWidget)
        self.addGroupWidget(self.rankCfgWidget)
        self.addGroupWidget(self.buttonsCfgWidget)

    async def initChampionList(self, champions: dict = None):
        if champions:
            self.champions = champions
        else:
            self.champions = {
                i: [name, await connector.getChampionIcon(i)]
                for i, name in connector.manager.getChampions().items()
                if i != -1
            }

        for ty in ['default', 'top', 'jug', 'mid', 'bot', 'sup']:
            configItem = getattr(self, f"{ty}ChampionsConfigItem")
            champions: ChampionsCard = getattr(self, f"{ty}Champions")
            selected = qconfig.get(configItem)

            champions.clearRequested.connect(
                lambda t=ty: self.__onChampionsChanged([], t))

            # 原来的配置项里储存字符串，使用 ',' 分隔
            # 现在储存的是 list 类型，其中是 championId
            # 为了兼容老版本的配置文件，这里手动对配置文件进行一下验证 / 重置
            if not (type(selected) is list and all(type(s) is int for s in selected)):
                selected = []
                qconfig.set(configItem, selected)

            if len(selected) == 0:
                continue

            champions.updateChampions(
                [self.champions[id][1] for id in selected])

        return self.champions

    def __onButtonClicked(self, type: str):
        configItem: ConfigItem = getattr(self, f"{type}ChampionsConfigItem")
        selected = qconfig.get(configItem)

        box = MultiChampionSelectMsgBox(
            self.champions, selected, self.window())
        box.completed.connect(
            lambda champions, t=type: self.__onChampionsChanged(champions, t))
        box.exec()

    def __onChampionsChanged(self, champions: list, type: str):
        configItem = getattr(self, f"{type}ChampionsConfigItem")
        qconfig.set(configItem, champions)

        card: ChampionsCard = getattr(self, f"{type}Champions")
        card.updateChampions(
            [self.champions[id][1] for id in champions])

        if type != 'default':
            return

        if len(champions) == 0:
            self.enableSwitchButton.setChecked(False)
            self.enableSwitchButton.setEnabled(False)
            self.friendlySwitchButton.setChecked(False)
            self.friendlySwitchButton.setEnabled(False)
            self.delaySpinBox.setEnabled(False)
            buttonEnable = False
        else:
            self.enableSwitchButton.setEnabled(True)
            self.delaySpinBox.setEnabled(True)
            buttonEnable = True

        for ty in ['top', 'jug', 'mid', 'bot', 'sup']:
            button: PushButton = getattr(self, f"{ty}SelectButton")
            button.setEnabled(buttonEnable)

    def __onEnableSwitchButtonClicked(self, checked):
        qconfig.set(self.enableConfigItem, checked)

        for ty in ['default', 'top', 'jug', 'mid', 'bot', 'sup']:
            button: PushButton = getattr(self, f"{ty}SelectButton")
            button.setEnabled(not checked)

        self.friendlySwitchButton.setEnabled(checked)
        self.delaySpinBox.setEnabled(not checked)

        if not checked:
            self.friendlySwitchButton.setChecked(False)

        self.__updateStatusLabel()

    def __onDelaySpinBoxValueChanged(self, value):
        qconfig.set(self.delayTimeConfigItem, value)

    def __onFriendlySwitchButtonClicked(self, checked):
        qconfig.set(self.friendlyConfigItem, checked)

    def __onResetButtonClicked(self):
        for ty in ['default', 'top', 'jug', 'mid', 'bot', 'sup']:
            self.__onChampionsChanged([], ty)

        self.delaySpinBox.setValue(0)

    def __updateStatusLabel(self):
        checked = self.enableSwitchButton.isChecked()

        text = self.tr("Enabled") if checked else self.tr("Disabled")
        self.statusLabel.setText(text)

    def __fixStyleSheetOfSpinBox(self):
        # 这玩意在深色 + Enabled 为 False 的时候看起来怪怪的，手动改一下
        light = """
            SpinBox:disabled {
                color: rgba(0, 0, 0, 150);
                background-color: rgba(249, 249, 249, 0.3);
                border: 1px solid rgba(0, 0, 0, 13);
                border-bottom: 1px solid rgba(0, 0, 0, 13);
            }
        """

        dark = """
            SpinBox:disabled {
                color: rgba(255, 255, 255, 150);
                background-color: rgba(255, 255, 255, 0.0419);
                border: 1px solid rgba(255, 255, 255, 0.0698);
            }
        """

        setCustomStyleSheet(self.delaySpinBox, light, dark)

class AutoSetSummonerSpellCard(ExpandGroupSettingCard):
    def __init__(self, title, content=None,
                 enableConfigItem: ConfigItem = None,
                 spellConfigItem: ConfigItem = None,
                 topSpellConfigItem: ConfigItem = None,
                 jugSpellConfigItem: ConfigItem = None,
                 midSpellConfigItem: ConfigItem = None,
                 botSpellConfigItem: ConfigItem = None,
                 supSpellConfigItem: ConfigItem = None,
                 parent=None):
        super().__init__(Icon.CHECKBOXFILL, title, content, parent)

        self.spells = {}

        self.enableConfigItem = enableConfigItem
        self.defaultSpellConfigItem = spellConfigItem
        self.topSpellConfigItem = topSpellConfigItem
        self.jugSpellConfigItem = jugSpellConfigItem
        self.midSpellConfigItem = midSpellConfigItem
        self.botSpellConfigItem = botSpellConfigItem
        self.supSpellConfigItem = supSpellConfigItem

        self.statusLabel = QLabel()

        self.defaultCfgWidget = QWidget(self.view)
        self.defaultCfgLayout = QGridLayout(self.defaultCfgWidget)
        self.defaultHintLabel = QLabel(self.tr("Default Configurations"))

        self.defaultLabel = QLabel(self.tr("Default summoner spells: "))
        self.defaultButtonLayout = QHBoxLayout()
        self.defaultSelectButton1 = SummonerSpellButton()
        self.defaultSelectButton2 = SummonerSpellButton()

        self.rankCfgWidget = QWidget(self.view)
        self.rankCfgLayout = QGridLayout(self.rankCfgWidget)
        self.rankLabel = QLabel(self.tr("Rank Configurations"))

        self.topLabel = QLabel(self.tr("Top: "))
        self.jugLabel = QLabel(self.tr("Juggle: "))
        self.midLabel = QLabel(self.tr("Mid: "))
        self.botLabel = QLabel(self.tr("Bottom: "))
        self.supLabel = QLabel(self.tr("Support: "))

        self.topButtonLayout = QHBoxLayout()
        self.topSelectButton1 = SummonerSpellButton()
        self.topSelectButton2 = SummonerSpellButton()
        self.jugButtonLayout = QHBoxLayout()
        self.jugSelectButton1 = SummonerSpellButton()
        self.jugSelectButton2 = SummonerSpellButton()
        self.midButtonLayout = QHBoxLayout()
        self.midSelectButton1 = SummonerSpellButton()
        self.midSelectButton2 = SummonerSpellButton()
        self.botButtonLayout = QHBoxLayout()
        self.botSelectButton1 = SummonerSpellButton()
        self.botSelectButton2 = SummonerSpellButton()
        self.supButtonLayout = QHBoxLayout()
        self.supSelectButton1 = SummonerSpellButton()
        self.supSelectButton2 = SummonerSpellButton()

        self.buttonsWidget = QWidget(self.view)
        self.buttonsLayout = QGridLayout(self.buttonsWidget)
        self.enableHintLabel = QLabel(self.tr("Enable:"))
        self.enableSwitchButton = SwitchButton(
            indicatorPos=IndicatorPosition.RIGHT)
        self.resetButton = PushButton(self.tr("Reset"))

        self.__initWidget()
        self.__initLayout()

    def __initWidget(self):
        # 逻辑是，必须要设置默认，才能设置具体分路和启动功能
        self.defaultHintLabel.setStyleSheet("font: bold")
        self.rankLabel.setStyleSheet("font: bold")

        # 54 是占位用的空图标
        selected = 54 not in qconfig.get(self.defaultSpellConfigItem)
        checked = qconfig.get(self.enableConfigItem)

        for ty in ['default', 'top', 'jug', 'mid', 'bot', 'sup']:
            for index in [1, 2]:
                button: SummonerSpellButton = getattr(
                    self, f"{ty}SelectButton{index}")
                button.setFixedSize(40, 40)
                button.clicked.connect(
                    lambda _, t=ty, i=index: self.__onButtonClicked(t, i))

                if ty != 'default':
                    button.setEnabled(selected)

        self.enableSwitchButton.checkedChanged.connect(
            self.__onEnableSelectChanged)
        self.enableSwitchButton.setEnabled(selected)
        self.enableSwitchButton.setChecked(checked)
        self.resetButton.setMinimumWidth(100)
        self.resetButton.clicked.connect(self.__onResetButtonClicked)

        self.__updateStatusLabel()

    def __initLayout(self):
        self.addWidget(self.statusLabel)

        self.defaultCfgLayout.setVerticalSpacing(19)
        self.defaultCfgLayout.setContentsMargins(48, 18, 44, 18)
        self.defaultCfgLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.defaultButtonLayout.addWidget(self.defaultSelectButton1)
        self.defaultButtonLayout.addWidget(self.defaultSelectButton2)
        self.defaultButtonLayout.setSpacing(10)
        self.defaultButtonLayout.setContentsMargins(0, 0, 0, 0)
        self.defaultCfgLayout.addWidget(
            self.defaultHintLabel, 0, 0, Qt.AlignLeft)
        self.defaultCfgLayout.addWidget(
            self.defaultLabel, 1, 0, Qt.AlignLeft)
        self.defaultCfgLayout.addLayout(
            self.defaultButtonLayout, 1, 1, Qt.AlignRight)

        self.rankCfgLayout.setVerticalSpacing(19)
        self.rankCfgLayout.setContentsMargins(48, 18, 44, 18)
        self.rankCfgLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.rankCfgLayout.addWidget(self.rankLabel, 0, 0, Qt.AlignLeft)

        for i, ty in enumerate(['top', 'jug', 'mid', 'bot', 'sup']):
            label = getattr(self, f"{ty}Label")
            button1 = getattr(self, f"{ty}SelectButton1")
            button2 = getattr(self, f"{ty}SelectButton2")
            layout: QHBoxLayout = getattr(self, f"{ty}ButtonLayout")

            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(10)
            layout.addWidget(button1)
            layout.addWidget(button2)

            self.rankCfgLayout.addWidget(label, i + 1, 0, Qt.AlignLeft)
            self.rankCfgLayout.addLayout(layout, i + 1, 1, Qt.AlignRight)

        self.buttonsLayout.setVerticalSpacing(19)
        self.buttonsLayout.setContentsMargins(48, 18, 44, 18)
        self.buttonsLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.buttonsLayout.addWidget(
            self.enableHintLabel, 0, 0, Qt.AlignLeft)
        self.buttonsLayout.addWidget(
            self.enableSwitchButton, 0, 1, Qt.AlignRight)

        self.buttonsLayout.addWidget(
            self.resetButton, 1, 1, Qt.AlignRight)

        self.viewLayout.setSpacing(0)
        self.viewLayout.setContentsMargins(0, 0, 0, 0)

        self.addGroupWidget(self.defaultCfgWidget)
        self.addGroupWidget(self.rankCfgWidget)
        self.addGroupWidget(self.buttonsWidget)

    async def initSummonerSpells(self):
        self.spells = {
            i: await connector.getSummonerSpellIcon(i)
            for i in connector.manager.getSummonerSpellList()
        }

        for ty in ['default', 'top', 'jug', 'mid', 'bot', 'sup']:
            configItem = getattr(self, f"{ty}SpellConfigItem")
            selected = qconfig.get(configItem)

            for i in [1, 2]:
                spellId = selected[i - 1]

                button = f"{ty}SelectButton{i}"
                button: SummonerSpellButton = getattr(self, button)
                button.setPicture(self.spells[spellId])
                button.setSpellId(spellId)

    def __onButtonClicked(self, type: str, index: int):
        view = SummonerSpellSelectFlyout(self.spells)
        view.selectWidget.spellClicked.connect(
            lambda i, ty=type, ind=index: self.__onSpellSelected(ty, ind, i))

        button = QObject.sender(self)

        if index == 1:
            position = FlyoutAnimationType.SLIDE_LEFT
        else:
            position = FlyoutAnimationType.SLIDE_RIGHT

        self.w = Flyout.make(view, button, self, position, True)
        view.selectWidget.spellClicked.connect(self.w.fadeOut)

    def __onSpellSelected(self, type: str, index: int, id):

        button = f"{type}SelectButton{index}"
        button: SummonerSpellButton = getattr(self, button)

        if id != 54:
            anotherButton = f"{type}SelectButton{2 if index == 1 else 1}"
            anotherButton: SummonerSpellButton = getattr(self, anotherButton)
            anotherSpellId = anotherButton.getSpellId()

            # 选的技能和另一个已经选好的一样，认为是想要交换位置
            if id == anotherSpellId:
                currentSpellId = button.getSpellId()
                anotherButton.setPicture(self.spells[currentSpellId])
                anotherButton.setSpellId(currentSpellId)
                anotherButton.repaint()

        button.setPicture(self.spells[id])
        button.setSpellId(id)
        button.repaint()

        button1 = f"{type}SelectButton1"
        button1: SummonerSpellButton = getattr(self, button1)
        button2 = f"{type}SelectButton2"
        button2: SummonerSpellButton = getattr(self, button2)

        spells = [button1.getSpellId(), button2.getSpellId()]

        configItem = getattr(self, f"{type}SpellConfigItem")
        cfg.set(configItem, spells)

        if type != 'default':
            return

        buttonEnabled = False
        if id == 54:
            self.enableSwitchButton.setChecked(False)
            self.enableSwitchButton.setEnabled(False)
        elif 54 not in spells:
            self.enableSwitchButton.setEnabled(True)
            buttonEnabled = True

        for ty in ['top', 'jug', 'mid', 'bot', 'sup']:
            for i in [1, 2]:
                button = f"{ty}SelectButton{i}"
                button: SummonerSpellButton = getattr(self, button)
                button.setEnabled(buttonEnabled)

    def __onEnableSelectChanged(self, checked):
        for ty in ['default', 'top', 'jug', 'mid', 'bot', 'sup']:
            for i in [1, 2]:
                button = f"{ty}SelectButton{i}"
                button: SummonerSpellButton = getattr(self, button)
                button.setEnabled(not checked)

        cfg.set(self.enableConfigItem, checked)

        self.__updateStatusLabel()

    def __onResetButtonClicked(self):
        for ty in ['default', 'top', 'jug', 'mid', 'bot', 'sup']:
            for i in [1, 2]:
                self.__onSpellSelected(ty, i, 54)

    def __updateStatusLabel(self):
        checked = self.enableSwitchButton.isChecked()

        text = self.tr("Enabled") if checked else self.tr("Disabled")
        self.statusLabel.setText(text)
