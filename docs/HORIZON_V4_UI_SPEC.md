# HORIZON V4 — SPATIAL GLASS COCKPIT

状态：**等待人工视觉验收** （`HORIZON_V4_SPATIAL_GLASS = AWAITING HUMAN VISUAL APPROVAL`）。

V3 被否决的原因：三个候选是同一套构图换装饰线，那条粗青色斜线没有语义。
V4 不复用那套语言，改为四层空间结构。本文与
`assets/ui/horizon_v4_layout.json`、`assets/ui/horizon_v4_tokens.json`
由同一份数据生成，文档不可能与场景不一致。

## 1. 四层空间结构

```text
LAYER 0  deep environment
LAYER 1  spatial road / vehicle stage
LAYER 2  information glass (navigation, speed limit, warning)
LAYER 3  state feedback
```

| 层 | 元素数 | 元素 |
|---|---|---|
| LAYER_0_DEEP_ENVIRONMENT | 3 | `env.depth`, `env.horizon.glow`, `env.atmosphere` |
| LAYER_1_VEHICLE_STAGE | 8 | `stage.road`, `stage.sheen`, `stage.lane.left`, `stage.lane.right`, `stage.contact.shadow`, `stage.reflection`, `stage.rim.light`, `vehicle` |
| LAYER_2_INFORMATION_GLASS | 3 | `nav.capsule`, `speedlimit.glass`, `warn.glass` |
| LAYER_3_STATE_FEEDBACK | 17 | `energy.flow.consume`, `energy.flow.regen`, `state.indicator.left0`, `state.indicator.right0`, `state.indicator.left1`, `state.indicator.right1`, `state.indicator.left2`, `state.indicator.right2`, `state.brake.reflection`, `state.headlight.l`, `state.headlight.r`, `state.door.fl`, `state.door.fr`, `state.door.rl`, `state.door.rr`, `state.frunk.underlight`, `state.trunk.underlight` |

## 2. 调色板（唯一来源）

| 用途 | 值 |
|---|---|
| bg_top | `#05090D` |
| bg_mid | `#071017` |
| bg_bottom | `#0A141C` |
| glass_fill | `#071017` |
| glass_border | `#101C26` |
| glass_top_edge | `#9FB6C4` |
| glass_bottom_shade | `#02060A` |
| primary_text | `#E9EEF3` |
| secondary_text | `#C3CDD7` |
| muted_text | `#7C8894` |
| accent | `#58C8D8` |
| accent_dim | `#1E3A44` |
| road | `#071017` |
| road_sheen | `#0A141C` |
| lane_edge | `#1E3A44` |
| shadow | `#02060A` |
| warning | `#D8A657` |
| critical | `#D8674F` |
| ready | `#7BD2C4` |
| wedge | `#E4E0D6` |

## 3. 字体层级

| 层级 | 字号 | 字距 |
|---|---|---|
| DISPLAY | 124 | -2.0 |
| TITLE | 62 | 0.0 |
| BODY | 28 | 1.2 |
| CAPTION | 22 | 1.6 |
| LABEL | 16 | 2.4 |

## 4. 元素表（全部 65 项由 layout 生成，此处为可读摘要）

