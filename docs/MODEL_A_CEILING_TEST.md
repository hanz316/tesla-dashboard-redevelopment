# MODEL A Quality Ceiling Test

状态：**测试完成，等待人工审核。本文件不宣布 production master。**

基线：`ce3be2e` + `6f5c283`。MODEL A 几何、Horizon、动画管线**均未修改**；
所有实验对象与 remesh 都只存在于内存中。

---

## 1. 一句话结论

**MODEL A 的上限不在反射平滑度上，而在细节上。**

- 把门板的拓扑换成 19 倍面数的规则网格，反射**变差**（waviness 1.671 →
  3.578），把体素从 4mm 加密到 2.5mm（面数 249k → 679k）**没有任何改善**。
  → **topology 不是天花板。**
- 逐 panel 的 normal 策略确实有效，但不是全车统一的：9 个 panel 里
  3 个应该 WEIGHTED、2 个 CLEAN、**4 个应该保持 ORIGINAL**。
- 唯一被证明**缺几何**的地方是尾灯（没有导光条）。
- MODEL B 视觉更亮更平，但**只有 1 个 mesh 对象**，没有任何可分离的门/盖，
  动画结构为零。

---

## 2. Part A — 逐 panel normal 策略

`panel_normal_policy.json`。三种处理：ORIGINAL / CLEAN（清 custom normals +
焊接 + recalc + smooth）/ WEIGHTED（CLEAN + Weighted Normal keep_sharp）。

每个 panel 取它投影面积最大的视角，记录四个互相独立的信号，**不由单一数字决定**：

| panel | 视角 | 判定 | 依据 |
|---|---|---|---|
| **door_lf** | rear_quarter | **WEIGHTED** | waviness 3.849 → 2.777，breaks 41 → 38，crease 2.082 → 2.052 |
| **door_rf** | rear_quarter | **CLEAN** | waviness 9.415 → 7.887 |
| door_lr | rear_quarter | **KEEP_ORIGINAL** | 两种处理都更差（clean 28.8 / weighted 23.2 vs original 23.0） |
| door_rr | rear_quarter | **KEEP_ORIGINAL** | 两种处理都更差（clean 17.0 / weighted 19.6 vs original 16.1） |
| **bonnet_ok** | roof | **WEIGHTED** | waviness 3.166 → 1.796 |
| boot | roof | **KEEP_ORIGINAL** | 都更差（clean 3.26 / weighted 2.81 vs original 2.75） |
| **front_bumper_ok** | roof | **CLEAN** | waviness 8.083 → 6.309 |
| rear_bumper_ok | roof | **KEEP_ORIGINAL** | original 已最好 |
| **body** | roof | **WEIGHTED** | waviness 7.696 → 3.405，breaks 123 → 122，crease 2.313 → 2.221 |

**保留 original 的 panel：door_lr、door_rr、boot、rear_bumper_ok。**
这与上一轮的发现一致（rear quarter 全局修复后反而变差 4.356 → 5.141）：
**全车统一修复是错的。**

判定用的是四个条件同时成立：waviness 必须下降 ≥15%、breaks 不能恶化
（≤1.25×+2）、highlight 变形（p95 脊线厚度/中位）不能恶化、crease 能量
不能低于原始的 85%。原始数据全部写在 JSON 里，可以人工推翻。

图：`panel_normal_policy.png`（3 处理 × 4 视角）

---

## 3. Part B — Source mesh quality ceiling

`mesh_quality_ceiling_report.json`。**关键：统计同时给出整对象与"外板本体"
（最大连通岛）两套数字**，因为整对象里混着大量内部小件，会污染统计
（body 有 281 个连通岛，boot 101 个，门 69–96 个）。

