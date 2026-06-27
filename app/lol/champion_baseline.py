"""英雄历史对照基线: 调用 OPGG 获取该英雄在指定模式下的胜率.

用于战犯/躺赢狗诊断:
- 胜率高的英雄, 在胜局"躺赢狗"判定权重应增大 (赢但贡献低更显躺赢)
- 胜率高的英雄, 在负局"战犯"判定权重应增大 (输应承担更多责任)
- 数据缺失时返回 None, 调用方降级到纯队伍内 z-score 模式
"""
from typing import Optional

TAG = "ChampionBaseline"

# queueId -> opgg mode 映射 (与 tools.showOpggBuild 一致)
_QUEUE_TO_MODE = {
    420: 'ranked', 440: 'ranked', 450: 'aram', 490: 'ranked',
    900: 'urf', 1900: 'urf', 1300: 'nexus_blitz',
    1700: 'arena', 1710: 'arena',
    1090: 'aram', 2400: 'aram_mayhem',
}

# 内存缓存: (championId, mode) -> winRate [0,1]
# OPGG 数据每个 patch 才更新, 进程内缓存即可
_winrateCache: dict = {}


def _queueIdToMode(queueId: Optional[int]) -> str:
    if queueId is None:
        return ''
    return _QUEUE_TO_MODE.get(queueId, '')


async def getChampionBaselineWinrate(championId: int,
                                     queueId: Optional[int]) -> Optional[float]:
    """获取英雄在指定模式下的 OPGG 胜率.

    Returns:
        胜率 [0,1] (如 0.523), 数据缺失或请求失败返回 None.
        海克斯大乱斗 (aram_mayhem) 取 summary.winRate;
        ranked 模式取第一个位置的 winRate.
    """
    if championId is None or championId == 0:
        return None

    mode = _queueIdToMode(queueId)
    if not mode:
        return None

    cacheKey = (championId, mode)
    if cacheKey in _winrateCache:
        return _winrateCache[cacheKey]

    # 惰性导入: 避免测试环境因 qfluentwidgets 缺失导致模块加载失败
    from .opgg import opgg
    from ..common.logger import logger

    try:
        if not getattr(opgg, 'apiSession', None) or opgg.apiSession.closed:
            await opgg.start()

        # 海克斯/ARAM/ Arena: position='none', tier='all'
        if mode == 'ranked':
            # ranked 取所有位置平均, 用 'none' 兜底
            position = 'none'
            tier = 'all'
        else:
            position = 'none'
            tier = 'all'

        build = await opgg.getChampionBuild(
            region='global', mode=mode,
            championId=championId, position=position, tier=tier)
        data = build.get('data') if isinstance(build, dict) else None
        if not isinstance(data, dict):
            logger.debug(
                f"baseline winrate: no data for {championId}/{mode}", TAG)
            _winrateCache[cacheKey] = None
            return None

        summary = data.get('summary') or {}
        wr = summary.get('winRate')
        if wr is None:
            logger.debug(
                f"baseline winrate: no winRate in summary for "
                f"{championId}/{mode}", TAG)
            _winrateCache[cacheKey] = None
            return None

        try:
            wr = float(wr)
        except (TypeError, ValueError):
            _winrateCache[cacheKey] = None
            return None

        # 归一化到 [0,1]
        if wr > 1.0:
            wr = wr / 100.0
        wr = max(0.0, min(1.0, wr))
        _winrateCache[cacheKey] = wr
        return wr
    except Exception as e:
        logger.warning(f"getChampionBaselineWinrate failed: {e}", TAG)
        _winrateCache[cacheKey] = None
        return None


def clearBaselineCache():
    """清空缓存 (patch 切换或测试用)."""
    _winrateCache.clear()
