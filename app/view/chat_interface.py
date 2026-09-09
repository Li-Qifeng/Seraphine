"""快捷喊话设置页：总开关 / 运行状态 / 测试发送 / 话术分组与内容管理 / 发送日志。

设计要点：
- 基础设置、话术分组管理、发送记录采用 SettingCardGroup 统一视觉分组，杜绝组件挤压错乱。
- 话术分组通过 SegmentedWidget 选项卡水平无缝切换，不再使用折叠手风琴；
- 当前选中分组的话术直接在 GroupDetailCard 中 100% 展开，支持直接修改、启用/停用、单条一键试发与删除。
- 测试发送针对局内（InProgress）场景提供自动切入游戏前台窗口机制，避免应用在前台导致检测失败。
"""
import asyncio
import time
import uuid

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QWidget, QLabel, QHBoxLayout, QVBoxLayout,
                             QTableWidgetItem, QAbstractItemView, QFrame)

from app.common.chat_config import chat_cfg
from app.common.icons import Icon
from app.common.qfluentwidgets import (SettingCard, SwitchSettingCard, InfoBar,
                                       InfoBarPosition, SettingCardGroup, CardWidget,
                                       SegmentedWidget, LineEdit, PushButton,
                                       TransparentPushButton, CheckBox, SpinBox,
                                       TableWidget, MessageBox)
from app.common.style_sheet import StyleSheet
from app.components.seraphine_interface import SeraphineInterface
from app.chat.domain.keys import HotkeyError, validate_hotkey
from app.chat.engine.foreground import activate_game_window, is_game_foreground
from app.chat.service import chat_service
from app.chat.store.seed import BUILTIN_PACK_ID

TAG = "ChatInterface"


def _new_id(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:10]}"


# ---------- 热键捕捉 ----------

# Qt 特殊键 → keys.py 键名（字母/数字/F 键/小键盘在函数内计算）
_QT_NAMED_KEYS = {
    Qt.Key_Space: "space", Qt.Key_Tab: "tab",
    Qt.Key_Return: "enter", Qt.Key_Enter: "enter", Qt.Key_Escape: "esc",
    Qt.Key_QuoteLeft: "`",
    Qt.Key_Up: "up", Qt.Key_Down: "down",
    Qt.Key_Left: "left", Qt.Key_Right: "right",
    Qt.Key_Insert: "insert", Qt.Key_Delete: "delete",
    Qt.Key_Home: "home", Qt.Key_End: "end",
    Qt.Key_PageUp: "pageup", Qt.Key_PageDown: "pagedown",
    Qt.Key_ScrollLock: "scrolllock", Qt.Key_Pause: "pause",
}
_QT_KEYPAD_KEYS = {
    Qt.Key_Period: "numdot", Qt.Key_Asterisk: "nummul",
    Qt.Key_Plus: "numadd", Qt.Key_Minus: "numsub", Qt.Key_Slash: "numdiv",
}
_KEY_DISPLAY = {
    "space": "Space", "tab": "Tab", "enter": "Enter", "esc": "Esc",
    "up": "Up", "down": "Down", "left": "Left", "right": "Right",
    "insert": "Insert", "delete": "Delete", "home": "Home", "end": "End",
    "pageup": "PageUp", "pagedown": "PageDown",
    "scrolllock": "ScrollLock", "pause": "Pause",
    "numdot": "NumDot", "nummul": "NumMul", "numadd": "NumAdd",
    "numsub": "NumSub", "numdiv": "NumDiv",
}


def qt_event_to_hotkey(key: int, modifiers) -> str:
    """QKeyEvent → 热键显示串（如 "Alt+1"）。无法识别返回 ""。"""
    if key in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta):
        return ""  # 纯修饰键，等主键
    mods = []
    if modifiers & Qt.ControlModifier:
        mods.append("Ctrl")
    if modifiers & Qt.AltModifier:
        mods.append("Alt")
    if modifiers & Qt.ShiftModifier:
        mods.append("Shift")
    if modifiers & Qt.MetaModifier:
        mods.append("Win")
    keypad = bool(modifiers & Qt.KeypadModifier)

    name = ""
    if Qt.Key_A <= key <= Qt.Key_Z:
        name = chr(ord("A") + key - Qt.Key_A)
    elif Qt.Key_0 <= key <= Qt.Key_9:
        digit = str(key - Qt.Key_0)
        name = ("Num" + digit) if keypad else digit
    elif Qt.Key_F1 <= key <= Qt.Key_F24:
        name = "F%d" % (key - Qt.Key_F1 + 1)
    elif keypad and key in _QT_KEYPAD_KEYS:
        name = _KEY_DISPLAY[_QT_KEYPAD_KEYS[key]]
    else:
        raw = _QT_NAMED_KEYS.get(key)
        if raw:
            name = _KEY_DISPLAY.get(raw, raw)
    if not name:
        return ""
    return "+".join(mods + [name]) if mods else name


