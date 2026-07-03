import json
import os
import re
import winreg
from pathlib import Path

import requests
import base64
import subprocess
import psutil
import win32api
import win32gui

from PyQt5.QtCore import QRectF

from app.common.config import cfg, VERSION
from app.common.logger import logger


TAG = "Util"


class Github:
    # 二次开发: 默认指向当前维护者的 fork 仓库, 用于 Release / 公告 / ver.json 拉取
    def __init__(self, user="Li-Qifeng", repositories="Seraphine"):
        self.githubApi = "https://api.github.com"

        self.user = user
        self.repositories = repositories
        self.sess = requests.session()
        self._release_info = None
        self._ver_info = None

    def __proxy(self):
        """
        构建代理字典。开启代理时同时为 http/https 两种协议注入
        (旧代码只设了 'https' 键，对当时的 http:// 地址其实从未生效)
        """
        if cfg.get(cfg.enableProxy):
            addr = cfg.get(cfg.proxyAddr)
            return {'http': addr, 'https': addr}
        return None

    def __headers(self):
        # GitHub API 要求带 User-Agent，匿名 UA 偶发被拒
        return {'User-Agent': f'Seraphine/{VERSION}'}

    def getReleasesInfo(self):
        if self._release_info is not None:
            return self._release_info
        url = f"{self.githubApi}/repos/{self.user}/{self.repositories}/releases/latest"
        # debug
        logger.info(f"getReleasesInfo: GET {url}", TAG)
        resp = self.sess.get(url, proxies=self.__proxy(),
                             headers=self.__headers(),
                             timeout=15)
        # debug
        logger.info(f"getReleasesInfo: status={resp.status_code} url={resp.url}", TAG)
        data = resp.json()
        # ponytail: 无认证 GitHub API 60 req/h 限流, 检测到限流 response 时
        # log warning 并返回空 dict, 避免静默按"无更新"处理.
        # 不缓存失败响应 — 否则首次限流后所有后续 checkUpdate 都命中缓存 {}
        # 永远返回"已是最新", 用户手动点检查也看不到更新.
        if isinstance(data, dict) and "message" in data and "rate limit" in data["message"].lower():
            logger.warning(f"GitHub API rate limited: {data['message']}", TAG)
            return {}
        # debug
        logger.info(f"getReleasesInfo: result_type={type(data).__name__} keys={list(data.keys()) if isinstance(data, dict) else 'not-dict'}", TAG)
        # 只缓存有效 release 数据 (含 tag_name), 避免错误响应被缓存
        if isinstance(data, dict) and "tag_name" in data:
            self._release_info = data
        return data

    def checkUpdate(self, force_refresh=False):
        """
        检查版本更新 (基于 tufup 增量更新框架).

        流程:
        1. tufup_updater.check_update() 从 GitHub Pages 拉取 tufup metadata,
           做语义化版本比较 (有更新可走增量 patch 下载).
        2. tufup 检测成功时直接返回; tufup 检测为无更新或失败时, **总是**回退到
           GitHub Releases API 做权威判定.
           背景: tufup metadata 可能滞后 (CI 发布失败), raw.githubusercontent 国内
           不可达, root.json 过期等都会导致 tufup 漏检. GitHub Releases API 是
           新版本发布的权威来源, 且 api.github.com 国内可达性更好. 不能让 tufup
           失败静默吞掉更新通知.
        3. GitHub API 回退也确认无更新 -> 返回 None.

        @param force_refresh: True 时清除 release/ver 缓存, 强制重新拉取.
            手动点击检查更新时应传 True, 避免启动时限流缓存的空 dict 毒化后续结果.
        @return: 有更新 -> info dict (含 tag_name/body/forbidden/new_version),
                 无更新 / 失败 -> None
        """
        from app.common.tufup_updater import check_update as tufup_check

        if force_refresh:
            self._release_info = None
            self._ver_info = None

        # debug
        logger.info("checkUpdate: tufup_check() start", TAG)
        has_update, new_version = tufup_check()
        # debug
        logger.info(f"checkUpdate: tufup has_update={has_update} new_version={new_version}", TAG)
        if has_update and new_version:
            return self._make_update_info(new_version)

        # debug
        logger.info("checkUpdate: tufup gave no update, falling back to GitHub API", TAG)
        # GitHub Releases API 权威回退: tufup 漏检时由 GitHub API 兜底.
        # 这是修复生产环境更新不可见的根因 — 旧代码仅 dev mode 走此分支,
        # 生产模式 tufup 任何失败都会静默返回 None, 用户收不到更新通知.
        try:
            release_info = self.getReleasesInfo()
            # debug
            logger.info(f"checkUpdate: release_info keys={list(release_info.keys()) if isinstance(release_info, dict) else 'not-dict'}", TAG)
            latest_tag = release_info.get("tag_name", "").lstrip('v')
            # debug
            logger.info(f"checkUpdate: latest_tag='{latest_tag}' VERSION='{VERSION}'", TAG)
            if latest_tag and latest_tag != VERSION:
                from app.common.version_utils import coerce_version
                c1 = coerce_version(latest_tag)
                c2 = coerce_version(VERSION)
                # debug
                logger.info(f"checkUpdate: coerce {latest_tag} -> {c1}, {VERSION} -> {c2}, {c1} > {c2} = {c1 > c2}", TAG)
                if c1 > c2:
                    logger.info(
                        f"update available (GitHub API fallback): "
                        f"{VERSION} -> {latest_tag}", TAG)
                    return self._make_update_info(latest_tag)
        except Exception as e:
            logger.warning(f"GitHub API fallback update check failed: {e}",
                           TAG)

        logger.info("no update available", TAG)
        return None

    def _make_update_info(self, new_version: str) -> dict:
        """构建 info dict 供 UpdateMessageBox 显示."""
        # debug
        logger.info(f"_make_update_info: new_version={new_version}", TAG)
        info = {
            "tag_name": f"v{new_version}",
            "new_version": new_version,
            "body": "",
            "forbidden": False,
        }

        try:
            release_info = self.getReleasesInfo()
            matched = release_info.get("tag_name", "").lstrip('v') == new_version
            # debug
            logger.info(f"_make_update_info: matched_tag={matched} body_len={len(release_info.get('body', ''))} has_assets={'assets' in release_info}", TAG)
            if matched:
                info["body"] = release_info.get("body", "")
                if "assets" in release_info:
                    info["assets"] = release_info["assets"]
        except Exception as e:
            logger.warning(f"failed to fetch release info for body: {e}", TAG)

        try:
            ver_info = self.__get_ver_info()
            info["forbidden"] = ver_info.get("forbidden", False)
            # debug
            logger.info(f"_make_update_info: forbidden={info['forbidden']}", TAG)
        except Exception as e:
            logger.warning(f"failed to fetch ver.json kill-switch: {e}", TAG)

        return info

    def __get_ver_info(self):
        if self._ver_info is not None:
            return self._ver_info.get(VERSION, {})
        url = f'{self.githubApi}/repos/{self.user}/{self.repositories}/contents/document/ver.json'
        # debug
        logger.info(f"__get_ver_info: GET {url}", TAG)
        res = self.sess.get(url, proxies=self.__proxy(),
                            headers=self.__headers(),
                            timeout=15).json()
        # debug
        logger.info(f"__get_ver_info: response_keys={list(res.keys()) if isinstance(res, dict) else 'not-dict'}", TAG)
        raw = json.loads(
            str(base64.b64decode(res['content']), encoding='utf-8'))
        self._ver_info = raw
        return raw.get(VERSION, {})

    def getNotice(self):
        url = f'{self.githubApi}/repos/{self.user}/{self.repositories}/contents/document/notice.md'

        res = self.sess.get(url, proxies=self.__proxy(),
                            headers=self.__headers(),
                            timeout=15).json()

        content = str(base64.b64decode(res['content']), encoding='utf-8')

        return {
            'sha': res['sha'],
            'content': content,
        }


