# LOL 战后复盘（Post Game Review）UI Design Specification v1.0

## 设计目标

-   参考 Riot Games 官方赛事（LPL / Worlds）数据分析面板。
-   风格：深色、科技感、HUD、电竞转播。
-   页面尺寸：1920×1080 固定 Dashboard。

## 页面布局

-   Header（80px）
-   三栏布局：左队伍（32%）｜中央对比（36%）｜右队伍（32%）
-   底部：经济曲线、资源控制、英雄雷达、事件时间线

```{=html}
<!-- -->
```
    ┌──────────────────────────────────────────────────────────┐
    │ Header                                                   │
    ├───────────────┬──────────────────┬───────────────────────┤
    │ Blue Team     │ Compare Area     │ Red Team              │
    ├───────────────┴──────────────────┴───────────────────────┤
    │ Economy │ Resource │ Hero Radar │ Timeline               │
    └──────────────────────────────────────────────────────────┘

## Design Tokens

### Colors

  Token            Value
  ---------------- ---------
  Background       #07111D
  Panel            #101D2C
  Secondary        #162739
  Blue             #2EA7FF
  Red              #E6525B
  Gold             #F5C35B
  Text Primary     #FFFFFF
  Text Secondary   #D3DAE4

### Typography

-   Title: 36px Bold
-   Panel Title: 22px Semibold
-   Body: 15px
-   Caption: 13px
-   Numbers: DIN Condensed Bold

## Header

左：战后复盘

中：比分 + 时长 + 地图

右：Tab - 总览 - 数据 - 经济 - 符文 - 装备 - 时间线

## Team Panel

每侧包含 5 个 PlayerCard。

PlayerCard 包含：

-   英雄头像（64×64）
-   等级
-   玩家 ID
-   KDA
-   召唤师技能
-   符文
-   输出占比
-   经济占比
-   参团率
-   视野得分
-   六边形评分

高度：108px

间距：12px

## Score Hexagon

-   SVG 正六边形
-   尺寸：76px
-   中央显示评分
-   评分颜色：
    -   9+ Gold
    -   8+ Blue
    -   7+ Cyan
    -   6+ Grey
    -   \<6 Red
-   MVP：金蓝发光
-   SVP：紫色

## Center Compare

### Team Radar

六维：

-   输出
-   承伤
-   经济
-   控制
-   视野
-   资源

### Resource Control

-   塔
-   小龙
-   峡谷先锋
-   男爵
-   远古龙

## Bottom

1.  Economy Chart
2.  Resource Control
3.  Hero Radar Compare
4.  Event Timeline

## Panel Style

-   Radius: 8px
-   Border: rgba(255,255,255,.08)
-   Background: Linear Gradient (#152334 → #0F1928)
-   Shadow: 0 0 20 rgba(0,0,0,.45)

## Component Tree

``` text
PostGameReviewPage
├── Header
├── LeftTeamPanel
│   └── PlayerCard ×5
├── ComparePanel
│   ├── MatchScore
│   ├── TeamRadarChart
│   ├── ResourceControl
│   └── MatchStatistics
├── RightTeamPanel
│   └── PlayerCard ×5
├── BottomSection
│   ├── EconomyChart
│   ├── HeroRadarCompare
│   ├── ResourceTimeline
│   └── EventTimeline
└── FooterAction
```

## Code Agent Requirements

-   React + TypeScript
-   Tailwind CSS
-   Apache ECharts
-   SVG 绘制六边形评分
-   不使用切图
-   全组件化
-   高度还原 Riot 官方赛事数据分析 HUD 风格
