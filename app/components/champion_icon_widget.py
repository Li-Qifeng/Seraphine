from PyQt5.QtCore import QEvent, Qt, pyqtSignal, QRectF
from PyQt5.QtGui import (QColor, QMouseEvent, QPainter, QPainterPath, QLinearGradient, QPen, QPixmap)
from PyQt5.QtWidgets import QFrame, QLabel, QGraphicsOpacityEffect




class RoundIcon(QFrame):
    def __init__(self, icon=None, diameter=None, overscaled=0,
                 borderWidth=1, drawBackground=False, enabled=True, parent=None) -> None:
        super().__init__(parent)
        self.image = QPixmap(icon) if icon else QPixmap()

        self.overscaled = overscaled
        self.borderWidth = borderWidth
        self.drawBackground = drawBackground
        self.enabled = enabled

        self.havePic = icon is not None and not self.image.isNull()

        self.setFixedSize(diameter, diameter)

    def paintEvent(self, event) -> None:
        if not self.havePic or self.image.isNull():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        width = self.image.width() - 2*self.overscaled
        height = self.image.height() - 2*self.overscaled

        image = self.image.copy(
            self.overscaled, self.overscaled, width, height)

        if image.isNull():
            return

        size = self.size() * self.devicePixelRatioF()
        image: QPixmap = image.scaled(size,
                                      Qt.AspectRatioMode.KeepAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation)

        path = QPainterPath()
        path.addEllipse(0, 0, self.width(), self.height())

        painter.setClipPath(path)

        if not self.enabled:
            painter.setOpacity(0.15)

        if self.drawBackground:
            painter.save()
            painter.setBrush(QColor(0, 0, 0))
            painter.drawEllipse(0, 0, self.width(), self.height())
            painter.restore()

        painter.drawPixmap(self.rect(), image)

        if self.borderWidth != 0 and self.enabled:
            painter.save()
            painter.setPen(
                QPen(QColor(120, 90, 40), self.borderWidth, Qt.SolidLine))
            painter.drawEllipse(0, 0, self.width(), self.height())
            painter.restore()

        return super().paintEvent(event)

    def setIcon(self, icon):
        new_image = QPixmap(icon) if icon else QPixmap()
        if new_image.isNull():
            self.havePic = False
            self.image = QPixmap()
        else:
            self.havePic = True
            self.image = new_image

        self.repaint()

    def setEnabeld(self, enabled):
        self.enabled = enabled

        self.repaint()


