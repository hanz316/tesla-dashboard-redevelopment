# Vehicle Visual V3 — controlled premium HMI shading

状态：**已产出，等待人工视觉审批**。MODEL A 几何**未做任何改动**。

基线 commit：`2f103e3`（V2）。本轮只改 shading / reflection / light rig /
colour management。

| 项目 | 值 |
|---|---|
| 引擎 | Cycles，Metal GPU |
| 采样 | 96 + 自适应 + 降噪 |
| 分辨率 | 2200×1520（1100×760 ×2），RGBA 透明 |
| 相机 | 与 V2 **完全相同**（V2-A，az −32°，el 22°，ortho 4.25） |
| 材质/灯光模块 | `tools/blender/hmi_studio_v3.py` |
| 渲染脚本 | `tools/blender/render_vehicle_visual_v3.py` |

> 相机、分辨率、超采样、几何全部与 V2 一致。所以两张图之间的任何差别都
> **只**来自 shading —— 这是让对比有意义的前提。

---

## 1. 对 V2 八条意见的处理（Part 2 → Parts 3-9）

| # | V2 的问题 | V3 的处理 |
|---|---|---|
| 1 | roof/trunk 柔光箱反射太大、太白、太均匀 | 大柔光箱拆成 **长窄 strip**；所有卡片改为 off-white/中性灰 |
| 2 | 暗侧过黑 | 新增**只走漫反射**的大面积补光（`visible_glossy=False`） |
| 3 | 暗侧车门/车身轮廓丢失 | 同上 + 侧向渐变卡（很暗的 tall card） |
| 4 | 轮拱/前轮融进背景 | 专用 `Wheel_Strip`（刻意的低强度）+ 石墨轮毂底色抬升 |
| 5 | 银色本体存在感不足 | **metallic 0.90 → 0.80**，base color 抬到 0.585（见 §2） |
| 6 | 反射对比过强 | 卡片更窄 + 强度全面下调 |
| 7 | 玻璃接近黑洞 | 微弱 transmission + fresnel 渐变写入 base color |
| 8 | 尾灯 OFF 灯壳缺 lens depth | 透镜透射/高光提高 + 反射碗改暗铬 |

### 1.1 最重要的一条：为什么 V2 暗侧是黑的

这不是"灯不够亮"，是**物理模型选错了**。V2 的 `metallic = 0.90`：
在 Principled BSDF 里，metallic=1.0 的表面**没有漫反射项**，它的颜色
100% 来自反射。一个 0.9 metallic 的车漆在没有东西可反射的方向上，
渲染出来就是黑的 —— 无论再加多少 fill light，只要那些灯不在镜面反射方向上，
它对 metallic 表面的贡献都接近零。

V3 把 metallic 降到 **0.80**（brighter 预设 0.74），base color 抬到
0.585，于是材质重新获得漫反射项：没被高光照到的面板仍然是"暗银"，
而不是"黑塑料"。**这是本轮真正的修复**，其余都是配合。

---

## 2. 车漆 V3（Part 6）

| 参数 | V2 silver01 | V3 silver_v3 |
|---|---|---|
| base color | 0.560/0.572/0.585 | **0.585/0.600/0.620** |
| metallic | 0.90 | **0.80** |
| roughness | 0.30 | 0.255 |
| coat | 0.70 | 0.50 |
| coat roughness | 0.055 | 0.060 |
| flake bump | strength ×0.08, dist 0.0007 | **×0.06, dist 0.0006** |
| roughness noise | scale 7, ramp 0.88–1.10 | **scale 5, ramp 0.93–1.05** |

flake 与 roughness 变化都**减弱**了：V2 那点"CG studio model 感"有一部分
正是来自过强的微表面扰动。仍然没有 glitter / sparkle。

---

## 3. 反射摄影棚 V3（Part 3）

V2 = 6 张卡片，最大的一张是 14 m 的 `Ceiling_Softbox`，颜色接近纯白。
V3 = **9 张**，全部 off-white（`0.560` 灰）或更暗的 fill 灰（`0.430`）：

