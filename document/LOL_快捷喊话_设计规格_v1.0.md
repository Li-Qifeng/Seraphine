# LOL 快捷喊话子系统 — 设计规格 v1.0

> 状态：**已与需求方逐条确认收敛（2026-09-09），进入开发**
> 上游输入：`D:\Code\lol-chat` 调研链（docs/01~05、references/A~G），其中 D1~D10 原决策经本轮沟通**部分修订**（见 §2）
> 宿主：Seraphine 本仓库 `feat/in-game-chat` 分支；开发环境 conda `seraphine_dev`（Python 3.10，**但代码须兼容 CI 打包的 Python 3.8**）

---

## 1. 一句话定位

**并入 Seraphine 的局内快捷喊话子系统**：全局热键直发（分组热键 + 组内循环），双通道发送（局内 SendInput 模拟输入 / BP·房间走 LCU），本地话术库（内置 seed + 自定义扩充），限流抖动作行为护栏，独立设置页管理；**全程人工触发，绝不自动发送**。

## 2. 本轮范围（与需求方确认）

### In scope

| # | 功能 | 规格 |
|---|---|---|
| F1 | 内置词库 | seed 机制，首次启动自动导入；内容精而少（约 5 组 × 5 条），支持后续版本升级合并（用户改过的 `dirty=1` 不覆盖，删除只标记 `enabled=0`） |
| F2 | 自定义扩充 | 话术/分组的增删改查、启停（用户资产，独立库文件 `seraphine_chat.db`，**只增不删、永不 DROP 重建**） |
| F3 | 分组热键直发 | 默认 `Alt+1`~`Alt+9`/`Alt+0` 绑分组 1~10；**组内循环**：每按一次发送组内下一条（顺序固定，设置页可见循环顺序与"下一条"预览）；热键可自定义改绑，**保存时冲突硬拦截**（LOL 默认键位 / Windows 系统键 / 其他已绑话术） |
| F4 | 双通道发送 | 生效矩阵：**InProgress 且游戏前台 → SendInput 逐字模拟**；**ChampSelect / Lobby → LCU** `POST /lol-chat/v1/conversations/{id}/messages`（复用 connector 现有会话发现逻辑）；其余状态热键不响应 |
| F5 | 发送方式可切 | 单字组句 = SendInput 逐字（默认，真机已压测达标）；整条发 = 剪贴板一次性粘贴（**默认关**，含全格式保存/还原 + 用户新复制检测） |
| F6 | 限流 + 抖动 | 最小间隔 ≥800ms ±30% 抖动；连续 3 条后强制 ≥3s 冷却；按键间隔 20ms + 5~15ms 抖动；参数在设置页可调（带硬下限） |
| F7 | 独立设置页「快捷喊话」 | 导航栏新增独立项。含：话术管理（CRUD/启停/热键绑定/使用统计）、循环顺序与下一条预览、总开关（**默认关**）、通道参数、发送方式切换、词库展示、发送日志查看 |
| F8 | 发送日志 | DB 表 `send_log`，滚动保留 30 天：时间/文本/通道/结果；设置页可查看 |

### Out of scope（本轮不做）

迷你指令窗（原 D9，推迟）· 连发（原 D7，取消本轮）· 变量引擎（原 D5，推迟）· 话术包导入导出 · 打字触发 · **内容安全模块整个不做**（需求方明示接受风险：封号主要风险源为内容审核，本地裸发送无预检护栏）

### 🔴 明确拒绝项（无妥协空间）

需求方曾提出"敏感词混淆转换器"（繁体/全半角混淆/等宽字符注入/拆偏旁部首规避审核）。**不予实现**——属审核对抗功能，违反《英雄联盟》游戏插件公约与 Riot 政策，且会招致用户加重处罚与工具下架。需求方已知情并改为放弃安全模块。

## 3. 原 D1~D10 决策修订记录

| # | 原决策 | 本轮结论 |
|---|---|---|
| D1 | M1 热键+指令窗 | **修订**：仅热键直发，指令窗推迟 |
| D5 | 变量引擎 M2 | 维持推迟，本轮不做 |
| D7 | 做受控连发 | **修订**：本轮不做 |
| D8 | 内置词库 | **确认**：内置 seed + 自定义扩充 |
| D9 | 指令窗保留 | **修订**：推迟 |
| 其余 | D2/D3/D4/D6/D10 | 维持（并入 Seraphine / SQLite 独立库 / 仅 LOL 等） |

新增决策：
- **D11 热键语义**：分组热键 + 组内循环；防护措施 = 设置页可见循环顺序与下一条预览（需求方选定）
- **D12 安全模块**：整个不做（需求方明示，风险自担）
- **D13 发送方式**：单字组句默认 / 剪贴板整条默认关，设置页可切

