"""
海克斯强化搭配协同推荐引擎。

基于 OPGG 强化列表 + 已选强化, 计算每个候选强化的推荐分。
推荐分 = OPGG 排名分 * 0.6 + 搭配协同分 * 0.4
"""

import re
from typing import Optional

from app.common.logger import logger

TAG = "AugmentRecommender"

# OPGG 分数权重
OPGG_WEIGHT = 0.6
SYNERGY_WEIGHT = 0.4

# 稀有度档位名称 (与 opgg.parseAramMayhemAugments 输出顺序对应)
TIER_NAMES = ('silver', 'gold', 'prismatic')

# 根据已选数量推断当前轮次档位 (Fallback 用: offer 不可得时推荐该档位)
# 假设流程: 第1轮银色, 第2轮银色, 第3轮金色, 第4轮金色, 第5轮棱彩, 第6轮棱彩
TIER_BY_ROUND = ['silver', 'silver', 'gold', 'gold', 'prismatic', 'prismatic']

# 关键词 -> 标签 映射 (中英文兼容)
_KEYWORD_TAGS = {
    # 法术伤害类
    '法术强度': 'ap_damage', '法强': 'ap_damage', 'ability power': 'ap_damage',
    'ap': 'ap_damage', '魔法伤害': 'ap_damage',
    # 法穿
    '法术穿透': 'magic_pen', '法穿': 'magic_pen', 'magic pen': 'magic_pen',
    # 物理伤害类
    '攻击力': 'ad_damage', '物理伤害': 'ad_damage', 'attack damage': 'ad_damage',
    'ad ': 'ad_damage', '物理攻击': 'ad_damage',
    # 护甲穿透
    '护甲穿透': 'armor_pen', '穿甲': 'armor_pen', 'armor pen': 'armor_pen',
    'lethality': 'armor_pen',
    # 攻速
    '攻击速度': 'attack_speed', '攻速': 'attack_speed', 'attack speed': 'attack_speed',
    # 技能急速
    '技能急速': 'ability_haste', 'ability haste': 'ability_haste',
    '冷却缩减': 'ability_haste',
    # 治疗护盾
    '治疗': 'heal_shield', '护盾': 'heal_shield', 'heal': 'heal_shield',
    'shield': 'heal_shield',
    # 最大生命
    '最大生命': 'max_hp', '生命值': 'max_hp', 'max hp': 'max_hp',
    '最大体力': 'max_hp',
    # 斩杀
    '斩杀': 'execute', '处决': 'execute', 'execute': 'execute',
    # 伤害放大
    '伤害提升': 'damage_amp', '伤害增加': 'damage_amp', 'damage amp': 'damage_amp',
    '增伤': 'damage_amp',
    # 机动
    '移速': 'mobility', '移动速度': 'mobility', 'movement speed': 'mobility',
    '冲刺': 'mobility', 'dash': 'mobility',
}

# 标签协同关系: {标签: (协同标签列表, 冲突标签列表)}
# 协同是对称的: A 协同 B 则 B 也协同 A (在 _computeSynergy 中双向检查)
_SYNERGY_RULES = {
    'ap_damage': (['magic_pen', 'ability_haste', 'damage_amp'], ['ad_damage']),
    'ad_damage': (['armor_pen', 'attack_speed', 'damage_amp'], ['ap_damage']),
    'magic_pen': (['ap_damage'], []),
    'armor_pen': (['ad_damage'], []),
    'attack_speed': (['ad_damage', 'armor_pen'], []),
    'ability_haste': (['ap_damage', 'ad_damage', 'heal_shield'], []),
    'heal_shield': (['max_hp', 'ability_haste'], []),
    'max_hp': (['heal_shield'], []),
    'execute': (['damage_amp', 'ap_damage', 'ad_damage'], []),
    'damage_amp': (['ap_damage', 'ad_damage', 'execute'], []),
    'mobility': ([], []),
}

