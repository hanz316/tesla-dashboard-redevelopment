# Vehicle Photoreal Diagnostic — geometry, normals, material

状态：**诊断完成，等待人工视觉审核。本文件不宣布 winner。**

基线 commit：`b180eb5`。本轮**没有**改 MODEL A、没有改 Horizon、
没有重渲任何门动画、没有做 V4 最终材质。目的只有一个：

> 找出塑料感到底来自 geometry、normals、material、lighting、color management
> 还是 source model detail。

环境不再是变量：**Photo Studio 01 固定**，HDRI HYBRID，同一套 rig，
exposure 0.10，film transparent。

---

## 1. 结论摘要

| 诊断项 | 结论 |
|---|---|
| **geometry 有问题吗** | **有**。整车 100% 三角化；body 有 9,720 条非流形边；车门最大面/中位面 = **1,406×** |
| **normals 有问题吗** | **有**。FBX 给每个对象都带了 custom split normals；清理后车门反射波纹下降 **83%**、车顶下降 **56%** |
| **最明显的 panel** | **door_lf / door_rf**（面积比 1406× / 1125×）→ 其次 boot、door_lr/rr、body |
| **需要 subdivision 吗** | **不需要**。清理 normals 已经拿到大部分收益；subdivision 会抹掉 panel crease |
| **material 是主因吗** | 不是唯一主因。material fix 单独作用时画面变化很小（mean +2.4），说明当前材料参数**不是**塑料感的主要来源 |
| **panel gap** | **真实几何**（门/盖/保险杠是独立对象），不是画出来的黑线 |
| **尾灯几何够吗** | **部分够**：有外透镜、反射碗、红色饰件、灯壳；**没有导光条（light guide）** |
| **color management** | 健康。无削顶、无死黑、中间调没有过压缩 |

**最重要的一条**：换了三个合格 HDRI 之后仍然存在的塑料感，
在几何诊断里找到了直接证据 —— 全三角化的车身 + 继承自 FBX 的 custom split
normals。清理 normals 后反射线的波纹下降 83%（门）与 56%（车顶），
而只换材质时画面几乎不变。**这指向 geometry/normals，而不是材质参数。**

---

## 2. Part A — Geometry / normal 诊断

`tools/blender/diagnose_body_geometry.py`，报告在
`assets/checkpoints/vehicle_material_diagnostic_2026-09-16/geometry_report.json`。

### 2.1 全表

| object | verts | tris | ngon% | 非流形边 | 重复顶点 | 反向面% | custom split normals | 最大面/中位面 | 大面占比 |
|---|---|---|---|---|---|---|---|---|---|
| **body** | 28,401 | 47,288 | 0.0 | **9,720** | **3,727** | 0.3 | True | 14.3 | 1.54% |
| **door_lf** | 19,934 | 35,532 | 0.0 | 4,308 | 1,108 | 7.7 | True | **1,406.3** | 8.88% |
| **door_rf** | 17,865 | 32,196 | 0.0 | 3,534 | 787 | 5.8 | True | **1,125.2** | 6.99% |
| door_lr | 14,082 | 25,150 | 0.0 | 3,008 | 741 | 5.2 | True | 27.3 | 4.34% |
| door_rr | 14,071 | 25,118 | 0.0 | 3,016 | 747 | 5.2 | True | 27.2 | 4.34% |
| boot | 6,947 | 11,084 | 0.0 | 2,826 | 1,158 | 0.4 | True | 13.7 | 4.33% |
| front_bumper_ok | 9,972 | 16,136 | 0.0 | 3,918 | 1,588 | 0.2 | True | 15.2 | 0.53% |
| rear_bumper_ok | 9,540 | 15,572 | 0.0 | 3,612 | 1,505 | 0.3 | True | 10.8 | 1.00% |
| bonnet_ok | 2,651 | 4,572 | 0.0 | 730 | 290 | 0.2 | True | 8.3 | 0.00% |
| bodysills | 6,434 | 10,616 | 0.0 | 2,314 | 688 | **99.4** | True | 10.5 | 0.17% |
| glass | 3,272 | 6,528 | 0.0 | 0 | 0 | 0.0 | True | 15.5 | 11.52% |
| hub_lf / hub_rf | 2,173 | 2,514 | 0.0 | 1,712 | 842 | **19.9** | True | 79.8 | 7.88% |
| hub_lb / hub_rb | 3,354 | 2,795 | 0.0 | 3,313 | 1,871 | **46.1** | True | 61.7 | 6.23% |
| black_lights | 3,550 | 6,348 | 0.0 | 740 | 0 | **35.5** | True | 19.3 | 3.94% |

