"""全队 5 档评级徽章组件.

每个队友行头的小型彩色徽章, 显示该玩家的档位标签.
延续 VerdictBadge 的 Material Design 3 tonal palette 风格, 但尺寸更小.

5 档配色 (按贡献从高到低):
  档1 (最高): 金色系    - 神/上等马
  档2:        绿色系    - 爹/中上等马
  档3 (中):   灰色系    - 小有亮点/中等马
  档4:        橙色系    - 躺赢狗/下等马
  档5 (最低): 红色系    - 消失/纯牛马
"""
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel

from app.common.qfluentwidgets import isDarkTheme


class GradeBadge(QFrame):
    """全队评级徽章: 小型彩色标签, 显示该玩家的 5 档评级.

    样式 (参考 VerdictBadge 的 M3 tonal palette):
    - isCurrent=True  (当前召唤师): 实色背景 + 白字, 醒目
    - isCurrent=False (其他队友):   半透明背景 + 类型色字, 不喧宾夺主
    """

    # 每档 6 个颜色值:
    # (light_fg_current, light_bg_current, light_border_current,
    #  light_fg_other,  light_bg_other,   light_border_other,
    #  dark_fg_current, dark_bg_current,  dark_border_current,
    #  dark_fg_other,   dark_bg_other,    dark_border_other)
    _COLORS = {
        # 档1 最高: 金色系 (M3 amber/gold)
        1: ('#ffffff', '#b8860b', '#7a5a00',
            '#856100', 'rgba(184,134,11,0.12)', '#cba433',
            '#ffffff', '#b8860b', '#ffd54f',
            '#ffd54f', 'rgba(255,213,79,0.16)', '#ffd54f'),
        # 档2: 绿色系 (M3 green)
        2: ('#ffffff', '#2e7d32', '#1b5e20',
            '#2e7d32', 'rgba(46,125,50,0.12)', '#4caf50',
            '#ffffff', '#2e7d32', '#81c784',
            '#81c784', 'rgba(129,199,132,0.16)', '#81c784'),
        # 档3 中: 灰色系 (M3 neutral)
        3: ('#ffffff', '#616161', '#424242',
            '#616161', 'rgba(97,97,97,0.10)', '#9e9e9e',
            '#ffffff', '#616161', '#bdbdbd',
            '#bdbdbd', 'rgba(189,189,189,0.14)', '#bdbdbd'),
        # 档4: 橙色系 (M3 orange)
        4: ('#ffffff', '#c46200', '#8a4400',
            '#c46200', 'rgba(196,98,0,0.12)', '#e89641',
            '#ffffff', '#c46200', '#ffb874',
            '#ffb874', 'rgba(255,184,116,0.16)', '#ffb874'),
        # 档5 最低: 红色系 (M3 red, error container)
        5: ('#ffffff', '#b3261e', '#7e1a14',
            '#b3261e', 'rgba(179,38,30,0.10)', '#dc4744',
            '#ffffff', '#b3261e', '#f2b8b5',
            '#f2b8b5', 'rgba(242,184,181,0.14)', '#f2b8b5'),
    }

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

        # 小型徽章, 适配 39px 行高
        self.setFixedHeight(20)

        self._applyStyle()

        # evidence tooltip (各指标 z-score)
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
        """格式化 evidence 列表为 tooltip 文本."""
        if not evidence:
            return ''

        metric_labels = {
            'damage': '伤害', 'deaths': '死亡', 'gold': '经济',
            'kda': 'KDA', 'damage_taken': '承伤', 'shield_heal': '护盾治疗',
            'cc': '控制时长', 'vision': '视野',
            'kill_participation': '参团率', 'damage_efficiency': '伤害转化率',
        }

        def fmt_val(metric, val):
            if metric in ('kill_participation',):
                return f"{val:.0%}"
            if metric in ('kda', 'damage_efficiency', 'vision'):
                return f"{val:.2f}"
            return f"{int(val):,}"

        def severity_comment(z):
            if z >= 1.5:
                return '遥遥领先'
            if z >= 0.8:
                return '突出'
            if z <= -1.5:
                return '垫底'
            if z <= -0.8:
                return '偏低'
            return '正常'

        lines = []
        for item in evidence:
            metric = item.get('metric', '')
            label = metric_labels.get(metric, metric)
            val = item.get('value', 0)
            avg = item.get('teamAvg', 0)
            z = item.get('zScore', 0)
            comment = severity_comment(z)
            lines.append(
                f"· {label}: {fmt_val(metric, val)} | "
                f"队友均 {fmt_val(metric, avg)} — {comment}")

        return '\n'.join(lines)
