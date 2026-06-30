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
    CreatePracticeLobbyCard,
    SpectateCard,
    LockConfigCard,
    AutoAcceptMatchingCard,
    AutoHonorCard,
    AutoAcceptSwapingCard,
    AutoSelectChampionCard,
    AutoBanChampionCard,
    AutoSetSummonerSpellCard,
    HextechChampionCard,
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
            self.tr("海克斯"), self.scrollWidget)
        self.toolsGroup = SettingCardGroup(
            self.tr("工具"), self.scrollWidget)

        self.gameInfoGroup = SettingCardGroup(
            self.tr("游戏信息"), self.scrollWidget)
        self.teamRatingGroup = SettingCardGroup(
            self.tr("全队评级"), self.scrollWidget)
        self.opggGroup = SettingCardGroup(
            self.tr("OPGG 助手"), self.scrollWidget)

        self.onlineStatusCard = OnlineStatusCard(
            title=self.tr("Online status"),
            content=self.tr("Set your profile online status"),
            parent=self.profileGroup)
        self.profileBackgroundCard = ProfileBackgroundCard(
            self.tr("Profile background"),
            self.tr("Set your profile background skin"), self.profileGroup)
        self.profileTierCard = ProfileTierCard(
            self.tr("Profile tier"),
            self.tr("Set your tier showed in your profile card"),
            self.profileGroup)
        self.onlineAvailabilityCard = OnlineAvailabilityCard(
            self.tr("Online Availability"),
            self.tr("Set your online Availability"), self.profileGroup)
        self.removeTokensCard = RemoveTokensCard(
            self.tr("Remove challenge tokens"),
            self.tr("Remove all challenge tokens from your profile"),
            self.profileGroup)
        self.removePrestigeCrestCard = RemovePrestigeCrestCard(
            self.tr("Remove prestige crest"),
            self.tr(
                "Remove prestige crest from your profile icon (need your summoner level >= 525)"),
            self.profileGroup)
        self.lockConfigCard = LockConfigCard(
            self.tr("Lock config"),
            self.tr("Make your game config unchangeable"),
            self.toolsGroup)

        self.fixDpiCard = FixClientDpiCard(
            self.tr("Fix client window"),
            self.tr(
                "Fix incorrect client window size caused by DirectX 9 (need UAC)"),
            self.toolsGroup
        )
        self.restartClientCard = RestartClientCard(
            self.tr("Restart client"),
            self.tr("Restart the LOL client without re queuing"),
            self.toolsGroup
        )

        self.createPracticeLobbyCard = CreatePracticeLobbyCard(
            self.tr("Create 5v5 practice lobby"),
            self.tr("Only bots can be added to the lobby"),
            self.toolsGroup)
        # 自动接受对局
        self.autoReconnectCard = SwitchSettingCard(
            Icon.CONNECTION,
            self.tr("Auto reconnect"),
            self.tr("Automatically reconnect when disconnected"),
            cfg.enableAutoReconnect, self.automationGroup)
        self.autoHonorCard = AutoHonorCard(
            self.tr("自动点赞"),
            self.tr(
                "游戏结束自动点赞一位队友。"
                "好友优先/仅好友策略需要队友在好友列表中。"),
            cfg.enableAutoHonor, cfg.autoHonorDelay, cfg.autoHonorStrategy,
            self.automationGroup)
        self.spectateCard = SpectateCard(
            self.tr("Spectate"),
            self.tr("Spectate live game of summoner in the same environment"),
            self.toolsGroup
        )

        self.autoAcceptMatchingCard = AutoAcceptMatchingCard(
            self.tr("Auto accept"),
            self.tr(
                "Accept match making automatically after the number of seconds you set"),
            cfg.enableAutoAcceptMatching, cfg.autoAcceptMatchingDelay,
            self.automationGroup)
        self.autoStartMatchmakingCard = AutoAcceptMatchingCard(
            self.tr("Auto start matchmaking"),
            self.tr(
                "Start searching for match automatically when in lobby"),
            cfg.enableAutoStartMatchmaking, cfg.autoStartMatchmakingDelay,
            self.automationGroup, delayRange=(0, 30),
            delayLabelText=self.tr("Delay seconds after entering lobby:"))
        self.autoPlayAgainCard = SwitchSettingCard(
            Icon.ARROWREPEAT,
            self.tr("自动再来一局"),
            self.tr(
                "游戏结束时自动点击\"再来一局\""),
            cfg.enableAutoPlayAgain, self.automationGroup)
        self.autoAcceptSwapingCard = AutoAcceptSwapingCard(
            self.tr("Auto accept swaping"),
            self.tr(
                "Accept ceil or champion swaping requests during B/P"),
            cfg.autoAcceptCeilSwap, cfg.autoAcceptChampTrade,
            self.automationGroup)
        self.autoSelectChampionCard = AutoSelectChampionCard(
            self.tr("Auto select champion"),
            self.tr("Auto select champion when your selection begins"),
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
            self.tr("Auto ban champion"),
            self.tr("Auto ban champion when your ban section begins"),
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
            self.tr("Auto set summoner spells"),
            self.tr("Auto set your summoner spells when champion selection begins"),
            cfg.enableAutoSetSpells,
            cfg.autoSetSummonerSpell,
            cfg.autoSetSummonerSpellTop,
            cfg.autoSetSummonerSpellJug,
            cfg.autoSetSummonerSpellMid,
            cfg.autoSetSummonerSpellBot,
            cfg.autoSetSummonerSpellSup,
            self.automationGroup
        )
        self.hextechChampionCard = HextechChampionCard(
            self.tr("海克斯/大乱斗抢英雄"),
            self.tr("在大乱斗/海克斯大乱斗中自动从备选席抢英雄"),
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
