from PyQt5.QtCore import Qt, QRect, QRectF
from PyQt5.QtGui import QColor, QPainter, QFontMetrics
from PyQt5.QtWidgets import QPushButton

from app.common.qfluentwidgets import isDarkTheme, themeColor


class QuickToggleButton(QPushButton):
    """侧边栏的一行快捷按钮.

    展开: [图标] 文字 ●        折叠: 仅居中图标 (悬停提示标题)
    checkable=True 时作为开关: 选中显示主题色底 + 左侧色条 + 右侧圆点.
    active=False 表示与当前阶段无关, 整行淡化 (仍可点击).
    """

    ICON_SIZE = 18
    HEIGHT = 36

    def __init__(self, icon, title, tip="", checkable=True, parent=None):
        super().__init__(parent)
        self._qicon = icon.icon()
        self._title = title
        self._tip = tip
        self._collapsed = False
        self._active = True

        self.setCheckable(checkable)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(self.HEIGHT)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_Hover, True)
        self._refreshToolTip()

    def title(self):
        return self._title

    def setCollapsed(self, collapsed: bool):
        if self._collapsed == collapsed:
            return
        self._collapsed = collapsed
        self._refreshToolTip()
        self.update()

    def setActive(self, active: bool):
        if self._active == active:
            return
        self._active = active
        self.update()

    def setFluentIcon(self, icon):
        self._qicon = icon.icon()
        self.update()

    def setTitle(self, title: str):
        self._title = title
        self._refreshToolTip()
        self.update()

    def _refreshToolTip(self):
        if self._collapsed:
            self.setToolTip(f"{self._title}\n{self._tip}" if self._tip
                            else self._title)
        else:
            self.setToolTip(self._tip)

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        dark = isDarkTheme()
        accent = themeColor()
        checked = self.isCheckable() and self.isChecked()

        painter.setOpacity(1.0 if self._active else 0.5)

        rect = QRectF(self.rect()).adjusted(4, 1, -4, -1)

        bg = None
        if checked:
            bg = QColor(accent)
            bg.setAlpha(70 if dark else 50)
        elif self.underMouse() or self.isDown():
            bg = QColor(255, 255, 255, 18) if dark else QColor(0, 0, 0, 14)
        if bg is not None:
            painter.setPen(Qt.NoPen)
            painter.setBrush(bg)
            painter.drawRoundedRect(rect, 5, 5)

        if checked:
            painter.setPen(Qt.NoPen)
            painter.setBrush(accent)
            painter.drawRoundedRect(
                QRectF(rect.left(), rect.top() + 8, 3, rect.height() - 16), 1.5, 1.5)

        size = self.ICON_SIZE
        iconY = int(rect.top() + (rect.height() - size) / 2)
        if self._collapsed:
            iconX = int(rect.left() + (rect.width() - size) / 2)
        else:
            iconX = int(rect.left() + 10)
        self._qicon.paint(painter, QRect(iconX, iconY, size, size))

        if self._collapsed:
            return

        textColor = QColor(255, 255, 255, 230) if dark else QColor(0, 0, 0, 210)
        painter.setPen(textColor)
        font = self.font()
        font.setPixelSize(13)
        painter.setFont(font)
        textRect = QRectF(rect.left() + 36, rect.top(),
                          rect.width() - 36 - (20 if self.isCheckable() else 8),
                          rect.height())
        text = QFontMetrics(font).elidedText(
            self._title, Qt.ElideRight, int(textRect.width()))
        painter.drawText(textRect, Qt.AlignVCenter | Qt.AlignLeft, text)

        if self.isCheckable():
            dot = 7
            painter.setPen(Qt.NoPen)
            if checked:
                painter.setBrush(accent)
                painter.drawEllipse(QRectF(
                    rect.right() - 14, rect.center().y() - dot / 2, dot, dot))
            else:
                painter.setBrush(Qt.NoBrush)
                painter.setPen(QColor(255, 255, 255, 90) if dark
                               else QColor(0, 0, 0, 80))
                painter.drawEllipse(QRectF(
                    rect.right() - 14, rect.center().y() - dot / 2, dot, dot))
