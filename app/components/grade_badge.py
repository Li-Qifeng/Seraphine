from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel

from app.common.qfluentwidgets import isDarkTheme
from app.lol.war_criminal_ui import (GRADE_BADGE_COLORS, METRIC_NAMES,
                                     format_metric_value, severity_comment)


class GradeBadge(QFrame):
    _COLORS = GRADE_BADGE_COLORS

    def __init__(self, grade: int, label: str, isCurrent: bool = False,
                 evidence: list = None, parent=None):
        super().__init__(parent)
        self.grade = grade
        self.label = label
        self.isCurrent = isCurrent

        self.hBoxLayout = QHBoxLayout(self)
        self.hBoxLayout.setContentsMargins(6, 1, 6, 1)
        self.hBoxLayout.setSpacing(0)

        self.textLabel = QLabel(label)
        self.hBoxLayout.addWidget(self.textLabel)

        self.setFixedHeight(22)

        self._applyStyle()

        if evidence:
            tip = self._formatEvidence(evidence)
            if tip:
                self.setToolTip(tip)

    def _applyStyle(self):
        palette = self._COLORS.get(self.grade, self._COLORS[3])
        if isDarkTheme():
            if self.isCurrent:
                fg, bg, border = palette[6], palette[7], palette[8]
            else:
                fg, bg, border = palette[9], palette[10], palette[11]
        else:
            if self.isCurrent:
                fg, bg, border = palette[0], palette[1], palette[2]
            else:
                fg, bg, border = palette[3], palette[4], palette[5]

        self.setStyleSheet(
            f"GradeBadge {{ background: {bg}; "
            f"border: 1px solid {border}; border-radius: 6px; }}")
        self.textLabel.setStyleSheet(
            f"QLabel {{ color: {fg}; "
            f"font: bold 10px 'Microsoft YaHei', 'Segoe UI'; "
            f"background: transparent; border: none; }}")

    @staticmethod
    def _formatEvidence(evidence: list) -> str:
        if not evidence:
            return ''

        lines = []
        for item in evidence:
            metric = item.get('metric', '')
            label = METRIC_NAMES.get(metric, metric)
            val = item.get('value', 0)
            avg = item.get('teamAvg', 0)
            z = item.get('zScore', 0)
            comment = severity_comment(z)
            lines.append(
                f"· {label}: {format_metric_value(metric, val)} | "
                f"队友均 {format_metric_value(metric, avg)} — {comment}")

        return '\n'.join(lines)
