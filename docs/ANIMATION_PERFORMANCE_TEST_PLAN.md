# 动画性能测试计划（含 60fps 的真实含义）

状态：**计划 + 资产已就绪，真机测试未执行**。

在真机数据出现之前，本文档里所有设备端帧率/耗时结论一律写作
**UNKNOWN UNTIL DEVICE TEST**。**不允许**把芯片型号、数据手册、Mac 上的测量
结果当作 T113 的性能结论。

---

## 1. Part M — "60 FPS" 必须拆成四件事

把下面四件事混成一个"60fps"是这类项目最常见的技术债来源：

| # | 名称 | 含义 | 当前状态 |
|---|---|---|---|
| 1 | **PANEL REFRESH RATE** | 屏幕/显示控制器是否真的 60Hz 刷新 | **UNKNOWN UNTIL DEVICE TEST** |
| 2 | **UI UPDATE RATE** | EasyUI / NanoVG 逻辑能否 60Hz 提交 | **UNKNOWN UNTIL DEVICE TEST** |
| 3 | **COMPLEX PNG ANIMATION RATE** | `ZKImageAnim` 能否稳定 60fps 解码 + 合成 | **UNKNOWN UNTIL DEVICE TEST** |
| 4 | **PERCEIVED MOTION QUALITY** | 主观流畅度；重车辆动画 30fps + 轻 UI 高刷也可以"看起来顺" | **UNKNOWN UNTIL DEVICE TEST** |

工程含义：

- 即使 1 成立，2/3 也可能不成立。
- 即使 3 不成立（复杂 PNG 只能 30fps），4 仍然可以达标 —— 这是
  `MotionQualityPolicy` 里 BALANCED 档存在的原因。
- 面板是否真 60Hz 需要**实测**（例如高帧率下拍摄屏幕或用内核/驱动信息确认），
  不能从"这是个 1920×480 的车机屏"推断。

---

## 2. Part N — Door 动画性能矩阵

### 2.1 测试矩阵（9 格）

| # | 车辆宽度 | fps | 资产目录 | 帧数 |
|---|---|---|---|---|
| 1 | 400 | 24 | `assets/rendered/door_fl/400_24` | 17 |
| 2 | 400 | 30 | `assets/rendered/door_fl/400_30` | 21 |
| 3 | 400 | 60 | `assets/rendered/door_fl/400_60` | 40 |
| 4 | 600 | 24 | `assets/rendered/door_fl/600_24` | 17 |
| 5 | 600 | 30 | `assets/rendered/door_fl/600_30` | 21 |
| 6 | 600 | 60 | `assets/rendered/door_fl/600_60` | 40 |
| 7 | 800 | 24 | `assets/rendered/door_fl/800_24` | 17 |
| 8 | 800 | 30 | `assets/rendered/door_fl/800_30` | 21 |
| 9 | 800 | 60 | `assets/rendered/door_fl/800_60` | 40 |

### 2.2 每格要记录的字段

| 字段 | 单位 | 怎么取 |
|---|---|---|
| `observed_fps` | fps | 动画播放期间的实际合成帧率 |
| `avg_frame_ms` | ms | 平均每帧总耗时 |
| `p95_frame_ms` | ms | 95 分位（卡顿敏感） |
| `p99_frame_ms` | ms | 99 分位，判定档位的依据 |
| `dropped_frames` | 帧 | 整个 0.65 s 播放期间丢的帧 |
| `decode_ms` | ms | 单帧 PNG 解码耗时 |
| `composite_ms` | ms | 单帧合成/上屏耗时 |
| `cpu` | % | 播放期间 CPU 占用 |
| `rss` | MB | 播放期间进程 RSS 峰值 |

这些字段与 `include/dashboard/motion_quality.h` 的 `MotionBenchmarkSample`
一一对应，测完直接喂给 `evaluateMotionQuality()` 就能得到允许的档位。

### 2.3 判定规则

以 30fps 为基准（每帧预算 33.3 ms）：

- `p99 ≤ 33.3 ms` 且 `dropped == 0` → 允许 **FULL**（并允许 60Hz UI）
- `p99 ≤ 50 ms` 且 `dropped ≤ 2` → **BALANCED**：车辆动画降到 30fps，轻量
  UI 仍可高刷
- 其余 → **SAFE**：30fps、同时只允许 1 个序列

