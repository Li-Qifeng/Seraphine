"""
tufup 客户端封装: 基于 TUF 安全标准的增量更新.

替代旧的 7z + updater.ps1 全量替换流程, 改为:
1. 从 GitHub Pages 拉 tufup metadata (targets.json/snapshot.json/timestamp.json)
2. 检查是否有新版本 (语义化比较)
3. 优先走 patch 链 (bsdiff 增量), patch 总和 > 80% 全量时退化全量
4. 下载 → 解压 → install_update (Windows 上生成 bat 替换文件 + 重启)

设计要点:
- 不依赖 PyQt5: check_update/download_and_install 均为纯 Python, progress 通过
  回调通知调用方, 由 message_box.py 桥接到 ProgressBar
- 开发模式 (无 Seraphine.exe) 禁用更新, 避免覆盖源码
- metadata_dir 随应用分发 (app/resource/tufup/metadata/root.json), 只含 trusted
  root, 其他 metadata 从远端拉
- target_dir / extract_dir 放 %APPDATA%/Seraphine/, 避免污染安装目录
"""
import os
import pathlib
from typing import TYPE_CHECKING, Callable, Optional, Tuple

from app.common.config import VERSION, LOCAL_PATH

if TYPE_CHECKING:
    # 仅类型注解用, 运行时延迟 import 避免未安装时模块加载失败
    from tufup.client import Client

from app.common.logger import logger

# tufup repo 地址 (gh-pages 分支). metadata 和 targets 分别托管.
# gh-pages 分支结构: tufup/{metadata,targets}/
#
# metadata / targets 统一用 raw.githubusercontent.com.
# jsDelivr CDN 因缓存策略时常提供过期 metadata, 且 targets 超过其 20MB 限制,
# 故全部走 GitHub raw 直连.
# ponytail: 改 fork 时同步修改 owner/repo
DEFAULT_METADATA_BASE_URL = (
    "https://raw.githubusercontent.com/Li-Qifeng/Seraphine/gh-pages/tufup/metadata/"
)
DEFAULT_TARGET_BASE_URL = (
    "https://raw.githubusercontent.com/Li-Qifeng/Seraphine/gh-pages/tufup/targets/"
)

APP_NAME = "Seraphine"

# 下载缓存与解压临时目录, 放 %APPDATA%/Seraphine/ 下
_TARGET_DIR = os.path.join(LOCAL_PATH, "tufup_targets")
_EXTRACT_DIR = os.path.join(LOCAL_PATH, "tufup_extract")


def _get_app_install_dir() -> Optional[pathlib.Path]:
    """
    获取 Seraphine 安装目录 (Seraphine.exe 所在目录).

    main.py 启动时 os.chdir 到 exe 所在目录, 故 os.getcwd() 即安装目录.
    开发模式 (python main.py, 无 Seraphine.exe) 返回 None, 调用方应据此禁用更新.
    """
    exe_path = os.path.join(os.getcwd(), "Seraphine.exe")
    if os.path.exists(exe_path):
        return pathlib.Path(os.getcwd())
    return None


def _bundled_metadata_dir(install_dir: pathlib.Path) -> pathlib.Path:
    """
    随应用分发的 trusted root metadata 目录.

    返回 <install_dir>/app/resource/tufup/metadata/. make.ps1 把 app/ 复制进
    安装目录, root.json 作为 loose 文件随之分发.

    注意: 用 install_dir 而非 __file__ 定位. PyInstaller frozen 后 __file__ 指向
    bundled bytecode 的内部路径 (非 loose 源码), 用 __file__ 算相对路径会找不到
    root.json. install_dir 来自 os.getcwd() (main.py 已 chdir 到 exe 目录), 可靠.
    """
    return install_dir / "app" / "resource" / "tufup" / "metadata"


