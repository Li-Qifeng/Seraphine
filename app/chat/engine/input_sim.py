"""局内发送引擎：SendInput(KEYEVENTF_UNICODE) 逐字 + Enter 序列 + 剪贴板整条（默认关）。

调研踩坑沉淀（D:\\Code\\lol-chat memory，务必保持）：
1. 所有 Win32 函数显式声明 argtypes/restype —— ctypes 默认返回 c_int(32 位)，
   64 位下 HANDLE 高位截断，GlobalLock/GlobalSize 静默失败（不报错只拿不到数据）。
2. LOL 读原始扫描码：Enter/Ctrl 只填 wVk 不填 wScan 会被游戏完全忽略，
   必须 wScan = MapVirtualKey(vk, MAPVK_VK_TO_VSC)。
3. 聊天框是异步消息队列消费：Enter down 后 UI 需 1~2 帧进输入态，
   紧随字符会被当作游戏按键丢弃 → 每步间必须 sleep（防首字/末字/整句丢失）。
4. 剪贴板路径：先写剪贴板再开框；Ctrl+V 落地需 ~120ms+，PASTE_SETTLE 300ms
   后才能按发送 Enter，否则发空消息；还原前检测用户新复制，绝不覆盖用户剪贴板。
"""
import ctypes
import random
import threading
import time
from ctypes import wintypes

from app.common.logger import logger

TAG = "ChatInputSim"

# ---- 时序常量（调研基线，见 references/C、D）----
KEY_DELAY_MS = 20            # 字符 down/up 对之间的基准间隔
KEY_JITTER_MS = 15           # 抖动上限（禁止毫秒级完全一致）
PRE_TYPE_DELAY_MS = 80       # 开框 Enter → 首个字符（留足输入框激活时间）
POST_TYPE_DELAY_MS = 50      # 末字符 → 发送 Enter
CHATBOX_READY_DELAY_MS = 300  # 剪贴板路径：开框后等输入框就绪
PASTE_SETTLE_DELAY_MS = 300   # Ctrl+V → 发送 Enter
CLIPBOARD_RESTORE_DELAY_MS = 800  # 必须 > PASTE_SETTLE

VK_RETURN = 0x0D
VK_CONTROL = 0x11
VK_V = 0x56
MAPVK_VK_TO_VSC = 0
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
GMEM_MOVEABLE = 0x0002
CF_UNICODETEXT = 13

# ---- ctypes 结构体（x64 下 INPUT 为 40 字节）----


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", INPUT_UNION)]


def _declare_signatures():
    """显式声明 argtypes/restype（64 位 HANDLE 截断铁律）。"""
    u32 = ctypes.windll.user32
    k32 = ctypes.windll.kernel32
    u32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
    u32.SendInput.restype = wintypes.UINT
    u32.MapVirtualKeyW.argtypes = (wintypes.UINT, wintypes.UINT)
    u32.MapVirtualKeyW.restype = wintypes.UINT
    u32.OpenClipboard.argtypes = (wintypes.HWND,)
    u32.OpenClipboard.restype = wintypes.BOOL
    u32.CloseClipboard.argtypes = ()
    u32.CloseClipboard.restype = wintypes.BOOL
    u32.EmptyClipboard.argtypes = ()
    u32.EmptyClipboard.restype = wintypes.BOOL
    u32.EnumClipboardFormats.argtypes = (wintypes.UINT,)
    u32.EnumClipboardFormats.restype = wintypes.UINT
    u32.GetClipboardData.argtypes = (wintypes.UINT,)
    u32.GetClipboardData.restype = wintypes.HANDLE
    u32.SetClipboardData.argtypes = (wintypes.UINT, wintypes.HANDLE)
    u32.SetClipboardData.restype = wintypes.HANDLE
    u32.GetClipboardSequenceNumber.argtypes = ()
    u32.GetClipboardSequenceNumber.restype = wintypes.DWORD
    k32.GlobalAlloc.argtypes = (wintypes.UINT, ctypes.c_size_t)
    k32.GlobalAlloc.restype = wintypes.HANDLE
    k32.GlobalFree.argtypes = (wintypes.HANDLE,)
    k32.GlobalFree.restype = wintypes.HANDLE
    k32.GlobalLock.argtypes = (wintypes.HANDLE,)
    k32.GlobalLock.restype = ctypes.c_void_p
    k32.GlobalUnlock.argtypes = (wintypes.HANDLE,)
    k32.GlobalUnlock.restype = wintypes.BOOL
    k32.GlobalSize.argtypes = (wintypes.HANDLE,)
    k32.GlobalSize.restype = ctypes.c_size_t
    return u32, k32


