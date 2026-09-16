# Vehicle Photoreal Material / Reflection Study（HDRI）

状态：**三个候选已产出，等待人工视觉选择。不要由实现方宣布 winner。**

基线 commit：`b51d578`。MODEL A 几何**未改**，Horizon **未改**，
door / delta pipeline **未改**，Open 0.62s / Close 0.54s **未改**。

本轮改的是**反射从哪里来**：

```
V3   人工 reflection cards  → 反射是几根完全笔直、完全均匀的条
本轮 real HDRI environment  → 反射来自真实拍摄的摄影棚，连续、不匀、方向正确
```

World 始终 `film_transparent = True`：HDRI 只塑造车，**不会**进入导出的 PNG。

---

## 1. HDRI 来源与许可（Part A）

| 项目 | 值 |
|---|---|
| 名称 | **Studio Kontrast 01**（本轮采用） |
| 作者 | Grzegorz Wronkowski |
| 来源 | https://polyhaven.com/a/studio_kontrast_01 |
| 下载 | `https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/2k/studio_kontrast_01_2k.hdr` |
| License | **CC0 1.0**（公共领域，可商用，无需署名） |
| 分辨率 | 2048×1024（渲染用 2k）；1024×512（1k，用于评估） |
| 获取日期 | 2026-09-16 |
| 本地路径 | `assets/source/hdri/studio_kontrast_01_2k.hdr`（git-ignored） |

### 1.1 为什么选它

对三个 CC0 暗棚候选做了逐像素统计（equirect 亮度分布）：

| 候选 | 平均 | 中位数 p50 | p99.9 | 峰值 | 最亮 1% 横向跨度 | 结论 |
|---|---|---|---|---|---|---|
| **studio_kontrast_01** | 0.724 | **0.237** | 63.7 | 129 | **22%** | **采用**：整体暗、光源集中在少数几个位置、中高度最亮 |
| brown_photostudio_02 | 0.719 | 0.284 | 44.6 | 87 | 100% | 光源横向铺满，反射会偏碎偏杂 |
| studio_small_03 | 1.871 | 0.012 | 124.1 | 3339 | 52% | 峰值 3339，会在车漆上打出无法控制的死白 |

判断依据是**光源的空间集中度**：车漆要读得出"这是几个柔光箱"，而不是"天上
到处是灯"。kontrast_01 的最亮 1% 只占 22% 宽度、且集中在中高度（相机高度），
这正好是车身侧面反射需要的位置。

淘汰的候选记录在此，避免下一轮重复评估。

### 1.2 明确没有使用

室外街道 / 森林 / 停车场 / 晴天风景类 HDRI 全部排除。

---

## 2. 三种 lighting setup（Part B）

三者**完全相同**的：geometry、camera（V2-A）、canvas（1100×760 ×2 = 2200×1520）、
engine（Cycles）、samples（96）、film transparent。

| | 反射来源 | 灯光 | 反射卡片 |
|---|---|---|---|
| **V3 CURRENT**（reference） | 9 张人工 reflection cards | V3 rig（key 520 W / rim 370 W / 暗侧补光 540 W / bounce 216 W / world 0.030） | 9 张，全部保留 |
| **HDRI ONLY** | HDRI world（strength 1.0） | 仅 1 盏大面积漫反射 bounce（92 W ×2.0） | **0 张** |
| **HDRI HYBRID** | HDRI world（strength 1.0）+ 少量造型光 | key 260 W（glossy）+ fill 90 W×2（diffuse-only）+ rim 150 W + bounce 46 W×2 | **0 张** |

HDRI ONLY 仍然留了一盏极暗的漫反射 bounce。理由：如果没有它，车底与轮拱只
由 HDRI 地平线以下的部分照明，会直接压成死黑 —— 那是打光错误，不是风格。
它 `visible_glossy=False`，所以**不会**在车漆上留下任何新的高光。

HYBRID 遵守"最多 1 key + 1 fill + 1 rim"的上限。

---

## 3. 材质参数

### 3.1 Body paint（Part C）

V3 把 metallic 压到 0.80 来保住漫反射项，从而让暗面不黑 —— 那是**绕过**问题，
不是解决。有真实环境之后车永远有东西可反射，所以本轮回到真正的多层车漆：

| 层 | silver_photoreal | silver_photoreal_cool |
|---|---|---|
| Base Color（金属层 F0） | 0.585 / 0.600 / 0.622 | 0.520 / 0.545 / 0.585 |
| **Metallic** | **0.94** | **0.96** |
| Roughness（金属层） | 0.215 | 0.235 |
| **Coat Weight** | **1.0** | **1.0** |
| Coat Roughness | 0.038 | 0.034 |
| IOR | 1.50 | 1.50 |
| flake bump | strength 0.055, scale 190, dist 0.0005 | 0.05 / 210 / 0.0005 |
| roughness 变化 | noise scale 3.5 → ramp 0.95–1.06 × roughness | 同 |

