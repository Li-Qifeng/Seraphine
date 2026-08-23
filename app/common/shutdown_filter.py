# coding:utf-8
import ctypes
import struct

from PyQt5.QtCore import QAbstractNativeEventFilter

from app.common.logger import logger

# Windows 关机 / 注销 / 强制关闭相关消息
WM_QUERYENDSESSION = 0x0011
WM_ENDSESSION = 0x0016
TAG = "Main"

# x64 下 HWND 是 8 字节, x86 下 4 字节; MSG.message 字段紧跟在 hwnd 之后
_PTR_SIZE = ctypes.sizeof(ctypes.c_void_p)


def _read_msg_id(message) -> int:
    # message 在运行时是 sip.voidptr (有 asstring); 测试中传 ctypes 指针,
    # 走 string_at。都不依赖 int(pointer), 规避各环境 int 语义差异。
    try:
        raw = message.asstring(_PTR_SIZE + 4)
    except AttributeError:
        raw = ctypes.string_at(message, _PTR_SIZE + 4)
    return struct.unpack_from("<I", raw, _PTR_SIZE)[0]


class ShutdownFilter(QAbstractNativeEventFilter):
    """
    全局原生事件过滤器: 捕获并吞掉 Windows 关机/注销消息。

    必须吞掉消息 (返回 True, 1) 而不能放行:
    Qt 会把 WM_QUERYENDSESSION 翻译成顶层窗口的 QCloseEvent, 而
    MainWindow.closeEvent 被 qasync @asyncClose 包装且在托盘模式下
    ignore 事件, Qt 随即对系统回复 FALSE -> "应用阻止关机"。
    opgg/hextech/deathCountdown 等子窗口的 closeEvent 也是无条件
    ignore+hide。此处直接答复 TRUE(允许结束会话) 并退出应用,
    所有窗口都不会再收到关机消息。
    """

    def __init__(self, app):
        super().__init__()
        self._app = app

    def nativeEventFilter(self, eventType, message):
        if eventType == b"windows_generic_MSG":
            try:
                msg_id = _read_msg_id(message)
                if msg_id in (WM_QUERYENDSESSION, WM_ENDSESSION):
                    logger.critical(
                        "received Windows shutdown/end-session signal, "
                        "quitting application", TAG)
                    # 立即退出, 不走异步 closeEvent 流程, 以免阻塞关机
                    self._app.quit()
                    return True, 1
            except Exception as e:
                logger.exception("shutdown filter error", e, TAG)

        return False, 0
