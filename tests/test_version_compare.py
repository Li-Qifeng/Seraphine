"""
版本比较逻辑测试 (app.common.version_utils.coerce_version).

coerce_version 被 app.common.util.Github.checkUpdate 调用, 用于语义化版本比较.
本测试只测纯函数, 不依赖 PyQt5 / requests / 网络.
"""
from app.common.version_utils import coerce_version as _coerce_version


class TestCoerceVersion:
    def test_standard_numeric(self):
        """标准数字版本号能被 packaging 正确解析."""
        v = _coerce_version("1.1.9")
        assert v is not None
        assert str(v) == "1.1.9"

    def test_with_v_prefix(self):
        """带 v 前缀的 tag 能正确去掉前缀."""
        assert _coerce_version("v1.1.9") == _coerce_version("1.1.9")

    def test_strip_whitespace(self):
        """前后空白被 strip."""
        assert _coerce_version("  1.1.9  ") == _coerce_version("1.1.9")

    def test_empty_returns_none(self):
        """空字符串返回 None."""
        assert _coerce_version("") is None
        assert _coerce_version(None) is None

    def test_10_greater_than_9(self):
        """关键回归: 字符串比较 '1.1.9' > '1.1.10' (因 '9' > '1'),
        但语义上 1.1.10 > 1.1.9. 这是旧实现的核心 bug.
        """
        v9 = _coerce_version("1.1.9")
        v10 = _coerce_version("1.1.10")
        assert v10 > v9, "1.1.10 should be > 1.1.9 (semantic, not string)"

    def test_major_version(self):
        """大版本号比较."""
        assert _coerce_version("2.0.0") > _coerce_version("1.99.99")

    def test_pre_release(self):
        """PEP 440 pre-release: 1.0.0a1 < 1.0.0."""
        assert _coerce_version("1.0.0a1") < _coerce_version("1.0.0")
        assert _coerce_version("1.0.0rc1") < _coerce_version("1.0.0")

    def test_invalid_fallback_to_string(self):
        """非标准版本号 (含日期/commit hash) 解析失败时退化到字符串,
        不抛异常, 保留旧行为兜底.
        """
        weird = _coerce_version("2024.01.01-dev+abc123")
        # 不管解析成功还是退化, 不应为 None 且不抛异常
        assert weird is not None

    def test_equal_versions(self):
        """相同版本号相等."""
        assert _coerce_version("1.1.9") == _coerce_version("v1.1.9")

    def test_downgrade_detection(self):
        """降级场景: 旧版本 < 新版本的比较能正确识别."""
        assert not (_coerce_version("1.1.8") > _coerce_version("1.1.9"))
