import itertools
import time
import ctypes
import os
from copy import deepcopy
from typing import Optional

import asyncio
from PyQt5.QtCore import QObject

from .exceptions import SummonerRankInfoNotFound
from ..common.config import cfg, Language
from ..lol.connector import connector
from ..common.signals import signalBus
from ..common.logger import logger

from .tools_pure import (
    timeStampToStr,
    timeStampToShortStr,
    secsToStr,
    separateTeams,
    sortedSummonersByGameRole,
    parseGames,
    parseSummonerOrder,  # noqa: F401  re-export for app.view.game_info_interface
)
from .tools_pure import (
    SummonerParsedData,
    GameSummary,
    GameDetail,
    TeamParticipant,
    TeamGameInfo,
)
from .persistent_cache import cache as sqlite_cache


SERVERS_NAME = {
    "NJ100": "联盟一区", "GZ100": "联盟二区", "CQ100": "联盟三区", "TJ100": "联盟四区", "TJ101": "联盟五区",
    "HN10": "黑色玫瑰", "HN1": "艾欧尼亚", "BGP2": "峡谷之巅"
}

SERVERS_SUBSET = {
    "NJ100": ["祖安", "皮尔特沃夫", "巨神峰", "教育网", "男爵领域", "均衡教派", "影流", "守望之海"],
    "GZ100": ["卡拉曼达", "暗影岛", "征服之海", "诺克萨斯", "战争学院", "雷瑟守备"],
    "CQ100": ["班德尔城", "裁决之地", "水晶之痕", "钢铁烈阳", "皮城警备"],
    "TJ100": ["比尔吉沃特", "弗雷尔卓德", "扭曲丛林"],
    "TJ101": ["德玛西亚", "无畏先锋", "恕瑞玛", "巨龙之巢"]
}


class ToolsTranslator(QObject):
    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.top = self.tr("TOP")
        self.jungle = self.tr("JUG")
        self.middle = self.tr("MID")
        self.bottom = self.tr("BOT")
        self.support = self.tr("SUP")

        self.positionMap = {
            "TOP": self.top,
            "JUNGLE": self.jungle,
            "MID": self.middle,
            "ADC": self.bottom,
            "SUPPORT": self.support
        }

        self.rankedSolo = self.tr('Ranked Solo')
        self.rankedFlex = self.tr("Ranked Flex")

        self.unranked = self.tr("Unranked")
        self.unknown = self.tr("Unknown")


def translateTier(orig: str, short=False) -> str:
    is_english = cfg.language.value == Language.ENGLISH
    from .tools_pure import translateTier as _translateTier_pure
    return _translateTier_pure(orig, short, is_english)


async def getRecentTeammates(games, puuid):
    summoners = {}

    for game in games:
        gameId = game['gameId']
        game = await connector.getGameDetailByGameId(gameId)
        teammates = getTeammates(game, puuid)

        for p in teammates['summoners']:
            if p['summonerId'] == 0:
                continue

            if p['puuid'] not in summoners:
                summonerIcon = await connector.getProfileIcon(p['icon'])
                summoners[p['puuid']] = {
                    "name": p['name'], 'icon': summonerIcon,
                    "total": 0, "wins": 0, "losses": 0, "puuid": p["puuid"]}

            summoners[p['puuid']]['total'] += 1

            if not teammates['remake']:
                if teammates['win']:
                    summoners[p['puuid']]['wins'] += 1
                else:
                    summoners[p['puuid']]['losses'] += 1

    ret = {"puuid": puuid, "summoners": [
        item for item in summoners.values()]}

    ret['summoners'] = sorted(ret['summoners'],
                              key=lambda x: x['total'], reverse=True)[:5]

    return ret


async def parseSummonerData(summoner, rankTask, gameTask) -> SummonerParsedData:
    iconId = summoner['profileIconId']
    try:
        icon = await connector.getProfileIcon(iconId)
    except Exception:
        cached_icon = f"./app/resource/game/profile icons/{iconId}.jpg"
        icon = cached_icon if os.path.exists(cached_icon) else "app/resource/images/game.png"
    level = summoner.get('summonerLevel', -1)
    xpSinceLastLevel = summoner.get('xpSinceLastLevel', 0)
    xpUntilNextLevel = summoner.get('xpUntilNextLevel', 0)

    try:
        gamesInfo = await gameTask
    except Exception as e:
        # ReferenceError 表示 LCU 尚未就绪 (启动竞态), 降为 warning 避免日志噪音
        logger.warning(f"parseSummonerData: failed to fetch games: {e}", "tools")
        champions = []
        games = {}
    else:
        # LCU 未就绪时 @retry 拦截 ReferenceError 返回 None
        if gamesInfo is None:
            logger.warning(
                "parseSummonerData: gamesInfo is None (LCU not ready)",
                "tools")
            champions = []
            games = {}
        else:
            games = {
                "gameCount": gamesInfo["gameCount"],
                "wins": 0,
                "losses": 0,
                "kills": 0,
                "deaths": 0,
                "assists": 0,
                "games": [],
            }
            for game in gamesInfo["games"]:
                info = await parseGameData(game)
                if time.time() - info["timeStamp"] / 1000 > 60 * 60 * 24 * 365:
                    continue
                if not info["remake"] and info["queueId"] != 0:
                    games["kills"] += info["kills"]
                    games["deaths"] += info["deaths"]
                    games["assists"] += info["assists"]
                    if info["win"]:
                        games["wins"] += 1
                    else:
                        games["losses"] += 1
                games["games"].append(info)

            champions = getRecentChampions(games['games'])
            logger.error(
                f"parseSummonerData: games fetched count={games['gameCount']} "
                f"parsed={len(games['games'])}", "tools")

    try:
        rankInfo = await rankTask
    except Exception as e:
        logger.warning(f"parseSummonerData: failed to fetch rank: {e}", "tools")
        rankInfo = {}
    else:
        # LCU 未就绪时 @retry 返回 None
        if rankInfo is None:
            rankInfo = {}

    return {
        'name': summoner.get("gameName") or summoner['displayName'],
        'icon': icon,
        'level': level,
        'xpSinceLastLevel': xpSinceLastLevel,
        'xpUntilNextLevel': xpUntilNextLevel,
        'puuid': summoner['puuid'],
        'rankInfo': rankInfo,
        'games': games,
        'champions': champions,
        'isPublic': summoner.get('privacy') == "PUBLIC",
        'tagLine': summoner.get("tagLine"),
    }


