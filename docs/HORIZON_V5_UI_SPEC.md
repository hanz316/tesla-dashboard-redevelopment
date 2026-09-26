# HORIZON V5 / V5.1 - the approved reference, implemented, then made to drive

状态：`HORIZON_V5_NEUTRAL = AWAITING HUMAN VISUAL APPROVAL`

人工审核结论（本轮之前）：V5 的**方向**没有被否决，被否决的是"没有实现已批准的
reference"。旧截图里是

```
reference image = MISSING
background      = TEMPORARY
BACKGROUND_ART_REQUIRED
```

所以本轮只做一件事：把 `assets/ui/horizon_v5_reference.png` 真正实现出来。
本文与 `assets/ui/horizon_v5_layout.json`、`assets/ui/horizon_v5_tokens.json`
由同一份数据生成，文档不可能与场景不一致。

## 1. 从 reference 到坐标（唯一映射，只写一次）

reference 是 **2172x724（3:1）**，面板是 **1920x480（4:1）**。映射方式：

```
panel_x = 960 + (x_ref - 1086) * 480/724      # 1086 = reference 水平中心
panel_y = y_ref * 480/724
```

即：reference 按**高度 1:1** 放进一个居中的 **1440x480 内容盒**，多出来的左右各
240 px 是环境。这样每一个元素的**大小和相对位置都是 reference 的**，并且所有元素
都自然避开了面板的梯形遮罩（顶部切 116 px、底部切 51 px）。

`tools/assets/analyze_v5_reference.py` 输出测量值，同时画出
`assets/ui/horizon_v5_reference_annotation.png`，人可以把框和参考图直接对照。

| 量 | reference 测量 |
|---|---|
| canvas | 2172x724 |
| horizon row | 252（0.348 h）|
| vehicle silhouette | x 788..1380, y 194..486（592x292 亮漆；含深色轮胎/阴影的真实高度约 326）|
| 仪器弧 | 圆心 (241.4, 338.6)，半径 174.1，拟合 rms 1.6 px |
| energy rail | x 2020..2075, y 120..575 |
| accent | `#2496D8`（hue 148）|
| 三段平均亮度 | top 31.4 / middle 47.2 / bottom 11.1 |

映射到面板：

| 元素 | 面板坐标 |
|---|---|
| 仪表圆心 / 半径 | (400.0, 224.5) / 115.4 px |
| 速度数字 | x 364.6..472.1, y 161.8..237.4（高 75.6 px）|
| 限速牌 | x 557.5..604.6, y 118.0..164.4 |
| RANGE 数值 | 右对齐于 x 1493, y 119..162 |
| energy rail | x 1578.9..1615.4, y 79.6..381.2 |
| SOC 63% | x 1619..1659, y 229..252 |
| 车辆可见宽度 | 392.5 px（reference 592 * 480/724；渲染实测 392）|
| 车辆接地 | y 345（reference 车顶 194*0.663 = 128.6，车高按 1.82 长宽比 = 216 → 344.6；实测 346）|
| horizon | y 167 |

## 2. 环境是渲染出来的，不是画出来的

`tools/blender/build_horizon_v5_environment.py` 用 Cycles 渲染这个空间：

| 组成 | 做法 |
|---|---|
| 天空 | 世界节点上的垂直渐变（夜景，地平线附近有暖灰光带）|
| 山脊 | 3 层位移围幕网格，正弦叠加的脊线 + 由底部向顶部衰减的自发光 |
| 城市 | 620 个面向相机的发光面片，色温分 5 族，距离 700–4200 m |
| 路灯 | 6 个发光球体，近处 96 m 到 400 m |
| 路面 | 深色沥青 + 噪声驱动的粗糙度（水膜 0.08 / 干燥 0.40），湿反射真实产生竖向光带 |
| 大气 | 山脊自带梯度，不靠后期雾 |

所有环境物体都放在**视空间** `(u, v, z)` 里——因为冻结的 Horizon 相机方位角是
49.4°，把城市放在世界 +Y 上会让它整个跑出画面（本轮之前就是这样）。

