import time
from typing import List, Optional, TypedDict

# auto honor 策略枚举字符串常量, 与 config.cfg.autoHonorStrategy 取值对齐
HONOR_STRATEGY_FRIENDS_FIRST = "friends_first"
HONOR_STRATEGY_FRIENDS_ONLY = "friends_only"
HONOR_STRATEGY_BEST_SCORE = "best_score"
HONOR_STRATEGY_RANDOM = "random"


TIER_MAP = {
    'Iron': ['坚韧黑铁', '黑铁'],
    'Bronze': ['英勇黄铜', '黄铜'],
    'Silver': ['不屈白银', '白银'],
    'Gold': ['荣耀黄金', '黄金'],
    'Platinum': ['华贵铂金', '铂金'],
    'Emerald': ['流光翡翠', '翡翠'],
    'Diamond': ['璀璨钻石', '钻石'],
    'Master': ['超凡大师', '大师'],
    'Grandmaster': ['傲世宗师', '宗师'],
    'Challenger': ['最强王者', '王者'],
}

DEFAULT_UNRANKED = "未定级"
DEFAULT_UNKNOWN = "未知"
DEFAULT_RANKED_SOLO = '单双排'
DEFAULT_RANKED_FLEX = "灵活组排"


def translateTier(orig: str, short=False, is_english=False) -> str:
    if orig == '':
        return "--"

    index = 1 if short else 0

    if is_english:
        return orig.capitalize()
    else:
        return TIER_MAP[orig.capitalize()][index]


def timeStampToStr(stamp):
    timeArray = time.localtime(stamp / 1000)
    return time.strftime("%Y/%m/%d %H:%M", timeArray)


def timeStampToShortStr(stamp):
    timeArray = time.localtime(stamp / 1000)
    return time.strftime("%m/%d", timeArray)


def secsToStr(secs):
    return time.strftime("%M:%S", time.gmtime(secs))


def separateTeams(data, currentSummonerId):
    team1 = data['teamOne']
    team2 = data['teamTwo']

    for summoner in team1:
        if summoner.get('summonerId') == currentSummonerId:
            return team1, team2

    for summoner in team2:
        if summoner.get('summonerId') == currentSummonerId:
            return team2, team1

    return None, None


def parseSummonerOrder(team):
    summoners = [{
        'summonerId': s['summonerId'],
        'cellId': s['cellId']
    } for s in team]

    summoners.sort(key=lambda x: x['cellId'])
    return [s['summonerId'] for s in summoners if s['summonerId'] != 0]


def sortedSummonersByGameRole(summoners: list):
    position = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]

    if any(x['selectedPosition'] not in position for x in summoners):
        return None

    return sorted(summoners,
                  key=lambda x: position.index(x['selectedPosition']))


def parseGames(games, targetId=0):
    kills, deaths, assists, wins, losses = 0, 0, 0, 0, 0
    hitGames = []

    for game in games:
        if not targetId or game['queueId'] == targetId:
            hitGames.append(game)

            if not game['remake']:
                kills += game['kills']
                deaths += game['deaths']
                assists += game['assists']

                if game['win']:
                    wins += 1
                else:
                    losses += 1

    return hitGames, kills, deaths, assists, wins, losses


def _extractHonorCandidates(eogStats: Optional[dict]) -> list:
    """从 ballot 提取 honor 候选列表.

    /lol-honor-v2/v1/ballot GET 返回:
    {gameId, eligibleAllies: [...], eligibleOpponents: [...], ...}.
    eligibleAllies[] 元素含 puuid/summonerId/summonerName/championId 等.
    默认只返回 allies (点赞通常只给队友).
    """
    if not isinstance(eogStats, dict):
        return []

    allies = eogStats.get('eligibleAllies')
    if isinstance(allies, list):
        return allies
    return []


def _candidateField(c: dict, *keys, default=None):
    """从候选 dict 中按优先级取第一个非空字段 (兼容多种 schema)."""
    for k in keys:
        v = c.get(k)
        if v is not None and v != "":
            return v
    return default


