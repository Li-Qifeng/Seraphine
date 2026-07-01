"""
tufup_updater 封装逻辑测试.

测试策略:
- mock app.common.config (sandbox 无 PyQt5, 无法 import 真实 config)
- mock tufup.client.Client (避免真实网络请求)
- 只测封装逻辑: 开发模式禁用 / root.json 缺失 / check_update 成功失败 / download_and_install 流程
- 不测 tufup 内部行为 (那是 tufup 库的职责)
"""
import sys
import types
from unittest.mock import MagicMock, patch

# === 在 import tufup_updater 前 mock app.common.config (sandbox 无 PyQt5) ===
_mock_config = types.ModuleType("app.common.config")
_mock_config.VERSION = "1.1.9"
_mock_config.LOCAL_PATH = "/tmp/mock_seraphine"
_mock_config.cfg = MagicMock()
sys.modules["app.common.config"] = _mock_config


from app.common import tufup_updater  # noqa: E402


class TestGetAppInstallDir:
    def test_dev_mode_returns_none(self, tmp_path, monkeypatch):
        """无 Seraphine.exe 时返回 None (开发模式)."""
        monkeypatch.chdir(tmp_path)
        assert tufup_updater._get_app_install_dir() is None

    def test_release_mode_returns_dir(self, tmp_path, monkeypatch):
        """有 Seraphine.exe 时返回安装目录."""
        (tmp_path / "Seraphine.exe").write_text("fake")
        monkeypatch.chdir(tmp_path)
        result = tufup_updater._get_app_install_dir()
        assert result is not None
        assert str(result) == str(tmp_path)


class TestCheckUpdate:
    def test_dev_mode_skip(self, tmp_path, monkeypatch):
        """开发模式 (无 Seraphine.exe) 直接返回 (False, None), 不查 tufup."""
        monkeypatch.chdir(tmp_path)
        has, ver = tufup_updater.check_update()
        assert has is False
        assert ver is None

    def test_missing_root_json(self, tmp_path, monkeypatch):
        """有 Seraphine.exe 但无 root.json (tufup 未初始化) 返回 (False, None)."""
        (tmp_path / "Seraphine.exe").write_text("fake")
        monkeypatch.chdir(tmp_path)
        # install_dir = tmp_path, bundled metadata 在
        # tmp_path/app/resource/tufup/metadata/root.json (不存在)
        has, ver = tufup_updater.check_update()
        assert has is False
        assert ver is None

    def test_update_available(self, tmp_path, monkeypatch):
        """tufup 返回新版本时, check_update 透传 (True, new_version)."""
        (tmp_path / "Seraphine.exe").write_text("fake")
        monkeypatch.chdir(tmp_path)

        # mock root.json 存在
        with patch.object(tufup_updater.os.path, "exists", return_value=True), \
             patch.object(tufup_updater, "_make_client") as mock_make:
            mock_client = MagicMock()
            mock_meta = MagicMock()
            mock_meta.version = "1.2.0"
            mock_client.check_for_updates.return_value = mock_meta
            mock_make.return_value = mock_client

            has, ver = tufup_updater.check_update()

        assert has is True
        assert ver == "1.2.0"

    def test_no_update(self, tmp_path, monkeypatch):
        """tufup 返回 None (无新版本) 时, check_update 返回 (False, None)."""
        (tmp_path / "Seraphine.exe").write_text("fake")
        monkeypatch.chdir(tmp_path)

        with patch.object(tufup_updater.os.path, "exists", return_value=True), \
             patch.object(tufup_updater, "_make_client") as mock_make:
            mock_client = MagicMock()
            mock_client.check_for_updates.return_value = None
            mock_make.return_value = mock_client

            has, ver = tufup_updater.check_update()

        assert has is False
        assert ver is None

    def test_network_failure_safe(self, tmp_path, monkeypatch):
        """tufup 抛异常 (网络失败) 时, check_update 不抛, 返回 (False, None)."""
        (tmp_path / "Seraphine.exe").write_text("fake")
        monkeypatch.chdir(tmp_path)

        with patch.object(tufup_updater.os.path, "exists", return_value=True), \
             patch.object(tufup_updater, "_make_client") as mock_make:
            mock_make.side_effect = ConnectionError("network down")

            has, ver = tufup_updater.check_update()

        assert has is False
        assert ver is None


