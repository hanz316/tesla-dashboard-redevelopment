# MODEL_A_PRODUCTION_MASTER

状态：**本轮完成 cleanup 与验证；是否冻结由人工审核决定。本文件不代替人工签署。**

基线：`0d5fcb7`。MODEL A **正式选为 V6 七套 UI 共用的 Production Vehicle
Master**。本轮不再比较模型、不搜索 HDRI、不做 retopology、不重设计
paint/glass 架构、不重设计 Horizon、不做任何动画。

---

## 1. 实际修改了什么

| # | 修改 | 范围 |
|---|---|---|
| 1 | 按实测策略逐 panel 应用 normal 处理 | **只处理 5 个对象**（107 个中的 5 个） |
| 2 | 尾灯内部新增正式 light-guide 几何 + 暗腔 | 4 个尾灯对象内部 |
| 3 | 冻结材质：reference paint / reference glass / v4 wheel | 仅安装，未重新设计 |
| 4 | 冻结相机、灯光、渲染与色彩管理设置 | 写入 master .blend |
| 5 | 生成 master .blend + 参数 manifest | 见 §7 |

**没有**全车重算 normals；**没有** subdivision / remesh；**没有**改动任何
外板 geometry；**没有**改动 Horizon 或任何动画资产。

## 2. 原计划修改但最终没有必要

| 原计划 | 结论 |
|---|---|
| 全车 normal 统一修复 | **不需要**。实测 4 个 panel（door_lr / door_rr / boot / rear_bumper_ok）统一修复会更差，因此只处理 5 个 |
| retopology / voxel remesh | **不需要且有害**。上一轮 4mm/2.5mm 实测让反射变差（waviness 1.671 → 3.578/3.597），面数 ×19 无收益 |
| subdivision surface | **不需要**。会削弱 panel gap 与 crease，且 Part C 已证明拓扑不是天花板 |
| 新的 paint architecture | **不需要**。reference paint 的双 lobe 架构已验证有效（两个 lobe 粗糙度相差 19 倍） |
| 新的 glass architecture | **不需要**。dielectric + 独立涂层已解决"黑亚克力"问题 |
| HDRI 重选 | **不需要**。Photo Studio 01 已固定为统一环境 |
| 车身大面积细节重建 | **不需要**。detail 检查未发现 floating geometry（0 个对象在车身包围盒之外） |

## 3. Taillight geometry 最终结构

**外轮廓完全未改**：原有 outer lens 对象一个顶点都没动。新增的部分全部在
透镜**内部**。

| 层 | 实现 | 参数 |
|---|---|---|
| outer lens | **原有 MODEL A 几何** | 保留 |
| internal dark cavity | 新增 cube shell，缩放至原 bbox 的 62%，居中 | `M_TailCavity_v4`：base 0.008，rough 0.70，specular 0.22 |
| reflector | **原有** `light_pantulan` / `pantulans` | `M_TailReflector_v4`：base 0.640，metallic 1.0，rough 0.065 |
| **light guide** | **新增** 沿弧线扫掠的实心圆棒 | 半径 **8.5 mm**，28 段弧 × 12 边环，内缩 **16 mm** |

Light guide 的构造方式（不是贴图、不是 overlay）：

- 取原尾灯对象的世界 bbox，沿长轴取 72% 长度
- 沿一条**浅弧**扫掠（sagitta = 灯宽的 16%），因此有真实曲率
- 圆截面、封口，**有真实厚度**
- 位于透镜内表面之后 **16 mm**，不接触外透镜
- 材质 `M_TaillightLightGuide_OFF`：base 0.165/0.020/0.022、metallic 0.0、
  rough 0.09、IOR 1.49、**transmission 0.42**、specular 0.90，**无 emission**

四盏灯各生成一组（`rear_lights` / `rear_lightsl` / `rear_lightsr` /
`light_breake`），共 4 根导光条 + 4 个暗腔。

**为后续状态预留**：LIGHT_OFF / BRAKE_ON / LEFT_INDICATOR / RIGHT_INDICATOR
只需要在**同一根导光条**上切换材质或增加 emission，不需要新的几何、
不需要重算相机或灯光。

## 4. Final paint parameters

架构**未改**（basecoat + 独立 clearcoat 双 lobe，Voronoi flake 在 basecoat 之下）：