这条规则已经实现在 `src/core/motion_quality.cpp`，并由
`tests/motion_quality_tests.cpp` 覆盖（含"Mac 数据不得升档"的用例）。

---

## 3. 资产侧实测（Mac，**不是**设备性能）

用 `python3 tools/assets/check_budget.py --sequence --alpha-crop <dir>` 得到。

### 3.1 全画布解码

| 变体 | 帧数 | canvas | PNG/帧 | 存储合计 | 解码/帧 | 折算设备解码 | 占 30fps 预算 |
|---|---|---|---|---|---|---|---|
| 400_24 | 17 | 513×354 | 77.1 KB | 1.31 MB | 0.693 MB | 14.9 ms | 45% |
| 400_30 | 21 | 513×354 | 77.1 KB | 1.62 MB | 0.693 MB | 14.9 ms | 45% |
| 400_60 | 40 | 513×354 | 77.1 KB | 3.08 MB | 0.693 MB | 14.9 ms | 45% |
| 600_24 | 17 | 769×531 | 156.1 KB | 2.65 MB | 1.558 MB | 33.4 ms | **100%** |
| 600_30 | 21 | 769×531 | 156.1 KB | 3.28 MB | 1.558 MB | 33.4 ms | **100%** |
| 600_60 | 40 | 769×531 | 156.1 KB | 6.24 MB | 1.558 MB | 33.4 ms | **100%** |
| 800_24 | 17 | 1026×709 | 260.7 KB | 4.43 MB | 2.775 MB | 59.6 ms | **179%** |
| 800_30 | 21 | 1026×709 | 260.7 KB | 5.47 MB | 2.775 MB | 59.6 ms | **179%** |
| 800_60 | 40 | 1026×709 | 260.7 KB | 10.43 MB | 2.775 MB | 59.6 ms | **179%** |

`check_budget.py` 对这 9 格全部报 **FAIL**（阈值是单序列 ≤30% 预算）。

> 折算方式：host 实测 237×351 约 0.227 ms，按像素数放大后再乘 A7 相对
> Apple Silicon 单核的约 30 倍系数（来源见 `RENDERING_CAPABILITY_AUDIT.md`
> §11）。**这是估计值，真机数字仍然是 UNKNOWN UNTIL DEVICE TEST。**

### 3.2 只解码实际有效像素（推荐的运行时做法）

序列为了对齐，保留了固定的空边距，画布上只有约 30% 的像素是车：

| 变体 | 车实际占用 | 占画布 | 裁剪后解码/帧 | 折算设备解码 | 占 30fps 预算 |
|---|---|---|---|---|---|
| 400_* | 310×179 | 31% | 0.212 MB | 4.5 ms | **14%** |
| 600_* | 462×266 | 30% | 0.469 MB | 10.1 ms | **30%** |
| 800_* | 617×354 | 30% | 0.833 MB | 17.9 ms | **54%** |

这张表是本轮最重要的工程结论：

1. **绝对不能整段 preload。** 800_60 全帧解码当量 = 111 MB，而设备可用
   RAM 约 183 MB；等于不留给别的东西。
2. **必须按有效像素上传/解码**（sprite 或 atlas 单元只取 alpha 包围盒），
   否则 600 和 800 两个尺寸在纸面上就已经超预算。
3. 裁剪后 600px 刚好卡在 30%（可接受），800px 是 54%（只能在 BALANCED/SAFE
   之下、且同时只跑一个序列）。
4. 400px 是唯一在全画布解码下仍有希望的尺寸，裁剪后只有 14%。

### 3.3 存储占用

800_60 一组 PNG 就是 **10.4 MB**。九组全放设备上是 37.6 MB。如果最终要保留
三种尺寸，建议只把**实际采用的那一档**放进发布资产，其余留在 Mac。

---

## 3.4 V3 更新：difference crop 加入后重算（Parts 15-16）

上面 A/B 的结论（全画布必败）没有变，但 V3 增加了第三种策略。完整数据在
`docs/DELTA_ANIMATION_PIPELINE.md`，这里只放结论：

| 变体（open） | A 全画布 | B alpha crop | **C difference crop** |
|---|---|---|---|
| 400px / 30fps | 14.9 ms（45%） | 4.5 ms（14%） | **1.9 ms（6%）** |
| 600px / 30fps | 33.4 ms（100%） | 10.1 ms（30%） | **3.0 ms（9%）** |
| 800px / 30fps | 59.5 ms（179%） | 17.9 ms（54%） | **5.8 ms（17%）** |
| 400px / 60fps | 14.9 ms（89%） | 4.5 ms（27%） | **1.8 ms（11%）** |
| **600px / 60fps** | 33.4 ms（**200%**） | 10.1 ms（60%） | **3.0 ms（18%）** |
| **800px / 60fps** | 59.5 ms（**357%**） | 17.9 ms（**107%**） | **5.6 ms（34%）** |