| 卡片 | 尺寸（m） | 强度 | 作用 |
|---|---|---|---|
| `Roof_Strip_L` | 9.0 × 0.55 | 1.55 | 车顶细长高光（取代大柔光箱） |
| `Roof_Strip_R` | 8.0 × 0.45 | 1.15 | 车顶第二条，形成**双条**而非一整块白 |
| `Shoulder_Strip` | 7.5 × 0.32 | 1.90 | 腰线/shoulder line |
| `Side_Gradient` | 8.5 × 3.6 | 0.42 | 很暗的侧向渐变，取代"一块高光 + 一片黑" |
| `Rear_Quarter_A` | 3.4 × 0.45 | 1.35 | rear quarter 曲线高光 |
| `Rear_Quarter_B` | 2.6 × 0.40 | 0.95 | 与 A 不同角度，近似曲面高光 |
| `Trunk_Fill` | 4.6 × 1.8 | 0.55 | 行李箱盖保持银色，不做成白色 |
| `Wheel_Strip` | 5.4 × 0.55 | 0.62 | 只负责轮圈与背景分离 |
| `Lens_Strip` | 4.2 × 0.28 | 0.70 | OFF 灯罩上的一条高光 |

"曲面高光"用两张不同角度的短卡近似 —— 单张平板卡在几何上不可能产生
沿着 quarter panel 弯曲的高光。

### 3.1 量化效果：反射的"白"被压掉了

| 指标 | V2 | V3 normal | V3 soft |
|---|---|---|---|
| 车身像素中 >200 的占比 | **15.93%** | **4.05%** | 7.98% |
| p95 | 215 | 196 | 207 |
| 最亮像素 | 233 | 226 | 231 |
| 平均亮度 | 135.5 | 105.5 | 125.1 |

>200 的像素从 16% 降到 4% —— 这是"太白的反射"这条意见的直接量化。

---

## 4. 暗侧恢复（Part 4）

两盏**只参与漫反射**的补光（`visible_glossy = False`），所以它们能抬
shadow floor 但**不可能**产生新的镜面高光：

| 灯 | 位置 | 能量 | 尺寸 |
|---|---|---|---|
| `HMI_Ambient_DarkSide` | (−1.6, 6.8, 2.6) | 540 W | 14 m |
| `HMI_Ambient_Bounce` | (−0.5, 3.2, 0.30) | 216 W | 12 m |

世界环境底色从 0.020 抬到 0.030（整体 shadow floor，不足以把车照平）。

调参过程（同一相机、24 采样，只看暗部）：

| ambient scale | mean | p1 | p5 | p95 | >200 |
|---|---|---|---|---|---|
| 1.0（旧） | 95.9 | 9 | 23 | 195 | 3.73% |
| 1.6 | 103.2 | 14 | 30 | 195 | 3.77% |
| **1.8（采用）** | **106.1** | **16** | **33** | **195** | 3.80% |
| 2.3 | 110.1 | 19 | 35 | 195 | 3.81% |

采用 1.8 而不是 2.3：暗部继续抬的同时 p95 完全不变（195），说明没有把车照平；
再往上加只是整体变亮，不再改善轮廓可读性。

---

## 5. 玻璃 V3（Part 7）

`LayerWeight(Facing)` → `ColorRamp` → Base Color，给出**不依赖环境反射**的
曲面渐变，所以即使没有 strip 打上去，玻璃也能读出弧面与边界：

| | base 内侧 | base 边缘 | rough | transmission | specular |
|---|---|---|---|---|---|
| 天窗 `M_RoofGlass_HMI_V3` | 0.019/0.023/0.030 | 0.085/0.098/0.120 | 0.030 | 0.24 | 0.80 |
| 侧窗 `M_WindowGlass_HMI_V3` | 0.024/0.029/0.037 | 0.100/0.112/0.135 | 0.042 | 0.36 | 0.74 |

仍然很深（base < 0.04），但 transmission 比 V2 高（0.16→0.24 / 0.28→0.36），
避免"完全黑死"。内饰仍然只是**很轻**可见。

---

## 6. 轮圈（Part 8）与灯壳（Part 9）

轮圈：`M_Wheel_Graphite_V3` base 0.115（V2 0.085）、metallic 0.84、rough 0.285、
coat 0.30、specular 0.62 —— 抬到能与背景分离，但远不到银白。配合
`Wheel_Strip`，前轮不再融进背景。