| 项 | 值 |
|---|---|
| silver | OEM SILVER NEUTRAL |
| base color | 0.560 / 0.578 / 0.605 |
| basecoat metallic | 1.0 |
| basecoat roughness | 0.340 |
| basecoat roughness 变化 | Noise scale 2.6，范围 0.90–1.12 |
| flake | Voronoi F1，scale 260，bump strength 0.16，distance 0.0006 |
| clearcoat BSDF | Glossy，roughness **0.018**，color 0.92/0.93/0.95 |
| mix | base 0.42 + Fresnel gain 0.62（Layer Weight blend 0.16） |

两个 lobe 的粗糙度相差 **19 倍**（0.018 vs 0.340），这是"宽 basecoat 反射 +
锐利 clearcoat 反射"能同时被看见的原因。

**flake 在 600px 下不可辨认**（实测）：生产 600px 渲染的车顶高频能量
**18.5**，与上一轮（无此 flake 配置）的 **17.8** 基本一致，stripes=1、
strMax=2。也就是说高频主要来自环境而不是 flake，没有变成颗粒。

## 5. Final glass parameters

架构**未改**（Principled 介电层 + 独立 Glossy 涂层，按 coat 权重混合）：

| pane | tint | roughness | transmission | IOR | coat |
|---|---|---|---|---|---|
| **roof** | 0.012/0.016/0.024 | **0.010** | 0.10 | 1.545 | **0.85** |
| front | 0.018/0.022/0.030 | 0.016 | 0.22 | 1.525 | 0.55 |
| side | 0.022/0.027/0.036 | 0.020 | 0.30 | 1.520 | 0.40 |
| rear | 0.017/0.021/0.029 | 0.018 | 0.25 | 1.522 | 0.48 |

天窗用最低 roughness 与最高 coat 权重，因此正视角深、掠射角有自然 Fresnel，
且不需要人为加白色大反射。

## 6. Final wheel / tire parameters

| | base | metallic | roughness | 其他 |
|---|---|---|---|---|
| rim | 0.150/0.157/0.170 | 0.95 | 0.225 | anisotropic **0.62**、coat 0.28、specular 0.70 |
| tire | 0.020/0.020/0.022 | 0.0 | **0.93** | specular 0.26 |
| brake disc | 0.270/0.272/0.278 | 1.0 | 0.38 | anisotropic 0.35 |

轮毂 base 0.150 对车身 0.560 —— 轮毂**不会比车身亮**。轮胎 rough 0.93 +
specular 0.26：极暗但不为 0，掠射角保留一点光泽以避免 black crush。
**没有添加任何 fake rim-light outline。**

## 7. Normal policy 是否完整应用

**是，且只应用了策略中的对象**（不为了统一而全车重算）：

| panel | 策略 | 是否处理 |
|---|---|---|
| door_lf | WEIGHTED | ✓ |
| door_rf | CLEAN | ✓ |
| door_lr | KEEP_ORIGINAL | 未触碰 |
| door_rr | KEEP_ORIGINAL | 未触碰 |
| bonnet_ok | WEIGHTED | ✓ |
| boot | KEEP_ORIGINAL | 未触碰 |
| front_bumper_ok | CLEAN | ✓ |
| rear_bumper_ok | KEEP_ORIGINAL | 未触碰 |
| body | WEIGHTED | ✓ |

处理了 **5 / 107** 个对象；焊接 **8,158** 个顶点；清除 5 个对象的 custom
split normals；3 个对象加了 Weighted Normal（keep_sharp=True）。
其余 102 个对象**完全未触碰**。

## 8. 亮度与 clipping 数据

| 输出 | mean | std | p1 | p5 | p95 | max | ≥250 clipping | <8 black crush |
|---|---|---|---|---|---|---|---|---|
| **full (2200×1520)** | 152.5 | 48.9 | 10 | 38 | 205 | 228 | **0** | 0.68% |
| **600px 车宽** | 152.0 | 48.6 | 10 | 38 | 205 | 228 | **0** | 0.77% |
| Horizon 1:1 | 车区 92.8 / std 78.9（背景 13.6） | | | | | | 0 | — |

三种尺寸**均无削顶**；自发光部分为零（尾灯为 OFF 状态）。

## 9. 是否发现仍未解决的 geometry defect

**没有发现阻止冻结的 defect，但有两点必须记录：**