async def parseGameData(game) -> GameSummary:
    timeStamp = game["gameCreation"]  # 毫秒级时间戳
    time = timeStampToStr(game['gameCreation'])
    shortTime = timeStampToShortStr(game['gameCreation'])
    gameId = game['gameId']
    duration = secsToStr(game['gameDuration'])
    queueId = game['queueId']

    nameAndMap = connector.manager.getNameMapByQueueId(queueId)
    modeName = nameAndMap['name']

    if queueId != 0:
        mapName = nameAndMap['map']
    else:
        mapName = connector.manager.getMapNameById(game['mapId'])

    participant = game['participants'][0]
    championId = participant['championId']
    championIcon = await connector.getChampionIcon(championId)
    spell1Id = participant['spell1Id']
    spell2Id = participant['spell2Id']
    spell1Icon = await connector.getSummonerSpellIcon(spell1Id)
    spell2Icon = await connector.getSummonerSpellIcon(spell2Id)
    stats = participant['stats']

    champLevel = stats['champLevel']
    kills = stats['kills']
    deaths = stats['deaths']
    assists = stats['assists']
    itemIds = [
        stats['item0'],
        stats['item1'],
        stats['item2'],
        stats['item3'],
        stats['item4'],
        stats['item5'],
        stats['item6'],
    ]

    itemIcons = [await connector.getItemIcon(itemId) for itemId in itemIds]
    runeId = stats['perk0']
    runeIcon = await connector.getRuneIcon(runeId)

    cs = stats['totalMinionsKilled'] + stats['neutralMinionsKilled']
    gold = stats['goldEarned']
    remake = stats['gameEndedInEarlySurrender']
    win = stats['win']

    timeline = participant['timeline']
    lane = timeline['lane']
    role = timeline['role']

    position = None

    # 海克斯大乱斗: 读取强化 ID (playerAugment1~6)
    augmentIds = []
    if queueId == 2400:
        for i in range(1, 7):
            aid = stats.get(f'playerAugment{i}', 0)
            if aid:
                augmentIds.append(aid)

    tt = ToolsTranslator()

    if queueId in [420, 440]:
        if lane == 'TOP':
            position = tt.top
        elif lane == "JUNGLE":
            position = tt.jungle
        elif lane == 'MIDDLE':
            position = tt.middle
        elif role == 'SUPPORT':
            position = tt.support
        elif lane == 'BOTTOM' and role == 'CARRY':
            position = tt.bottom

    return {
        'queueId': queueId,
        'gameId': gameId,
        'time': time,
        'shortTime': shortTime,
        'name': modeName,
        'map': mapName,
        'duration': duration,
        'remake': remake,
        'win': win,
        'championId': championId,
        'championIcon': championIcon,
        'spell1Icon': spell1Icon,
        'spell2Icon': spell2Icon,
        'champLevel': champLevel,
        'kills': kills,
        'deaths': deaths,
        'assists': assists,
        'itemIcons': itemIcons,
        'runeIcon': runeIcon,
        'cs': cs,
        'gold': gold,
        'timeStamp': timeStamp,
        'position': position,
        'augmentIds': augmentIds,
    }


async def parseGameDetailData(puuid, game) -> GameDetail:
    queueId = game['queueId']
    mapId = game['mapId']

    names = connector.manager.getNameMapByQueueId(queueId)
    modeName = names['name']
    if queueId != 0:
        mapName = names['map']
    else:
        mapName = connector.manager.getMapNameById(mapId)

    def origTeam(teamId):
        return {
            'win': None,
            'bans': [],
            'baronKills': 0,
            'baronIcon': f"app/resource/images/baron-{teamId}.png",
            'dragonKills': 0,
            'dragonIcon': f'app/resource/images/dragon-{teamId}.png',
            'riftHeraldKills': 0,
            'riftHeraldIcon': f'app/resource/images/herald-{teamId}.png',
            'inhibitorKills': 0,
            'inhibitorIcon': f'app/resource/images/inhibitor-{teamId}.png',
            'hordeKills': 0,
            'towerKills': 0,
            'towerIcon': f'app/resource/images/tower-{teamId}.png',
            'kills': 0,
            'deaths': 0,
            'assists': 0,
            'gold': 0,
            'summoners': []
        }

    teams = {
        100: origTeam("100"),
        200: origTeam("200"),
        300: origTeam("100"),
        400: origTeam("200"),
        500: origTeam("100"),
        600: origTeam("200"),
        700: origTeam("100"),
        800: origTeam("200"),
    }

    cherryResult = None
    win = None

    for team in game['teams']:
        teamId = team['teamId']

        if teamId == 0:
            teamId = 200

        teams[teamId]['win'] = team['win']
        teams[teamId]['bans'] = [
            await connector.getChampionIcon(item['championId'])
            for item in team['bans']
        ]
        teams[teamId]['baronKills'] = team['baronKills']
        teams[teamId]['dragonKills'] = team['dragonKills']
        teams[teamId]['riftHeraldKills'] = team['riftHeraldKills']
        teams[teamId]['hordeKills'] = team['hordeKills']
        teams[teamId]['towerKills'] = team['towerKills']
        teams[teamId]['inhibitorKills'] = team['inhibitorKills']

    for participant in game['participantIdentities']:
        participantId = participant['participantId']
        summonerName = participant['player'].get(
            'gameName') or participant['player'].get('summonerName')  # 兼容外服
        summonerPuuid = participant['player']['puuid']
        isCurrent = (summonerPuuid == puuid)

        if summonerPuuid == '00000000-0000-0000-0000-000000000000':  # AI
            isPublic = True
        else:
            t = await connector.getSummonerByPuuid(summonerPuuid)
            isPublic = t.get("privacy") == "PUBLIC"

        for summoner in game['participants']:
            if summoner['participantId'] == participantId:
                stats = summoner['stats']

                if queueId != 1700:
                    subteamPlacement = None
                    tid = summoner['teamId']
                else:
                    subteamPlacement = stats['subteamPlacement']
                    tid = subteamPlacement * 100

                if isCurrent:
                    remake = stats['gameEndedInEarlySurrender']
                    win = stats['win']

                    if queueId == 1700:
                        cherryResult = subteamPlacement

                championId = summoner['championId']
                championIcon = await connector.getChampionIcon(championId)

                spell1Id = summoner['spell1Id']
                spell1Icon = await connector.getSummonerSpellIcon(spell1Id)
                spell2Id = summoner['spell2Id']
                spell2Icon = await connector.getSummonerSpellIcon(spell2Id)

                kills = stats['kills']
                deaths = stats['deaths']
                assists = stats['assists']
                gold = stats['goldEarned']

                teams[tid]['kills'] += kills
                teams[tid]['deaths'] += deaths
                teams[tid]['assists'] += assists
                teams[tid]['gold'] += gold

                runeIcon = await connector.getRuneIcon(stats['perk0'])

                itemIds = [
                    stats['item0'],
                    stats['item1'],
                    stats['item2'],
                    stats['item3'],
                    stats['item4'],
                    stats['item5'],
                    stats['item6'],
                ]

                itemIcons = [
                    await connector.getItemIcon(itemId) for itemId in itemIds
                ]

                getRankInfo = cfg.get(cfg.showTierInGameInfo)

                tier = division = lp = rankIcon = ""
                if getRankInfo:
                    try:
                        rank = await connector.getRankedStatsByPuuid(
                            summonerPuuid)
                    except SummonerRankInfoNotFound:
                        ...
                    else:
                        rank = rank['queueMap']

                        if queueId == 1700 and 'CHERRY' in rank:
                            rankInfo = rank["CHERRY"]
                            lp = rankInfo['ratedRating']
                        else:
                            rankInfo = rank[
                                'RANKED_FLEX_SR'] if queueId == 440 else rank['RANKED_SOLO_5x5']

                            tier = rankInfo['tier']
                            division = rankInfo['division']
                            lp = rankInfo['leaguePoints']

                            if tier == '':
                                rankIcon = 'app/resource/images/unranked.png'
                            else:
                                rankIcon = f'app/resource/images/{tier.lower()}.png'
                                tier = translateTier(tier, True)

                            if division == 'NA':
                                division = ''

                # 海克斯大乱斗: 读取强化 ID (playerAugment1~6)
                augmentIds = []
                if queueId == 2400:
                    for i in range(1, 7):
                        aid = stats.get(f'playerAugment{i}', 0)
                        if aid:
                            augmentIds.append(aid)

                item = {
                    'summonerName': summonerName,
                    'puuid': summonerPuuid,
                    'isCurrent': isCurrent,
                    'championIcon': championIcon,
                    'rankInfo': getRankInfo,
                    'tier': tier,
                    'division': division,
                    'lp': lp,
                    'rankIcon': rankIcon,
                    'spell1Icon': spell1Icon,
                    'spell2Icon': spell2Icon,
                    'itemIcons': itemIcons,
                    'kills': kills,
                    'deaths': deaths,
                    'assists': assists,
                    'cs': stats['totalMinionsKilled'] + stats['neutralMinionsKilled'],
                    'gold': gold,
                    'runeIcon': runeIcon,
                    'champLevel': stats['champLevel'],
                    'damage': stats['totalDamageDealtToChampions'],
                    'subteamPlacement': subteamPlacement,
                    'isPublic': isPublic,
                    'augmentIds': augmentIds,
                    # 战犯/躺赢狗诊断字段 (v4 stats 全量, OPGG 战犯算法使用)
                    'damageTaken': stats.get('totalDamageTaken', 0),
                    'magicDamage': stats.get('magicDamageDealtToChampions', 0),
                    'physicalDamage': stats.get('physicalDamageDealtToChampions', 0),
                    'trueDamage': stats.get('trueDamageDealtToChampions', 0),
                    'totalHeal': stats.get('totalHeal', 0),
                    'shieldOnTeammates': stats.get('totalDamageShieldedOnTeammates', 0),
                    'ccTime': stats.get('timeCCingOthers', 0),
                    'damageToTurrets': stats.get('damageDealtToTurrets', 0),
                    'damageToObjectives': stats.get('damageDealtToObjectives', 0),
                    'visionScore': stats.get('visionScore', 0),
                    'wardsPlaced': stats.get('wardsPlaced', 0),
                    'wardsKilled': stats.get('wardsKilled', 0),
                    'goldSpent': stats.get('goldSpent', 0),
                    'longestTimeSpentLiving': stats.get('longestTimeSpentLiving', 0),
                    'largestKillingSpree': stats.get('largestKillingSpree', 0),
                }
                teams[tid]['summoners'].append(item)

                break

    mapIcon = connector.manager.getMapIconByMapId(mapId, win)

    if win is None:
        return None

    result = {
        'gameId': game['gameId'],
        'mapIcon': mapIcon,
        'gameCreation': timeStampToStr(game['gameCreation']),
        'gameDuration': secsToStr(game['gameDuration']),
        'modeName': modeName,
        'mapName': mapName,
        'queueId': queueId,
        'win': win,
        'cherryResult': cherryResult,
        'remake': remake,
        'teams': teams,
    }
    asyncio.get_running_loop().run_in_executor(
        None, sqlite_cache.set_game_detail, game['gameId'], result)
    return result


