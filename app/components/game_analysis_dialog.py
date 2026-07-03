from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QFrame, QWidget, QSizePolicy, QSpacerItem,
                             QScrollArea)
from app.common.qfluentwidgets import MessageBoxBase, TitleLabel, isDarkTheme

from app.lol.war_criminal_cache import getVerdict
from app.lol.war_criminal_ui import GRADE_ACCENT, METRIC_NAMES

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


class GameAnalysisDialog(MessageBoxBase):
    def __init__(self, gameData: dict, parent=None):
        super().__init__(parent=parent)
        self.yesButton.setVisible(False)
        self.cancelButton.setVisible(False)

        closeBtn = QPushButton(self.tr("Close"))
        closeBtn.setObjectName("cancelButton")
        closeBtn.clicked.connect(self.accept)
        self.buttonLayout.addWidget(closeBtn)

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

        header = QHBoxLayout()
        title = TitleLabel(self.tr("Game Analysis"))
        info = QLabel(f"{mapName} · {modeName} · {duration}")
        info_color = '#aaaaaa' if dark else '#666666'
        info.setStyleSheet(f"font-size: 13px; color: {info_color};")
        header.addWidget(title)
        header.addSpacerItem(QSpacerItem(1, 1, QSizePolicy.Expanding, QSizePolicy.Minimum))
        header.addWidget(info)
        self.viewLayout.addLayout(header)

        scrollArea = QScrollArea()
        scrollArea.setWidgetResizable(True)
        scrollArea.setStyleSheet("QScrollArea { border: none; }")
        scrollWidget = QWidget()
        teamsLayout = QHBoxLayout(scrollWidget)
        teamsLayout.setSpacing(12)

        teamsLayout.addWidget(self._makeTeamColumn(
            "Blue Team" if win100 else "Red Team",
            "🏆 Win", winSummoners, isWin=True))
        teamsLayout.addWidget(self._makeTeamColumn(
            "Red Team" if win100 else "Blue Team",
            "💀 Lose", loseSummoners, isWin=False))

        scrollArea.setWidget(scrollWidget)
        self.viewLayout.addWidget(scrollArea, 1)

    def _makeTeamColumn(self, teamName: str, resultLabel: str,
                        players: list, isWin: bool = True) -> QFrame:
        dark = isDarkTheme()
        frame = QFrame()
        if isWin:
            border = 'rgba(0,200,83,0.3)' if dark else 'rgba(0,200,83,0.4)'
            bg = 'rgba(0,200,83,0.06)' if dark else 'rgba(0,200,83,0.04)'
        else:
            border = 'rgba(255,65,54,0.3)' if dark else 'rgba(255,65,54,0.4)'
            bg = 'rgba(255,65,54,0.06)' if dark else 'rgba(255,65,54,0.04)'
        frame.setStyleSheet(f"""
            QFrame {{ border: 1px solid {border}; border-radius: 8px; background: {bg}; }}
        """)

        layout = QVBoxLayout(frame)
        layout.setSpacing(4)

        header_color = '#e0e0e0' if dark else '#333333'
        header = QLabel(f"{teamName}  {resultLabel}")
        header.setStyleSheet(
            f"font-size: 14px; font-weight: bold; padding: 4px 0; color: {header_color};")
        layout.addWidget(header)

        if players:
            avgScore = sum(p['score'] for p in players) / len(players)
            avg_color = '#888888' if dark else '#999999'
            avgLabel = QLabel(
                self.tr("Avg contribution: ") + f"{avgScore:+.2f}")
            avgLabel.setStyleSheet(
                f"font-size: 11px; color: {avg_color}; padding-bottom: 4px;")
            layout.addWidget(avgLabel)

        for p in players:
            layout.addWidget(_PlayerRow(p))

        layout.addSpacerItem(QSpacerItem(1, 1, QSizePolicy.Minimum, QSizePolicy.Expanding))
        return frame


class _PlayerRow(QFrame):
    def __init__(self, data: dict, parent=None):
        super().__init__(parent)
        dark = isDarkTheme()
        self.setFixedHeight(44)

        if dark:
            row_style = "_PlayerRow:hover { background: rgba(255,255,255,0.03); border-radius: 4px; }"
        else:
            row_style = "_PlayerRow:hover { background: rgba(0,0,0,0.03); border-radius: 4px; }"
        self.setStyleSheet(row_style)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        grade = data.get('grade', 3)
        grade_color = GRADE_ACCENT.get(grade, '#888')

        indicator = QFrame()
        indicator.setFixedSize(3, 28)
        indicator.setStyleSheet(f"background: {grade_color}; border-radius: 1px;")
        layout.addWidget(indicator)

        icon = QLabel()
        icon.setFixedSize(32, 32)
        pixmap = QPixmap(data.get('championIcon', ''))
        if not pixmap.isNull():
            icon.setPixmap(pixmap.scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        icon.setStyleSheet("border-radius: 3px;")
        layout.addWidget(icon)

        info = QVBoxLayout()
        info.setSpacing(0)
        name_color = '#e0e0e0' if dark else '#333333'
        name = QLabel(data.get('summonerName', '?'))
        name.setStyleSheet(f"font-size: 11px; color: {name_color};")
        k = data.get('kills', 0)
        d = data.get('deaths', 0)
        a = data.get('assists', 0)
        kda_color = '#777777' if dark else '#999999'
        kda = QLabel(f"{k}/{d}/{a}")
        kda.setStyleSheet(f"font-size: 10px; color: {kda_color};")
        info.addWidget(name)
        info.addWidget(kda)
        layout.addLayout(info)

        layout.addSpacerItem(QSpacerItem(1, 1, QSizePolicy.Expanding, QSizePolicy.Minimum))

        score = data.get('score', 0)
        label = data.get('label', '')
        badge = QLabel(f"{label} {score:+.2f}")
        badge.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {grade_color};")
        layout.addWidget(badge)

        ev = data.get('evidence', [])
        if ev:
            btn = QPushButton("📊")
            btn.setFixedSize(22, 22)
            btn.setStyleSheet(
                "QPushButton { border: none; font-size: 12px; }"
                "QPushButton:hover { background: rgba(255,255,255,0.1); border-radius: 3px; }"
            )
            html = _formatEvidence(ev)
            btn.setToolTip(html)
            layout.addWidget(btn)
