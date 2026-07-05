from typing import Optional

import math

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap, QPainter, QPainterPath, QColor, QFont, QPen
from PyQt5.QtWidgets import (QVBoxLayout, QHBoxLayout,
                             QLabel, QFrame, QWidget, QSizePolicy,
                             QSpacerItem)

from app.common.qfluentwidgets import (isDarkTheme, SmoothScrollArea)
from app.lol.war_criminal_cache import getVerdict
from app.lol.war_criminal_ui import METRIC_NAMES


# ── Design Tokens ──────────────────────────────────────────

_DARK_BG = '#07111D'
_PANEL_BG = '#101D2C'
_CARD_BG = '#162739'
_BLUE = '#2EA7FF'
_RED = '#E6525B'
_GOLD = '#F5C35B'
_TEXTP = '#FFFFFF'
_TEXTS = '#B0B8C4'
_BORDER = 'rgba(255,255,255,0.08)'

_SCORE_COLORS = [
    (1.0, _GOLD),   # z≥1.0 gold (grade 1)
    (0.3, _BLUE),   # z≥0.3 blue (grade 2)
    (-0.3, '#00D4AA'),  # z≥-0.3 cyan (grade 3)
    (-1.0, '#8B95A5'),  # z≥-1.0 grey (grade 4)
    (-999, _RED),   # z<-1.0 red (grade 5)
]

# ── Helpers ────────────────────────────────────────────────

