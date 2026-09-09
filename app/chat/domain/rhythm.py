"""发送节奏：最小间隔 + 随机抖动 + 连发冷却（纯逻辑，可单测）。

反作弊最典型的行为画像特征是「毫秒级完全一致」，所以所有等待
都带抖动；这是行为层唯一真正影响封号概率的设计。
"""
import random
from collections import deque

# 硬下限：配置项低于此值直接拒绝（人类手速的物理下限）
MIN_INTERVAL_FLOOR_MS = 600


class Rhythm:
    def __init__(self, min_interval_ms: int = 800, jitter_ratio: float = 0.3,
                 burst_limit: int = 3, burst_cooldown_ms: int = 3000):
        if min_interval_ms < MIN_INTERVAL_FLOOR_MS:
            raise ValueError(
                f"发送间隔不得低于 {MIN_INTERVAL_FLOOR_MS}ms（防机器节奏特征）")
        self._min_ms = min_interval_ms
        self._jitter = jitter_ratio
        self._burst_limit = burst_limit
        self._cooldown_ms = burst_cooldown_ms
        self._history = deque(maxlen=max(burst_limit, 1))

    def record(self, now: float):
        """记录一次实际发送时间（秒）。"""
        self._history.append(now)

    def next_delay(self, now: float) -> float:
        """距下次允许发送还需等待的秒数（含抖动）。0 = 可立即发。"""
        wait = 0.0
        if self._history:
            elapsed_ms = (now - self._history[-1]) * 1000
            wait = max(0.0, (self._min_ms - elapsed_ms) / 1000)
        if len(self._history) >= self._burst_limit:
            burst_start = self._history[0]
            cooldown_left = self._cooldown_ms / 1000 - (now - burst_start)
            if cooldown_left > 0:
                wait = max(wait, cooldown_left)
        if wait > 0 and self._jitter > 0:
            wait *= random.uniform(1 - self._jitter, 1 + self._jitter)
        return max(0.0, wait)
