import os
import json
import hashlib

import aiohttp
from async_lru import alru_cache

from app.common.logger import logger
from app.lol.static_data import (
    static_data, safeGetChampionName, safeGetChampionIcon,
    safeGetItemIcon, safeGetSummonerSpellIcon, safeGetRuneIcon,
    safeGetAugmentName, safeGetAugmentIcon,
)

TAG = "opgg"

_OPGG_AUGMENT_CACHE_DIR = os.path.join("app", "resource", "opgg", "augment icons")

_MODE_ALIAS = {
    'aram_mayhem': 'aram',
}

_RSC_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/x-component',
    'RSC': '1',
}


def _resolveMode(mode: str) -> str:
    return _MODE_ALIAS.get(mode, mode)


class Opgg:
    def __init__(self):
        self.apiSession = None
        self.webSession = None
        self._mayhemSlugCache = {}
        os.makedirs(_OPGG_AUGMENT_CACHE_DIR, exist_ok=True)

    async def start(self):
        if self.apiSession is None or self.apiSession.closed:
            self.apiSession = aiohttp.ClientSession("https://lol-api-champion.op.gg")
        if self.webSession is None or self.webSession.closed:
            self.webSession = aiohttp.ClientSession("https://www.op.gg")
        try:
            await static_data.ensure_loaded()
        except (aiohttp.ClientError, OSError, RuntimeError) as e:
            logger.debug(f"[{TAG}] static_data load skipped: {e}")

    async def close(self):
        if self.apiSession:
            await self.apiSession.close()
        if self.webSession:
            await self.webSession.close()

    @alru_cache(maxsize=512)
    async def __fetchTierList(self, region, mode, tier):
        url = f"/api/{region}/champions/{_resolveMode(mode)}"
        params = {"tier": tier}

        return await self.__getApi(url, params)

    @alru_cache(maxsize=512)
    async def __fetchChampionBuild(self, region, mode, championId, position, tier):
        resolved = _resolveMode(mode)
        if resolved != 'arena':
            url = f"/api/{region}/champions/{resolved}/{championId}/{position}"
        else:
            url = f"/api/{region}/champions/{resolved}/{championId}"

        params = {"tier": tier}

        return await self.__getApi(url, params)

    @alru_cache(maxsize=512)
    async def __fetchRsc(self, path):
        headers = dict(_RSC_HEADERS)
        headers['Next-Url'] = path
        timeout = aiohttp.ClientTimeout(total=20)
        try:
            async with self.webSession.get(path, headers=headers, ssl=False, proxy=None, timeout=timeout) as res:
                if res.status != 200:
                    body = await res.text()
                    from app.common.logger import logger
                    logger.warning(f"OPGG RSC {path} returned {res.status}: {body[:200]}", TAG)
                    return None
                return await res.text()
        except Exception as e:
            from app.common.logger import logger
            logger.warning(f"OPGG RSC {path} fetch failed: {e}", TAG)
            return None

    @alru_cache(maxsize=256)
    async def __fetchMayhemTierList(self):
        text = await self.__fetchRsc('/lol/modes/aram-mayhem')
        if not text:
            return None
        return _extractChampionTierFromRsc(text)

    @alru_cache(maxsize=512)
    async def __fetchMayhemAugments(self, champion_slug):
        en_path = f'/lol/modes/aram-mayhem/{champion_slug}/augments'
        zh_path = f'/zh-cn/lol/modes/aram-mayhem/{champion_slug}/augments'
        en_text = await self.__fetchRsc(en_path)
        zh_text = await self.__fetchRsc(zh_path)
        en_augs = _extractAugmentsFromRsc(en_text) if en_text else None
        zh_augs = _extractAugmentsFromRsc(zh_text) if zh_text else None
        if not en_augs:
            return None
        name_map = {}
        desc_map = {}
        if zh_augs:
            for a in zh_augs:
                if isinstance(a, dict):
                    aid = a.get('id')
                    if aid is not None:
                        n = a.get('name')
                        d = a.get('desc')
                        if n:
                            name_map[aid] = n
                        if d:
                            desc_map[aid] = d
        for a in en_augs:
            if isinstance(a, dict):
                aid = a.get('id')
                if aid is not None:
                    if aid in name_map:
                        a['name'] = name_map[aid]
                    if aid in desc_map:
                        a['desc'] = desc_map[aid]
        return en_augs

    async def __getMayhemChampionSlug(self, championId):
        if championId in self._mayhemSlugCache:
            return self._mayhemSlugCache[championId]

        tier_data = await self.__fetchMayhemTierList()
        if not tier_data:
            return None

        slug = None
        for cid, info in tier_data.items():
            self._mayhemSlugCache[cid] = info.get('key')
            if cid == championId:
                slug = info.get('key')

        return slug

    @alru_cache(maxsize=512)
    async def getChampionBuild(self, region, mode, championId, position, tier):
        positions = await self.getChampionPositions(region, championId, tier)
        resolved = _resolveMode(mode)
        if position not in positions and resolved == 'ranked':
            position = positions[0] if positions else 'none'

        raw = await self.__fetchChampionBuild(region, mode, championId, position, tier)
        if not isinstance(raw, dict):
            from app.common.logger import logger
            logger.warning(f"OPGG getChampionBuild unexpected response for {mode}/{region}/{championId}/{position}/{tier}: {type(raw)}", TAG)
            raise ConnectionError(f"OPGG champion build returned invalid data for {mode}/{championId}")

        if resolved == 'arena':
            res = await OpggDataParser.parseArenaChampionBuild(raw)
        else:
            res = await OpggDataParser.parseOtherChampionBuild(raw, position)

        if mode == 'aram_mayhem':
            augments = await self.__fetchMayhemAugmentsForChampion(championId)
            if augments:
                res['augments'] = augments
            mayhem_summary = await self.__fetchMayhemChampionSummary(championId)
            if mayhem_summary:
                res['summary']['tier'] = mayhem_summary.get('tier', res['summary'].get('tier'))
                res['summary']['rank'] = mayhem_summary.get('rank', res['summary'].get('rank'))
            res['perks'] = []

        return {
            'data': res,
            'version': (raw.get('meta') or {}).get('version', 'unknown'),
            'mode': mode,
        }

    async def __fetchMayhemAugmentsForChampion(self, championId):
        slug = await self.__getMayhemChampionSlug(championId)
        if not slug:
            return None
        raw_augs = await self.__fetchMayhemAugments(slug)
        if not raw_augs:
            return None
        icon_urls = set()
        aug_url_map = {}
        for aug in raw_augs:
            if isinstance(aug, dict):
                u = aug.get('largeIcon') or aug.get('smallIcon')
                if u:
                    icon_urls.add(u)
                    aug_url_map[aug.get('id')] = u
        icon_map = {}
        failed_urls = set()
        for u in icon_urls:
            local = await self.__downloadAugmentIcon(u)
            if local:
                icon_map[u] = local
            else:
                failed_urls.add(u)
        # 注册 augId -> OPGG 本地图标路径, 供战绩页面 safeGetAugmentIcon 使用
        # (OPGG 海克斯图标本身带稀有度颜色, 优于 LCU 默认图标)
        try:
            from app.lol.static_data import registerAugmentOpggIcon
            for aid, u in aug_url_map.items():
                if aid is None:
                    continue
                local = icon_map.get(u)
                if local:
                    registerAugmentOpggIcon(aid, local)
        except (OSError, KeyError, TypeError) as e:
            logger.debug(f"[{TAG}] augment icon register skipped: {e}")
        for aug in raw_augs:
            if not isinstance(aug, dict):
                continue
            aid = aug.get('id')
            u = aug_url_map.get(aid)
            if not u or u not in failed_urls:
                continue
            if aid is None:
                continue
            try:
                local = await safeGetAugmentIcon(aid)
                if local and os.path.exists(local):
                    icon_map[u] = local
            except Exception as e:
                from app.common.logger import logger
                logger.warning(f"Failed to get client augment icon for {aid}: {e}", TAG)
        return await OpggDataParser.parseAramMayhemAugments(raw_augs, icon_map)

    async def fetchMayhemAugmentRarities(self, championId):
        """公开方法: 拉取指定英雄的海克斯强化列表, 返回 [(augId, rarity_str), ...]

        用于战绩页面 AugmentRow 获取 rarity 并着色边框.
        rarity 是全局固定的, 拉取一次即可缓存.
        """
        try:
            groups = await self.__fetchMayhemAugmentsForChampion(championId)
            if not groups or not isinstance(groups, list):
                return []
            rarity_names = ['silver', 'gold', 'prismatic']
            result = []
            for idx, group in enumerate(groups):
                if idx >= len(rarity_names) or not isinstance(group, list):
                    continue
                for aug in group:
                    if isinstance(aug, dict) and aug.get('id') is not None:
                        result.append((aug['id'], rarity_names[idx]))
            return result
        except Exception as e:
            from app.common.logger import logger
            logger.warning(f"fetchMayhemAugmentRarities failed: {e}", TAG)
            return []

    async def __fetchMayhemChampionSummary(self, championId):
        tier_data = await self.__fetchMayhemTierList()
        if not tier_data:
            return None
        return tier_data.get(championId)

    @alru_cache(maxsize=512)
    async def getTierList(self, region, mode, tier):
        if mode == 'aram_mayhem':
            raw = await self.__fetchMayhemTierList()
            if raw:
                # RSC 响应只含 tier/rank, 不含 win_rate/pick_rate/kda,
                # 用普通大乱斗 API 数据补充这些字段
                try:
                    aram_raw = await self.__fetchTierList(region, 'aram', tier)
                    if isinstance(aram_raw, dict):
                        for item in (aram_raw.get('data') or []):
                            if not isinstance(item, dict):
                                continue
                            cid = item.get('id')
                            if cid is None or cid not in raw:
                                continue
                            stats = item.get('average_stats') or {}
                            if raw[cid].get('win_rate') is None:
                                raw[cid]['win_rate'] = stats.get('win_rate')
                            if raw[cid].get('pick_rate') is None:
                                raw[cid]['pick_rate'] = stats.get('pick_rate')
                            if raw[cid].get('kda') is None:
                                raw[cid]['kda'] = stats.get('kda')
                except Exception as e:
                    from app.common.logger import logger
                    logger.warning(f"Failed to supplement aram_mayhem with aram stats: {e}", TAG)

                res = await OpggDataParser.parseMayhemTierList(raw)
                return {'data': res, 'version': 'latest'}
            return {'data': [], 'version': 'unknown'}

        raw = await self.__fetchTierList(region, mode, tier)
        if not isinstance(raw, dict):
            from app.common.logger import logger
            logger.warning(f"OPGG getTierList unexpected response type for {mode}/{region}/{tier}: {type(raw)}", TAG)
            return {'data': [] if _resolveMode(mode) != 'ranked' else {p: [] for p in ['TOP', 'JUNGLE', 'MID', 'ADC', 'SUPPORT']}, 'version': 'unknown'}

        version = (raw.get('meta') or {}).get('version', 'unknown')

        if _resolveMode(mode) == 'ranked':
            res = await OpggDataParser.parseRankedTierList(raw)
        else:
            res = await OpggDataParser.parseOtherTierList(raw)

        return {
            'data': res,
            'version': version
        }

    @alru_cache(maxsize=512)
    async def getChampionPositions(self, region, championId, tier):
        data = await self.__fetchTierList(region, "ranked", tier)

        for item in (data.get('data') or []):
            if item.get('id') == championId:
                positions = item.get('positions') or []
                return [p.get('name') for p in positions if p.get('name')]

        return []

    async def __getApi(self, url, params=None):
        timeout = aiohttp.ClientTimeout(total=15)
        async with self.apiSession.get(url, params=params, ssl=False, proxy=None, timeout=timeout) as res:
            if res.status != 200:
                body = await res.text()
                raise ConnectionError(
                    f"OPGG API {url} returned {res.status}: {body[:200]}")
            return await res.json()

    async def __downloadAugmentIcon(self, url):
        if not url:
            return None
        os.makedirs(_OPGG_AUGMENT_CACHE_DIR, exist_ok=True)
        fname = hashlib.md5(url.encode('utf-8')).hexdigest() + ".png"
        fpath = os.path.join(_OPGG_AUGMENT_CACHE_DIR, fname)
        if os.path.exists(fpath):
            return fpath
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with self.webSession.get(url, ssl=False, proxy=None, timeout=timeout) as res:
                if res.status != 200:
                    return None
                data = await res.read()
                with open(fpath, 'wb') as f:
                    f.write(data)
                return fpath
        except Exception as e:
            from app.common.logger import logger
            logger.warning(f"Failed to download OPGG augment icon {url}: {e}", TAG)
            return None