关键尺寸（驾驶位 1.8 m 高、35 mm 镜头）由
`solve_environment_framing()` 反解相机位移，把地平线**精确**放在 y=167。

## 3. 车辆：站在画面里

冻结的相机是**正交 24.8° 俯视**。从这个角度，车辆自身的镜像会落在**车后面**——
实测车下有车/无车的差异只有 2/255。因此按人工审核给出的资产清单，反射用**预烘焙**
方式生成：

```
Plate  ->  VehicleLayer(base)  ->  UI
```

`tools/assets/compose_horizon_v5_vehicle.py` 把三张 Blender 输出合成一张 RGBA：

| 输入 | 用途 |
|---|---|
| `road/no_car.png` | 没有车时的湿路面（参考基线）|
| `road/<state>.png` | 同一相机、同一光照、有车的路面 |
| `car/<state>/000.png` | 干净的车辆通道（film transparent）|

差异 `C1 - C0` 就是"车改变了路面的所有像素"：遮挡、接地阴影、灯光在地面的响应。
反射层则是把车辆像素**镜像、压扁 0.55、高斯模糊、随距离衰减、加水纹**后预烘焙的
透明 PNG——设备端不做任何 runtime blur。

| 状态 | 层 | 说明 |
|---|---|---|
| base | 车 + 路面响应 + 反射 | 常显 |
| running | 尾灯点亮 | `position_light` |
| brake | 刹车灯 | `brake` |
| indicator_left / right | 转向灯 | 对应信号 |
| headlight | 前照灯 | `headlight` |

车辆可见轮廓（从最终 1920x480 渲染里量出来的，不是节点框；做法是同一场景去掉车辆
图层再渲染一次做差，再按合成器记录的车辆矩形切掉地面响应）：
**x 757..1149, y 129..346（392x217）**；连同湿路面响应（接地阴影 + 反射 + 灯光
地面响应）延伸到 y 480。左侧 speed primary 到 x 672 结束，右侧 RANGE primary 从
x 1357 开始——两侧都不碰撞。

## 4. 两个仪表簇

**Speed cluster**：225° 完整部分弧（0 km/h 在左下 135°，240 km/h 在 0°），
包含

* 预烘焙 `horizon_v5_arc_glow.png`（弧的辉光，宽度 4.2×描边）；
* 预烘焙 `horizon_v5_numeral_glow.png`（数字后面的光池）；
* 24 格刻度环（每 12 格加长）；
* 非激活弧 + 激活弧（`speed / 240`）；
* 数字、`km/h`、PRND、READY/CHILL、22 °C、限速牌。

**Energy cluster**：RANGE 数值、RANGE 标签、分隔线、功率波形（有语义：功率历史）、
POWER 数值、SOC 百分比，以及**竖向分段 energy rail**：

* 预烘焙 `horizon_v5_rail_track.png`（圆角轨道 + 24 段分隔）；
* 24 个 `vticks` 段按 SOC 自下而上点亮；
* SOC <= 20% 时切换到警告色（阈值规则）。

## 5. 被明令禁止、并且真的不存在的元素

| 禁止项 | 现状 |
|---|---|
| WHITE ROAD TRAPEZOIDS | 整个 V5 布局里**没有任何 polygon 组件**；测试会失败如果出现 |
| RED BRAKE TRAPEZOID | 同上；刹车的地面响应来自渲染差异 + 预烘焙红色反射 |
| solid polygon light beam | 前照灯只改 `car.headlight` 图层，没有多边形光束 |
| 没有语义的装饰线 | 只剩分隔线与功率波形，两条都有语义 |
| runtime blur | `cost_model.runtime_blur = none`；所有辉光都是位图 |
| gradient + polygon 当背景 | 背景是 Cycles 渲染的 1920x480 位图 |

## 6. 分层与成本

```text
LAYER_0_ENVIRONMENT   env.plate, speed.arc.glow, speed.numeral.glow, energy.rail.track
LAYER_1_VEHICLE      vehicle.base, vehicle.running, vehicle.brake,
                     vehicle.indicator_left, vehicle.indicator_right,
                     vehicle.headlight
LAYER_2_INSTRUMENT   speed / energy / driver / sign 的全部文字与矢量
LAYER_3_STATE        warn.glass, warn.text
```