### 2.2 三个关键发现

**一、模型 100% 三角化。** 所有 10 个外板对象的 ngon 占比都是 0，三角形数
= 面数。三角化网格没有连续的四边面流向，反射线在三角形边界处容易
pinch / 折弯 —— 这正是人工看到的 "body reflection deformation"。

**二、door_lf / door_rf 有极端尺寸差异的面。** 最大面是中位面的
**1,406 倍 / 1,125 倍**，大面占比 8.88% / 6.99%。也就是说门板上混着
极少数超大三角形和大量微小三角形。超大三角形上任何法线误差都会被放大成
可见的反射折痕 —— 与"door / rear quarter panel 像大块光滑塑料"完全吻合。

**三、所有对象都带 custom split normals（FBX 导入带来的）。**
custom split normals **优先于**任何 smooth/sharp 设置，也就是说后续无论怎么
设 shading，实际法线仍然是导入时那一套。这是本轮最重要的发现之一。

另外：`bodysills` 99.4% 反向面、轮毂 19.9–46.1% 反向面、`black_lights` 35.5%
反向面。对开放曲面（薄板）来说"反向"有一半是 recalc 参考系的问题，
但轮毂接近 50% 说明它基本是随机绕序。

---

## 3. Part B — Class-A 反射检测

不使用漂亮 HDRI。标准汽车曲面检测装置：**纯黑 world + 5 条极长极宽的白色
反射带**（`tools/blender/render_reflection_diagnostic.py`），
相机 SIDE / REAR QUARTER / ROOF / DOORS 四个视角。

好曲面上反射线是**直的、连续的**；波浪、折断、pinch 都是曲面缺陷。

图：`geometry_reflection_diagnostic.png`（4 视角 × ORIGINAL / NORMAL FIX）

### 3.1 定量连续性

`tools/assets/analyze_reflection_continuity.py` 追踪每一列最亮脊线的位置，
报告断裂列数与二阶差分 RMS（"waviness"，直线为 0）：

| 视角 | ORIGINAL waviness | NORMAL FIX waviness | 变化 |
|---|---|---|---|
| **doors** | **11.272** | **1.946** | **−83%** |
| **roof** | **7.696** | **3.405** | **−56%** |
| side | 2.866 | 2.693 | −6% |
| rear_quarter | 4.356 | 5.141 | +18% |

断裂列数几乎不变（门的 33 → 34），因为"断裂"大多发生在反射带根本不落到
曲面上的位置，那不是缺陷。

> 注：这是**客观测量**，不是视觉结论。哪个视角看起来最差仍需要人眼判断。

---

## 4. Part C — Normal fix A/B

`--normals clean` 做了四件事，**全部只在内存中，绝不写回 FBX 或 master .blend**：

1. 清除 custom split normals（107 个对象）
2. merge by distance（阈值 0.0002）→ 焊接 **26,868** 个重复顶点
3. recalculate outside
4. 全部 shade smooth + Weighted Normal modifier（keep_sharp = True）

**keep_sharp = True 是关键**：保留 panel gap、door edge、fender crease、
trunk shoulder、bumper transition 的折痕，不会把真实造型抹平成"光滑塑料"。