def getTeammates(game, targetPuuid):
    """
    通过 game 信息获取目标召唤师的队友

    @param game: @see connector.getGameDetailByGameId
    @param targetPuuid: 目标召唤师 puuid
    @return: @see res
    """
    targetParticipantId = None

    for participant in game['participantIdentities']:
        puuid = participant['player']['puuid']

        if puuid == targetPuuid:
            targetParticipantId = participant['participantId']
            break

    assert targetParticipantId is not None

    for player in game['participants']:
        if player['participantId'] == targetParticipantId:
            if game['queueId'] != 1700:
                tid = player['teamId']
            else:  # 斗魂竞技场
                tid = player['stats']['subteamPlacement']

            win = player['stats']['win']
            remake = player['stats']['teamEarlySurrendered']

            break

    res = {
        'queueId': game['queueId'],
        'win': win,
        'remake': remake,
        'summoners': [],  # 队友召唤师 (由于兼容性, 未修改字段名)
        'enemies': []  # 对面召唤师, 若有多个队伍会全放这里面
    }

    for player in game['participants']:

        if game['queueId'] != 1700:
            cmp = player['teamId']
        else:
            cmp = player['stats']['subteamPlacement']

        p = player['participantId']
        s = game['participantIdentities'][p - 1]['player']

        if cmp == tid:
            if s['puuid'] != targetPuuid:
                res['summoners'].append(
                    {'summonerId': s['summonerId'], 'name': s['summonerName'], 'puuid': s['puuid'], 'icon': s['profileIcon']})
            else:
                # 当前召唤师在该对局使用的英雄, 自定义对局没有该字段
                res["championId"] = player.get('championId', -1)
        else:
            res['enemies'].append(
                {'summonerId': s['summonerId'], 'name': s['summonerName'], 'puuid': s['puuid'],
                 'icon': s['profileIcon']})

    return res


def getRecentChampions(games):
    champions = {}

    for game in games:
        if game['queueId'] == 0:
            continue

        championId = game['championId']

        if championId not in champions:
            champions[championId] = {
                'icon': game['championIcon'], 'wins': 0, 'losses': 0, 'total': 0}

        champions[championId]['total'] += 1

        if not game['remake']:
            if game['win']:
                champions[championId]['wins'] += 1
            else:
                champions[championId]['losses'] += 1

    ret = [item for item in champions.values()]
    ret.sort(key=lambda x: x['total'], reverse=True)

    maxLen = 10

    return ret if len(ret) < maxLen else ret[:maxLen]


def parseRankInfo(info):
    """
    解析 `connector.getRankedStatsByPuuid()` 的数据。


    api: `/lol-ranked/v1/ranked-stats/{puuid}`

    :param info: 接口返回值, 允许为空（接口异常时抛出 `SummonerRankInfoNotFound`, 需要捕获置空）

    """
    tt = ToolsTranslator()
    is_english = cfg.language.value == Language.ENGLISH
    from .tools_pure import parseRankInfo as _parseRankInfoPure
    return _parseRankInfoPure(info, tt.unranked, tt.unknown, is_english)


def parseRankInfoFromSGP(info):
    '''解析来自 `connector.getRankedStatsByPuuidViaSGP()` 的数据'''

    tt = ToolsTranslator()

    soloIcon = flexIcon = "app/resource/images/UNRANKED.svg"
    soloTier = flexTier = tt.unknown
    soloDivision = flexDivision = ""
    soloRankInfo = flexRankInfo = {"leaguePoints": ""}

    if info:
        for queue in info['queues']:
            type = queue['queueType']
            if type == 'RANKED_FLEX_SR':
                flexRankInfo = queue
            elif type == 'RANKED_SOLO_5x5':
                soloRankInfo = queue

        soloTier = soloRankInfo.get("tier", "")
        soloDivision = soloRankInfo.get("rank", "NA")

        if soloTier == "":
            soloIcon = "app/resource/images/UNRANKED.svg"
            soloTier = tt.unranked
        else:
            soloIcon = f"app/resource/images/{soloTier}.svg"
            soloTier = translateTier(soloTier, True)
        if soloDivision == "NA":
            soloDivision = ""

        flexTier = flexRankInfo.get("tier", "")
        flexDivision = flexRankInfo.get("rank", "NA")

        if flexTier == "":
            flexIcon = "app/resource/images/UNRANKED.svg"
            flexTier = tt.unranked
        else:
            flexIcon = f"app/resource/images/{flexTier}.svg"
            flexTier = translateTier(flexTier, True)
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


