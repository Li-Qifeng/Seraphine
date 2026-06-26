# coding:utf-8
import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt, QTranslator, QAbstractNativeEventFilter, QTimer
from app.common.qfluentwidgets import FluentTranslator
from qasync import QApplication, QEventLoop
import asyncio
import ctypes
import signal
import sys
from app.common.config import cfg, VERSION, BETA
from app.common.logger import logger
from app.view.main_window import MainWindow

# Windows 关机 / 注销 / 强制关闭相关消息
WM_QUERYENDSESSION = 0x0011
WM_ENDSESSION = 0x0016
TAG = "Main"

# x64 下 HWND 是 8 字节, x86 下 4 字节; MSG.message 字段紧跟在 hwnd 之后
_PTR_SIZE = ctypes.sizeof(ctypes.c_void_p)


class _ShutdownFilter(QAbstractNativeEventFilter):
    """
    全局原生事件过滤器: 捕获 Windows 关机/注销消息。

    Seraphine 主窗口 closeEvent 是异步的, 且在 "最小化到托盘" 模式下会
    ignore 掉关闭事件, 导致系统认为进程没有响应退出, 从而阻塞/延迟关机。
    这里在关机消息到来时直接让 QApplication 退出, 绕过 closeEvent。
    """

    def __init__(self, app):
        super().__init__()
        self._app = app

    def nativeEventFilter(self, eventType, message):
        if eventType == b"windows_generic_MSG":
            try:
                # message 是 MSG 指针的包装; 取地址后读出 MSG.message (UINT)
                ptr = int(message)
                msg_id = ctypes.c_uint.from_buffer_copy(
                    ctypes.string_at(ptr, _PTR_SIZE + 4), _PTR_SIZE).value
                if msg_id in (WM_QUERYENDSESSION, WM_ENDSESSION):
                    logger.critical(
                        "received Windows shutdown/end-session signal, "
                        "quitting application", TAG)
                    # 立即退出, 不走异步 closeEvent 流程, 以免阻塞关机
                    self._app.quit()
            except Exception as e:
                logger.exception("shutdown filter error", e, TAG)

        return False, 0


def main():
    args = sys.argv
    if len(args) == 2 and args[1] in ['--version', '-v']:
        print(BETA or VERSION)
        return

    if cfg.get(cfg.dpiScale) == "Auto":
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    else:
        os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
        os.environ["QT_SCALE_FACTOR"] = str(cfg.get(cfg.dpiScale))
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)

    font = QFont()
    font.setStyleStrategy(QFont.PreferAntialias)
    font.setHintingPreference(QFont.PreferFullHinting)
    QApplication.setFont(font)

    app = QApplication(sys.argv)
    app.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings)

    # 安装 Windows 关机消息过滤器, 避免关机被异步 closeEvent / 托盘最小化阻塞
    app.installNativeEventFilter(_ShutdownFilter(app))

    # 允许 Ctrl+C 退出: Windows 下 qasync 事件循环不会主动处理 SIGINT,
    # 用一个短间隔定时器让解释器有机会执行 Python 信号处理函数
    def _sigint_handler(*_):
        logger.info("SIGINT received, quitting application", TAG)
        QTimer.singleShot(0, app.quit)
    signal.signal(signal.SIGINT, _sigint_handler)

    _sigint_wakeup = QTimer()
    _sigint_wakeup.timeout.connect(lambda: None)
    _sigint_wakeup.start(200)

    eventLoop = QEventLoop(app)
    asyncio.set_event_loop(eventLoop)

    appCloseEvent = asyncio.Event()
    app.aboutToQuit.connect(appCloseEvent.set)

    locale = cfg.get(cfg.language).value
    fluentTranslator = FluentTranslator(locale)
    seraphineTranslator = QTranslator()
    seraphineTranslator.load(locale, "Seraphine", ".", "./app/resource/i18n")

    app.installTranslator(fluentTranslator)
    app.installTranslator(seraphineTranslator)

    w = MainWindow()
    w.show()

    eventLoop.run_until_complete(appCloseEvent.wait())
    eventLoop.close()


if __name__ == '__main__':
    main()