1. **detail 检查通过**：0 个对象位于车身包围盒之外（无 floating geometry）、
   无退化对象；alpha fringe 全分辨率 **0** 个可疑像素、600px 仅 3 个
   （占半透明像素 0.2%），没有 halo。
2. **仍然存在的、已知且不修的限制**：外板 100% 三角化、面积比最高 1406×、
   dihedral p95 18–27°。上一轮已证明这些**不影响反射连续性**（remesh 反而更差），
   所以它们被记录为"已知且接受"，而不是"待修"。
3. 尾灯之外的灯组（前灯/雾灯/转向灯）没有各自的内部结构升级 —— 它们不在
   本轮问题清单里，也未被证明缺几何。

## 10. 是否达到可以冻结的状态

**技术上达到。** 判据：

- normal 策略按实测逐 panel 应用，未做全车统一处理
- 尾灯导光条为正式几何（真实厚度 8.5mm、真实曲率、内缩 16mm、无 emission）
- 材质/相机/灯光/色彩管理全部写入 master 并记录在 manifest
- 三种尺寸零削顶、无 alpha halo、无 floating geometry
- 6 项原计划修改被证明**没有必要**（§2），因此没有增加风险面

**仍建议人工确认两件事**，因为无法由数字判定：

1. 尾灯 OFF 状态下，新增导光条在 600px 尺度上的观感是否自然
   （`production_taillight.png` / `taillight_lightguide_test.png`）。
2. 生产 hero 相对上一轮 `CURRENT MAX QUALITY` 的整体观感是否达到冻结标准
   （`before_after_production.png`）。

## 11. 产物路径

全部在 `assets/checkpoints/model_a_production_master/`：

| 文件 | 内容 |
|---|---|
| `MODEL_A_PRODUCTION_MASTER.json` | **冻结清单**（几何版本、normal 策略、paint、glass、wheel、尾灯几何、相机、灯光、渲染与色彩管理） |
| `production_hero.png` | full 2200×1520 |
| `production_hero_600px.png` | 车宽 600px |
| `production_hero_horizon1to1.png` / `horizon_production.png` | 1920×480 实尺寸 / 1:1 裁切 |
| `production_taillight.png` | 尾灯特写 |
| `production_glass.png` | 玻璃/天窗特写 |
| `production_wheel.png` | 轮毂/轮胎特写 |
| `production_door.png` | 侧门反射特写 |
| `before_after_production.png` | CURRENT MAX QUALITY vs PRODUCTION FINAL |
| `detail_report.json` | detail 检查（floating geometry / 退化对象 / 包围盒） |

`assets/source/blender/model_a_production_master.blend` **不提交**（含第三方几何，
见 `assets/ATTRIBUTION.md`）；由 `tools/blender/build_production_master.py`
从 FBX + manifest 确定性重建。

## 12. 冻结规则

`MODEL_A_PRODUCTION_MASTER.json` 中的全部参数默认 **LOCKED**。

后续 Door_FL / Door_FR / Door_RL / Door_RR、frunk、trunk、brake、indicator、
headlight 资产**必须从同一个 master 派生**。

**禁止**为每个状态重新调整材质、相机或灯光 —— 否则状态切换会出现视觉跳变。

## 13. 渲染时间（Mac，CPU）

| 视图 | 设置 | 时间 |
|---|---|---|
| hero | 2200×1520，96 spp | 49.0 s |
| taillight / glass / wheel / door | 1100×760，64 spp | 15.4–16.6 s |

> Metal GPU 本轮仍不可用（显存不足），全部使用 CPU。

---

# 附录：Part 0 light-guide 修复结果（BLOCKED）

人工审核指出 `lightguide-v1` 的红色导光条穿出透镜、形成可见红杆。
本轮尝试了两种**几何证明式**的修复，两种都无法认证任何放置：

| 方法 | 结果 |
|---|---|
| 视差内外判定（ray parity） | **不适用** —— 四个尾灯对象（`rear_lights` / `rear_lightsl` / `rear_lightsr` / `light_breake`）是**开放壳体**，不是封闭体积，"内部"在数学上没有定义。所有候选都被判为外部。 |
| 5 方向外向遮挡测试 | **全部失败** —— 即使半径缩到 3.8mm、内缩加到 36mm，仍有顶点在至少一个外向方向上逃逸。 |

