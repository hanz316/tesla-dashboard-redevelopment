# Horizon V2 — UI SPEC

状态：**第一版已实现并出图，等待人工视觉验收。**

> **v2.1 构图修订（人工评审后）**：车辆放大、路面加强、氛围光斑削弱、
> 限速牌并入速度簇、SOC 与档位同一水平带。见 §10。

```text
HORIZON_V2_VISUAL = AWAITING HUMAN VISUAL APPROVAL
```

本轮只做 Horizon。Mono / Pulse / Route / Studio / Energy / Nocturne 保持现状；
UART、指挥官协议、Model A 几何、尾灯几何、仲裁策略一律未改。

---

## 1. 为什么是"设计即数据"

实现方没有视觉能力，不能靠"看起来不错"验收。所以这套 UI 的所有决定都写在
两个机器可读文件里，代码从它们生成，测试再读回来核对。

| 文件 | 内容 |
|---|---|
| [`assets/ui/horizon_v2_layout.json`](../assets/ui/horizon_v2_layout.json) | 画布、面板遮罩、安全区、三大区域、每个组件的 bounds/z-order/token 引用/可见性规则/数据绑定/未知态行为 |
| [`assets/ui/design_tokens.json`](../assets/ui/design_tokens.json) | 颜色、字体层级、间距、圆角、透明度、动画时长、Model A 实测包围盒 |

生成的场景：[`scenes/horizon_v2.scene`](../scenes/horizon_v2.scene)
（32 个节点 = 21 文本 + 10 矢量 + 1 车辆）。

流程是单向的：

```text
layout.json + design_tokens.json
        |  tools/preview/build_horizon_v2.py   (越界/踩遮罩/超安全区直接拒绝生成)
        v
scenes/horizon_v2.scene
        |  tools/preview/scene_preview.py      (Mac 预览 + 截图, 与设备同一份规则)
        v
assets/checkpoints/horizon_v2/*.png
        |  tools/preview/horizon_v2_layout_qa.py + tests/horizon_v2_tests.py
        v
布局/重叠/未知态/调试文本/状态落点 全部自动判定
```

**禁止**文档一套坐标、代码另一套坐标：测试会重新生成场景并逐字节比对。

---

## 2. 画布与物理约束

| 项 | 值 |
|---|---|
| 逻辑画布 | 1920 × 480，坐标 x 0..1919 / y 0..479 |
| 安全区 | 左右 48、上 22、下 24 |
| 面板梯形遮罩 | 上角切 116 px、下角切 51 px（实机标定），`cut(y) = 116 - 65*y/480` |
| 三大区域 | 驾驶员 x 60..430；车辆 x 430..1490；能量 x 1490..1860（只是布局约束，不画框） |

面板遮罩是硬约束：`x >= cut(y)`、`x + w <= 1920 - cut(y)`。
生成器和 QA 都按组件上下边分别计算，因此"看着居中、上机被切"不会发生。

### 2.1 与提示词的偏差（两处，均可复核）

| id | 提示词 | 实际 | 原因 |
|---|---|---|---|
| `speed_x` | 速度 x = 90 | **120** | 遮罩在速度框上沿（y = 105）已到 x ≈ 101.8，x = 90 会让首位数字被切；120 留 18 px 余量 |
| `time_anchor` | 时间 x = 1640 | **右对齐至 1806** | 读作"能量列里的时钟"：与 range/SOC 同一右边界，而不是浮在屏幕中段 |

其余坐标（温度 500/35、导航 pill 中心 960/y18/w620/h62、车辆视觉中心
960/295、range y115、SOC bar 180×12）与提示词一致。

导航 pill 的 y=18 在安全区上边（22）之上 4 px —— 提示词自己如此规定，
已在 layout 里标为 `exempt_from_safe_area`（其内容从 y=48 开始，在安全区内）。

---

## 3. 组件与层级

### 3.1 顶部