## 4. 架构与模块落位

```
app/chat/                      # 子系统内核，与 app/lol/ 平级
├── __init__.py
├── model.py                   # Phrase / Group 数据类（dataclass，3.8 兼容）
├── store/
│   ├── db.py                  # SQLite 封装（%APPDATA%/Seraphine/seraphine_chat.db，WAL，只增不删）
│   ├── repo.py                # PhraseRepo / GroupRepo：CRUD/search/record_use/循环游标
│   └── seed.py                # BUILTIN_PACK 内置词库 + 幂等导入/升级合并
├── domain/
│   ├── rhythm.py              # 限流 + 抖动 + 冷却（纯逻辑，可单测）
│   ├── keys.py                # 键位解析 + 冲突校验（LOL_RESERVED_KEYS 硬拦截，纯逻辑）
│   └── orchestrator.py        # SendOrchestrator 唯一发送出口（阶段路由→闸→限流→发送→记账）
├── engine/
│   ├── input_sim.py           # SendInput(KEYEVENTF_UNICODE) 逐字 + Enter 补 wScan + 剪贴板整条（默认关）
│   ├── foreground.py          # 前台判定（进程名 league of legends.exe，标题匹配回退）
│   └── hotkey.py              # HotkeyManager(QAbstractNativeEventFilter)：RegisterHotKey，hwnd=NULL
└── service.py                 # ChatService 单例门面（初始化 DB/seed/热键，订阅 signalBus.gameStatusChanged）

app/common/chat_config.py      # chat_config.json 独立配置（不塞进现有 Config 类），默认 enabled=False
app/view/chat_interface.py     # 设置页「快捷喊话」
app/resource/qss/{light,dark}/chat_interface.qss
```

**接线纪律**：不改 `MainWindow.__conncetSignalToSlot`；热键用 `QAbstractNativeEventFilter` 收 `WM_HOTKEY`；游戏状态订阅 `signalBus.gameStatusChanged`；LCU 发送复用 `connector`（会话发现逻辑参照现有 `sendChampSelectMessage`）。

## 5. 关键工程纪律（调研踩坑沉淀）

1. **Python 3.8 兼容**：禁止 `list[...]` / `X | Y` 注解（CI 打包跑 3.8，曾线上崩过）
2. **Win32 调用必须显式声明 `argtypes/restype`**（64 位 HANDLE 截断坑）
3. **Enter/Ctrl 必须补 `wScan`**（`MapVirtualKey(vk, MAPVK_VK_TO_VSC)`），否则游戏完全忽略
4. **pywin32 显式写入 `requirements.txt`**（此前靠传递依赖，断了启动即崩）
5. 新文件登记 `Seraphine.pro`（否则 `tr()` 抽不到）
6. ruff 强制绿；TDD：domain/store 纯逻辑先写测试

## 6. 验收标准

### 离线可验（开发方交付）

- [ ] `pytest tests/` 全绿（含新增 chat 用例：repo CRUD/seed 幂等/rhythm 限流冷却/keys 冲突拦截/orchestrator 阶段路由与组内循环）
- [ ] `ruff check app/ tests/` 全绿
- [ ] offscreen 冒烟：构造 ChatInterface → seed 5 组 → 启用后热键注册 → `Alt+1` 循环发送顺序正确 → 无游戏时闸拦截 → 关闭后热键注销
- [ ] 无 `list[` / `X | Y` 注解（3.8 兼容 grep 检查）

### 真机验收（需求方，训练模式）

- [ ] 启用总开关 → 游戏前台按 `Alt+1` → 话术进聊天框并发出（连续 20 次成功率 ≥95%）
- [ ] 组内循环：连按 3 次 `Alt+1` 依次发出组内第 1/2/3 条，第 4 次回到第 1 条
- [ ] BP 阶段按热键 → 消息出现在 BP 聊天（LCU 通道）
- [ ] 游戏非前台 / 未运行时按热键无反应
- [ ] 改绑热键为 `Alt+Q` → 保存被硬拦截
- [ ] send_log 记录完整（时间/文本/通道/结果）

## 7. 已知风险与声明

| 风险 | 说明 | 应对 |
|---|---|---|
| 无内容预检 | 裸发送，骂人/敏感词直发会被服务端审核处罚 | 需求方明示接受（D12）；README/UI 加免责提示 |
| 组内循环误发 | 用户不预知本次发出哪条 | 设置页循环顺序 + 下一条预览（D11）；send_log 可追溯 |
| 客户端脆弱 | 高并发 HTTP 会崩客户端（#158） | LCU 发送走 connector 既有 `@retry`+信号量 |
| 剪贴板路径 | 与剪贴板管家冲突、隐私副作用 | 默认关（D13），粘贴前读回校验 |