**处理**：把导光条从 production master **移除**。
「没有几何」严格优于「几何穿出」。master 保留 outer lens、dark cavity、
reflector 三层，OFF 状态仍有内部深度。

验证渲染：`taillight_fixed_closeup.png` / `taillight_fixed_600px.png`，
红色主导像素 18,880（占车体像素 2.65%），包围盒 (296,268)–(699,386)，
为一个紧凑区域，**没有横跨画面的细长红杆**。

**最小修复方案（二选一，尚未实施）**：

1. 先建**封闭的内腔体**（用镜片壳体边界环 loft 出一个闭合体积），
   之后现有的视差判定才成立，导光条即可带证明地放置。
2. 改用**渲染验证**：导光条单独用 emission 材质渲染、镜片与车身做 holdout，
   要求所有导光条像素都落在镜片的屏幕空间轮廓内。这测的是真正的缺陷
   （可见性），而不是几何代理量。

**在其中一个方案实现并通过之前，不向 production master 加入导光条。**

`MODEL_A_PRODUCTION_MASTER.json` 中 `taillight_geometry.status`
已标记为 `BLOCKED_BY_SOURCE_GEOMETRY`。

---

# 附录 2：方案 1（封闭内腔体）实施结果

按人工选择实施方案 1。结果分两半：

## 做到的部分

**封闭内腔体本身成功了。** 对每个 lens shell 的顶点做凸包（convex hull
按构造就是闭合的），再向质心收缩：

| shrink | boundary edges | 结果 |
|---|---|---|
| 0.88 | **0** | watertight |
| 0.82 | **0** | watertight |
| 0.76 | **0** | watertight |
| 0.70 | **0** | watertight |
| 0.64 | **0** | watertight |
| 0.58 | **0** | watertight |
| 0.52 | **0** | watertight |

`boundary_edges = 0`、无非流形开口 —— 即"closed cavity"这一步是成立的。
这验证了方案 1 的前半段可行。

## 没有做到的部分：放置证明

**导光条的 containment 证明仍然失败。** 三轮迭代后定位到两个**具体**原因：

1. **`rear_lights` 横跨车尾两侧**（3,550 顶点覆盖整个后部）。
   用一个对象的质心 Y 符号去定义"外侧方向"是错的 —— 一半顶点必然在另一侧，
   无论怎么收缩都会被判为外露。**必须先按 Y 符号把灯对象拆成左右两份**，
   "outward" 才有定义。

2. **镜片是开放壳体。** 壳体内部的点总能从某个斜向经开口被"看到"，
   所以"要求所有方向都被遮挡"在数学上永远不成立。这不是放置错误，
   是**检验方法选错了**：应该用
   - **parity 判定**（对闭合腔体）证明 100% contained，以及
   - **screen-space QA**（渲染导光条为高亮、其余 holdout，要求所有可见
     导光条像素落在尾灯屏幕区域内部）证明不可见，
   而不是用一个方向性遮挡代理量去代替这两件事。

## 决定

**master 不加入导光条，也不加入腔体。** 没有几何优于未经证明的几何。
`MODEL_A_PRODUCTION_MASTER.json` 的 `taillight_geometry` 中新增
`cavity_attempt` 段，完整记录上述两个原因与下一步（**按左右拆分灯对象后
重跑**）。

## 为什么没有在通过前执行 Parts 1–22

人工指示"修复通过后不要停"。但 Step 12 的冻结条件是**六条同时满足**
（cavity closed / 100% containment / zero visible protrusion / zero body
intersection / zero trunk relationship error / OFF 600px acceptable）。
当前第 2 条与第 3 条**没有通过**。

而 brake、left indicator、right indicator **全部建立在同一套灯腔内部结构上**
（Step 8 明确要求"不要分别重建 brake geometry 和 indicator geometry"）。
在灯腔结构未冻结时先生成这三个状态，它们必然要在灯腔定案后全部重做；
人工在同一份指示中也写明"不要偷偷修改整个 Production Master 来解决局部状态问题"。

因此这属于指示中预留的例外：**"除非出现新的真正 BLOCKER —— 即无法通过
局部修复继续"**。当前 blocker 是灯对象的左右拆分，属于局部修复，但**尚未完成**，
所以在完成前不进入 Parts 1–22。
