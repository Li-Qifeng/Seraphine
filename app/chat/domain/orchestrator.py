"""SendOrchestrator：唯一发送出口。

所有入口（热键 / 设置页测试按钮 / 未来指令窗）必须经由此处，
否则限流、阶段闸、前台校验与发送日志无法保证不被绕过。

管线：busy 检查 → 阶段闸 → 取组内下一条（推进循环游标）
     → 节奏等待 → 通道发送 → 记账（send_log）。

依赖全注入（repo / rhythm / phase_provider / foreground_checker /
lcu_sender / ingame_sender），domain 层保持无 Qt / Win32 依赖。
"""
import asyncio
import time
from typing import Callable, Optional

from app.common.logger import logger

TAG = "ChatOrchestrator"

_INGAME_PHASE = "InProgress"
_LCU_PHASES = ("ChampSelect", "Lobby")


class SendOrchestrator:
    def __init__(self, repo, rhythm,
                 phase_provider: Callable[[], Optional[str]],
                 foreground_checker: Callable[[], bool],
                 lcu_sender: Callable,       # async (text) -> bool
                 ingame_sender: Callable,    # sync  (text) -> bool（自动 offload 到线程）
                 time_func: Callable[[], float] = time.monotonic):
        self._repo = repo
        self._rhythm = rhythm
        self._phase_provider = phase_provider
        self._foreground_checker = foreground_checker
        self._lcu_sender = lcu_sender
        self._ingame_sender = ingame_sender
        self._time = time_func
        self._lock = asyncio.Lock()

    def set_rhythm(self, rhythm):
        """运行期更新节奏参数（设置页调整后重建注入）。"""
        self._rhythm = rhythm

    async def send_group(self, group_id: str) -> dict:
        """发送指定分组的组内下一条。返回 {ok, stage, text, channel, detail}。"""
        if self._lock.locked():
            logger.debug("send_group dropped: busy", TAG)
            return {"ok": False, "stage": "busy", "text": None, "channel": None,
                    "detail": "发送正忙"}
        async with self._lock:
            return await self._do_send(group_id)

    async def send_direct(self, text: str) -> dict:
        """直接发送一段文本（供测试或即时喊话使用）。"""
        if self._lock.locked():
            return {"ok": False, "stage": "busy", "detail": "发送正忙"}
        async with self._lock:
            phase = self._phase_provider()
            if phase == _INGAME_PHASE:
                if not self._foreground_checker():
                    return {"ok": False, "stage": "gate", "detail": "游戏非前台窗口"}
                channel = "ingame"
            elif phase in _LCU_PHASES:
                channel = "lcu"
            else:
                return {"ok": False, "stage": "gate",
                        "detail": f"当前状态不可发送 ({phase or '未连接'})"}
            ok, detail = await self._send_via_channel(channel, text)
            self._repo.add_send_log(text, channel=channel, ok=ok, detail=detail)
            return {"ok": ok, "stage": "done" if ok else "send",
                    "text": text, "channel": channel, "detail": detail}

    async def _do_send(self, group_id: str) -> dict:
        phase = self._phase_provider()
        if phase == _INGAME_PHASE:
            if not self._foreground_checker():
                logger.warning("gate: game not foreground, dispatch skipped", TAG)
                return {"ok": False, "stage": "gate", "text": None, "channel": None,
                        "detail": "游戏非前台窗口"}
            channel = "ingame"
        elif phase in _LCU_PHASES:
            channel = "lcu"
        else:
            logger.warning(f"gate blocked: phase={phase}", TAG)
            return {"ok": False, "stage": "gate", "text": None, "channel": None,
                    "detail": f"当前状态不可发送 ({phase or '未连接'})"}

        phrase = self._repo.next_phrase_in_group(group_id)
        if not phrase:
            logger.warning(f"send_group aborted: group {group_id!r} has no enabled phrases", TAG)
            return {"ok": False, "stage": "empty", "text": None, "channel": None,
                    "detail": "该分组没有启用的话术"}
        text = phrase["content"]

        delay = self._rhythm.next_delay(self._time())
        if delay > 0:
            await asyncio.sleep(delay)
        self._rhythm.record(self._time())

        ok, detail = await self._send_via_channel(channel, text)
        self._repo.add_send_log(text, channel=channel, ok=ok, detail=detail)
        if ok:
            try:
                self._repo.record_use(phrase["id"])
            except Exception as e:
                logger.debug(f"record_use failed: {e}", TAG)
        return {"ok": ok, "stage": "done" if ok else "send",
                "text": text, "channel": channel, "detail": detail}

    async def _send_via_channel(self, channel: str, text: str):
        """返回 (ok, detail)。异常不外抛 —— 发送失败只记账与上报结果。"""
        try:
            if channel == "lcu":
                ok = await self._lcu_sender(text)
                return (True, "") if ok else (False, "lcu send failed")
            loop = asyncio.get_running_loop()
            ok = await loop.run_in_executor(None, self._ingame_sender, text)
            return (True, "") if ok else (False, "ingame send failed")
        except Exception as e:
            logger.warning(f"send via {channel} raised: {e}", TAG)
            return False, str(e)
