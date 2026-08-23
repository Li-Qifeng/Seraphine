# coding:utf-8
import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt, QTranslator, QTimer
from app.common.qfluentwidgets import FluentTranslator
from qasync import QApplication, QEventLoop
import asyncio
import signal
import sys
from app.common.config import cfg, VERSION, BETA
from app.common.logger import logger
from app.common.shutdown_filter import ShutdownFilter
from app.view.main_window import MainWindow

TAG = "Main"


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

    # 安装 Windows 关机消息过滤器: 吞掉关机消息并答复允许,
    # 避免 Qt closeEvent(托盘模式 ignore) 回 FALSE 阻塞关机
    app.installNativeEventFilter(ShutdownFilter(app))

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
    app.aboutToQuit.connect(w.processListener.terminate)
    w.show()

    eventLoop.run_until_complete(appCloseEvent.wait())
    eventLoop.close()


if __name__ == '__main__':
    main()
