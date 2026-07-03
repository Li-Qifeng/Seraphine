"""Debug script: run update check without Qt GUI.

Bypasses qfluentwidgets import (which hangs outside QApplication).
Output to stderr.

Usage:
    python -m app.debug_update
    $env:SERAPHINE_DEV_VERSION="0.0.1"; python -m app.debug_update
"""
import json
import logging
import os
import sys

# 绕开 qfluentwidgets 导入, 直接构造 Github 实例
os.environ.setdefault("SERAPHINE_CONFIG_DIR", os.path.join(os.path.dirname(__file__), "..", "config"))

# 注入 VERSION (与 config.py 相同的逻辑)
VERSION = os.environ.get("SERAPHINE_DEV_VERSION") or "1.2.8"

# 简易 logger, 输出到 stderr
logger = logging.getLogger("DebugUpdate")
logger.setLevel(logging.INFO)
console = logging.StreamHandler(sys.stderr)
console.setFormatter(logging.Formatter('%(asctime)s - [%(name)s] %(levelname)s - %(message)s'))
logger.addHandler(console)

# 直接从 util 引用, 但只取 Github 类, 绕过 config 导入
TAG = "DebugUpdate"

try:
    import requests
    from packaging.version import InvalidVersion, parse as parse_version
except ImportError as e:
    logger.error(f"missing dependency: {e}")
    sys.exit(2)


def coerce_version(v: str):
    if not v:
        return None
    s = v.lstrip('v').strip()
    try:
        return parse_version(s)
    except InvalidVersion:
        return s


class Github:
    def __init__(self, user="Li-Qifeng", repositories="Seraphine"):
        self.githubApi = "https://api.github.com"
        self.user = user
        self.repositories = repositories
        self.sess = requests.session()
        self._release_info = None
        self._ver_info = None

    def getReleasesInfo(self):
        if self._release_info is not None:
            logger.info("getReleasesInfo: cache HIT")
            return self._release_info
        url = f"{self.githubApi}/repos/{self.user}/{self.repositories}/releases/latest"
        logger.info(f"getReleasesInfo: GET {url}")
        resp = self.sess.get(url, headers={'User-Agent': f'Seraphine/{VERSION}'}, timeout=15)
        logger.info(f"getReleasesInfo: status={resp.status_code} url={resp.url}")
        data = resp.json()
        if isinstance(data, dict) and "message" in data and "rate limit" in data["message"].lower():
            logger.warning(f"GitHub API rate limited: {data['message']}")
            return {}
        logger.info(f"getReleasesInfo: keys={list(data.keys()) if isinstance(data, dict) else 'not-dict'}")
        if isinstance(data, dict) and "tag_name" in data:
            self._release_info = data
        return data

    def _make_update_info(self, new_version: str) -> dict:
        logger.info(f"_make_update_info: new_version={new_version}")
        info = {"tag_name": f"v{new_version}", "new_version": new_version, "body": "", "forbidden": False}
        try:
            release_info = self.getReleasesInfo()
            matched = release_info.get("tag_name", "").lstrip('v') == new_version
            logger.info(f"  matched_tag={matched} body_len={len(release_info.get('body', ''))} has_assets={'assets' in release_info}")
            if matched:
                info["body"] = release_info.get("body", "")
                if "assets" in release_info:
                    info["assets"] = release_info["assets"]
        except Exception as e:
            logger.warning(f"failed to fetch release info for body: {e}")
        return info

    def checkUpdate(self):
        logger.info("checkUpdate: tufup check skipped (standalone mode)")
        logger.info("checkUpdate: falling back to GitHub API")
        try:
            release_info = self.getReleasesInfo()
            logger.info(f"checkUpdate: release_info keys={list(release_info.keys()) if isinstance(release_info, dict) else 'not-dict'}")
            latest_tag = release_info.get("tag_name", "").lstrip('v')
            logger.info(f"checkUpdate: latest_tag='{latest_tag}' VERSION='{VERSION}'")
            if latest_tag and latest_tag != VERSION:
                c1, c2 = coerce_version(latest_tag), coerce_version(VERSION)
                logger.info(f"checkUpdate: coerce {latest_tag} -> {c1}, {VERSION} -> {c2}, {c1} > {c2} = {c1 > c2}")
                if c1 > c2:
                    logger.info(f"update available (GitHub API): {VERSION} -> {latest_tag}")
                    return self._make_update_info(latest_tag)
        except Exception as e:
            logger.warning(f"GitHub API fallback check failed: {e}")
        logger.info("no update available")
        return None


logger.info(f"VERSION={VERSION}")
logger.info(f"SERAPHINE_DEV_VERSION={os.environ.get('SERAPHINE_DEV_VERSION', '(not set)')}")

github = Github()
result = github.checkUpdate()

logger.info(f"checkUpdate returned: {result}")
if result is None:
    logger.info("RESULT: no update")
elif isinstance(result, dict):
    logger.info(f"RESULT: update available keys={list(result.keys())}")
    for k, v in result.items():
        logger.info(f"  {k}={v}")
    logger.info(f"\n>>> new_version={result.get('new_version')}")
    logger.info(f">>> tag_name={result.get('tag_name')}")
    logger.info(f">>> body_len={len(result.get('body', ''))}")
    logger.info(f">>> forbidden={result.get('forbidden')}")

sys.exit(0 if result else 1)