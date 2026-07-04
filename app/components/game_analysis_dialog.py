# DEPRECATED — use app.view.analysis_page.AnalysisPage instead

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QFrame, QWidget, QSizePolicy, QSpacerItem,
                             QProgressBar)
from app.common.qfluentwidgets import (MessageBoxBase, TitleLabel,
                                       isDarkTheme, SmoothScrollArea)

from app.lol.war_criminal_cache import getVerdict
from app.lol.war_criminal_ui import GRADE_ACCENT, METRIC_NAMES
from app.components.grade_badge import GradeBadge

SEV_DOT = {
    'high_pos': '<b style="color: #27ae60;">◆</b>',
    'pos': '<span style="color: #5bbd72;">◇</span>',
    'normal': '<span style="color: #888888;">·</span>',
    'neg': '<span style="color: #e67e22;">▲</span>',
    'high_neg': '<b style="color: #e74c3c;">✕</b>',
}


def _formatEvidence(evidence: list) -> str:
    lines = ['<div style="font-size: 12px; line-height: 1.6;">']
    for e in (evidence or []):
        sev = e.get('severity', '')
        dot = SEV_DOT.get(sev, '·')
        metric = METRIC_NAMES.get(e.get('metric', ''), e.get('metric', ''))
        z = e.get('zScore', 0)
        v = e.get('value', 0)
        avg = e.get('teamAvg', 0)
        lines.append(f'{dot} {metric}: <b>{v}</b> (队均 {avg}, z={z:+.2f})<br>')
    lines.append('</div>')
    return ''.join(lines)


def _mergeTeam(summoners: list, ratingList: list) -> list:
    byPuuid = {r.get('puuid'): r for r in (ratingList or [])}
    merged = []
    for s in summoners:
        puuid = s.get('puuid')
        rating = byPuuid.get(puuid, {})
        merged.append({
            'summonerName': s.get('summonerName', '?'),
            'championIcon': s.get('championIcon', ''),
            'kills': s.get('kills', 0), 'deaths': s.get('deaths', 0),
            'assists': s.get('assists', 0),
            'cs': s.get('cs', 0),
            'gold': s.get('gold', 0),
            'champLevel': s.get('champLevel', 0),
            'tier': s.get('tier', ''),
            'division': s.get('division', ''),
            'rankIcon': s.get('rankIcon', ''),
            'score': rating.get('score', 0), 'grade': rating.get('grade', 3),
            'label': rating.get('label', ''),
            'evidence': rating.get('evidence', []),
        })
    merged.sort(key=lambda x: x['score'], reverse=True)
    return merged


def _isWin(winField) -> bool:
    if isinstance(winField, str):
        return winField.lower() in ('win', 'true')
    return bool(winField) if winField is not None else False


def _formatGold(gold: int) -> str:
    if gold >= 1000:
        return f"{gold/1000:.1f}k"
    return str(gold)