try:
    _U32, _K32 = _declare_signatures()
except (OSError, AttributeError) as e:
    # 非 Windows 环境（CI）下 windll.user32 不存在；发送路径本就只能真机跑
    logger.warning(f"input_sim: Win32 unavailable: {e}", TAG)
    _U32 = _K32 = None


# ---- 纯构建逻辑（可单测）----

def build_unicode_inputs(text: str):
    """把字符串构建为 KEYEVENTF_UNICODE 输入事件序列（每码元 down/up 成对）。

    返回 (INPUT 列表)。>0xFFFF 的字符（emoji 等）按 UTF-16 代理对拆成两个码元。
    纯函数，不触碰 Win32，可单测。
    """
    events = []
    for ch in text:
        code = ord(ch)
        if code > 0xFFFF:
            code -= 0x10000
            units = (0xD800 + (code >> 10), 0xDC00 + (code & 0x3FF))
        else:
            units = (code,)
        for unit in units:
            for flags in (KEYEVENTF_UNICODE, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP):
                inp = INPUT()
                inp.type = INPUT_KEYBOARD
                inp.u.ki = KEYBDINPUT(0, unit, flags, 0, None)
                events.append(inp)
    return events


def _jittered_ms(base: int) -> float:
    return (base + random.uniform(0, KEY_JITTER_MS)) / 1000


def _send_array(inputs) -> bool:
    sent = _U32.SendInput(len(inputs), (INPUT * len(inputs))(*inputs),
                          ctypes.sizeof(INPUT))
    if sent != len(inputs):
        logger.warning(f"SendInput partial: {sent}/{len(inputs)}", TAG)
        return False
    return True


def _press_enter() -> bool:
    scan = _U32.MapVirtualKeyW(VK_RETURN, MAPVK_VK_TO_VSC)
    down = INPUT()
    down.type = INPUT_KEYBOARD
    down.u.ki = KEYBDINPUT(VK_RETURN, scan, 0, 0, None)
    up = INPUT()
    up.type = INPUT_KEYBOARD
    up.u.ki = KEYBDINPUT(VK_RETURN, scan, KEYEVENTF_KEYUP, 0, None)
    if not _send_array([down]):
        return False
    time.sleep((20 + random.uniform(5, 15)) / 1000)  # 20~35ms 驻留时间，确保游戏帧引擎采样
    return _send_array([up])


def _send_keys(text: str) -> bool:
    """通道 A：Enter 开框 → 逐字注入 → Enter 发送。"""
    if not _press_enter():
        return False
    time.sleep(_jittered_ms(PRE_TYPE_DELAY_MS))
    events = build_unicode_inputs(text)
    # 分批发送，批间抖动（整批一次性发也可，但分批更像人类节奏）
    batch = []
    for inp in events:
        batch.append(inp)
        if len(batch) >= 2:  # 一个码元的 down/up 一对
            if not _send_array(batch):
                return False
            batch = []
            time.sleep(_jittered_ms(KEY_DELAY_MS))
    if batch and not _send_array(batch):
        return False
    time.sleep(_jittered_ms(POST_TYPE_DELAY_MS))
    return _press_enter()


# ---- 通道 B：剪贴板整条（默认关）----

def _snapshot_clipboard():
    """保存剪贴板全部格式 [(fmt, bytes)]。失败返回 None。"""
    items = []
    if not _U32.OpenClipboard(None):
        return None
    try:
        fmt = 0
        while True:
            fmt = _U32.EnumClipboardFormats(fmt)
            if fmt == 0:
                break
            h = _U32.GetClipboardData(fmt)
            if not h:
                continue
            size = _K32.GlobalSize(h)
            ptr = _K32.GlobalLock(h)
            if not ptr or size == 0:
                continue
            try:
                items.append((fmt, ctypes.string_at(ptr, size)))
            finally:
                _K32.GlobalUnlock(h)
    finally:
        _U32.CloseClipboard()
    return items


def _write_clipboard_text(text: str) -> bool:
    data = (text + "\0").encode("utf-16-le")
    h = _K32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    if not h:
        return False
    ptr = _K32.GlobalLock(h)
    if not ptr:
        _K32.GlobalFree(h)
        return False
    ctypes.memmove(ptr, data, len(data))
    _K32.GlobalUnlock(h)
    if not _U32.OpenClipboard(None):
        _K32.GlobalFree(h)
        return False
    try:
        _U32.EmptyClipboard()
        if not _U32.SetClipboardData(CF_UNICODETEXT, h):
            _K32.GlobalFree(h)
            return False
        h = None  # 所有权已移交系统
        return True
    finally:
        _U32.CloseClipboard()
        if h:
            _K32.GlobalFree(h)