def parseDetailRankInfo(rankInfo):
    pt = ToolsTranslator()
    is_english = cfg.language.value == Language.ENGLISH
    from .tools_pure import parseDetailRankInfo as _parseDetailRankInfoPure
    return _parseDetailRankInfoPure(rankInfo, pt.rankedSolo, pt.rankedFlex, is_english)


async def parseAllyGameInfo(session, currentSummonerId, queueID, useSGP=False) -> TeamGameInfo:

    if useSGP and connector.isInTencent():
        # 如果是国服就优先尝试 SGP
        try:
            tasks = [getSummonerGamesInfoViaSGP(item, queueID, currentSummonerId)
                     for item in session['myTeam']]
            summoners = await asyncio.gather(*tasks)
        except Exception:
            tasks = [parseSummonerGameInfo(item, queueID, currentSummonerId)
                     for item in session['myTeam']]
            summoners = await asyncio.gather(*tasks)

    else:
        tasks = [parseSummonerGameInfo(item, queueID, currentSummonerId)
                 for item in session['myTeam']]
        summoners = await asyncio.gather(*tasks)

    summoners = [summoner for summoner in summoners if summoner]

    # 按照楼层排序
    summoners = sorted(
        summoners, key=lambda x: x["cellId"])

    champions = {summoner['summonerId']: summoner['championId']
                 for summoner in summoners}
    order = [summoner['summonerId'] for summoner in summoners]

    return {'summoners': summoners, 'champions': champions, 'order': order, "isAram": session.get('benchEnabled', False)}


async def parseGameInfoByGameflowSession(session, currentSummonerId, side, useSGP=False) -> Optional[TeamGameInfo]:
    data = session['gameData']
    queueId = data['queue']['id']

    if queueId in (1700, 1090, 1100, 1110, 1130, 1160):  # 斗魂 云顶匹配 (排位)
        return None

    if side == 'enemy':
        _, team = separateTeams(data, currentSummonerId)
    else:
        team, _ = separateTeams(data, currentSummonerId)

    if team is None:
        return None

    # Filter invalid entries and deduplicate
    valid = []
    seen = set()
    for p in team:
        sid = p.get('summonerId', 0)
        if sid == 0 or sid is None or sid in seen:
            continue
        seen.add(sid)
        valid.append(p)
    team = valid

    if not team:
        return None

    if useSGP and connector.isInTencent():
        # 如果是国服就优先尝试 SGP
        try:
            tasks = [getSummonerGamesInfoViaSGP(item, queueId, currentSummonerId)
                     for item in team]
            summoners = await asyncio.gather(*tasks)

        except Exception:
            tasks = [parseSummonerGameInfo(item, queueId, currentSummonerId)
                     for item in team]
            summoners = await asyncio.gather(*tasks)

    else:
        tasks = [parseSummonerGameInfo(item, queueId, currentSummonerId)
                 for item in team]
        summoners = await asyncio.gather(*tasks)

    summoners = [summoner for summoner in summoners if summoner]

    if queueId in [420, 440]:
        s = sortedSummonersByGameRole(summoners)

        if s is not None:
            summoners = s

    champions = {summoner['summonerId']: summoner['championId']
                 for summoner in summoners}
    order = [summoner['summonerId'] for summoner in summoners]

    return {'summoners': summoners, 'champions': champions, 'order': order}


def getAllyOrderByGameRole(session, currentSummonerId):
    data = session['gameData']
    queueId = data['queue']['id']

    # 只有排位模式下有返回值
    if queueId not in (420, 440):
        return None

    ally, _ = separateTeams(data, currentSummonerId)
    if ally is None:
        return None

    ally = sortedSummonersByGameRole(ally)

    if ally is None:
        return None

    return [x['summonerId'] for x in ally]


def getTeamColor(session, currentSummonerId):
    '''
    输入 session 以及当前召唤师 id，输出 summonerId -> 颜色的映射
    '''
    data = session['gameData']
    ally, enemy = separateTeams(data, currentSummonerId)

    if ally is None or enemy is None:
        return {}

    def makeTeam(team):
        # teamParticipantId => [summonerId]
        tIdToSIds = {}

        for s in team:
            summonerId = s.get('summonerId')
            if not summonerId:
                continue

            teamParticipantId = s.get('teamParticipantId')
            if not teamParticipantId:
                continue

            summoners = tIdToSIds.get(teamParticipantId)

            if not summoners:
                tIdToSIds[teamParticipantId] = [summonerId]
            else:
                tIdToSIds[teamParticipantId].append(summonerId)

        # summonerId => color
        res = {}

        currentColor = 0

        for ids in tIdToSIds.values():
            if len(ids) == 1:
                res[ids[0]] = -1
            else:
                for id in ids:
                    res[id] = currentColor

                currentColor += 1

        return res

    return makeTeam(ally), makeTeam(enemy)


async def parseGamesDataConcurrently(games, puuid: str = ""):
    results = await asyncio.gather(*[parseGameData(game) for game in games])
    if puuid:
        asyncio.get_running_loop().run_in_executor(
            None, sqlite_cache.set_games, puuid, results)
    return results


