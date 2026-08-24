"""lzyumi 第三方数据源纯函数：签名 / 响应解码 / 解析。

契约来自黑盒侦察文档（/root/ctf-lol/REPLICATION.md）：
- lzyumiSign = md5(f"dld{MM}o{dd}u{HH}d{mm}o{ss}dld")，各字段两位补零
- signStr = 各字段十进制拼接 + 各字段位数*3 拼接
- 响应可能为 base64 编码，需检测后先 b64decode 再 json.loads
"""

import base64
import binascii
import hashlib
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

TAG = "lzyumiTools"


def _pad(x: int) -> str:
    return f"{x:02d}"


def sign_seed(dt: datetime) -> str:
    """签名原文：dld{MM}o{dd}u{HH}d{mm}o{ss}dld"""
    return (
        f"dld{_pad(dt.month)}o{_pad(dt.day)}u{_pad(dt.hour)}"
        f"d{_pad(dt.minute)}o{_pad(dt.second)}dld"
    )


def lzyumi_sign(dt: datetime) -> str:
    return hashlib.md5(sign_seed(dt).encode()).hexdigest()


def sign_str(dt: datetime) -> str:
    v = [dt.month, dt.day, dt.hour, dt.minute, dt.second]
    return "".join(str(x) for x in v) + "".join(str(len(str(x)) * 3) for x in v)


def decode_response(data: bytes) -> Dict[str, Any]:
    """响应解码：base64 编码或明文 JSON 均可。失败抛 ValueError。"""
    text = data.decode("utf-8", errors="strict").strip()
    try:
        decoded = base64.b64decode(text, validate=True)
        # 合法 b64 且解出的是 JSON 才认为是编码响应
        candidate = json.loads(decoded.decode("utf-8"))
        if isinstance(candidate, dict):
            return candidate
    except (binascii.Error, ValueError, UnicodeDecodeError):
        pass
    try:
        result = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"[{TAG}] invalid response body: {text[:80]!r}") from e
    if not isinstance(result, dict):
        raise ValueError(f"[{TAG}] response is not an object: {text[:80]!r}")
    return result


def _parse_elo_field(value: Any) -> Optional[int]:
    """解析 '单双：1478' 中文冒号格式为 int elo；无法解析返回 None。"""
    if not isinstance(value, str) or "：" not in value:
        return None
    tail = value.rsplit("：", 1)[1].strip()
    try:
        return int(tail)
    except ValueError:
        return None


def parse_rank_elo(raw: Dict[str, Any]) -> Optional[Dict[str, Optional[int]]]:
    """解析隐藏分响应 → {solo, flex, aram}；全部缺失时返回 None。"""
    if not isinstance(raw, dict):
        return None
    result = {
        "solo": _parse_elo_field(raw.get("dataRankEloNum")),
        "flex": _parse_elo_field(raw.get("dataRankEloInfoB")),
        "aram": _parse_elo_field(raw.get("dataRankEloInfoA")),
    }
    if all(v is None for v in result.values()):
        return None
    return result


def parse_recent_games(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    """解析近十场响应 data[] → [{gameId, championId, isWin, isMvp, isSvp}]"""
    if not isinstance(raw, dict):
        return []
    games = raw.get("data")
    if not isinstance(games, list):
        return []
    out = []
    for g in games:
        if not isinstance(g, dict):
            continue
        out.append(
            {
                "gameId": g.get("gameId"),
                "championId": g.get("championId"),
                "isWin": bool(g.get("isWin")),
                "isMvp": bool(g.get("wasMvp")),
                "isSvp": bool(g.get("wasSvp")),
            }
        )
    return out