def pickHonorTarget(eogStats: Optional[dict],
                    friendsPuuids: set,
                    strategy: str = HONOR_STRATEGY_FRIENDS_FIRST,
                    currentPuuid: Optional[str] = None) -> Optional[dict]:
    """从本局 EOG 数据选择 auto honor 目标.

    Args:
        eogStats: connector.getEogStats() 返回值
        friendsPuuids: 好友 puuid 集合, 用于 friends_first/friends_only 策略
        strategy: HONOR_STRATEGY_* 之一
        currentPuuid: 当前召唤师 puuid, 用于排除自己 (不可给自己点赞)

    Returns:
        选中的候选 dict 或 None (无可用候选).
    """
    candidates = _extractHonorCandidates(eogStats)
    if not candidates:
        return None

    # 归一化候选项: 统一字段名 (puuid/summonerId/score)
    normalized = []
    for c in candidates:
        if not isinstance(c, dict):
            continue
        puuid = _candidateField(c, 'puuid', 'playerUuid', 'summonerPuuid')
        if currentPuuid and puuid == currentPuuid:
            continue  # 不能给自己点赞
        if puuid is None and 'summonerId' not in c:
            continue
        score = _candidateField(c, 'score', 'honorScore', 'voteCount', default=0)
        try:
            score = float(score or 0)
        except (TypeError, ValueError):
            score = 0.0
        normalized.append({
            'puuid': puuid,
            'summonerId': _candidateField(c, 'summonerId', 'summonerID'),
            'summonerName': _candidateField(c, 'summonerName', 'name', 'gameName'),
            'score': score,
        })

    if not normalized:
        return None

    friend_pool = [c for c in normalized
                   if c['puuid'] and c['puuid'] in friendsPuuids]

    if strategy == HONOR_STRATEGY_FRIENDS_ONLY:
        pool = friend_pool
        if not pool:
            return None
    elif strategy == HONOR_STRATEGY_FRIENDS_FIRST:
        pool = friend_pool if friend_pool else normalized
    elif strategy == HONOR_STRATEGY_BEST_SCORE:
        pool = normalized
    elif strategy == HONOR_STRATEGY_RANDOM:
        import random
        return random.choice(normalized)
    else:
        pool = normalized  # 未知策略退回 best_score 行为

    return max(pool, key=lambda c: c['score'])


def parseRankInfo(info, unranked_text=None, unknown_text=None, is_english=False):
    unranked_text = unranked_text or DEFAULT_UNRANKED
    unknown_text = unknown_text or DEFAULT_UNKNOWN

    soloIcon = flexIcon = "app/resource/images/UNRANKED.svg"
    soloTier = flexTier = unknown_text
    soloDivision = flexDivision = ""
    soloRankInfo = flexRankInfo = {"leaguePoints": ""}

    if info:
        soloRankInfo = info["queueMap"]["RANKED_SOLO_5x5"]
        flexRankInfo = info["queueMap"]["RANKED_FLEX_SR"]

        soloTier = soloRankInfo["tier"]
        soloDivision = soloRankInfo["division"]

        if soloTier == "":
            soloIcon = "app/resource/images/UNRANKED.svg"
            soloTier = unranked_text
        else:
            soloIcon = f"app/resource/images/{soloTier}.svg"
            soloTier = translateTier(soloTier, True, is_english)
        if soloDivision == "NA":
            soloDivision = ""

        flexTier = flexRankInfo["tier"]
        flexDivision = flexRankInfo["division"]

        if flexTier == "":
            flexIcon = "app/resource/images/UNRANKED.svg"
            flexTier = unranked_text
        else:
            flexIcon = f"app/resource/images/{flexTier}.svg"
            flexTier = translateTier(flexTier, True, is_english)
        if flexDivision == "NA":
            flexDivision = ""

    return {
        "solo": {
            "tier": soloTier,
            "icon": soloIcon,
            "division": soloDivision,
            "lp": soloRankInfo["leaguePoints"],
        },
        "flex": {
            "tier": flexTier,
            "icon": flexIcon,
            "division": flexDivision,
            "lp": flexRankInfo["leaguePoints"],
        },
    }