class GameAnalysisDialog(MessageBoxBase):
    def __init__(self, gameData: dict, parent=None):
        super().__init__(parent=parent)
        self.yesButton.setVisible(False)
        self.cancelButton.setVisible(False)

        closeBtn = QPushButton(self.tr("Close"))
        closeBtn.setObjectName("cancelButton")
        closeBtn.clicked.connect(self.accept)
        self.buttonLayout.addWidget(closeBtn)

        self.widget.setMinimumWidth(720)
        self.widget.setMaximumWidth(880)
        self._buildContent(gameData)

    def _buildContent(self, gameData: dict):
        dark = isDarkTheme()
        gameId = gameData.get('gameId')
        verdict = getVerdict(gameId) if gameId else None
        winnerRating = (verdict or {}).get('winnerRating') or []
        loserRating = (verdict or {}).get('loserRating') or []

        teams = gameData.get('teams', {})
        team100 = teams.get(100, {})
        team200 = teams.get(200, {})

        win100 = _isWin(team100.get('win'))
        win200 = _isWin(team200.get('win'))

        winTeam = team100 if win100 else team200
        loseTeam = team200 if win100 else team100
        winSummoners = _mergeTeam(winTeam.get('summoners', []), winnerRating)
        loseSummoners = _mergeTeam(loseTeam.get('summoners', []), loserRating)

        modeName = gameData.get('modeName', '')
        mapName = gameData.get('mapName', '')
        duration = gameData.get('gameDuration', '')

        font = "'Segoe UI', 'Microsoft YaHei'"

        self.viewLayout.setContentsMargins(24, 20, 24, 16)
        self.viewLayout.setSpacing(12)

        header = QHBoxLayout()
        title = TitleLabel(self.tr("Game Analysis"))
        info_color = '#aaaaaa' if dark else '#666666'
        info = QLabel(f"{mapName}  ·  {modeName}  ·  {duration}")
        info.setStyleSheet(
            f"font-family: {font}; font-size: 13px; color: {info_color};")
        header.addWidget(title)
        header.addSpacerItem(QSpacerItem(
            1, 1, QSizePolicy.Expanding, QSizePolicy.Minimum))
        header.addWidget(info)
        self.viewLayout.addLayout(header)

        divider = QFrame()
        divider.setFixedHeight(1)
        c = 'rgba(255,255,255,0.08)' if dark else 'rgba(0,0,0,0.08)'
        divider.setStyleSheet(f"background: {c}; border: none;")
        self.viewLayout.addWidget(divider)

        teamsRow = QHBoxLayout()
        teamsRow.setSpacing(12)
        teamsRow.setContentsMargins(0, 0, 0, 0)

        teamsRow.addWidget(_TeamColumn(
            "Blue Team" if win100 else "Red Team",
            "🏆 Win", winSummoners, isWin=True))
        teamsRow.addWidget(_TeamColumn(
            "Red Team" if win100 else "Blue Team",
            "💀 Lose", loseSummoners, isWin=False))

        self.viewLayout.addLayout(teamsRow, 1)