| id | 类型 | x | y | w | h | z | 层 | 可见性 |
|---|---|---|---|---|---|---|---|---|
| `env.depth` | vector/vgradient | 0 | 0 | 1920 | 480 | 0 | static | 总是 |
| `env.horizon.glow` | vector/radial | 340 | 150 | 1240 | 290 | 1 | static | 总是 |
| `env.atmosphere` | vector/vgradient | 300 | 248 | 1320 | 56 | 1 | static | 总是 |
| `stage.road` | vector/polygon | 300 | 296 | 1320 | 160 | 2 | static | 总是 |
| `stage.sheen` | vector/polygon | 620 | 296 | 680 | 160 | 3 | static | 总是 |
| `stage.lane.left` | vector/line | 620 | 296 | 280 | 160 | 4 | static | 总是 |
| `stage.lane.right` | vector/line | 1020 | 296 | 280 | 160 | 4 | static | 总是 |
| `stage.contact.shadow` | vector/polygon | 720 | 398 | 480 | 34 | 4 | static | 总是 |
| `stage.reflection` | vector/vgradient | 740 | 402 | 440 | 54 | 5 | static | 总是 |
| `stage.rim.light` | vector/line | 762 | 402 | 396 | 1 | 6 | static | 总是 |
| `vehicle` | vehicle/ | 600 | 0 | 716 | 474 | 30 | dynamic | 总是 |
| `speed.sweep` | vector/arc | 130 | 118 | 300 | 300 | 6 | static | 总是 |
| `speed.sweep.active` | vector/arc | 130 | 118 | 300 | 300 | 7 | static | 总是 |
| `speed.sweep.marker.start` | vector/line | 126 | 118 | 8 | 1 | 8 | static | 总是 |
| `speed.sweep.marker.end` | vector/line | 426 | 118 | 8 | 1 | 8 | static | 总是 |
| `speed.value` | text/ | 120 | 105 | 300 | 140 | 40 | dynamic | 总是 |
| `speed.unit` | text/ | 124 | 250 | 120 | 30 | 40 | dynamic | 总是 |
| `gear.p` | text/ | 120 | 283 | 30 | 34 | 40 | dynamic | 总是 |
| `gear.r` | text/ | 164 | 283 | 30 | 34 | 40 | dynamic | 总是 |
| `gear.n` | text/ | 208 | 283 | 30 | 34 | 40 | dynamic | 总是 |
| `gear.d` | text/ | 252 | 283 | 30 | 34 | 40 | dynamic | 总是 |
| `gear.unknown` | text/ | 120 | 283 | 30 | 34 | 40 | dynamic | binding=gear、show_when_invalid=True |
| `driver.status` | text/ | 120 | 337 | 220 | 30 | 40 | dynamic | 总是 |
| `speedlimit.glass.fill` | vector/roundrect | 300 | 236 | 76 | 76 | 24 | dynamic | binding=speed_limit、show_when_valid=True |
| `speedlimit.glass.edge` | vector/line | 302 | 236 | 72 | 1 | 25 | dynamic | binding=speed_limit、show_when_valid=True |
| `speedlimit.glass.shade` | vector/line | 302 | 311 | 72 | 1 | 25 | dynamic | binding=speed_limit、show_when_valid=True |
| `speedlimit.ring` | vector/roundrect | 308 | 244 | 60 | 60 | 25 | dynamic | binding=speed_limit、show_when_valid=True |
| `speedlimit.value` | text/ | 300 | 262 | 76 | 32 | 40 | dynamic | binding=speed_limit、show_when_valid=True |
| `energy.range` | text/ | 1606 | 138 | 200 | 74 | 40 | dynamic | 总是 |
| `energy.range.label` | text/ | 1606 | 216 | 200 | 24 | 40 | dynamic | 总是 |
| `energy.surface` | vector/vticks | 1748 | 264 | 8 | 116 | 6 | static | 总是 |
| `energy.surface.warn` | vector/vticks | 1748 | 264 | 8 | 116 | 7 | static | binding=actual_soc、lte=20 |
| `energy.soc` | text/ | 1606 | 276 | 120 | 36 | 40 | dynamic | 总是 |
| `energy.soc.label` | text/ | 1606 | 316 | 120 | 24 | 40 | dynamic | 总是 |
| `energy.power` | text/ | 1606 | 336 | 200 | 36 | 40 | dynamic | 总是 |
| `energy.flow.consume` | vector/line | 1690 | 362 | 34 | 1 | 8 | dynamic | binding=battery_power、gte=0.5 |
| `energy.flow.regen` | vector/line | 1690 | 376 | 34 | 1 | 8 | dynamic | binding=battery_power、lte=-0.5 |
| `top.temperature` | text/ | 500 | 57 | 120 | 34 | 40 | dynamic | 总是 |
| `top.clock` | text/ | 1606 | 57 | 200 | 34 | 40 | dynamic | 总是 |
| `nav.capsule.fill` | vector/roundrect | 650 | 16 | 620 | 64 | 20 | dynamic | binding=nav_manoeuvre、show_when_valid=True |
| `nav.capsule.edge` | vector/line | 652 | 16 | 616 | 1 | 21 | dynamic | binding=nav_manoeuvre、show_when_valid=True |
| `nav.capsule.shade` | vector/line | 652 | 79 | 616 | 1 | 21 | dynamic | binding=nav_manoeuvre、show_when_valid=True |
| `nav.leading` | vector/line | 650 | 26 | 3 | 44 | 22 | dynamic | binding=nav_manoeuvre、show_when_valid=True |
| `nav.icon` | text/ | 676 | 30 | 44 | 36 | 40 | dynamic | binding=nav_manoeuvre、show_when_valid=True |
| `nav.distance` | text/ | 724 | 30 | 120 | 36 | 40 | dynamic | binding=nav_manoeuvre、show_when_valid=True |
| `nav.instruction` | text/ | 850 | 30 | 400 | 36 | 40 | dynamic | binding=nav_manoeuvre、show_when_valid=True |
| `state.indicator.left0` | vector/line | 618 | 352 | 96 | 1 | 12 | dynamic | binding=indicator_left、show_when_true=True |
| `state.indicator.right0` | vector/line | 1206 | 352 | 96 | 1 | 12 | dynamic | binding=indicator_right、show_when_true=True |
| `state.indicator.left1` | vector/line | 628 | 380 | 96 | 1 | 12 | dynamic | binding=indicator_left、show_when_true=True |
| `state.indicator.right1` | vector/line | 1196 | 380 | 96 | 1 | 12 | dynamic | binding=indicator_right、show_when_true=True |
| `state.indicator.left2` | vector/line | 638 | 408 | 96 | 1 | 12 | dynamic | binding=indicator_left、show_when_true=True |
| `state.indicator.right2` | vector/line | 1186 | 408 | 96 | 1 | 12 | dynamic | binding=indicator_right、show_when_true=True |
| `state.brake.reflection` | vector/polygon | 800 | 402 | 320 | 40 | 11 | dynamic | binding=brake、show_when_true=True |
| `state.headlight.l` | vector/polygon | 620 | 300 | 440 | 140 | 10 | dynamic | binding=headlight、show_when_true=True |
| `state.headlight.r` | vector/polygon | 1120 | 300 | 440 | 140 | 10 | dynamic | binding=headlight、show_when_true=True |
| `state.door.fl` | vector/line | 700 | 168 | 64 | 1 | 11 | dynamic | binding=door_fl、show_when_true=True |
| `state.door.fr` | vector/line | 1160 | 168 | 64 | 1 | 11 | dynamic | binding=door_fr、show_when_true=True |
| `state.door.rl` | vector/line | 700 | 300 | 64 | 1 | 11 | dynamic | binding=door_rl、show_when_true=True |
| `state.door.rr` | vector/line | 1160 | 300 | 64 | 1 | 11 | dynamic | binding=door_rr、show_when_true=True |
| `state.frunk.underlight` | vector/line | 900 | 196 | 120 | 1 | 11 | dynamic | binding=frunk、show_when_true=True |
| `state.trunk.underlight` | vector/line | 900 | 404 | 120 | 1 | 11 | dynamic | binding=trunk、show_when_true=True |
| `warn.glass.fill` | vector/roundrect | 660 | 406 | 600 | 36 | 29 | dynamic | binding=warning_active、show_when_true=True |
| `warn.glass.edge` | vector/line | 662 | 406 | 596 | 1 | 30 | dynamic | binding=warning_active、show_when_true=True |
| `warn.glass.shade` | vector/line | 662 | 441 | 596 | 1 | 30 | dynamic | binding=warning_active、show_when_true=True |
| `warn.text` | text/ | 660 | 424 | 600 | 30 | 40 | dynamic | 总是 |