async def parseSummonerGameInfo(item, queueId, currentSummonerId) -> Optional[TeamParticipant]:
    summonerId = item.get('summonerId', None)

    if item.get('nameVisibilityType') == 'HIDDEN':
        return None

    if summonerId == 0 or summonerId is None:
        return None

    summoner = await connector.getSummonerById(summonerId)

    championId = item.get('championId') or 0
    icon = await connector.getChampionIcon(championId)

    puuid = summoner.get("puuid", None)

    if puuid == "00000000-0000-0000-0000-000000000000" or not puuid:
        return None

    try:
        origRankInfo = await connector.getRankedStatsByPuuid(puuid)
    except SummonerRankInfoNotFound:
        origRankInfo = None

    rankInfo = parseRankInfo(origRankInfo)

    try:
        origGamesInfo = await connector.getSummonerGamesByPuuid(
            puuid, 0, 14)

        queueFilterList = cfg.get(cfg.queueFilter)
        queueIds = queueFilterList.get(f"{queueId}")
        if queueIds:
            origGamesInfo["games"] = [
                game for game in origGamesInfo["games"] if game["queueId"] in queueIds]

            begIdx = 15
            while len(origGamesInfo["games"]) < 11 and begIdx <= 70:
                endIdx = begIdx + 5
                new = (await connector.getSummonerGamesByPuuid(puuid, begIdx, endIdx))["games"]

                for game in new:
                    if game["queueId"] in queueIds:
                        origGamesInfo['games'].append(game)

                begIdx = endIdx + 1
    except Exception:
        gamesInfo = []
    else:
        tasks = [parseGameData(game)
                 for game in origGamesInfo["games"][:11]]
        gamesInfo = await asyncio.gather(*tasks)

    _, kill, deaths, assists, _, _ = parseGames(gamesInfo)

    teammatesInfo = [
        getTeammates(
            await connector.getGameDetailByGameId(game["gameId"]),
            puuid
        ) for game in gamesInfo[:1]  # 避免空报错, 查上一局的队友(对手)
    ]

    recentlyChampionName = ""
    fateFlag = None

    if teammatesInfo:  # 判个空, 避免太久没有打游戏的玩家或新号引发异常
        if currentSummonerId in [t['summonerId'] for t in teammatesInfo[0]['summoners']]:
            # 上把队友
            fateFlag = "ally"
        elif currentSummonerId in [t['summonerId'] for t in teammatesInfo[0]['enemies']]:
            # 上把对面
            fateFlag = "enemy"
        recentlyChampionId = max(
            teammatesInfo and teammatesInfo[0]['championId'], 0)  # 取不到时是-1, 如果-1置为0
        recentlyChampionName = connector.manager.champs.get(
            recentlyChampionId)

    return {
        "name": summoner.get("gameName") or summoner.get("internalName"),
        'tagLine': summoner.get("tagLine"),
        "icon": icon,
        'championId': championId,
        "level": summoner["summonerLevel"],
        "rankInfo": rankInfo,
        "gamesInfo": gamesInfo,
        "xpSinceLastLevel": summoner["xpSinceLastLevel"],
        "xpUntilNextLevel": summoner["xpUntilNextLevel"],
        "puuid": puuid,
        "summonerId": summonerId,
        "kda": [kill, deaths, assists],
        "cellId": item.get("cellId"),
        "selectedPosition": item.get("selectedPosition"),
        "fateFlag": fateFlag,
        "isPublic": summoner["privacy"] == "PUBLIC",
        # 最近游戏的英雄 (用于上一局与与同一召唤师游玩之后显示)
        "recentlyChampionName": recentlyChampionName
    }


async def getSummonerGamesInfoViaSGP(item, queueID, currentSummonerId) -> Optional[TeamParticipant]:
    '''
    使用 SGP 接口取战绩信息
    '''
    puuid = item.get('puuid')

    if item.get('nameVisibilityType') == 'HIDDEN':
        return None

    if puuid == "00000000-0000-0000-0000-000000000000" or not puuid:
        return None

    championId = item.get('championId') or 0
    icon = await connector.getChampionIcon(championId)
    summoner = await connector.getSummonerByPuuidViaSGP(puuid)

    try:
        origRankInfo = await connector.getRankedStatsByPuuidViaSGP(puuid)
    except SummonerRankInfoNotFound:
        origRankInfo = None

    rankInfo = parseRankInfoFromSGP(origRankInfo)

    try:
        origGamesInfo = await connector.getSummonerGamesByPuuidViaSGP(puuid, 0, 14)

        queueFilterList = cfg.get(cfg.queueFilter)
        queueIds = queueFilterList.get(f"{queueID}")
        if queueIds:
            origGamesInfo["games"] = [
                game for game in origGamesInfo["games"] if game['json']["queueId"] in queueIds]

            begIdx = 15
            while len(origGamesInfo["games"]) < 11 and begIdx <= 70:
                endIdx = begIdx + 10
                new = (await connector.getSummonerGamesByPuuidViaSGP(puuid, begIdx, endIdx))["games"]

                for game in new:
                    if game['json']["queueId"] in queueIds:
                        origGamesInfo['games'].append(game)

                begIdx = endIdx + 1
    except Exception:
        gamesInfo = []
    else:
        summonerName, tagLine = getNameTagLineFromGame(
            origGamesInfo['games'][0], puuid)

        tasks = [parseGamesDataFromSGP(game, puuid)
                 for game in origGamesInfo["games"][:11]]
        gamesInfo = await asyncio.gather(*tasks)

    _, kill, deaths, assists, _, _ = parseGames(gamesInfo)

    teammatesInfo = [
        getTeammatesFromSGPGame(
            game,
            puuid
        ) for game in origGamesInfo['games'][:1]  # 避免空报错, 查上一局的队友(对手)
    ]

    recentlyChampionName = ""
    fateFlag = None

    if teammatesInfo:  # 判个空, 避免太久没有打游戏的玩家或新号引发异常
        if currentSummonerId in [t['summonerId'] for t in teammatesInfo[0]['summoners']]:
            # 上把队友
            fateFlag = "ally"
        elif currentSummonerId in [t['summonerId'] for t in teammatesInfo[0]['enemies']]:
            # 上把对面
            fateFlag = "enemy"
        recentlyChampionId = max(
            teammatesInfo and teammatesInfo[0]['championId'], 0)  # 取不到时是-1, 如果-1置为0
        recentlyChampionName = connector.manager.champs.get(
            recentlyChampionId)

    # 适用于 LCU API 返回值
    # return {
    #     "name": summoner.get("gameName"),
    #     'tagLine': summoner.get('tagLine'),
    #     "icon": icon,
    #     'championId': championId,
    #     "level": summoner["summonerLevel"],
    #     "rankInfo": rankInfo,
    #     "gamesInfo": gamesInfo,
    #     "xpSinceLastLevel": summoner["xpSinceLastLevel"],
    #     "xpUntilNextLevel": summoner["xpUntilNextLevel"],
    #     "puuid": puuid,
    #     "summonerId": summoner['summonerId'],
    #     "kda": [kill, deaths, assists],
    #     "cellId": item.get("cellId"),
    #     "selectedPosition": item.get("selectedPosition"),
    #     "fateFlag": fateFlag,
    #     "isPublic": summoner["privacy"] == "PUBLIC",
    #     # 最近游戏的英雄 (用于上一局与与同一召唤师游玩之后显示)
    #     "recentlyChampionName": recentlyChampionName
    # }

    # 适用于 SGP API 返回值
    return {
        "name": summonerName,
        'tagLine': tagLine,
        "icon": icon,
        'championId': championId,
        "level": summoner["level"],
        "rankInfo": rankInfo,
        "gamesInfo": gamesInfo,
        "xpSinceLastLevel": summoner["expPoints"],
        "xpUntilNextLevel": summoner["expToNextLevel"],
        "puuid": puuid,
        "summonerId": summoner['id'],
        "kda": [kill, deaths, assists],
        "cellId": item.get("cellId"),
        "selectedPosition": item.get("selectedPosition"),
        "fateFlag": fateFlag,
        "isPublic": summoner["privacy"] == "PUBLIC",
        # 最近游戏的英雄 (用于上一局与与同一召唤师游玩之后显示)
        "recentlyChampionName": recentlyChampionName
    }