def parseDetailRankInfo(rankInfo, ranked_solo_text=None, ranked_flex_text=None, is_english=False):
    ranked_solo_text = ranked_solo_text or DEFAULT_RANKED_SOLO
    ranked_flex_text = ranked_flex_text or DEFAULT_RANKED_FLEX

    soloRankInfo = rankInfo['queueMap']['RANKED_SOLO_5x5']
    soloTier = translateTier(soloRankInfo['tier'], is_english=is_english)
    soloDivision = soloRankInfo['division']
    if soloTier == '--' or soloDivision == 'NA':
        soloDivision = ""

    soloHighestTier = translateTier(soloRankInfo['highestTier'], is_english=is_english)
    soloHighestDivision = soloRankInfo['highestDivision']
    if soloHighestTier == '--' or soloHighestDivision == 'NA':
        soloHighestDivision = ""

    solxPreviousSeasonEndTier = translateTier(
        soloRankInfo['previousSeasonEndTier'], is_english=is_english)
    soloPreviousSeasonDivision = soloRankInfo[
        'previousSeasonEndDivision']
    if solxPreviousSeasonEndTier == '--' or soloPreviousSeasonDivision == 'NA':
        soloPreviousSeasonDivision = ""

    soloWins = soloRankInfo['wins']
    soloLosses = soloRankInfo['losses']
    soloTotal = soloWins + soloLosses
    soloWinRate = soloWins * 100 // soloTotal if soloTotal != 0 else 0
    soloLp = soloRankInfo['leaguePoints']

    flexRankInfo = rankInfo['queueMap']['RANKED_FLEX_SR']
    flexTier = translateTier(flexRankInfo['tier'], is_english=is_english)
    flexDivision = flexRankInfo['division']
    if flexTier == '--' or flexDivision == 'NA':
        flexDivision = ""

    flexHighestTier = translateTier(flexRankInfo['highestTier'], is_english=is_english)
    flexHighestDivision = flexRankInfo['highestDivision']
    if flexHighestTier == '--' or flexHighestDivision == 'NA':
        flexHighestDivision = ""

    flexPreviousSeasonEndTier = translateTier(
        flexRankInfo['previousSeasonEndTier'], is_english=is_english)
    flexPreviousSeasonEndDivision = flexRankInfo[
        'previousSeasonEndDivision']

    if flexPreviousSeasonEndTier == '--' or flexPreviousSeasonEndDivision == 'NA':
        flexPreviousSeasonEndDivision = ""

    flexWins = flexRankInfo['wins']
    flexLosses = flexRankInfo['losses']
    flexTotal = flexWins + flexLosses
    flexWinRate = flexWins * 100 // flexTotal if flexTotal != 0 else 0
    flexLp = flexRankInfo['leaguePoints']

    return [
        [
            ranked_solo_text,
            str(soloTotal),
            str(soloWinRate) + ' %' if soloTotal != 0 else '--',
            str(soloWins),
            str(soloLosses),
            f'{soloTier} {soloDivision}',
            str(soloLp),
            f'{soloHighestTier} {soloHighestDivision}',
            f'{solxPreviousSeasonEndTier} {soloPreviousSeasonDivision}',
        ],
        [
            ranked_flex_text,
            str(flexTotal),
            str(flexWinRate) + ' %' if flexTotal != 0 else '--',
            str(flexWins),
            str(flexLosses),
            f'{flexTier} {flexDivision}',
            str(flexLp),
            f'{flexHighestTier} {flexHighestDivision}',
            f'{flexPreviousSeasonEndTier} {flexPreviousSeasonEndDivision}',
        ],
    ]


# ---------------------------------------------------------------------------
# 数据层返回类型 (TypedDict)
#
# 这些结构对应 tools.py 中 parseGameData / parseSummonerData /
# parseGameDetailData 等解析函数返回的 dict, 供 IDE 补全与调用方校验.
# 注: 字段标注 total=False 表示所有字段均可选 (解析过程中可能因数据缺失而省略),
#     与现有解析逻辑的容错行为一致.
# ---------------------------------------------------------------------------


