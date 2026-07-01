"""
版本号解析与比较的纯工具模块 (不依赖 PyQt5 / requests / win32).

分离原因: app.common.util 模块级 import requests / winreg / win32api,
非 Windows 或缺依赖环境下无法 import, 导致 _coerce_version 无法被测试.
本模块只依赖 packaging, 可在任何平台独立测试.
"""
from packaging.version import InvalidVersion, parse as parse_version


def coerce_version(v: str):
    """
    将版本字符串解析为 PEP 440 对象用于语义化比较.

    Seraphine 用纯数字版本号 (如 "1.1.9"), packaging 能正常解析;
    若遇到非标准格式 (如含日期/commit hash), 退化到去掉前导 'v' 后的字符串,
    避免解析失败导致 checkUpdate 整体抛错.

    Args:
        v: 版本字符串, 可带可不带 'v' 前缀 (如 "v1.1.9" / "1.1.9")

    Returns:
        packaging.version.Version 对象, 或 str (解析失败时), 或 None (空输入)
    """
    if not v:
        return None
    s = v.lstrip('v').strip()
    try:
        return parse_version(s)
    except InvalidVersion:
        return s
