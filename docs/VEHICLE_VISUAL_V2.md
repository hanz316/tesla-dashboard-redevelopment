# Vehicle Visual V2 — 车漆 / 反射摄影棚 / 玻璃 / 轮组 / 引擎 A-B

状态：**静态检查点已产出，等待视觉批准（Part Q）**。本轮**未**更换车辆几何，
仍然使用 MODEL A（Tesla 2018 Model 3 FBX → `model3_master.blend`）。

基线 commit：`8068cb5`（上一轮 V1）。

| 项目 | 值 |
|---|---|
| 渲染引擎（正式候选） | Cycles，Metal GPU |
| 采样 | 96 + 自适应采样 + 降噪 |
| 分辨率 | 2200×1520（1100×760 ×2 超采样），RGBA 透明 |
| 材质脚本 | `tools/blender/hmi_studio_v2.py` |
| 渲染脚本 | `tools/blender/render_vehicle_visual_v2.py` |
| 复现脚本 | `tools/blender/render_v2_checkpoint.sh` |

## 1. 本轮到底改了什么（Part A）

V1 的问题不是"参数不对"，而是**没有分层**：车漆只有一个 Principled 的
Base Color / Metallic / Roughness，反射里没有任何东西可反射，所以无论怎么调
都像塑料。V2 加了两样东西：

1. **分层车漆** `M_BodyPaint_HMI_V2`（base + 清漆 + 极轻微噪声/破片）
2. **虚拟反射摄影棚** `HMI_Reflection_Studio_V2`（真正塑造车身的东西）

### 1.1 车漆（A1 / A2）

`M_BodyPaint_HMI_V2_<preset>` 结构：

| 层 | 实现 | 作用 |
|---|---|---|
| Base | Principled Base Color（金属度 0.89–0.94） | 银色基调 |
| Clearcoat | `Coat Weight` 0.65–0.85，`Coat Roughness` 0.040–0.065 | 宽、柔和、连续的 studio 反射 |
| Roughness 变化 | `Noise(scale 7.0, detail 2.0)` → `ColorRamp(0.88–1.10)` → `× base roughness` | 打散均匀的 CG 高光过渡 |
| 破片法线 | `Noise(scale 260)` → `Bump(strength = flake×0.08, distance 0.0007)` | 1:1 下几乎不可见，缩小后只体现为高光"活"了 |

三个预设：

| preset | base RGB | metallic | roughness | coat | coat rough | IOR |
|---|---|---|---|---|---|---|
| silver01 Neutral | 0.560/0.572/0.585 | 0.90 | 0.30 | 0.70 | 0.055 | 1.50 |
| silver02 Dark | 0.150/0.158/0.172 | 0.94 | 0.235 | 0.85 | 0.040 | 1.52 |
| silver03 Cool | 0.455/0.505/0.575 | 0.89 | 0.315 | 0.65 | 0.065 | 1.49 |

明确**没有**做的事（Part A 禁止项）：glitter / sparkle / chrome / mirror
finish / wet plastic。高光最亮值 231–233（0–255），**没有任何像素被削顶**，
说明没有做成镜面或过曝。

### 1.2 反射摄影棚（Part B）

6 块自发光卡片，全部 `visible_camera = False` + `visible_glossy = True`：
渲染中**不可见**，只出现在车漆/玻璃的反射里。没有 HDRI、没有天空、没有
摄影棚背景，最终仍然是透明 RGBA。

| 卡片 | 作用 |
|---|---|
| `Ceiling_Softbox` | 车顶长条高光 |
| `Shoulder_Stripe_Card` | 沿腰线/shoulder line 的窄高光 |
| `Side_Softbox_L` (强度 1.35) | 面向相机一侧的车门曲面渐变 |
| `Side_Softbox_R` (强度 0.55) | 远侧补光，避免死黑 |
| `Rear_Rim_Card` | 尾部与深色仪表背景分离的轮廓光 |
| `Front_Fill_Card` | 前部渐变 |

**它是有效的（Cycles 实测）**：同一相机、同一材质，开/关摄影棚的差异为
**1,098,745 像素（占车体像素 80%）**，最大通道差 201，车体平均亮度
81.6 → 135.5，暗部 p5 从 7 抬到 37（死黑被拉开）。

### 1.3 玻璃（Part C）

`M_RoofGlass_HMI` 与 `M_WindowGlass_HMI` 分开：

| | base | rough | transmission | specular |
|---|---|---|---|---|
| 全景天窗 | 0.011/0.014/0.019 | 0.035 | 0.16 | 0.72 |
| 侧窗 | 0.015/0.019/0.025 | 0.045 | 0.28 | 0.68 |

天窗更暗、更清亮（低 transmission + 高 specular），侧窗稍透一点让内饰
若隐若现。两者都不是黑块、不是灰塑料。

### 1.4 轮组 / 轮胎 / 刹车（Part D）

`M_Wheel_Graphite`（0.085/0.090/0.098，metallic 0.88，rough 0.32，带
clearcoat 边缘高光）、`M_Tire_Rubber`（near-black，rough 0.94，靠 rim light
与背景分离）、`M_Brake_Dark`（metallic 0.60 / rough 0.52，刻意低调）。

### 1.5 灯组（Part E）

全部灯 **OFF**，但灯壳有真实深度：`M_Lens_Clear_Off`（transmission 0.34）、
`M_Lens_Red_Off`、`M_Lens_Amber_Off`，后面垫 `M_Reflector_Dark`
（metallic 1.0 / rough 0.14 的暗铬反射碗）。本轮**不做** emissive 动画。