解码内存估算（Mac 上估算，**T113 上未验证**）：

```
总解码 RGBA ≈ 8.31 MB（六个状态层全算上）
  env.plate            1920x480x4 = 3.69 MB
  vehicle layer        510x379x4  = 0.77 MB (每状态一张, 同屏最多 2-3 张)
  arc/numeral glow     0.36 MB
  rail track           0.04 MB
```

## 7. 复现

```bash
python3 tools/assets/analyze_v5_reference.py        # 测量 + 标注图
blender -b -P tools/blender/build_horizon_v5_environment.py -- \
    --master assets/source/blender/model_a_material_candidate.blend \
    --samples 64                                    # 环境 + 车辆通道
python3 tools/assets/compose_horizon_v5_vehicle.py  # 合成车辆层
python3 tools/assets/bake_horizon_v5_ui.py          # 弧辉光 / 轨道
python3 tools/preview/build_horizon_v5.py           # 布局 -> 场景
python3 tools/assets/bake_horizon_v55_ground_band.py  # 地面带（视差层）
python3 tools/assets/bake_horizon_v55_chase.py        # chase yaw 车辆通道（Blender）
python3 tools/assets/measure_horizon_v55_chase_boxes.py  # 各 yaw 的车高补偿
python3 tools/preview/horizon_v55_yaw_select.py       # 角度测量与选择
python3 tools/preview/horizon_v55_chase_evidence.py   # V5.5 六张证据 + 指标
python3 tools/preview/horizon_v5_evidence.py        # A/B/C/D 四件交付物
python3 tools/preview/horizon_v2_layout_qa.py --layout assets/ui/horizon_v5_layout.json \
    --scene scenes/horizon_v5.scene --tokens assets/ui/horizon_v5_tokens.json
```

## 8. 本轮交付物

| | 文件 |
|---|---|
| A reference | `assets/ui/horizon_v5_reference.png` |
| B implementation neutral | `assets/checkpoints/horizon_v5/horizon_v5_neutral.png` |
| C reference vs implementation | `assets/checkpoints/horizon_v5/horizon_v5_reference_vs_implementation.png` |
| D physical size | `assets/checkpoints/horizon_v5/horizon_v5_physical_scale.png` |

报告：`assets/checkpoints/horizon_v5/horizon_v5_report.json`。

**没有做的**（人工明确要求停在这里）：不生成 20 个状态、不 LOCK、不做设备集成、
不替换生产 Horizon、不动其它页面。视觉结论只有人工能给：
`HORIZON_V5_NEUTRAL = AWAITING HUMAN VISUAL APPROVAL`。


## 9. V5.1 — MOTION

`tools/assets/horizon_v5_motion.py` 是运动通道的唯一定义：`wheel_motion_level`、
`road_flow_level`、`wet_streak_level`、`aero_wake_level`、`micro_motion_level`，
全部是 0/30/80/120 km/h 锚点之间的 smoothstep 曲线。**没有任何效果是开关式的**：
测试每 0.5 km/h 采样一次，任何一步 >0.02、任何下降、任何越界都会失败。

| 通道 | 0 | 30 | 80 | 120 | 实现 |
|---|---|---|---|---|---|
| wheel | 0.00 | 0.35 | 0.70 | 1.00 | 三张预烘焙旋转模糊层，三角窗权重混合（30 以上和为 1，静止时为 0） |
| road flow | 0.00 | 0.30 | 0.75 | 1.00 | 一张 1920×160 平铺贴图，按速度平移 + 换行 |
| wet streak | 0.00 | 0.30 | 0.70 | 1.00 | 尾灯/转向灯在湿路面的倒影，长度按速度裁切 |
| aero wake | 0.00 | 0.05 | 0.45 | 1.00 | 车后方的青色气流拖尾，0 km/h 完全为 0 |
| micro motion | 0.00 | 0.60 px | 1.20 px | 2.00 px | 车身 0.55 Hz 微动，上限 2 px |

