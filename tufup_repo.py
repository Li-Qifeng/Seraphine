"""
tufup 服务端仓库管理脚本 (CI 中调用).

替代手动维护 tufup metadata 的繁琐操作, 提供:
- init:        初始化仓库 (生成签名密钥 + root.json), 幂等
- add-bundle:  添加新版本 (生成 tar.gz 全量包 + bsdiff 增量 patch), 签名发布
- pack-keys:   把 keys_dir 打包成 base64 (存入 GitHub secret)
- unpack-keys: 从 base64 还原 keys_dir (CI 运行时从 secret 取出)

== 整体流程 ==

仓库结构 (部署到 gh-pages 分支的 tufup/ 目录下):
    tufup/
      metadata/   root.json, 1.root.json, targets.json, snapshot.json, timestamp.json
      targets/    Seraphine-<ver>.tar.gz, Seraphine-<ver>.patch

签名密钥 (私有, 存 CI secret TUFUP_KEYS_B64, 不入仓库):
    keys/  root, root.pub, targets, targets.pub, snapshot, snapshot.pub, timestamp, timestamp.pub

客户端 trusted root (随应用分发): app/resource/tufup/metadata/root.json

== 首次引导 (bootstrap) ==

tufup 客户端必须随包带 root.json 才能校验更新. 首次启用 tufup 前, 开发者需本地跑一次:
    python tufup_repo.py init -r repo -k keys
    python tufup_repo.py pack-keys -k keys          # 输出 base64, 存为 secret TUFUP_KEYS_B64
    cp repo/metadata/root.json app/resource/tufup/metadata/root.json
    git add app/resource/tufup/metadata/root.json && git commit
随后 CI 即可正常 add-bundle + 发布到 gh-pages.

== CI 调用 (build_seraphine.yaml 的 publish-tufup job) ==

    # 1. 从 secret 还原密钥
    python tufup_repo.py unpack-keys -b "$TUFUP_KEYS_B64" -k keys
    # 2. 初始化 (密钥已存在则跳过创建)
    python tufup_repo.py init -r tufup_repo -k keys
    # 3. 添加新版本 (dist/Seraphine 为 PyInstaller onedir 产物)
    python tufup_repo.py add-bundle -v 1.2.0 -d dist/Seraphine -r tufup_repo -k keys
    # 4. 部署 tufup_repo/{metadata,targets} 到 gh-pages/tufup/ (peaceiris/actions-gh-pages)
"""
import argparse
import base64
import builtins
import io
import pathlib
import sys
import tarfile
from contextlib import contextmanager

APP_NAME = "Seraphine"


@contextmanager
def _noninteractive_input():
    """临时把 builtins.input 替换为始终返回 'n'.

    tufup 的 Keys.create_key_pair 在公钥已存在时会 input('Overwrite key pair?
    [n]/y') 询问是否覆盖. CI 非交互环境下 input() 抛 EOFError. 这里统一返回 'n'
    (不覆盖), 因为:
    - 首次运行: 公钥文件不存在, 根本不会走到 input, 正常创建密钥
    - 后续运行: 密钥已从 secret 还原, 不应覆盖, 返回 'n' 正确保留旧密钥

    返回 'n' 也顺带覆盖 make_gztar_archive 的归档已存在提示 (复用已有归档).
    """
    original = builtins.input
    builtins.input = lambda *a, **k: "n"
    try:
        yield
    finally:
        builtins.input = original


def _make_repository(repo_dir, keys_dir):
    """构造 tufup Repository 实例. 延迟 import: 本脚本只在 CI/开发机跑, 但延迟
    import 可让 --help 等不依赖 tufup 的子命令在缺包时也能解析参数."""
    from tufup.repo import Repository

    return Repository(
        app_name=APP_NAME,
        app_version_attr=None,  # 用 add_bundle 的 new_version 显式传版本, 不读模块属性
        repo_dir=pathlib.Path(repo_dir),
        keys_dir=pathlib.Path(keys_dir),
    )


def cmd_init(args):
    """初始化 tufup 仓库: 创建密钥 (若缺) + root metadata (若缺). 幂等."""
    repo = _make_repository(args.repo_dir, args.keys_dir)
    with _noninteractive_input():
        repo.initialize()
    root_json = pathlib.Path(args.repo_dir) / "metadata" / "root.json"
    keys_dir = pathlib.Path(args.keys_dir)
    print(f"[init] repo_dir: {args.repo_dir}")
    print(f"[init] keys_dir: {args.keys_dir}")
    print(f"[init] root.json: {root_json}")
    if not root_json.exists():
        print("[init] WARNING: root.json not created", file=sys.stderr)
        return 1
    # 列出密钥文件, 便于确认
    key_files = sorted(p.name for p in keys_dir.glob("*"))
    print(f"[init] keys: {key_files}")
    print("[init] done. 若为首次引导, 请执行 pack-keys 并将输出存为 secret,")
    print("[init]       并把 root.json 复制到 app/resource/tufup/metadata/.")
    return 0