def getTeammatesFromSGPGame(game, puuid):
    json = game['json']
    queueId = json['queueId']

    for player in json['participants']:
        if player['puuid'] == puuid:
            if queueId != 1700:
                tid = player['teamId']
            else:  # 斗魂竞技场
                tid = player['subteamPlacement']

            win = player['win']
            remake = player['teamEarlySurrendered']

            break

    res = {
        'queueId': queueId,
        'win': win,
        'remake': remake,
        'summoners': [],  # 队友召唤师 (由于兼容性, 未修改字段名)
        'enemies': []  # 对面召唤师, 若有多个队伍会全放这里面
    }

    for player in json['participants']:
        if queueId != 1700:
            cmp = player['teamId']
        else:
            cmp = player['subteamPlacement']

        if cmp == tid:
            if player['puuid'] != puuid:
                res['summoners'].append({
                    'summonerId': player['summonerId'],
                    'name': player['summonerName'],
                    'puuid': player['puuid'],
                    'icon': player['profileIcon']
                })
            else:
                # 当前召唤师在该对局使用的英雄, 自定义对局没有该字段
                res["championId"] = player.get('championId', -1)
        else:
            res['enemies'].append({
                'summonerId': player['summonerId'],
                'name': player['summonerName'],
                'puuid': player['puuid'],
                'icon': player['profileIcon']
            })

    return res


async def parseGamesDataFromSGP(game, puuid):
    """
    解析由 SGP 接口得到的具体到某一局的对局记录信息
    """

    game = game['json']

    timeStamp = game["gameCreation"]  # 毫秒级时间戳
    time = timeStampToStr(game['gameCreation'])
    shortTime = timeStampToShortStr(game['gameCreation'])
    gameId = game['gameId']
    duration = secsToStr(game['gameDuration'])
    queueId = game['queueId']

    nameAndMap = connector.manager.getNameMapByQueueId(queueId)
    modeName = nameAndMap['name']

    if queueId != 0:
        mapName = nameAndMap['map']
    else:
        mapName = connector.manager.getMapNameById(game['mapId'])

    participant = None
    for p in game['participants']:
        if p['puuid'] == puuid:
            participant = p

    championId = participant['championId']
    championIcon = await connector.getChampionIcon(championId)
    spell1Id = participant['spell1Id']
    spell2Id = participant['spell2Id']
    spell1Icon = await connector.getSummonerSpellIcon(spell1Id)
    spell2Icon = await connector.getSummonerSpellIcon(spell2Id)

    champLevel = participant['champLevel']
    kills = participant['kills']
    deaths = participant['deaths']
    assists = participant['assists']

    itemIds = [
        participant['item0'],
        participant['item1'],
        participant['item2'],
        participant['item3'],
        participant['item4'],
        participant['item5'],
        participant['item6'],
    ]

    itemIcons = [await connector.getItemIcon(itemId) for itemId in itemIds]
    runeId = participant['perks']['styles'][0]['selections'][0]['perk']
    runeIcon = await connector.getRuneIcon(runeId)

    cs = participant['totalMinionsKilled'] + \
        participant['neutralMinionsKilled']
    gold = participant['goldEarned']
    remake = participant['gameEndedInEarlySurrender']
    win = participant['win']

    lane = participant['lane']
    role = participant['role']

    position = None
    tt = ToolsTranslator()

    if queueId in [420, 440]:
        if lane == 'TOP':
            position = tt.top
        elif lane == "JUNGLE":
            position = tt.jungle
        elif lane == 'MIDDLE':
            position = tt.middle
        elif role == 'SUPPORT':
            position = tt.support
        elif lane == 'BOTTOM' and role == 'CARRY':
            position = tt.bottom

    # 海克斯大乱斗: 读取强化 ID (SGP 通道, participant 上扁平字段)
    augmentIds = []
    if queueId == 2400:
        for i in range(1, 7):
            aid = participant.get(f'playerAugment{i}', 0)
            if aid:
                augmentIds.append(aid)

    return {
        'queueId': queueId,
        'gameId': gameId,
        'time': time,
        'shortTime': shortTime,
        'name': modeName,
        'map': mapName,
        'duration': duration,
        'remake': remake,
        'win': win,
        'championId': championId,
        'championIcon': championIcon,
        'spell1Icon': spell1Icon,
        'spell2Icon': spell2Icon,
        'champLevel': champLevel,
        'kills': kills,
        'deaths': deaths,
        'assists': assists,
        'itemIcons': itemIcons,
        'runeIcon': runeIcon,
        'cs': cs,
        'gold': gold,
        'timeStamp': timeStamp,
        'position': position,
        'augmentIds': augmentIds,
    }


def getNameTagLineFromGame(game, puuid):
    for player in game['json']['participants']:
        if player['puuid'] == puuid:
            return player['riotIdGameName'], player['riotIdTagline']

    return None


class ChampionSelection:
    def __init__(self):
        self.isSummonerSpellSetted = False
        self.isChampionShowed = False
        self.isChampionBanned = False
        self.isChampionPicked = False
        self.isChampionPickedCompleted = False
        self.isSkinPicked = False
        self.opggShowChampionId = None
        self.queueId = None

        # 海克斯/大乱斗抢英雄 (备选席模式, 与上面的 Rift 字段相互隔离)
        self.isHextechMode = False          # 本局是否为备选席抢人模式 (benchEnabled)
        self.hextechTargetId = None         # 当前抢人目标 championId (愿望单命中 or 用户手动点击)
        self.isHextechGrabbed = False       # 本局是否已成功抢到 (幂等防抖, 成功后 early-return)
        self.manualGrabRequested = False    # 用户是否在窗口手动点了头像触发抢

    def reset(self):
        self.__init__()


def _getLocalChampionId(data):
    """
    从 champ-select session 取本地玩家当前手持的英雄 id
    ARAM/Hextech 下 data['actions'] 为空, 英雄持有信息在 myTeam[*].championId
    """
    cellId = data.get('localPlayerCellId')
    if cellId is None:
        return 0
    for player in data.get('myTeam', []):
        if player.get('cellId') == cellId:
            return player.get('championId', 0) or 0
    return 0


def _getBenchChampionIds(data):
    """
    从 champ-select session 取备选席英雄 id 列表
    兼容两种格式:
      - 新版/国服: benchChampions = [{championId, isPriority}, ...] (对象数组)
      - 旧版:      benchChampionIds = [int, ...] (int 数组, 已废弃)
    """
    benchChampions = data.get('benchChampions')
    if isinstance(benchChampions, list):
        return [item.get('championId') for item in benchChampions
                if isinstance(item, dict) and item.get('championId')]
    # 兼容旧版
    ids = data.get('benchChampionIds')
    if isinstance(ids, list):
        return [i for i in ids if i]
    return []


def _resolveHextechTarget(bench, mine, selection):
    """
    决定本次抢人的目标英雄 id
    优先级: 用户手动点击 (selection.hextechTargetId) > 愿望单按序匹配 (cfg.hextechChampions)
    返回目标 id; 无目标返回 None
    """
    # 用户手动指定优先
    target = selection.hextechTargetId
    if target and target != mine:
        return target

    # 愿望单按序匹配, 命中备选席且非当前手持
    wishlist = cfg.get(cfg.hextechChampions) or []
    for w in wishlist:
        if w in bench and w != mine:
            return w

    return None


async def _doBenchSwapWithRetry(target, max_retries=20):
    for attempt in range(max_retries):
        try:
            await connector.benchSwap(target)
            return True
        except Exception as e:
            if attempt < max_retries - 1:
                logger.debug(
                    f"hextech benchSwap attempt {attempt+1} failed for {target}: {e}, retrying...",
                    "autoBenchGrab")
                await asyncio.sleep(0.1)
            else:
                logger.warning(
                    f"hextech benchSwap failed for {target} after {max_retries} attempts: {e}",
                    "autoBenchGrab")
                return False
    return False