| 组件 | 位置 | 绑定 | 未知态 |
|---|---|---|---|
| 温度 | 左 500，垂直中心 74 | `temperature_primary` | `—°C` |
| 时钟 | 右对齐 1806 | 系统时钟 `%H:%M` | 不适用 |
| 导航 pill | 中心 960 / y18 / 620×62 / r10 | `nav_manoeuvre` 有效才出现 | **整块隐藏**（不画空矩形） |
| pill 内容 | 图标 + 距离 + 指路文字 | `nav_icon` / `nav_distance` / `nav_instruction` | 跟随 pill |

### 3.2 驾驶区（左）

| 组件 | 位置 | 字号 | 绑定 | 未知态 |
|---|---|---|---|---|
| 速度 | x120，垂直中心 175 | DISPLAY 120 | `speed` | `—` |
| 单位 | x124，垂直中心 263 | CAPTION 22 | 静态 `km/h` | 不适用 |
| 限速牌 | 386..440 / y118..172 | CAPTION 22 | `speed_limit` | **完全隐藏**（不虚构限速） |
| 档位 | x120/164/208/252，垂直中心 309 | BODY 28 | `gear` | 四个字母隐藏，只画 `—` |
| 驾驶员状态 | x120，垂直中心 359 | CAPTION 22 | `driver_status_text` | 空 |

档位：非当前档 0.28 透明度，当前档 `active_gear` 高亮；未知时整行隐藏只留 `—`，
**绝不允许 UNKNOWN → P**。速度单位放在数字下方而不是右侧，否则三位数会顶到单位。

### 3.3 车辆区（中）

| 项 | 值 |
|---|---|
| 渲染框 | x666 y85 584×387（asset 的 356×236 等比放大 1.64） |
| 可见车辆（关闭态） | x750..1170，y178..411（宽 420，中心 960/295） |
| 全部打开时的并集 | x748..1169，y119..412 |
| 允许区域 | x560..1360，y100..456 |

车辆状态全部来自 `VehicleState → VehicleVisualController → asset layers`：
刹车灯、近光灯、示宽灯按 asset overlay；四个车门 / 前备箱 / 后备箱按 to_state
序列；左/右转向与双闪按循环序列（**双闪 = 左右同时**，没有第四盏灯；后备箱内灯
按 `vehicle_state_moving_lighting.json` 的 TRUNK_MOVING 变体随盖板走）。
Horizon 自己不解释 UART / 指挥官数据。

道路：静态层，一条地平线 + 一个梯形路面 + 两条车道线 + 一层很淡的冷色渐变。
无粒子、无实时模糊、无 WebGL、无 3D 路面网格。

转向反馈：车辆对应灯亮；左右两侧各有一个 `◀` / `▶` 次级提示（CAPTION 22，
`indicator` 绿），只在对应侧亮时出现，不做大箭头。

#### 3.3.1 移动面板的合成模型（V2 第一版后修）

**问题**：每个状态渲染都是"整车重新渲染"——开门帧是整台车带着一扇开着的门。
把两张这样的图叠起来，后画的那张会用它的"关闭姿态"把前一张已开的门重新盖上。
实机可见表现就是"双盖板 / 一个个开着的门旁边还有关闭的车身"。

**根因（像素级证据，非推断）**：

```text
每个状态帧 vs 关闭 base ：erased 像素 = 0（帧从不擦掉 base 的像素）
                          差异集中在 1.5k–4.6k 像素（该部件所在区域）
door_fr 与 door_rr 两层重叠 1000 像素，其中 855 像素相差最多 185 级
  → 开一扇门会改变相邻门上的阴影，两张渲染在对方区域都"有改动"
```

**采用的模型（选项 B 的确定性版本，无需重渲资产、无运行时遮罩）**：

```text
base（关闭姿态整车）
  + Σ 当前活动状态各自的 delta 层
delta = 该状态新增的像素（帧不透明、base 透明）
      ∪ 该状态改变了的像素（两者都实心、颜色差 > 8 级）
```