**没有使用 subdivision。** 结论是当前不需要：清理 normals 已经拿到车门 83%、
车顶 56% 的收益，而 subdivision 会系统性削弱折痕。

A/B 图：`geometry_reflection_diagnostic.png` 的 ORIGINAL / NORMAL FIX 两行。

---

## 5. Part D/E — 车漆

### 5.1 四个 shader 候选

| | PAINT A（基线） | PAINT B 物理保守 | PAINT C basecoat+clearcoat | PAINT D 600px flake |
|---|---|---|---|---|
| metallic | 0.94 | **1.00** | 0.80 | 0.88 |
| roughness（basecoat） | 0.215 | 0.300 | **0.360** | 0.295 |
| coat weight | 1.00 | **0.00** | 1.00 | 1.00 |
| coat roughness | 0.038 | — | **0.022** | 0.045 |
| flake strength | 0.055 | 0.030 | 0.075 | **0.115** |
| flake scale | 190 | 220 | 150 | **120** |
| roughness 变化幅度 / 尺度 | 0.055 / 3.5 | 0.040 / 4.0 | 0.070 / 3.0 | 0.085 / 2.4 |

设计意图：

- **B** 只有一个 lobe（金属本体），不做额外清漆，作为"物理最保守"的参照。
- **C** 是**两个明显不同宽度的 lobel**：粗糙 basecoat 提供宽反射，
  极光滑 clearcoat 提供锐利但受控的反射。
- **D** 专门为**最终的 600px 尺寸**设计：渲染时车宽 1868px，发布资产 600px，
  即 3.1 倍降采样。flake scale 120 → 渲染尺度约 16px → 600px 下约 5px，
  刚好是"高光有极轻微真实质感"而不是 glitter 的尺度。

### 5.2 三个银色

| | base color | 说明 |
|---|---|---|
| **OEM SILVER NEUTRAL** | 0.585 / 0.600 / 0.622 | 中性银 |
| **OEM SILVER COOL** | 0.520 / 0.548 / 0.592 | 偏冷，蓝向 |
| **OEM SILVER GRAPHITE** | 0.400 / 0.412 / 0.430 | 深银，仍为金属，不是 gunmetal black |

三者都是高 metallic 金属漆，没有纯灰、纯白、chrome。
图：`paint_candidates.png`、`paint_colours.png`

---

## 6. Part F — Clearcoat 分层验证

把两个 lobe 分别关掉：

| 模式 | 做法 | mean | p95 | max |
|---|---|---|---|---|
| BASECOAT ONLY | coat weight = 0 | 139.9 | 197 | 215 |
| CLEARCOAT ONLY | base color → 0.004（金属 lobe 几乎不贡献），coat = 1 | **90.6** | 171 | 239 |
| COMBINED | 两者都在 | 140.5 | 197 | 223 |

COMBINED ≈ BASECOAT：说明**当前亮度主要来自 basecoat**，clearcoat 是叠加在
上面的锐利次级 lobe；CLEARCOAT ONLY 明显更暗更硬（p95 171 但 max 239，
即少量极亮窄高光）。**两个 lobe 确实在贡献不同尺度的反射**，不是单层 specular。

图：`clearcoat_lobes.png`

---

## 7. Part G — Glass

按 pane 分开，不再统一"深色 + transmission"：

| pane | tint | roughness | transmission | specular | IOR |
|---|---|---|---|---|---|
| **roof** | 0.014/0.018/0.026 | **0.014** | **0.12** | **1.00** | 1.54 |
| front | 0.020/0.024/0.032 | 0.020 | 0.26 | 0.92 | 1.52 |
| side | 0.024/0.029/0.038 | 0.026 | 0.34 | 0.86 | 1.52 |
| rear | 0.019/0.023/0.031 | 0.022 | 0.28 | 0.90 | 1.52 |