结构上的关键：**clearcoat 在金属之上**。锐利的摄影棚反射来自 coat，
车身色彩深度来自下面的金属层 —— 这个分离才是"漆"，而不是"上色的塑料"。
flake 强度 0.055（V3 是 0.10 ×0.08 的等效），只够让 coat 高光不像镜子。

禁止项全部遵守：没有 chrome、没有 mirror、没有 glitter、没有 pearl。

### 3.2 Glass（Part D）

不再是"深色 base + transmission"。现在是介质 BSDF，靠 Fresnel/IOR 与环境：

| | base（tint） | rough | transmission | specular | IOR |
|---|---|---|---|---|---|
| 全景天窗 `M_Glass_Roof_Photoreal` | 0.020/0.024/0.031 | 0.020 | 0.20 | 0.90 | 1.52 |
| 侧窗 `M_Glass_Side_Photoreal` | 0.026/0.031/0.040 | 0.028 | 0.34 | 0.86 | 1.52 |
| 后窗 `M_Glass_Rear_Photoreal` | 0.022/0.027/0.035 | 0.024 | 0.28 | 0.88 | 1.52 |

正视角深、掠射角反射增强是介质 BSDF 自带的 Fresnel 行为，不是画上去的渐变。
transmission 刻意压低（0.20–0.34），因为真车玻璃是有色玻璃：你看到的主要是
它**反射**的环境，只有少量是它后面的东西。内饰因此保持低调。

### 3.3 Wheel / Tire / Brake（Part E）

| | base | metallic | rough | 其他 |
|---|---|---|---|---|
| 轮毂 `M_Wheel_Machined_Photoreal` | 0.135/0.142/0.155 | 0.95 | 0.255 | coat 0.20 / coat rough 0.12 / **anisotropic 0.45** / specular 0.55 |
| 轮胎 `M_Tire_Rubber_Photoreal` | 0.022/0.022/0.024 | 0.0 | **0.92** | specular **0.28** |
| 刹车盘 `M_Brake_Disc_Photoreal` | 0.240/0.242/0.248 | 1.0 | 0.42 | **anisotropic 0.30**（径向拉丝） |
| 卡钳 `M_Brake_Caliper_Photoreal` | 0.045/0.046/0.050 | 0.55 | 0.46 | — |

轮毂的关键是 **anisotropic 0.45**：加工面不同法线方向因此产生不同长度的高光，
而不是一整块 dark grey。轮胎 specular 0.28 —— 足够低所以不像塑料，
但不为 0，掠射角那一点微弱光泽正是避免 black crush 的东西。

### 3.4 Taillight / Headlight OFF（Part F）

尾灯不再是一个红色表面。几何没动，深度靠**三层材质**建立：

| 层 | 材质 | 参数 | 作用 |
|---|---|---|---|
| outer lens | `M_Lens_Red_Photoreal` | base 0.190/0.020/0.020，rough 0.035，**transmission 0.30**，specular 0.92 | 透光，所以后面的腔体看得见 |
| 内部腔体 | `M_Lamp_Cavity_Photoreal` | base 0.012/0.012/0.014，rough 0.62，specular 0.30 | 它才是"镜片后面有东西"的来源 |
| 反射碗 | `M_Reflector_Photoreal` | base 0.560/0.575/0.600，metallic 1.0，rough 0.085 | 内部结构感 |

头灯透镜 `M_Lens_Clear_Photoreal`：transmission 0.55、specular 0.95、
rough 0.025。全部 **无 emission**。

---

## 4. Color management 与削顶（Part G）

V3 阶段已经查明：这个 Blender 构建的 `view_settings.look` 只有 `None`，
view-settings 的 CurveMapping 不可用（改白点无效）。所以只使用实测有效的
曝光与 gamma，**不用 gamma 去把车"调亮"**（gamma 保持 1.0）。

### 4.1 发现：HDRI 会把车漆打到死白

HDRI 里有极强的摄影棚灯。无论曝光降到 −0.45 EV，仍有 0.12% 像素停在 255 ——
因为那是光源的镜面像，降低整体曝光只会同时压死暗部。

解决办法不是降亮度，而是 **Cycles 光源钳制**（保留整体能量，只限制峰值）：

| clamp_indirect | max | ≥250 占比 | std |
|---|---|---|---|
| 2.0 | 233 | 0.000% | 62.9 |
| **4.0（采用）** | **242** | **0.000%** | **65.0** |
| 8.0 | 251 | 0.060% | 66.4 |

### 4.2 发现：下采样会**制造**削顶

把 2200×1520 的渲染缩成 600px 车宽时，直接对非预乘 RGBA 做 LANCZOS，
会在轮廓边缘产生源图里**不存在**的 255 像素（V3 源图 max 226，缩完却出现 255）。

修正：**预乘 alpha 后在 float32 通道上缩放**，并把结果钳制到源峰值。

| 做法 | 600px 资产中 ≥250 的像素 |
|---|---|
| 直接缩放（原做法） | 77 / 70 / 84（V3 / HDRI / HYBRID） |
| 预乘但量化成 8bit | 1119 / 1280 / 1288（更糟：除以小 alpha 放大舍入误差） |
| **预乘 + float32 通道 + 钳制到源峰值** | **0 / 0 / 0** |

