"""
静态契约测试: 项目自定义 Icon 枚举 (app/common/icons.py) 的引用完整性.

背景: 引用未定义的 Icon.XXX 成员 (如 Icon.MEGAPHONE) 在导入视图模块时
直接 AttributeError 闪退, 但 CI 的 pytest/ruff 均无法覆盖 UI 文件导入,
导致带崩构建发布 (v1.3.0 后 sideChatCard 事故).

契约:
1. app/**/*.py 中所有 `Icon.XXX` 引用 (排除 FluentIcon/QIcon 等同名后缀)
   必须是 Icon 枚举的已定义成员
2. Icon 每个成员的 value 必须有对应的本地 SVG 资源
   (app/resource/icons/{value}_black.svg 与 _white.svg),
   否则 path() 渲染空白图标

纯文本/ast 扫描, 不导入任何 Qt 模块.
"""
import ast
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICONS_FILE = os.path.join(ROOT, "app", "common", "icons.py")
SVG_DIR = os.path.join(ROOT, "app", "resource", "icons")

# 匹配裸 Icon.XXX, 排除 FluentIcon/QIcon/QSystemTrayIcon/RoundIcon 等前缀
_REF_RE = re.compile(r'(?<![A-Za-z_])Icon\.([A-Z][A-Z0-9_]*)')


def _icon_members():
    """ast 解析 icons.py, 返回 {成员名: value}."""
    with open(ICONS_FILE, encoding="utf-8") as f:
        tree = ast.parse(f.read())

    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "Icon":
            members = {}
            for stmt in node.body:
                if (isinstance(stmt, ast.Assign)
                        and len(stmt.targets) == 1
                        and isinstance(stmt.targets[0], ast.Name)
                        and isinstance(stmt.value, ast.Constant)
                        and isinstance(stmt.value.value, str)):
                    members[stmt.targets[0].id] = stmt.value.value
            return members
    return {}


def _scan_icon_refs():
    """扫描 app/**/*.py 中的 Icon.XXX 引用, 返回 {文件: [成员名]}."""
    refs = {}
    for dirpath, dirnames, filenames in os.walk(os.path.join(ROOT, "app")):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            path = os.path.join(dirpath, fn)
            with open(path, encoding="utf-8", errors="ignore") as f:
                names = _REF_RE.findall(f.read())
            if names:
                # 相对路径便于失败信息定位
                refs[os.path.relpath(path, ROOT)] = sorted(set(names))
    return refs


class TestIconEnumContract:
    def test_all_icon_refs_defined(self):
        """所有 Icon.XXX 引用必须是已定义成员 (防 AttributeError 启动闪退)."""
        members = _icon_members()
        refs = _scan_icon_refs()
        assert members, "Icon 枚举解析为空, icons.py 结构可能已变"

        undefined = {
            path: [n for n in names if n not in members]
            for path, names in refs.items()
        }
        undefined = {p: n for p, n in undefined.items() if n}
        assert not undefined, (
            f"引用了未定义的 Icon 成员 (启动时 AttributeError 闪退): {undefined}")

    def test_all_members_have_svg_resources(self):
        """每个成员的 value 必须有 black/white 两个本地 SVG (path() 契约)."""
        members = _icon_members()
        missing = []
        for name, value in members.items():
            for color in ("black", "white"):
                svg = os.path.join(SVG_DIR, f"{value}_{color}.svg")
                if not os.path.exists(svg):
                    missing.append(f"{name} = {value}: 缺 {color} 版")
        assert not missing, f"Icon 成员缺本地 SVG 资源: {missing}"