针对"天窗像一整块黑色 glossy plastic"：天窗的 roughness 降到 0.014、
specular 拉满、transmission 降到 0.12、IOR 提到 1.54 —— 让 Fresnel 边缘响应
和掠射反射成为主要视觉信号，而不是让透射压成一块黑。

Diagnostic 图（含 before/after）：`detail_before_after.png` 的上排。

---

## 8. Part H — 尾灯

### 8.1 MODEL A 到底有什么结构（实测）

| 结构 | 是否存在 | 对应对象 / 材质 |
|---|---|---|
| outer lens 几何 | **有** | `light_breake`、`rear_lights`、`rear_lightsl`、`rear_lightsr`、`light_turn_lr_boot`、`lightrevese_boot` |
| 内部反射碗 | **有** | `light_pantulan`、`pantulans` |
| 红色饰件 | **有** | `satin_red` |
| 灯壳 / trim | **有** | `black_lights`、`back_chrome_light` |
| **导光条 (light guide)** | **没有** | — |

**明确结论：仅靠材质无法做出真实尾灯的导光条效果**，因为模型里没有那段几何。
材质能做到的是：外透镜、内部暗腔、反射碗、红色饰件四层分离。
再往上就是加几何，本轮不做（也超出"不改 geometry"的约束）。

### 8.2 材质结构

| 层 | 材质 | 参数 |
|---|---|---|
| 外红透镜 | `M_TailLens_Outer_v4` | base 0.230/0.022/0.024，rough 0.028，**transmission 0.36**，specular 0.95，IOR 1.51 |
| 内部暗腔 | `M_TailCavity_v4` | base 0.008，rough 0.70，specular 0.22 |
| 反射碗 | `M_TailReflector_v4` | base 0.640，metallic 1.0，rough 0.065 |
| 红色饰件 | `M_TailSatinRed_v4` | base 0.140/0.016/0.018，rough 0.34 |
| 灯壳 | `M_LightHousing_v4` | base 0.016，metallic 0.20，rough 0.46 |

图：`detail_before_after.png` 的中排（taillight CURRENT / MATERIAL FIX）。
文件名按你要求为 `taillight_closeup_before_after` 的对应产出 = 该图的中间两格，
独立文件在 `checks/` 内。

---

## 9. Part I — Wheel

| | CURRENT | MATERIAL FIX |
|---|---|---|
| 轮毂 base | 0.135 | **0.150** |
| roughness | 0.255 | **0.225** |
| **anisotropic** | 0.45 | **0.62** |
| coat | 0.20 | 0.28 |
| specular | 0.55 | **0.70** |
| 刹车盘 | base 0.240 rough 0.42 | base 0.270 rough 0.38 + anisotropic 0.35 |

加强各向异性（0.45 → 0.62）让不同辐条面产生明显不同的反射长度；
刹车盘单独提亮以与轮毂分离。轮毂 base 仍远低于车身（0.150 vs 0.585），
**没有把轮毂做得比车身亮**。

图：`detail_before_after.png` 的下排。

---

## 10. Part J — Panel gap

**结论：真实几何，不是贴图黑线。**

门（`door_lf/rf/lr/rr`）、引擎盖（`bonnet_ok`）、后备箱（`boot`）、
前后保险杠（`front_bumper_ok` / `rear_bumper_ok`）都是**独立对象**，
各自有边界边（body 9,720 条非流形/边界边的一部分来自这些接缝）。
这意味着 panel gap 来自对象之间的真实间隙与轮廓，不是画出来的一条线。

本轮**没有**用粗黑线去增强它，也没有做任何 gap 相关的材质改动。
清理 normals 时使用的 Weighted Normal（keep_sharp = True）会保留这些折痕。

---

## 11. Part K — Color management

### 11.1 RAW LINEAR（EXR，显示变换之前）

`assets/rendered/material_study/linear_both.exr`：