def _mergeTeam(summoners: list, ratingList: list) -> list:
    byPuuid = {r.get('puuid'): r for r in (ratingList or [])}
    merged = []
    for s in summoners:
        puuid = s.get('puuid')
        rating = byPuuid.get(puuid, {})
        merged.append({
            'puuid': puuid,
            'summonerName': s.get('summonerName', '?'),
            'championIcon': s.get('championIcon', ''),
            'spell1Icon': s.get('spell1Icon', ''),
            'spell2Icon': s.get('spell2Icon', ''),
            'runeIcon': s.get('runeIcon', ''),
            'itemIcons': s.get('itemIcons', []),
            'kills': s.get('kills', 0), 'deaths': s.get('deaths', 0),
            'assists': s.get('assists', 0),
            'cs': s.get('cs', 0), 'gold': s.get('gold', 0),
            'champLevel': s.get('champLevel', 0),
            'tier': s.get('tier', ''), 'division': s.get('division', ''),
            'rankIcon': s.get('rankIcon', ''),
            'damage': s.get('damage', 0),
            'damageTaken': s.get('damageTaken', 0),
            'visionScore': s.get('visionScore', 0),
            'ccTime': s.get('ccTime', 0),
            'lane': s.get('lane', ''), 'role': s.get('role', ''),
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


def _teamTotals(players: list) -> dict:
    return {
        'totalDamage': sum(p.get('damage', 0) for p in players),
        'totalGold': sum(p.get('gold', 0) for p in players),
        'totalKills': sum(p.get('kills', 0) for p in players),
    }


def _pct(val: float, total: float) -> str:
    if total <= 0:
        return '0%'
    return f"{val / total * 100:.0f}%"


def _scoreColor(score: float) -> str:
    for threshold, color in _SCORE_COLORS:
        if score >= threshold:
            return color
    return _RED


def _buildInsights(bluePlayers: list, redPlayers: list) -> list:
    allPlayers = [('蓝', p) for p in bluePlayers] + [('红', p) for p in redPlayers]
    items = []
    for team_label, p in allPlayers:
        for e in (p.get('evidence') or []):
            z = e.get('zScore', 0)
            metric = METRIC_NAMES.get(e.get('metric', ''), e.get('metric', ''))
            items.append((abs(z), team_label, p['summonerName'], metric, z))
    items.sort(key=lambda x: x[0], reverse=True)
    insights = []
    seen = set()
    for _, team_label, name, metric, z in items:
        if len(insights) >= 4:
            break
        key = (name, metric)
        if key in seen:
            continue
        seen.add(key)
        if z >= 1.5:
            insights.append(f"🟢 {name}({team_label}) {metric} z={z:+.1f}")
        elif z <= -1.5:
            insights.append(f"🔴 {name}({team_label}) {metric} z={z:+.1f}")
    return insights


def _teamRadarVals(players: list) -> list:
    metrics = ['damage', 'damage_taken', 'gold', 'cc', 'vision', 'kill_participation']
    result = []
    for m in metrics:
        zs = []
        for p in players:
            for e in (p.get('evidence') or []):
                if e.get('metric') == m:
                    zs.append(e.get('zScore', 0))
        avg = sum(zs) / max(len(zs), 1) if zs else 0
        result.append(max(0.0, min(1.0, (avg + 2) / 4)))
    return result


_TEAM_RADAR_LABELS = ['输出', '承伤', '经济', '控制', '视野', '参团']

# ── Tab Utilities ──────────────────────────────────────────

_TAB_NAMES = ['总览', '数据', '经济', '符文', '装备', '时间线']

def _tabStyle(dark: bool, active: bool) -> str:
    font = "'Segoe UI', 'Microsoft YaHei'"
    color = '#2EA7FF' if active else ('#8B95A5' if dark else '#888')
    bg = 'rgba(46, 167, 255, 0.12)' if (active and dark) else \
         'rgba(46, 167, 255, 0.10)' if active else 'transparent'
    return (
        f"font-family: {font}; font-size: 12px; font-weight: bold; "
        f"color: {color}; background: {bg}; "
        f"border-radius: 4px; padding: 2px 10px;")


def _smallIcon(path: str, size: int = 18) -> QLabel:
    """Create a small icon QLabel from an image path."""
    lbl = QLabel()
    lbl.setFixedSize(size, size)
    if path:
        p = QPixmap(path)
        if not p.isNull():
            lbl.setPixmap(p.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
    lbl.setStyleSheet("border-radius: 2px;")
    return lbl

# ── HexagonScore ───────────────────────────────────────────

class HexagonScore(QWidget):
    """Compact score badge: colored hexagon with score number in center."""
    def __init__(self, score: float, size=76, parent=None):
        super().__init__(parent)
        self._score = score
        self._color_str = _scoreColor(score)
        self._color = QColor(self._color_str)
        self.setFixedSize(size, size)
        self._size = size

    def paintEvent(self, event):
        _renderBuf(self, self._draw)

    def _draw(self, p, w, h):
        r = self._size / 2 - 2
        cx, cy = w / 2, h / 2
        n = 6

        path = QPainterPath()
        for i in range(n + 1):
            angle = -math.pi / 2 + i * 2 * math.pi / n
            x = cx + r * math.cos(angle)
            y = cy + r * math.sin(angle)
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)

        p.setBrush(self._color)
        p.setPen(Qt.NoPen)
        p.drawPath(path)

        inner = QPainterPath()
        ir = r * 0.7
        for i in range(n + 1):
            angle = -math.pi / 2 + i * 2 * math.pi / n
            x = cx + ir * math.cos(angle)
            y = cy + ir * math.sin(angle)
            if i == 0:
                inner.moveTo(x, y)
            else:
                inner.lineTo(x, y)
        bg = QColor(self._color_str)
        bg.setAlpha(40)
        p.setBrush(bg)
        p.drawPath(inner)

        p.setFont(QFont('Consolas', int(self._size / 4.5), QFont.Bold))
        p.setPen(QColor('#FFFFFF'))
        text = f"{self._score:.1f}"
        fm = p.fontMetrics()
        tw = fm.horizontalAdvance(text)
        th = fm.height()
        p.drawText(int(cx - tw / 2), int(cy + th / 4), text)


# ── PlayerCard ─────────────────────────────────────────────

class PlayerCard(QFrame):
    """Player card with spells, rune, items, and score hexagon."""
    def __init__(self, data: dict, teamTotals: dict, parent=None):
        super().__init__(parent)
        dark = isDarkTheme()
        font = "'Segoe UI', 'Microsoft YaHei'"
        bg = _CARD_BG if dark else '#E8ECF0'
        border = _BORDER if dark else 'rgba(0,0,0,0.08)'
        self.setStyleSheet(f"""
            PlayerCard {{
                background: {bg}; border: 1px solid {border};
                border-radius: 8px;
            }}
        """)

        hl = QHBoxLayout(self)
        hl.setContentsMargins(6, 4, 6, 4)
        hl.setSpacing(6)

        # ── Champion icon + level + spells + rune ──
        iconCol = QVBoxLayout()
        iconCol.setSpacing(2)
        iconCol.setAlignment(Qt.AlignCenter)

        # Champion icon with level overlay
        iconC = QWidget()
        iconC.setFixedSize(48, 48)
        ci = QLabel(iconC)
        ci.setFixedSize(48, 48)
        ci.move(0, 0)
        champ_icon = data.get('championIcon', '')
        pix = QPixmap(champ_icon) if champ_icon else QPixmap()
        if not pix.isNull():
            ci.setPixmap(pix.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        ci.setStyleSheet("border-radius: 4px;")

        lv = QLabel(str(data.get('champLevel', 1)))
        lv.setFixedSize(18, 15)
        lv.move(0, 33)
        lv.setAlignment(Qt.AlignCenter)
        lv.setStyleSheet(
            "background: rgba(0,0,0,0.75); color: #fff;"
            "font-size: 9px; font-weight: bold; border-radius: 2px;")
        iconCol.addWidget(iconC)

        # Spell + rune row
        srRow = QHBoxLayout()
        srRow.setSpacing(2)
        srRow.setAlignment(Qt.AlignCenter)

        srRow.addWidget(_smallIcon(data.get('spell1Icon', '')))
        srRow.addWidget(_smallIcon(data.get('spell2Icon', '')))
        srRow.addWidget(_smallIcon(data.get('runeIcon', '')))
        iconCol.addLayout(srRow)

        hl.addLayout(iconCol)

        # ── Middle info column ──
        vi = QVBoxLayout()
        vi.setSpacing(1)

        # Name
        nameLabel = QLabel(data.get('summonerName', '?'))
        nl_color = _TEXTP if dark else '#222'
        nameLabel.setStyleSheet(
            f"font-family: {font}; font-size: 11px; font-weight: bold; "
            f"color: {nl_color}; background: transparent;")
        vi.addWidget(nameLabel)

        # KDA + CS + Gold
        k = data.get('kills', 0)
        d = data.get('deaths', 0)
        a = data.get('assists', 0)
        cs = data.get('cs', 0)
        gold = _formatGold(data.get('gold', 0))
        stats_color = _TEXTS if dark else '#777'
        stats = QLabel(f"{k}/{d}/{a}  {cs}CS  {gold}")
        stats.setStyleSheet(
            f"font-family: {font}; font-size: 10px; color: {stats_color}; background: transparent;")
        vi.addWidget(stats)

        # Damage%, Gold%, KP%, Vision
        dmg = _pct(data.get('damage', 0), teamTotals.get('totalDamage', 0))
        gld = _pct(data.get('gold', 0), teamTotals.get('totalGold', 0))
        kp_val = None
        for e in (data.get('evidence') or []):
            if e.get('metric') == 'kill_participation':
                kp_val = f"{e.get('value', 0)*100:.0f}%" if e.get('value') is not None else None
        vis = data.get('visionScore', 0)
        subs = f"{dmg}  {gld}  {kp_val or '--'}  {int(vis)}"
        pct_color = '#8899aa' if dark else '#888'
        pctLabel = QLabel(subs)
        pctLabel.setStyleSheet(
            f"font-family: {font}; font-size: 9px; color: {pct_color}; background: transparent;")
        vi.addWidget(pctLabel)

        # Items row
        items = data.get('itemIcons', [])
        itemsRow = QHBoxLayout()
        itemsRow.setSpacing(2)
        itemsRow.setAlignment(Qt.AlignLeft)
        for itemPath in items[:7]:
            il = QLabel()
            il.setFixedSize(20, 20)
            if itemPath:
                p = QPixmap(itemPath)
                if not p.isNull():
                    il.setPixmap(p.scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            il.setStyleSheet("border-radius: 2px; background: rgba(0,0,0,0.2);")
            itemsRow.addWidget(il)
        vi.addLayout(itemsRow)

        hl.addLayout(vi, 1)

        # ── HexagonScore ──
        score = data.get('score', 0)
        hs = HexagonScore(score, size=76)
        hl.addWidget(hs)


# ── TeamRadar (Compare Center) ─────────────────────────────

class TeamRadar(QWidget):
    def __init__(self, blueVals: list, redVals: list, parent=None):
        super().__init__(parent)
        self._blueVals = blueVals
        self._redVals = redVals
        self._n = len(blueVals)
        self.setFixedSize(172, 180)

    def paintEvent(self, event):
        _renderBuf(self, self._draw)

    def _draw(self, p, w, h):
        n = self._n
        r = min(w, h) / 2 - 24
        cx, cy = w / 2, h / 2

        for ring in (0.25, 0.5, 0.75):
            path = QPainterPath()
            for i in range(n + 1):
                angle = -math.pi / 2 + i * 2 * math.pi / n
                x = cx + r * ring * math.cos(angle)
                y = cy + r * ring * math.sin(angle)
                if i == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            p.setBrush(QColor('#1A2D44'))
            p.setPen(QPen(QColor('rgba(255,255,255,0.1)'), 0.5))
            p.drawPath(path)

        for i in range(n):
            angle = -math.pi / 2 + i * 2 * math.pi / n
            x = cx + r * math.cos(angle)
            y = cy + r * math.sin(angle)
            p.setPen(QPen(QColor('rgba(255,255,255,0.08)'), 0.5))
            p.drawLine(int(cx), int(cy), int(x), int(y))

            label_x = cx + (r + 14) * math.cos(angle)
            label_y = cy + (r + 14) * math.sin(angle)
            p.setPen(QColor('#8B95A5'))
            p.setFont(QFont('Segoe UI', 8))
            fm = p.fontMetrics()
            text = _TEAM_RADAR_LABELS[i]
            tw = fm.horizontalAdvance(text)
            p.drawText(int(label_x - tw / 2), int(label_y + 3), text)

        def _drawTeam(vals, color):
            path = QPainterPath()
            for i in range(n + 1):
                angle = -math.pi / 2 + i * 2 * math.pi / n
                v = vals[i % n]
                x = cx + r * v * math.cos(angle)
                y = cy + r * v * math.sin(angle)
                if i == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            c = QColor(color)
            fill = QColor(color)
            fill.setAlpha(35)
            p.setBrush(fill)
            p.setPen(QPen(c, 2))
            p.drawPath(path)

        _drawTeam(self._blueVals, _BLUE)
        _drawTeam(self._redVals, _RED)

        p.setPen(QColor('#8B95A5'))
        p.setFont(QFont('Segoe UI', 9))
        p.drawText(4, 14, "● 蓝队")
        p.drawText(w - 50, 14, "● 红队")


# ── Insights Summary ───────────────────────────────────────

class InsightsSummary(QFrame):
    def __init__(self, insights: list, parent=None):
        super().__init__(parent)
        dark = isDarkTheme()
        font = "'Segoe UI', 'Microsoft YaHei'"
        bg = _CARD_BG if dark else '#E8ECF0'
        self.setStyleSheet(f"background: {bg}; border: none; border-radius: 8px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(3)

        for ins in (insights or []):
            row = QLabel(ins)
            row.setStyleSheet(
                f"font-family: {font}; font-size: 10px; color: {'#ccc' if dark else '#444'};"
                f"background: transparent;")
            layout.addWidget(row)

        if not insights:
            empty = QLabel("暂无突出数据")
            empty.setStyleSheet(
                f"font-family: {font}; font-size: 10px; color: {'#666' if dark else '#aaa'};"
                f"background: transparent;")
            layout.addWidget(empty)


# ── CenterCompare ──────────────────────────────────────────

class CenterCompare(QFrame):
    def __init__(self, bluePlayers: list, redPlayers: list,
                 blueWin: bool, blueTeam: Optional[dict] = None,
                 redTeam: Optional[dict] = None, parent=None):
        super().__init__(parent)
        dark = isDarkTheme()
        font = "'Segoe UI', 'Microsoft YaHei'"
        bg = _PANEL_BG if dark else '#F0F2F5'
        border = _BORDER if dark else 'rgba(0,0,0,0.08)'
        self.setStyleSheet(f"""
            CenterCompare {{
                background: {bg}; border: 1px solid {border};
                border-radius: 8px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignCenter)

        blueScore = sum(p['score'] for p in bluePlayers) / max(len(bluePlayers), 1)
        redScore = sum(p['score'] for p in redPlayers) / max(len(redPlayers), 1)

        scoreLabel = QLabel(f"{blueScore:+.1f}  vs  {redScore:+.1f}")
        sc = _BLUE if blueScore >= redScore else _RED
        scoreLabel.setAlignment(Qt.AlignCenter)
        scoreLabel.setStyleSheet(
            f"font-family: {font}; font-size: 14px; font-weight: bold; "
            f"color: {sc}; background: transparent;")
        layout.addWidget(scoreLabel)

        blueVals = _teamRadarVals(bluePlayers)
        redVals = _teamRadarVals(redPlayers)
        layout.addWidget(TeamRadar(blueVals, redVals), 0, Qt.AlignCenter)

        bKills = sum(p['kills'] for p in bluePlayers)
        rKills = sum(p['kills'] for p in redPlayers)
        bGold = sum(p['gold'] for p in bluePlayers)
        rGold = sum(p['gold'] for p in redPlayers)
        ts_color = _TEXTS if dark else '#777'
        statsText = QLabel(
            f"击杀: {bKills} vs {rKills}    经济: {_formatGold(bGold)} vs {_formatGold(rGold)}")
        statsText.setAlignment(Qt.AlignCenter)
        statsText.setStyleSheet(
            f"font-family: {font}; font-size: 10px; color: {ts_color}; background: transparent;")
        layout.addWidget(statsText)

        # ── Resource Control ──
        bt = blueTeam or {}
        rt = redTeam or {}
        resources = [
            ('🔫 防御塔', bt.get('towerKills', 0), rt.get('towerKills', 0)),
            ('🐉 巨龙', bt.get('dragonKills', 0), rt.get('dragonKills', 0)),
            ('👹 先锋', bt.get('riftHeraldKills', 0), rt.get('riftHeraldKills', 0)),
            ('🐛 虚空虫', bt.get('hordeKills', 0), rt.get('hordeKills', 0)),
            ('👑 男爵', bt.get('baronKills', 0), rt.get('baronKills', 0)),
            ('🏛️ 水晶', bt.get('inhibitorKills', 0), rt.get('inhibitorKills', 0)),
        ]
        resLabel = QLabel('  '.join(
            f"{name} {b}/{r}" for name, b, r in resources if b or r))
        hasResources = any(b or r for _, b, r in resources)
        if not hasResources:
            resLabel.hide()
        resLabel.setWordWrap(True)
        resLabel.setAlignment(Qt.AlignCenter)
        rl_color = _TEXTS if dark else '#777'
        resLabel.setStyleSheet(
            f"font-family: {font}; font-size: 9px; color: {rl_color}; background: transparent;")
        layout.addWidget(resLabel)

        insights = _buildInsights(bluePlayers, redPlayers)
        if insights:
            layout.addWidget(InsightsSummary(insights))

        layout.addSpacerItem(QSpacerItem(1, 1, QSizePolicy.Minimum, QSizePolicy.Expanding))


# ── TeamPanel ──────────────────────────────────────────────

class TeamPanel(QFrame):
    def __init__(self, teamName: str, players: list, isWin: bool,
                 teamTotals: dict, parent=None):
        super().__init__(parent)
        dark = isDarkTheme()
        bg = _PANEL_BG if dark else '#F0F2F5'
        border = _BORDER if dark else 'rgba(0,0,0,0.08)'
        self.setStyleSheet(f"""
            TeamPanel {{
                background: {bg}; border: 1px solid {border};
                border-radius: 8px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        font = "'Segoe UI', 'Microsoft YaHei'"
        hColor = _BLUE if isWin else _RED
        avgScore = sum(p['score'] for p in players) / max(len(players), 1)
        header = QLabel(f"{teamName}  {avgScore:+.1f}")
        header.setStyleSheet(
            f"font-family: {font}; font-size: 12px; font-weight: bold; "
            f"color: {hColor}; background: transparent;")
        layout.addWidget(header)

        for p in players:
            layout.addWidget(PlayerCard(p, teamTotals))

        layout.addSpacerItem(QSpacerItem(1, 1, QSizePolicy.Minimum, QSizePolicy.Expanding))


# ── Bottom Chart Widgets ────────────────────────────────────

def _renderBuf(widget, drawFn):
    """Render widget content to offscreen QPixmap to avoid QPainter
    conflict with QGraphicsEffect applied by SmoothScrollArea."""
    w, h = widget.width(), widget.height()
    if w < 10 or h < 10:
        return
    buf = QPixmap(w, h)
    buf.fill(Qt.transparent)
    p = QPainter(buf)
    p.setRenderHint(QPainter.Antialiasing)
    try:
        drawFn(p, w, h)
    finally:
        p.end()
    p2 = QPainter(widget)
    p2.drawPixmap(0, 0, buf)
    p2.end()


# ── AnalysisPage ───────────────────────────────────────────

class AnalysisPage(QFrame):
    backRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._game = None
        self._teamContainer = None
        self._activeTab = 0
        self._tabLabels = []
        font = "'Segoe UI', 'Microsoft YaHei'"
        dark = isDarkTheme()

        self.setStyleSheet(f"AnalysisPage {{ background: {_DARK_BG if dark else '#E8ECF0'}; }}")

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        # ── Header ──
        self.headerWidget = QWidget()
        self.headerWidget.setFixedHeight(80)
        hb = _PANEL_BG if dark else '#FFFFFF'
        hborder = _BORDER if dark else 'rgba(0,0,0,0.08)'
        self.headerWidget.setStyleSheet(
            f"background: {hb}; border-bottom: 1px solid {hborder};")

        headerRow = QHBoxLayout(self.headerWidget)
        headerRow.setContentsMargins(16, 6, 16, 6)
        headerRow.setSpacing(12)

        # Back button
        self.backBtn = QLabel("←  赛后复盘")
        self.backBtn.setCursor(Qt.PointingHandCursor)
        self.backBtn.setStyleSheet(
            f"font-family: {font}; font-size: 15px; font-weight: bold; "
            f"color: {_BLUE}; background: transparent;")
        headerRow.addWidget(self.backBtn)

        # Tab bar
        tabBar = QHBoxLayout()
        tabBar.setSpacing(2)
        tabBar.setAlignment(Qt.AlignCenter)
        for i, name in enumerate(_TAB_NAMES):
            tab = QLabel(name)
            tab.setCursor(Qt.PointingHandCursor)
            tab.setFixedHeight(28)
            tab.setAlignment(Qt.AlignCenter)
            tab.setStyleSheet(_tabStyle(dark, i == 0))
            tab.mousePressEvent = lambda e, idx=i: self._switchTab(idx)
            tabBar.addWidget(tab)
            self._tabLabels.append(tab)
        headerRow.addLayout(tabBar, 1)

        # Game info
        self.infoLabel = QLabel("")
        ic = _TEXTS if dark else '#888'
        self.infoLabel.setStyleSheet(
            f"font-family: {font}; font-size: 13px; color: {ic}; background: transparent;")
        headerRow.addWidget(self.infoLabel)

        self._layout.addWidget(self.headerWidget)

        self.scrollArea = SmoothScrollArea()
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }")
        self.contentWidget = QWidget()
        self.contentWidget.setStyleSheet("background: transparent;")
        self.contentLayout = QVBoxLayout(self.contentWidget)
        self.contentLayout.setContentsMargins(0, 0, 0, 0)
        self.contentLayout.setSpacing(0)
        self.scrollArea.setWidget(self.contentWidget)
        self._layout.addWidget(self.scrollArea, 1)

        self.backBtn.mousePressEvent = lambda e: self.backRequested.emit()

    def _switchTab(self, idx: int):
        if idx == self._activeTab:
            return
        dark = isDarkTheme()
        for i, tab in enumerate(self._tabLabels):
            tab.setStyleSheet(_tabStyle(dark, i == idx))
        self._activeTab = idx
        # TODO: switch content view per tab when data/economy/rune/item/timeline views are implemented

    def loadGame(self, gameData: dict):
        self._game = gameData
        dark = isDarkTheme()

        if self._teamContainer:
            self._teamContainer.deleteLater()

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
        bluePlayers = _mergeTeam(
            winTeam.get('summoners', []), winnerRating) if win100 else \
            _mergeTeam(loseTeam.get('summoners', []), loserRating)
        redPlayers = _mergeTeam(
            loseTeam.get('summoners', []), loserRating) if win100 else \
            _mergeTeam(winTeam.get('summoners', []), winnerRating)

        modeName = gameData.get('modeName', '')
        mapName = gameData.get('mapName', '')
        duration = gameData.get('gameDuration', '')
        self.infoLabel.setText(f"{mapName}  ·  {modeName}  ·  {duration}")

        self._teamContainer = QWidget()
        cl = QVBoxLayout(self._teamContainer)
        cl.setContentsMargins(12, 8, 12, 8)
        cl.setSpacing(0)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.setContentsMargins(0, 0, 0, 0)

        blueTotals = _teamTotals(bluePlayers)
        redTotals = _teamTotals(redPlayers)

        row.addWidget(TeamPanel(
            "蓝队" if win100 else "红队",
            bluePlayers, win100, blueTotals), 8)

        row.addWidget(CenterCompare(
            bluePlayers, redPlayers, win100,
            blueTeam=team100 if win100 else team200,
            redTeam=team200 if win100 else team100), 9)

        row.addWidget(TeamPanel(
            "红队" if win100 else "蓝队",
            redPlayers, not win100, redTotals), 8)

        cl.addLayout(row, 1)

        self.contentLayout.addWidget(self._teamContainer)

        self.contentLayout.addStretch(1)