## 2. 相机最终候选（Part F）

**重要修正：相机改到 +Y 侧（驾驶员侧）。**

模型归一化后车头为 +X、上为 +Z，因此 +Y 是左侧（`door_lf` 所在侧）。
上一轮的 az=+32° 把相机放在 −Y（副驾侧），结果是：

- 左前门在**远侧**开启，只有 7.5% 的车体像素发生变化，看起来像"车后有东西动了一下"
- 相机切到 −32°（驾驶员侧）后，同一动作有 **12.1%** 的像素变化，门是朝观察者打开的

仪表将来必须表达 Door FL/FR/RL/RR，所以正式相机必须在门能被看见的一侧。
三个候选的仰角都比 V1 更平（避免"地图俯视汽车"）。

| 候选 | 方位角 | 仰角 | ortho | look-at Z | 说明 |
|---|---|---|---|---|---|
| V2-A | −32° | 22° | 4.25 | 0.60 | 平衡，当前推荐 |
| V2-B | −36° | 17° | 4.15 | 0.56 | 更低、更有体量感 |
| V2-C | −26° | 20° | 4.20 | 0.58 | 更偏正后方 |

## 3. EEVEE vs Cycles（Part G）

EEVEE Next 和 Cycles 用**完全相同**的材质与相机渲染后比较：

| 指标 | Cycles + studio | Cycles 无 studio | EEVEE + studio | EEVEE 无 studio |
|---|---|---|---|---|
| 车体平均亮度 | 135.5 | 81.6 | 79.0 | 79.0 |
| 亮度标准差 | 58.7 | 69.1 | 66.0 | 66.0 |
| 暗部 p5 | 37 | 7 | 7 | 7 |
| 高光 p95 | 215 | 207 | 204 | 204 |
| 最亮像素 | 233 | 230 | 229 | 229 |

结论：

1. **EEVEE 完全无视反射摄影棚** —— 开/关 studio 的差异是 *0 像素*（最大差 1，
   即 JPEG 级噪声）。EEVEE Next 不把这 6 块 `visible_camera=False` 的自发光
   卡片当作 glossy 反射的光源（它是屏幕空间反射，没有 light probe 烘焙），
   所以 EEVEE 下整个 Part B 是不存在的。
2. **Cycles 是唯一能让摄影棚生效的引擎**：80% 车体像素被改变，暗部从死黑
   被拉开到 37。
3. 因此**正式离线资产使用 Cycles**。代价是离线渲染时间，而 T113 只读 PNG，
   运行时代价为零 —— 这个交换是划算的。

渲染时间（Apple M4, 2200×1520, 96 采样 + 降噪 + 自适应, Metal GPU）：

| 图 | 引擎 | 采样 | 时间 |
|---|---|---|---|
| V2-A silver01 + studio | Cycles | 96 | 1641 s |
| V2-A silver01 无 studio | Cycles | 96 | 1324 s |
| V2-A silver01 + studio | EEVEE Next | 192 | 687 s |
| V2-B silver01 + studio | Cycles | 96 | 574 s |
| V2-C silver01 + studio | Cycles | 96 | 1057 s |
| V2-A silver03 + studio | Cycles | 96 | 1011 s |

> 时间是墙钟时间，且这些渲染与门动画渲染并发进行，因此只能当作量级参考，
> 不是干净的 benchmark。单张 4–28 分钟都属正常。

## 4. 静态检查点（Part H）

最多 6 张，只回答三个问题（车漆/反射、相机、引擎）：

| 图 | 回答的问题 |
|---|---|
| `v2a_silver01_cycles_studio.png` | 候选基准 |
| `v2a_silver01_cycles_nostudio.png` | 摄影棚到底有没有用 |
| `v2a_silver01_eevee_studio.png` | 引擎差异 |
| `v2b_silver01_cycles_studio.png` | 相机 B |
| `v2c_silver01_cycles_studio.png` | 相机 C |
| `v2a_silver03_cycles_studio.png` | 第二种车漆 |

对比图：`assets/rendered/v2/vehicle_visual_v2_comparison.png`

Horizon 预览（1920×480，梯形安全区，已去掉误导性的占位横幅）：

- `assets/rendered/v2/horizon/horizon_v2a_silver01_cycles.png`
- `assets/rendered/v2/horizon/horizon_v2b_silver01_cycles.png`
- `assets/rendered/v2/horizon/horizon_v2a_silver03_cycles.png`

## 5. 仍需真机/人工确认的问题

- **视觉是否达到"高级"** —— 只有人眼能判断。数值上暗部/高光动态范围已经
  合理（p5=37 / p95=215），但"premium"是主观判断。
- 当前渲染的**车漆亮度偏高**（平均 135）是否过亮、是否需要降曝光 —— 需要
  在实际梯形屏幕上、和 Horizon 背景放在一起看。
- 反射卡片强度（Side_Softbox_L 1.35 / R 0.55）是在 −32° 相机下调的，
  如果最终选另一个候选相机，需要复调。
- 最终运行时 PNG 尺寸/内存占用 —— 见 `ANIMATION_PERFORMANCE_TEST_PLAN.md`。

## 6. 生产美术规则（Part Q）

在用户视觉批准之前：

- 旧 placeholder 车辆仍然**禁止**作为 production art。
- V1 的 Silver 01/02/03 只是 Visual V1，**不是** production。
- 本轮 V2 **尚未**成为 production vehicle visual，状态 = **待批准**。
