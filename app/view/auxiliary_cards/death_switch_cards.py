import psutil
import win32gui
import win32process

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (QWidget, QLabel, QHBoxLayout, QGridLayout,
                             QListWidget, QListWidgetItem, QVBoxLayout,
                             QDialog, QFrame)

from app.common.qfluentwidgets import (PushButton, SwitchButton, ConfigItem,
                                       qconfig, IndicatorPosition,
                                       ExpandGroupSettingCard)
from app.common.icons import Icon

TAG = 'DeathSwitchCard'


class ProcessSelectDialog(QDialog):
    """浏览: 显示当前所有运行中的可见窗口, 选择目标进程"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("选择目标窗口"))
        self.resize(500, 450)
        self._selectedExe = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        hint = QLabel(self.tr("选择死亡后要切换到哪个窗口/应用:"))
        layout.addWidget(hint)

        self.listWidget = QListWidget()
        self.listWidget.setAlternatingRowColors(True)
        self.listWidget.itemDoubleClicked.connect(self._onAccept)
        layout.addWidget(self.listWidget)

        btnLayout = QHBoxLayout()
        self.okBtn = PushButton(self.tr("确定"))
        self.cancelBtn = PushButton(self.tr("取消"))
        self.okBtn.clicked.connect(self._onAccept)
        self.cancelBtn.clicked.connect(self.reject)
        btnLayout.addStretch()
        btnLayout.addWidget(self.okBtn)
        btnLayout.addWidget(self.cancelBtn)
        layout.addLayout(btnLayout)

        self._populate()

    def _populate(self):
        seen = set()
        items = []
        hwnds = []
        win32gui.EnumWindows(lambda hwnd, _: hwnds.append(hwnd) or True, None)
        for hwnd in hwnds:
            if not win32gui.IsWindowVisible(hwnd):
                continue
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                proc = psutil.Process(pid)
                exe = proc.name()
                if exe.lower() in seen or not exe:
                    continue
                seen.add(exe.lower())
                title = win32gui.GetWindowText(hwnd)
                display = f"{exe}" + (f'  —  "{title[:60]}"' if title else "")
                items.append((display, exe))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        items.sort(key=lambda x: x[0].lower())
        for display, exe in items:
            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, exe)
            self.listWidget.addItem(item)

    def _onAccept(self):
        item = self.listWidget.currentItem()
        if item:
            self._selectedExe = item.data(Qt.UserRole)
        self.accept()

    def getSelectedExe(self):
        return self._selectedExe


class DeathSwitchCard(ExpandGroupSettingCard):
    """死亡自动切窗设置卡片"""

    def __init__(self, title, content=None,
                 enableConfigItem: ConfigItem = None,
                 exeConfigItem: ConfigItem = None,
                 parent=None):
        super().__init__(Icon.GAME, title, content, parent)

        self.enableConfigItem = enableConfigItem
        self.exeConfigItem = exeConfigItem

        self.statusLabel = QLabel()

        self.cfgWidget = QWidget(self.view)
        self.cfgLayout = QGridLayout(self.cfgWidget)

        self.exeLabel = QLabel(self.tr("目标程序："))
        self.exeEdit = QLabel()
        self.exeEdit.setFrameShape(QFrame.StyledPanel)
        self.exeEdit.setMinimumWidth(200)
        self.exeEdit.setMaximumWidth(300)
        self.exeEdit.setStyleSheet(
            "padding: 4px 8px; border: 1px solid #ccc; border-radius: 4px;")

        self.browseButton = PushButton(self.tr("浏览"))
        self.pickButton = PushButton(self.tr("选取"))

        self.buttonsWidget = QWidget(self.view)
        self.buttonsLayout = QGridLayout(self.buttonsWidget)
        self.enableLabel = QLabel(self.tr("启用："))
        self.enableSwitchButton = SwitchButton(
            indicatorPos=IndicatorPosition.RIGHT)

        self._pickTimer = None
        self._pickCountdown = 0

        self.__initWidget()
        self.__initLayout()

    def __initWidget(self):
        self.browseButton.setMinimumWidth(80)
        self.pickButton.setMinimumWidth(80)
        self.browseButton.clicked.connect(self.__onBrowseClicked)
        self.pickButton.clicked.connect(self.__onPickClicked)

        selected = qconfig.get(self.exeConfigItem)
        self.__updateExeLabel(selected)

        checked = qconfig.get(self.enableConfigItem)
        self.enableSwitchButton.checkedChanged.connect(
            self.__onEnableChanged)
        self.enableSwitchButton.setChecked(checked)

        self.__updateStatusLabel()

    def __initLayout(self):
        self.addWidget(self.statusLabel)

        self.cfgLayout.setVerticalSpacing(19)
        self.cfgLayout.setContentsMargins(48, 18, 44, 18)

        self.cfgLayout.addWidget(self.exeLabel, 0, 0, Qt.AlignLeft)
        self.cfgLayout.addWidget(self.exeEdit, 0, 1, Qt.AlignLeft)
        self.cfgLayout.addWidget(self.browseButton, 0, 2, Qt.AlignRight)
        self.cfgLayout.addWidget(self.pickButton, 0, 3, Qt.AlignRight)

        self.buttonsLayout.setVerticalSpacing(19)
        self.buttonsLayout.setContentsMargins(48, 18, 44, 18)
        self.buttonsLayout.addWidget(self.enableLabel, 0, 0, Qt.AlignLeft)
        self.buttonsLayout.addWidget(
            self.enableSwitchButton, 0, 1, Qt.AlignRight)

        self.viewLayout.setSpacing(0)
        self.viewLayout.setContentsMargins(0, 0, 0, 0)

        self.addGroupWidget(self.cfgWidget)
        self.addGroupWidget(self.buttonsWidget)

    def __updateExeLabel(self, exe: str):
        if exe:
            self.exeEdit.setText(exe)
            self.exeEdit.setToolTip(exe)
        else:
            self.exeEdit.setText(self.tr("（未设置）"))
            self.exeEdit.setToolTip("")

    def __onBrowseClicked(self):
        dialog = ProcessSelectDialog(self.window())
        if dialog.exec() == QDialog.Accepted:
            exe = dialog.getSelectedExe()
            if exe:
                qconfig.set(self.exeConfigItem, exe)
                self.__updateExeLabel(exe)

    def __onPickClicked(self):
        if self._pickTimer and self._pickTimer.isActive():
            return
        self.pickButton.setText(self.tr("3"))
        self.pickButton.setEnabled(False)
        self._pickCountdown = 3
        self._pickTimer = QTimer(self)
        self._pickTimer.timeout.connect(self.__onPickTick)
        self._pickTimer.start(1000)

    def __onPickTick(self):
        self._pickCountdown -= 1
        if self._pickCountdown > 0:
            self.pickButton.setText(str(self._pickCountdown))
            return
        self._pickTimer.stop()
        self._pickTimer = None
        self.pickButton.setEnabled(True)
        self.pickButton.setText(self.tr("选取"))

        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            exe = psutil.Process(pid).name()
            if exe:
                qconfig.set(self.exeConfigItem, exe)
                self.__updateExeLabel(exe)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    def __onEnableChanged(self, checked):
        qconfig.set(self.enableConfigItem, checked)
        self.__updateStatusLabel()

    def __updateStatusLabel(self):
        checked = self.enableSwitchButton.isChecked()
        self.statusLabel.setText(
            self.tr("已启用") if checked else self.tr("已禁用"))