## 5. 状态反应

| 层 | id | 绑定 | 触发 | 透明度 |
|---|---|---|---|---|
| dynamic | `gear.unknown` | gear | show_when_invalid=True | 1.0 |
| dynamic | `speedlimit.glass.fill` | speed_limit | show_when_valid=True | 0.72 |
| dynamic | `speedlimit.glass.edge` | speed_limit | show_when_valid=True | 0.25 |
| dynamic | `speedlimit.glass.shade` | speed_limit | show_when_valid=True | 0.4 |
| dynamic | `speedlimit.ring` | speed_limit | show_when_valid=True | 0.85 |
| dynamic | `speedlimit.value` | speed_limit | show_when_valid=True | 1.0 |
| static | `energy.surface.warn` | actual_soc | lte=20 | 1.0 |
| dynamic | `energy.flow.consume` | battery_power | gte=0.5 | 0.85 |
| dynamic | `energy.flow.regen` | battery_power | lte=-0.5 | 0.85 |
| dynamic | `nav.capsule.fill` | nav_manoeuvre | show_when_valid=True | 0.72 |
| dynamic | `nav.capsule.edge` | nav_manoeuvre | show_when_valid=True | 0.25 |
| dynamic | `nav.capsule.shade` | nav_manoeuvre | show_when_valid=True | 0.4 |
| dynamic | `nav.leading` | nav_manoeuvre | show_when_valid=True | 0.85 |
| dynamic | `nav.icon` | nav_manoeuvre | show_when_valid=True | 1.0 |
| dynamic | `nav.distance` | nav_manoeuvre | show_when_valid=True | 1.0 |
| dynamic | `nav.instruction` | nav_manoeuvre | show_when_valid=True | 1.0 |
| dynamic | `state.indicator.left0` | indicator_left | show_when_true=True | 0.5 |
| dynamic | `state.indicator.right0` | indicator_right | show_when_true=True | 0.5 |
| dynamic | `state.indicator.left1` | indicator_left | show_when_true=True | 0.5 |
| dynamic | `state.indicator.right1` | indicator_right | show_when_true=True | 0.5 |
| dynamic | `state.indicator.left2` | indicator_left | show_when_true=True | 0.5 |
| dynamic | `state.indicator.right2` | indicator_right | show_when_true=True | 0.5 |
| dynamic | `state.brake.reflection` | brake | show_when_true=True | 0.22 |
| dynamic | `state.headlight.l` | headlight | show_when_true=True | 0.1 |
| dynamic | `state.headlight.r` | headlight | show_when_true=True | 0.1 |
| dynamic | `state.door.fl` | door_fl | show_when_true=True | 0.55 |
| dynamic | `state.door.fr` | door_fr | show_when_true=True | 0.55 |
| dynamic | `state.door.rl` | door_rl | show_when_true=True | 0.55 |
| dynamic | `state.door.rr` | door_rr | show_when_true=True | 0.55 |
| dynamic | `state.frunk.underlight` | frunk | show_when_true=True | 0.45 |
| dynamic | `state.trunk.underlight` | trunk | show_when_true=True | 0.45 |
| dynamic | `warn.glass.fill` | warning_active | show_when_true=True | 0.72 |
| dynamic | `warn.glass.edge` | warning_active | show_when_true=True | 0.25 |
| dynamic | `warn.glass.shade` | warning_active | show_when_true=True | 0.4 |