| panel | 全对象 dihedral p95 | **外板 dihedral p95** | 外板 aspect p95 | 薄三角% | max/median | 密度/m² | 岛屿 | 外板占比 | 分类 |
|---|---|---|---|---|---|---|---|---|---|
| door_lf | 40.76° | **18.06°** | 67.67 | 32.0 | 1406.3 | 3963 | 96 | 20.6% | FIXABLE_BY_LOCAL_REMESH |
| door_rf | 39.34° | **17.92°** | 67.74 | 33.3 | 1125.2 | 3595 | 76 | 22.7% | 同 |
| door_lr | 37.68° | 19.48° | 26.95 | 30.3 | 27.3 | 4280 | 70 | 24.2% | 同 |
| door_rr | 37.69° | 19.86° | 27.05 | 30.3 | 27.2 | 4280 | 69 | 24.3% | 同 |
| bonnet_ok | 25.56° | 25.56° | 41.24 | 38.2 | 8.3 | 1785 | 28 | 99.1% | 同 |
| boot | 25.64° | 26.87° | 33.41 | 35.0 | 13.7 | 5088 | 101 | 72.5% | 同 |
| body | 25.46° | 24.27° | 29.04 | 35.8 | 14.3 | 7596 | 281 | 20.6% | 同 |
| front_bumper_ok | 20.70° | 20.71° | 31.70 | 29.0 | 15.2 | 6904 | 109 | 99.1% | 同 |
| rear_bumper_ok | 20.98° | 20.99° | 38.63 | 31.4 | 10.8 | 6680 | 106 | 99.2% | 同 |

**最大问题**：在**应当是光滑曲面**的区域，相邻三角形法线差的中位数只有
0.27–0.97°，但 p95 达 **18–27°**。也就是说绝大多数面是平滑的，只有约 5%
的边存在 18–27° 的折角 —— 这是三角化与法线不一致造成的几何缺陷，
不是造型。加上 29–38% 的薄三角形（aspect > 8），最大值/中位面积比最高 1406×。

分类全部落在 **FIXABLE_BY_LOCAL_REMESH**（密度足够，形状正确，只是不规则），
**没有一个 panel 落到 SOURCE_MODEL_LIMITATION** —— 但这个结论被 Part C 直接否定了
（见下），说明这个分类规则本身过于乐观。

---

## 4. Part C — Local remesh 实验（最重要的否定结果）

对 **door_lf** 做体素 remesh（内存中，作为 retopology 代理），严格检查轮廓偏差：

| | 面数 | 轮廓偏差（中位 / p95 / max） | 反射 waviness |
|---|---|---|---|
| CURRENT | 34,961 | — | **1.671** |
| NORMAL FIX | 34,961 | — | 1.668 |
| **LOCAL REMESH 4mm** | **249,522** | 1.8mm / 10mm / 52mm | **3.578** |
| **LOCAL REMESH 2.5mm** | **679,472** | 1.15mm / 9.6mm / 51mm | **3.597** |

**结论：local remesh 让反射明显变差，而且加密体素没有任何改善。**

这是一条明确且反直觉的答案：

- 面数增加 19 倍、体素加密 2.7 倍，两者结果几乎相同（3.578 vs 3.597），
  说明**不是"面不够多"，而是规则网格在微尺度上比原本手工建的面更不平**。
- 轮廓中位偏差 1.2–1.8mm 已经很小，所以这不是"形状变了所以变差"。

**→ topology 不是 MODEL A 的反射质量天花板。继续做 retopology 收益为负。**

图：`local_remesh_test.png`

---

## 5. Part D/E — Reference automotive paint

结构上完全不同（不再是一个 Principled 改滑块）：

```
Glossy BSDF (clearcoat, rough 0.018)  ─┐
                                       ├─ Mix Shader ← Layer Weight/Fresnel ×0.62 + 0.42
Principled BSDF (metallic 1.0, rough 0.34) ─┘
        ↑ Voronoi bump (scale 260, strength 0.16)
        ↑ Noise → roughness 变化 (scale 2.6, ±10%)
```

两个关键设计：

1. **flake 加在 basecoat 上，而不是 clearcoat 上。** 真车漆的铝粉在清漆**下面**，
   所以它扰动的是宽的 basecoat lobe，而锐利的 clearcoat 反射保持完整。
   上一个版本把二者混在一个 Principled 里，所以 4 个候选看起来差不多。
