from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import QWidget


class SignalBus(QObject):
    # listener:
    tasklistNotFound = pyqtSignal()

    lolClientStarted = pyqtSignal(int)
    lolClientEnded = pyqtSignal()
    lolClientChanged = pyqtSignal(int)

    terminateListeners = pyqtSignal()

    # connector:
    lcuApiExceptionRaised = pyqtSignal(str, object)
    # LCU 未就绪 (lcuSess is None) 时仍有请求发送, 由 @retry 统一拦截后发射,
    # UI 层接收并显示"客户端未连接"提示, 不再抛 ReferenceError 给上层
    lcuNotConnected = pyqtSignal()
    currentSummonerProfileChanged = pyqtSignal(dict)
    gameStatusChanged = pyqtSignal(str)
    champSelectChanged = pyqtSignal(dict)
    getCmdlineError = pyqtSignal()

    # career_interface
    careerGameBarClicked = pyqtSignal(str)

    # search_interface:
    gameTabClicked = pyqtSignal(QWidget)

    # jumps:
    toCareerInterface = pyqtSignal(str)
    toSearchInterface = pyqtSignal(str)

    # style:
    customColorChanged = pyqtSignal(str)

    # OPGG:
    toOpggBuildInterface = pyqtSignal(int, str, str)

    # hextech/aram 抢英雄 (备选席模式):
    hextechGrabbed = pyqtSignal(int)          # 抢到目标英雄 (championId)
    hextechSessionUpdated = pyqtSignal(dict)  # 会话刷新 (供窗口更新头像墙)

    # Live Client API (游戏中实时数据):
    liveGameDataUpdated = pyqtSignal(dict)    # allgamedata 实时数据更新


signalBus = SignalBus()