def _read_clipboard_text() -> str:
    if not _U32.OpenClipboard(None):
        return ""
    try:
        h = _U32.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return ""
        ptr = _K32.GlobalLock(h)
        if not ptr:
            return ""
        try:
            return ctypes.wstring_at(ptr)
        finally:
            _K32.GlobalUnlock(h)
    finally:
        _U32.CloseClipboard()


def _restore_clipboard(snapshot, expect_seq: int):
    """延迟还原；期间用户自己复制了新内容（序列号变化）→ 放弃还原。"""
    time.sleep(CLIPBOARD_RESTORE_DELAY_MS / 1000)
    if _U32.GetClipboardSequenceNumber() != expect_seq:
        logger.info("clipboard changed by user, skip restore", TAG)
        return
    if not _U32.OpenClipboard(None):
        return
    try:
        _U32.EmptyClipboard()
        for fmt, data in snapshot:
            h = _K32.GlobalAlloc(GMEM_MOVEABLE, len(data))
            if not h:
                continue
            ptr = _K32.GlobalLock(h)
            if ptr:
                ctypes.memmove(ptr, data, len(data))
                _K32.GlobalUnlock(h)
                if _U32.SetClipboardData(fmt, h):
                    continue
            _K32.GlobalFree(h)
    finally:
        _U32.CloseClipboard()
    logger.debug("clipboard restored", TAG)


def _send_ctrl_v() -> bool:
    def _make_key(vk, flags):
        scan = _U32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC)
        inp = INPUT()
        inp.type = INPUT_KEYBOARD
        inp.u.ki = KEYBDINPUT(vk, scan, flags, 0, None)
        return inp

    # Ctrl Down
    if not _send_array([_make_key(VK_CONTROL, 0)]):
        return False
    time.sleep((15 + random.uniform(5, 10)) / 1000)
    # V Down
    if not _send_array([_make_key(VK_V, 0)]):
        _send_array([_make_key(VK_CONTROL, KEYEVENTF_KEYUP)])
        return False
    time.sleep((20 + random.uniform(5, 10)) / 1000)
    # V Up
    _send_array([_make_key(VK_V, KEYEVENTF_KEYUP)])
    time.sleep((15 + random.uniform(5, 10)) / 1000)
    # Ctrl Up
    return _send_array([_make_key(VK_CONTROL, KEYEVENTF_KEYUP)])


def _send_via_clipboard(text: str) -> bool:
    """通道 B：先写剪贴板 → 开框 → Ctrl+V → Enter → 延迟还原（默认关闭的路径）。"""
    snapshot = _snapshot_clipboard()
    if snapshot is None:
        logger.warning("clipboard snapshot failed", TAG)
        return False
    base_seq = _U32.GetClipboardSequenceNumber()
    if not _write_clipboard_text(text):
        return False
    # 粘贴前校验：被第三方剪贴板管家改写则放弃发送
    if _read_clipboard_text() != text:
        logger.warning("clipboard verify failed (hijacked?), abort send", TAG)
        return False
    if not _press_enter():  # 开框
        return False
    time.sleep(CHATBOX_READY_DELAY_MS / 1000)
    if not _send_ctrl_v():
        return False
    time.sleep(PASTE_SETTLE_DELAY_MS / 1000)
    if not _press_enter():  # 发送
        return False
    threading.Thread(
        target=_restore_clipboard, args=(snapshot, base_seq + 1), daemon=True,
    ).start()
    return True


# ---- 对外入口 ----

def send_text(text: str, use_clipboard: bool = False) -> bool:
    """把一行文本送进游戏聊天框并发出。返回是否完成（以 Windows 接受事件为准）。

    ⚠️ 调用方必须已完成阶段闸与前台校验；本函数在调用线程内阻塞 ~1s，
    应经 run_in_executor offload。
    """
    if _U32 is None:
        logger.error("send_text: Win32 unavailable", TAG)
        return False
    if not text:
        return False
    try:
        if use_clipboard:
            return _send_via_clipboard(text)
        return _send_keys(text)
    except Exception as e:
        logger.exception(f"send_text failed: {e}", e, TAG)
        return False