def _extractJsonArray(text, marker, max_scan=200000):
    idx = text.find(marker)
    if idx < 0:
        return None
    start = text.find('[', idx)
    if start < 0 or start - idx > max_scan:
        return None
    depth = 0
    in_string = False
    escape = False
    end = start
    for j in range(start, min(start + max_scan, len(text))):
        c = text[j]
        if escape:
            escape = False
            continue
        if c == '\\':
            escape = True
            continue
        if c == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == '[':
            depth += 1
        elif c == ']':
            depth -= 1
            if depth == 0:
                end = j + 1
                break
    try:
        return json.loads(text[start:end])
    except (json.JSONDecodeError, ValueError):
        return None


def _extractChampionTierFromRsc(text):
    arr = _extractJsonArray(text, '"champions":[')
    if not arr:
        arr = _extractJsonArray(text, '"champion_id"')
    if not arr:
        return {}

    result = {}
    for item in arr:
        if not isinstance(item, dict):
            continue
        cid = item.get('champion_id') or item.get('id')
        if cid is None:
            continue
        result[cid] = {
            'key': item.get('key'),
            'name': item.get('name'),
            'tier': item.get('tier'),
            'rank': item.get('rank'),
            'image_url': item.get('image_url'),
            'win_rate': item.get('win_rate'),
            'pick_rate': item.get('pick_rate'),
            'play': item.get('play'),
            'win': item.get('win'),
            'kda': item.get('kda'),
        }
    return result


