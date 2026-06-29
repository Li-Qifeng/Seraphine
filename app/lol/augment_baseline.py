"""海克斯强化组合分: 基于用户已选强化的 OPGG pick/win 数据评估组合强度.

用于战犯/躺赢狗诊断:
- 强化组合越强, 该英雄"预期贡献"基线越高
- 强化组合弱的玩家若仍打出伤害, 实际贡献相对于强组合玩家更值得肯定
- 数据缺失 (非海克斯局 / 无 OPGG 数据) 返回 None, 调用方降级处理
"""
from typing import Optional

TAG = "AugmentBaseline"

# 内存缓存: championId -> list[list[dict]] (三档 silver/gold/prismatic)
_augmentCache: dict = {}


async def _loadChampionAugments(championId: int) -> list:
    """加载某英雄的海克斯强化列表 (opgg.getChampionBuild 缓存已内置).

    Returns:
        list of 3 lists (silver/gold/prismatic), 每个 list 元素是 dict 含
        id/name/win/play/pickRate. 失败返回 [].
    """
    # 惰性导入: 避免测试环境因 qfluentwidgets 缺失导致模块加载失败
    from .opgg import opgg
    from ..common.logger import logger

    if championId in _augmentCache:
        return _augmentCache[championId]

    try:
        if not getattr(opgg, 'apiSession', None) or opgg.apiSession.closed:
            await opgg.start()

        build = await opgg.getChampionBuild(
            region='global', mode='aram_mayhem',
            championId=championId, position='none', tier='all')
        data = build.get('data') if isinstance(build, dict) else None
        if not isinstance(data, dict):
            _augmentCache[championId] = []
            return []

        augments = data.get('augments') or []
        if not isinstance(augments, list):
            _augmentCache[championId] = []
            return []

        _augmentCache[championId] = augments
        return augments
    except Exception as e:
        logger.warning(f"_loadChampionAugments failed: {e}", TAG)
        _augmentCache[championId] = []
        return []


def _augmentScore(aug: dict) -> float:
    """单个强化得分 = 胜率(0..1) * 0.6 + 选用率(0..1) * 0.4.

    OPGG parseAramMayhemAugments 输出字段: pickRate / winRate (0-100 百分数).
    高胜率高选用 = 强力主流强化; 胜率高选用低 = 偏门但强.
    失败返回 0.5 (中性).
    """
    if not isinstance(aug, dict):
        return 0.5

    pickRate = aug.get('pickRate')
    winRate = aug.get('winRate')
    try:
        pickRate = float(pickRate) if pickRate is not None else 0.0
        winRate = float(winRate) if winRate is not None else 0.0
        # OPGG 返回的是 0-100 百分数, 归一化到 [0,1]
        if pickRate > 1.0:
            pickRate = pickRate / 100.0
        if winRate > 1.0:
            winRate = winRate / 100.0
    except (TypeError, ValueError):
        pickRate = 0.0
        winRate = 0.0

    pickRate = max(0.0, min(1.0, pickRate))
    winRate = max(0.0, min(1.0, winRate))
    return winRate * 0.6 + pickRate * 0.4


async def getHextechAugmentScore(augmentIds: list,
                                 championId: Optional[int] = None) -> Optional[float]:
    """评估用户已选海克斯强化组合强度.

    Args:
        augmentIds: 已选强化 id 列表 (通常 6 个)
        championId: 英雄 id, 用于查 OPGG 该英雄的强化列表. None 则按全局 id 查找

    Returns:
        [0,1] 范围的组合分. 数据完全缺失返回 None.
        空列表 (未选强化 / 已重开局) 返回 None.
    """
    if not augmentIds:
        return None
    if not isinstance(augmentIds, (list, tuple)):
        return None

    augIds = [int(x) for x in augmentIds if x is not None]
    if not augIds:
        return None

    # 海克斯强化最多 6 个, 取平均得分
    augmentsData = await _loadChampionAugments(championId) if championId else []
    if not augmentsData:
        return None

    # 构建 id -> aug dict 索引
    augMap = {}
    for tier in augmentsData:
        if not isinstance(tier, list):
            continue
        for aug in tier:
            if isinstance(aug, dict) and aug.get('id') is not None:
                augMap[int(aug['id'])] = aug

    scores = []
    for aid in augIds:
        aug = augMap.get(aid)
        if aug is None:
            # 该强化不在 OPGG 列表中 (新增/未收录), 按中性 0.5
            scores.append(0.5)
        else:
            scores.append(_augmentScore(aug))

    if not scores:
        return None
    return sum(scores) / len(scores)


def clearAugmentCache():
    """清空缓存."""
    _augmentCache.clear()
