from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QFrame, QWidget, QSizePolicy, QSpacerItem,
                             QScrollArea, QProgressBar)
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

        self.viewLayout.setContentsMargins(24, 16, 24, 16)
        self.viewLayout.setSpacing(12)
        font_family = "'Microsoft YaHei', 'Segoe UI', sans-serif"

        header = QHBoxLayout()
        title = TitleLabel(self.tr("Game Analysis"))
        title.setStyleSheet(f"font-family: {font_family};")
        info = QLabel(f"{mapName}  ·  {modeName}  ·  {duration}")
        info_color = '#aaaaaa' if dark else '#666666'
        info.setStyleSheet(
            f"font-family: {font_family}; font-size: 13px; color: {info_color};")
        header.addWidget(title)
        header.addSpacerItem(QSpacerItem(
            1, 1, QSizePolicy.Expanding, QSizePolicy.Minimum))
        header.addWidget(info)
        self.viewLayout.addLayout(header)

        divider = QFrame()
        divider.setFixedHeight(1)
        divider_color = 'rgba(255,255,255,0.08)' if dark else 'rgba(0,0,0,0.08)'
        divider.setStyleSheet(f"background: {divider_color}; border: none;")
        self.viewLayout.addWidget(divider)

        scrollArea = QScrollArea()
        scrollArea.setWidgetResizable(True)
        scrollArea.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
            "QWidget#viewport { background: transparent; }")
        scrollWidget = QWidget()
        scrollWidget.setStyleSheet("background: transparent;")
        teamsLayout = QHBoxLayout(scrollWidget)
        teamsLayout.setSpacing(12)
        teamsLayout.setContentsMargins(0, 4, 0, 4)

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
            QFrame {{
                border: 1px solid {border};
                border-radius: 10px;
                background: {bg};
            }}
        """)

        layout = QVBoxLayout(frame)
        layout.setSpacing(4)
        layout.setContentsMargins(12, 10, 12, 10)

        header_color = '#f0f0f0' if dark else '#222222'
        header = QLabel(f"{teamName}    {resultLabel}")
        header.setStyleSheet(
            f"font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;"
            f"font-size: 14px; font-weight: bold; padding: 2px 0;"
            f"color: {header_color};")
        layout.addWidget(header)

        maxAbsScore = 0.01
        if players:
            avgScore = sum(p['score'] for p in players) / len(players)
            maxAbsScore = max(abs(p['score']) for p in players)
            maxAbsScore = max(maxAbsScore, 0.01)
            avg_color = '#999999' if dark else '#888888'
            avgLabel = QLabel(
                self.tr("Avg contribution: ") + f"{avgScore:+.2f}")
            avgLabel.setStyleSheet(
                f"font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;"
                f"font-size: 11px; color: {avg_color}; padding-bottom: 6px;")
            layout.addWidget(avgLabel)

            for p in players:
                layout.addWidget(_PlayerRow(p, maxAbsScore))

        layout.addSpacerItem(QSpacerItem(
            1, 1, QSizePolicy.Minimum, QSizePolicy.Expanding))
        return frame


class _PlayerRow(QFrame):
    def __init__(self, data: dict, maxAbsScore: float = 1.0, parent=None):
        super().__init__(parent)
        dark = isDarkTheme()
        self.setFixedHeight(48)

        hover_bg = 'rgba(255,255,255,0.05)' if dark else 'rgba(0,0,0,0.04)'
        self.setStyleSheet(
            f"_PlayerRow {{ background: transparent; }}"
            f"_PlayerRow:hover {{ background: {hover_bg}; border-radius: 6px; }}")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 3, 6, 3)
        layout.setSpacing(8)

        grade = data.get('grade', 3)
        grade_color = GRADE_ACCENT.get(grade, '#888')
        font_family = "'Microsoft YaHei', 'Segoe UI', sans-serif"

        # 档位色指示条
        indicator = QFrame()
        indicator.setFixedSize(3, 32)
        indicator.setStyleSheet(
            f"background: {grade_color}; border-radius: 1px;")
        layout.addWidget(indicator)

        # 英雄头像 (32x32) + 段位角标 (右下角叠加)
        iconContainer = QWidget()
        iconContainer.setFixedSize(32, 32)
        champIcon = QLabel(iconContainer)
        champIcon.setFixedSize(32, 32)
        champIcon.move(0, 0)
        pixmap = QPixmap(data.get('championIcon', ''))
        if not pixmap.isNull():
            champIcon.setPixmap(pixmap.scaled(
                32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        champIcon.setStyleSheet("border-radius: 4px;")

        rankIconPath = data.get('rankIcon', '')
        if rankIconPath:
            rankPixmap = QPixmap(rankIconPath)
            if not rankPixmap.isNull():
                rankBadge = QLabel(iconContainer)
                rankBadge.setFixedSize(14, 14)
                rankBadge.move(18, 18)
                rankBadge.setPixmap(rankPixmap.scaled(
                    14, 14, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                rankBadge.setStyleSheet(
                    "background: rgba(0,0,0,0.65); border-radius: 3px; padding: 1px;")
        layout.addWidget(iconContainer)

        # 召唤师名 + 统计 (KDA · CS · 经济 · 段位)
        info = QVBoxLayout()
        info.setSpacing(0)
        name_color = '#f0f0f0' if dark else '#222222'
        name = QLabel(data.get('summonerName', '?'))
        name.setStyleSheet(
            f"font-family: {font_family}; font-size: 11px; font-weight: bold;"
            f"color: {name_color};")

        k = data.get('kills', 0)
        d = data.get('deaths', 0)
        a = data.get('assists', 0)
        cs = data.get('cs', 0)
        gold = _formatGold(data.get('gold', 0))
        tier = data.get('tier', '')
        division = data.get('division', '')

        stats_parts = [f"{k}/{d}/{a}", f"{cs} CS", f"{gold}"]
        if tier:
            tier_text = f"{tier} {division}".strip()
            stats_parts.append(tier_text)
        stats_text = "    ·    ".join(stats_parts)

        stats_color = '#a8a8a8' if dark else '#888888'
        kda = QLabel(stats_text)
        kda.setStyleSheet(
            f"font-family: {font_family}; font-size: 10px; color: {stats_color};")

        info.addWidget(name)
        info.addWidget(kda)
        layout.addLayout(info)

        layout.addSpacerItem(QSpacerItem(
            1, 1, QSizePolicy.Expanding, QSizePolicy.Minimum))

        # 评分可视化 (色条 + 评级+数字)
        score = data.get('score', 0)
        label = data.get('label', '')

        scoreViz = QVBoxLayout()
        scoreViz.setSpacing(2)
        scoreViz.setContentsMargins(0, 0, 0, 0)

        score_text = QLabel(f"{label}  {score:+.2f}")
        score_text.setFixedWidth(64)
        score_text.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        score_text.setStyleSheet(
            f"font-family: {font_family}; font-size: 11px; font-weight: bold;"
            f"color: {grade_color};")
        scoreViz.addWidget(score_text)

        score_bar = QProgressBar()
        score_bar.setFixedWidth(64)
        score_bar.setFixedHeight(4)
        score_bar.setRange(0, 100)
        score_bar.setTextVisible(False)
        pct = int((score / maxAbsScore + 1) / 2 * 100) if maxAbsScore > 0 else 50
        pct = max(0, min(100, pct))
        score_bar.setValue(pct)
        bar_bg = 'rgba(255,255,255,0.10)' if dark else 'rgba(0,0,0,0.06)'
        score_bar.setStyleSheet(f"""
            QProgressBar {{
                background: {bar_bg}; border: none; border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background: {grade_color}; border-radius: 2px;
            }}
        """)
        scoreViz.addWidget(score_bar)
        layout.addLayout(scoreViz)

        ev = data.get('evidence', [])
        if ev:
            btn = QPushButton("📊")
            btn.setFixedSize(24, 24)
            btn.setStyleSheet(
                "QPushButton { border: none; font-size: 12px; }"
                "QPushButton:hover { background: rgba(255,255,255,0.12); border-radius: 4px; }"
            )
            html = _formatEvidence(ev)
            btn.setToolTip(html)
            layout.addWidget(btn)
