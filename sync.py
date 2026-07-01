"""
该模块用于在 GitHub 发布新 Release 时，同步上传到 Gitee 上.

改进点 (相对旧实现):
1. 幂等: 先按 tag 查 Gitee release, 已存在则复用, 不存在才创建.
   旧实现重复跑会因 release 已存在抛 HTTPError.
2. 同时上传 Seraphine.7z 和 Seraphine.7z.sha256 (供客户端 SHA256 校验).
3. --sha256 可选: 指定 .sha256 文件名, 默认 Seraphine.7z.sha256.

CI 集成: 在 .github/workflows/build_seraphine.yaml 的 release job 中,
GitHub Release 发布成功后调用 `python sync.py -t v1.1.9` 即可自动同步到 Gitee.
需配置 GITEE_* secrets.
"""

import argparse
import os
import requests

parser = argparse.ArgumentParser(
    description="sync GitHub Release to Gitee release (7z + sha256)."
)
parser.add_argument(
    "-t", "--tag", type=str, help="version tag of GitHub Release", required=True
)
parser.add_argument(
    "--sha256", type=str, default="Seraphine.7z.sha256",
    help="sha256 checksum file to upload (default: Seraphine.7z.sha256)"
)
args = parser.parse_args()

GITEE_OWNER = os.environ["GITEE_OWNER"]
GITEE_REPO = os.environ["GITEE_REPO"]
GITEE_USERNAME = os.environ["GITEE_USERNAME"]
GITEE_PASSWORD = os.environ["GITEE_PASSWORD"]
GITEE_CLIENT_ID = os.environ["GITEE_CLIENT_ID"]
GITEE_CLIENT_SECRET = os.environ["GITEE_CLIENT_SECRET"]

ACCESS_TOKEN = requests.post(
    "https://gitee.com/oauth/token",
    data={
        "grant_type": "password",
        "username": GITEE_USERNAME,
        "password": GITEE_PASSWORD,
        "client_id": GITEE_CLIENT_ID,
        "client_secret": GITEE_CLIENT_SECRET,
        "scope": "projects",
    },
).json()["access_token"]

TAG_NAME = args.tag
NAME = TAG_NAME
BODY = f"Seraphine {TAG_NAME}"
TARGET_COMMITISH = "master"
FILE_PATH = "Seraphine.7z"
SHA256_PATH = args.sha256

HEADERS = {"Authorization": f"Bearer {ACCESS_TOKEN}"}


def get_or_create_release(owner, repo):
    """
    幂等获取或创建 Gitee release.

    先按 tag 查; 已存在则返回其 id (复用), 避免重复跑报错.
    不存在才创建.
    """
    # 先查 tag 是否已有 release
    get_url = f"https://gitee.com/api/v5/repos/{owner}/{repo}/releases/tags/{TAG_NAME}"
    resp = requests.get(get_url, headers=HEADERS, timeout=30)
    if 200 <= resp.status_code < 300:
        print(f"release for tag {TAG_NAME} already exists, reusing.")
        return resp.json()["id"]
    if resp.status_code != 404:
        # 其他错误抛出
        print(resp.text)
        raise requests.HTTPError(
            f"query release by tag failed: {resp.status_code}")

    # 404 -> 创建
    url = f"https://gitee.com/api/v5/repos/{owner}/{repo}/releases"
    data = {
        "tag_name": TAG_NAME,
        "name": NAME,
        "body": BODY,
        "target_commitish": TARGET_COMMITISH,
    }
    response = requests.post(url, data=data, headers=HEADERS, timeout=30)
    if 200 <= response.status_code < 300:
        return response.json()["id"]
    else:
        print(response.json())
        raise requests.HTTPError("create release on gitee failed.")


def upload_file(owner, repo, release_id, file_path):
    """上传单个文件到 Gitee release, 返回下载 URL."""
    url = f"https://gitee.com/api/v5/repos/{owner}/{repo}/releases/{release_id}/attach_files"
    with open(file_path, "rb") as f:
        response = requests.post(
            url, files={"file": f}, headers=HEADERS, timeout=30)

    if 200 <= response.status_code < 300:
        return response.json()["browser_download_url"]
    else:
        print(response.json())
        raise requests.HTTPError(
            f"push {file_path} to Gitee failed.")


release_id = get_or_create_release(GITEE_OWNER, GITEE_REPO)

# 上传主包
download_url = upload_file(GITEE_OWNER, GITEE_REPO, release_id, FILE_PATH)
print(f"Seraphine.7z synced to Gitee: {download_url}")

# 上传 sha256 (best effort, 文件不存在则跳过)
if os.path.exists(SHA256_PATH):
    sha_url = upload_file(GITEE_OWNER, GITEE_REPO, release_id, SHA256_PATH)
    print(f"{SHA256_PATH} synced to Gitee: {sha_url}")
else:
    print(f"{SHA256_PATH} not found, skipping sha256 upload.")
