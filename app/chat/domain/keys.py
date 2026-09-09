"""热键解析与冲突校验（纯逻辑，无 Win32 依赖）。

铁律：RegisterHotKey 注册成功后会**吞掉**该组合键，游戏根本收不到 ——
绑错键 = 直接废掉一个游戏功能，所以冲突必须在**保存时硬拦截**，
不是警告后允许。

键位表依据：League Wiki「Hotkeys and commands」+ KBVE 键位表交叉验证
（2026-09，见调研 docs/04 §3.4）。
"""
from typing import Dict, FrozenSet, Optional, Tuple


class HotkeyError(ValueError):
    """热键非法或与游戏/系统/已有绑定冲突。"""


_VALID_MODS = {"ctrl", "alt", "shift", "win"}

# 合法主键名（小写）
_NAMED_KEYS = {
    "enter", "esc", "tab", "space", "`",
    "up", "down", "left", "right",
    "insert", "delete", "home", "end", "pageup", "pagedown",
    "scrolllock", "pause",
}

# LOL 默认占用的单键（不可作为热键，即便加修饰键单独使用也要走高危区表）
_FORBIDDEN_SINGLE = (
    set("qwerdf") | set("baxshpcgvtyomljz") | set("1234567") |
    {"enter", "esc", "tab", "space", "`",
     "up", "down", "left", "right",
     "f2", "f3", "f4", "f5", "f12"}
)


def _build_reserved() -> set:
    """LOL 默认键位 + Windows 系统级组合（高危区，命中即拦截）。"""
    combos = set()
    for k in "qwerdf":
        combos.add((frozenset({"alt"}), k))       # 技能/召唤师技能自我施法
    for k in ("q", "w", "e", "r", "1", "2", "3", "4", "6"):
        combos.add((frozenset({"ctrl"}), k))      # 加点 / 表情
    for k in "qwerdf":
        combos.add((frozenset({"shift"}), k))     # 智能施法
    for k in ("tab", "f4", "space", "esc"):
        combos.add((frozenset({"alt"}), k))       # 系统级
    combos.add((frozenset({"ctrl"}), "esc"))      # 系统级（开始菜单）
    return combos


RESERVED_COMBOS = _build_reserved()

# 主键名 → Win32 虚拟键码（注册热键用；常量列此避免 domain 依赖 win32con）
_VK_MAP = {
    "enter": 0x0D, "esc": 0x1B, "tab": 0x09, "space": 0x20, "`": 0xC0,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "insert": 0x2D, "delete": 0x2E, "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pagedown": 0x22, "scrolllock": 0x91, "pause": 0x13,
    "numdot": 0x6E, "numadd": 0x6B, "numsub": 0x6D,
    "nummul": 0x6A, "numdiv": 0x6F,
}
for _i in range(10):
    _VK_MAP[str(_i)] = 0x30 + _i          # 主键盘数字
    _VK_MAP[f"num{_i}"] = 0x60 + _i       # 小键盘数字
for _c in range(ord("a"), ord("z") + 1):
    _VK_MAP[chr(_c)] = ord(chr(_c).upper())
for _i in range(1, 25):
    _VK_MAP[f"f{_i}"] = 0x70 + _i - 1

_MOD_FLAGS = {"alt": 0x0001, "ctrl": 0x0002, "shift": 0x0004, "win": 0x0008}


def _is_valid_key(key: str) -> bool:
    return key in _VK_MAP or key in _NAMED_KEYS


def parse_hotkey(text: str) -> Tuple[FrozenSet[str], str]:
    """解析 "Alt+1" → (frozenset({'alt'}), '1')。非法格式抛 HotkeyError。"""
    if not text or not text.strip():
        raise HotkeyError("热键不能为空")
    parts = [p.strip().lower() for p in text.split("+")]
    if any(p == "" for p in parts):
        raise HotkeyError(f"热键格式非法: {text!r}")
    if len(parts) < 1:
        raise HotkeyError(f"热键格式非法: {text!r}")
    *mod_parts, key = parts
    mods = set()
    for m in mod_parts:
        if m not in _VALID_MODS:
            raise HotkeyError(f"非法修饰键: {m}")
        mods.add(m)
    if not _is_valid_key(key):
        raise HotkeyError(f"非法按键: {key}")
    return frozenset(mods), key


def validate_hotkey(text: str, existing: Optional[Dict[str, str]] = None,
                    self_id: Optional[str] = None):
    """保存时硬拦截：格式非法 / LOL 高危区 / 系统占用 / 与其他分组冲突 → 抛 HotkeyError。

    existing: {hotkey: group_id} 现有绑定清单；self_id 用于排除自身（改绑不算冲突）。
    """
    mods, key = parse_hotkey(text)
    if not mods and key in _FORBIDDEN_SINGLE:
        raise HotkeyError(f"「{text}」是 LOL 默认按键，绑定会让游戏功能失效")
    if (mods, key) in RESERVED_COMBOS:
        raise HotkeyError(f"「{text}」与 LOL / 系统关键组合冲突，禁止使用")
    if existing:
        canonical = canonical_hotkey(text)
        for hk, gid in existing.items():
            if canonical_hotkey(hk) == canonical and gid != self_id:
                raise HotkeyError(f"「{text}」已被其他分组绑定")


def canonical_hotkey(text: str) -> str:
    """归一化为 'alt+ctrl+shift+win+key' 形式，用于等价比较。"""
    mods, key = parse_hotkey(text)
    ordered = [m for m in ("ctrl", "alt", "shift", "win") if m in mods]
    return "+".join(ordered + [key])


def hotkey_to_vk(text: str) -> Tuple[int, int]:
    """转 Win32 (mod_flags, vk)，供 RegisterHotKey 使用。"""
    mods, key = parse_hotkey(text)
    flags = 0
    for m in mods:
        flags |= _MOD_FLAGS[m]
    return flags, _VK_MAP[key]
