"""快捷喊话设置页：总开关 / 发送参数 / 话术库管理（分组·热键·循环预览）/ 发送日志。

设计要点：
- 热键改绑走 keys.validate_hotkey 保存时硬拦截（LOL 高危区/系统占用/冲突）。
- 组内循环防护（D11）：每个分组卡片展示固定循环顺序与"下一条"预览。
- 内置话术可编辑（自动标 dirty 保护用户版），用户分组可整体删除。
"""
import time
import uuid

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QWidget, QLabel, QHBoxLayout, QVBoxLayout,
                             QTableWidgetItem, QAbstractItemView)

from app.common.chat_config import chat_cfg
from app.common.icons import Icon
from app.common.qfluentwidgets import (SettingCard, SwitchSettingCard, InfoBar,
                                       InfoBarPosition, ExpandGroupSettingCard,
                                       LineEdit, PushButton, TransparentPushButton,
                                       CheckBox, SpinBox, TableWidget,
                                       MessageBox)
from app.common.style_sheet import StyleSheet
from app.components.seraphine_interface import SeraphineInterface
from app.chat.domain.keys import HotkeyError, validate_hotkey
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


class GroupCard(ExpandGroupSettingCard):
    """单个话术分组的管理卡片。"""

    def __init__(self, group: dict, interface):
        # 注意：PyQt 下 super().__init__ 之前不得给 self 赋属性
        super().__init__(Icon.COMMENT, group["name"],
                         "分组热键 + 组内循环话术", interface)
        self.group = group
        self.interface = interface

        self.hotkeyRow = QWidget(self.view)
        self.hotkeyLayout = QHBoxLayout(self.hotkeyRow)
        self.hotkeyLabel = QLabel(self.tr("分组快捷键（点击后直接按下组合键）："))
        self.hotkeyEdit = KeyCaptureEdit()
        self.hotkeySaveBtn = PushButton(self.tr("保存快捷键"))

        self.cycleRow = QWidget(self.view)
        self.cycleLayout = QHBoxLayout(self.cycleRow)
        self.nextLabel = QLabel()
        self.resetCycleBtn = TransparentPushButton(self.tr("重置循环游标"))

        self.phraseContainer = QWidget(self.view)
        self.phraseLayout = QVBoxLayout(self.phraseContainer)

        self.addRow = QWidget(self.view)
        self.addLayout = QHBoxLayout(self.addRow)
        self.addEdit = LineEdit()
        self.addBtn = PushButton(self.tr("添加话术"))

        self.deleteGroupBtn = TransparentPushButton(self.tr("删除此分组"))

        self.__initLayout()
        self.__initWidget()
        self.reload_phrases()
        self.refresh_preview()

    # ---------- 布局 ----------

    def __initLayout(self):
        self.hotkeyLayout.setContentsMargins(48, 18, 44, 6)
        self.hotkeyLayout.addWidget(self.hotkeyLabel, alignment=Qt.AlignLeft)
        self.hotkeyLayout.addWidget(self.hotkeyEdit, alignment=Qt.AlignRight)
        self.hotkeyLayout.addWidget(self.hotkeySaveBtn, alignment=Qt.AlignRight)

        self.cycleLayout.setContentsMargins(48, 6, 44, 6)
        self.cycleLayout.addWidget(self.nextLabel, alignment=Qt.AlignLeft)
        self.cycleLayout.addStretch(1)
        self.cycleLayout.addWidget(self.resetCycleBtn, alignment=Qt.AlignRight)

        self.phraseLayout.setContentsMargins(48, 6, 44, 6)
        self.phraseLayout.setSpacing(6)

        self.addLayout.setContentsMargins(48, 6, 44, 6)
        self.addLayout.addWidget(self.addEdit)
        self.addLayout.addWidget(self.addBtn, alignment=Qt.AlignRight)

        bottomRow = QWidget(self.view)
        bottomLayout = QHBoxLayout(bottomRow)
        bottomLayout.setContentsMargins(48, 6, 44, 18)
        bottomLayout.addWidget(self.deleteGroupBtn, alignment=Qt.AlignLeft)

        self.viewLayout.setSpacing(0)
        self.viewLayout.setContentsMargins(0, 0, 0, 0)
        self.addGroupWidget(self.hotkeyRow)
        self.addGroupWidget(self.cycleRow)
        self.addGroupWidget(self.phraseContainer)
        self.addGroupWidget(self.addRow)
        if self.group["pack_id"] != BUILTIN_PACK_ID:
            self.addGroupWidget(bottomRow)

    def __initWidget(self):
        self.hotkeyEdit.setText(self.group.get("hotkey") or "")
        self.hotkeyEdit.setPlaceholderText(self.tr("点击后按键，Esc清空"))
        self.hotkeyEdit.setMaximumWidth(140)
        self.hotkeySaveBtn.clicked.connect(self.__on_save_hotkey)
        self.resetCycleBtn.clicked.connect(self.__on_reset_cycle)
        self.addEdit.setPlaceholderText(self.tr("输入新话术内容"))
        self.addBtn.clicked.connect(self.__on_add_phrase)
        self.addEdit.returnPressed.connect(self.__on_add_phrase)
        self.deleteGroupBtn.clicked.connect(self.__on_delete_group)

    # ---------- 数据刷新 ----------

    def reload_phrases(self):
        while self.phraseLayout.count():
            item = self.phraseLayout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for p in self.interface.repo.list_phrases(self.group["id"]):
            self.phraseLayout.addWidget(self.__make_phrase_row(p))

    def __make_phrase_row(self, p: dict) -> QWidget:
        row = QWidget(self.phraseContainer)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)

        edit = LineEdit()
        edit.setText(p["content"])
        enabledBox = CheckBox(self.tr("启用"))
        enabledBox.setChecked(bool(p["enabled"]))
        delBtn = TransparentPushButton(self.tr("删除"))

        layout.addWidget(edit, 1)
        layout.addWidget(enabledBox)
        layout.addWidget(delBtn)

        edit.editingFinished.connect(
            lambda pid=p["id"], e=edit: self.__on_edit_phrase(pid, e))
        enabledBox.stateChanged.connect(
            lambda _state, pid=p["id"], b=enabledBox: (
                self.interface.repo.set_phrase_enabled(pid, b.isChecked()),
                self.refresh_preview()))
        delBtn.clicked.connect(
            lambda _checked=False, pid=p["id"]: self.__on_remove_phrase(pid))
        return row

    def refresh_preview(self):
        nxt = self.interface.repo.peek_next_phrase(self.group["id"])
        text = nxt["content"] if nxt else self.tr("(暂无启用的话术)")
        self.nextLabel.setText(self.tr("下一次将发送：") + text)

    # ---------- 事件 ----------

    def __on_save_hotkey(self):
        hotkey = self.hotkeyEdit.text().strip()
        try:
            if hotkey:
                validate_hotkey(
                    hotkey,
                    existing=self.interface.repo.list_hotkey_bindings(),
                    self_id=self.group["id"])
        except HotkeyError as e:
            InfoBar.error(title=self.tr("热键冲突或不合法"), content=str(e),
                          orient=Qt.Vertical, isClosable=True,
                          position=InfoBarPosition.TOP_RIGHT, duration=5000,
                          parent=self.interface)
            self.hotkeyEdit.setText(self.group.get("hotkey") or "")
            return
        self.interface.repo.update_group_fields(
            self.group["id"], hotkey=hotkey or "")
        self.group["hotkey"] = hotkey
        chat_service.refresh_hotkeys()
        self.interface.refresh_status()
        InfoBar.success(title=self.tr("热键已保存"), content=hotkey or self.tr("已清除"),
                        orient=Qt.Vertical, isClosable=True,
                        position=InfoBarPosition.TOP_RIGHT, duration=3000,
                        parent=self.interface)

    def __on_reset_cycle(self):
        self.interface.repo.reset_cycle(self.group["id"])
        self.refresh_preview()

    def __on_add_phrase(self):
        content = self.addEdit.text().strip()
        if not content:
            return
        phrases = self.interface.repo.list_phrases(self.group["id"])
        self.interface.repo.upsert_phrase(
            _new_id("u.p"), self.group["id"], content,
            sort=(phrases[-1]["sort"] + 1 if phrases else 1),
            pack_id="user")
        self.addEdit.clear()
        self.reload_phrases()
        self.refresh_preview()

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

    def __on_delete_group(self):
        box = MessageBox(
            self.tr("删除分组"),
            self.tr("确定要删除该分组及其全部话术吗？此操作不可撤销。"),
            self.interface.window())
        box.yesButton.setText(self.tr("删除"))
        box.cancelButton.setText(self.tr("取消"))
        if box.exec_():
            self.interface.repo.delete_group(self.group["id"])
            chat_service.refresh_hotkeys()
            self.interface.refresh_groups()
            self.interface.refresh_status()


