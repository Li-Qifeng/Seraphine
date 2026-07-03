
from PyQt5.QtCore import QThread

from app.common.logger import logger
from app.common.signals import signalBus
from app.common.util import getLolClientPids, isLolGameProcessExist, getTasklistPath

TAG = "Listener"


class LolProcessExistenceListener(QThread):
    def __init__(self, parent):
        # 当前 Seraphine 连接的客户端 pid
        self.runningPid = 0

        super().__init__(parent)

    def run(self):
        path = getTasklistPath()

        if not path:
            signalBus.tasklistNotFound.emit()
            return

        while True:
            try:
                # 取一下当前运行中的所有客户端 pid
                pids = getLolClientPids(path)
            except Exception as e:
                # tasklist / psutil 偶发异常 (issue #367), 记录后跳过本轮,
                # 不要让监听线程整个崩溃退出
                logger.exception(
                    'getLolClientPids failed in this loop', e, TAG)
                pids = []

            # 如果有客户端正在运行
            if len(pids) != 0:

                # 如果当前没有连接客户端，则是第一个客户端启动了
                if self.runningPid == 0:
                    self.runningPid = pids[0]
                    signalBus.lolClientStarted.emit(self.runningPid)

                # 如果当前有客户端启动中，但是当前连接的客户端不在这些客户端里
                # 则说明是原来多开了客户端，现在原本连接的客户端关了，则切换到新的客户端
                elif self.runningPid not in pids:
                    self.runningPid = pids[0]
                    signalBus.lolClientChanged.emit(self.runningPid)

            # 如果没有任何客户端在运行，且上一次检查时有客户端在运行
            else:
                try:
                    gameExist = isLolGameProcessExist(path)
                except Exception as e:
                    logger.exception(
                        'isLolGameProcessExist failed in this loop', e, TAG)
                    gameExist = False

                if self.runningPid and not gameExist:
                    self.runningPid = 0
                    signalBus.lolClientEnded.emit()

            self.msleep(1500)


class StoppableThread(QThread):
    def __init__(self, target, parent) -> None:
        self.target = target
        super().__init__(parent)

    def run(self):
        try:
            self.target()
        except Exception as e:
            logger.exception(f"StoppableThread target failed: {e}", TAG)
