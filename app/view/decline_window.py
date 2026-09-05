from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QIcon, QShowEvent
from PyQt5.QtWidgets import QVBoxLayout, QApplication

from app.common.qfluentwidgets import (StrongBodyLabel, CaptionLabel,
                                       PushButton)
from app.common.util import getLolClientWindowPos
from app.view.opgg_window import OpggWindowBase

TAG = 'DeclineWindow'


class DeclineWindow(OpggWindowBase):
    """拒绝对局窗口: 自动接受后反悔用, ready check 期间贴客户端左下角显示

    生命周期由 MainWindow.__onReadyCheckChanged 驱动:
    匹配确认 InProgress 且开启反悔权限时 show, 结束/已拒绝时 hide.
    """

    declineRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.vBoxLayout = QVBoxLayout(self)

        self.titleLabel = StrongBodyLabel(self.tr("对局已自动接受"))
        self.hintLabel = CaptionLabel(self.tr("反悔？拒绝后重新开始匹配"))
        self.declineButton = PushButton(self.tr("拒绝对局"))
        self.declineButton.setMinimumWidth(160)

        self.__initWindow()
        self.__initLayout()

        self.declineButton.clicked.connect(self.declineRequested.emit)

    def __initWindow(self):
        self.setFixedSize(240, 170)
        self.setWindowIcon(QIcon("app/resource/images/logo.png"))
        self.setWindowTitle(self.tr("拒绝对局"))
        self.setCustomBackgroundColor("#f3f3f3", "#202020")
        # 瞬态反悔窗口: 恒置顶, 不提供配置 (仅在 ready check 几秒内出现)
        self.setStaysOnTopEnabled(True)

    def __initLayout(self):
        self.vBoxLayout.setContentsMargins(0, 36, 0, 0)
        self.vBoxLayout.setSpacing(6)

        self.vBoxLayout.addWidget(self.titleLabel, 0, Qt.AlignCenter)
        self.vBoxLayout.addWidget(self.hintLabel, 0, Qt.AlignCenter)
        self.vBoxLayout.addSpacing(8)
        self.vBoxLayout.addWidget(self.declineButton, 0, Qt.AlignCenter)
        self.vBoxLayout.addStretch(1)

    def showEvent(self, a0: QShowEvent) -> None:
        """贴客户端左下角 (与海克斯窗口的左侧上方区域错开); 客户端不可见时贴屏幕左下角"""
        size = self.size()
        pos = getLolClientWindowPos()
        if not pos:
            self.__moveScreenBottomLeft()
            return super().showEvent(a0)

        # pos 是物理像素, 需除以 dpi 转成逻辑坐标
        dpi = self.devicePixelRatioF() or 1.0
        clientLeft = int(pos.left() / dpi)
        clientBottom = int(pos.bottom() / dpi)

        # 贴客户端左侧, 底边对齐客户端底边
        x = clientLeft - size.width()
        y = clientBottom - size.height()

        # 超出屏幕左边界时改贴客户端右侧
        if x < 0:
            x = int(pos.right() / dpi)

        self.move(x, y)
        return super().showEvent(a0)

    def __moveScreenBottomLeft(self):
        desktop = QApplication.desktop().availableGeometry()
        self.move(0, desktop.bottom() - self.height())

    def closeEvent(self, e):
        e.ignore()
        self.hide()