github = Github()


def getLoLPathByRegistry() -> str:
    """
    从注册表获取LOL的安装路径

    ** 只能获取到国服的路径, 外服不支持 **

    无法获取时返回空串
    """
    mainKey = winreg.HKEY_CURRENT_USER
    subKey = r"SOFTWARE\Tencent\LOL"
    valueName = "InstallPath"

    try:
        with winreg.OpenKey(mainKey, subKey) as k:
            installPath, _ = winreg.QueryValueEx(k, valueName)
            path = str(Path(rf"{installPath}\TCLS").absolute()
                       ).replace("\\", "/")
            return f"{path[:1].upper()}{path[1:]}"
    except FileNotFoundError:
        logger.warning("reg path or val does not exist.", TAG)
    except WindowsError as e:
        logger.warning(f"occurred while reading the registry: {e}", TAG)
    except Exception as e:
        logger.exception("unknown error reading registry", e, TAG)

    return ""


def getTasklistPath():
    for path in ['tasklist',
                 'C:/Windows/System32/tasklist.exe']:
        try:
            cmd = f'{path} /FI "imagename eq LeagueClientUx.exe" /NH'
            _ = subprocess.check_output(cmd, shell=True)
            return path
        except (subprocess.CalledProcessError, OSError):
            pass

    return None