async def autoBenchGrab(data, selection: ChampionSelection):
    """
    海克斯/大乱斗抢英雄: 检测备选席, 命中愿望单/手动目标则自动 benchSwap

    节奏策略 (事件驱动为主):
      - 默认靠 WS 的 champSelectChanged 每帧判一次, 零额外 HTTP
      - benchSwap 失败时自动重试 (网络抖动/竞态保护)
      - 仅在目标不在 bench 但用户已手动请求时, 短轮询 (200ms x 8) 等待释放

    返回 True 表示本帧已消费 (触发 phase dispatch 的 break)
    """
    if not data.get('benchEnabled'):
        return False
    selection.isHextechMode = True

    if selection.isHextechGrabbed:
        return False

    if not cfg.get(cfg.enableAutoAramBench) and not selection.manualGrabRequested:
        return False

    bench = set(_getBenchChampionIds(data))
    mine = _getLocalChampionId(data)

    logger.debug(
        f"hextech bench={sorted(bench)}, mine={mine}, "
        f"target={selection.hextechTargetId}, wishlist={cfg.get(cfg.hextechChampions)}",
        "autoBenchGrab")

    target = _resolveHextechTarget(bench, mine, selection)
    if target is None:
        return False

    if target in bench:
        if await _doBenchSwapWithRetry(target):
            selection.isHextechGrabbed = True
            logger.info(f"hextech grabbed champion {target}", "autoBenchGrab")
            signalBus.hextechGrabbed.emit(target)
            return True
        return False

    if not selection.manualGrabRequested:
        return False

    for _ in range(8):
        await asyncio.sleep(0.15)
        try:
            sess = await connector.getChampSelectSession()
        except Exception:
            continue
        curBench = set(_getBenchChampionIds(sess))
        curMine = _getLocalChampionId(sess)
        if target == curMine:
            selection.isHextechGrabbed = True
            logger.info(
                f"hextech already holding champion {target}", "autoBenchGrab")
            signalBus.hextechGrabbed.emit(target)
            return True
        if target in curBench:
            if await _doBenchSwapWithRetry(target):
                selection.isHextechGrabbed = True
                logger.info(
                    f"hextech grabbed champion {target} (after poll)",
                    "autoBenchGrab")
                signalBus.hextechGrabbed.emit(target)
                return True
            return False

    return False


async def autoSwap(data, selection: ChampionSelection):
    """
    选用顺序交换请求发生时，自动接受
    """

    if not cfg.get(cfg.autoAcceptCeilSwap):
        return

    for pickOrderSwap in data['pickOrderSwaps']:
        if 'RECEIVED' == pickOrderSwap['state']:
            await asyncio.sleep(0.5)
            await connector.acceptSwap(pickOrderSwap['id'])

            selection.isChampionPickedCompleted = False
            return True


async def autoTrade(data, selection):
    """
    英雄交换请求发生时，自动接受
    """
    if not cfg.get(cfg.autoAcceptChampTrade):
        return False

    for trade in data['trades']:
        if 'RECEIVED' == trade['state']:
            await asyncio.sleep(0.5)
            await connector.acceptTrade(trade['id'])

            return True

    return False


async def showOpggBuild(data, selection: ChampionSelection):
    cellId = data['localPlayerCellId']

    # 只有在英雄已经选定后才会尝试刷新 OPGG 界面
    for actionGroup in data['actions']:
        # 这里必须遍历完所有的 actorCellId == cellId 的所有 action
        for action in actionGroup:
            if not action['actorCellId'] == cellId:
                continue

            if action['type'] != 'pick':
                continue

            if not action['completed']:
                return False

    # 拿一下位置和英雄 ID
    for player in data['myTeam']:
        if player['cellId'] == cellId:
            position = player.get('assignedPosition', "")
            championId = player['championId'] or player['championPickIntent']
            break

    # 大乱斗模式下，即使锁定了也可能会换英雄，这里判断一下
    if championId == selection.opggShowChampionId:
        return False

    map = {
        'TOP': "TOP",
        'JUNGLE': "JUNGLE",
        'MIDDLE': "MID",
        'BOTTOM': "ADC",
        'UTILITY': "SUPPORT",
    }

    position = map.get(position, "")

    if championId == 0:
        return False

    if selection.queueId is None:
        if data.get('benchEnabled'):
            mode = "aram"
        elif len(data['myTeam']) == 2:
            mode = 'arena'
        else:
            mode = ""
    else:
        if selection.queueId == 450:
            mode = 'aram'
        elif selection.queueId == 2400:
            mode = 'aram_mayhem'
        elif selection.queueId in (1700, 1710):
            mode = 'arena'
        elif selection.queueId == 1300:
            mode = 'nexus_blitz'
        elif selection.queueId in (900, 1900):
            mode = 'urf'
        else:
            mode = 'ranked'

    selection.opggShowChampionId = championId
    signalBus.toOpggBuildInterface.emit(championId, mode, position)

    return True


async def autoPick(data, selection: ChampionSelection):
    """
    自动选用英雄
    """

    if not cfg.get(cfg.enableAutoSelectChampion) or selection.isChampionPicked:
        return

    localPlayerCellId = data['localPlayerCellId']

    for player in data['myTeam']:
        if player["cellId"] != localPlayerCellId:
            continue

        if bool(player['championId']) or bool(player['championPickIntent']):
            selection.isChampionPicked = True
            return

        break

    bans = itertools.chain(data["bans"]['myTeamBans'],
                           data["bans"]['theirTeamBans'])

    pos = next(filter(lambda x: x['cellId'] ==
               localPlayerCellId, data['myTeam']), None)
    pos = pos.get('assignedPosition')

    if pos == 'top':
        candidates = deepcopy(cfg.get(cfg.autoSelectChampionTop))
    elif pos == 'jungle':
        candidates = deepcopy(cfg.get(cfg.autoSelectChampionJug))
    elif pos == 'middle':
        candidates = deepcopy(cfg.get(cfg.autoSelectChampionMid))
    elif pos == 'bottom':
        candidates = deepcopy(cfg.get(cfg.autoSelectChampionBot))
    elif pos == 'utility':
        candidates = deepcopy(cfg.get(cfg.autoSelectChampionSup))
    else:
        candidates = []

    candidates.extend(cfg.get(cfg.autoSelectChampion))

    candidates = [x for x in candidates if x not in bans]

    if not candidates:
        selection.isChampionPicked = True
        return

    championId = candidates[0]

    for actionGroup in reversed(data['actions']):
        for action in actionGroup:
            if (action["actorCellId"] == localPlayerCellId
                    and action['type'] == "pick"):

                await connector.selectChampion(action['id'], championId)
                selection.isChampionPicked = True
                return True