烘焙：`tools/assets/bake_vehicle_deltas.py` → `assets/rendered/vehicle/delta/`
（173 层，15 组；派生+可重生成，与渲染资产一样不进 git）。烘焙前断言：
`erased == 0`、`base ⊕ layer == 原帧`（实心区零差异）、层覆盖面积 < 25%。

绘制顺序（写进 layout 的 `parts` 顺序，即契约）：前门 → 后门 → 前备箱 → 后备箱；
灯光层永远最后画。同侧两扇门同时打开时它们的投影在 2D 里必然重叠
（FL/RL 366 像素、FR/RR 1000 像素），按上述顺序由后画者覆盖：这是 2D 投影的
固有限制，已在 QA 中量化为"重叠占比 < 30%"，不做 3D 求解。

**效果**：单个部件打开时等于它自己的渲染（实心区 0 像素差异）；关闭状态与
修复前的参考图在车身内部**逐像素相同**；每个部件"伸出去"的几何全部保留
（曾经尝试过按改动幅度仲裁层归属，结果把 FL 门切掉 159 像素、RL 切掉 427 像素，
已回退——不能为了修阴影而删真几何）。

**三个资产发现（记录，不擅自修图）**：

1. 每张 PNG 在**全透明像素里仍带颜色数据**（约 5081 像素）。旧路径贴整帧时
   LANCZOS 会把这些颜色渗到车身边缘形成极淡光晕；delta 层透明区是纯零，
   没有这个渗色。这是本修复带来的边缘差异（车身内部 0 差异）。
2. `base/000.png` 与所有状态渲染在尾灯条（资产坐标 x53..137 y128..165）
   相差最多 148 级、约 190 像素——base 那个位置的灯带比状态渲染更亮。
   两者谁才是"关灯静止"的正确外观需要人判断（当前 neutral 用 base）。
3. 后备箱指示灯变体（`trunk/ind_*`）与普通开盖在同一帧上只差约 28 像素，
   而且**方向是变暗**（mean dRGB −29/−9/−2）。这既可能是该角度下内侧灯本身
   很微弱，也可能是渲染时的灯光约定差异——**未定，不据此下结论**。灯光归属
   因此由渲染器契约（后备箱携带转向灯时跳过固定位置灯层）加输出级检查保证：
   开盖状态下点亮左转向只改变 52 像素，且全部落在盖板自身区域内。

### 3.4 能量区（右）

| 组件 | 位置 | 字号 | 绑定 | 未知态 |
|---|---|---|---|---|
| 续航 | 右对齐 1806，垂直中心 175 | TITLE 62 | `range` | `— km` |
| RANGE 标签 | 右对齐 1806，垂直中心 230 | CAPTION 22，0.55 透明 | 静态 | 不适用 |
| SOC 条 | 1626..1806，y268..280 | 高 12 / r6 | `actual_soc` | **整条隐藏** |
| SOC 百分比 | 右对齐 1806，垂直中心 312 | BODY 28 | `actual_soc` | `— %` |
| 功耗 | 右对齐 1806，垂直中心 368 | CAPTION 22 | `battery_power` | `— kW` |

SOC 颜色：正常低饱和青 `soc_normal`，≤20 % 转 `soc_low`（琥珀），≤10 % 转
`soc_critical`（红）。规则写在 layout 的 `progress.color_when`，预览器与设备
后端读同一份。

SOC 来源：**指挥官 `actual_soc`**（当前仲裁策略）。指挥官无数据时保持未知，
不启用已被否决的 MCU SOC 字节。

### 3.5 警告

居中偏下（660..1260，垂直中心 435），CAPTION 22，琥珀色，只在 `warning_text`
有效时出现；无警告时不画。

---

## 4. 生产 Horizon 禁止出现

