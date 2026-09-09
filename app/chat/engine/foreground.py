"""前台判定：游戏窗口（League of Legends.exe）是否为前台。

铁律：必须用**进程名**判定，不能用窗口类名 —— 客户端与游戏的窗口类名
都是 RiotWindowClass。标题回退时注意区分：游戏标题是
「League of Legends (TM) Client」，客户端标题是「League of Legends」。
"""
import psutil
import win32gui
import win32process

from app.common.logger import logger

TAG = "ChatForeground"
_GAME_EXE = "league of legends.exe"
_GAME_TITLE_MARK = "(TM) Client"


def is_game_foreground() -> bool:
    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        return False
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        return psutil.Process(pid).name().lower() == _GAME_EXE
    except psutil.AccessDenied:
        # 反作弊挡 psutil 时回退标题匹配（只认游戏窗口的 (TM) Client 标记）
        try:
            title = win32gui.GetWindowText(hwnd) or ""
            ok = _GAME_TITLE_MARK in title
            logger.debug(f"foreground by title={ok} ({title[:60]})", TAG)
            return ok
        except Exception as e:
            logger.debug(f"foreground title fallback failed: {e}", TAG)
            return False
    except (psutil.NoSuchProcess, Exception) as e:
        logger.debug(f"is_game_foreground failed: {e}", TAG)
        return False