轮圈旋转**不是**在 Blender 里转 `wheels` 网格做的：实测那样只改变 1.8k 像素、轮辋
对比度不变——那两个网格不是这台相机看到的轮子（可见轮子属于 body 网格，拆出来
等于改几何，而几何是冻结的）。因此模糊是从相机真正看到的像素烘焙的：把轮子
patch 绕自身中心在曝光范围内旋转采样并平均，写成一张**替换**轮盘区域的 RGBA 层。

尾灯/转向灯倒影的颜色和位置来自**灯光像素本身**（`car/brake − car/base`），不是
UI 常量；将来尾灯系统改了，倒影会跟着改。倒影画在路面响应之上、且被车体 alpha
遮掉，绝不会画到车漆上。

证据：`horizon_v5_1_motion_{000,030,080,120}.png` +
`horizon_v5_1_motion_comparison.png` + `horizon_v5_1_motion_metrics.json`。
实测（区域平均差）：wheel 0.00 → 3.53 → 6.66 → 14.67；wake 0.00 → 0.12 → 0.16 →
0.23；flow 0.00 → 0.14 → 0.26 → 0.53；刹车倒影长度 0 → 12 → 55 → 76 px。

## 10. V5.1 — 昼夜环境（全局）

`tools/assets/horizon_v5_environment_time.py` 定义 DAWN / DAY / DUSK / NIGHT 四相、
它们的时间权重、每相的 HUD 调色板，以及**离线**日出日落日程：

1. 由 日期 + 经纬度 + 时区 计算（标准太阳赤纬近似，不联网）；
2. Southern Ontario 月度区域 profile（同一模型生成，12 个月）；
3. 固定兜底 07:00 / 19:00。

四张环境底板（`assets/ui/horizon_v5_background{,_dawn,_day,_dusk}.png`）由同一个
Blender 场景生成：几何、相机、车辆完全相同，只有天空、太阳、城市灯光、路面响应
不同——这正是"过渡=两张底板交叉淡入"而不是"两个地方"的原因。

过渡窗口 90/105 分钟，smoothstep：每分钟权重变化上限 0.0167。实测（每 2 分钟
采样 91 帧）最大单步是整段过渡的 6.5%–8.1%，调色板最大单步 7/255。17:59/18:00
式切换会表现为"一步等于整段"。

**日间可读性是量出来的**：第一版日间调色板对着渲染底板只有 2.4:1（主文字）和
1.8:1（能量轨），加深后通过：主文字 6.0:1、次级 8.3:1、弱化 5.9:1、accent 3.4:1、
轨道 3.3:1。语义色（刹车红 / 转向琥珀 / READY 绿）**不随环境改变**，有测试保证。

内存：过渡期间只保留**两张**底板（2 × 3.69 MB）+ 常驻车辆层 + 运动叠加层，估算
9.57 MB（250 MB 设备余量充足）。

证据：`horizon_v5_1_{dawn,day,dusk,night}.png`、
`horizon_v5_1_daily_cycle_contact_sheet.png`（12 个时刻）、
`horizon_v5_1_seasonal_daylight_test.png`（1/4/7/10 月）、
`horizon_v5_1_{day,night}_key_states.png`、
`horizon_v5_1_vehicle_material_day_night.png`、
`horizon_v5_1_final_contact_sheet.png`、`horizon_v5_1_metrics.json`。

## 11. V5.1 之后的真实状态（交接）

- Horizon V5.1 的结构 / 运动 / 昼夜三块都已有自动 gate 与像素证据；
- V6 页面清单见 `docs/V6_PAGE_SET.md`（7 套行车页 + 设置 + 开发者 = 9 屏），
  当前 9 屏的 scene 都还是**矢量背景**，尚未接入烘焙环境底板；
- 其余页面尚未逐个继续；下一页按清单顺序是 **Mono**（最省资源 / 夜间备用），
  它应当是全局 `EnvironmentTimeSystem` 的第一个非 Horizon 使用方，而不是再写一套
  时间算法。