class KeyCaptureEdit(LineEdit):
    """按键捕捉输入框：按下组合键自动填入；Esc/退格清空。不允许手打字符。"""

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key_Escape, Qt.Key_Backspace, Qt.Key_Delete) \
                and not (event.modifiers() & Qt.KeypadModifier):
            self.clear()
            return
        hotkey = qt_event_to_hotkey(key, event.modifiers())
        if hotkey:
            self.setText(hotkey)
        # 吞掉事件：捕捉模式下不进入正常文本编辑


# ---------- 选中分组详情卡片（全展开直接编辑） ----------

class GroupDetailCard(CardWidget):
    """当前选中分组的话术管理卡片（全展开、直接编辑、单条试发）。"""

    def __init__(self, interface, parent=None):
        super().__init__(parent=parent)
        self.interface = interface
        self.current_group_id = None
        self.group = None

        self.vLayout = QVBoxLayout(self)
        self.vLayout.setContentsMargins(24, 18, 24, 18)
        self.vLayout.setSpacing(12)

        # 顶部操作栏
        self.topRow = QWidget(self)
        self.topLayout = QHBoxLayout(self.topRow)
        self.topLayout.setContentsMargins(0, 0, 0, 0)
        self.topLayout.setSpacing(10)

        self.groupNameLabel = QLabel(self)
        self.groupNameLabel.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.groupTypeLabel = QLabel(self)
        self.groupTypeLabel.setStyleSheet("color: #888888; font-size: 13px;")

        self.hotkeyPromptLabel = QLabel(self.tr("快捷键:"), self)
        self.hotkeyEdit = KeyCaptureEdit(self)
        self.hotkeyEdit.setPlaceholderText(self.tr("点击按键, Esc清空"))
        self.hotkeyEdit.setFixedWidth(130)
        self.saveHotkeyBtn = PushButton(self.tr("保存快捷键"), self)
        self.saveHotkeyBtn.clicked.connect(self.__on_save_hotkey)

        self.resetCycleBtn = TransparentPushButton(self.tr("重置游标"), self)
        self.resetCycleBtn.clicked.connect(self.__on_reset_cycle)

        self.deleteGroupBtn = TransparentPushButton(self.tr("删除此分组"), self)
        self.deleteGroupBtn.clicked.connect(self.__on_delete_group)

        self.topLayout.addWidget(self.groupNameLabel)
        self.topLayout.addWidget(self.groupTypeLabel)
        self.topLayout.addStretch(1)
        self.topLayout.addWidget(self.hotkeyPromptLabel)
        self.topLayout.addWidget(self.hotkeyEdit)
        self.topLayout.addWidget(self.saveHotkeyBtn)
        self.topLayout.addWidget(self.resetCycleBtn)
        self.topLayout.addWidget(self.deleteGroupBtn)

        # 循环状态说明行
        self.cycleLabel = QLabel(self)
        self.cycleLabel.setStyleSheet("color: #666666; font-size: 13px;")

        # 话术列表容器
        self.phraseContainer = QWidget(self)
        self.phraseLayout = QVBoxLayout(self.phraseContainer)
        self.phraseLayout.setContentsMargins(0, 4, 0, 4)
        self.phraseLayout.setSpacing(8)

        # 底部添加新话术栏
        self.addRow = QWidget(self)
        self.addLayout = QHBoxLayout(self.addRow)
        self.addLayout.setContentsMargins(0, 6, 0, 0)
        self.addLayout.setSpacing(10)
        self.addEdit = LineEdit(self)
        self.addEdit.setPlaceholderText(self.tr("输入新话术内容，按 Enter 或点击添加"))
        self.addEdit.returnPressed.connect(self.__on_add_phrase)
        self.addBtn = PushButton(self.tr("添加话术"), self)
        self.addBtn.clicked.connect(self.__on_add_phrase)
        self.addLayout.addWidget(self.addEdit, 1)
        self.addLayout.addWidget(self.addBtn)

        self.vLayout.addWidget(self.topRow)
        self.vLayout.addWidget(self.cycleLabel)
        self.vLayout.addWidget(self._make_divider())
        self.vLayout.addWidget(self.phraseContainer)
        self.vLayout.addWidget(self._make_divider())
        self.vLayout.addWidget(self.addRow)

    def _make_divider(self) -> QWidget:
        line = QFrame(self)
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setStyleSheet("background-color: rgba(128, 128, 128, 0.15); max-height: 1px;")
        return line

    def adjustCardHeight(self):
        self.phraseContainer.updateGeometry()
        self.updateGeometry()
        h = max(self.vLayout.sizeHint().height(), 120)
        self.resize(self.width(), h)
        if self.parent() and hasattr(self.parent(), "adjustSize"):
            self.parent().adjustSize()

    def load_group(self, group_id: str):
        if not group_id or not isinstance(group_id, str):
            return
        self.current_group_id = group_id
        self.group = self.interface.repo.get_group(group_id)
        if not self.group:
            self.hide()
            if self.parent() and hasattr(self.parent(), "adjustSize"):
                self.parent().adjustSize()
            return
        self.show()

        self.groupNameLabel.setText(f"【{self.group['name']}】")
        is_builtin = self.group.get("pack_id") == BUILTIN_PACK_ID
        self.groupTypeLabel.setText(self.tr("(内置词库)") if is_builtin else self.tr("(自定义分组)"))
        self.hotkeyEdit.setText(self.group.get("hotkey") or "")
        self.deleteGroupBtn.setVisible(not is_builtin)

        self.refresh_preview()
        self.reload_phrases()

    def refresh_preview(self):
        if not self.current_group_id:
            return
        nxt = self.interface.repo.peek_next_phrase(self.current_group_id)
        text = nxt["content"] if nxt else self.tr("(暂无启用的话术)")
        self.cycleLabel.setText(self.tr("当前轮转状态：下一次按该分组快捷键将发送 → ") + f"「{text}」")

    def reload_phrases(self):
        while self.phraseLayout.count():
            item = self.phraseLayout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

        if not self.current_group_id:
            self.adjustCardHeight()
            return

        phrases = self.interface.repo.list_phrases(self.current_group_id)
        if not phrases:
            emptyLabel = QLabel(self.tr("该分组暂无话术，请在下方输入框添加"), self.phraseContainer)
            emptyLabel.setStyleSheet("color: #888888; font-style: italic; padding: 10px 0;")
            self.phraseLayout.addWidget(emptyLabel)
            emptyLabel.show()
        else:
            for i, p in enumerate(phrases):
                row = QWidget(self.phraseContainer)
                layout = QHBoxLayout(row)
                layout.setContentsMargins(0, 0, 0, 0)
                layout.setSpacing(10)

                idxLabel = QLabel(f"#{i+1}", row)
                idxLabel.setFixedWidth(28)
                idxLabel.setStyleSheet("color: #888888; font-weight: bold;")

                edit = LineEdit(row)
                edit.setText(p["content"])

                enabledBox = CheckBox(self.tr("启用"), row)
                enabledBox.setChecked(bool(p["enabled"]))

                testBtn = TransparentPushButton(self.tr("试发"), row)
                delBtn = TransparentPushButton(self.tr("删除"), row)

                layout.addWidget(idxLabel)
                layout.addWidget(edit, 1)
                layout.addWidget(enabledBox)
                layout.addWidget(testBtn)
                layout.addWidget(delBtn)

                edit.editingFinished.connect(
                    lambda pid=p["id"], e=edit: self.__on_edit_phrase(pid, e))
                enabledBox.stateChanged.connect(
                    lambda _state, pid=p["id"], b=enabledBox: (
                        self.interface.repo.set_phrase_enabled(pid, b.isChecked()),
                        self.refresh_preview()))
                testBtn.clicked.connect(
                    lambda _, text=p["content"]: self.interface.test_send_text(text))
                delBtn.clicked.connect(
                    lambda _, pid=p["id"]: self.__on_remove_phrase(pid))

                self.phraseLayout.addWidget(row)
                row.show()

        self.adjustCardHeight()

    def __on_save_hotkey(self):
        if not self.current_group_id:
            return
        hotkey = self.hotkeyEdit.text().strip()
        try:
            if hotkey:
                validate_hotkey(
                    hotkey,
                    existing=self.interface.repo.list_hotkey_bindings(),
                    self_id=self.current_group_id)
        except HotkeyError as e:
            InfoBar.error(title=self.tr("热键冲突或不合法"), content=str(e),
                          orient=Qt.Vertical, isClosable=True,
                          position=InfoBarPosition.TOP_RIGHT, duration=5000,
                          parent=self.interface)
            self.hotkeyEdit.setText(self.group.get("hotkey") or "")
            return

        self.interface.repo.update_group_fields(
            self.current_group_id, hotkey=hotkey or "")
        self.group["hotkey"] = hotkey
        chat_service.refresh_hotkeys()
        self.interface.refresh_status()
        self.interface.refresh_groups(keep_id=self.current_group_id)
        InfoBar.success(title=self.tr("热键已保存"), content=hotkey or self.tr("已清除"),
                        orient=Qt.Vertical, isClosable=True,
                        position=InfoBarPosition.TOP_RIGHT, duration=3000,
                        parent=self.interface)

    def __on_reset_cycle(self):
        if not self.current_group_id:
            return
        self.interface.repo.reset_cycle(self.current_group_id)
        self.refresh_preview()
        InfoBar.info(title=self.tr("循环游标已重置"), content=self.tr("下次将从本组第一条启用话术开始发送"),
                     orient=Qt.Vertical, isClosable=True,
                     position=InfoBarPosition.TOP_RIGHT, duration=2500,
                     parent=self.interface)

    def __on_add_phrase(self):
        if not self.current_group_id:
            return
        content = self.addEdit.text().strip()
        if not content:
            return
        phrases = self.interface.repo.list_phrases(self.current_group_id)
        self.interface.repo.upsert_phrase(
            _new_id("u.p"), self.current_group_id, content,
            sort=(phrases[-1]["sort"] + 1 if phrases else 1),
            pack_id="user")
        self.addEdit.clear()
        self.reload_phrases()
        self.refresh_preview()
        self.interface.refresh_groups(keep_id=self.current_group_id)

    def __on_edit_phrase(self, phrase_id: str, edit: LineEdit):
        content = edit.text().strip()
        if not content:
            return
        self.interface.repo.update_phrase_content(phrase_id, content)
        self.refresh_preview()

    def __on_remove_phrase(self, phrase_id: str):
        self.interface.repo.delete_phrase(phrase_id)
        self.reload_phrases()
        self.refresh_preview()
        self.interface.refresh_groups(keep_id=self.current_group_id)

    def __on_delete_group(self):
        if not self.current_group_id or not self.group:
            return
        if self.group.get("pack_id") == BUILTIN_PACK_ID:
            InfoBar.warning(title=self.tr("不可删除"), content=self.tr("内置词库分组不可整组删除"),
                            orient=Qt.Vertical, isClosable=True,
                            position=InfoBarPosition.TOP_RIGHT, duration=3000,
                            parent=self.interface)
            return

        box = MessageBox(
            self.tr("删除分组"),
            self.tr(f"确定要删除自定义分组【{self.group['name']}】及其全部话术吗？此操作不可撤销。"),
            self.interface.window())
        box.yesButton.setText(self.tr("删除"))
        box.cancelButton.setText(self.tr("取消"))
        if box.exec_():
            self.interface.repo.delete_group(self.current_group_id)
            chat_service.refresh_hotkeys()
            self.interface.refresh_groups()
            self.interface.refresh_status()
            InfoBar.success(title=self.tr("分组已删除"), content=self.group['name'],
                            orient=Qt.Vertical, isClosable=True,
                            position=InfoBarPosition.TOP_RIGHT, duration=3000,
                            parent=self.interface)