## 6. 动画令牌（本轮只声明）

| 令牌 | 值 |
|---|---|
| chevron_stage_ms | 180 |
| chevron_travel_px | 26 |
| navigation_fade_ms | 200 |
| navigation_slide_px | 12 |
| state_fade_ms | 220 |
| flow_travel_ms | 900 |
| arc_ease_ms | 160 |

## 7. T113 成本

| 项 | 值 |
|---|---|
| 静态背景 | 3 层，可烘焙为 1 张 `assets/ui/horizon_v4_background.png` |
| 玻璃材质 | 9-slice 位图，无运行时模糊 |
| 常驻解码资产 | 5（背景位图 + 车辆底图 + 面板 delta 层）≈ 4.6 MB |
| 每帧工作 | 文本 + 透明度 + 少量状态矢量；车辆是唯一每帧位图 |
| 同时状态叠加 | ≤ 4 |
| 同时动画序列 | ≤ 2 |

## 8. 自动验收

- 与 v2.1 同一套几何 QA（画布 / 梯形遮罩 / 区域 / 文本碰撞 /
  速度 0–288 十档间距 / UNKNOWN / 无调试文本 / 装饰线不穿文字）
- 导航隐藏 = 0 像素（探针渲染）
- 与 V3 B 的像素差异（排除车辆位图）见 `horizon_v4_report.json`

## 9. 证据

`assets/checkpoints/horizon_v4/` 下：14 张状态图、`horizon_v4_contact_sheet.png`、
`horizon_v4_key_states.png`、`horizon_v4_physical_scale.png`、
`horizon_v3_vs_v4.png`、`horizon_v4_report.json`。
