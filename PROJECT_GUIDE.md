# Seraphine 项目开发指南（PROJECT_GUIDE）

> 本文档面向**二次开发者**，聚焦于：架构与实现原理深析、二次开发规范、已知问题与技术债。
> 安装、卸载、FAQ、免责声明、致谢等内容请参见 [`readme.md`](./readme.md)。
>
> **当前适用版本**：`v1.1.9`（`app/common/config.py:251`）
> **原作者 / 年份**：Zzaphkiel / 2023
> **当前维护者**：Li-Qifeng（[Li-Qifeng/Seraphine](https://github.com/Li-Qifeng/Seraphine)）—— 本仓库为 [Zzaphkiel/Seraphine](https://github.com/Zzaphkiel/Seraphine) 的二次开发版本
> **许可证**：GPLv3（禁止商用）
> **目标平台**：Windows（桌面端，仅 64 位）

---

## 目录

- [0. 文档说明](#0-文档说明)
- [1. 项目概览](#1-项目概览)
  - [1.1 定位](#11-定位)
  - [1.2 技术栈](#12-技术栈)
  - [1.3 版本与发布机制](#13-版本与发布机制)
  - [1.4 运行环境约束](#14-运行环境约束)
- [2. 整体架构与实现原理](#2-整体架构与实现原理)
  - [2.1 分层架构](#21-分层架构)
  - [2.2 启动流程剖析](#22-启动流程剖析)
  - [2.3 核心设计模式](#23-核心设计模式)
  - [2.4 LCU 连接器深度剖析](#24-lcu-连接器深度剖析)
  - [2.5 异步与并发模型](#25-异步与并发模型)
  - [2.6 游戏状态机](#26-游戏状态机)
  - [2.7 数据层与缓存策略](#27-数据层与缓存策略)
  - [2.8 Win32 原生集成](#28-win32-原生集成)
  - [2.9 UI / 主题 / 国际化体系](#29-ui--主题--国际化体系)
- [3. 模块清单](#3-模块清单)
- [4. 二次开发规范](#4-二次开发规范)
- [5. 已知问题与技术债](#5-已知问题与技术债)
- [6. 功能开发指引](#6-功能开发指引)
- [7. 附录](#7-附录)

---

## 0. 文档说明

| 项目 | 内容 |
|---|---|
| 文档定位 | 给二次开发者的"地图 + 规范 + 排雷手册"，配合 `readme.md` 使用 |
| 读者 | 准备给 Seraphine 提 PR、二次开发或维护的工程师 |
| 三大重点 | ①架构与原理深析　②二次开发规范　③已知问题与技术债 |
| 维护方式 | 代码变更时同步更新本文档相应章节；版本号变更时更新顶部「适用版本」 |

**与 `readme.md` 的分工**：`readme.md` 面向**使用者**（下载、运行、卸载、FAQ、免责声明）；本文档面向**开发者**（架构、原理、规范、技术债）。两者不重复。

---

## 1. 项目概览

### 1.1 定位

Seraphine 是一个 **Windows 桌面端英雄联盟（League of Legends）辅助工具**，通过 Riot 官方的 **LCU（League Client Update）API** 与正在运行的英雄联盟客户端通信，提供：

- **战绩查询**：同大区任意召唤师战绩、BP 阶段自动查队友、对局开始自动查对手。
- **自动化（B/P + 结算）**：自动接受对局、自动选英雄、自动禁英雄、自动接受换位/交换（按 5 个位置分别配置）、**结算后自动点赞**（4 策略：好友优先/仅好友/最高评分/随机）。
- **AI 复盘（全队 5 档评级）**：每局结束后基于 z-score 标准化的综合贡献分，给全队每人打 5 档标签（胜方：神/爹/小有亮点/躺赢狗/消失；败方：人类/类人/战犯嫌疑人/甲级战犯/初升东曦；可切马系风）。海克斯模式视野分不计入，海克斯强化与 OPGG 英雄胜率纳入预期贡献基线。
- **外部数据**：大乱斗 Buff 信息、OP.GG 英雄排行与出装加点（一键导入符文）。
- **游戏/客户端工具**：创建 5v5 训练房、观战、锁定游戏设置、自动重连、修复结算无限加载/缩窗 bug、热重启客户端。
- **个性化**：修改主页背景、在线状态、签名、段位卡片显示、一键卸勋章/头像框。

⚠️ **重要前提**：所有功能**仅依赖 LCU API**，不含任何内存读写或文件篡改。但客户端本身较为脆弱（见 §5.4 的 #158 闪退、#408 封号风险）。

### 1.2 技术栈

| 类别 | 选型 | 版本 | 用途 |
|---|---|---|---|
| 语言 | Python | 3.8（conda 环境） | 主语言；类型注解使用尚不充分 |
| GUI 框架 | PyQt5 | 5.15.9 | 核心 GUI；`sip` 绑定 12.12.1 |
| UI 组件库 | PyQt-Fluent-Widgets | 1.5.7 | Fluent Design（Win11 风格）控件、导航、主题、`QConfig` |
| 异步桥接 | qasync | 0.27.1 | 将 `asyncio` 事件循环接入 Qt 事件循环 |
| 异步 HTTP | aiohttp | 3.10.10 | LCU REST + WebSocket 客户端 |
| 同步 HTTP | requests | 2.32.3 | GitHub 更新检查、Gitee 镜像同步 |
| 进程/系统 | psutil | 5.9.8 | 检测 LoL 客户端 PID、读取 cmdline |
| Win32 | pywin32（隐式） | — | `win32api`/`win32gui`/`winreg`/`ctypes.windll` |
| 剪贴板 | pyperclip | 1.8.2 | 复制错误信息等 |
| 增量更新 | tufup | ≥0.10.0 | 基于 TUF 的安全增量更新（bsdiff 补丁） |
| 版本比较 | packaging | ≥23.0 | PEP 440 语义版本比较（自更新检测） |
| 缓存 | async-lru / functools.lru_cache | 2.0.4 / 内置 | OPGG / ARAM 数据的异步 LRU 缓存 |
| 打包 | PyInstaller | 5.13（仅 CI/打包） | 打包为单目录 `Seraphine.exe` |

### 1.3 版本与发布机制

```
改 app/common/config.py 的 VERSION 常量
        │
        ▼
push 到 main 分支
        │
        ▼
.github/workflows/build_seraphine.yaml 触发
        │
        ├─ build-seraphine job（windows-latest, py3.8）
        │     pip install -r requirements.txt
        │     pip install pyinstaller==5.13
        │     .\make.ps1 -keepDist   # → Seraphine.7z + 保留 dist/Seraphine
        │     upload-artifact (Seraphine.7z + Seraphine-dist)
        │
        ├─ build-installer job（windows-latest, 依赖 build-seraphine）
        │     choco install innosetup
        │     ISCC Seraphine.iss → SeraphineSetup-{VERSION}.exe
        │     upload-artifact (installer exe + sha256)
        │
        ├─ release job（ubuntu-latest, 依赖 build + installer）
        │     用 git diff HEAD~1 HEAD 检测 VERSION 行是否在本次提交被修改
        │     若 UPDATED == true:
        │       download artifacts → ncipollo/release-action
        │       发布 tag v{VERSION} 的 GitHub Release
        │       （附件: Seraphine.7z + .sha256 + SeraphineSetup-*.exe + .sha256）
        │     outputs: updated / version （供下游 publish-tufup 复用）
        │
        └─ publish-tufup job（ubuntu-latest, 依赖 build+release, 仅 VERSION 变更时运行）
              download Seraphine-dist artifact
              恢复 gh-pages 上既有 tufup 仓库 (metadata + targets, patch 链需要)
              从 TUFUP_KEYS_B64 secret 还原签名密钥
              add-bundle + 签名发布
              deploy 到 gh-pages/tufup/
```

- **Gitee 镜像**：`sync.py` 通过 Gitee OAuth 把 Release（含 `.7z` + `.sha256`）同步到 Gitee（国内访问），幂等可重入。
- **增量自更新（tufup）**：基于 TUF（The Update Framework）安全标准。客户端 `app/common/tufup_updater.py` 通过 `check_update()` 拉取 gh-pages 上的 metadata 判断是否有新版本，`download_and_install()` 下载 bsdiff 补丁并就地应用、重启。流程：下载 patch → 应用到安装目录 → 重启。**不再需要 7z 解压、删除旧文件、`updater.ps1`**。
  - **可信根**：`app/resource/tufup/metadata/root.json` 随应用分发（loose 文件），客户端据此校验 gh-pages 上 metadata 的签名。
  - **托管**：tufup 仓库（`metadata/` + `targets/`）托管在 GitHub Pages 的 `gh-pages` 分支 `tufup/` 子目录。
  - **密钥管理**：TUF 签名密钥以 tar.gz→base64 形式存于 GitHub secret `TUFUP_KEYS_B64`，CI 运行时还原；首次运行（无 secret）生成新密钥并输出到 step summary，需开发者手动保存为 secret，同时下载 root.json artifact 提交到 `app/resource/tufup/metadata/`。
  - **服务端脚本**：`tufup_repo.py`（仓库根）提供 `init`/`add-bundle`/`pack-keys`/`unpack-keys` 子命令，封装了 CI 非交互式运行所需的 `input()` 屏蔽逻辑（`Keys.create_key_pair` 与 `make_gztar_archive` 都会交互式询问覆盖）。
- **版本 kill-switch**：`document/ver.json`（如 `{"0.12.3": {"forbidden": false}}`），应用启动时检查，可用于远程禁用有问题的版本。

> **发包约定**：不要手敲 Release，只改 `VERSION` 让 CI 自动出包并发布 tufup 增量更新。每次发版产两件：`Seraphine.7z`（便携版，旧用户升级路径）和 `SeraphineSetup-{VERSION}.exe`（Inno Setup 安装包，新用户推荐）。
>
> **安装包设计要点**：
> - 安装路径：`%LOCALAPPDATA%\Programs\Seraphine`（per-user，无需管理员权限，tufup 增量更新可正常写文件）
> - CI 通过 `choco install innosetup` + `ISCC.exe /Q` 编译，产物自动上传到 Release
> - 卸载时自动清理 tufup 缓存目录（`%LOCALAPPDATA%\Seraphine\tufup_targets`），避免新旧版本缓存混用

### 1.4 运行环境约束

- **仅 Windows**：深度依赖 `win32api`/`winreg`/`tasklist`/`wmic`/`ctypes.windll`，无跨平台抽象层。
- **数据目录**：`%APPDATA%\Seraphine\`（`config.json`、`AramBuff.json`、`ChampionAlias.json`、`temp/`）。代码常量：`cfg.LOCAL_PATH`（`config.py:243`）。
- **日志目录**：`./log/`（脚本启动目录下，rotating 2MB × 20 文件）。
- **开发环境**：`conda create -n seraphine python=3.8` → `pip install -r requirements.txt` → `python main.py`。
- **Windows 11 检测**：`isWin11()` = `sys.getwindowsversion().build >= 22000`，用于决定是否启用 Mica 效果。

---

## 2. 整体架构与实现原理

### 2.1 分层架构

```
┌─────────────────────────────────────────────────────────────┐
│  app/view/        表现层（PyQt5 widgets，被动 + emit 信号）   │
│    main_window.py  ←─ MainWindow：导航壳 + 编排者(presenter)  │
│    start/career/search/game_info/auxiliary/setting_interface │
│    opgg_window.py + opgg_tier/opgg_build_interface           │
└───────────────▲─────────────────────────────────────────────┘
                │ signalBus（pyqtSignal）+ 直接方法调用
┌───────────────┴─────────────────────────────────────────────┐
│  app/lol/         业务 + 数据层                              │
│    connector.py   LcuWebSocket + LolClientConnector（REST）  │
│    tools.py       纯业务逻辑/解析/自动 B/P 状态机            │
│    war_criminal.py 全队5档评级算法 (z-score + OPGG基线)      │
│    war_criminal_cache.py 评级结果内存缓存 (按gameId)         │
│    augment_baseline.py 海克斯强化组合分 (OPGG pick/win)      │
│    champion_baseline.py 英雄OPGG胜率基线                     │
│    opgg.py / aram.py / champions.py   外部数据源客户端       │
│    exceptions.py  5 个自定义异常（均继承 Exception）      │
└───────────────▲─────────────────────────────────────────────┘
                │ 依赖
┌───────────────┴─────────────────────────────────────────────┐
│  app/common/      基础设施（单例）                           │
│    config.py(cfg) signals.py(signalBus) logger.py(logger)   │
│    util.py(github + Win32/进程辅助) style_sheet.py          │
│    tufup_updater.py(增量更新) version_utils.py(版本比较)    │
│    icons.py qfluentwidgets.py                                │
└─────────────────────────────────────────────────────────────┘

┌──────────────────────────┐   ┌──────────────────────────────┐
│  app/components/         │   │  app/resource/               │
│  ~20 个复用控件          │   │  images/ qss/{light,dark}/   │
│  （SeraphineInterface 是 │   │  i18n/ bin/(fix_lcu_window)  │
│   所有页面的滚动基类）    │   │  game/(运行时生成的 icon 缓存)│
└──────────────────────────┘   └──────────────────────────────┘
```

**关键观察**：
1. **没有 MVC 框架**，但有清晰的职责分离：`connector`（I/O）↔ `tools`（纯转换）↔ `views`（渲染），由 `MainWindow` 作为 orchestrator 编排。
2. **单例服务层**在模块导入时即实例化（见 §2.3），无 DI 容器。
3. `MainWindow.__conncetSignalToSlot`（`main_window.py:275`）是**显式接线表**，是理解整个应用事件流的入口。

### 2.2 启动流程剖析

**入口 `main.py`**（顺序）：
1. `os.chdir` 到脚本目录，保证 `app/resource/...` 相对路径可用。
2. 读取 `cfg`（**模块导入即触发** `%APPDATA%\Seraphine\config.json` 的加载，见 `config.py:245`）。
3. 处理 `--version`/`-v` 命令行（快速退出）。
4. 根据 `cfg.dpiScale` 配置 Hi-DPI 缩放（`Auto` 用 Qt rounding policy，否则强制 `QT_SCALE_FACTOR`）。
5. 设置全局抗锯齿字体，创建 `QApplication`。
6. **桥接事件循环**：`QEventLoop(app)`（来自 qasync）成为活跃的 `asyncio` 事件循环；`asyncio.Event` 绑定 `app.aboutToQuit`，关闭时退出循环。
7. 安装两个 `QTranslator`：Fluent 内置翻译 + 项目级 `Seraphine.zh_CN.qm`。
8. 构造 `MainWindow()` 并 `show()`。
9. `eventLoop.run_until_complete(appCloseEvent.wait())` 阻塞直到退出。

**`MainWindow.__init__`**（`main_window.py:69`）：
```
__init__
 ├─ __initConfig           # 首次运行时从注册表自动探测 LoL 安装路径
 ├─ __initWindow           # 最小尺寸、图标、Mica、SplashScreen
 ├─ __initSystemTray       # 系统托盘（关闭到托盘可配置）
 ├─ 实例化 6 个子界面      # Start/Career/Search/GameInfo/Auxiliary/Setting
 ├─ 实例化 processListener (QThread)
 ├─ 实例化 2 个 StoppableThread（checkUpdate / checkNotice）
 ├─ __initInterface        # 各界面初始化内容
 ├─ __initNavigation       # 注册到 FluentWindow 导航栏（见下）
 ├─ __initListener         # 启动 listener 线程
 ├─ __conncetSignalToSlot  # ★ 全局信号接线表
 ├─ __autoStartLolClient   # 若配置则自动启动客户端
 ├─ splashScreen.finish()
 ├─ OpggWindow()           # 独立窗口（FramelessWindow）
 └─ __silentStart          # 若配置则静默启动到托盘
```

**导航注册（`__initNavigation`，`main_window.py:194`）**：
- 顶部滚动区：Start / Career / Search 👀 / Game Information / Auxiliary Functions（5 个主界面）
- 底部固定区：OP.GG（弹出独立窗口）/ Back to Lobby（修复客户端）/ Notice（公告）/ 头像 widget / Settings

### 2.3 核心设计模式

#### ① 全局信号总线 `signalBus`

`app/common/signals.py` 定义单一 `SignalBus(QObject)` 实例 `signalBus`，承载约 17 个 `pyqtSignal`，按来源分组：

| 分组 | 信号 | 触发源 |
|---|---|---|---|
| listener | `tasklistNotFound`, `lolClientStarted(int)`, `lolClientEnded`, `lolClientChanged(int)`, `terminateListeners` | `LolProcessExistenceListener`（QThread 轮询 tasklist） |
| connector | `lcuApiExceptionRaised(str, BaseException)`, `currentSummonerProfileChanged(dict)`, `gameStatusChanged(str)`, `champSelectChanged(dict)`, `getCmdlineError` | LCU REST/WS 回调 |
| 跨界面跳转 | `toCareerInterface(str)`, `toSearchInterface(str)`, `toOpggBuildInterface(int,str,str)`, `careerGameBarClicked(str)`, `gameTabClicked(QWidget)` | 各 view |
| 更新检查 | `checkUpdateRequested` | 设置页"Check now"按钮 |
| 样式 | `customColorChanged(str)` | `__ColorManager` |

**接线全部集中在 `MainWindow.__conncetSignalToSlot`**，逐行 `connect`。这是解耦 listener / connector / views 的关键：模块间不持有引用，只通过 `signalBus` 通信。

#### ② 单例服务层（模块级实例化）

| 单例 | 位置 | 说明 |
|---|---|---|
| `connector` | `connector.py:1504` | LCU 客户端，进程内唯一，持有 port/token/server/manager 等可变状态 |
| `signalBus` | `signals.py:46` | 全局信号总线 |
| `cfg` | `config.py:245` | QConfig 单例，import 即加载 config.json |
| `logger` | `logger.py:109` | 日志器，rotating |
| `opgg` | `opgg.py:923` | OPGG 异步客户端（带 `@alru_cache`） |
| `github` | `util.py:93` | 更新/公告拉取（可选代理） |

无 DI 容器，到处 `from ... import connector` 直接使用。**多客户端场景**通过 `connector.start()/close()` 复用同一实例，存在已知竞态窗口（见 `__onLolClientChanged`）。

#### ③ MVP/MVVM 混合（MainWindow 作 presenter）

- **Model**：`JsonManager`（LCU 引用数据内存表）+ `cfg`（持久化配置）+ 缓存 JSON。
- **View**：`app/view/*`，被动，用户操作 `emit` 信号。
- **Presenter**：`MainWindow` 的各 `__onXxx` slot 方法（如 `__onGameStatusChanged`、`__onChampSelectChanged`），编排 `connector` + `tools` 调用并把结果 push 回 view。

### 2.4 LCU 连接器深度剖析

`app/lol/connector.py` 是项目核心。两大组件：`LcuWebSocket`（实时推送）+ `LolClientConnector`（REST 请求）。

#### 进程发现与端口/Token 提取

```
getLolClientPid(tasklistPath)
   └─ os.popen('tasklist /FI "imagename eq LeagueClientUx.exe"')  解析 PID
      失败回退：psutil.process_iter() 过滤进程名

getPortTokenServerByPid(pid)
   └─ psutil.Process(pid).cmdline()  解析命令行参数：
        --app-port=xxx          → port
        --remoting-auth-token=xxx → token
        --rso_platform_id=xxx   → server（大区标识）
      失败回退：wmic（需管理员）；再失败 emit signalBus.getCmdlineError
```

#### HTTP 客户端

- `aiohttp.ClientSession`，`https://127.0.0.1:{port}`，HTTP Basic Auth `riot:token`，`ssl=False`。
- 5 个动词 `__get/__post/__put/__delete/__patch` 均被 `@needLcu` 守卫：若 `connector.lcuSess is None`（LCU 未就绪）则 `raise ReferenceError`。
- **Tencent SGP**：当 `connector.isInTencent()`（server 属于 `tj100/hn1/cq100/gz100/nj100/hn10/tj101/bgp2`）时，走 `https://{server}-sgp.lol.qq.com:21019/...`，Bearer token 来自 entitlements 端点。用于国服战绩/排位/观战的补充数据。

#### `@retry` 装饰器机制（`connector.py:54`）

每个对外 LCU 方法都套 `@retry(count=5)`，关键逻辑：

```
对每次调用：
1. logger.info 记录 func.__name__
2. 用 inspect 提取参数名 → 构建 params_dict
3. 加锁（dqLock）创建 PastRequest，append 到 connector.callStack（deque maxlen=10，崩溃诊断用）
4. 循环 count 次：
     async with connector.semaphore:   # 并发上限 = cfg.apiConcurrencyNumber
         res = await func(...)
     成功 → 写入 req_obj.response，break
   except CancelledError: raise         # ★ 必须 re-raise（见陷阱）
   except BaseException as e:
     若 isinstance(e, SummonerNotFound): raise   # 重试会触发 429 限流
     记录 exce，sleep(retry_sep)，continue
   else (全失败):
     若 type(exce) is ReferenceError: 静默吞掉（LCU 未就绪属正常）
     否则 signalBus.lcuApiExceptionRaised.emit(func.__name__, exce)  # 弹提示
     raise exce
```

**为什么所有自定义异常继承 `BaseException` 而非 `Exception`？**（见 `exceptions.py`）为了让它们**绕过通用的 `except Exception` 处理**，直达 `retry` 装饰器的特判逻辑。这有副作用——`retry` 里用 `except BaseException` 会一并捕获 `CancelledError`/`KeyboardInterrupt`，故显式 `except CancelledError: raise` 是必须的（见 §5.3）。

#### WebSocket 订阅（`LcuWebSocket`）

```
runWs():
  session = aiohttp.ClientSession(auth=BasicAuth('riot', token), ...)
  ws = session.ws_connect('wss://127.0.0.1:{port}/', ssl=False)
  for event in self.events:
      ws.send_json([5, event])            # [5, "OnJsonApiEvent_xxx"] 订阅帧（见 Hextechdocs）
  while True:
      msg = ws.receive()
      if msg.type == TEXT: matchUri(json.loads(msg.data)[2])

subscribe(event, uri, type=('Update','Create','Delete'))  # 装饰器，注册回调
matchUri(data): URI + eventType 匹配 → asyncio.create_task(callable(data))
```

订阅的 4 个核心事件（`__runListener`）：
- `/lol-summoner/v1/current-summoner` → `currentSummonerProfileChanged`
- `/lol-gameflow/v1/gameflow-phase` → `gameStatusChanged`（驱动状态机）
- `/lol-champ-select/v1/session` → `champSelectChanged`
- entitlements/SGP token

⚠️ **禁止订阅全量 `OnJsonApiEvent`**（`start()` 有 `AssertionError` 拦截，仅调试时可注释）。

### 2.5 异步与并发模型

- **qasync 桥接**：`QEventLoop(app)` 让 Qt 事件循环驱动 asyncio。`@asyncSlot(...)` 装饰 Qt slot 使其在集成循环上运行。
- **并行取数**：大量使用 `asyncio.gather`，典型场景——同时取 N 个队友的图标 + 段位 + 历史战绩。
- **并发上限**：`asyncio.Semaphore(cfg.apiConcurrencyNumber)`（默认 1，可在 1–100 配置，改后需重启）。**默认为 1 是因为客户端对并发 HTTP 较脆弱**（见 README「客户端为什么有时候会闪退」）。
- **后台线程**：`StoppableThread`（继承 QThread）跑阻塞 I/O——`checkUpdate`、`checkNotice`；`LolProcessExistenceListener` 每 1.5s 轮询 tasklist。
- **`asyncSlot` 陷阱**：作者在 `main_window.py:561-585` 留有详细注释——`asyncSlot` 返回的是 task，若需等待结果须 `await`，否则后续逻辑可能跑在 task 完成前。
- **`CancelledError` 陷阱**：见 §5.3。

### 2.6 游戏状态机

`gameflow-phase` WebSocket 事件驱动 `MainWindow.__onGameStatusChanged`（`main_window.py:876`）：

```
状态字符串          → 行为
─────────────────────────────────────────────────────────────
None               → __onGameEnd()
Lobby              → __onGameEnd() + careerInterface.refresh() + 若在 GameInfo 则切回 Career
Matchmaking        → __onGameEnd()
ReadyCheck         → __onMatchMade()（若开 enableAutoAcceptMatching，延时后接受）
ChampSelect        → getMapSide()（标题加蓝/红方）+ __onChampionSelectBegin()
                      ├─ championSelection.reset()
                      ├─ gather(getChampSelectSession, getGameflowSession)
                      ├─ 可选 show OpggWindow
                      └─ 触发 GameInfoInterface.updateAllySummoners（自动查队友）
GameStart          → __onGameStart()（parseGameInfoByGameflowSession('enemy') 自动查对手）
InProgress         → 若非 GameStart 走过则补 __onGameStart()（重连场景）
Reconnect          → __onReconnect()（若开 enableAutoReconnect，每 0.3s 重试 reconnect）
EndOfGame          → 仅更新标题
WaitingForStatus   → 仅更新标题
```

**自动 B/P 状态机**（`tools.py` 的 `ChampionSelection` 类 + `autoPick/autoBan/autoComplete/autoSwap/autoTrade/autoSetSummonerSpell`）：由 `champSelectChanged` 推送驱动，按 BP 阶段（pick/ban/complete/swap/trade）和**当前召唤师所处位置**（Top/Jug/Mid/Bot/Sup）读取对应的 `cfg.autoSelectChampionXxx`/`autoBanChampionXxx` 配置，逐阶段执行动作。

### 2.7 数据层与缓存策略

**无传统数据库**。四套持久化机制：

| 机制 | 位置 | 失效/更新策略 |
|---|---|---|
| 用户配置 | `%APPDATA%\Seraphine\config.json`（QConfig 自动序列化 ~60 个 ConfigItem） | 实时写回 |
| 版本化远程缓存 | `AramBuff.json`（大乱斗之家数据）/ `ChampionAlias.json`（英雄昵称） | 按**本地 LoL 客户端版本**比对，版本变则重新拉取（`jddld.com` / `game.gtimg.cn`） |
| LCU 资源缓存 | `app/resource/game/{champion,item,profile,rune,spell,augment icon, splash}/` | `connector.__initFolder` 创建目录；图标**按需**从 LCU `/lol-game-data/assets/` 拉取落盘，**永不重复下载** |
| 内存引用表 | `JsonManager`（items/spells/runes/perkstyles/queues/champions/skins/augments 共 8 张） | 客户端连接时 `__initManager` 一次性拉取，整会话驻留内存作查找字典 |
| 日志 | `./log/Seraphine_YYYY-MM-DD_<LEVEL>.log` | rotating 2MB × 20（`CustomRotatingFileHandler` 重命名为 `xxx_1.log` 而非 `xxx.log.1`） |

**外部数据源**：LCU REST（主）/ LCU WebSocket（实时推送）/ Tencent SGP（国服补充）/ OPGG API（`lol-api-champion.op.gg`，带 `@alru_cache(512)`）/ GitHub API（release/notice/`ver.json` kill-switch）/ `jddld.com`（ARAM）/ `game.gtimg.cn`（英雄昵称）。

### 2.8 Win32 原生集成

| 能力 | API | 文件 |
|---|---|---|
| 读 LoL 安装路径 | `winreg` → `HKCU\SOFTWARE\Tencent\LOL\InstallPath` | `util.getLoLPathByRegistry` |
| 读客户端版本 | `win32api.GetFileVersionInfo('League of Legends.exe')` | `util.getLolClientVersion` |
| 定位客户端窗口 | `win32gui.FindWindow("RCLIENT", "League of Legends")` + `GetWindowRect`（OpggWindow 贴其右侧） | `util.getLolClientWindowPos` |
| 屏幕尺寸 | `win32api.GetSystemMetrics`（DPI 健全性检查） | `util` |
| UAC 提权跑修复器 | `ctypes.windll.shell32.ShellExecuteW(None, "runas", "fix_lcu_window.exe", ...)` | `main_window` |
| Win11 Mica | `windowEffect.setMicaEffect(winId, isDarkTheme)`（仅 build≥22000） | `MainWindow`/`OpggWindow` |
| 启动/观战外部进程 | `os.popen`（启客户端）/ `subprocess.Popen(['League of Legends.exe', 'spectator ...'])`（观战） | `connector` |

**`fix_lcu_window.exe`**（`app/resource/bin/fix_lcu_window.c`）：编译的 C 辅助，对 RCLIENT 窗口发 DPI-changed 消息并调整 CEF 子窗口尺寸，修复"结算时无限加载/缩成一角"bug。源码参考 `LeagueTavern/fix-lcu-window`。

### 2.9 UI / 主题 / 国际化体系

- **导航壳**：`FluentWindow`（PyQt-Fluent-Widgets）= 左侧 `NavigationInterface` + `QStackedWidget`，页面在 `__initNavigation` 注册。
- **页面基类**：`SeraphineInterface`（`app/components/seraphine_interface.py`）= `SmoothScrollArea`，所有页面继承它。
- **QSS 主题**：`app/resource/qss/{light,dark}/*.qss`，**按界面拆分**（每个 view 一份）。`StyleSheet` 枚举（`style_sheet.py`）按主题映射路径。
- **颜色 pub/sub**：`__ColorManager` + `ColorChangeable` mixin——胜/负/重开局卡片色、段位色、死亡数色等会响应配置与主题变化。
- **i18n**：`QTranslator` + `.ts`（源）/`.qm`（编译）文件，在 `app/resource/i18n/`。每个面向用户的字符串走 `self.tr(...)`。`Seraphine.pro` 是 Qt Linguist 项目文件（**不是 qmake 构建文件**），用 `lupdate`/`lrelease` 维护翻译。支持 zh_CN 与 English，默认按系统自动检测。
- **图标**：`app/resource/icons/` 约 150 个 Fluent 风格 SVG（黑白双套），`app/common/icons.py` 的 `Icon` 类集中引用。

---

## 3. 模块清单

### `app/common/`（基础设施，全部单例）

| 文件 | 职责 | 关键符号 |
|---|---|---|
| `config.py` | QConfig 配置 + 元信息（VERSION/AUTHOR/LOCAL_PATH） | `Config`, `cfg`, `Language`, `isWin11()` |
| `signals.py` | 全局信号总线 | `SignalBus`, `signalBus` |
| `logger.py` | rotating 日志（2MB×20） | `Logger`, `logger` |
| `util.py` | Win32/进程辅助 + GitHub 更新/公告拉取 | `Github`, `getLolClientPid(s)`, `getPortTokenServerByPid`, `getLoLPathByRegistry`, `getLolClientVersion`, `getLolClientWindowPos` |
| `style_sheet.py` | QSS 主题映射 + 颜色 pub/sub | `StyleSheet`, `ColorChangeable`, `__ColorManager` |
| `tufup_updater.py` | 基于 tufup 的客户端增量更新封装（检查/下载/应用补丁） | `check_update()`, `download_and_install()`, `get_current_version()` |
| `version_utils.py` | 纯函数版本比较（PEP 440），独立于 util.py 的 Windows 依赖以便单测 | `coerce_version()` |
| `icons.py` | Fluent 图标集中引用 | `Icon` |
| `qfluentwidgets.py` | PyQt-Fluent-Widgets 再导出（去广告） | — |

### `app/lol/`（业务 + 数据层）

| 文件 | 职责 | 关键符号 |
|---|---|---|
| `connector.py` | LCU REST + WS 客户端（~70 个端点方法） | `LolClientConnector`, `connector`, `LcuWebSocket`, `@retry`, `@needLcu`, `PastRequest` |
| `listener.py` | QThread 轮询 tasklist 检测客户端进程 | `LolProcessExistenceListener`, `StoppableThread` |
| `tools.py`（~1843 行） | 纯业务逻辑：数据解析 + 自动 B/P 状态机 + auto honor 策略 | `parseSummonerData`, `parseGameData`, `parseGameDetailData`, `parseAllyGameInfo`, `parseGameInfoByGameflowSession`, `ChampionSelection`, `autoPick/autoBan/autoComplete/autoSwap/autoTrade/autoSetSummonerSpell/autoShow/showOpggBuild`, `pickHonorTarget`, `getTeamColor`, `SERVERS_NAME/SUBSET` |
| `tools_pure.py` | 无 Qt/connector 依赖的纯函数（可单测） | `translateTier`, `timeStampToStr`, `separateTeams`, `parseSummonerOrder`, `sortedSummonersByGameRole`, `parseGames`, `parseRankInfo`, `parseDetailRankInfo`, `pickHonorTarget`, `HONOR_STRATEGY_*` |
| `war_criminal.py` | **全队 5 档评级算法**：z-score 标准化 + 角色权重 + OPGG 胜率/海克斯强化基线 | `rateEntireTeam`, `gradeFromScore`, `gradeLabel`, `diagnoseGameFromParsed`, `GRADE_THRESHOLDS`, `GRADE_LABELS_TIEBA/HORSE`, `ROLE_WEIGHTS`, `ParticipantStats`, `TeamRatingResult` |
| `war_criminal_cache.py` | 评级结果内存缓存（按 gameId，重启清空） | `setVerdict`, `getVerdict`, `getTeamRating`, `PlayerRating` |
| `augment_baseline.py` | 海克斯强化组合分（OPGG pick/win 加权） | `getHextechAugmentScore` |
| `champion_baseline.py` | 英雄 OPGG 胜率基线（按 queueId 映射模式） | `getChampionBaselineWinrate` |
| `opgg.py` | OPGG 异步客户端 + 数据解析（带 LRU 缓存） | `Opgg`, `opgg`, `OpggDataParser` |
| `aram.py` | 大乱斗 Buff 数据（jddld.com，版本化缓存） | `AramBuff` |
| `champions.py` | 英雄昵称/关键词（gtimg.cn，版本化缓存，模糊搜索） | `ChampionAlias` |
| `exceptions.py` | 5 个自定义异常（均继承 Exception） | `SummonerNotFound`, `SummonerGamesNotFound`, `SummonerRankInfoNotFound`, `SummonerNotInGame`, `RetryMaximumAttempts` |

### `app/view/`（表现层）

| 文件 | 职责 |
|---|---|
| `main_window.py` | `MainWindow(FluentWindow)`：导航壳 + 编排者，所有信号接线在此 |
| `start_interface.py` | 连接前的占位/加载页 |
| `career_interface.py` | 当前召唤师生涯：图标/等级/段位/近期对局/近期队友/英雄统计 |
| `search_interface.py` | 按召唤师名搜战绩 + 对局详情（队伍/KDA/装备/符文/Ban） |
| `game_info_interface.py` | BP/对局中实时队友与对手分析（核心特性） |
| `auxiliary_interface.py` | 工具箱：资料编辑、游戏/客户端工具、B/P 自动化开关 |
| `setting_interface.py` | 所有 `cfg` 配置项的 SettingCard 界面 |
| `opgg_window.py` + `opgg_tier_interface.py` + `opgg_build_interface.py` | 独立 `FramelessWindow`，显示 OP.GG 排行与出装，自动贴在客户端右侧 |

### `app/components/`（~20 个复用控件）

`seraphine_interface.py`（页面滚动基类）、`game_infobar_widget.py`（含 `VerdictBadge` 战犯/躺赢狗徽章 + `GameInfoBar`）、`grade_badge.py`（**全队 5 档评级徽章** `GradeBadge`，M3 tonal palette 配色）、`champion_icon_widget.py`、`avatar_widget.py`、`draggable_widget.py`、`animation_frame.py`（彩色卡片动画基类 `ColorAnimationFrame`）、`message_box.py`（自定义对话框：更新/公告/异常/等待 LoL/DPI 变更）、`multi_champion_select.py`、`multi_lol_path_setting.py`、`setting_cards.py`、`temp_system_tray_menu.py`、`search_line_edit.py`、`mode_filter_widget.py` 等。

### `app/resource/`（静态资源）

| 子目录 | 内容 |
|---|---|
| `images/` | 段位徽章、地图目标、logo 等 |
| `icons/` | ~150 个 Fluent SVG（黑白双套） |
| `qss/{light,dark}/` | 按界面拆分的 Qt 样式表 |
| `i18n/` | `Seraphine.zh_CN.ts/.qm` + `gamemodes.json` |
| `bin/` | `fix_lcu_window.c` / `.exe`（原生辅助） |
| `game/`（运行时生成） | 从 LCU 按需下载的 icon 缓存 |

---

## 4. 二次开发规范

> 每节配可复制的代码骨架。新增功能时**先读 §6.1 的「需求→落地」标准模板**，再对号入座查本节。

### 4.1 新增一个界面/页面

```python
# 1) 新建 app/view/my_feature_interface.py
from app.components.seraphine_interface import SeraphineInterface
from app.common.icons import Icon

class MyFeatureInterface(SeraphineInterface):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MyFeatureInterface")   # ★ objectName 必须与 QSS 选择器一致
        # ... 布局控件，所有文案用 self.tr("...")

    def tr(self, text):  # 若基类未提供，按现有 view 模式实现
        return ...
```

```python
# 2) app/view/main_window.py 的 __init__ 中实例化
self.myFeatureInterface = MyFeatureInterface(self)
```

```python
# 3) __initNavigation 中注册（参考现有 5 个主界面）
self.addSubInterface(
    self.myFeatureInterface, Icon.MY_ICON, self.tr("My Feature"),
    NavigationItemPosition.SCROLL)
```

```css
/* 4) app/resource/qss/{light,dark}/my_feature_interface.qss —— 双主题都要写！ */
#MyFeatureInterface { background: transparent; }
```

```python
# 5) app/common/style_sheet.py 的 StyleSheet 枚举里登记路径
```

**要点**：`setObjectName` ↔ QSS 选择器 ↔ `StyleSheet` 枚举三者必须对齐；文案一律 `self.tr()`；light/dark 两份 QSS 都要维护。

### 4.2 新增一个配置项

```python
# 1) app/common/config.py 的 Config 类中，按分组（General/Personalization/Functions/Other）添加：
class Config(QConfig):
    myFeatureEnabled = ConfigItem(
        "Functions", "MyFeatureEnabled", False, BoolValidator())
    myFeatureCount = RangeConfigItem(
        "Functions", "MyFeatureCount", 10, RangeValidator(1, 100))
    myFeatureMode = OptionsConfigItem(
        "Functions", "MyFeatureMode", "a",
        OptionsValidator(["a", "b", "c"]))   # restart=True 表示改后需重启才生效
```

```python
# 2) app/view/setting_interface.py 添加对应 SettingCard：
from app.common.config import cfg
self.myFeatureCard = SwitchSettingCard(
    Icon.TOGGLE, self.tr("My Feature"),
    self.tr("Description shown under the title."),
    cfg.myFeatureEnabled)   # 直接绑 ConfigItem
self.settingGroup.addWidget(self.myFeatureCard)
```

```python
# 3) 使用处：
if cfg.get(cfg.myFeatureEnabled): ...
# 需要响应变更：连 card.checkedChanged 或读 cfg；不推荐自行轮询
```

**要点**：默认值类型与 Validator 匹配；`restart=True` 仅用于无法热生效的项（如并发数、DPI、语言）；配置自动持久化到 config.json，无需手写序列化。

### 4.3 新增一个全局信号

```python
# 1) app/common/signals.py 的 SignalBus：
class SignalBus(QObject):
    myEvent = pyqtSignal(dict)   # 参数必须是 Qt 可识别类型（int/str/dict/list/object）
```

```python
# 2) app/view/main_window.py 的 __conncetSignalToSlot 接线（按来源分组加注释）：
signalBus.myEvent.connect(self.__onMyEvent)

async def __onMyEvent(self, data):  # 通常用 @asyncSlot
    ...

# 3) 触发处：signalBus.myEvent.emit({...})
```

**要点**：信号类型在定义后**不可改**（PyQt 限制）；用 `object`/`dict`/`QWidget` 等通用类型避免后续返工；接线表保持分组注释清晰。

### 4.4 新增一个 LCU API 调用

```python
# 1) app/lol/connector.py 的 LolClientConnector，加 @retry 方法：
@retry()
@needLcu()
async def getMyEndpoint(self, someId: int):
    return await self.__get(f"/lol-my-endpoint/v1/{someId}")

# 2) 若返回数据需要落盘成资源/进引用表，在 __initManager/__initFolder 旁按现有模式扩展
```

```python
# 3) 纯解析逻辑放 app/lol/tools.py（与 I/O 解耦）：
def parseMyData(raw: dict) -> dict:
    return {...}
```

```python
# 4) 在 MainWindow slot 或 view 中编排：
raw = await connector.getMyEndpoint(someId)
data = parseMyData(raw)
```

**要点**：所有 LCU 调用必经 `@retry`（自动诊断+重试+异常上报）和 `@needLcu`（守卫未连接）；**I/O 留在 connector，纯转换放 tools**；端点 URL 参考 [mingweisamuel/lcu-schema](https://www.mingweisamuel.com/lcu-schema/tool/) 或 [Hextechdocs](https://hextechdocs.dev/tag/lcu/)。**新增方法应标注返回类型**（`dict`/`list`/`str`/`bool`/`bytes`/`Optional[dict]`/`aiohttp.ClientResponse` 等），与现有 connector.py 标注风格保持一致。

### 4.5 异步任务规范

- ✅ Qt slot 跑异步逻辑用 `@asyncSlot(...)`（参数为信号传参类型）。
- ✅ 并行取数用 `asyncio.gather`（如同时取 N 个召唤师）。
- ✅ 受 `connector.semaphore` 约束（已内置于 `@retry`），不要绕开。
- ✅ 长耗时后台 I/O 用 `StoppableThread`，不阻塞 UI 循环。
- ❌ **禁止**在主循环上做同步阻塞 I/O（如 `requests.get`）——目前 `util.sendNotificationMsg` 有此问题（见 §5.3），属待修。`getLoginSummonerByPid` 已改造为 aiohttp 异步（见 §5.3 ⑦）。
- ⚠️ **`CancelledError` 必须能穿透** `@retry`——装饰器已 `except CancelledError: raise`，新增类似装饰器时要照搬。
- ⚠️ `asyncSlot` 返回的是 task，需等待结果要 `await`（见 `main_window.py:561-585` 注释）。

### 4.6 资源与缓存规范

- **图标**：不要手贴图片到 `app/resource/game/`；走 `connector` 的资源拉取方法（自动按需落盘 + 永不重下）。
- **版本化远程缓存**（新增第三方数据源时套用 `aram.py`/`champions.py` 模板）：
  ```python
  # 伪代码骨架
  class MyDataSource:
      CACHE_PATH = f"{LOCAL_PATH}\\MyData.json"
      def __init__(self):
          self.data = None
      async def __needUpdate(self, lolVersion):
          # 读缓存里的 version 字段，与本地客户端版本比对；异常时保守返回 True
      async def update(self, lolVersion):
          # 拉远端 → 写 CACHE_PATH（含 version 字段）→ 更新内存
          self.data = json.load(...)
  ```
- **i18n**：所有用户可见字符串走 `self.tr(...)`；新增文案后用 `lupdate Seraphine.pro` 更新 `.ts`，`lrelease` 编译 `.qm`。
- **QSS**：light/dark **双份**都写，文件名与界面 `objectName` 对应，在 `StyleSheet` 枚举登记。

### 4.7 日志规范

```python
from app.common.logger import logger
TAG = "MyModule"   # 模块内常量

logger.debug(f"detail = {x}", TAG)    # 开发诊断（默认不输出，受 cfg.logLevel 控制）
logger.info(f"call xxx", TAG)          # 关键流程节点
logger.warning(f"unexpected but handled: {e}", TAG)
logger.error(...)
logger.critical(f"Seraphine started, version: {VERSION}", TAG)  # 启动/重大事件
logger.exception(f"exit xxx", exc, TAG)  # 带堆栈
```

- **必传 `TAG`**（模块名），便于按模块过滤。
- **级别**：DEBUG=10 / INFO=20 / WARNING=30 / ERROR=40 / CRITICAL=50（CRITICAL 在本项目用于"启动""连接成功"等关键里程碑，不是错误）。
- 日志 rotating 2MB × 20，存 `./log/`。
- `cfg.logLevel` 可热改（设置页），但部分项标记 `restart=True`。

### 4.8 错误处理规范

**5 个自定义异常**（`app/lol/exceptions.py`，均继承 `Exception`）的使用场景：

| 异常 | 何时抛 | retry 行为 |
|---|---|---|
| `SummonerNotFound` | 召唤师名查不到 | **立即抛出**，不重试（否则触发 429） |
| `SummonerGamesNotFound` | 该召唤师无对局记录 | 正常重试 |
| `SummonerRankInfoNotFound` | 无段位信息 | 正常重试 |
| `SummonerNotInGame` | 召唤师不在游戏中 | 正常重试 |
| `RetryMaximumAttempts` | retry 耗尽（兜底） | — |

**约定**：
- ✅ 业务方法在对应"未找到"场景**主动抛**上述异常，让上层统一处理。
- ❌ **禁止裸 `except:` 或 `except Exception: pass`**（见 §5.3，全仓 31 处待清理）；要捕获就写明异常类型并至少 `logger.warning`。
- ✅ 对 LCU 未就绪场景依赖 `ReferenceError`（`@needLcu` 抛出），`@retry` 会静默吞掉，**不要**再额外弹窗。
- ⚠️ `@retry` 装饰器用 `except CancelledError: raise` 显式放行取消，再用 `except Exception as e:` 兜底——新增类似装饰器须照搬此模式。

### 4.9 打包发布流程

```
开发者侧：
  1. 改 app/common/config.py 的 VERSION（如 "1.1.4" → "1.1.5"），如有 BETA 则设 BETA 字符串
  2. commit + push 到 main
  3. CI 自动：
     build  (windows-latest, py3.8, make.ps1 -keepDist → Seraphine.7z + dist/Seraphine)
       → release  (git diff 检测 VERSION 变更 → 发布 GitHub Release v1.1.5)
       → publish-tufup  (打 tar.gz + bsdiff 补丁 → 部署到 gh-pages/tufup/)
  4. sync.py 把 Release 镜像到 Gitee（CI 或手动）

产物结构（make.ps1）：
  Seraphine.7z
   └─ Seraphine/
        ├─ Seraphine.exe        # PyInstaller -w -i logo.ico main.py
        └─ app/resource/         # 仅资源（源码已冻结进 exe；含 tufup/metadata/root.json）

本地预打包测试：
  pip install pyinstaller==5.13   # 在 seraphine 环境下
  .\make.ps1 -dest .              # 或默认当前目录
  # 需保留 dist 用于本地 tufup 测试时加 -keepDist:
  .\make.ps1 -keepDist
```

**要点**：
- 只改 `VERSION`，不手动发 Release。
- `make.ps1` 会删除 dist 里的 `app/common`、`app/components`、`app/lol`、`app/view` 源码目录（已被 PyInstaller 冻结），勿误以为丢失；`-keepDist` 保留 `dist/Seraphine` 供 tufup 打 `tar.gz` 增量包。
- PyInstaller 命令含 `--collect-submodules tufup --collect-submodules tuf`：tufup.client 为函数内延迟导入，tuf 内部有动态导入，需显式收集子模块否则 frozen 后运行时 ImportError。
- **tufup 首次 bootstrap**：仓库无 `TUFUP_KEYS_B64` secret 时，publish-tufup job 会生成新密钥并输出到 step summary，需开发者（a）将密钥存为 secret `TUFUP_KEYS_B64`，（b）下载 `tufup-root-json` artifact 中的 `root.json` 提交到 `app/resource/tufup/metadata/root.json` 后重新发版，客户端方可校验更新。

**安装包（Inno Setup）**：
- 脚本：`packaging/installer/Seraphine.iss`，编译需 Inno Setup 6（CI 通过 `choco install innosetup` 安装）
- 编译命令：`ISCC.exe packaging\installer\Seraphine.iss /DMyAppVersion={VERSION} /Q`
- 安装路径：`%LOCALAPPDATA%\Programs\Seraphine`（per-user，无需管理员权限，tufup 可正常写文件）
- CI 的 `build-installer` job 自动构建，产物 `SeraphineSetup-{VERSION}.exe` 随 Release 发布
- 卸载时自动清理 `%LOCALAPPDATA%\Seraphine\tufup_targets` 缓存目录

---

## 5. 已知问题与技术债

### 5.1 代码级 bug 标记清单（FIXME / FIX）

| 位置 | 标记 | 现象 | 影响 | 状态 |
|---|---|---|---|---|
| `app/lol/connector.py:884` | 原 FIXME → 已改为 NOTE | `getGameflowSession()` 在「刚打完一局→开自定义→玩家在红方且蓝方无人」时会**泄露上一局蓝方名单**（teamOne/teamTwo） | 自动查对手可能拿到错误阵容 | ✅ 已修复：`tools.py:parseGameInfoByGameflowSession` (line 720-729) 增加 summonerId 去重 + `0`/`None` 过滤；契约见 `tests/test_parse_game_info.py::TestDedupeContract` |

> 当前代码库已无 `FIXME` 标记；`# NOTE` 注释保留用于记录上游 quirk 与既有约束。

### 5.2 未完成 TODO 清单

| 位置 | TODO 内容 | 性质 |
|---|---|---|
| `app/lol/aram.py:43` | 暂未提供历史版本数据查询接口（需服务端配合） | 功能增强 |
| `app/view/search_interface.py:1386` | 某处可以弹个窗（作者留，需求不明） | 小优化 |

> 另有大量 `# NOTE -- By Hpero4/Zzaphkiel` 注释，记录异步任务生命周期、puuid 刷新语义等，非待办但**改这些区域前务必读注释**。

> 历史已解决：`mode_filter_widget.py` 筛选功能已接入 `GameInfoInterface`；`tools.py` `rollAndSwapBack`（海克斯大乱斗已无摇骰子机制）已删除；`main_window.py` 自定义模式 <5 人重载已加 `allyChampions` + `expected_ally_count` 守卫；`search_line_edit.py` / `search_interface.py` 焦点与分页绘制 FIXME 已无对应代码标记；`style_sheet.py:180,187` team1/team2 预组队高亮色已开放用户自定义（`TeamColorSettingCard`，参见 §6.3）。

### 5.3 代码质量问题（现状→风险→建议）

#### ① 测试套件（已有初步覆盖）
- **现状**：已有 8 个测试文件共 213 用例（CI windows-latest 全绿）：
  - `tests/test_tools_pure.py`（35 用例，覆盖 `translateTier`、`timeStampToStr`、`separateTeams`、`parseSummonerOrder`、`sortedSummonersByGameRole`、`parseGames`、`parseRankInfo`、`parseDetailRankInfo`）。
  - `tests/test_connector_contract.py`（31 用例，mock 私有 HTTP 方法注入预设 LCU 响应，验证 connector 公共方法的返回值结构、异常分支、响应转换契约，覆盖 `getSummonerByPuuid` / `getSummonerGamesByPuuid` / `getRankedStatsByPuuid` / `getCurrentSummoner` / `getGameStatus` / `getMapSide` / `getLobbyStatus` / `getMatchmakingStatus` / `isLobbyReadyToSearch` / `isInTencent` / `getLoginSummonerByPid` / `startMatchmaking`）。
  - `tests/test_json_manager.py`（41 用例，纯数据访问层单测，mock 掉 `static_data.registerAugmentRarity` 副作用后由 8 份构造 JSON 实例化 `JsonManager`，覆盖 `getItemIconPath` / `getSummonerSpellIconPath` / `getRuneIconPath` / `getRuneName` / `getRuneDesc`（含 HTML 白名单过滤与 `.strip("<br>")` 字符集剥离语义）/ `getChampionIconPath` / `getMapNameById` / `getNameMapByQueueId` / `getSkinListByChampionName` / `getSkinIdByChampionAndSkinName` / `getAugmentsIconPath` / `getPerkStyles` 等）。
  - `tests/test_parse_game_info.py`（21 用例，`parseGameInfoByGameflowSession` 契约测试，mock `parseSummonerGameInfo` / `getSummonerGamesInfoViaSGP` / `connector.isInTencent`，覆盖不支持队列早返回、`side='ally'/'enemy'` 选队、`separateTeams` 找不到 summoner 返回 None、**FIXME 修复契约（重复 summonerId / `0` / `None` 去重过滤）**、去重后空 team 返回 None、`parseSummonerGameInfo` 返回 None 被过滤、返回结构 `{summoners, champions, order}`、ranked (420/440) 按 `selectedPosition` 排序、`useSGP` 路径与异常 fallback）。
  - `tests/test_war_criminal.py`（33 用例，覆盖 `_kda`/`_zScore`/`_roleOf` 纯函数、`rateEntireTeam` 集成（明显 worst/明显躺赢狗/平衡全档3/海克斯视野不计/OPGG基线放大/强化基线放大）、`gradeLabel`/`gradeFromScore` 分级、`war_criminal_cache` 读写、`pickHonorTarget` 4 策略。stub PyQt5 使非 Windows 环境可导入）。
  - `tests/test_team_rating.py`（28 用例，专测全队 5 档评级：`gradeFromScore` 阈值边界、`gradeLabel` 贴吧风/马系风胜败方、`rateEntireTeam` 全队分级与排序、缓存 `getTeamRating` 胜败方查询）。
  - `tests/test_version_compare.py`（10 用例，覆盖 `version_utils.coerce_version` 的 PEP 440 解析：`v` 前缀剥离、空串/None 容错、预发布/构建元数据、非法版本回退为原串比较）。
  - `tests/test_tufup_updater.py`（14 用例，覆盖 `tufup_updater` 封装逻辑：开发模式（无 Seraphine.exe）跳过、`root.json` 缺失、`check_update` 成功/无更新/网络异常、`download_and_install` 成功/失败/`progress_hook` 透传/`purge_dst_dir` 默认 True。mock `app.common.config` 与 `tufup.client.Client`，sandbox 无 PyQt5 可跑）。
- **运行方式**：`python -m pytest tests/`（CI 共 213 passed）。CI 在非 Windows 环境通过 `tests/conftest.py` stub `winreg/win32api/win32gui` 使 connector 可导入；`test_war_criminal.py`/`test_team_rating.py` 额外 stub `PyQt5` 使评级算法可独立单测；`test_tufup_updater.py`/`test_version_compare.py` 纯逻辑无 GUI 依赖。
- **CI lint**：`.github/workflows/build_seraphine.yaml` 的 `lint-and-test` job 已用 `ruff check app/ tests/ --output-format=github` **强制阻断**（曾为 `continue-on-error: true` advisory 模式，现已收紧）；161 个历史 ruff 错误（136 个 `--fix` 自动修复 + 18 个手动修复，含 E711/E402/E741/F823/W293）已清零。
- **建议**：后续给 `tools.py` 的 `parseAllyGameInfo` 等带状态依赖的函数补测试；可选引入 `mypy`/`pyright` CI。

#### ② 裸 `except` / 静默吞异常（已清理）
- **现状**：原约 31 处裸 `except:` / `except Exception: pass` 已全部清理（跨 8 文件，含 `util.py`、`aram.py`、`champions.py`、`static_data.py`、`connector.py`、`main_window.py`、`opgg.py`、`opgg_hextech_assist_interface.py`、`hextech_window.py`、`animation_frame.py`）。现统一为具体异常类型 + `logger.debug`/`warning`。
- **残留**：仍有约 19 处 `except Exception:`（如 `parseSummonerData`、`parseGameData` 等），属**有意兜底**（外部数据格式不可控），均带 `logger.warning` 或回退逻辑，非静默吞。
- **建议**：后续仅在外部边界保留兜底，内部代码逐步收敛到具体异常类型。

#### ③ 类型注解缺失（部分覆盖）
- **现状**：`app/lol/tools_pure.py` 已定义 `SummonerParsedData`/`GameSummary`/`GameDetail`/`TeamParticipant`/`TeamGameInfo` 等 `TypedDict`，`tools.py` 中 `parseSummonerData`/`parseGameData`/`parseGameDetailData`/`parseAllyGameInfo`/`parseGameInfoByGameflowSession`/`parseSummonerGameInfo`/`getSummonerGamesInfoViaSGP` 已标注返回类型。`connector.py` 公共 LCU 端点方法（约 50 个，含 getter/setter/action）与私有 HTTP 方法（`__get/__post/__put/__delete/__patch/__sgp__get`）及 `__json_retry_get` 均已标注返回类型（`dict`/`list`/`str`/`int`/`bool`/`bytes`/`None`/`Optional[dict]`/`Union[dict, list]`/`aiohttp.ClientResponse`）。`JsonManager` 约 20 个访问方法（`getItemIconPath` / `getSummonerSpellIconPath` / `getRuneIconPath` / `getRuneName` / `getRuneDesc` / `getChampionIconPath` / `getMapNameById` / `getNameMapByQueueId` / `getMapIconByMapId` / `getChampionList` / `getChampions` / `getSkinListByChampionName` / `getSkinIdByChampionAndSkinName` / `getChampionIdByName` / `getChampionNameById` / `getSkinAugments` / `getPerkStyles` / `getAugmentsIconPath` / `getAugmentsName` / `getSummonerSpellList` 等）已标注返回类型；`__init__` 参数（`itemData`/`spellData`/`runeData`/`queueData`/`champions`/`skins`/`perks`/`augments`）也已标注。`opgg.py` 共 22 个方法已标注（`Opgg` 类 16 个：`start`/`close`/`__fetchTierList`/`__fetchChampionBuild`/`getChampionBuild`/多个 `Optional[dict]`/`__getMayhemChampionSlug`/`__downloadAugmentIcon`/`getChampionPositions`；`OpggDataParser` 类 6 个 staticmethod：`parseRankedTierList`/`parseOtherTierList` 等）。
- **残留**：`tools.py` 中部分辅助函数、`aram.py`/`champions.py` 等数据层仍无类型注解。
- **建议**：后续渐进式补全残留模块；可选 `mypy`/`pyright` CI。

#### ④ 自定义异常继承 `BaseException` 的脆弱性（已修复）
- **现状**：`app/lol/exceptions.py` 中 5 个自定义异常均继承 `Exception`（非 `BaseException`）；`@retry` 装饰器用 `except CancelledError: raise` 显式放行取消，再用 `except Exception as e:` 兜底，已不会误捕 `KeyboardInterrupt`/`SystemExit`。
- **建议**：新增类似装饰器时照搬 `except CancelledError: raise` 模式即可。

#### ⑤ 硬编码密钥
- **现状**：`app/lol/aram.py:22` 的 `APP_SECRET` 已改为从环境变量 `SERAPHINE_ARAM_SECRET` 读取，未设置时回退旧的硬编码值。
- **风险**：旧密钥已收敛；推荐所有开发者设置 `SERAPHINE_ARAM_SECRET` 环境变量以彻底消除密钥泄漏。
- **建议**：长期看可与服务端协商限流方案以彻底消除客户端密钥。

#### ⑥ Windows 强耦合，无跨平台抽象层
- **现状**：`win32api`/`winreg`/`win32gui`/`tasklist`/`wmic`/`ctypes.windll` 散落各处。
- **风险**：无法在 macOS/Linux 运行（可接受，目标就是 Windows）；但即便只考虑 Windows，进程发现的 `tasklist`→`psutil`→`wmic` 多级回退路径复杂且各自有裸 except。
- **建议**：统一收敛到 `util.py` 的薄抽象层，对外只暴露 `getLolClient()` 一类高层 API。

#### ⑦ 死代码 / 调试代码（已清理）
- **现状**：原列出的 3 项已全部处理：
  - `OpggWindow` 隐藏 debug 按钮及其处理函数 `__onDebugButtonClicked` 已移除。
  - `getLoginSummonerByPid` 已从同步 `requests` 改为 `aiohttp.ClientSession` 异步实现（含 `BasicAuth` + `TCPConnector(ssl=False)` + `ClientTimeout(total=3)`），异常分支捕获 `aiohttp.ClientError`/`asyncio.TimeoutError`/`ValueError` 返回 `{}`；调用链已改造（`start_interface.__onPushButtonClicked` 用 `@asyncSlot` + `asyncio.gather` 并发预取多客户端召唤师信息后传给 `ChangeClientMessageBox`，避免阻塞 Qt 事件循环）。`requests` import 已从 connector.py 移除。
  - `sendNotificationMsg` 经核实为同步工具方法，沿用现状。
- **建议**：保持定期核查，避免新的调试代码遗留。

#### ⑧ connector 单例的可变状态竞态（已加锁保护）
- **现状**：`connector` 进程内唯一，`port/token/server/manager` 可变；多客户端切换靠 `start()/close()` 复用。`LolClientConnector.__init__` 中新增 `self._stateLock = asyncio.Lock()`（用 `hasattr` 守卫，避免 `close()` 末尾 `self.__init__()` 重置锁），`start()`/`close()` 均在 `async with self._stateLock:` 临界区内执行，防止 `lolClientEnded` 与 `lolClientChanged` 信号触发的 task 在 asyncio 事件循环中交错导致 close 与 start 并发。
- **残留风险**：`__onLolClientChanged` 内 `close→start` 之间释放锁的窗口仍可能被其他 start 插入（罕见，且 start 内部重建 session 不会崩溃）；in-flight 请求在 close 后遇 `lcuSess is None` 由 `@needLcu` 抛 `ReferenceError`、`@retry` 静默吞掉，属既有行为。
- **建议**：如需更强保证，可在 `__onLolClientChanged` 层面再加一把可重入锁串行化整个切换流程。

### 5.4 客户端侧风险（README 已声明）

- **#158**：使用过程中客户端**闪退**——怀疑客户端无法承载某些 HTTP 访问。
- **#408**：极少数情况**账号封禁**——理论上 LCU API 不破坏完整性，但反作弊更新存在不确定性。

> 开发新功能时牢记：**客户端脆弱**，默认 `apiConcurrencyNumber=1`、调用间适当间隔，避免高频并发请求。

---

## 6. 功能开发指引

### 6.1「需求→落地」标准模板

以「**新增赛后统计弹窗**」为例，串起各层：

```
1. 需求澄清
   - 数据从哪来？→ LCU /lit-games/v1/session 或 EndOfGame 事件
   - 触发时机？→ gameStatusChanged 收到 'EndOfGame'（见 §2.6）
   - 配置项？→ 是否启用、显示哪些字段（见 §4.2）

2. 数据层（app/lol/）
   - connector.py：加 @retry @needLcu async def getEndOfGameStats(self): ...
   - tools.py：def parseEndOfGameStats(raw) -> dict（纯函数，可单测）

3. 配置层（app/common/config.py）
   - enableEndOfGamePopup = ConfigItem("Functions", "...", False, BoolValidator())

4. UI 层（app/view 或 app/components）
   - 新建 popup widget 或复用 message_box.py 的对话框模式
   - 文案 self.tr()，QSS 双主题

5. 编排（app/view/main_window.py）
   - __onGameStatusChanged 的 'EndOfGame' 分支：
       if cfg.get(cfg.enableEndOfGamePopup):
           raw = await connector.getEndOfGameStats()
           data = parseEndOfGameStats(raw)
           self.__showEndOfGamePopup(data)

6. 信号（如需跨界面通信）
   - signals.py 加 pyqtSignal → __conncetSignalToSlot 接线

7. 资源
   - 新图标走 connector 拉取；i18n 更新 .ts/.qm；QSS 双主题

8. 设置页
   - setting_interface.py 加 SwitchSettingCard 绑 enableEndOfGamePopup

9. 测试 / 验证
   - 至少给 parseEndOfGameStats 写 pytest 单测（见 §5.3 ①）
   - 手动走查完整 BP→对局→结束流程

10. 发版
    - 改 VERSION → push → CI 自动出 Release
```

### 6.2 与 LCU / Riot 的能力边界

README FAQ 已明确：**英雄联盟客户端未提供**以下数据，Seraphine 因此做不到——开发时勿浪费时间找接口：

- 特定模式 / 特定英雄的**总场次与总胜率**（需自己累计，但客户端不提供原始数据）。
- 云顶之弈（TFT）战绩（本项目明确不支持）。
- 跨大区战绩（仅同大区）。

国服（Tencent SGP）部分数据走 SGP 端点，能力与全球 LCU 略有差异，开发前查 `connector.isInTencent()` 分支。

### 6.3 同类项目功能矩阵（2026‑07）

| 功能 | Seraphine (本 fork) | LeagueAkari | KBotExt | league-tools | L9Lenny profile_tool |
|---|---|---|---|---|---|
| 技术栈 | PyQt5, Python | Electron, Vue 3, TS | C++, Win32 | Electron, TS | Tauri v2, React, Rust |
| 活跃度 | ✅ 活跃 | ✅ 活跃 (v1.4.3) | ⚠️ 停滞 (2024‑05) | ✅ 活跃 | ✅ 活跃 |
| 战绩查询 (队友/对手) | ✅ | ✅ | ❌ | ❌ | ❌ |
| 自动 B/P (选/禁/秒接) | ✅ | ✅ | ✅ | ❌ | ❌ |
| OPGG 一键符文 | ✅ | ✅ | ✅ | ❌ | ❌ |
| 海克斯/大乱斗抢人 | ✅ | ✅ | ❌ | ❌ | ❌ |
| 个人资料修改 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 全队 5 档评级 | ✅ 独家 | ❌ | ❌ | ❌ | ❌ |
| 战犯诊断 | ✅ | ❌ | ❌ | ❌ | ❌ |
| 增量自更新 (tufup) | ✅ | ✅ | ✅ (内置) | ❌ | ✅ (签名) |
| 安装包 (Inno Setup) | ✅ | ❌ | ❌ | ❌ | ❌ |
| 好友管理 (批量删/加) | ❌ | ✅ | ✅ | ❌ | ✅ |
| 大厅暴露召唤师名 | ❌ | ❌ | ✅ | ❌ | ❌ |
| 自定义 LCU 请求发送 | ❌ | ❌ | ✅ | ❌ | ❌ |
| 多开客户端 | ❌ | ❌ | ✅ | ❌ | ❌ |
| 修客户端窗口 | ✅ | ✅ | ❌ | ❌ | ❌ |
| 观战 | ✅ | ✅ | ❌ | ❌ | ❌ |
| 跨平台 | ❌ (Win) | ❌ (Win) | ❌ (Win) | ✅ (Win/Linux) | ✅ (Tauri) |

### 6.4 下一步规划（优先级排序）

#### 📦 P0 — 基础设施完善（当前 sprint）
- [x] CI 自动构建 7z + 安装包 + tufup 增量更新
- [x] 默认开启自动检查更新
- [x] 设置页"Check Now"手动检查按钮
- [ ] **导航栏更新 badge**：检测到新版本时在 Settings 图标右上角显示小红点 + 主界面右下角 InfoBar 提示
- [ ] **定时轮询检查**：启动后每 4h 用 QTimer 自动检查一次

#### 🎯 P1 — 功能补齐（对标竞品缺失项）
- [ ] **好友管理器**：批量删除好友、接受好友请求、查询好友最近对局
- [ ] **大厅暴露召唤师名**：Ranked 选人阶段显示队友/对手 ID（KBotExt 热门功能）
- [ ] **秒退不关客户端**：通过 `POST /lol-lobby/v2/leave-queue` 实现，省 30s 重开时间
- [ ] **OPGG 代理设置**：已支持 HTTP 代理，可补充内置代理/缓存加速国内访问

#### 📊 P2 — AI 复盘扩展
- [ ] **最近 N 场趋势曲线**：生涯页胜率/KDA 折线图（数据已就绪，需图表组件）
- [ ] **代练/小号预警**：查对手时算近期胜率+KDA 突变+段位差，标记"疑似小号"
- [ ] **连胜/连败 momentum**：结算后弹"已连败 N 场，建议休息"
- [ ] **队友位置冲突预警**：BP 阶段检测多人常玩同位置 → 提示"建议秒"

#### 🔬 P3 — 探索性方向
- [ ] **对局中实时提醒**：打野计时/龙刷新/敌方消失（已有 `live_client.py` + `liveGameDataUpdated` 信号）
- [ ] **Replay 管理器**：浏览/重命名/分享 .rofl 文件
- [ ] **赛季分析面板**：按英雄/角色/双排队友/时段的胜率统计
- [ ] **皮肤/战利品通知**：检测宝箱资格、皮肤折扣、英雄碎片

> 已完成方向：GameInfo 按队列模式筛选（`mode_filter_widget.py` 已接入 `GameInfoInterface`）；自定义模式 <5 人重载守卫（`main_window.py`）；rollAndSwapBack 删除（海克斯大乱斗无摇骰子）；team1/team2 预组队高亮色开放用户自定义（`TeamColorSettingCard`，cfg 项 `team1Color`/`team2Color`，经 `signalBus.customColorChanged` 触发刷新）；`getLoginSummonerByPid` 异步化改造；CI ruff lint 收紧为强制阻断 + 161 个历史错误清零；`JsonManager` + `opgg.py` 类型注解补全；`parseGameInfoByGameflowSession` 契约测试建立 + §5.1 FIXME（自定义模式名单泄露）修复；**结算后自动点赞**（`tools_pure.pickHonorTarget` 4 策略 + `connector.getEogStats/submitHonor`，cfg 项 `enableAutoHonor`/`autoHonorStrategy`/`autoHonorDelay`）；**全队 5 档评级**（`war_criminal.py` z-score 算法 + `grade_badge.py` UI + OPGG 胜率/海克斯强化基线，cfg 项 `enableTeamRating`/`teamRatingStyle`）。

---

## 7. 附录

### 7.1 关键文件路径速查

| 用途 | 路径 |
|---|---|
| 入口 | `D:\Code\Seraphine\main.py` |
| 版本常量 | `app\common\config.py:251`（`VERSION`） |
| 配置单例 | `app\common\config.py`（`cfg`） |
| 信号总线 | `app\common\signals.py`（`signalBus`） |
| 日志器 | `app\common\logger.py`（`logger`） |
| Win32/进程辅助 + GitHub | `app\common\util.py` |
| 增量更新（客户端） | `app\common\tufup_updater.py` |
| 版本比较（纯函数） | `app\common\version_utils.py` |
| tufup 仓库管理（CI 端） | `tufup_repo.py`（仓库根） |
| LCU 连接器（REST+WS） | `app\lol\connector.py`（`connector`） |
| 业务逻辑 / 自动 B/P | `app\lol\tools.py`（`ChampionSelection` 等） |
| 纯函数（可单测） | `app\lol\tools_pure.py`（`pickHonorTarget` 等） |
| 全队 5 档评级算法 | `app\lol\war_criminal.py`（`rateEntireTeam`/`gradeFromScore`） |
| 评级结果缓存 | `app\lol\war_criminal_cache.py`（`setVerdict`/`getTeamRating`） |
| 海克斯强化基线 | `app\lol\augment_baseline.py`（`getHextechAugmentScore`） |
| 英雄 OPGG 胜率基线 | `app\lol\champion_baseline.py`（`getChampionBaselineWinrate`） |
| 进程监听 | `app\lol\listener.py` |
| 自定义异常 | `app\lol\exceptions.py` |
| OPGG 客户端 | `app\lol\opgg.py`（`opgg`） |
| ARAM 数据 | `app\lol\aram.py`（`AramBuff`） |
| 英雄昵称 | `app\lol\champions.py`（`ChampionAlias`） |
| 主窗口 / 编排者 | `app\view\main_window.py`（`MainWindow`） |
| 6 个主界面 | `app\view\{start,career,search,game_info,auxiliary,setting}_interface.py` |
| OPGG 窗口 | `app\view\opgg_window.py` + `opgg_tier_interface.py` + `opgg_build_interface.py` |
| 页面滚动基类 | `app\components\seraphine_interface.py` |
| 自定义对话框 | `app\components\message_box.py` |
| 原生修复器源码 | `app\resource\bin\fix_lcu_window.c` |
| 版本 kill-switch | `document\ver.json` |
| 打包脚本 | `make.ps1` |
| CI | `.github\workflows\build_seraphine.yaml` |
| Issue 模板 | `.github\ISSUE_TEMPLATE\{bugreport,enhancement,question}.yml` |
| 翻译项目（Linguist） | `Seraphine.pro` |

### 7.2 依赖清单

| 依赖 | 版本 | 用途 |
|---|---|---|
| PyQt5 | 5.15.9 | GUI 框架 |
| PyQt5-sip | 12.12.1 | 绑定运行时 |
| PyQt-Fluent-Widgets | 1.5.7 | Fluent 控件 + QConfig |
| qasync | 0.27.1 | asyncio ↔ Qt 桥接 |
| aiohttp | 3.10.10 | LCU REST + WS 客户端 |
| requests | 2.32.3 | 同步 HTTP（更新检查、Gitee 同步） |
| psutil | 5.9.8 | 进程检测 |
| pyperclip | 1.8.2 | 剪贴板 |
| tufup | ≥0.10.0 | TUF 增量更新（bsdiff 补丁） |
| packaging | ≥23.0 | PEP 440 版本比较 |
| async-lru | 2.0.4 | 异步 LRU 缓存 |
| pywin32（隐式） | — | Win32 API |
| PyInstaller | 5.13（仅打包） | 打包 |

### 7.3 外部数据源 / 接口汇总

| 数据源 | 端点 | 用途 |
|---|---|---|
| LCU REST | `https://127.0.0.1:{port}/...` | 召唤师/对局/BP 全部主数据 |
| LCU WebSocket | `wss://127.0.0.1:{port}/` | 实时事件推送（4 个订阅） |
| Tencent SGP | `https://{server}-sgp.lol.qq.com:21019/...` | 国服战绩/排位/观战补充（Bearer 鉴权） |
| OPGG | `lol-api-champion.op.gg` | 英雄排行 + 出装加点 |
| GitHub API | `api.github.com/repos/Li-Qifeng/Seraphine/...`（默认指向当前维护者 fork，见 `util.Github`） | Release / 公告 / `ver.json` kill-switch |
| 大乱斗之家 | `jddld.com` | ARAM Buff 数据 |
| 腾讯 gtimg | `game.gtimg.cn` | 英雄中文昵称/关键词 |

### 7.4 参考资料

- LCU API 文档：
  - https://riot-api-libraries.readthedocs.io/en/latest/lcu.html
  - https://hextechdocs.dev/tag/lcu/
  - https://developer.riotgames.com/docs/lol
  - https://www.mingweisamuel.com/lcu-schema/tool/
- 同类参考项目：`KebsCS/KBotExt`、`XHXIAIEIN/LeagueCustomLobby`、`7rebux/league-tools`
- 锁定游戏设置：https://www.bilibili.com/video/BV1s84y1x7ub
- 修复客户端缩窗：https://github.com/LeagueTavern/fix-lcu-window
- 游戏资源：https://raw.communitydragon.org/latest/ 、https://github.com/CommunityDragon/Docs/blob/master/assets.md
- Fluent Icons：https://fluenticons.co/outlined
- GUI 基础：PyQt5 + https://github.com/zhiyiYo/PyQt-Fluent-Widgets

---

*本文档基于 v1.1.9 源码梳理。代码变更时请同步更新对应章节，并在版本升级时更新顶部「适用版本」。*
