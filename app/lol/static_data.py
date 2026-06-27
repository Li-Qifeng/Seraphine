import os
import json
import asyncio
import aiohttp
from typing import Optional

from app.common.config import LOCAL_PATH
from app.common.logger import logger

TAG = "StaticData"

CDN_HERO_LIST = 'https://game.gtimg.cn/images/lol/act/img/js/heroList/hero_list.js'
CDN_CHAMP_ICON = 'https://game.gtimg.cn/images/lol/act/img/champion/{alias}.png'
CDN_ITEM_ICON = 'https://game.gtimg.cn/images/lol/act/img/item/{id}.png'
CDN_SPELL_ICON_BY_KEY = 'https://game.gtimg.cn/images/lol/act/img/spell/{spell_key}.png'
CDN_SUMMONER_SPELL_BY_ID = None
CDN_RUNE_ICON = 'https://game.gtimg.cn/images/lol/act/img/rune/{id}.png'

GAME_DATA_DIR = "app/resource/game"

SUMMONER_SPELL_ID_TO_KEY = {
    1: "SummonerBoost",
    3: "SummonerExhaust",
    4: "SummonerFlash",
    6: "SummonerHaste",
    7: "SummonerHeal",
    11: "SummonerSmite",
    12: "SummonerTeleport",
    13: "SummonerMana",
    14: "SummonerDot",
    21: "SummonerBarrier",
    30: "SummonerPoroRecall",
    31: "SummonerPoroThrow",
    32: "SummonerSnowball",
}


def _is_connector_available():
    try:
        from app.lol.connector import connector
        return connector.manager is not None and connector.lcuSess is not None
    except (ImportError, AttributeError):
        return False