2. **两个 lobe 由两个不同的 BSDF 产生**，空间尺度天然不同：
   coat rough 0.018（极锐）vs basecoat rough 0.34（很宽），相差 **19 倍**。

图：`paint_reference_comparison.png`

## 6. Part F — Reference glass

`Principled 介电层 + 独立 Glossy 涂层`，由 coat 权重混合：

| pane | tint | roughness | transmission | IOR | coat |
|---|---|---|---|---|---|
| roof | 0.012/0.016/0.024 | **0.010** | 0.10 | 1.545 | **0.85** |
| front | 0.018/0.022/0.030 | 0.016 | 0.22 | 1.525 | 0.55 |
| side | 0.022/0.027/0.036 | 0.020 | 0.30 | 1.520 | 0.40 |
| rear | 0.017/0.021/0.029 | 0.018 | 0.25 | 1.522 | 0.48 |

涂层是"深色车玻璃"与"黑色亚克力"的区别：它在介电层之上加了一层受控的
镜面反射，让玻璃即使在天窗这种几乎不透光的配置下也保有 Fresnel 边缘和
低粗糙度环境反射。

图：`glass_reference_comparison.png`

## 7. Part G — 尾灯 light guide 实验

| | 内容 |
|---|---|
| CURRENT | 现有材质 |
| REFERENCE MATERIALS, NO LIGHT GUIDE | 参考材质，不加几何 |
| **+ TEMP LIGHT GUIDE GEOMETRY** | 在 4 个尾灯对象内部各加一条胶囊状导光条（临时，非 production） |

导光条材质：base 0.420/0.030/0.032、metallic 0.35、roughness 0.18、
specular 0.75、**无 emission**（关闭状态）。

图：`taillight_lightguide_test.png` —— 三格可以直接比较"材质能到哪里"与
"几何补上之后到哪里"。**TAILLIGHT REQUIRES GEOMETRY UPGRADE** 这个判断由
这三格的视觉差异支持，但最终判断权在人工。

## 8. Part H — AO / contact shadow

做法：把全部材质换成 0.82 漫反射白、world 换成均匀白光，渲染结果就是
**几何自身的 AO 图**（`ao_contact_shadow.png`）。这不是假阴影，而是
检查模型是否在缝隙/轮拱/门把手/灯壳处**有足够的腔体深度**让 Cycles 自然
产生接触阴影。

本轮**没有**添加任何假的阴影贴图，也没有把 panel gap 画成黑线。

## 9. Part I — Hero render

`hero.png`：per-panel normal 策略 + reference paint + reference glass +
临时导光条 + 现有最佳轮毂 + Photo Studio 01 + Cycles 96 spp +
2200×1520（1100×760 ×2 超采样）。

| 尺寸 | 文件 |
|---|---|
| FULL RES | `hero.png` |
| **600px 车宽** | `hero_600px.png` |
| Horizon 实尺寸 | `hero_horizon1to1.png` / `horizon_hero.png` |

统计：mean 152.9、std 48.6、p95 205、**削顶 0**。

图：`hero_max_quality.png`（三种尺寸并排）

## 10. Part J — MODEL A vs MODEL B

同一相机族（V2-A）、同一 Photo Studio 01、同一 hybrid rig、同一曝光，
MODEL B 统一使用一种中性银（**故意不用我们的材质管线**，因为比较的是模型
不是我们的 shader）。MODEL B 原本朝向差 90°，已按 MODEL A 的方式归一化。

| | MODEL A | MODEL B |
|---|---|---|
| mesh 对象数 | **107** | **1**（`Full Car Extra`） |
| 顶点 / 三角形 | 28,401 / 47,288（body） | 134,283 / 126,258（全车一个网格） |
| 连通岛 | 281（body） | 305 |
| 非流形边 | 9,720（body） | 20,773 |
| dihedral 中位 / p95 | **0.27–0.97° / 20–41°** | **6.60° / 53.86°** |
| aspect p95 / 薄三角 | 27–67 / 29–38% | 26.0 / 21.0% |
| 600px 画面 | mean 136.7 std 49.9 | mean **166.6** std **34.5** |