# 标签中文名 (用于推荐理由文案)
_TAG_LABELS = {
    'ap_damage': '法伤', 'magic_pen': '法穿', 'ad_damage': '物伤',
    'armor_pen': '穿甲', 'attack_speed': '攻速', 'ability_haste': '技能急速',
    'heal_shield': '治疗护盾', 'max_hp': '最大生命', 'execute': '斩杀',
    'damage_amp': '伤害放大', 'mobility': '机动',
}

_HTML_RE = re.compile(r'<[^>]+>')


class AugmentRecommender:
    """海克斯强化推荐引擎"""

    def __init__(self):
        self._tagCache = {}  # augId -> set(tags)

    def recommend(self, selectedAugIds: list, allAugments: list,
                  offerAugIds: Optional[list] = None) -> list:
        """计算推荐列表。

        Args:
            selectedAugIds: 已选强化 ID 列表
            allAugments: opgg parseAramMayhemAugments 的三档输出
                         [[silver...], [gold...], [prismatic...]]
            offerAugIds: 当前可选 offer 的强化 ID (None 或空表示未知, 降级为全量)

        Returns:
            [{'aug': augDict, 'score': float, 'reason': str, 'tier': str}]
            按 score 降序排序, 过滤已选
        """
        try:
            selected_set = set(selectedAugIds or [])
            selected_tags = set()
            for aid in selected_set:
                tags = self._getTagsForAugId(aid, allAugments)
                selected_tags.update(tags)

            # 确定候选池
            if offerAugIds:
                # 有 offer: 只在 offer 中推荐
                candidates = self._collectFromOffer(offerAugIds, allAugments)
            elif selectedAugIds:
                # 有已选但无 offer: 推荐当前轮次档位
                current_tier = self._inferCurrentTier(len(selectedAugIds))
                candidates = self._collectByTier(current_tier, allAugments)
            else:
                # 无已选也无 offer: 展示全档位
                candidates = self._collectAll(allAugments)

            # 过滤已选
            candidates = [c for c in candidates if c['aug']['id'] not in selected_set]

            # 归一化 pickRate/winRate: OPGG 返回 0-100 百分数, 转为 0-1
            def _norm(v):
                try:
                    v = float(v or 0)
                    return v / 100.0 if v > 1.0 else v
                except (TypeError, ValueError):
                    return 0.0

            # 计算归一化用的最大值
            max_pick = max((_norm(c['aug'].get('pickRate')) for c in candidates), default=1) or 1
            max_win = max((_norm(c['aug'].get('winRate')) for c in candidates), default=1) or 1

            results = []
            for c in candidates:
                aug = c['aug']
                tier = c['tier']
                pick = _norm(aug.get('pickRate'))
                win = _norm(aug.get('winRate'))
                opgg_score = (pick / max_pick) * 0.5 + (win / max_win) * 0.5

                # 协同分
                aug_tags = self._getTagsForAug(aug)
                synergy, reasons = self._computeSynergy(aug_tags, selected_tags)

                score = opgg_score * OPGG_WEIGHT + synergy * SYNERGY_WEIGHT

                # 推荐理由
                if reasons:
                    reason = f"与已选 {'/'.join(reasons)} 协同"
                elif opgg_score > 0.7:
                    reason = "OPGG 高登场率"
                else:
                    reason = ""

                results.append({
                    'aug': aug,
                    'score': round(score, 3),
                    'reason': reason,
                    'tier': tier,
                })

            results.sort(key=lambda x: x['score'], reverse=True)
            return results
        except Exception as e:
            logger.warning(f"recommend failed: {e}", TAG)
            return []

    def _getTagsForAugId(self, augId: int, allAugments: list) -> set:
        """根据 augId 从全量数据中查找强化并提取标签."""
        if augId in self._tagCache:
            return self._tagCache[augId]
        for group in allAugments:
            for aug in group:
                if isinstance(aug, dict) and aug.get('id') == augId:
                    tags = self._getTagsForAug(aug)
                    self._tagCache[augId] = tags
                    return tags
        return set()

    def _getTagsForAug(self, aug: dict) -> set:
        """从强化的 desc/tooltip 提取标签."""
        aid = aug.get('id')
        if aid in self._tagCache:
            return self._tagCache[aid]
        text = ''
        for field in ('desc', 'tooltip', 'name'):
            v = aug.get(field)
            if isinstance(v, str):
                text += ' ' + v
        text = _HTML_RE.sub('', text).lower()
        tags = set()
        for kw, tag in _KEYWORD_TAGS.items():
            if kw.lower() in text:
                tags.add(tag)
        self._tagCache[aid] = tags
        return tags

    def _computeSynergy(self, augTags: set, selectedTags: set) -> tuple:
        """计算候选强化与已选强化的协同分和理由.

        协同是双向的: 候选 ap_damage 与已选 magic_pen 协同,
        候选 magic_pen 与已选 ap_damage 也协同.

        Returns:
            (synergy_score in [0, 1], reason_tag_labels list)
        """
        if not selectedTags or not augTags:
            return 0.0, []
        score = 0.0
        reasons = []
        for tag in augTags:
            rule = _SYNERGY_RULES.get(tag)
            if not rule:
                continue
            synergies, conflicts = rule
            # 正向: 候选 tag 的协同列表中有已选 tag
            for syn in synergies:
                if syn in selectedTags:
                    score += 0.3
                    if tag in _TAG_LABELS:
                        reasons.append(_TAG_LABELS[tag])
                    break
            # 反向: 已选 tag 的协同列表中有候选 tag (双向协同)
            for selTag in selectedTags:
                selRule = _SYNERGY_RULES.get(selTag)
                if not selRule:
                    continue
                selSynergies, _ = selRule
                if tag in selSynergies:
                    score += 0.3
                    if tag in _TAG_LABELS and tag not in reasons:
                        reasons.append(_TAG_LABELS[tag])
                    break
            for con in conflicts:
                if con in selectedTags:
                    score -= 0.2
        return max(0.0, min(1.0, score)), list(dict.fromkeys(reasons))[:3]

    def _inferCurrentTier(self, selectedCount: int) -> str:
        """根据已选数量推断当前轮次档位 (Fallback)."""
        if selectedCount < 0:
            selectedCount = 0
        if selectedCount >= len(TIER_BY_ROUND):
            return TIER_BY_ROUND[-1]
        return TIER_BY_ROUND[selectedCount]

    def _collectFromOffer(self, offerAugIds: list, allAugments: list) -> list:
        """从 offer 列表收集候选强化."""
        id_set = set(offerAugIds)
        result = []
        for idx, group in enumerate(allAugments):
            tier = TIER_NAMES[idx] if idx < len(TIER_NAMES) else 'silver'
            for aug in group:
                if isinstance(aug, dict) and aug.get('id') in id_set:
                    result.append({'aug': aug, 'tier': tier})
        return result

    def _collectByTier(self, tier: str, allAugments: list) -> list:
        """收集指定档位的所有强化 (Fallback)."""
        idx = TIER_NAMES.index(tier) if tier in TIER_NAMES else 0
        if idx >= len(allAugments):
            return []
        return [{'aug': aug, 'tier': tier}
                for aug in allAugments[idx] if isinstance(aug, dict)]

    def _collectAll(self, allAugments: list) -> list:
        """收集全档位所有强化 (无已选无 offer 时用)."""
        result = []
        for idx, group in enumerate(allAugments):
            tier = TIER_NAMES[idx] if idx < len(TIER_NAMES) else 'silver'
            for aug in group:
                if isinstance(aug, dict):
                    result.append({'aug': aug, 'tier': tier})
        return result


# 全局单例
augmentRecommender = AugmentRecommender()
