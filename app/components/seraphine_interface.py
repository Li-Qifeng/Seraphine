from PyQt5.sip import wrapper
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QLabel

from app.common.qfluentwidgets import SmoothScrollArea, ExpandLayout
from app.common.style_sheet import StyleSheet


class SeraphineInterface(SmoothScrollArea):
    """设置/辅助功能等滚动界面的基类.

    封装通用初始化逻辑: scrollWidget + expandLayout + titleLabel,
    子类只需提供标题文本和样式枚举, 在 __init__ 末尾调用 _initCommon(title, style).
    分组/卡片的创建和 __initLayout 仍由子类自行实现.
    """

    def __str__(self):
        methods = [attr for attr in dir(self) if callable(getattr(self, attr))]
        attrs = [f"{k}({type(v).__name__})={v!r}" for k, v in self.__dict__.items() if
                 not isinstance(v, wrapper) and k not in methods]
        return f"{self.__class__.__name__}({', '.join(attrs)})"

    def _initCommon(self, title: str, style: StyleSheet):
        """初始化通用滚动布局.

        Args:
            title: 顶部标题文本 (已 tr 过的字符串)
            style: StyleSheet 枚举值, 如 StyleSheet.SETTING_INTERFACE
        """
        self.scrollWidget = QWidget()
        self.expandLayout = ExpandLayout(self.scrollWidget)
        self.titleLabel = QLabel(title, self)

        self.titleLabel.setObjectName('titleLabel')
        self.scrollWidget.setObjectName('scrollWidget')

        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setViewportMargins(0, 90, 0, 20)
        self.setWidget(self.scrollWidget)
        self.setWidgetResizable(True)

        style.apply(self)

        self.titleLabel.move(36, 30)
