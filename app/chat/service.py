"""ChatService：快捷喊话子系统单例门面。

生命周期：MainWindow.__init__ 调 init(app) → 装原生事件过滤器 + 订阅
signalBus.gameStatusChanged + 装载热键（若总开关开启）；
退出时调 shutdown() 注销热键、关 DB。

接线纪律：不改 MainWindow.__conncetSignalToSlot，所有接线都在此处完成。
"""
import asyncio

from PyQt5.QtCore import QObject

from app.common.chat_config import chat_cfg
from app.common.logger import logger
from app.common.signals import signalBus
from app.chat.domain.orchestrator import SendOrchestrator
from app.chat.domain.rhythm import Rhythm
from app.chat.engine.foreground import is_game_foreground
from app.chat.engine.hotkey import HotkeyManager
from app.chat.engine.input_sim import send_text
from app.chat.store.db import ChatDb
from app.chat.store.repo import ChatRepo
from app.chat.store.seed import ensure_seed

TAG = "ChatService"

# LCU 通道：不同阶段的会话类型优先级（见 connector.sendChatMessage）
_CONV_TYPES_BY_PHASE = {
    "ChampSelect": ("championSelect",),
    "Lobby": ("party", "customGame", "lol-chat", "chat"),
}


class ChatService(QObject):
    def __init__(self):
        super().__init__()
        self._inited = False
        self._db = None
        self._repo = None
        self._orchestrator = None
        self._hotkeys = None
        self._phase = None

    # ---------- 生命周期 ----------

    def init(self, app, hwnd: int = None):
        if self._inited:
            if hwnd and self._hotkeys:
                self._hotkeys.set_hwnd(hwnd)
            return
        self._db = ChatDb()
        self._repo = ChatRepo(self._db)
        ensure_seed(self._repo)
        self._repo.prune_send_logs(days=30)

        self._orchestrator = SendOrchestrator(
            repo=self._repo,
            rhythm=self._build_rhythm(),
            phase_provider=lambda: self._phase,
            foreground_checker=is_game_foreground,
            lcu_sender=self._lcu_send,
            ingame_sender=self._ingame_send,
        )

        self._hotkeys = HotkeyManager(parent=self, hwnd=hwnd)
        self._hotkeys.triggered.connect(self._on_hotkey_triggered)
        app.installNativeEventFilter(self._hotkeys.event_filter)

        signalBus.gameStatusChanged.connect(self._on_game_status_changed)
        signalBus.lolClientEnded.connect(self._on_client_ended)
        signalBus.lcuNotConnected.connect(self._on_client_ended)

        self._inited = True
        self.refresh_hotkeys()
        self._try_sync_active_phase()
        logger.info(f"chat service inited (hwnd={hwnd})", TAG)

    def set_hwnd(self, hwnd: int):
        """设置主窗口 HWND，用于绑定全局热键消息路由。"""
        if self._hotkeys:
            self._hotkeys.set_hwnd(hwnd)
            self.refresh_hotkeys()

    def shutdown(self):
        if not self._inited:
            return
        if self._hotkeys:
            self._hotkeys.unregister_all()
        if self._db:
            self._db.close()
        self._inited = False
        logger.info("chat service shutdown", TAG)

    # ---------- 对外属性与方法 ----------

    @property
    def phase(self):
        return self._phase

    @property
    def repo(self) -> ChatRepo:
        return self._repo

    @property
    def orchestrator(self) -> SendOrchestrator:
        return self._orchestrator

    def registered_hotkeys(self) -> list:
        return self._hotkeys.registered_hotkeys() if self._hotkeys else []

    async def test_send(self, text: str) -> dict:
        """测试发送指定文本，用于设置页或调试。"""
        return await self._orchestrator.send_direct(text)

    # ---------- 热键与生命周期 ----------

    def refresh_hotkeys(self):
        """总开关开启时装载全部分组热键，关闭时全部注销。"""
        if not self._hotkeys:
            return
        if chat_cfg.get(chat_cfg.enabled):
            self._hotkeys.register_bindings(self._repo.list_hotkey_bindings())
        else:
            self._hotkeys.unregister_all()

    def _on_hotkey_triggered(self, group_id: str):
        # 热键事件在 Qt 线程（qasync 循环）到达，直接派生协程
        logger.info(f"hotkey triggered for group={group_id}, dispatching send_group", TAG)
        asyncio.ensure_future(self._handle_send_group(group_id))

    async def _handle_send_group(self, group_id: str):
        res = await self._orchestrator.send_group(group_id)
        ok = res.get("ok")
        stage = res.get("stage")
        detail = res.get("detail")
        channel = res.get("channel")
        text = res.get("text")
        if ok:
            logger.info(f"send_group SUCCESS: group={group_id}, channel={channel}, text={text!r}", TAG)
        else:
            logger.warning(f"send_group FAILED: group={group_id}, stage={stage}, detail={detail}", TAG)

    def _on_game_status_changed(self, status):
        old_phase = self._phase
        self._phase = None if status in (None, "", "None") else status
        if old_phase != self._phase:
            logger.info(f"chat service: phase updated {old_phase} -> {self._phase}", TAG)

    def _on_client_ended(self):
        self._phase = None
        logger.info("chat service: client disconnected, phase reset", TAG)

    def _try_sync_active_phase(self):
        """如果 Seraphine 启动时 LOL 已在运行，主动同步当前阶段。"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self._do_sync_phase())
        except Exception:
            pass

    async def _do_sync_phase(self):
        try:
            from app.lol.connector import connector
            if hasattr(connector, "lcuSess") and connector.lcuSess:
                status = await connector.getGameStatus()
                if status:
                    self._on_game_status_changed(status)
        except Exception as e:
            logger.debug(f"sync active phase: {e}", TAG)

    # ---------- 发送通道 ----------

    async def _lcu_send(self, text: str) -> bool:
        from app.lol.connector import connector
        conv_types = _CONV_TYPES_BY_PHASE.get(self._phase, ("championSelect",))
        return await connector.sendChatMessage(text, conv_types)

    def _ingame_send(self, text: str) -> bool:
        return send_text(text, use_clipboard=chat_cfg.get(chat_cfg.useClipboard))

    def _build_rhythm(self) -> Rhythm:
        return Rhythm(
            min_interval_ms=chat_cfg.get(chat_cfg.minIntervalMs),
            burst_limit=chat_cfg.get(chat_cfg.burstLimit),
            burst_cooldown_ms=chat_cfg.get(chat_cfg.burstCooldownMs),
        )

    def update_rhythm(self):
        """设置页修改节奏参数后重建注入。"""
        if self._orchestrator:
            self._orchestrator.set_rhythm(self._build_rhythm())


chat_service = ChatService()
