# Sona 源码分析报告

> 基于 Sona v1.6.0 (AGPL-3.0) 源码分析，供 Seraphine 架构参考
> 分析日期：2026-07-03

---

## 目录

1. [架构总览](#1-架构总览)
2. [核心支撑模块](#2-核心支撑模块)
3. [功能模块实现模式](#3-功能模块实现模式)
4. [关键技术点详解](#4-关键技术点详解)
5. [与 Seraphine 的对比与可复用模式](#5-与-seraphine-的对比与可复用模式)
6. [附录：功能模块清单](#6-附录功能模块清单)

---

## 1. 架构总览

### 1.1 系统定位

Sona 是一个运行在 LCU (League Client Update) 内置 Chromium 浏览器中的插件，依赖 **Pengu Loader** 注入到客户端进程中。它的本质是一个前端应用，获得了对客户端 DOM 的完全控制权和 LCU API 的直接访问权限。

### 1.2 架构分层

```
┌──────────────────────────────────────────────────────┐
│                   功能模块层 (features/)                │
│  auto-accept  auto-ban  auto-lock  auto-honor  ...    │
│  champselect-quit-button  custom-banner  profile-bg   │
│  game-analysis-popup  enhanced-friend-status  ...      │
├──────────────────────────────────────────────────────┤
│                   核心支撑层 (lib/)                     │
│  features.ts  (功能注册/调度/生命周期)                  │
│  store.ts     (配置定义/持久化/监听)                    │
│  lcu.ts       (LCU API 客户端 + WebSocket 观察)         │
│  injections.ts (DOM 注入点注册中心)                     │
│  InjectorManager.ts (全局 DOM 注入管理器)               │
│  logger.ts    (日志工具)                                │
│  utils.ts     (工具函数)                                │
├──────────────────────────────────────────────────────┤
│                   运行环境层                             │
│  Pengu Loader (注入宿主)                                │
│  LCU Chromium 浏览器 (运行时)                           │
│  LCU API (HTTP + WebSocket)                           │
└──────────────────────────────────────────────────────┘
```

### 1.3 数据流

```
用户操作 UI 开关 → store.ts onChange 回调
  → features.ts initFeatures() 
    → 各 feature updateXxx(enabled)
      → enabled: 订阅 LCU 事件 + 注册 injector 任务
      → disabled: 取消订阅 + 取消注入

LCU WebSocket 事件 → lcu.ts 分发
  → features.ts GameflowPhase 订阅 → 各 feature onGameflowPhase / onChampSelectSession
  → InjectorManager 触发 DOM 注入

Store 配置变更 → DataStore.set() 持久化
  → 跨会话保持
```

### 1.4 目录结构

```
sona/
├── src/
│   ├── index.ts              # 入口：初始化 store → features → injections
│   ├── App.tsx               # React 根组件（配置面板 UI）
│   ├── lib/
│   │   ├── lcu.ts            # LCU API 封装
│   │   ├── store.ts          # 配置管理
│   │   ├── features.ts       # 功能注册调度
│   │   ├── InjectorManager.ts # DOM 注入管理器
│   │   ├── injections.ts     # 注入点定义
│   │   ├── logger.ts         # 日志
│   │   └── utils.ts          # 工具函数
│   ├── components/           # React UI 组件
│   ├── features/             # 功能模块（~25 个）
│   └── i18n/                 # 国际化
├── vite.config.ts            # Vite 配置
└── package.json
```

---

## 2. 核心支撑模块

### 2.1 `lcu.ts` — LCU API 客户端

**文件**: `D:\Code\sona\src\lib\lcu.ts`

这是连接 LCU 的通信核心，提供 HTTP 请求和 WebSocket 事件订阅能力。

#### 2.1.1 HTTP 请求封装

```typescript
// GET 请求
export async function request(method: string, url: string, body?: any): Promise<any>
// 便捷方法
export const get = (url: string) => request('GET', url)
export const post = (url: string, body?: any) => request('POST', url, body)
export const put = (url: string, body?: any) => request('PUT', url, body)
export const del = (url: string, body?: any) => request('DELETE', url, body)
export const patch = (url: string, body?: any) => request('PATCH', url, body)
```

**关键实现细节**:
- 底层用 `fetch()` —— 浏览器原生 API，不需要 port/token（Pengu 自动代理）
- 无重试逻辑 —— 运行在客户端内，连接稳定
- 无超时设置 —— 依赖浏览器默认行为
- 返回 `response.json()`，失败时 throw error

**与 Seraphine 对比**: Seraphine 需要自行解析 `tasklist` 找到 port/token，用 `aiohttp` 构造 `https://127.0.0.1:{port}` 带 Basic Auth 的请求，且有 `@retry(count=5)` + `Semaphore(1)` 并发控制。Sona 因为运行在客户端浏览器内，这些都不需要。

#### 2.1.2 WebSocket 事件观察

```typescript
export function observe<T>(eventUri: string, cb: (data: T) => void, eventType?: string): () => void
```

**关键实现细节**:
- 底层调用 `PenguContext.socket.observe(eventUri, cb, eventType)` —— Pengu 提供的 WebSocket API
- 返回 `unsubscribe` 函数 —— 让调用者可以取消订阅
- 类型参数 `T` 让事件数据类型化
- 无重连逻辑 —— Pengu 管理 Socket 生命周期
- 无过滤/缓冲 —— 事件直接透传

**与 Seraphine 对比**: Seraphine 需要手动创建 WebSocket 连接 (`wss://127.0.0.1:{port}`)，处理握手、心跳、重连；而 Sona 这个只需要一行代码。

#### 2.1.3 LCU 事件常量

```typescript
export const LCU_EVENTS = {
  GAMEFLOW_PHASE: '/lol-gameflow/v1/gameflow-phase',
  CHAMP_SELECT_SESSION: '/lol-champ-select/v1/session',
  READY_CHECK: '/lol-matchmaking/v1/ready-check',
  CURRENT_SUMMONER: '/lol-summoner/v1/current-summoner',
  EOG_DETAILS: '/lol-end-of-game/v1/eog-details',
  HONOR_CONFIG: '/lol-honor-v2/v1/config',
  // ... 其他事件
}
```

**设计要点**: 将所有 LCU 事件 URI 集中定义为常量，便于复用和后续 LCU 版本变更时统一修改。

#### 2.1.4 LCU API 端点封装

`lcu.ts` 还封装了大量 LCU API 端点，按功能域组织：

- **ChampSelect**: `getCurrentChampSelectSession()`, `getChampSelectPickableChampionIds()`, `getChampSelectBanableChampionIds()`, `patchChampSelectSession()`, `champSelectAction()`, `champSelectRetractAction()`, `champSelectBenchSwap()`
- **Honor**: `getHonorConfig()`, `getHonoredPlayers()`, `postHonorPlayer()`
- **Gameflow**: `playAgain()`, `searchLobby()`, `acceptReadyCheck()`
- **Lobby**: `getLobbyMembers()`, `getLobbyMemberCount()`, `getLobbyMember*()`
- **Perks**: `getPerksInventory()`, `putPerksPage()`, `deletePerksPage()`, `getPerksPage()`
- **Summoner**: `getCurrentSummoner()`, `getSummonerBySummonerName()`, `getSummonerByPuuid()`
- **Chat**: `getConversations()`, `getMessages()`, `sendMessage()`
- **Login**: `getLoginSession()`
- **Eog**: `getEogDetails()`
- **Regalia**: `getCurrentSummonerRegalia()`

**设计要点**: 所有端点都是纯函数，无状态，只封装 HTTP 请求细节和类型签名。

### 2.2 `store.ts` — 配置管理

**文件**: `D:\Code\sona\src\lib\store.ts`

Sona 的配置系统是类型安全的，支持默认值、监听变更、持久化。

#### 2.2.1 配置结构

```typescript
export const defaultConfig = {
  // 通用
  enabled: true,
  lang: 'auto' as 'zh-CN' | 'en-US' | 'auto',

  // 自动接受对局
  'auto-accept': {
    enabled: false,
    delay: 1000,            // 延迟毫秒
  },

  // 自动禁用英雄
  'auto-ban-champion': {
    enabled: false,
    champions: [] as number[],  // 首选英雄 ID 列表
  },

  // ... 约 80 项配置
}
```

#### 2.2.2 运行时 Store

```typescript
export class SonaStore {
  private config: SonaConfig
  private listeners: Map<string, Set<(value: any) => void>>

  // 获取配置（类型安全）
  get<K extends keyof SonaConfig>(key: K): SonaConfig[K]

  // 设置配置（触发 onChange + 持久化）
  set<K extends keyof SonaConfig>(key: K, value: SonaConfig[K]): void

  // 监听单个配置变更
  onChange<K extends keyof SonaConfig>(key: K, cb: (value: SonaConfig[K]) => void): () => void

  // 从 DataStore 初始化
  async init(): Promise<void>

  // 持久化到 DataStore
  private async save(): Promise<void>
}
```

#### 2.2.3 关键实现细节

- **类型安全**: 所有配置项有完整 TypeScript 类型定义，IDE 自动补全
- **`onChange` 监听**: 返回取消函数，与 React `useEffect` 的 cleanup 模式一致
- **持久化**: 使用 Pengu `DataStore` API（键值对存储），每次 `set()` 自动 `save()`
- **初始化**: `init()` 从 DataStore 读取上次配置，与 defaultConfig 深度合并
- **`:never` 尾坠**: 每个功能模块的最后一条 `onChange` 返回 `:never` 类型，确保分支覆盖完整

**与 Seraphine 对比**: Seraphine 的 `QConfig` 方案类似——都是单例 + 序列化到 JSON 文件 + 监听变更。不同在于 Seraphine 用 PyQt5 信号 (`configChanged`)，Sona 用回调函数。

### 2.3 `features.ts` — 功能注册调度中心

**文件**: `D:\Code\sona\src\lib\features.ts`

这是所有功能模块的统一入口和管理调度中心。

#### 2.3.1 功能注册

```typescript
export function initFeatures(store: SonaStore): void {
  // 每个功能：
  // 1. 读取当前开关状态
  // 2. 注册 onChange 监听（开关切换时调用）
  // 3. 初始状态下启用功能

  store.onChange('auto-accept', (value) => {
    updateAutoAccept(value)
  })
  updateAutoAccept(store.get('auto-accept'))

  // ... 其他功能类似
}
```

**设计模式**: 注册即生效。`initFeatures()` 在应用启动时调用一次，遍历所有功能，注册变更监听并执行初始状态同步。

#### 2.3.2 GameflowPhase 订阅

```typescript
// 全局 GameflowPhase 订阅（某些功能不通过 store，直接监听对局状态）
lcu.observe(lcu.LCU_EVENTS.GAMEFLOW_PHASE, (phase: GameflowPhase) => {
  // 分发到各个功能
  autoAcceptFeature.onGameflowPhase(phase)
  autoBanFeature.onGameflowPhase(phase)
  autoReturnToLobby.onGameflowPhase(phase)
  // ...
})
```

**限流设计**: 通过 `requestAnimationFrame` 对高频事件（如 ChampSelectSession 更新）进行节流，避免过度渲染。

#### 2.3.3 生命周期管理

```
Store 配置变更
  → onChange 回调
    → updateXxx(enabled)
      → enabled:
          - LCU 事件订阅（需要时）
          - Injector 任务注册（需要时）
          - React root 创建（需要时）
      → disabled:
          - 取消 LCU 订阅
          - 取消 Injector 任务
          - 销毁 React root / 移除 DOM
```

### 2.4 `InjectorManager.ts` — 全局 DOM 注入管理器

**文件**: `D:\Code\sona\src\lib\InjectorManager.ts`

这是 Sona 实现客户端美化和 DOM 注入能力的核心引擎。

#### 2.4.1 核心设计

```typescript
export class InjectorManager {
  private observer: MutationObserver
  private tasks: Map<string, InjectionTask>
  private pendingTasks: Set<string>

  // 注册注入任务（带自愈能力）
  registerTask(id: string, task: InjectionTask): void

  // 取消任务
  unregisterTask(id: string): void

  // 停止观察（清理）
  destroy(): void
}

interface InjectionTask {
  selector: string            // 目标 DOM 选择器
  inject: (target: HTMLElement) => void  // 注入函数
  onRemove?: (target: HTMLElement) => void  // 清理函数（可选）
}
```

#### 2.4.2 MutationObserver 策略

```typescript
const observer = new MutationObserver((mutations) => {
  // 批量处理，标记所有需要重新注入的任务
  for (const task of this.tasks.values()) {
    if (task.selector) {
      this.pendingTasks.add(task.id)
    }
  }

  // requestAnimationFrame 节流
  if (!this.rafScheduled) {
    this.rafScheduled = true
    requestAnimationFrame(() => this.processTasks())
  }
})

observer.observe(document.body, {
  childList: true,     // 子节点变更
  subtree: true,       // 深度观察
  attributes: false,   // 不需要属性变化
  characterData: false // 不需要文本变化
})
```

#### 2.4.3 关键设计要点

1. **单一全局 Observer**: 整个应用只有一个 MutationObserver，所有 DOM 注入共享
2. **`requestAnimationFrame` 节流**: DOM 变化可能非常频繁，rAF 确保在下一帧统一处理，避免重复注入
3. **自愈能力**: 客户端页面会随着导航重建 DOM（SPA 路由变化），MutationObserver 会自动检测到新 DOM 并重新注入
4. **`selector` 匹配**: 每个任务通过 CSS 选择器定位目标元素，找不到时自动跳过，下次 mutation 再尝试
5. **清理回调**: `onRemove` 在 DOM 被移除时调用，用于释放资源

### 2.5 `injections.ts` — DOM 注入点注册中心

**文件**: `D:\Code\sona\src\lib\injections.ts`

定义具体的 DOM 注入点位置，所有 UI 注入功能从这里统一管理。

#### 2.5.1 注入点定义

```typescript
export function initInjections(manager: InjectorManager, store: SonaStore): void {
  // 入口按钮 — 客户端右上角
  manager.registerTask('entry-button', {
    selector: '.some-header-selector',
    inject: (target) => {
      const btn = document.createElement('div')
      btn.className = 'sona-entry-button'
      btn.textContent = 'Sona'
      btn.onclick = () => toggleSonaPanel()
      target.appendChild(btn)
    }
  })

  // 在线状态切换
  manager.registerTask('online-status-toggle', {
    selector: '.status-selector',
    inject: (target) => { /* ... */ }
  })

  // 更新徽章
  manager.registerTask('update-badge', {
    selector: '.badge-selector',
    inject: (target) => { /* ... */ }
  })
}
```

#### 2.5.2 注入点列表

| 注入点 | 用途 | 注入方式 |
|--------|------|----------|
| 入口按钮 | 客户端右上角 Sona 图标 | 直接 DOM append |
| 在线状态切换 | 好友列表顶部快速切换在线状态 | DOM append |
| 更新徽章 | 版本更新提示标记 | DOM class 操作 |
| 选人界面按钮 | 退出按钮、分析按钮 | DOM 劫持 + append |
| 主页背景区域 | 自定义壁纸容器 | 属性劫持 + React root |
| 生涯页 | 自定义背景、T 级角标 | DOM 属性劫持 |

### 2.6 `logger.ts` — 日志工具

**文件**: `D:\Code\sona\src\lib\logger.ts`

一个轻量级日志工具，支持彩色输出和级别控制。

```typescript
export const log = {
  info: (message: string, ...args: any[]) => {
    console.log(`%c[Sona] %c${message}`, 'color: #00bcd4', 'color: #fff', ...args)
  },
  warn: (message: string, ...args: any[]) => { /* 黄色 */ },
  error: (message: string, ...args: any[]) => { /* 红色 */ },
  debug: (message: string, ...args: any[]) => {
    if (store.get('debug')) {
      console.log(`%c[Sona Debug] %c${message}`, 'color: #888', 'color: #aaa', ...args)
    }
  },
}

// 启动 Banner
export function showBanner(): void {
  console.log('%c Sona %c v1.6.0 ',
    'background: #00bcd4; color: #000; font-size: 16px; font-weight: bold; padding: 4px 8px;',
    'background: #333; color: #fff; font-size: 12px; padding: 4px 8px;'
  )
}
```

---

## 3. 功能模块实现模式

通过分析 ~25 个功能模块，归纳出 5 种主要实现模式：

### 3.1 模式 A：纯 LCU API 调用（无 UI 注入）

**适用场景**: 自动化操作、状态修改

**代表模块**: `auto-accept`, `auto-ban`, `auto-lock`, `auto-honor`, `auto-return-to-lobby`, `rank-disguise`

**实现模板**:

```typescript
// auto-accept.ts

let enabled = false
let userDeclinedThisSession = false

// Store 配置变更入口
export function updateAutoAccept(config: AutoAcceptConfig): void {
  enabled = config.enabled
}

// GameflowPhase 事件
export function onGameflowPhase(phase: GameflowPhase): void {
  if (!enabled) return

  if (phase === 'ReadyCheck') {
    handleReadyCheck()
  } else if (phase === 'Lobby') {
    // 回到大厅 → 重置拒绝标记
    userDeclinedThisSession = false
  }
}

// ChampSelectSession 事件
export function onChampSelectSession(session: ChampSelectSession): void {
  if (!enabled) return
  // 处理选人阶段逻辑
}

async function handleReadyCheck(): Promise<void> {
  // 延迟策略
  const delay = store.get('auto-accept').delay || 1000
  await sleep(delay)

  try {
    await lcu.acceptReadyCheck()
    log.info('已接受对局')
  } catch (error) {
    log.error('接受对局失败:', error)
  }
}
```

**拒绝保护机制** (auto-accept):

```typescript
// 玩家手动接受后，标记为"本局已手动"
let userAccepted = false

export function onChampSelectSession(session: ChampSelectSession): void {
  if (session && !userAccepted) {
    userDeclinedThisSession = true
    log.info('检测到玩家手动操作，本会话暂停自动接受')

    // 需要等回到大厅才重置
  }
}

export function onGameflowPhase(phase: GameflowPhase): void {
  if (phase === 'Lobby') {
    userDeclinedThisSession = false
  }
}
```

**状态管理**:
- 使用模块级全局变量，不依赖 React 状态
- 每个功能维护自己的状态机（`enabled`, `userDeclinedThisSession`, `lastAction` 等）
- 无类封装——直接导出函数

### 3.2 模式 B：DOM 注入 + LCU API 调用

**适用场景**: 需要修改客户端 UI 同时调用 LCU API

**代表模块**: `balance-buff-viewer`, `champselect-tier-badge`, `custom-banner`, `profile-background`, `lobby-member-match-history`

**实现模板**:

```typescript
// custom-banner.ts

let enabled = false
let currentReactRoot: ReactRoot | null = null

export function updateCustomBanner(config: CustomBannerConfig): void {
  enabled = config.enabled

  if (enabled) {
    injectBannerButton()    // 注入入口按钮
  } else {
    removeBannerButton()
  }
}

// 注入入口按钮（通过 InjectorManager）
function injectBannerButton(): void {
  window.injectorManager.registerTask('custom-banner-button', {
    selector: '.profile-header',
    inject: (target) => {
      const btn = document.createElement('button')
      btn.className = 'sona-custom-banner-btn'
      btn.textContent = '自定义旗帜'
      btn.onclick = () => openBannerPicker()
      target.appendChild(btn)
    },
    onRemove: (target) => {
      // 清理 React root
      destroyReactRoot()
    }
  })
}

// 打开选择弹窗（React root）
function openBannerPicker(): void {
  const container = document.createElement('div')
  container.id = 'sona-banner-picker'
  document.body.appendChild(container)

  currentReactRoot = createRoot(container)
  currentReactRoot.render(
    <CustomBannerPicker
      onClose={() => destroyReactRoot()}
      onSelect={(bannerId) => applyBanner(bannerId)}
    />
  )
}

function destroyReactRoot(): void {
  if (currentReactRoot) {
    currentReactRoot.unmount()
    currentReactRoot = null
    const container = document.getElementById('sona-banner-picker')
    if (container) container.remove()
  }
}

// 调用 LCU API 应用配置
async function applyBanner(bannerId: string): Promise<void> {
  try {
    await lcu.put(`/lol-summoner/v1/current-summoner/custom-banner`, { bannerId })
    log.info('旗帜已更新')
  } catch (error) {
    log.error('更新旗帜失败:', error)
  }
}
```

### 3.3 模式 C：纯 DOM 操作（无 LCU API）

**适用场景**: UI 样式修改、DOM 劫持、事件拦截

**代表模块**: `bench-no-cooldown`, `champselect-quit-button`, `hide-esports-popup`, `unlock-status`, `global-particle`

**实现模板**:

```typescript
// bench-no-cooldown.ts

export function updateBenchNoCooldown(enabled: boolean): void {
  if (enabled) {
    // 直接修改 DOM 元素属性
    patchBenchElements()
    // 注册 MutationObserver 任务，确保新出现的 DOM 也被修改
    window.injectorManager.registerTask('bench-no-cooldown', {
      selector: '.bench-champion',
      inject: (target) => {
        // 劫持点击事件
        target.onclick = async (e) => {
          e.stopPropagation()
          // 直接调用 LCU 接口
          await lcu.champSelectBenchSwap(championId)
        }
      }
    })
  } else {
    window.injectorManager.unregisterTask('bench-no-cooldown')
    // 恢复原始行为
    restoreBenchElements()
  }
}
```

### 3.4 模式 D：Ember 组件劫持

**适用场景**: 修改客户端 React (Ember) 组件属性

**代表模块**: `chroma-unlock`

**实现模板**:

```typescript
// chroma-unlock.ts

export function initChromaUnlock(): void {
  // Ember 组件在 window 上暴露类
  // 通过修改类的 prototype 或 override 方法实现
  const ChromaComponent = (window as any).Ember?.TEMPLATES?.['components/...']

  if (ChromaComponent) {
    const originalRender = ChromaComponent.prototype.render
    ChromaComponent.prototype.render = function() {
      // 修改组件属性，取消锁
      this.set('isLocked', false)
      this.set('showAllChromas', true)
      return originalRender.apply(this, arguments)
    }
  }
}
```

**注意**: 这是一个脆弱的模式，强耦合于客户端内部的 Ember 实现，客户端版本更新可能随时失效。

### 3.5 模式 E：XHR 拦截

**适用场景**: 修改客户端请求/响应数据

**代表模块**: `global-particle`（修改壁纸数据）

**实现模板**:

```typescript
// 拦截 fetch 请求修改响应
const originalFetch = window.fetch
window.fetch = async function(url: string, init?: RequestInit) {
  const response = await originalFetch(url, init)

  // 拦截特定 API
  if (url.includes('/lol-game-data/assets/v1/')) {
    const cloned = response.clone()
    const data = await cloned.json()

    // 修改数据
    data.particles = customParticles

    return new Response(JSON.stringify(data), {
      status: response.status,
      headers: response.headers
    })
  }

  return response
}
```

---

## 4. 关键技术点详解

### 4.1 DOM 属性劫持 (Attribute Hooking)

Sona 中一个重要的技术手段是通过 `Object.defineProperty` 劫持客户端 DOM 元素的属性，实现"被动响应"。

```typescript
// 劫持 DOM 属性
function hookDomProperty(element: Element, property: string, handler: (value: any) => void): void {
  let _value = (element as any)[property]

  Object.defineProperty(element, property, {
    get() { return _value },
    set(value) {
      _value = value
      handler(value)
    }
  })
}
```

**典型用途**:
- 监听客户端组件 `props` / `state` 变化
- 在客户端更新数据后自动触发 Sona UI 刷新
- 劫持 `background-image` 等样式属性，替换为自定义内容

### 4.2 React Root 动态注入

Sona 使用 React 客户端但不直接与客户端共享 React 实例——每个需要 UI 的功能创建独立的 React root。

```typescript
import { createRoot, type Root } from 'react-dom/client'

// 管理动态根
const roots = new Map<string, Root>()

function mountReactComponent(id: string, element: React.ReactElement): void {
  // 创建容器
  const container = document.createElement('div')
  container.id = `sona-${id}`
  document.body.appendChild(container)

  // 创建 root 并渲染
  const root = createRoot(container)
  root.render(element)
  roots.set(id, root)
}

function unmountReactComponent(id: string): void {
  const root = roots.get(id)
  if (root) {
    root.unmount()
    document.getElementById(`sona-${id}`)?.remove()
    roots.delete(id)
  }
}
```

**关键考虑**:
- 每个功能独立 root，互不影响
- 卸载时完全清理 DOM 和 React 实例
- 容器元素添加 `sona-` 前缀避免与客户端冲突

### 4.3 MutationObserver 自愈机制

```typescript
// InjectorManager 的核心自愈循环
class InjectorManager {
  private processTasks(): void {
    for (const taskId of this.pendingTasks) {
      const task = this.tasks.get(taskId)
      if (!task) continue

      const targets = document.querySelectorAll(task.selector)
      for (const target of targets) {
        if (!this.isInjected(target)) {
          task.inject(target as HTMLElement)
          this.markInjected(target)
        }
      }
    }
    this.pendingTasks.clear()
    this.rafScheduled = false
  }
}
```

**为什么需要自愈**: LCU 基于 React (Ember) 构建，页面切换（路由变化）会导致 DOM 完全重建。MutationObserver 检测到新 DOM 后重新注入，确保功能持续有效。

### 4.4 延迟策略

```typescript
// utils.ts
export function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms))
}

// auto-accept 中使用随机延迟模拟人类行为
const delay = config.delay + Math.floor(Math.random() * 200)
await sleep(delay)
```

**典型延迟用途**:
- 自动接受：随机延迟 500-1500ms，避免秒开被检测
- 自动禁英雄：需要等待客户端加载完数据后再操作
- 自动点赞：对局结束后等几秒，等待荣誉系统就绪

### 4.5 捕获阶段事件拦截 (capture phase)

```typescript
// quick-lobby-mode.ts
// 使用捕获阶段（第三个参数为 true）拦截事件
element.addEventListener('click', (e) => {
  e.stopPropagation()
  // 自定义处理
}, true) // ← capture phase
```

**为什么用捕获阶段**: 客户端自己的事件监听在冒泡阶段处理，在捕获阶段拦截可以在客户端之前拿到事件，阻止默认行为。

### 4.6 OP.GG / SGP 数据集成

Sona 通过外部队站 API 获取数据增强游戏体验：

```typescript
// OP.GG API
export async function fetchOpggData(summonerName: string, region: string): Promise<OpggData> {
  const url = `https://www.op.gg/summoners/${region}/${encodeURIComponent(summonerName)}`
  // 通过 CORS 代理或直接请求
}

// SGP API (腾讯国服)
export async function fetchSgpStatus(): Promise<void> {
  // 腾讯 SGP 协议，跨区查询
}
```

**特点**: Sona 利用了腾讯互通大区的 JWT 特性，可以同时查询所有区服的战绩数据——这是 Seraphine 当前不具备的能力。

---

## 5. 与 Seraphine 的对比与可复用模式

### 5.1 架构决策对比

| 维度 | Sona（前端插件） | Seraphine（桌面应用） | 建议方向 |
|------|-----------------|---------------------|---------|
| DOM 操作 | 核心能力，但脆 | 不支持 | 对固定能力参考代码逻辑 |
| UI 框架 | React 组件 | PyQt5 Widgets | 仅在"查阵容窗口"等独立 UI 场景参考 | 
| 状态管理 | 模块级全局变量 | SignalBus + QConfig | **可复用模式**：SignalBus 信号解耦 |
| 事件驱动 | Pengu WebSocket | @retry + asyncio | **可复用模式**：重试/并发控制设计 |
| 数据缓存 | 无缓存 | @lru_cache + 版本化文件 | Seraphine 更优 |
| LCU 版本容错 | 弱（DOM/Ember hook 脆） | 强（纯 API 调用） | 优先纯 API 方案 |
| 测试 | 无 | 213 pytest | 维持并扩展 |

### 5.2 可直接复用的架构模式

#### 5.2.1 Feature 注册调度模式

Seraphine 当前的功能注册分散在 `MainWindow.__connetSignalToSlot` 和各种 `if-elif` 中。可以参考 Sona 的 `features.ts` 模式：

```
// 当前 Seraphine 模式（长函数 + if-elif）
def __onGameStatusChanged(self, status):
    if status == 'Lobby':
        self.__updateCareer()
    elif status == 'ReadyCheck':
        if self.cfg.get(cfg.autoAccept):
            self.accept_ready_check()
    elif status == 'ChampSelect':
        if self.cfg.get(cfg.autoBan):
            self.start_auto_ban()
        if self.cfg.get(cfg.autoPick):
            self.start_auto_pick()

// 改进方向（注册式）
features: dict[str, Feature] = {
    'auto-accept': AutoAcceptFeature(),
    'auto-ban': AutoBanFeature(),
    'auto-pick': AutoPickFeature(),
}

def on_gameflow_phase(phase):
    for feature in features.values():
        if feature.enabled:
            feature.on_gameflow_phase(phase)
```

**优点**: 每个功能独立文件、独立状态、可单独测试，新增功能只需添加新文件并注册。

#### 5.2.2 统一的 LCU 事件分发

Sona 通过 `observe()` 返回取消函数的方式管理事件订阅，Seraphine 可以通过类似模式统一管理 WebSocket 事件监听：

```python
# 参考 Sona 的 observe pattern
class LcuEventBus:
    _listeners: dict[str, list[Callable]] = defaultdict(list)

    @classmethod
    def on(cls, event_uri: str, callback: Callable) -> Callable:
        cls._listeners[event_uri].append(callback)
        return lambda: cls._listeners[event_uri].remove(callback)

    @classmethod
    async def dispatch(cls, event_uri: str, data: Any):
        for cb in cls._listeners.get(event_uri, []):
            try:
                await cb(data)
            except Exception:
                logger.exception(f"Event handler failed for {event_uri}")
```

#### 5.2.3 DOM 注入模式（移植到 Qt）

虽然 Seraphine 无法直接操作 LCU DOM，但某些能力可以通过其他方式模拟：

| Sona DOM 能力 | Seraphine 等效方案 |
|---------------|-------------------|
| 在选人界面显示胜率 | 通过 LCU API 获取数据 + 外部 Overlay 窗口 |
| 替换壁纸 | 调用 LCU API 修改资源 |
| 劫持按钮事件 | 通过 LCU API 模拟操作 |
| 选人粒子特效 | 无法直接实现（客户端浏览器外部） |

### 5.3 Sona 的算法参考价值

以下 Sona 功能模块的**业务逻辑**可以按需参考：

| 功能 | 可参考逻辑 |
|------|-----------|
| `auto-ban-champion.ts` | 英雄 ID 冲突检测、首选/备选/禁用列表管理 |
| `auto-lock-champion.ts` | 回合管理、Chef 角色/队长分配、状态机 |
| `auto-honor.ts` | 点赞投票策略（单人/全体/随机/跳过自己） |
| `auto-return-to-lobby.ts` | Play Again 后自动搜索、有限重试、状态追踪 |
| `enhanced-friend-game-status.ts` | 好友状态解析模式、游戏时长计算 |
| `friend-smart-group.ts` | 同对局识别逻辑（队列 ID 匹配） |

### 5.4 Sona 的不足与 Seraphine 可避免的问题

1. **DOM 选择器脆弱性**: 客户端 UI 更新会导致选择器失效
2. **Ember hook 不可持续**: 客户端从 Ember 迁移到 React 时这类功能全部失效
3. **无测试覆盖**: 建议 Seraphine 对所有自动化逻辑编写测试
4. **无错误恢复**: LCU API 调用无重试，依赖浏览器默认行为
5. **模块间耦合**: 全局变量模式不利于测试和调试
6. **react-root 管理碎片化**: 每个功能各自管理自己的 root，缺乏统一管理

---

## 6. 附录：功能模块清单

| 文件名 | 功能 | 模式 | 关键依赖 |
|--------|------|------|---------|
| `auto-accept.ts` | 自动接受对局 | A (纯 API) | LCU ReadyCheck API |
| `auto-ban-champion.ts` | 自动禁用英雄 | A (纯 API) | ChampSelect Session API |
| `auto-lock-champion.ts` | 自动锁定英雄 | A (纯 API) | ChampSelect Action API |
| `auto-honor.ts` | 自动点赞 | A (纯 API) | Honor API |
| `auto-return-to-lobby.ts` | 自动返回房间 | A (纯 API) | Play Again API |
| `bench-no-cooldown.ts` | 大乱斗无 CD 换英雄 | C (纯 DOM) | DOM 劫持 + API |
| `champselect-quit-button.ts` | 选人退出按钮 | C (纯 DOM) | DOM 注入 |
| `balance-buff-viewer.ts` | 平衡性 Buff 显示 | B (DOM + API) | 数据获取 + Tooltip 注入 |
| `champselect-tier-badge.ts` | T 级角标 | B (DOM + API) | OPGG 数据 + DOM 角标 |
| `chroma-unlock.ts` | 炫彩解锁 | D (Ember hook) | Ember 组件劫持 |
| `custom-banner.ts` | 自定义旗帜 | B (DOM + API) | React root + DOM 劫持 |
| `debug-gameflow.ts` | Gameflow 调试日志 | A (纯 API) | 日志输出 |
| `enhanced-friend-game-status.ts` | 好友状态增强 | B (DOM + API) | LCU Chat API |
| `friend-smart-group.ts` | 好友智能分组 | B (DOM + API) | 颜色标记 + 分组逻辑 |
| `game-analysis-popup.ts` | 对局分析弹窗 | B (DOM + API) | React root + API 数据 |
| `game-mode-filter.ts` | 游戏模式过滤 | C (纯 DOM) | DOM 注入 + 动画 |
| `global-particle.ts` | 全局粒子特效 | C (纯 DOM) | Canvas + requestAnimationFrame |
| `hide-esports-popup.ts` | 关闭赛事弹窗 | C (纯 DOM) | MutationObserver 守护 |
| `lobby-member-match-history.ts` | 房间队友战绩 | B (DOM + API) | React 弹窗 + SGP 数据 |
| `opgg-build-recommendation.ts` | OPGG 配装推荐 | B (DOM + API) | OPGG 数据 + 物品组创建 |
| `profile-background.ts` | 生涯背景自定义 | B (DOM + API) | React root + LCU API |
| `quick-lobby-mode.ts` | 快速大厅模式 | C (纯 DOM) | 捕获阶段事件拦截 |
| `rank-disguise.ts` | 段位伪装 | A (纯 API) | PUT /lol-chat/v1/me |
| `ready-check-control.ts` | 接受后再拒绝 | C (纯 DOM) | DOM 按钮状态劫持 |
| `unlock-status.ts` | 解锁自定义签名 | C (纯 DOM) | DOM class 操作 |

---

## 总结

Sona 的核心优势在于**运行在客户端内部**带来的 DOM 操作能力，使客户端美化和 UI 增强成为可能。Seraphine 作为外部桌面应用，不具备这个能力，但正因如此：

1. **更稳定** — 不依赖客户端 DOM 结构/Ember 版本
2. **可测试** — 纯 API 调用 + 业务逻辑可以编写单元测试
3. **更专业** — 完整的增量更新、缓存、错误恢复机制
4. **用户体验更好** — 独立窗口，不会被客户端刷新影响

建议 Seraphine 重点参考 Sona 的：
- **Feature 注册调度模式**（但用 Python 类实现）
- **自动化逻辑的实现细节**（延迟策略、状态机、冲突检测）
- **OPGG/SGP 数据处理逻辑**（战绩解析、排名计算）
- **LCU API 封装的组织方式**（按功能域分组）

避免参考：
- **DOM 操作相关**（客户端版本脆弱性）
- **Ember hook 技术**（不可持续）
- **无重试/无错误处理**（桌面应用需要健壮性）