灯壳：透镜 specular 0.80→0.88（clear）/ 0.86（red）、roughness 0.045→0.030、
transmission 0.34→0.42；反射碗 `M_Reflector_Dark_V3` metallic 1.0 / rough 0.115。
**完全没有 emission**，但 OFF 灯壳有透镜深度与内部反射碗的观感。

---

## 7. Filmic / AgX / 曝光（Part 5）

Blender 5.2.2 的 `view_settings.look` 在这个构建里**只暴露 `None`**，
没有任何 AgX look 变体。View-settings 的 CurveMapping 也实测**不可用** ——
把它的白色控制点从 0.94 改到 0.60，渲染结果**逐位相同**（只有低端生效）。

所以 V3 的两种 look 只使用实测有效的两个显示参数：

| look | view transform | exposure | gamma | 说明 |
|---|---|---|---|---|
| **V3_Normal** | AgX | 0.30 | 1.00 | 基准 |
| **V3_SoftContrast** | AgX | 0.16 | 1.35 | 降曝光保护高光 + 抬 gamma 抬暗部 |

结果：

| 指标 | V3 normal | V3 soft |
|---|---|---|
| mean | 105.5 | 125.1 |
| std | 53.1 | 50.7 |
| p1 / p5 | 14 / 33 | **27 / 53** |
| p95 | 196 | 207 |
| 最亮像素 | 226 | 231 |
| ≥250 的像素 | 0.00% | **0.00%** |

两种 look **都没有削顶**。

---

## 8. V2 vs V3（Part 18）

对比图：`assets/rendered/v3/vehicle_visual_v3_comparison.png`
（V2 reference / V3_Normal / V3_SoftContrast，同相机同比例）

| 指标 | V2 reference | V3 normal | V3 soft |
|---|---|---|---|
| mean | 135.5 | 105.5 | 125.1 |
| std | 58.7 | 53.1 | 50.7 |
| p1 | 11 | 14 | 27 |
| p5 | 37 | 33 | 53 |
| p50 | 149 | 105 | 127 |
| p95 | 215 | 196 | 207 |
| 最亮 | 233 | 226 | 231 |
| >200 占比 | **15.93%** | **4.05%** | 7.98% |
| ≥250 占比 | 0.00% | 0.00% | 0.00% |

读法：V2 的 p50 是 149 —— 车身**一半以上的像素**亮于中灰，这就是"整块发白"
的来源。V3 normal 的 p50 降到 105，同时 p5 只从 37 降到 33，暗部没有变差。
换句话说：**减掉的是高光泛滥，不是暗部**（暗部由补光单独补了回来）。

---

## 9. Horizon 预览（Part 19）

没有重新设计 Horizon，只把 V3 车辆放进真实 UI 背景判断亮度：

- `assets/rendered/v3/horizon/horizon_vehicle_v3_normal.png`
- `assets/rendered/v3/horizon/horizon_vehicle_v3_soft.png`

| | 整帧平均 | 背景平均 | p99 |
|---|---|---|---|
| V2 放进 Horizon | 49.5 | 11.0 | 244 |
| V3 normal | 42.8 | 11.0 | 244 |
| V3 soft | 47.2 | 11.0 | 244 |

背景平均亮度 11.0，V3 normal 的车辆平均 105.5 —— 车比背景亮约 9.6 倍，
soft 约 11.4 倍。两者都能从背景里立起来；具体选哪个属于视觉判断，交给人工。

---

## 10. 仍未确认 / 需要人工判断

- **是否达到"premium"**：只有人眼能判断，数值只证明"没有再糊成一片白"。
- 暗侧恢复是**全局补光**，不是分区处理。如果实际观察发现某一处（例如后轮
  或车门下部）仍然读不出来，需要针对该区域再加一张定向卡，而不是整体提亮。
- `Side_Gradient`(0.42) 与 `Rear_Quarter_A/B` 是在 V2-A 相机下调的；
  换相机需要复调。
- 反射卡片强度是**离线渲染参数**，与真机无关；但车辆 PNG 的最终亮度在真实
  梯形屏上的观感仍未验证。

## 11. 生产美术规则

V3 **尚未**成为 production vehicle visual。旧 placeholder 与 V1/V2 资产
同样都不是。等人工批准后，V3 的这一版才成为正式车辆视觉。