def getLolClientPidSlowly():
    for process in psutil.process_iter():
        if process.name() in ['LeagueClientUx.exe', 'LeagueClientUx']:
            return process.pid

    return -1


def getLolClientPid(path):
    processes = subprocess.check_output(
        f'{path} /FI "imagename eq LeagueClientUx.exe" /NH', shell=True)

    if b'LeagueClientUx.exe' in processes:
        arr = processes.split()
        try:
            pos = arr.index(b"LeagueClientUx.exe")
            return int(arr[pos + 1])
        except ValueError:
            raise ValueError(f"Subprocess return exception: {processes}")
    else:
        return 0


def getLolClientPids(path):
    """
    获取所有 LeagueClientUx.exe 进程的 pid 列表。

    tasklist 通过 shell 起子进程时偶尔会抛 PermissionError / OSError
    (见 issue #367), 这里捕获后回退到 psutil 慢速枚举, 避免监听线程整个崩溃。
    """
    try:
        processes = subprocess.check_output(
            f'{path} /FI "imagename eq LeagueClientUx.exe" /NH',
            shell=True,
            stderr=subprocess.STDOUT
        )
    except subprocess.CalledProcessError as e:
        logger.error(
            'an error occurred when calling tasklist command, '
            f'original output: {e.output.decode() if e.output else ""}'
        )
        return getLolClientPidsSlowly()
    except (PermissionError, OSError, FileNotFoundError) as e:
        # tasklist 子进程启动失败 (Windows 上 fork/exec 偶发), 回退 psutil
        logger.warning(
            f'tasklist subprocess failed, fallback to psutil: {e}', TAG)
        return getLolClientPidsSlowly()

    pids = []

    if b'LeagueClientUx.exe' not in processes:
        return pids

    arr = processes.split()

    for i, s in enumerate(arr):
        if s == b'LeagueClientUx.exe':
            pids.append(int(arr[i + 1]))

    return pids


def getLolClientPidsSlowly():
    pids = []

    for process in psutil.process_iter():
        if process.name() in ['LeagueClientUx.exe', 'LeagueClientUx']:
            pids.append(process.pid)

    return pids


def isLolGameProcessExist(path):
    """
    判断游戏主程序 (League of Legends.exe) 是否在运行。

    tasklist 子进程可能间歇性失败 (issue #367), 失败时回退 psutil,
    宁可误判也不会让监听线程崩溃退出。
    """
    try:
        processes = subprocess.check_output(
            f'{path} /FI "imagename eq League of Legends.exe" /NH',
            shell=True, stderr=subprocess.STDOUT)
    except (PermissionError, OSError, FileNotFoundError,
            subprocess.CalledProcessError) as e:
        logger.warning(
            f'tasklist subprocess failed, fallback to psutil: {e}', TAG)
        for process in psutil.process_iter():
            try:
                if process.name() == 'League of Legends.exe':
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return False

    return b'League of Legends.exe' in processes


def getPortTokenServerByPidViaPsutil(pid):
    port, token, server = None, None, None

    process = psutil.Process(pid)
    cmdline = process.cmdline()

    for cmd in cmdline:

        p = cmd.find("--app-port=")
        if p != -1:
            port = cmd[11:]

        p = cmd.find("--remoting-auth-token=")
        if p != -1:
            token = cmd[22:]

        p = cmd.find("--rso_platform_id=")
        if p != -1:
            server = cmd[18:]

        if port and token and server:
            break

    return port, token, server


def getPortTokenServerByPidViaWmic():
    '''
    ### 需要管理员权限
    '''
    command = "wmic process WHERE name='LeagueClientUx.exe' GET commandline"
    output = subprocess.check_output(command, shell=True).decode("gbk")

    port = re.findall(r'--app-port=(.+?)"', output)[0]
    token = re.findall(r'--remoting-auth-token=(.+?)"', output)[0]
    server = re.findall(r'--rso_platform_id=(.+?)"', output)[0]

    return port, token, server