`layout.forbidden_in_production` 列出并逐项自动检查：`CMDR` / `NativeBle` /
`PhoneBridge` / `UART` / `FPS` / `RSS` / `frame time` / `packet` / `checksum` /
`protocol` / `mapping confidence` / `source:` / `quality` / `stale` / `valid` /
`priority` / `debug` / `DEV`。

这些属于 Developer 页（独立 overlay，默认 OFF）。当前 Horizon（v6）上的
`commander.state` / `commander.detail` / `uart.lost` 在 V2 里**全部移除**。

---

## 5. 未知态硬规则

```text
UNKNOWN != 0        UNKNOWN != OFF      UNKNOWN != CLOSED
range -> — km       SOC -> — %          gear -> 四个字母隐藏 + —
temperature -> —°C  speed -> —          speed limit -> 整块隐藏
battery_power -> — kW                   nav -> 整块隐藏
```

自动检查两遍：布局层（每个绑定节点在 unknown 状态必须落到 `invalid_text`，
且占位符里不含数字），像素层（unknown 截图与 neutral 截图必须在三列都不同，
证明是"画了占位符"而不是"整屏空白"）。

---

## 6. 性能约束

保持 asset-driven，不做运行时重效果：

| 层 | 每帧工作 |
|---|---|
| 静态 | 1 个全屏渐变 + 1 个径向氛围 + 1 个路面多边形 + 3 条线 + 导航 pill 底板 |
| 动态矢量 | SOC 条填充 1 个 |
| 动态位图 | 车辆（唯一每帧位图，门/盖序列由状态触发） |
| 动态文本 | 速度、档位、续航、SOC、功耗、温度、时钟、状态、警告、导航 |

每帧位图仅车辆一张；动画序列同一时刻不超过 1-2 个（符合
`docs/RENDERING_CAPABILITY_AUDIT.md` §11 的推导）。目标 T113 稳定 30 fps；
真机帧时 / RSS 仍属 **UNKNOWN UNTIL DEVICE TEST**，本轮未做 60 fps 优化。

---

## 7. 自动化验收（无视觉能力下的"眼睛"）

`tools/preview/horizon_v2_layout_qa.py` 与 `tests/horizon_v2_tests.py` 执行：

1. 组件不越出画布
2. 组件不越出安全区（除非 layout 显式豁免并写明理由）
3. 组件不踩面板梯形遮罩
4. 速度不与车辆（含全开态）重叠
5. 车辆不与续航 / SOC 条重叠，且不侵入左右两列
6. 导航 pill 不压温度 / 时钟
7. 文本墨迹框两两不相交（neutral / unknown / low SOC / navigation 四态各测一次）
8. Model A 完整可见（关闭态与全开并集都在允许区域内），并用 PNG 实测 alpha
   包围盒核对 golden 数字，防止资产漂移
9. 生产 Horizon 无调试文本
10. unknown 截图无假数据（文本层 + 像素层各一遍）

外加：场景可从 layout 重新生成且逐字节一致；12 张截图各 1920×480；
两次渲染逐字节相同（确定性）；每个车辆状态只改变车辆区域（区域外变化像素
必须为 0）。

---

## 8. 产物

| 文件 | 说明 |
|---|---|
| `assets/checkpoints/horizon_v2/horizon_v2_neutral.png` 等 12 张 | 1920×480 确定性截图 |
| `assets/checkpoints/horizon_v2/horizon_v2_contact_sheet.png` | 12 态总览（人工验收用） |
| `assets/ui/horizon_v2_layout.json` | 布局 golden source |
| `assets/ui/design_tokens.json` | token golden source |
| `scenes/horizon_v2.scene` | 生成产物（runtime 读的就是它） |

复现：

```bash
python3 tools/preview/build_horizon_v2.py
python3 tools/preview/horizon_v2_shots.py
python3 tools/preview/horizon_v2_layout_qa.py
python3 tests/horizon_v2_tests.py
```

---

## 9. 下一步

**停下等人工看图。** 验收通过后（用户明确说 OK / 通过 / 可以），才：

