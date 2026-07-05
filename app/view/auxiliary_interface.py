import asyncio
from app.common.config import cfg
from app.common.icons import Icon
from app.common.qfluentwidgets import (SettingCardGroup, SwitchSettingCard,
                                        ComboBoxSettingCard)
from app.common.style_sheet import StyleSheet
from app.components.seraphine_interface import SeraphineInterface
from app.components.setting_cards import QueueFilterCard
from app.view.auxiliary_cards import (
    OnlineStatusCard,
    ProfileBackgroundCard,
    ProfileTierCard,
    OnlineAvailabilityCard,
    RemoveTokensCard,
    RemovePrestigeCrestCard,
    FixClientDpiCard,
    RestartClientCard,
    LeaveQueueCard,
    CreatePracticeLobbyCard,
    SpectateCard,
    LockConfigCard,
     AutoAcceptMatchingCard,
     AutoAcceptMsCard,
    AutoHonorCard,
    AutoAcceptSwapingCard,
    AutoSelectChampionCard,
    AutoBanChampionCard,
    AutoSetSummonerSpellCard,
    HextechChampionCard,
    DeathSwitchCard,
)


class AuxiliaryInterface(SeraphineInterface):

    def __init__(self, parent=None):
        super().__init__(parent)

        self._initCommon(self.tr("Auxiliary Functions"),
                         StyleSheet.AUXILIARY_INTERFACE)

        self.profileGroup = SettingCardGroup(self.tr("个人主页"),
                                             self.scrollWidget)
        self.automationGroup = SettingCardGroup(
            self.tr("自动化"), self.scrollWidget)
        self.hextechGroup = SettingCardGroup(
            self.tr("大乱斗"), self.scrollWidget)
        self.toolsGroup = SettingCardGroup(
            self.tr("工具"), self.scrollWidget)

        self.gameInfoGroup = SettingCardGroup(
            self.tr("游戏信息"), self.scrollWidget)
        self.teamRatingGroup = SettingCardGroup(
            self.tr("全队评级"), self.scrollWidget)
        self.opggGroup = SettingCardGroup(
            self.tr("OPGG 助手"), self.scrollWidget)

        self.onlineStatusCard = OnlineStatusCard(
            title=self.tr("在线状态"),
            content=self.tr("设置个人主页在线状态"),
            parent=self.profileGroup)
        self.profileBackgroundCard = ProfileBackgroundCard(
            self.tr("个人主页背景"),
            self.tr("设置个人主页背景皮肤"), self.profileGroup)
        self.profileTierCard = ProfileTierCard(
            self.tr("个人主页段位"),
            self.tr("设置个人主页卡片显示的段位"),
            self.profileGroup)
        self.onlineAvailabilityCard = OnlineAvailabilityCard(
            self.tr("在线可用状态"),
            self.tr("设置在线可用状态"), self.profileGroup)
        self.removeTokensCard = RemoveTokensCard(
            self.tr("移除挑战代币"),
            self.tr("从个人主页移除所有挑战代币"),
            self.profileGroup)
        self.removePrestigeCrestCard = RemovePrestigeCrestCard(
            self.tr("移除荣誉徽章"),
            self.tr(
                "从个人主页图标移除荣誉徽章 (需要召唤师等级 >= 525)"),
            self.profileGroup)
        self.lockConfigCard = LockConfigCard(
            self.tr("锁定配置"),
            self.tr("锁定游戏配置文件不可更改"),
            self.toolsGroup)

        self.fixDpiCard = FixClientDpiCard(
            self.tr("修复客户端窗口"),
            self.tr(
                "修复 DirectX 9 导致的客户端窗口大小异常 (需要 UAC)"),
            self.toolsGroup
        )
        self.restartClientCard = RestartClientCard(
            self.tr("重启客户端"),
            self.tr("重启英雄联盟客户端而不退出队列"),
            self.toolsGroup
        )
        self.leaveQueueCard = LeaveQueueCard(
            self.tr("秒退"),
            self.tr("离开队列或退出英雄选择"),
            self.toolsGroup
        )

        self.createPracticeLobbyCard = CreatePracticeLobbyCard(
            self.tr("创建 5v5 训练模式"),
            self.tr("仅可添加机器人到房间"),
            self.toolsGroup)
        # 自动接受对局
        self.autoReconnectCard = SwitchSettingCard(
            Icon.CONNECTION,
            self.tr("自动重连"),
            self.tr("断线时自动重新连接"),
            cfg.enableAutoReconnect, self.automationGroup)
        self.autoHonorCard = AutoHonorCard(
            self.tr("自动点赞"),
            self.tr(
                "游戏结束自动点赞一位队友。"
                "好友优先/仅好友策略需要队友在好友列表中。"),
            cfg.enableAutoHonor, cfg.autoHonorDelay, cfg.autoHonorStrategy,
            self.automationGroup)
        self.spectateCard = SpectateCard(
            self.tr("观战"),
            self.tr("观战同一局域网的召唤师实时对局"),
            self.toolsGroup
        )

        self.autoAcceptMatchingCard = AutoAcceptMsCard(
            self.tr("自动接受对局"),
            self.tr("随机延迟后自动接受对局匹配"),
            cfg.enableAutoAcceptMatching,
            cfg.autoAcceptDelayMs,
            cfg.autoAcceptDeclineEnabled,
            self.automationGroup)
        self.autoStartMatchmakingCard = AutoAcceptMatchingCard(
            self.tr("自动开始匹配"),
            self.tr(
                "在大厅时自动开始搜索对局"),
            cfg.enableAutoStartMatchmaking, cfg.autoStartMatchmakingDelay,
            self.automationGroup, delayRange=(0, 30),
            delayLabelText=self.tr("进入大厅后延迟秒数:"))
        self.autoPlayAgainCard = SwitchSettingCard(
            Icon.ARROWREPEAT,
            self.tr("自动再来一局"),
            self.tr(
                "游戏结束时自动点击\"再来一局\""),
            cfg.enableAutoPlayAgain, self.automationGroup)
        self.autoAcceptSwapingCard = AutoAcceptSwapingCard(
            self.tr("自动同意换人/换英雄"),
            self.tr(
                "自动接受禁用/选人阶段的换人和换英雄请求"),
            cfg.autoAcceptCeilSwap, cfg.autoAcceptChampTrade,
            self.automationGroup)
        self.autoSelectChampionCard = AutoSelectChampionCard(
            self.tr("自动选择英雄"),
            self.tr("轮到选人时自动选择预设英雄"),
            cfg.enableAutoSelectChampion,
            cfg.autoSelectChampion,
            cfg.autoSelectChampionTop,
            cfg.autoSelectChampionJug,
            cfg.autoSelectChampionMid,
            cfg.autoSelectChampionBot,
            cfg.autoSelectChampionSup,
            cfg.enableAutoSelectTimeoutCompleted,
            self.automationGroup)
        self.autoBanChampionsCard = AutoBanChampionCard(
            self.tr("自动禁用英雄"),
            self.tr("轮到禁用时自动禁用预设英雄"),
            cfg.enableAutoBanChampion,
            cfg.autoBanChampion,
            cfg.autoBanChampionTop,
            cfg.autoBanChampionJug,
            cfg.autoBanChampionMid,
            cfg.autoBanChampionBot,
            cfg.autoBanChampionSup,
            cfg.pretentBan,
            cfg.autoBanDelay,
            self.automationGroup)
        self.autoSetSpellCard = AutoSetSummonerSpellCard(
            self.tr("自动设置召唤师技能"),
            self.tr("选人开始时自动设置召唤师技能"),
            cfg.enableAutoSetSpells,
            cfg.autoSetSummonerSpell,
            cfg.autoSetSummonerSpellTop,
            cfg.autoSetSummonerSpellJug,
            cfg.autoSetSummonerSpellMid,
            cfg.autoSetSummonerSpellBot,
            cfg.autoSetSummonerSpellSup,
            self.automationGroup
        )
        self.deathSwitchCard = DeathSwitchCard(
            self.tr("死亡自动切窗"),
            self.tr("死亡时自动切换到指定窗口/应用, 复活后自动切回游戏窗口"),
            cfg.enableDeathSwitch,
            cfg.deathSwitchTargetExe,
            self.automationGroup)

        self.hextechChampionCard = HextechChampionCard(
            self.tr("自动换英雄"),
            self.tr("在大乱斗中自动从备选席换英雄（无CD强刷）"),
            cfg.enableAutoAramBench,
            cfg.hextechChampions,
            self.hextechGroup)

        self.hextechAssistCard = SwitchSettingCard(
            Icon.GAME,
            self.tr("海克斯强化辅助"),
            self.tr("在 ARAM Mayhem 游戏中, 根据已选强化推荐后续选择 (仅 queueId 2400)"),
            cfg.enableHextechAssist,
            self.hextechGroup)
        self.hextechAssistAutoShowCard = SwitchSettingCard(
            Icon.EYES,
            self.tr("自动显示辅助页"),
            self.tr("游戏开始时自动切换到 OPGG 海克斯辅助页"),
            cfg.hextechAssistAutoShow,
            self.hextechGroup)

        # --- 游戏信息组 ---
        self.queueFilterCard = QueueFilterCard(
            self.tr("Game Infomation filter"),
            self.tr(
                "Show game modes in Game Infomation interface based on your current game mode"),
            cfg.queueFilter,
            parent=self.gameInfoGroup)

        self.autoClearGameinfoCard = SwitchSettingCard(
            Icon.ATTACHTEXT, self.tr("Reserve Game Information interface"),
            self.tr(
                "Reserve Game Information interface until the next champion selection starts"),
            cfg.enableReserveGameinfo,
            parent=self.gameInfoGroup)

        self.gameInfoShowTierCard = SwitchSettingCard(
            Icon.TROPHY, self.tr("Show tier in game information"),
            self.tr(
                "Show tier icon in game information interface. Enabling this option affects APP's performance"),
            cfg.showTierInGameInfo,
            parent=self.gameInfoGroup)

        # --- 全队评级组 ---
        self.enableTeamRatingCard = SwitchSettingCard(
            Icon.TROPHY, self.tr("Team rating badges"),
            self.tr(
                "Show a 5-tier rating badge (e.g. 神/爹/小有亮点/躺赢狗/消失) "
                "for each teammate in game detail view"),
            cfg.enableTeamRating,
            parent=self.teamRatingGroup)

        self.teamRatingStyleCard = ComboBoxSettingCard(
            cfg.teamRatingStyle,
            Icon.SCALEFIT,
            self.tr("Team rating style"),
            self.tr(
                "Tieba: 贴吧风 (win/loss separate labels); "
                "Horse: 马系风 (上等马/中等马/下等马/纯牛马)"),
            texts=[self.tr("Tieba"), self.tr("Horse")],
            parent=self.teamRatingGroup)

        # --- OPGG 助手组 ---
        self.autoShowOpggCard = SwitchSettingCard(
            Icon.WINDOW, self.tr("Show OP.GG window automatically"),
            self.tr("Show OP.GG window automatically when champion selection starts"),
            cfg.autoShowOpgg,
            parent=self.opggGroup)

        self.opggOnTopCard = SwitchSettingCard(
            Icon.PADDINGTOP, self.tr("Show OP.GG window on top"),
            self.tr(
                "Show OP.GG window in front of other windows while selecting champions"),
            cfg.enableOpggOnTop,
            parent=self.opggGroup)

        self.__initLayout()

    def setEnabled(self, enabled: bool) -> None:
        """重写 setEnabled: 仅禁用真正需要 LCU 的执行类卡片.

        配置开关类卡片 (auto-*/hextech*) 只是写 cfg, 应随时可改;
        LockConfigCard 只做文件系统操作, 不依赖 LCU.
        需要禁用的是实际调用 connector 的执行类卡片 (profile/spectate/practice/fixDpi/restart).
        """
        # 需要禁用的执行类卡片 (依赖 LCU connector)
        lcu_cards = [
            self.onlineStatusCard, self.profileBackgroundCard,
            self.profileTierCard, self.onlineAvailabilityCard,
            self.removeTokensCard, self.removePrestigeCrestCard,
            self.spectateCard, self.createPracticeLobbyCard,
            self.fixDpiCard, self.restartClientCard,
        ]
        for card in lcu_cards:
            try:
                card.setEnabled(enabled)
            except (AttributeError, RuntimeError):
                pass
        # 配置开关类 (auto-*/hextech*) 和 lockConfigCard 不随 LCU 状态禁用
        # 让父类 QScrollArea 的滚动行为保持可用, 但不调用 super().setEnabled
        # (super 会把所有子控件都禁用, 连累配置开关)

    def __initLayout(self):
        # 自动化
        self.automationGroup.addSettingCard(self.autoAcceptMatchingCard)
        self.automationGroup.addSettingCard(self.autoStartMatchmakingCard)
        self.automationGroup.addSettingCard(self.autoPlayAgainCard)
        self.automationGroup.addSettingCard(self.autoAcceptSwapingCard)
        self.automationGroup.addSettingCard(self.autoSelectChampionCard)
        self.automationGroup.addSettingCard(self.autoBanChampionsCard)
        self.automationGroup.addSettingCard(self.autoSetSpellCard)
        self.automationGroup.addSettingCard(self.autoReconnectCard)
        self.automationGroup.addSettingCard(self.autoHonorCard)
        self.automationGroup.addSettingCard(self.deathSwitchCard)

        # 海克斯
        self.hextechGroup.addSettingCard(self.hextechChampionCard)
        self.hextechGroup.addSettingCard(self.hextechAssistCard)
        self.hextechGroup.addSettingCard(self.hextechAssistAutoShowCard)

        # 个人主页
        self.profileGroup.addSettingCard(self.onlineStatusCard)
        self.profileGroup.addSettingCard(self.profileBackgroundCard)
        self.profileGroup.addSettingCard(self.profileTierCard)
        self.profileGroup.addSettingCard(self.onlineAvailabilityCard)
        self.profileGroup.addSettingCard(self.removeTokensCard)
        self.profileGroup.addSettingCard(self.removePrestigeCrestCard)

        # 工具
        self.toolsGroup.addSettingCard(self.createPracticeLobbyCard)
        self.toolsGroup.addSettingCard(self.spectateCard)
        self.toolsGroup.addSettingCard(self.lockConfigCard)
        self.toolsGroup.addSettingCard(self.fixDpiCard)
        self.toolsGroup.addSettingCard(self.restartClientCard)
        self.toolsGroup.addSettingCard(self.leaveQueueCard)

        # 游戏信息
        self.gameInfoGroup.addSettingCard(self.queueFilterCard)
        self.gameInfoGroup.addSettingCard(self.autoClearGameinfoCard)
        self.gameInfoGroup.addSettingCard(self.gameInfoShowTierCard)

        # 全队评级
        self.teamRatingGroup.addSettingCard(self.enableTeamRatingCard)
        self.teamRatingGroup.addSettingCard(self.teamRatingStyleCard)

        # OPGG 助手
        self.opggGroup.addSettingCard(self.autoShowOpggCard)
        self.opggGroup.addSettingCard(self.opggOnTopCard)

        self.expandLayout.setSpacing(30)
        self.expandLayout.setContentsMargins(36, 0, 36, 0)
        self.expandLayout.addWidget(self.gameInfoGroup)
        self.expandLayout.addWidget(self.teamRatingGroup)
        self.expandLayout.addWidget(self.opggGroup)
        self.expandLayout.addWidget(self.automationGroup)
        self.expandLayout.addWidget(self.hextechGroup)
        self.expandLayout.addWidget(self.profileGroup)
        self.expandLayout.addWidget(self.toolsGroup)

    async def initChampionList(self):
        async def initChampions():
            champions = await self.autoSelectChampionCard.initChampionList()
            await self.autoBanChampionsCard.initChampionList(champions)
            await self.hextechChampionCard.initChampionList(champions)
            await self.profileBackgroundCard.initChampionList(champions)

        async def initSummonerSpell():
            await self.autoSetSpellCard.initSummonerSpells()

        await asyncio.gather(initChampions(), initSummonerSpell())
