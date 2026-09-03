import json
import os
import subprocess
from functools import lru_cache

import aiohttp

from app.common.config import LOCAL_PATH
from app.common.logger import logger
from app.common.util import getLolClientVersion


class AramBuff:
    """
    #### 数据使用已获得授权
    Powered by: 大乱斗之家
    Site: http://www.jddld.com

    jddld 不可用时的兜底数据源: balance-buff-viewer-plugin (npm),
    原始数据来自 League Wiki (Module:ChampionData), 拉取后转换为
    jddld 字段格式, 对 UI (AramFlyoutView / 备选席 tooltip) 透明.
    """
    ARAM_CFG_PATH = f"{LOCAL_PATH}/AramBuff.json"
    # 兜底数据缓存 (jddld 失败时使用)
    BALANCE_CFG_PATH = f"{LOCAL_PATH}/champion-balance.json"
    URL = "http://www.jddld.com"
    # npm 包 balance-buff-viewer-plugin 的 dist/balance.json
    NPM_REGISTRY_URL = "https://registry.npmjs.org/balance-buff-viewer-plugin"
    BALANCE_CDN_URL = ("https://cdn.jsdelivr.net/npm/"
                       "balance-buff-viewer-plugin@{version}/dist/balance.json")
    TAG = "AramBuff"
    APPID = 1
    APP_SECRET = os.environ.get("SERAPHINE_ARAM_SECRET", "PHPCMFBBC77AF8E8FA5")
    data = None

    @classmethod
    async def checkAndUpdate(cls):
        m = cls()
        if m.__needUpdate():
            # 主源 (jddld, 含中文描述) 失败时走 npm 兜底 (League Wiki 数据)
            if not await m.__update():
                await m.__updateFallback()

    def __needUpdate(self):
        """
        检查缓存的数据与当前版本是否匹配, 若不匹配尝试更新

        尽可能在游戏启动后再调用, 否则当存在多个客户端时, `cfg.lolFolder` 不一定是准确的
        （外服国服可能版本不同）

        @return :
        - `True` -> 需要更新
        - `False` -> 无需更新

        TODO: 暂未提供历史版本数据查询接口
        """
        try:
            lolVersion = getLolClientVersion()
        except (OSError, subprocess.SubprocessError):
            return True

        if not os.path.exists(self.ARAM_CFG_PATH):
            return True

        with open(self.ARAM_CFG_PATH, 'r') as f:
            try:
                AramBuff.data = json.loads(f.read())
            except json.JSONDecodeError:
                return True

            # 兼容老版本的 json
            if AramBuff.data.get('version') is None:
                return True

            return AramBuff.getDataVersion() != lolVersion

    @classmethod
    def getDataVersion(cls):
        return AramBuff.data.get("version")

    async def __update(self) -> bool:
        url = f'{self.URL}/index.php'
        params = {
            'appid': self.APPID,
            'appsecret': self.APP_SECRET,
            's': 'news',
            'c': 'search',
            'api_call_function': 'module_list',
            'pagesize': '200'
        }

        try:
            async with aiohttp.ClientSession() as session:
                res = await session.get(
                    url, params=params, proxy=None, ssl=False,
                    timeout=aiohttp.ClientTimeout(total=15))
                data = await res.json()
        except Exception:
            logger.warning("Getting Aram buff failed", self.TAG)
            return False

        if data.get('code') != 1:
            logger.warning(f"Update Aram buff failed, data: {data}", self.TAG)
            return False

        try:
            data: dict = data['data']

            version = data.pop('banben')
            champions = {item['heroid']: item for item in data.values()}

            AramBuff.data = {
                'champions': champions,
                'version': version
            }

            with open(self.ARAM_CFG_PATH, 'w') as f:
                json.dump(AramBuff.data, f)

        except (KeyError, TypeError):
            logger.warning(f"Parse Aram buff failed, data: {data}", self.TAG)
            return False

        return True

    async def __updateFallback(self) -> bool:
        """jddld 失败后的兜底: 拉取 npm 上 balance-buff-viewer-plugin 的
        balance.json (League Wiki 平衡数据), 转换成 jddld 字段格式.

        网络/解析失败时回退到本地 champion-balance.json 缓存 (若存在).
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                        self.NPM_REGISTRY_URL,
                        timeout=aiohttp.ClientTimeout(total=10)) as res:
                    if res.status != 200:
                        raise aiohttp.ClientError(
                            f"npm registry HTTP {res.status}")
                    info = await res.json()

                version = ((info or {}).get('dist-tags') or {}).get('latest')
                if not version:
                    raise ValueError("npm registry has no latest version")

                async with session.get(
                        self.BALANCE_CDN_URL.format(version=version),
                        timeout=aiohttp.ClientTimeout(total=30)) as res:
                    if res.status != 200:
                        raise aiohttp.ClientError(f"cdn HTTP {res.status}")
                    raw = await res.json()

            AramBuff.data = {
                'champions': self.__convertBalancePlugin(raw),
                'version': f"npm-{version}",
            }

            with open(self.BALANCE_CFG_PATH, 'w') as f:
                json.dump(AramBuff.data, f)

            logger.info(
                f"Aram buff fallback loaded "
                f"(balance-buff-viewer-plugin {version})", self.TAG)
            return True

        except Exception as e:
            logger.warning(f"Getting Aram buff fallback failed: {e}", self.TAG)

            # 完全离线: 尝试加载磁盘上的兜底缓存
            if AramBuff.data is None and os.path.exists(self.BALANCE_CFG_PATH):
                try:
                    with open(self.BALANCE_CFG_PATH, 'r') as f:
                        AramBuff.data = json.loads(f.read())
                    logger.info(
                        "Aram buff fallback loaded from local cache", self.TAG)
                    return True
                except (OSError, json.JSONDecodeError):
                    pass
            return False

    @staticmethod
    def __convertBalancePlugin(raw) -> dict:
        """balance.json -> jddld champions 字典格式.

        倍率字段 (0.95) 转为百分比整数 (95), ability_haste 保持原值,
        tenacity (1.2) 转为百分比整数 (120); 缺省值与 UI 层
        (AramFlyoutView/_getBuffTip) 的默认值对齐, 保证 100/0 不展示.
        """
        from app.lol.connector import connector  # 延迟导入避免循环依赖

        def pct(v, default=None):
            if v is None:
                return default
            try:
                return round(float(v) * 100)
            except (TypeError, ValueError):
                return default

        champions = {}
        for cid, item in (raw or {}).items():
            aram = ((item or {}).get('stats') or {}).get('aram') or {}
            if not aram:
                continue

            name = item.get('name') or str(cid)
            title = item.get('title') or ''
            catname = f"{name} - {title}" if title else name

            # 尽量换成本地化的英雄名 (国服客户端为中文名)
            try:
                if connector.manager is not None:
                    cn = connector.manager.getChampionNameById(int(cid))
                    if cn:
                        catname = f"{cn} - {title}" if title else cn
            except (ValueError, AttributeError, TypeError):
                pass

            champions[str(cid)] = {
                'heroid': str(cid),
                'catname': catname,
                'zcsh': pct(aram.get('dmg_dealt'), 100),
                'sdsh': pct(aram.get('dmg_taken'), 100),
                'zlxl': pct(aram.get('healing'), 100),
                'hdxn': pct(aram.get('shielding'), 100),
                'jnjs': aram.get('ability_haste', 0),
                'renxing': pct(aram.get('tenacity'), 0),
            }

        return champions

    @classmethod
    def isAvailable(cls) -> bool:
        return AramBuff.data is not None

    @classmethod
    @lru_cache(maxsize=None)
    def getInfoByChampionId(cls, championId):
        if not AramBuff.isAvailable():
            return None

        return AramBuff.data['champions'].get(str(championId))