def _make_client(install_dir: pathlib.Path) -> "Client":  # type: ignore[name-defined]
    """构造 tufup Client 实例. 延迟 import 避免 tufup 未安装时模块加载失败."""
    from tufup.client import Client

    metadata_dir = _bundled_metadata_dir(install_dir)
    target_dir = pathlib.Path(_TARGET_DIR)
    extract_dir = pathlib.Path(_EXTRACT_DIR)

    # 确保目录存在
    target_dir.mkdir(parents=True, exist_ok=True)
    extract_dir.mkdir(parents=True, exist_ok=True)

    return Client(
        app_name=APP_NAME,
        app_install_dir=install_dir,
        current_version=VERSION,
        metadata_dir=metadata_dir,
        metadata_base_url=DEFAULT_METADATA_BASE_URL,
        target_dir=target_dir,
        target_base_url=DEFAULT_TARGET_BASE_URL,
        extract_dir=extract_dir,
    )


def check_update() -> Tuple[bool, Optional[str]]:
    """
    检查是否有可用更新.

    Returns:
        (has_update, new_version): has_update 为 True 时 new_version 是新版本号
        (如 "1.2.0"), 否则 (False, None).

    开发模式 / tufup 未配置 / 网络失败时返回 (False, None), 不抛异常.
    """
    install_dir = _get_app_install_dir()
    if install_dir is None:
        logger.info("development mode (Seraphine.exe not found), "
                    "skip update check")
        return False, None

    # 检查 bundled root.json 是否存在 (首次分发必须随包带)
    root_json = _bundled_metadata_dir(install_dir) / "root.json"
    if not root_json.exists():
        logger.warning(
            f"root.json not found at {root_json}, tufup not initialized")
        return False, None

    try:
        client = _make_client(install_dir)
        new_archive_meta = client.check_for_updates(patch=True)
        if new_archive_meta is not None:
            new_version = str(new_archive_meta.version)
            logger.info(f"update available: {VERSION} -> {new_version}")
            return True, new_version
        logger.info("no update available")
        return False, None
    except Exception as e:
        # tufup 网络失败 / metadata 解析失败等, 不阻塞应用启动
        logger.warning(f"check_update failed: {e}")
        return False, None


def download_and_install(
    progress_hook: Optional[Callable] = None,
    purge_dst_dir: bool = True,
    exclude_from_purge: Optional[list] = None,
) -> bool:
    """
    下载并安装更新. 调用前应先调用 check_update() 且确认有更新.

    tufup 默认的 install_update (Windows) 会:
    1. 下载 patch/full archive
    2. 解压到 extract_dir
    3. 生成 bat 脚本: 等待主进程退出 → purge 安装目录 → 移入新版 → 重启
    4. 主进程调用 sys.exit() (我们改为由调用方做 QApplication.quit())

    Args:
        progress_hook: 下载进度回调, 签名 (bytes_done: int, bytes_total: int)
        purge_dst_dir: 是否清空安装目录再移入新版. 默认 True (Seraphine 装在
            独立目录, 安全). 这解决了旧 filelist.txt 无法清理用户手动加文件
            的问题.
        exclude_from_purge: purge 时保留的路径列表 (如用户配置文件)

    Returns:
        True 表示更新已触发 (主进程应退出), False 表示失败 (未触发更新).

    Raises:
        仅在不可恢复错误时抛出 (如 tufup 未安装). 常见失败已 log 并返回 False.
    """
    install_dir = _get_app_install_dir()
    if install_dir is None:
        logger.warning("cannot install update in development mode")
        return False

    try:
        client = _make_client(install_dir)
        if not client.updates_available:
            logger.warning("no updates available, call check_update first")
            return False

        client.download_and_apply_update(
            skip_confirmation=True,
            progress_hook=progress_hook,
            purge_dst_dir=purge_dst_dir,
            exclude_from_purge=exclude_from_purge,
        )
        return True
    except Exception as e:
        logger.exception("download_and_install failed", e)
        return False


def get_current_version() -> str:
    """返回当前应用版本 (供调试 / 日志用)."""
    return VERSION
