from PyQt5.QtCore import Qt, pyqtSignal, QEvent, QSize
from PyQt5.QtWidgets import QWidget, QLabel, QHBoxLayout, QGridLayout, QFrame, QSpacerItem, QSizePolicy
from app.common.icons import Icon
from app.common.qfluentwidgets import PushButton, SwitchButton, ConfigItem, qconfig, IndicatorPosition, ExpandGroupSettingCard, TransparentToolButton, FluentIcon, ToolTipFilter, ToolTipPosition
from app.components.champion_icon_widget import RoundIcon
from app.components.message_box import MultiChampionSelectMsgBox
from app.lol.connector import connector


class ChampionsCard(QFrame):
    clearRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.hBoxLayout = QHBoxLayout(self)
        self.hBoxLayout.setContentsMargins(2, 0, 4, 0)
        self.hBoxLayout.setAlignment(Qt.AlignCenter)

        self.iconLayout = QHBoxLayout()
        self.iconLayout.setContentsMargins(6, 6, 0, 6)
        self.clearButton = TransparentToolButton(FluentIcon.CLOSE)
        self.clearButton.setFixedSize(28, 28)
        self.clearButton.setIconSize(QSize(15, 15))
        self.clearButton.setVisible(False)
        self.clearButton.clicked.connect(self.clearRequested)

        self.hBoxLayout.addLayout(self.iconLayout)
        self.hBoxLayout.addItem(QSpacerItem(
            0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed))
        self.hBoxLayout.addWidget(self.clearButton, alignment=Qt.AlignVCenter)

        self.setFixedWidth(250)
        self.setFixedHeight(42)

    def updateChampions(self, champions):
        self.clear()

        for icon in champions:
            icon = RoundIcon(icon, 28, 2, 2)
            self.iconLayout.addWidget(icon, alignment=Qt.AlignVCenter)

    def clear(self):
        for i in reversed(range(self.iconLayout.count())):
            item = self.iconLayout.itemAt(i)
            self.iconLayout.removeItem(item)

            if item.widget():
                item.widget().deleteLater()

    def enterEvent(self, a0: QEvent) -> None:
        self.clearButton.setVisible(True)
        return super().enterEvent(a0)

    def leaveEvent(self, a0: QEvent) -> None:
        self.clearButton.setVisible(False)
        return super().leaveEvent(a0)