class ChatInterface(SeraphineInterface):
    """快捷喊话设置页（独立导航项）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ChatInterface")
        self._initCommon(self.tr("快捷喊话"), StyleSheet.CHAT_INTERFACE)

        self.repo = chat_service.repo
        self.groupCards = []

        # 总开关
        self.enableCard = SwitchSettingCard(
            Icon.COMMENT, self.tr("启用快捷喊话"),
            self.tr("开启全局热键一键发送预设短语（局内模拟键盘输入，选人与房间走 LCU 通道）"),
            chat_cfg.enabled, self)
        self.enableCard.checkedChanged.connect(self.__on_enable_changed)

        # 运行状态检测与测试
        self.statusCard = SettingCard(
            Icon.INFO, self.tr("运行状态与调试"),
            self.tr("检测当前客户端环境并支持直接测试发送"), self)
        self.statusLabel = QLabel(self)
        self.refreshStatusBtn = TransparentPushButton(self.tr("刷新状态"), self)
        self.refreshStatusBtn.clicked.connect(self.refresh_status)
        self.testEdit = LineEdit(self)
        self.testEdit.setPlaceholderText(self.tr("输入测试文本，如：集合打龙"))
        self.testEdit.setMaximumWidth(200)
        self.testBtn = PushButton(self.tr("测试发送"), self)
        self.testBtn.clicked.connect(self.__on_test_send)
        self.statusCard.hBoxLayout.addWidget(self.statusLabel)
        self.statusCard.hBoxLayout.addSpacing(10)
        self.statusCard.hBoxLayout.addWidget(self.refreshStatusBtn)
        self.statusCard.hBoxLayout.addSpacing(16)
        self.statusCard.hBoxLayout.addWidget(self.testEdit)
        self.statusCard.hBoxLayout.addWidget(self.testBtn)
        self.statusCard.hBoxLayout.addSpacing(16)

        # 发送参数
        self.paramCard = SettingCard(
            Icon.SETTING, self.tr("发送频率限制"),
            self.tr("两次发送最小间隔（带随机抖动，防止固定频率被检测）"), self)
        self.intervalSpin = SpinBox(self)
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
            chat_cfg.useClipboard, self)
        self.clipboardCard.checkedChanged.connect(self.__on_params_changed)

        # 新建分组
        self.newGroupCard = SettingCard(
            Icon.TEXTEDIT, self.tr("新建话术分组"),
            self.tr("创建独立话术组并可绑定专属快捷键"), self)
        self.newNameEdit = LineEdit(self)
        self.newNameEdit.setPlaceholderText(self.tr("分组名称，如：战术"))
        self.newNameEdit.setMaximumWidth(160)
        self.newHotkeyEdit = KeyCaptureEdit(self)
        self.newHotkeyEdit.setPlaceholderText(self.tr("点击后按键（可选）"))
        self.newHotkeyEdit.setMaximumWidth(150)
        self.newGroupBtn = PushButton(self.tr("创建分组"), self)
        self.newGroupBtn.clicked.connect(self.__on_create_group)
        self.newGroupCard.hBoxLayout.addWidget(self.newNameEdit)
        self.newGroupCard.hBoxLayout.addWidget(self.newHotkeyEdit)
        self.newGroupCard.hBoxLayout.addWidget(self.newGroupBtn)
        self.newGroupCard.hBoxLayout.addSpacing(16)

        # 动态分组卡片容器
        self.groupContainer = QWidget(self.scrollWidget)
        self.groupContainerLayout = QVBoxLayout(self.groupContainer)
        self.groupContainerLayout.setContentsMargins(0, 0, 0, 0)
        self.groupContainerLayout.setSpacing(12)

        # 词库信息
        self.packCard = SettingCard(
            Icon.DOCUMENT, self.tr("内置词库信息"),
            "", self)
        self.packLabel = QLabel(self)
        self.packCard.hBoxLayout.addWidget(self.packLabel)
        self.packCard.hBoxLayout.addSpacing(16)

        # 发送日志
        self.logCard = SettingCard(
            Icon.LOG, self.tr("最近发送日志"),
            self.tr("展示最近 100 条快捷喊话记录（本地保留 30 天）"), self)
        self.logTable = TableWidget(self)
        self.logTable.setColumnCount(4)
        self.logTable.setHorizontalHeaderLabels(
            [self.tr("时间"), self.tr("话术内容"), self.tr("发送通道"),
             self.tr("发送结果")])
        self.logTable.verticalHeader().hide()
        self.logTable.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.logTable.setMinimumHeight(260)
        self.logRefreshBtn = PushButton(self.tr("刷新日志"), self)
        self.logRefreshBtn.clicked.connect(self.refresh_logs)
        self.logCard.hBoxLayout.addWidget(self.logRefreshBtn)
        self.logCard.hBoxLayout.addSpacing(16)

        self.__initLayout()
        self.refresh_groups()
        self.refresh_status()
        self.refresh_logs()
        self.__refresh_pack_info()

    def __initLayout(self):
        self.expandLayout.setSpacing(18)
        self.expandLayout.setContentsMargins(36, 10, 36, 0)
        self.expandLayout.addWidget(self.enableCard)
        self.expandLayout.addWidget(self.statusCard)
        self.expandLayout.addWidget(self.paramCard)
        self.expandLayout.addWidget(self.clipboardCard)
        self.expandLayout.addWidget(self.newGroupCard)
        self.expandLayout.addWidget(self.groupContainer)
        self.expandLayout.addWidget(self.packCard)
        self.expandLayout.addWidget(self.logCard)
        self.expandLayout.addWidget(self.logTable)

    # ---------- 数据刷新 ----------

    def refresh_groups(self):
        while self.groupContainerLayout.count():
            item = self.groupContainerLayout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.groupCards = []
        for g in self.repo.list_groups():
            card = GroupCard(g, self)
            self.groupCards.append(card)
            self.groupContainerLayout.addWidget(card)

    def refresh_status(self):
        phase = chat_service.phase
        phase_map = {
            "InProgress": "对局进行中",
            "ChampSelect": "英雄选择阶段",
            "Lobby": "组队大厅",
            "Matchmaking": "匹配中",
            "ReadyCheck": "就绪确认",
            "GameStart": "游戏加载中",
            "None": "客户端闲置",
        }
        phase_str = phase_map.get(phase, phase or "未连接/未开始")
        hotkeys = chat_service.registered_hotkeys()
        hk_str = f"已注册 {len(hotkeys)} 个 ({', '.join(hotkeys)})" if hotkeys else "未注册（总开关关闭或未绑定）"
        self.statusLabel.setText(f"【环境状态】阶段: {phase_str}  |  热键: {hk_str}")

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
        self.packLabel.setText(
            self.tr("内置中文词库 v%s（包含 5 组 25 条，支持自定义扩展）") % version)

    # ---------- 事件 ----------

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
        self.refresh_groups()
        self.refresh_status()

    def __on_test_send(self):
        text = self.testEdit.text().strip() or "Seraphine 快捷喊话测试"
        import asyncio
        asyncio.ensure_future(self._async_test_send(text))

    async def _async_test_send(self, text: str):
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
                title=self.tr("测试发送拦截"),
                content=self.tr(f"原因: {detail}"),
                orient=Qt.Vertical, isClosable=True,
                position=InfoBarPosition.TOP_RIGHT, duration=5000,
                parent=self)
        self.refresh_logs()
        self.refresh_status()