def _extractAugmentsFromRsc(text):
    idx = 0
    while True:
        pos = text.find('"data":[', idx)
        if pos < 0:
            return None
        arr = _extractJsonArrayAt(text, pos)
        if arr and isinstance(arr, list) and len(arr) > 0:
            first = arr[0]
            if isinstance(first, dict) and 'popular' in first and 'performance' in first:
                return arr
        idx = pos + 1
    return None


def _extractJsonArrayAt(text, pos):
    start = text.find('[', pos)
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for j in range(start, min(start + 200000, len(text))):
        c = text[j]
        if escape:
            escape = False
            continue
        if c == '\\':
            escape = True
            continue
        if c == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == '[':
            depth += 1
        elif c == ']':
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:j+1])
                except (json.JSONDecodeError, ValueError):
                    return None
    return None


class OpggDataParser:

    @staticmethod
    async def parseRankedTierList(data):
        data = data.get('data') or []
        res = {p: []
               for p in ['TOP', 'JUNGLE', 'MID', 'ADC', 'SUPPORT']}

        for item in data:
            championId = item['id']
            name = await safeGetChampionName(championId)
            icon = await safeGetChampionIcon(championId)

            positions = item.get('positions') or []
            for p in positions:
                position = p.get('name')
                stats = p.get('stats') or {}
                tier = stats.get('tier_data') or {}

                counters = []
                for c in (p.get('counters') or []):
                    cid = c.get('champion_id')
                    if cid is None:
                        continue
                    counters.append({
                        'championId': cid,
                        'icon': await safeGetChampionIcon(cid)
                    })

                res[position].append({
                    'championId': championId,
                    'name': name,
                    'icon': icon,
                    'winRate': stats.get('win_rate'),
                    'pickRate': stats.get('pick_rate'),
                    'banRate': stats.get('ban_rate'),
                    'kda': stats.get('kda'),
                    'tier': tier.get('tier'),
                    'rank': tier.get('rank'),
                    'position': position,
                    'counters': counters,
                })

        for tier in res.values():
            tier.sort(key=lambda x: (x['rank'] is None, x['rank']))

        return res

    @staticmethod
    async def parseOtherTierList(data):
        data = data.get('data') or []
        res = []

        for item in data:
            stats = item.get('average_stats')

            if stats is None:
                continue

            if stats.get('rank') is None:
                continue

            championId = item['id']
            name = await safeGetChampionName(championId)
            icon = await safeGetChampionIcon(championId)

            res.append({
                'championId': championId,
                'name': name,
                'icon': icon,
                'winRate': stats.get('win_rate'),
                'pickRate': stats.get('pick_rate'),
                'banRate': stats.get('ban_rate'),
                'kda': stats.get('kda'),
                'tier': stats.get('tier'),
                'rank': stats.get('rank'),
                "position": None,
                'counters': [],
            })

        return sorted(res, key=lambda x: (x['rank'] is None, x['rank']))

    @staticmethod
    async def parseMayhemTierList(raw):
        res = []
        for cid, info in raw.items():
            championId = cid
            cname = await safeGetChampionName(championId)
            name = cname or info.get('name', '')
            icon = await safeGetChampionIcon(championId)
            res.append({
                'championId': championId,
                'name': name,
                'icon': icon,
                'winRate': info.get('win_rate'),
                'pickRate': info.get('pick_rate'),
                'banRate': None,
                'kda': info.get('kda'),
                'tier': info.get('tier'),
                'rank': info.get('rank'),
                'position': None,
                'counters': [],
            })
        return sorted(res, key=lambda x: (x['rank'] is None, x['rank']))

    @staticmethod
    async def parseOtherChampionBuild(data, position):
        data = data.get('data') or {}

        summary = data.get('summary') or {}
        championId = summary.get('id')
        icon = await safeGetChampionIcon(championId) if championId else None
        name = (await safeGetChampionName(championId)) if championId else ""

        stats = None
        if position != 'none':
            positions = summary.get('positions') or []
            for p in positions:
                if p.get('name') == position:
                    stats = p.get('stats') or {}
                    break
            if stats is None:
                stats = summary.get('average_stats') or {}
        else:
            stats = summary.get('average_stats') or {}

        winRate = stats.get('win_rate')
        pickRate = stats.get('pick_rate')
        banRate = stats.get('ban_rate')
        kda = stats.get('kda')
        tierData = stats.get('tier_data') or {}
        tier = tierData.get("tier") if tierData else stats.get("tier")
        rank = tierData.get("rank") if tierData else stats.get("rank")

        summonerSpells = []
        for s in (data.get('summoner_spells') or []):
            ids = s.get('ids') or []
            icons = [await safeGetSummonerSpellIcon(id) for id in ids]
            summonerSpells.append({
                'ids': ids,
                'icons': icons,
                'win': s.get('win'),
                'play': s.get('play'),
                'pickRate': s.get('pick_rate')
            })

        skill_masteries = data.get('skill_masteries') or []
        skills_data = data.get('skills') or []
        skills = {}
        if skill_masteries and skills_data:
            sm0 = skill_masteries[0]
            sk0 = skills_data[0]
            skills = {
                "masteries": sm0.get('ids', []),
                "order": sk0.get('order', []),
                'play': sk0.get('play'),
                'win': sk0.get('win'),
                'pickRate': sk0.get('pick_rate')
            }

        async def _safeItems(key, limit):
            result = []
            for i in (data.get(key) or [])[:limit]:
                ids = i.get('ids') or []
                icons = [await safeGetItemIcon(id) for id in ids]
                result.append({
                    "icons": icons,
                    "play": i.get('play'),
                    "win": i.get('win'),
                    'pickRate': i.get('pick_rate')
                })
            return result

        boots = await _safeItems('boots', 3)
        startItems = await _safeItems('starter_items', 3)
        coreItems = await _safeItems('core_items', 5)

        lastItems = []
        for i in (data.get('last_items') or [])[:16]:
            ids = i.get('ids') or []
            if ids:
                lastItems.append(await safeGetItemIcon(ids[0]))

        strongAgainst = []
        weakAgainst = []

        for c in (data.get('counters') or []):
            play = c.get('play', 0)
            win = c.get('win', 0)
            win_rate_c = (win / play) if play > 0 else 0
            arr = strongAgainst if win_rate_c >= 0.5 else weakAgainst

            cid = c.get('champion_id')
            if cid is None:
                continue
            arr.append({
                'championId': cid,
                'name': await safeGetChampionName(cid),
                'icon': await safeGetChampionIcon(cid),
                'play': play,
                'win': win,
                'winRate': win_rate_c
            })

        strongAgainst.sort(key=lambda x: -x['winRate'])
        weakAgainst.sort(key=lambda x: x['winRate'])

        perks = []
        for perk in (data.get('runes') or []):
            mainId = perk.get('primary_page_id')
            subId = perk.get('secondary_page_id')
            perkIds = (perk.get('primary_rune_ids') or []) + \
                (perk.get('secondary_rune_ids') or []) + \
                (perk.get('stat_mod_ids') or [])
            perks.append({
                'primaryId': mainId,
                "primaryIcon": await safeGetRuneIcon(mainId) if mainId else None,
                'secondaryId': subId,
                "secondaryIcon": await safeGetRuneIcon(subId) if subId else None,
                'perks': perkIds,
                "icons": [await safeGetRuneIcon(id) for id in perkIds],
                'play': perk.get('play'),
                'win': perk.get('win'),
                'pickRate': perk.get('pick_rate'),
            })

        return {
            "summary": {
                'name': name,
                'championId': championId,
                'icon': icon,
                'position': position,
                'winRate': winRate,
                'pickRate': pickRate,
                'banRate': banRate,
                'kda': kda,
                'tier': tier,
                'rank': rank
            },
            "summonerSpells": summonerSpells,
            "championSkills": skills,
            "items": {
                "boots": boots,
                "startItems": startItems,
                "coreItems": coreItems,
                "lastItems": lastItems,
            },
            "counters": {
                "strongAgainst": strongAgainst,
                "weakAgainst": weakAgainst,
            },
            "perks": perks,
        }

    @staticmethod
    async def parseAramMayhemAugments(raw_augs, icon_map=None):
        icon_map = icon_map or {}
        groups = [[], [], []]
        for aug in raw_augs:
            if not isinstance(aug, dict):
                continue
            rarity = aug.get('rarity') or 0
            if rarity & 1:
                tier_idx = 0
            elif rarity & 4:
                tier_idx = 1
            elif rarity & 8:
                tier_idx = 2
            else:
                continue

            popular = aug.get('popular', 0) or 0
            if popular <= 0:
                continue

            icon_url = aug.get('largeIcon') or aug.get('smallIcon')
            icon_local = icon_map.get(icon_url) if icon_url else None
            name = aug.get('name', '')
            performance = aug.get('performance', 0) or 0
            aid = aug.get('id')
            if aid is not None and not any('\u4e00' <= ch <= '\u9fff' for ch in (name or '')):
                cn_name = await safeGetAugmentName(aid)
                if cn_name and any('\u4e00' <= ch <= '\u9fff' for ch in cn_name):
                    name = cn_name

            groups[tier_idx].append({
                'id': aid,
                'name': name,
                'icon': icon_local,
                'iconIsUrl': False,
                'play': 0,
                'firstPlace': 0,
                'pickRate': popular,
                'winRate': performance,
                'desc': aug.get('desc', ''),
                'tooltip': aug.get('tooltip', ''),
                'rarity': rarity,
            })
            # 注册强化稀有度, 供战绩页面 AugmentRow 着色边框使用
            if aid is not None:
                try:
                    from app.lol.static_data import registerAugmentRarity
                    registerAugmentRarity(aid, rarity)
                except (ImportError, AttributeError, TypeError) as e:
                    logger.debug(f"[{TAG}] augment rarity register skipped: {e}")

        for g in groups:
            g.sort(key=lambda x: -x.get('pickRate', 0))

        return groups

    @staticmethod
    async def parseArenaChampionBuild(data):
        data = data.get('data') or {}

        summary = data.get('summary') or {}
        championId = summary.get('id')
        name = (await safeGetChampionName(championId)) if championId else ""
        icon = await safeGetChampionIcon(championId) if championId else None

        stats = summary.get('average_stats') or {}
        play = stats.get('play', 0) or 0
        win = stats.get('win', 0) or 0
        first = stats.get('first_place', 0) or 0
        total_place = stats.get('total_place', 0) or 0
        winRate = (win / play) if play > 0 else 0
        firstRate = (first / play) if play > 0 else 0
        averagePlace = (total_place / play) if play > 0 else 0
        pickRate = stats.get('pick_rate')
        banRate = stats.get('ban_rate')
        tier = stats.get('tier')

        skill_masteries = data.get('skill_masteries') or []
        skills_data = data.get('skills') or []
        skills = {}
        if skill_masteries and skills_data:
            sm0 = skill_masteries[0]
            sk0 = skills_data[0]
            skills = {
                "masteries": sm0.get('ids', []),
                "order": sk0.get('order', []),
                'play': sk0.get('play'),
                'win': sk0.get('win'),
                'pickRate': sk0.get('pick_rate')
            }

        async def _safeArenaItems(key, limit):
            result = []
            for i in (data.get(key) or [])[:limit]:
                ids = i.get('ids') or []
                icons = [await safeGetItemIcon(id) for id in ids]
                i_play = i.get('play', 0) or 0
                i_win = i.get('win', 0) or 0
                i_first = i.get('first_place', 0) or 0
                i_total = i.get('total_place', 0) or 0
                result.append({
                    "icons": icons,
                    "play": i_play,
                    "win": i_win,
                    'pickRate': i.get('pick_rate'),
                    "averagePlace": (i_total / i_play) if i_play > 0 else 0,
                    "firstRate": (i_first / i_play) if i_play > 0 else 0,
                })
            return result

        boots = await _safeArenaItems('boots', 3)
        startItems = await _safeArenaItems('starter_items', 3)
        coreItems = await _safeArenaItems('core_items', 5)
        prismItems = await _safeArenaItems('prism_items', 5)

        lastItems = []
        for i in (data.get('last_items') or [])[:16]:
            ids = i.get('ids') or []
            if ids:
                lastItems.append(await safeGetItemIcon(ids[0]))

        augments = []
        for group in (data.get('augment_group') or []):
            arr = []
            for aug in (group.get('augments') or []):
                augId = aug.get('id')
                if augId is None:
                    continue
                a_play = aug.get('play', 0) or 0
                a_win = aug.get('win', 0) or 0
                a_first = aug.get('first_place', 0) or 0
                a_total = aug.get('total_place', 0) or 0
                arr.append({
                    "id": augId,
                    "icon": await safeGetAugmentIcon(augId),
                    "name": await safeGetAugmentName(augId),
                    "win": a_win,
                    'play': a_play,
                    "totalPlace": a_total,
                    "firstPlace": a_first,
                    'pickRate': aug.get('pick_rate'),
                    "averagePlace": (a_total / a_play) if a_play > 0 else 0,
                    "firstRate": (a_first / a_play) if a_play > 0 else 0,
                })
            augments.append(arr)

        synergies = []
        for syn in (data.get('synergies') or []):
            chId = syn.get('champion_id')
            if chId is None:
                continue
            s_play = syn.get('play', 0) or 0
            s_win = syn.get('win', 0) or 0
            s_first = syn.get('first_place', 0) or 0
            s_total = syn.get('total_place', 0) or 0
            synergies.append({
                "championId": chId,
                'icon': await safeGetChampionIcon(chId),
                "name": await safeGetChampionName(chId),
                "win": s_win,
                'play': s_play,
                "totalPlace": s_total,
                "firstPlace": s_first,
                'pickRate': syn.get('pick_rate'),
                "averagePlace": (s_total / s_play) if s_play > 0 else 0,
                "firstRate": (s_first / s_play) if s_play > 0 else 0,
            })

        return {
            "summary": {
                "name": name,
                "icon": icon,
                "championId": championId,
                "play": play,
                "winRate": winRate,
                "firstRate": firstRate,
                "averagePlace": averagePlace,
                "pickRate": pickRate,
                "banRate": banRate,
                "tier": tier,
                "position": "none"
            },
            "championSkills": skills,
            "items": {
                "boots": boots,
                "startItems": startItems,
                "coreItems": coreItems,
                "lastItems": lastItems,
                "prismItems": prismItems,
            },
            "augments": augments,
            "synergies": synergies,
        }


opgg = Opgg()