这条现在是流水线规则：**下采样不得引入比源图更亮的值**。

---

## 5. 三种尺寸检查（Part H）

只在 Blender 大图上判断材质是错的。每个候选都在三个尺寸下产出：

| 尺寸 | 做法 | 用途 |
|---|---|---|
| full | 2200×1520 渲染 → 1100×760 | 看材质本身 |
| **600px** | 整帧缩放到**车宽 600 px** | 仪表上车辆的真实尺寸；用的就是发布资产的下采样路径 |
| **Horizon 1:1** | 真实 1920×480 composite 里裁 900×480，**不重采样** | 看真实像素 |

Horizon composite 使用既有 `scenes/horizon_v1.scene` 与既有 framing
（`864x597@582,-93`），与之前的 V2/V3 预览可直接对比。**Horizon 本轮未改。**

---

## 6. 数值结果（Part 11-12）

> 这些数字**只**用于证明"没有削顶、没有死黑、反射结构确实更丰富"。
> **不用于宣布哪个更好看。**

### 6.1 2200×1520 全渲染

| 指标 | V3 CURRENT | HDRI ONLY | HDRI HYBRID |
|---|---|---|---|
| mean | 105.5 | 97.7 | 108.3 |
| **std（反射结构丰富度）** | **53.1** | **60.9** | **64.0** |
| p1 / p5 | 14 / 33 | 8 / 32 | 9 / 33 |
| p25 / p50 | 59 / 105 | 43 / 79 | 50 / 88 |
| p75 / p95 / p99 | 143 / 196 / 217 | 145 / 229 / 238 | 160 / 231 / 239 |
| 最亮像素 | 226 | 243 | 246 |
| **≥250 削顶** | **0** | **0** | **0** |
| dark<8（死黑） | 0.46% | 0.99% | 0.87% |
| 渲染时间（M4 / Cycles / 96 spp） | 24.9 s | 24.2 s | 38.4 s |

### 6.2 车顶区域（针对"大片均匀灰白"这条意见）

| | 车顶带 mean | **车顶带 std** |
|---|---|---|
| V3 CURRENT | 138.7 | **58.3** |
| HDRI ONLY | 146.1 | **79.7** |
| HDRI HYBRID | 155.2 | **80.0** |

车顶反射的明暗变化幅度提高约 **37%**。卡片是几根笔直的条，所以车顶一定是
平滑渐变；真实摄影棚会给出多个不同方向、不同强度的光源，统计上表现为
同样亮度下大得多的方差。

### 6.3 600px（车宽）与 Horizon 实尺寸

| | 600px mean/std | Horizon 1:1 车区 mean/std |
|---|---|---|
| V3 CURRENT | 104.7 / 52.9 | 75.6 / 60.4 |
| HDRI ONLY | 97.0 / 60.3 | 70.1 / 61.7 |
| HDRI HYBRID | 107.5 / 63.5 | 77.2 / 67.0 |

反射结构的差异在缩小到 600px 之后**依然存在**（52.9 → 60.3/63.5），
说明它不是大图才看得见的细节。三个尺寸下都 **≥250 削顶 = 0**。

---

## 7. 产物

| 文件 | 内容 |
|---|---|
| `vehicle_material_photoreal_comparison.png` | Part I：3 列（V3 / HDRI ONLY / HYBRID）× 2 行（full crop / Horizon 实尺寸） |
| `vehicle_material_sizecheck_600px.png` | Part H 追加：车宽 600px 检查 |
| `checks/<v>_full.png` | 全图 |
| `checks/<v>_600px.png` | 车宽 600px |
| `checks/<v>_horizon.png` | 1920×480 实尺寸 1:1 裁切 |
| `checks/horizon_photoreal_<v>.png` | 完整 1920×480 Horizon composite |

复现：

```bash
for L in v3 hdri hybrid; do
  /Applications/Blender.app/Contents/MacOS/Blender -b \
    -P tools/blender/render_vehicle_photoreal.py -- \
    --lighting $L --engine cycles --samples 96 \
    $([ $L = v3 ] && echo --exposure 0.30 || echo --exposure 0.10 --fill-scale 2.0) \
    --out assets/rendered/photoreal/${L}_silver.png
done
python3 tools/assets/build_photoreal_comparison.py
```

## 8. 仍未确定 / 需要真机验证

- 三个候选哪一个视觉最好 —— **由人工审核决定，本轮不做选择**。
- 面板实际 gamma / 亮度：本轮亮度判断在 Mac 上完成，梯形屏观感可能不同。
- HDRI 反射与 Horizon 背景的相互作用（背景是很暗的渐变，车漆反射的是摄影棚，
  两者亮度关系只在真机上才能最终确认）。
- Cycles 渲染时间只影响离线生产，与 T113 无关。
- 本轮的 vehicle PNG 尚未接入 delta 管线重新导出（结论确定后再做）。