**VISUAL QUALITY**：MODEL B 更亮、更平（std 34.5 vs 49.9），dihedral 中位数
是 MODEL A 的 7–24 倍（更粗糙），但它是单一网格、没有分件，
量化比较到此为止 —— 哪个更好看必须由人眼判断。

**ANIMATION STRUCTURE**：**MODEL B 完全不具备。** 只有一个对象，
没有可分离的门、前备箱、后备箱，也没有可分离的玻璃/轮毂/尾灯。
即使 MODEL B 视觉更好，也不能直接替代 MODEL A。

图：`model_a_vs_model_b.png`

## 11. Part K — Decision matrix

`decision_matrix.json`（只有事实，没有总分、没有 winner）：

| 维度 | MODEL A CURRENT | MODEL A CLEANED | MODEL A LOCAL REMESH | MODEL B |
|---|---|---|---|---|
| surface quality | 100% 三角化；skin dihedral p95 18–27° | 几何不变 | 规则网格，反射更差 | dihedral 中位 6.6°（更糙） |
| normal quality | 全部带 custom split normals | 已清理 + weighted | 已清理 + weighted | 单一网格，无法分件控制 |
| topology quality | max/median 最高 1406× | 不变 | 面数 ×19，**无收益** | aspect p95 26，薄三角 21% |
| panel separation | **有**（门/盖/保险杠独立） | 保留折痕 | 保留 | **无** |
| door animation | **READY**（4 门验证过铰链） | READY | READY | **NO** |
| frunk / trunk | READY / READY | READY | READY | **NO / NO** |
| taillight detail | 有透镜+反射碗，**无导光条** | 同 | 同 | 无法分离 |
| wheel / glass | 独立对象 | 同 | 同 | 无法分离 |
| 600px visual | mean 136.7 std 49.9 | mean 136.8 std 49.9 | 更差 | mean 166.6 std 34.5 |
| 估算 cleanup | 2 类 | — | 不推荐 | 不适用 |

## 12. 是否存在明确的 source-model ceiling

**存在，但不在大家以为的地方。**

- **不是**反射平滑度的天花板 —— Part C 用 19 倍面数证明了 retopology 收益为负。
- **是**细节的天花板：外板 100% 三角化、面积比最高 1406×、
  尾灯**根本没有导光条几何**。这些是"模型里没有的东西"，材质补不出来。
- 分件结构、门/盖动画、normal 驱动的明暗**都完好且可修**。

## 13. 如果继续 MODEL A，需要多少类 cleanup

**两类，都不是 retopology：**

1. **A1 — normal 策略（已实现，可逆）**：按 `panel_normal_policy.json`
   逐 panel 应用。9 个 panel 中 3 个 WEIGHTED、2 个 CLEAN、4 个保持原样。
2. **A2 — 尾灯几何升级**：加入内部导光条与腔体结构。这是唯一被
   **证明**缺几何的地方，也是本轮唯一需要动 geometry 的工作。

**不包含**：全车 remesh / retopology / subdivision（Part C 已证明收益为负）。

## 14. 渲染时间（Mac，CPU）

| 批次 | 单张 |
|---|---|
| 逐 panel 反射检测（900×620，32 spp）× 12 | 8.7–22.8 s |
| local remesh 对比（1100×760，48 spp）× 4 | 12.5–15.0 s |
| reference paint / glass / light guide / AO（1100×760，48 spp） | 8.5–19.5 s |
| MODEL B（1100×760，48 spp） | 7.0 s |
| **HERO（2200×1520，96 spp）** | **77.9 s** |

> Metal GPU 本轮再次显存不足，全部渲染使用 CPU。

## 15. 未做的事

没有开始 Door_FR/RL/RR、Frunk、Trunk、Indicator；没有重新设计 Horizon；
没有继续搜索 HDRI；没有修改 MODEL A 的源文件或 master `.blend`。