class StaticData:
    _instance = None
    _lock = asyncio.Lock()

    def __init__(self):
        self.champions = {}
        self.version = None
        self._loaded = False
        self._session: Optional[aiohttp.ClientSession] = None
        self.cfg_path = f"{LOCAL_PATH}/StaticChampions.json"

    @classmethod
    def instance(cls) -> "StaticData":
        if cls._instance is None:
            cls._instance = StaticData()
        return cls._instance

    async def ensure_loaded(self):
        if self._loaded and self.champions:
            return
        async with self._lock:
            if self._loaded and self.champions:
                return
            await self._load()

    async def _load(self):
        self.champions = {}
        if os.path.exists(self.cfg_path):
            try:
                with open(self.cfg_path, 'r', encoding='utf-8') as f:
                    cached = json.load(f)
                self.champions = cached.get('champions', {})
                self.version = cached.get('version')
                if self.champions:
                    self._loaded = True
            except Exception as e:
                logger.warning(f"Failed to load static champions cache: {e}", TAG)
        try:
            await self._refresh()
        except Exception as e:
            logger.warning(f"Failed to refresh static data from CDN: {e}", TAG)
        self._loaded = True

    async def _get_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _refresh(self):
        s = await self._get_session()
        async with s.get(CDN_HERO_LIST, proxy=None, ssl=False, timeout=aiohttp.ClientTimeout(total=15)) as res:
            if res.status != 200:
                return
            text = await res.text()
        d = json.loads(text)
        version = d.get('version')
        champs = {}
        for h in d.get('hero', []):
            try:
                cid = int(h['heroId'])
                champs[cid] = {
                    'name': h.get('name', ''),
                    'title': h.get('title', ''),
                    'alias': h.get('alias', ''),
                    'display_name': h.get('title', '') or h.get('name', ''),
                }
            except (KeyError, ValueError):
                continue
        if champs:
            self.champions = champs
            self.version = version
            try:
                os.makedirs(LOCAL_PATH, exist_ok=True)
                with open(self.cfg_path, 'w', encoding='utf-8') as f:
                    json.dump({'champions': champs, 'version': version}, f, ensure_ascii=False)
            except Exception as e:
                logger.warning(f"Failed to save static data cache: {e}", TAG)

    def getChampionNameById(self, championId) -> Optional[str]:
        cid = int(championId) if championId is not None else None
        if cid in self.champions:
            c = self.champions[cid]
            return c.get('display_name') or c.get('name')
        return None

    async def getChampionIcon(self, championId) -> str:
        cid = int(championId) if championId is not None else -1
        if cid in (-1, 0):
            return "app/resource/images/champion-0.png"
        folder = os.path.join(GAME_DATA_DIR, "champion icons")
        os.makedirs(folder, exist_ok=True)
        local = os.path.join(folder, f"{cid}.png")
        if os.path.exists(local) and os.path.getsize(local) > 0:
            return local
        alias = self.champions.get(cid, {}).get('alias')
        if not alias:
            await self.ensure_loaded()
            alias = self.champions.get(cid, {}).get('alias')
        if alias:
            url = CDN_CHAMP_ICON.format(alias=alias)
            try:
                s = await self._get_session()
                async with s.get(url, proxy=None, ssl=False, timeout=aiohttp.ClientTimeout(total=15)) as r:
                    if r.status == 200:
                        data = await r.read()
                        with open(local, 'wb') as f:
                            f.write(data)
                        return local
            except Exception as e:
                logger.warning(f"Failed to download champ icon for {cid}/{alias}: {e}", TAG)
        return "app/resource/images/champion-0.png"

    async def getItemIcon(self, iconId) -> str:
        if iconId == 0:
            return "app/resource/images/item-0.png"
        folder = os.path.join(GAME_DATA_DIR, "item icons")
        os.makedirs(folder, exist_ok=True)
        local = os.path.join(folder, f"{iconId}.png")
        if os.path.exists(local) and os.path.getsize(local) > 0:
            return local
        url = CDN_ITEM_ICON.format(id=iconId)
        try:
            s = await self._get_session()
            async with s.get(url, proxy=None, ssl=False, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status == 200:
                    data = await r.read()
                    if len(data) > 100:
                        with open(local, 'wb') as f:
                            f.write(data)
                        return local
        except Exception as e:
            logger.warning(f"Failed to download item icon for {iconId}: {e}", TAG)
        return "app/resource/images/item-0.png"

    async def getSummonerSpellIcon(self, spellId) -> str:
        folder = os.path.join(GAME_DATA_DIR, "summoner spell icons")
        os.makedirs(folder, exist_ok=True)
        local = os.path.join(folder, f"{spellId}.png")
        if os.path.exists(local) and os.path.getsize(local) > 0:
            return local
        key = SUMMONER_SPELL_ID_TO_KEY.get(int(spellId))
        if not key:
            return "app/resource/images/spell-0.png" if os.path.exists("app/resource/images/spell-0.png") else ""
        url = CDN_SPELL_ICON_BY_KEY.format(spell_key=key)
        try:
            s = await self._get_session()
            async with s.get(url, proxy=None, ssl=False, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status == 200:
                    data = await r.read()
                    if len(data) > 100:
                        with open(local, 'wb') as f:
                            f.write(data)
                        return local
        except Exception as e:
            logger.warning(f"Failed to download spell icon for {spellId}/{key}: {e}", TAG)
        return ""

    async def getRuneIcon(self, runeId) -> str:
        if runeId == 0:
            return "app/resource/images/rune-0.png"
        folder = os.path.join(GAME_DATA_DIR, "rune icons")
        os.makedirs(folder, exist_ok=True)
        local = os.path.join(folder, f"{runeId}.png")
        if os.path.exists(local) and os.path.getsize(local) > 0:
            return local
        url = CDN_RUNE_ICON.format(id=runeId)
        try:
            s = await self._get_session()
            async with s.get(url, proxy=None, ssl=False, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status == 200:
                    data = await r.read()
                    if len(data) > 100:
                        with open(local, 'wb') as f:
                            f.write(data)
                        return local
        except Exception as e:
            logger.warning(f"Failed to download rune icon for {runeId}: {e}", TAG)
        return ""

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None


static_data = StaticData.instance()

# 强化 ID -> 稀有度 ("silver" / "gold" / "prismatic")
# 由 OPGG aram-mayhem 数据解析时填充, 战绩页面 AugmentRow 据此着色边框
# 持久化到本地文件, 避免每次重启都要重新拉取
_augment_rarity_map: dict = {}
_AUGMENT_RARITY_CACHE = f"{LOCAL_PATH}/AugmentRarity.json"

# 强化 ID -> OPGG 海克斯强化本地图标路径
# OPGG 的海克斯图标本身带稀有度颜色, 优先使用; 持久化避免重复下载
_augment_opgg_icon_map: dict = {}
_AUGMENT_OPGG_ICON_CACHE = f"{LOCAL_PATH}/AugmentOpggIcon.json"


def _loadAugmentOpggIconCache():
    global _augment_opgg_icon_map
    try:
        if os.path.exists(_AUGMENT_OPGG_ICON_CACHE):
            with open(_AUGMENT_OPGG_ICON_CACHE, 'r', encoding='utf-8') as f:
                cached = json.load(f)
            if isinstance(cached, dict):
                _augment_opgg_icon_map = {int(k): v for k, v in cached.items()}
    except Exception as e:
        logger.warning(f"Failed to load augment opgg icon cache: {e}", TAG)


def _saveAugmentOpggIconCache():
    try:
        os.makedirs(LOCAL_PATH, exist_ok=True)
        data = {str(k): v for k, v in _augment_opgg_icon_map.items()}
        with open(_AUGMENT_OPGG_ICON_CACHE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"Failed to save augment opgg icon cache: {e}", TAG)


def registerAugmentOpggIcon(augId, iconPath):
    """注册强化 ID -> OPGG 本地图标路径 (由 opgg.py 下载图标后调用)"""
    if augId is None or not iconPath:
        return
    try:
        augId = int(augId)
    except (TypeError, ValueError):
        return
    if _augment_opgg_icon_map.get(augId) != iconPath:
        _augment_opgg_icon_map[augId] = iconPath
        _saveAugmentOpggIconCache()


def getAugmentOpggIconPath(augId):
    """返回已缓存的 OPGG 海克斯强化本地图标路径, 无则返回 ''"""
    if augId is None:
        return ''
    try:
        augId = int(augId)
    except (TypeError, ValueError):
        return ''
    if not _augment_opgg_icon_map and os.path.exists(_AUGMENT_OPGG_ICON_CACHE):
        _loadAugmentOpggIconCache()
    return _augment_opgg_icon_map.get(augId, '')


def _loadAugmentRarityCache():
    """从本地缓存加载 rarity 映射"""
    global _augment_rarity_map
    try:
        if os.path.exists(_AUGMENT_RARITY_CACHE):
            with open(_AUGMENT_RARITY_CACHE, 'r', encoding='utf-8') as f:
                cached = json.load(f)
            if isinstance(cached, dict):
                # JSON key 是字符串, 转回 int
                _augment_rarity_map = {int(k): v for k, v in cached.items()}
    except Exception as e:
        logger.warning(f"Failed to load augment rarity cache: {e}", TAG)


def _saveAugmentRarityCache():
    """保存 rarity 映射到本地缓存"""
    try:
        os.makedirs(LOCAL_PATH, exist_ok=True)
        # key 转字符串以兼容 JSON
        data = {str(k): v for k, v in _augment_rarity_map.items()}
        with open(_AUGMENT_RARITY_CACHE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"Failed to save augment rarity cache: {e}", TAG)


def registerAugmentRarity(augId, rarity):
    """注册强化稀有度 (由 opgg.py 解析时调用)

    rarity 可为位掩码 (OPGG 格式: &1=silver, &4=gold, &8=prismatic)
    或字符串 ('silver'/'gold'/'prismatic')
    """
    if augId is None:
        return
    # 确保 key 是 int
    try:
        augId = int(augId)
    except (TypeError, ValueError):
        return

    new_rarity = None
    if isinstance(rarity, str):
        r = rarity.lower()
        if r in ('silver', 'gold', 'prismatic'):
            new_rarity = r
    else:
        try:
            r = int(rarity)
        except (TypeError, ValueError):
            return
        if r & 1:
            new_rarity = 'silver'
        elif r & 4:
            new_rarity = 'gold'
        elif r & 8:
            new_rarity = 'prismatic'

    if new_rarity:
        # 只在有变化时更新并保存 (避免频繁写文件)
        if _augment_rarity_map.get(augId) != new_rarity:
            _augment_rarity_map[augId] = new_rarity
            _saveAugmentRarityCache()


async def safeGetAugmentRarity(augId):
    """返回强化稀有度 ('silver'/'gold'/'prismatic'), 未知返回 ''"""
    if augId is None:
        return ''
    try:
        augId = int(augId)
    except (TypeError, ValueError):
        return ''

    # 启动时加载本地缓存 (懒加载)
    if not _augment_rarity_map and os.path.exists(_AUGMENT_RARITY_CACHE):
        _loadAugmentRarityCache()

    r = _augment_rarity_map.get(augId)
    if r:
        return r
    # 回退: 尝试从 LCU cherry-augments 读取 rarity 字段
    if _is_connector_available():
        try:
            from app.lol.connector import connector
            raw = connector.manager.cherryAugments.get(augId)
            if raw and isinstance(raw, dict):
                rarity = raw.get('rarity')
                if rarity is not None:
                    registerAugmentRarity(augId, rarity)
                    return _augment_rarity_map.get(augId, '')
        except (AttributeError, TypeError, KeyError) as e:
            logger.debug(f"[{TAG}] getAugmentRarity fallback: {e}")
    return ''


async def safeGetChampionName(championId):
    if _is_connector_available():
        try:
            from app.lol.connector import connector
            name = connector.manager.getChampionNameById(championId)
            if name:
                return name
        except (AttributeError, TypeError, KeyError) as e:
            logger.debug(f"[{TAG}] getChampionName fallback: {e}")
    await static_data.ensure_loaded()
    return static_data.getChampionNameById(championId) or ''


async def safeGetChampionIcon(championId):
    if _is_connector_available():
        try:
            from app.lol.connector import connector
            return await connector.getChampionIcon(championId)
        except (AttributeError, TypeError, KeyError, aiohttp.ClientError) as e:
            logger.debug(f"[{TAG}] getChampionIcon fallback: {e}")
    await static_data.ensure_loaded()
    return await static_data.getChampionIcon(championId)


async def safeGetItemIcon(iconId):
    if _is_connector_available():
        try:
            from app.lol.connector import connector
            return await connector.getItemIcon(iconId)
        except (AttributeError, TypeError, KeyError, aiohttp.ClientError) as e:
            logger.debug(f"[{TAG}] getItemIcon fallback: {e}")
    return await static_data.getItemIcon(iconId)


async def safeGetSummonerSpellIcon(spellId):
    if _is_connector_available():
        try:
            from app.lol.connector import connector
            return await connector.getSummonerSpellIcon(spellId)
        except (AttributeError, TypeError, KeyError, aiohttp.ClientError) as e:
            logger.debug(f"[{TAG}] getSummonerSpellIcon fallback: {e}")
    return await static_data.getSummonerSpellIcon(spellId)


async def safeGetRuneIcon(runeId):
    if _is_connector_available():
        try:
            from app.lol.connector import connector
            return await connector.getRuneIcon(runeId)
        except (AttributeError, TypeError, KeyError, aiohttp.ClientError) as e:
            logger.debug(f"[{TAG}] getRuneIcon fallback: {e}")
    return await static_data.getRuneIcon(runeId)


async def safeGetAugmentName(augId):
    if _is_connector_available():
        try:
            from app.lol.connector import connector
            name = connector.manager.getAugmentsName(augId)
            if name:
                return name
        except (AttributeError, TypeError, KeyError) as e:
            logger.debug(f"[{TAG}] getAugmentName fallback: {e}")
    return ''


async def safeGetAugmentIcon(augId):
    # 优先使用 OPGG 海克斯强化图标 (图标本身带稀有度颜色)
    if augId is not None:
        try:
            augId_int = int(augId)
        except (TypeError, ValueError):
            augId_int = None
        if augId_int is not None:
            if not _augment_opgg_icon_map and os.path.exists(_AUGMENT_OPGG_ICON_CACHE):
                _loadAugmentOpggIconCache()
            opgg_icon = _augment_opgg_icon_map.get(augId_int)
            if opgg_icon and os.path.exists(opgg_icon):
                return opgg_icon
    if _is_connector_available():
        try:
            from app.lol.connector import connector
            return await connector.getAugmentIcon(augId)
        except (AttributeError, TypeError, KeyError, aiohttp.ClientError) as e:
            logger.debug(f"[{TAG}] getAugmentIcon fallback: {e}")
    return None