class _TeamColumn(QFrame):
    def __init__(self, teamName: str, resultLabel: str,
                 players: list, isWin: bool = True, parent=None):
        super().__init__(parent)
        dark = isDarkTheme()
        if isWin:
            border = 'rgba(0,200,83,0.3)' if dark else 'rgba(0,200,83,0.4)'
            bg = 'rgba(0,200,83,0.06)' if dark else 'rgba(0,200,83,0.04)'
        else:
            border = 'rgba(255,65,54,0.3)' if dark else 'rgba(255,65,54,0.4)'
            bg = 'rgba(255,65,54,0.06)' if dark else 'rgba(255,65,54,0.04)'
        self.setStyleSheet(f"""
            _TeamColumn {{
                border: 1px solid {border};
                border-radius: 8px;
                background: {bg};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(10, 10, 10, 10)

        font = "'Segoe UI', 'Microsoft YaHei'"
        hc = '#f0f0f0' if dark else '#222222'
        header = QLabel(f"{teamName}    {resultLabel}")
        header.setStyleSheet(
            f"font-family: {font}; font-size: 13px; font-weight: bold; "
            f"color: {hc}; padding: 2px 0;")
        layout.addWidget(header)

        scroll = SmoothScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(min(len(players) * 44 + 10, 320))
        scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }")
        sp = QWidget()
        sp.setStyleSheet("background: transparent;")
        sl = QVBoxLayout(sp)
        sl.setSpacing(2)
        sl.setContentsMargins(0, 2, 0, 2)

        if players:
            avgScore = sum(p['score'] for p in players) / len(players)
            font = "'Segoe UI', 'Microsoft YaHei'"
            ac = '#999999' if dark else '#888888'
            avg = QLabel("Avg: " + f"{avgScore:+.2f}")
            avg.setStyleSheet(
                f"font-family: {font}; font-size: 11px; color: {ac}; "
                f"padding-bottom: 4px;")
            sl.addWidget(avg)

            maxAbs = max(abs(p['score']) for p in players)
            maxAbs = max(maxAbs, 0.01)
            for p in players:
                sl.addWidget(_PlayerRow(p, maxAbs))

        sl.addSpacerItem(QSpacerItem(
            1, 1, QSizePolicy.Minimum, QSizePolicy.Expanding))
        scroll.setWidget(sp)
        layout.addWidget(scroll, 1)


class _PlayerRow(QFrame):
    def __init__(self, data: dict, maxAbsScore: float = 1.0, parent=None):
        super().__init__(parent)
        dark = isDarkTheme()
        self.setFixedHeight(40)

        hover = 'rgba(255,255,255,0.04)' if dark else 'rgba(0,0,0,0.03)'
        self.setStyleSheet(
            "_PlayerRow { background: transparent; }"
            f"_PlayerRow:hover {{ background: {hover}; border-radius: 4px; }}")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        grade = data.get('grade', 3)
        gc = GRADE_ACCENT.get(grade, '#888')
        font = "'Segoe UI', 'Microsoft YaHei'"

        indicator = QFrame()
        indicator.setFixedSize(3, 28)
        indicator.setStyleSheet(f"background: {gc}; border-radius: 1px;")
        layout.addWidget(indicator)

        iconC = QWidget()
        iconC.setFixedSize(28, 28)
        ci = QLabel(iconC)
        ci.setFixedSize(28, 28)
        ci.move(0, 0)
        pix = QPixmap(data.get('championIcon', ''))
        if not pix.isNull():
            ci.setPixmap(pix.scaled(28, 28, Qt.KeepAspectRatio,
                                     Qt.SmoothTransformation))
        ci.setStyleSheet("border-radius: 3px;")
        ri = data.get('rankIcon', '')
        if ri:
            rp = QPixmap(ri)
            if not rp.isNull():
                rb = QLabel(iconC)
                rb.setFixedSize(11, 11)
                rb.move(15, 15)
                rb.setPixmap(rp.scaled(11, 11, Qt.KeepAspectRatio,
                                        Qt.SmoothTransformation))
                rb.setStyleSheet(
                    "background: rgba(0,0,0,0.65); border-radius: 2px;")
        layout.addWidget(iconC)

        info = QVBoxLayout()
        info.setSpacing(0)
        nc = '#f0f0f0' if dark else '#222222'
        name = QLabel(data.get('summonerName', '?'))
        name.setStyleSheet(
            f"font-family: {font}; font-size: 10px; font-weight: bold; "
            f"color: {nc};")

        k = data.get('kills', 0)
        d = data.get('deaths', 0)
        a = data.get('assists', 0)
        cs = data.get('cs', 0)
        gold = _formatGold(data.get('gold', 0))
        tier = data.get('tier', '')
        div = data.get('division', '')
        sparts = [f"{k}/{d}/{a}", f"{cs} CS", f"{gold}"]
        if tier:
            sparts.append(f"{tier} {div}".strip())
        sc = '#a8a8a8' if dark else '#888888'
        kda = QLabel("  ".join(sparts))
        kda.setStyleSheet(
            f"font-family: {font}; font-size: 9px; color: {sc};")

        info.addWidget(name)
        info.addWidget(kda)
        layout.addLayout(info)

        layout.addSpacerItem(QSpacerItem(
            1, 1, QSizePolicy.Expanding, QSizePolicy.Minimum))

        score = data.get('score', 0)
        label = data.get('label', '')

        badge = GradeBadge(grade, label, isCurrent=False)
        layout.addWidget(badge)

        bar = QProgressBar()
        bar.setFixedWidth(50)
        bar.setFixedHeight(4)
        bar.setRange(0, 100)
        bar.setTextVisible(False)
        pct = int((score / maxAbsScore + 1) / 2 * 100) if maxAbsScore > 0 else 50
        pct = max(0, min(100, pct))
        bar.setValue(pct)
        bb = 'rgba(255,255,255,0.10)' if dark else 'rgba(0,0,0,0.06)'
        bar.setStyleSheet(f"""
            QProgressBar {{
                background: {bb}; border: none; border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background: {gc}; border-radius: 2px;
            }}
        """)
        layout.addWidget(bar)

        ev = data.get('evidence', [])
        if ev:
            btn = QPushButton("📊")
            btn.setFixedSize(20, 20)
            btn.setStyleSheet(
                "QPushButton { border: none; font-size: 11px; }"
                "QPushButton:hover { background: rgba(255,255,255,0.1); "
                "border-radius: 3px; }")
            html = _formatEvidence(ev)
            btn.setToolTip(html)
            layout.addWidget(btn)