def cmd_add_bundle(args):
    """添加新版本到仓库并签名发布.

    幂等: 若该版本 tar.gz 已存在则跳过 (避免重复注册 target / 重复生成 patch).
    """
    repo_dir = pathlib.Path(args.repo_dir)
    targets_dir = repo_dir / "targets"
    targets_dir.mkdir(parents=True, exist_ok=True)

    # 预期归档文件名: Seraphine-<version>.tar.gz
    archive_path = targets_dir / f"{APP_NAME}-{args.version}.tar.gz"
    if archive_path.exists():
        print(f"[add-bundle] {archive_path.name} already published, skip.")
        return 0

    bundle_dir = pathlib.Path(args.bundle_dir)
    if not bundle_dir.is_dir():
        print(f"[add-bundle] ERROR: bundle dir not found: {bundle_dir}",
              file=sys.stderr)
        return 1

    repo = _make_repository(args.repo_dir, args.keys_dir)
    with _noninteractive_input():
        repo.initialize()  # 幂等: 加载已有密钥/roles (input 被屏蔽, 不会覆盖密钥)
        print(f"[add-bundle] adding {bundle_dir} as version {args.version}")
        repo.add_bundle(
            new_bundle_dir=bundle_dir,
            new_version=args.version,
            skip_patch=args.skip_patch,
        )
        repo.publish_changes(private_key_dirs=[pathlib.Path(args.keys_dir)])
    print(f"[add-bundle] published. targets: {sorted(p.name for p in targets_dir.glob('*'))}")
    return 0


def cmd_pack_keys(args):
    """把 keys_dir 打包成 base64 字符串 (输出到 stdout), 供存为 GitHub secret."""
    keys_dir = pathlib.Path(args.keys_dir)
    if not keys_dir.is_dir():
        print(f"[pack-keys] ERROR: keys_dir not found: {keys_dir}",
              file=sys.stderr)
        return 1
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for p in sorted(keys_dir.rglob("*")):
            if p.is_file():
                tar.add(p, arcname=p.relative_to(keys_dir))
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    print(encoded)
    return 0


def cmd_unpack_keys(args):
    """从 base64 字符串还原 keys_dir (CI 运行时从 secret 取出)."""
    keys_dir = pathlib.Path(args.keys_dir)
    keys_dir.mkdir(parents=True, exist_ok=True)
    raw = base64.b64decode(args.base64)
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tar:
        # 校验成员落在 keys_dir 内, 防止路径穿越
        for member in tar.getmembers():
            member_path = (keys_dir / member.name).resolve()
            if not str(member_path).startswith(str(keys_dir.resolve())):
                print(f"[unpack-keys] ERROR: unsafe path in archive: {member.name}",
                      file=sys.stderr)
                return 1
        tar.extractall(keys_dir)
    print(f"[unpack-keys] restored keys to {keys_dir}: "
          f"{sorted(p.name for p in keys_dir.glob('*'))}")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        description="tufup 服务端仓库管理 (CI 中发布增量更新)."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="初始化仓库 (生成密钥 + root.json)")
    p_init.add_argument("-r", "--repo-dir", required=True,
                        help="tufup 仓库目录 (含 metadata/ targets/)")
    p_init.add_argument("-k", "--keys-dir", required=True,
                        help="签名密钥目录 (私有, 不入仓库)")
    p_init.set_defaults(func=cmd_init)

    p_add = sub.add_parser("add-bundle", help="添加新版本并签名发布")
    p_add.add_argument("-v", "--version", required=True,
                       help="新版本号 (如 1.2.0, 不带 v 前缀)")
    p_add.add_argument("-d", "--bundle-dir", required=True,
                       help="应用 bundle 目录 (PyInstaller onedir 产物)")
    p_add.add_argument("-r", "--repo-dir", required=True, help="tufup 仓库目录")
    p_add.add_argument("-k", "--keys-dir", required=True, help="签名密钥目录")
    p_add.add_argument("--skip-patch", action="store_true",
                       help="不生成 bsdiff patch (仅全量包)")
    p_add.set_defaults(func=cmd_add_bundle)

    p_pack = sub.add_parser("pack-keys", help="密钥目录 -> base64 (存 secret)")
    p_pack.add_argument("-k", "--keys-dir", required=True, help="签名密钥目录")
    p_pack.set_defaults(func=cmd_pack_keys)

    p_unpack = sub.add_parser("unpack-keys", help="base64 -> 还原密钥目录")
    p_unpack.add_argument("-b", "--base64", required=True,
                          help="pack-keys 输出的 base64 字符串")
    p_unpack.add_argument("-k", "--keys-dir", required=True, help="目标密钥目录")
    p_unpack.set_defaults(func=cmd_unpack_keys)

    return parser


def main():
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