# ---------- 快捷喊话主界面 ----------

class ChatInterface(SeraphineInterface):
    """快捷喊话设置页（独立导航项）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ChatInterface")
        self._initCommon(self.tr("快捷喊话"), StyleSheet.CHAT_INTERFACE)

        self.repo = chat_service.repo
        self.active_group_id = None

        # 1. 基础设置组
        self.basicGroup = SettingCardGroup(self.tr("基础设置"), self.scrollWidget)

        self.enableCard = SwitchSettingCard(
            Icon.COMMENT, self.tr("启用快捷喊话"),
            self.tr("开启全局热键一键发送预设短语（局内模拟输入，选人与房间走 LCU 通道）"),
            chat_cfg.enabled, self.basicGroup)
        self.enableCard.checkedChanged.connect(self.__on_enable_changed)

        self.statusCard = SettingCard(
            Icon.INFO, self.tr("运行环境状态"),
            self.tr("正在检测客户端与全局热键状态..."), self.basicGroup)
        self.refreshStatusBtn = PushButton(self.tr("刷新状态"), self.statusCard)
        self.refreshStatusBtn.clicked.connect(self.refresh_status)
        self.statusCard.hBoxLayout.addWidget(self.refreshStatusBtn)
        self.statusCard.hBoxLayout.addSpacing(16)

        self.testCard = SettingCard(
            Icon.FEEDBACK, self.tr("测试发送"),
            self.tr("局内将自动激活游戏窗口并模拟输入发送，选人与房间走 LCU 通道"), self.basicGroup)
        self.testEdit = LineEdit(self.testCard)
        self.testEdit.setPlaceholderText(self.tr("输入测试文本，如：集合打龙"))
        self.testEdit.setFixedWidth(200)
        self.testBtn = PushButton(self.tr("测试发送"), self.testCard)
        self.testBtn.clicked.connect(self.__on_test_send)
        self.testCard.hBoxLayout.addWidget(self.testEdit)
        self.testCard.hBoxLayout.addWidget(self.testBtn)
        self.testCard.hBoxLayout.addSpacing(16)

        self.paramCard = SettingCard(
            Icon.SETTING, self.tr("发送频率限制"),
            self.tr("两次发送最小间隔（带随机抖动，防止固定频率被检测）"), self.basicGroup)
        self.intervalSpin = SpinBox(self.paramCard)
        self.intervalSpin.setRange(600, 5000)
        self.intervalSpin.setSingleStep(100)
        self.intervalSpin.setSuffix(" ms")
        self.intervalSpin.setValue(chat_cfg.get(chat_cfg.minIntervalMs))
        self.intervalSpin.valueChanged.connect(self.__on_params_changed)
        self.paramCard.hBoxLayout.addWidget(self.intervalSpin)
        self.paramCard.hBoxLayout.addSpacing(16)

        self.clipboardCard = SwitchSettingCard(
            Icon.COPY, self.tr("剪贴板粘贴模式"),
            self.tr("默认关闭（采用逐字安全模拟）。开启后通过剪贴板秒发，并在发送后延迟还原剪贴板"),
            chat_cfg.useClipboard, self.basicGroup)
        self.clipboardCard.checkedChanged.connect(self.__on_params_changed)

        self.basicGroup.addSettingCards([
            self.enableCard,
            self.statusCard,
            self.testCard,
            self.paramCard,
            self.clipboardCard,
        ])

        # 2. 话术分组与内容管理组
        self.manageGroup = SettingCardGroup(self.tr("话术分组与管理"), self.scrollWidget)

        self.newGroupCard = SettingCard(
            Icon.TEXTEDIT, self.tr("新建话术分组"),
            self.tr("创建独立自定义分组并可绑定专属全局快捷键"), self.manageGroup)
        self.newNameEdit = LineEdit(self.newGroupCard)
        self.newNameEdit.setPlaceholderText(self.tr("分组名称，如：战术"))
        self.newNameEdit.setFixedWidth(140)
        self.newHotkeyEdit = KeyCaptureEdit(self.newGroupCard)
        self.newHotkeyEdit.setPlaceholderText(self.tr("点击按键(可选)"))
        self.newHotkeyEdit.setFixedWidth(130)
        self.newGroupBtn = PushButton(self.tr("创建分组"), self.newGroupCard)
        self.newGroupBtn.clicked.connect(self.__on_create_group)
        self.newGroupCard.hBoxLayout.addWidget(self.newNameEdit)
        self.newGroupCard.hBoxLayout.addWidget(self.newHotkeyEdit)
        self.newGroupCard.hBoxLayout.addWidget(self.newGroupBtn)
        self.newGroupCard.hBoxLayout.addSpacing(16)

        # 分组选项卡 + 分组详情卡片（规范挂载到 manageGroup，通过 addSettingCards 注册）
        self.groupSegmented = SegmentedWidget(self.manageGroup)
        self.groupDetailCard = GroupDetailCard(self, parent=self.manageGroup)

        self.manageGroup.addSettingCards([
            self.newGroupCard,
            self.groupSegmented,
            self.groupDetailCard,
        ])

        # 3. 词库与发送记录组
        self.logGroup = SettingCardGroup(self.tr("词库与发送记录"), self.scrollWidget)

        self.packCard = SettingCard(
            Icon.DOCUMENT, self.tr("内置词库信息"),
            "", self.logGroup)

        self.logCard = SettingCard(
            Icon.LOG, self.tr("最近发送记录"),
            self.tr("展示最近 100 条快捷喊话记录（本地保留 30 天）"), self.logGroup)
        self.logRefreshBtn = PushButton(self.tr("刷新日志"), self.logCard)
        self.logRefreshBtn.clicked.connect(self.refresh_logs)
        self.logCard.hBoxLayout.addWidget(self.logRefreshBtn)
        self.logCard.hBoxLayout.addSpacing(16)

        self.logTable = TableWidget(self.logGroup)
        self.logTable.setColumnCount(4)
        self.logTable.setHorizontalHeaderLabels(
            [self.tr("时间"), self.tr("话术内容"), self.tr("发送通道"),
             self.tr("发送结果")])
        self.logTable.verticalHeader().hide()
        self.logTable.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.logTable.setMinimumHeight(240)

        self.logGroup.addSettingCards([
            self.packCard,
            self.logCard,
            self.logTable,
        ])

        self.__initLayout()
        self.refresh_groups()
        self.refresh_status()
        self.refresh_logs()
        self.__refresh_pack_info()
        self.manageGroup.adjustSize()
        self.logGroup.adjustSize()

    def __initLayout(self):
        self.expandLayout.setSpacing(28)
        self.expandLayout.setContentsMargins(36, 10, 36, 30)
        self.expandLayout.addWidget(self.basicGroup)
        self.expandLayout.addWidget(self.manageGroup)
        self.expandLayout.addWidget(self.logGroup)

    # ---------- 数据刷新 ----------

    def refresh_groups(self, keep_id=None):
        self.groupSegmented.clear()
        groups = self.repo.list_groups()
        target_id = keep_id or self.active_group_id
        if not any(g["id"] == target_id for g in groups):
            target_id = groups[0]["id"] if groups else None

        self.active_group_id = target_id

        for g in groups:
            hotkey = g.get("hotkey")
            count = len(self.repo.list_phrases(g["id"]))
            label = f"{g['name']} ({hotkey})" if hotkey else f"{g['name']} ({count})"
            self.groupSegmented.addItem(
                g["id"], label,
                onClick=lambda *_, gid=g["id"]: self.__on_select_group(gid)
            )

        if target_id:
            self.__on_select_group(target_id)
        else:
            self.groupDetailCard.hide()

    def __on_select_group(self, group_id: str):
        self.active_group_id = group_id
        self.groupSegmented.setCurrentItem(group_id)
        self.groupDetailCard.load_group(group_id)

    def refresh_status(self):
        phase = chat_service.phase
        phase_map = {
            "InProgress": "对局进行中 (InProgress)",
            "ChampSelect": "英雄选择阶段 (ChampSelect)",
            "Lobby": "组队大厅 (Lobby)",
            "Matchmaking": "匹配中",
            "ReadyCheck": "就绪确认",
            "GameStart": "游戏加载中",
            "None": "客户端闲置",
        }
        phase_str = phase_map.get(phase, phase or "未连接/未开始")
        hotkeys = chat_service.registered_hotkeys()
        hk_str = f"已注册 {len(hotkeys)} 个 ({', '.join(hotkeys)})" if hotkeys else "未注册（总开关关闭或未绑定）"

        # 校验管理员权限状态
        is_admin = False
        try:
            import ctypes
            is_admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            pass
        admin_tip = " | 权限: 管理员" if is_admin else " | 权限: 普通用户（若游戏以管理员运行，Seraphine 也需以管理员启动）"

        self.statusCard.setContent(f"【阶段】{phase_str}  |  【热键】{hk_str}{admin_tip}")

    def refresh_logs(self):
        rows = self.repo.list_send_logs(limit=100)
        self.logTable.setRowCount(len(rows))
        for i, row in enumerate(rows):
            self.logTable.setItem(i, 0, QTableWidgetItem(
                time.strftime("%m-%d %H:%M:%S", time.localtime(row["ts"]))))
            self.logTable.setItem(i, 1, QTableWidgetItem(row["text"]))
            self.logTable.setItem(i, 2, QTableWidgetItem(row["channel"]))
            result = self.tr("成功") if row["ok"] else (
                self.tr("失败: ") + (row["detail"] or ""))
            self.logTable.setItem(i, 3, QTableWidgetItem(result))
        self.logTable.resizeColumnsToContents()

    def __refresh_pack_info(self):
        version = self.repo.get_meta("builtin_pack_version") or "-"
        self.packCard.setContent(
            self.tr(f"内置中文词库 v{version}（包含 5 组 25 条预设战术话术，支持自由编辑与自定义新增）"))

    # ---------- 事件与发送 ----------

    def __on_enable_changed(self, checked: bool):
        chat_service.refresh_hotkeys()
        self.refresh_status()
        state = self.tr("已启用") if checked else self.tr("已关闭")
        InfoBar.info(title=self.tr("快捷喊话"), content=state,
                     orient=Qt.Vertical, isClosable=True,
                     position=InfoBarPosition.TOP_RIGHT, duration=3000,
                     parent=self)

    def __on_params_changed(self, *_args):
        chat_cfg.set(chat_cfg.minIntervalMs, self.intervalSpin.value())
        chat_service.update_rhythm()

    def __on_create_group(self):
        name = self.newNameEdit.text().strip()
        hotkey = self.newHotkeyEdit.text().strip()
        if not name:
            return
        try:
            if hotkey:
                validate_hotkey(
                    hotkey, existing=self.repo.list_hotkey_bindings())
        except HotkeyError as e:
            InfoBar.error(title=self.tr("热键冲突或不合法"), content=str(e),
                          orient=Qt.Vertical, isClosable=True,
                          position=InfoBarPosition.TOP_RIGHT, duration=5000,
                          parent=self)
            return

        groups = self.repo.list_groups()
        gid = _new_id("u.g")
        self.repo.upsert_group(gid, name, hotkey=hotkey,
                               sort=(groups[-1]["sort"] + 1 if groups else 1))
        self.newNameEdit.clear()
        self.newHotkeyEdit.clear()
        chat_service.refresh_hotkeys()
        self.refresh_groups(keep_id=gid)
        self.refresh_status()
        InfoBar.success(title=self.tr("分组创建成功"), content=name,
                        orient=Qt.Vertical, isClosable=True,
                        position=InfoBarPosition.TOP_RIGHT, duration=3000,
                        parent=self)

    def test_send_text(self, text: str):
        """单条话术一键试发入口。"""
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(self._async_test_send(text))

    def __on_test_send(self):
        text = self.testEdit.text().strip() or "Seraphine 快捷喊话测试"
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(self._async_test_send(text))

    async def _async_test_send(self, text: str):
        phase = chat_service.phase
        if phase == "InProgress":
            # 局内模拟击键发送：Seraphine 在前台时，自动将游戏窗口激活到前台
            if not is_game_foreground():
                activated = activate_game_window()
                if not activated:
                    InfoBar.warning(
                        title=self.tr("未找到游戏对局窗口"),
                        content=self.tr("局内发送需要游戏窗口运行在前台，未找到 League of Legends.exe 窗口"),
                        orient=Qt.Vertical, isClosable=True,
                        position=InfoBarPosition.TOP_RIGHT, duration=4000,
                        parent=self)
                    return
                # 等待 350ms 供 Windows 与游戏引擎完成前台激活与焦点捕获
                await asyncio.sleep(0.35)

        res = await chat_service.test_send(text)
        if res.get("ok"):
            InfoBar.success(
                title=self.tr("测试发送成功"),
                content=self.tr(f"已通过 {res.get('channel')} 通道发送: {text}"),
                orient=Qt.Vertical, isClosable=True,
                position=InfoBarPosition.TOP_RIGHT, duration=4000,
                parent=self)
        else:
            detail = res.get("detail") or res.get("stage") or "未知原因"
            InfoBar.warning(
                title=self.tr("测试发送未完成"),
                content=self.tr(f"原因: {detail}（当前阶段: {phase or '未连接'}）"),
                orient=Qt.Vertical, isClosable=True,
                position=InfoBarPosition.TOP_RIGHT, duration=5000,
                parent=self)
        self.refresh_logs()
        self.refresh_status()

    @property
    def groupCards(self):
        """兼容既有测试与接口检查。"""
        return self.repo.list_groups()