def getPortTokenServerByPid(pid):
    '''
    通过进程 id 获得启动命令行参数中的 port、token 以及登录服务器
    '''

    try:
        return getPortTokenServerByPidViaPsutil(pid)
    except Exception:
        return getPortTokenServerByPidViaWmic()


def getFileProperties(fname):
    """
    读取给定文件的所有属性, 返回一个字典.

    returns : {'FixedFileInfo': {'Signature': -17890115, 'StrucVersion': 65536, 'FileVersionMS': 917513, 'FileVersionLS':
    38012988, 'ProductVersionMS': 917513, 'ProductVersionLS': 38012988, 'FileFlagsMask': 23, 'FileFlags': 0,
    'FileOS': 4, 'FileType': 1, 'FileSubtype': 0, 'FileDate': None}, 'StringFileInfo': {'Comments': None,
    'InternalName': 'League of Legends (TM) Client', 'ProductName': 'League of Legends (TM) Client', 'CompanyName':
    'Riot Games, Inc.', 'LegalCopyright': 'Copyright (C) 2009', 'ProductVersion': '14.9.580.2108', 'FileDescription':
    'League of Legends (TM) Client', 'LegalTrademarks': None, 'PrivateBuild': None, 'FileVersion': '14.9.580.2108',
    'OriginalFilename': 'League of Legends.exe', 'SpecialBuild': None}, 'FileVersion': '14.9.580.2108'}

    """

    propNames = ('Comments', 'InternalName', 'ProductName',
                 'CompanyName', 'LegalCopyright', 'ProductVersion',
                 'FileDescription', 'LegalTrademarks', 'PrivateBuild',
                 'FileVersion', 'OriginalFilename', 'SpecialBuild')

    props = {'FixedFileInfo': None,
             'StringFileInfo': None, 'FileVersion': None}

    try:
        fixedInfo = win32api.GetFileVersionInfo(fname, '\\')
        props['FixedFileInfo'] = fixedInfo
        props['FileVersion'] = "%d.%d.%d.%d" % (fixedInfo['FileVersionMS'] / 65536,
                                                fixedInfo['FileVersionMS'] % 65536, fixedInfo['FileVersionLS'] / 65536,
                                                fixedInfo['FileVersionLS'] % 65536)

        # \VarFileInfo\Translation returns list of available (language, codepage)
        # pairs that can be used to retreive string info. We are using only the first pair.
        lang, codepage = win32api.GetFileVersionInfo(
            fname, '\\VarFileInfo\\Translation')[0]

        # any other must be of the form \StringfileInfo\%04X%04X\parm_name, middle
        # two are language/codepage pair returned from above

        strInfo = {}
        for propName in propNames:
            strInfoPath = u'\\StringFileInfo\\%04X%04X\\%s' % (
                lang, codepage, propName)
            strInfo[propName] = win32api.GetFileVersionInfo(fname, strInfoPath)

        props['StringFileInfo'] = strInfo
    except (win32api.error, KeyError):
        return {}
    else:
        return props


def getLolClientVersion():
    gamePath = cfg.get(cfg.lolFolder)[0]

    assert gamePath  # 必须有, 否则就是调用逻辑有问题 -- By Hpero4

    # 特判一下国服 -- By Hpero4
    gamePath = gamePath.replace("/TCLS", "")

    lolExe = f"{gamePath}/Game/League of Legends.exe"
    # 判断一下, 客户端特殊? 为啥会没有LOL的主程序 -- By Hpero4
    if not os.path.exists(lolExe):
        raise FileNotFoundError(lolExe)

    fileInfo = getFileProperties(lolExe).get("StringFileInfo", {})
    lolVer = fileInfo.get("ProductVersion") or fileInfo.get("FileVersion")

    assert lolVer

    # 缩短至大版本号
    return re.search(r"\d+\.\d+", lolVer).group(0)


def getLolClientWindowPos() -> QRectF:
    # 获取客户端窗口句柄
    hwnd = win32gui.FindWindow("RCLIENT", "League of Legends")

    # 如果没客户端，就直接 return 一个 None
    if not hwnd:
        return None

    # 获取客户端窗口位置
    # struct RECT {
    #     LONG left;
    #     LONG top;
    #     LONG right;
    #     LONG bottom;
    # }
    rect = win32gui.GetWindowRect(hwnd)

    # 窗口最小化的时候，比例不是 16:9，直接 return 一个 None
    if (rect[3] - rect[1]) / (rect[2] - rect[0]) != 0.5625:
        return None

    return QRectF(rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1])