class HextechChampionCard(ExpandGroupSettingCard):
    """
    大乱斗换英雄 - 愿望单配置卡
     单一英雄列表 (无分路) + 总开关, 仅在备选席模式 (benchEnabled) 生效
    """

    def __init__(self, title, content=None,
                 enableConfigItem: ConfigItem = None,
                 championsConfigItem: ConfigItem = None,
                 parent=None):
        super().__init__(Icon.GAME, title, content, parent)

        self.champions = {}

        self.enableConfigItem = enableConfigItem
        self.championsConfigItem = championsConfigItem

        self.statusLabel = QLabel()

        self.cfgWidget = QWidget(self.view)
        self.cfgLayout = QGridLayout(self.cfgWidget)

        self.hintLabel = QLabel(self.tr("愿望单（从左到右为优先级顺序，可拖拽调整）"))
        self.helpButton = TransparentToolButton(Icon.QUESTION_CIRCLE)
        self.championsLabel = QLabel(self.tr("英雄："))
        self.championsCard = ChampionsCard()
        self.selectButton = PushButton(self.tr("选择"))

        self.buttonsWidget = QWidget(self.view)
        self.buttonsLayout = QGridLayout(self.buttonsWidget)
        self.enableLabel = QLabel(self.tr("启用："))
        self.enableSwitchButton = SwitchButton(
            indicatorPos=IndicatorPosition.RIGHT)

        self.__initWidget()
        self.__initLayout()

    def __initWidget(self):
        self.hintLabel.setStyleSheet("font: bold")

        self.helpButton.setFixedSize(QSize(26, 26))
        self.helpButton.setIconSize(QSize(16, 16))
        self.helpButton.setToolTip(self.tr(
            "仅在大乱斗（备选席模式）下生效。\n\n"
            "进入英雄选择后，若备选席出现愿望单中的英雄，"
            "将按从左到右的优先级顺序自动抢夺（无CD强刷）。\n\n"
            "若备选席没有愿望单英雄，换英雄窗口会显示本局所有英雄，"
            "点击任意头像即可手动抢夺。\n\n"
            "提示：愿望单中的英雄可拖拽调整顺序，左侧优先级更高。"))
        self.helpButton.installEventFilter(ToolTipFilter(
            self.helpButton, 0, ToolTipPosition.RIGHT))

        # 必须先有愿望单才能启用
        selected = qconfig.get(self.championsConfigItem)
        if not (type(selected) is list and all(type(s) is int for s in selected)):
            selected = []
            qconfig.set(self.championsConfigItem, selected)

        checked = qconfig.get(self.enableConfigItem)

        self.selectButton.setMinimumWidth(100)
        self.selectButton.clicked.connect(self.__onButtonClicked)
        self.selectButton.setEnabled(True)

        self.enableSwitchButton.checkedChanged.connect(
            self.__onEnableChanged)
        # 开关始终可用: 愿望单为空时也可启用 (进选人后窗口照常弹出, 仅不会自动抢)
        self.enableSwitchButton.setEnabled(True)
        self.enableSwitchButton.setChecked(checked)

        self.championsCard.clearRequested.connect(
            lambda: self.__onChampionsChanged([]))

        self.__updateStatusLabel()

    def __initLayout(self):
        self.addWidget(self.statusLabel)

        self.cfgLayout.setVerticalSpacing(19)
        self.cfgLayout.setContentsMargins(48, 18, 44, 18)
        self.cfgLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        helpLayout = QHBoxLayout()
        helpLayout.setContentsMargins(0, 0, 0, 0)
        helpLayout.setSpacing(10)
        helpLayout.addWidget(self.hintLabel)
        helpLayout.addWidget(self.helpButton)
        self.cfgLayout.addLayout(helpLayout, 0, 0, Qt.AlignLeft)

        self.cfgLayout.addWidget(self.championsLabel, 1, 0, Qt.AlignLeft)
        self.cfgLayout.addWidget(self.championsCard, 1, 1, Qt.AlignHCenter)
        self.cfgLayout.addWidget(self.selectButton, 1, 2, Qt.AlignRight)

        self.buttonsLayout.setVerticalSpacing(19)
        self.buttonsLayout.setContentsMargins(48, 18, 44, 18)
        self.buttonsLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)
        self.buttonsLayout.addWidget(self.enableLabel, 0, 0, Qt.AlignLeft)
        self.buttonsLayout.addWidget(
            self.enableSwitchButton, 0, 1, Qt.AlignRight)

        self.viewLayout.setSpacing(0)
        self.viewLayout.setContentsMargins(0, 0, 0, 0)

        self.addGroupWidget(self.cfgWidget)
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

        selected = qconfig.get(self.championsConfigItem)
        if not (type(selected) is list and all(type(s) is int for s in selected)):
            selected = []
            qconfig.set(self.championsConfigItem, selected)

        if len(selected) > 0:
            self.championsCard.updateChampions(
                [self.champions[id][1] for id in selected if id in self.champions])

        return self.champions

    def __onButtonClicked(self):
        selected = qconfig.get(self.championsConfigItem)
        # 愿望单无数量限制
        box = MultiChampionSelectMsgBox(
            self.champions, selected, maxCount=999, parent=self.window())
        box.completed.connect(self.__onChampionsChanged)
        box.exec()

    def __onChampionsChanged(self, champions: list):
        qconfig.set(self.championsConfigItem, champions)

        self.championsCard.updateChampions(
            [self.champions[id][1] for id in champions if id in self.champions])

        # 愿望单为空时不禁用开关 (允许仅弹出窗口、手动点头像抢)

    def __onEnableChanged(self, checked):
        qconfig.set(self.enableConfigItem, checked)
        self.__updateStatusLabel()

    def __updateStatusLabel(self):
        checked = self.enableSwitchButton.isChecked()
        self.statusLabel.setText(
            self.tr("已启用") if checked else self.tr("已禁用"))