class RoundIconButton(QFrame):
    clicked = pyqtSignal(int)

    def __init__(self, icon, diameter, overscaled, borderWidth, championName, championId, parent=None) -> None:
        super().__init__(parent)

        self.image = QPixmap(icon) if icon else QPixmap()
        self.havePic = not self.image.isNull()

        self.borderWidth = borderWidth
        self.overscaled = overscaled

        self.championName: str = championName
        self.championId = championId

        self.isPressed = False
        self.isHover = False
        self.isSelected = False
        self.isGrabbed = False
        self.isWishlist = False

        self._toolTipFilter = None

        self.setFixedSize(diameter, diameter)

    def setToolTipFilter(self, tooltipFilter):
        """保存 ToolTipFilter 引用, 供 clearAll 时主动隐藏 tooltip"""
        self._toolTipFilter = tooltipFilter

    def cleanupToolTip(self):
        """主动隐藏并清理 tooltip, 解决 deleteLater 延迟期间 tooltip 堆叠不消失的问题"""
        if self._toolTipFilter:
            try:
                self._toolTipFilter.hideToolTip()
            except RuntimeError:
                # 防御: filter 内部的 widget 已被 Qt 原生删除 (RuntimeError:
                # wrapped C/C++ object of type ... has been deleted)
                pass
            self._toolTipFilter = None

    def paintEvent(self, event) -> None:
        if not self.havePic or self.image.isNull():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        path = QPainterPath()
        path.addEllipse(0, 0, self.width(), self.height())
        painter.setClipPath(path)

        width = self.image.width() - 2*self.overscaled
        height = self.image.height() - 2*self.overscaled

        image = self.image.copy(
            self.overscaled, self.overscaled, width, height)

        if image.isNull():
            return

        size = self.size() * self.devicePixelRatioF()
        image = image.scaled(size,
                             Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)

        if self.isPressed:
            painter.setOpacity(0.63)
        elif self.isHover:
            painter.setOpacity(0.80)
        else:
            painter.setOpacity(1)

        painter.drawPixmap(self.rect(), image)

        # 选中态: 半透明绿色遮罩
        if self.isSelected and not self.isGrabbed:
            painter.setOpacity(1)
            painter.setBrush(QColor(34, 197, 94, 90))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(self.rect())

        painter.setClipping(False)

        # 边框: 选中/已抢到用绿色, 愿望单用金色, 否则默认棕色
        if self.isSelected or self.isGrabbed:
            painter.setPen(
                QPen(QColor(34, 197, 94), self.borderWidth + 1, Qt.SolidLine))
        elif self.isWishlist:
            painter.setPen(
                QPen(QColor(234, 179, 8), self.borderWidth + 1, Qt.SolidLine))
        else:
            painter.setPen(
                QPen(QColor(120, 90, 40), self.borderWidth, Qt.SolidLine))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(0, 0, self.width(), self.height())

        # 已抢到: 画一个白色勾
        if self.isGrabbed:
            painter.setPen(QPen(QColor(255, 255, 255), 2.5,
                                Qt.SolidLine, Qt.RoundCap))
            cx, cy = self.width() / 2, self.height() / 2
            painter.drawLine(int(cx - 6), int(cy),
                             int(cx - 2), int(cy + 4))
            painter.drawLine(int(cx - 2), int(cy + 4),
                             int(cx + 6), int(cy - 5))

        return super().paintEvent(event)

    def enterEvent(self, a0: QEvent) -> None:
        self.isHover = True
        self.update()
        return super().enterEvent(a0)

    def leaveEvent(self, a0: QEvent) -> None:
        self.isHover = False
        self.update()
        return super().leaveEvent(a0)

    def mousePressEvent(self, a0: QMouseEvent) -> None:
        self.isPressed = True
        self.update()
        return super().mousePressEvent(a0)

    def mouseReleaseEvent(self, a0: QMouseEvent) -> None:
        self.isPressed = False
        self.update()
        ret = super().mouseReleaseEvent(a0)
        self.clicked.emit(self.championId)
        return ret


class TopRoundedLabel(QLabel):
    def __init__(self, imagePath=None, radius=4.0, parent=None):
        super().__init__(parent)
        pixmap = QPixmap(imagePath) if imagePath else QPixmap()
        self.setPixmap(pixmap)

        self.havePic = imagePath is not None and not pixmap.isNull()
        self.radius = radius

        self.opacity = QGraphicsOpacityEffect(opacity=1)
        self.setGraphicsEffect(self.opacity)

    def paintEvent(self, e):
        if not self.havePic:
            return super().paintEvent(e)

        pm = self.pixmap()
        if pm is None or pm.isNull():
            return super().paintEvent(e)

        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing)

        pixmap = pm.scaled(
            self.size()*self.devicePixelRatioF(),
            Qt.IgnoreAspectRatio, Qt.SmoothTransformation)

        path = QPainterPath()

        topPath = QPainterPath()
        topRect = QRectF(self.rect().x(), self.rect().y(),
                         self.rect().width(), self.rect().height())
        topPath.addRoundedRect(topRect, self.radius, self.radius)

        bottomPath = QPainterPath()
        bottomRect = QRectF(self.rect().x(), self.rect().y() + self.rect().height() / 2,
                            self.rect().width(), self.rect().height() / 2)
        bottomPath.addRect(bottomRect)

        path = topPath.united(bottomPath)
        painter.setClipPath(path)

        grad = QLinearGradient(0, 0, 0, self.rect().height())
        grad.setColorAt(0.7, Qt.GlobalColor.black)
        grad.setColorAt(1, Qt.GlobalColor.transparent)
        self.opacity.setOpacityMask(grad)

        painter.drawPixmap(self.rect(), pixmap)

    def setPicture(self, imagePath):
        pm = QPixmap(imagePath) if imagePath else QPixmap()
        if pm.isNull():
            self.havePic = False
        else:
            self.havePic = True
            self.setPixmap(pm)
        self.repaint()

    def setRedius(self, radius):
        self.radius = radius
        self.repaint()

    def setText(self, text):
        self.havePic = False

        return super().setText(text)