class TestDownloadAndInstall:
    def test_dev_mode_returns_false(self, tmp_path, monkeypatch):
        """开发模式无法安装, 返回 False."""
        monkeypatch.chdir(tmp_path)
        assert tufup_updater.download_and_install() is False

    def test_no_updates_available(self, tmp_path, monkeypatch):
        """client.updates_available=False 时返回 False."""
        (tmp_path / "Seraphine.exe").write_text("fake")
        monkeypatch.chdir(tmp_path)

        with patch.object(tufup_updater, "_make_client") as mock_make:
            mock_client = MagicMock()
            mock_client.updates_available = False
            mock_make.return_value = mock_client

            result = tufup_updater.download_and_install()

        assert result is False

    def test_install_success(self, tmp_path, monkeypatch):
        """updates_available=True 且 download_and_apply_update 不抛 → 返回 True."""
        (tmp_path / "Seraphine.exe").write_text("fake")
        monkeypatch.chdir(tmp_path)

        with patch.object(tufup_updater, "_make_client") as mock_make:
            mock_client = MagicMock()
            mock_client.updates_available = True
            mock_client.download_and_apply_update = MagicMock()
            mock_make.return_value = mock_client

            result = tufup_updater.download_and_install()

        assert result is True
        mock_client.download_and_apply_update.assert_called_once()

    def test_install_failure_safe(self, tmp_path, monkeypatch):
        """download_and_apply_update 抛异常 → 返回 False, 不向上抛."""
        (tmp_path / "Seraphine.exe").write_text("fake")
        monkeypatch.chdir(tmp_path)

        with patch.object(tufup_updater, "_make_client") as mock_make:
            mock_client = MagicMock()
            mock_client.updates_available = True
            mock_client.download_and_apply_update.side_effect = RuntimeError(
                "install failed")
            mock_make.return_value = mock_client

            result = tufup_updater.download_and_install()

        assert result is False

    def test_progress_hook_passed_through(self, tmp_path, monkeypatch):
        """progress_hook 参数被透传给 download_and_apply_update."""
        (tmp_path / "Seraphine.exe").write_text("fake")
        monkeypatch.chdir(tmp_path)

        captured_kwargs = {}

        def fake_download_and_apply(**kwargs):
            captured_kwargs.update(kwargs)

        with patch.object(tufup_updater, "_make_client") as mock_make:
            mock_client = MagicMock()
            mock_client.updates_available = True
            mock_client.download_and_apply_update = fake_download_and_apply
            mock_make.return_value = mock_client

            def my_hook(d, t):
                pass

            tufup_updater.download_and_install(progress_hook=my_hook)

        assert captured_kwargs.get("progress_hook") is my_hook

    def test_purge_dst_dir_default_true(self, tmp_path, monkeypatch):
        """默认 purge_dst_dir=True (清空安装目录, 解决 filelist.txt 遗留问题)."""
        (tmp_path / "Seraphine.exe").write_text("fake")
        monkeypatch.chdir(tmp_path)

        captured_kwargs = {}

        def fake_download_and_apply(**kwargs):
            captured_kwargs.update(kwargs)

        with patch.object(tufup_updater, "_make_client") as mock_make:
            mock_client = MagicMock()
            mock_client.updates_available = True
            mock_client.download_and_apply_update = fake_download_and_apply
            mock_make.return_value = mock_client

            tufup_updater.download_and_install()

        assert captured_kwargs.get("purge_dst_dir") is True


class TestGetCurrentVersion:
    def test_returns_config_version(self):
        """get_current_version 返回 config.VERSION."""
        assert tufup_updater.get_current_version() == "1.1.9"