1. 把 V2 提升为生产 Horizon（让运行时指向 `horizon_v2.scene`），并把 `status`
   改为 `LOCKED`；
2. 把静态层烘焙进背景位图（设备 `IRenderBackendV6` 适配器），届时每帧只剩
   文本 + SOC 条填充 + 一张车辆位图；
3. 真机帧时 / RSS / 面板 gamma 实测。

```text
HORIZON_V2_VISUAL = AWAITING HUMAN VISUAL APPROVAL
```

---

## 10. v2.1 构图修订（本轮的数值）

人工评审结论：移动面板合成缺陷**通过**，但整体仍像"左信息岛 + 小车 + 右信息岛"，
而不是一台整体的仪表。以下是按评审意见做的**纯构图**修订——不加任何信息。

| 项 | v2.0 | v2.1 | 依据 |
|---|---|---|---|
| 车辆渲染框 | 584×387 @ (666,85) | **716×474 @ (600,0)** | 缩放 2.011（356×236 → 716×474） |
| 车辆可见宽度 | 420 px | **515 px** | 目标 460–520，取满足所有硬边界的最大值 |
| 车辆地面接触 | y ≈ 411 | **y = 400** | 目标 390–410 |
| 可见车辆（关闭） | 750..1170 / 178..411 | **703..1218 / 115..401** | 由资产 alpha 包围盒与新缩放算出，QA 复核 |
| 全部打开并集 | — | **701..1218 / 42..400** | 仍在 allowed region (560..1360 / 36..456) 内 |
| 氛围光斑 | 800×380 @ (560,40)，0.50 | **1320×520 @ (300,−40)，0.26** | "不再像一个椭圆聚光灯" |
| 路面 | 430..1490 梯形 | **760..1160（地平线 y296）→ 360..1560（y456）** | 收敛在车后，横跨三大区域 |
| 车道线 | 两条短线 | **左 (500,456)→(880,296)、右 (1420,456)→(1040,296)** | 透视指向车后地平线 |
| 地平线 | 430..1490 细线 | **300..1620 细线于 y296** | 与路面同一消失点 |
| 速度字号 | DISPLAY 120 | **DISPLAY 124** | 目标 118–132 |
| 限速牌 | (386,118) 浮在中上 | **(316,248)**，与档位同一水平带 | "靠近速度簇" |
| 档位 | 中心 y309 | **中心 y300** | 与右侧 SOC 行对齐 |
| SOC | 条 y268，% y312 | **条 (1606,294,120×12) 与 % 同一行（中心 y300）** | range 主 / SOC 次 / 功率第三次序 |
| 功率 | 中心 y368 | **中心 y352** | 与左侧 READY 行对齐 |
| 温度/时间 | BODY 28 | **CAPTION 22** | "small, muted" |

**目标 +25%~+35% 与 460–520 px 两条要求互相冲突**：420 × 1.25 = 525 > 520。
这里听从**显式像素区间**（460–520），取 515 px（+22.7%），理由写进 layout 的
`deviations_from_prompt.vehicle_scale`：520 px 需要缩放 2.031，车架底边到 479、
轮胎接地 404，虽仍在画布内但轮胎下方没有任何余量。

**同时修掉一个真实渲染缺陷**：`ImageDraw` 在 alpha=0 时**仍会写入像素**
（把区域压平而不是不画），所以导航隐藏时那圈描边一直可见——也就是评审说的
"空的导航容器"。现在：① 描边跟随 opacity；② opacity ≤ 0 的形状整段不画。
验证方式是探针渲染：把导航节点从场景里删掉再渲染，中性态两张图**逐像素相同
（0 差异）**，这条已进测试。

`assets/checkpoints/horizon_v2/reference/neutral_pre_panel_fix.png` 保留为
**面板修复当时**的中性参考（记录用途）。测试不再与它比对，因为本轮的构图改动
是刻意的；现在的"关闭态"检查是自证的——把车辆节点的状态层全部去掉再渲染，
两者必须逐像素相同。