class RankTierInfo(TypedDict, total=False):
    """单队列段位信息 (parseRankInfo 中 solo/flex 子结构)."""
    tier: str
    icon: str
    division: str
    lp: object  # int 或 str


class RankInfo(TypedDict, total=False):
    """parseSummonerData 返回的 rankInfo."""
    solo: RankTierInfo
    flex: RankTierInfo


class GameSummary(TypedDict, total=False):
    """parseGameData 返回的单局摘要 (用于战绩栏)."""
    queueId: int
    gameId: int
    time: str
    shortTime: str
    name: str
    map: str
    duration: str
    remake: bool
    win: bool
    championId: int
    championIcon: object
    spell1Icon: object
    spell2Icon: object
    champLevel: int
    kills: int
    deaths: int
    assists: int
    itemIcons: List[object]
    runeIcon: object
    cs: int
    gold: int
    timeStamp: int
    position: Optional[str]
    augmentIds: List[int]


class GamesAggregate(TypedDict, total=False):
    """parseSummonerData 返回的 games 聚合."""
    gameCount: int
    wins: int
    losses: int
    kills: int
    deaths: int
    assists: int
    games: List[GameSummary]


class ChampionStat(TypedDict, total=False):
    """getRecentChampions 中的单项."""
    championId: int
    icon: object
    name: str
    total: int
    wins: int
    losses: int
    kills: int
    deaths: int
    assists: int


class SummonerParsedData(TypedDict, total=False):
    """parseSummonerData 的返回结构 (生涯页/搜索页)."""
    name: str
    icon: object
    level: int
    xpSinceLastLevel: int
    xpUntilNextLevel: int
    puuid: str
    rankInfo: RankInfo
    games: GamesAggregate
    champions: List[ChampionStat]
    isPublic: bool
    tagLine: Optional[str]


class TeamParticipant(TypedDict, total=False):
    """parseGameDetailData 中队伍内单个召唤师.

    也兼容 parseSummonerGameInfo / getSummonerGamesInfoViaSGP 返回的
    对局信息项 (额外含 cellId / selectedPosition / fateFlag / kda 等).
    """
    name: str
    puuid: str
    isPublic: bool
    isCurrent: bool
    championId: int
    championIcon: object
    spell1Icon: object
    spell2Icon: object
    kills: int
    deaths: int
    assists: int
    gold: int
    runeIcon: object
    itemIcons: List[object]
    rankInfo: object
    subteamPlacement: Optional[int]
    # parseSummonerGameInfo / getSummonerGamesInfoViaSGP 额外字段
    tagLine: Optional[str]
    icon: object
    level: int
    xpSinceLastLevel: int
    xpUntilNextLevel: int
    summonerId: int
    gamesInfo: List[GameSummary]
    kda: List[int]
    cellId: Optional[int]
    selectedPosition: Optional[str]
    fateFlag: Optional[str]
    recentlyChampionName: str


class TeamDetail(TypedDict, total=False):
    """parseGameDetailData 中单支队伍信息."""
    win: Optional[bool]
    bans: List[object]
    baronKills: int
    baronIcon: str
    dragonKills: int
    dragonIcon: str
    riftHeraldKills: int
    riftHeraldIcon: str
    inhibitorKills: int
    inhibitorIcon: str
    hordeKills: int
    towerKills: int
    towerIcon: str
    kills: int
    deaths: int
    assists: int
    gold: int
    summoners: List[TeamParticipant]


class GameDetail(TypedDict, total=False):
    """parseGameDetailData 的返回结构 (对局详情)."""
    queueId: int
    map: str
    name: str
    win: Optional[bool]
    remake: Optional[bool]
    cherryResult: Optional[int]
    teams: dict
    gameId: int


class TeamGameInfo(TypedDict, total=False):
    """parseAllyGameInfo / parseGameInfoByGameflowSession 的返回结构.

    summoners 元素的具体字段由 parseSummonerGameInfo / getSummonerGamesInfoViaSGP
    产生, 详见 TeamParticipant 与 ChampionStat.
    """
    summoners: List[dict]
    champions: dict  # {summonerId: championId}
    order: List[int]
    isAram: bool