class RoundedLabel(QLabel):
    def __init__(self, imagePath=None, radius=4.0, borderWidth=2, borderColor: QColor = None, drawBackground=False, parent=None):
        super().__init__(parent)
        pixmap = QPixmap(imagePath)
        self.setPixmap(pixmap)

        self.havePic = imagePath is not None and not pixmap.isNull()
        self.radius = radius
        self.borderWidth = borderWidth
        self.borderColor = borderColor if borderColor else QColor(120, 90, 40)
        self.drawBackground = drawBackground

    def paintEvent(self, e):
        if not self.havePic:
            return super().paintEvent(e)

        pm = self.pixmap()
        if pm is None or pm.isNull():
            return super().paintEvent(e)

        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing)

        pixmap = pm.scaled(
            self.size()*self.devicePixelRatioF(),
            Qt.IgnoreAspectRatio, Qt.SmoothTransformation)

        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), self.radius, self.radius)

        painter.setClipPath(path)

        if self.drawBackground:
            painter.save()
            painter.setBrush(QColor(0, 0, 0))
            painter.setOpacity(0.8)
            painter.drawRoundedRect(
                QRectF(self.rect()), self.radius, self.radius)
            painter.restore()

        painter.drawPixmap(self.rect(), pixmap)

        if self.borderWidth != 0:
            painter.setPen(
                QPen(self.borderColor, self.borderWidth, Qt.SolidLine))

            painter.drawRoundedRect(
                QRectF(self.rect()), self.radius, self.radius)

    def setPicture(self, imagePath):
        pm = QPixmap(imagePath) if imagePath else QPixmap()
        if pm.isNull():
            self.havePic = False
        else:
            self.havePic = True
            self.setPixmap(pm)
        self.repaint()

    def setRedius(self, radius):
        self.radius = radius
        self.repaint()

    def setText(self, text):
        self.havePic = False

        return super().setText(text)


class SummonerSpellButton(QFrame):
    clicked = pyqtSignal(int)

    def __init__(self, imagePath=None, spellId=None, parent=None):
        super().__init__(parent)

        self.image = None
        if imagePath:
            pm = QPixmap(imagePath)
            if not pm.isNull():
                self.image = pm

        self.spellId = spellId
        self.radius = 5.0
        self.borderWidth = 2
        self.borderColor = QColor(120, 90, 40)

        self.isPressed = False
        self.isHovered = False
        self.enabled = True

    def paintEvent(self, e):
        if self.image is None or self.image.isNull():
            return super().paintEvent(e)

        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), self.radius, self.radius)
        painter.setClipPath(path)

        size = self.size() * self.devicePixelRatioF()
        image = self.image.scaled(size, Qt.AspectRatioMode.KeepAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation)

        if not self.enabled:
            painter.setOpacity(0.5)
        elif self.isPressed:
            painter.setOpacity(0.63)
        elif self.isHovered:
            painter.setOpacity(0.80)
        else:
            painter.setOpacity(1)

        painter.drawPixmap(self.rect(), image)

        painter.setPen(
            QPen(self.borderColor, self.borderWidth, Qt.SolidLine))

        painter.drawRoundedRect(
            QRectF(self.rect()), self.radius, self.radius)

        return super().paintEvent(e)

    def setPicture(self, path):
        pm = QPixmap(path) if path else QPixmap()
        self.image = None if pm.isNull() else pm

    def setSpellId(self, id):
        self.spellId = id

    def getSpellId(self):
        return self.spellId

    def enterEvent(self, a0: QEvent) -> None:
        self.isHovered = True
        self.update()
        return super().enterEvent(a0)

    def leaveEvent(self, a0: QEvent) -> None:
        self.isHovered = False
        self.update()
        return super().leaveEvent(a0)

    def mousePressEvent(self, a0: QMouseEvent) -> None:
        self.isPressed = True
        self.update()
        return super().mousePressEvent(a0)

    def mouseReleaseEvent(self, a0: QMouseEvent) -> None:
        self.isPressed = False
        self.update()
        ret = super().mouseReleaseEvent(a0)

        if self.enabled:
            self.clicked.emit(self.spellId)

        return ret

    def isEnabled(self):
        return self.isEnabled()

    def setEnabled(self, enabled: bool):
        self.enabled = enabled
        return super().setEnabled(enabled)