async def autoComplete(data, selection: ChampionSelection):
    """
    超时自动选定（当前选中英雄）
    """
    isAutoCompleted = cfg.get(cfg.enableAutoSelectTimeoutCompleted)
    if not isAutoCompleted or selection.isChampionPickedCompleted:
        return

    if not (localPlayerCellId := data.get('localPlayerCellId', None)):
        return

    for actionGroup in reversed(data['actions']):
        for action in actionGroup:
            if action['actorCellId'] != localPlayerCellId:
                continue

            if action['type'] != 'pick':
                continue

            if not action['isInProgress']:
                return False

            if action['completed']:
                selection.isChampionPickedCompleted = True
                return False

            break

    selection.isChampionPickedCompleted = True

    sleepTime = int(data['timer']['adjustedTimeLeftInPhase'] / 1000) - 4
    await asyncio.sleep(sleepTime)

    data = await connector.getChampSelectSession()

    if not data:
        return

    # 双方选过的英雄
    cantSelect = []

    # 双方 ban 掉的英雄
    bans = itertools.chain(data["bans"]['myTeamBans'],
                           data["bans"]['theirTeamBans'])

    championIntent = 0
    for actionGroup in data['actions']:
        for action in actionGroup:
            if (action['type'] == 'pick' and action['completed']
                    and action['actorCellId'] != localPlayerCellId):
                cantSelect.append(action['championId'])

            if action['actorCellId'] != localPlayerCellId:
                continue

            if action['type'] != 'pick':
                continue

            if action['completed']:
                return

            # 现在亮着的英雄
            championIntent = action['championId']
            actionId = action['id']

    if not championIntent:
        return

    cantSelect.extend(bans)

    if championIntent not in cantSelect:
        await connector.selectChampion(actionId, championIntent, True)
        return True

    pos = next(filter(lambda x: x['cellId'] ==
               localPlayerCellId, data['myTeam']), None)
    pos = pos.get('assignedPosition')

    if pos == 'top':
        candidates = deepcopy(cfg.get(cfg.autoSelectChampionTop))
    elif pos == 'jungle':
        candidates = deepcopy(cfg.get(cfg.autoSelectChampionJug))
    elif pos == 'middle':
        candidates = deepcopy(cfg.get(cfg.autoSelectChampionMid))
    elif pos == 'bottom':
        candidates = deepcopy(cfg.get(cfg.autoSelectChampionBot))
    elif pos == 'utility':
        candidates = deepcopy(cfg.get(cfg.autoSelectChampionSup))
    else:
        candidates = []

    candidates.extend(cfg.get(cfg.autoSelectChampion))

    candidates = [x for x in candidates if x not in cantSelect]

    if len(candidates) == 0:
        return

    await connector.selectChampion(actionId, candidates[0], True)

    return True


async def autoBan(data, selection: ChampionSelection):
    """
    自动禁用英雄
    """
    isAutoBan = cfg.get(cfg.enableAutoBanChampion)

    if not isAutoBan or selection.isChampionBanned:
        return

    localPlayerCellId = data['localPlayerCellId']
    for actionGroup in data['actions']:
        for action in actionGroup:
            if (action["actorCellId"] == localPlayerCellId
                    and action['type'] == 'ban'
                    and action["isInProgress"]):

                pos = next(
                    filter(lambda x: x['cellId'] == localPlayerCellId, data['myTeam']), None)
                pos = pos.get('assignedPosition')

                if pos == 'top':
                    candidates = deepcopy(cfg.get(cfg.autoBanChampionTop))
                elif pos == 'jungle':
                    candidates = deepcopy(cfg.get(cfg.autoBanChampionJug))
                elif pos == 'middle':
                    candidates = deepcopy(cfg.get(cfg.autoBanChampionMid))
                elif pos == 'bottom':
                    candidates = deepcopy(cfg.get(cfg.autoBanChampionBot))
                elif pos == 'utility':
                    candidates = deepcopy(cfg.get(cfg.autoBanChampionSup))
                else:
                    candidates = []

                candidates.extend(cfg.get(cfg.autoBanChampion))

                bans = itertools.chain(data["bans"]['myTeamBans'],
                                       data["bans"]['theirTeamBans'])
                candidates = [x for x in candidates if x not in bans]

                # 给队友一点预选的时间
                await asyncio.sleep(cfg.get(cfg.autoBanDelay))

                isFriendly = cfg.get(cfg.pretentBan)
                if isFriendly:
                    myTeam = (await connector.getChampSelectSession()).get("myTeam")

                    if not myTeam:
                        return

                    intents = [player["championPickIntent"]
                               for player in myTeam]
                    candidates = [x for x in candidates if x not in intents]

                if not candidates:
                    return

                championId = candidates[0]
                await connector.banChampion(action['id'], championId, True)
                selection.isChampionBanned = True

                return True


async def autoSetSummonerSpell(data, selection: ChampionSelection):
    if selection.isSummonerSpellSetted:
        return False

    selection.isSummonerSpellSetted = True

    if not cfg.get(cfg.enableAutoSetSpells):
        return False

    cellId = data['localPlayerCellId']

    for player in data['myTeam']:
        if player['cellId'] != cellId:
            continue

        pos = player.get("assignedPosition", None)
        break

    if pos == 'top':
        spells = deepcopy(cfg.get(cfg.autoSetSummonerSpellTop))
    elif pos == 'jungle':
        spells = deepcopy(cfg.get(cfg.autoSetSummonerSpellJug))
    elif pos == 'middle':
        spells = deepcopy(cfg.get(cfg.autoSetSummonerSpellMid))
    elif pos == 'bottom':
        spells = deepcopy(cfg.get(cfg.autoSetSummonerSpellBot))
    elif pos == 'utility':
        spells = deepcopy(cfg.get(cfg.autoSetSummonerSpellSup))
    else:
        spells = [54, 54]

    if 54 in spells:
        spells = deepcopy(cfg.get(cfg.autoSetSummonerSpell))

    if 54 in spells:
        return False

    await connector.setSummonerSpells(spells[0], spells[1])


async def autoShow(data, selection: ChampionSelection):
    '''在 B/P 前展示英雄'''
    if selection.isChampionShowed:
        return

    if not cfg.get(cfg.enableAutoSelectChampion):
        return

    cellId = data['localPlayerCellId']

    for player in data['myTeam']:
        if player['cellId'] != cellId:
            continue

        if (player['championId'] != 0
                or player['championPickIntent'] != 0):
            selection.isChampionShowed = True
            return

        pos = player.get("assignedPosition", None)

        break

    if pos == 'top':
        candidates = deepcopy(cfg.get(cfg.autoSelectChampionTop))
    elif pos == 'jungle':
        candidates = deepcopy(cfg.get(cfg.autoSelectChampionJug))
    elif pos == 'middle':
        candidates = deepcopy(cfg.get(cfg.autoSelectChampionMid))
    elif pos == 'bottom':
        candidates = deepcopy(cfg.get(cfg.autoSelectChampionBot))
    elif pos == 'utility':
        candidates = deepcopy(cfg.get(cfg.autoSelectChampionSup))
    else:
        candidates = []

    default = deepcopy(cfg.get(cfg.autoSelectChampion))
    candidates.extend(default)

    if len(candidates) == 0:
        selection.isChampionShowed = True
        return

    championId = candidates[0]
    for actionGroup in reversed(data['actions']):
        for action in actionGroup:
            if (action['actorCellId'] == cellId and
                    action['type'] == 'pick'):

                await connector.selectChampion(action['id'], championId)
                selection.isChampionShowed = True

                return True


async def fixLCUWindowViaExe():
    zoom = await connector.getClientZoom()

    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", "app\\resource\\bin\\fix_lcu_window.exe", f"{zoom}", None, 0)