| 指标 | 值 |
|---|---|
| p1 | 0.0051 |
| p50 | 0.3910 |
| p95 | 0.9193 |
| p99 | 1.4289 |
| max | 2.6 |
| **>1.0 的像素** | **3.95%** （有 headroom，交给 AgX 滚降，不是硬裁） |
| <0.005（近黑） | 0.977% |
| 动态范围 p99/p1 | **282 : 1** |

### 11.2 FINAL DISPLAY TRANSFORM（8-bit PNG）

| 列 | mean | std | p1 | p5 | p50 | p95 | max | =0 | ≥250 | 中间调(100–155)占比 |
|---|---|---|---|---|---|---|---|---|---|---|
| CURRENT | 136.7 | 49.9 | 10 | 40 | 158 | 192 | 234 | 0.01% | **0.00%** | 16.1% |
| GEOM FIX | 136.8 | 49.9 | 10 | 40 | 158 | 193 | 234 | 0.01% | **0.00%** | 16.0% |
| MATERIAL FIX | 139.1 | 50.1 | 11 | 39 | 162 | 196 | 227 | 0.01% | **0.00%** | 14.3% |
| BOTH | 139.2 | 50.1 | 11 | 39 | 162 | 196 | 228 | 0.00% | **0.00%** | 14.2% |

**结论：没有 washed highlights（0% ≥250）、没有 grey blacks（≈0% 在 0，
p1 仍有 10–11）、中间调没有过压缩（13.8–16.1% 落在 100–155 区间）。**
没有为了"高级"去加对比度。

一个值得注意的点：**GEOM FIX 列与 CURRENT 列几乎完全相同**（mean 136.7 vs 136.8，
所有分位数一致）。清理 normals 改变的是反射的**形状**（waviness −83%/−56%），
不是整体亮度分布。这正说明它是曲面问题，不是曝光问题。

---

## 12. Part L/M — 4 列对比与 600px

固定环境：**Photo Studio 01**，HDRI HYBRID，同一 rig，exposure 0.10，
camera V2-A，1100×760（supersample 1），Cycles 48 spp。

四列：

| 列 | normals | material |
|---|---|---|
| CURRENT | original | baseline（photoreal v3 冻结值） |
| GEOMETRY / NORMAL FIX ONLY | clean | baseline |
| MATERIAL FIX ONLY | original | v4（PAINT D + NEUTRAL + v4 glass/taillight/wheel） |
| GEOMETRY + MATERIAL FIX | clean | v4 |

产物：

- `vehicle_material_diagnostic_4column.png`（四列全尺寸）
- `vehicle_material_diagnostic_600px.png`（**车宽 600px**，最终判断尺寸）
- `vehicle_material_diagnostic_horizon.png`（Horizon 实尺寸 1:1）

600px 是主判断尺寸：**如果某个效果只在 full-res 可见，它对项目没有价值。**
四列的 600px 与 Horizon 1:1 都在 `checks/` 里单独存了一份。

Horizon 背景使用既有的 `scenes/horizon_redesign_a.scene`（normal_drive，
framing `700x401@610,40`），**未修改 Horizon**。

---

## 13. 渲染时间（Mac，CPU，1100×760，48 spp）

| 批次 | 单张 |
|---|---|
| 反射检测（900×620，32 spp，CPU） | 8.7–22.8 s |
| 车漆候选 / 颜色 / clearcoat / 4 列对比 | 10.4–15.7 s |
| 玻璃特写 | 18.5–26.2 s |
| 尾灯 / 轮毂特写 | 16.1–18.6 s |
| LINEAR EXR（同一设置） | 9.0 s |

> GPU（Metal）在本轮**两次因显存不足失败**（`Insufficient Memory`），
> 因此诊断渲染全部改为 CPU。这是环境限制，不影响结论。

## 14. 明确未做的事

没有重渲 Door_FL 动画；没有做 Door_FR/RL/RR、Frunk、Trunk、Indicators；
没有改 Horizon；没有改 VehicleState / UART / Commander；
没有把任何本轮材质写入 master `.blend`。