百分比以各自帧率的预算为分母（30fps = 33.3 ms，60fps = 16.7 ms）。

三条读法：

1. 全画布在 60fps 下**根本不可能**（600px 就要 200%，800px 要 357%）。
2. alpha crop 修好了 30fps，但 800px/60fps 仍是 107% —— 仍然超预算。
3. **difference crop 是唯一让 800px/60fps 落到预算内的方案（34%）**。

> 仍然只是 **ESTIMATED ONLY**。解码只是每帧成本的一部分，合成、上屏、UI
> 逻辑都没算进来，所以"解码占 18%"不等于"能跑 60fps"。
> **UNKNOWN UNTIL DEVICE TEST。**

另外注意：difference crop **不能**简单理解为"渲染得更少"——每帧仍要完整渲染，
省下来的只是**传输与解码**。渲染成本在 Mac 上，与设备无关。

---

## 4. Part O — 全屏 Benchmark 矩阵（准备好，**不要**现在真机执行）

每一格都要记录 §2.2 的全部字段，并明确回答"这一格能不能稳定 60fps / 30fps"。

| 测试 | 内容 | 目的 |
|---|---|---|
| **A** | 静态 Horizon，目标刷新率 | 面板 + 静态合成基线 |
| **B** | Horizon + speed 文本 10Hz | 文本重绘代价 |
| **C** | Horizon + NanoVG 轻量矢量动画 | 纯矢量路径的刷新上限 |
| **D** | Horizon + 400px Door @60fps | 小尺寸序列能否 60 |
| **E** | Horizon + 600px Door @60fps | 中尺寸序列能否 60 |
| **F** | Horizon + 800px Door @60fps | 大尺寸序列能否 60 |
| **G** | Horizon + 600px Door @30fps + NanoVG 动画 | 混合档：重动画 30 + 轻 UI 高刷 |

判定目标：找出哪些组合可以稳定 60fps、哪些只能稳定 30fps，并把结果写回
`MotionQualityPolicy`，而不是写死在代码里。

---

## 5. Part P — MotionQualityManager（接口已落地，运行时未改）

`include/dashboard/motion_quality.h` + `src/core/motion_quality.cpp`。

三个档位：

| 档位 | UI 刷新 | 车辆动画 | 同时序列数 | 映射到既有引擎枚举 |
|---|---|---|---|---|
| **FULL** | 60 Hz | 60 fps | 2 | `MotionQuality::Full` |
| **BALANCED** | 60 Hz | 30 fps | 1 | `MotionQuality::Low` |
| **SAFE** | 30 Hz | 30 fps | 1 | `MotionQuality::Off` |

硬性规则：

1. **绝不根据芯片理论自动选 FULL。** `measured_on_device == false` 时
   `evaluateMotionQuality()` 直接返回 SAFE —— 这就是当前项目的真实状态。
2. 一个矩阵格子不达标，`worstCasePolicy()` 必须能把整体档位拉下来。

这层是**新增**的，没有改动 `MotionEngine` / `HorizonRendererV6` /
`PageManagerV6` 的任何行为。

---

## 6. 真机执行步骤（将来）

1. `git checkout feature/v6-cockpit`，确认 HEAD。
2. Mac：`cmake -S . -B build && cmake --build build -j && ctest --test-dir build`
3. Mac：`bash scripts/build_t113.sh`（Docker 工具链，32-bit musl hard-float）
4. 只读确认 `/dev/ttyS5` 仍以 `O_RDONLY` 打开；**不发**任何车辆控制命令。
5. 用现有安全流程**只部署到 `/tmp`**，重启 `zkswe`，核对 PID/maps 确实加载了
   临时 `libzkgui.so`。
6. 按 §2.1 逐格播放，抓 `/data/local/tmp` 上的计时日志。
7. 同时记录 CPU / RSS / dropped frames / decode / composite。
8. 结果填回本文件，再更新 `MotionQualityPolicy` 的默认档位。

禁止：刷 flash、写 bootloader、写 MCU 固件、Raw CAN TX。
