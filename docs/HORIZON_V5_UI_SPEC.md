# HORIZON V5 - pending reference

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
| LAYER_0_DEEP_ENVIRONMENT | 4 | `env.base`, `env.horizon.glow`, `env.horizon.line`, `env.distant.ridge` |
| LAYER_1_VEHICLE_STAGE | 5 | `stage.ground`, `stage.ground.sheen`, `stage.contact.shadow`, `stage.reflection`, `vehicle` |
| LAYER_2_INFORMATION | 13 | `speed.value`, `speed.unit`, `gear.p`, `gear.r`, `gear.n`, `gear.d`, `energy.range`, `energy.rail`, `energy.soc`, `energy.power`, `nav.capsule.fill`, `speedlimit.glass.fill`, `warn.glass.fill` |
| LAYER_3_STATE_FEEDBACK | 9 | `state.left.ground0`, `state.left.ground1`, `state.left.ground2`, `state.right.ground0`, `state.right.ground1`, `state.right.ground2`, `state.brake.reflection`, `state.headlight.left`, `state.headlight.right` |

## 2. 调色板（唯一来源）

| 用途 | 值 |
|---|---|
| bg_deep | `#05090D` |
| bg_mid | `#071017` |
| bg_horizon | `#0A141C` |
| bg_ground | `#0E1A22` |
| ground_sheen | `#101A22` |
| contact_shadow | `#02060A` |
| reflection | `#0B141B` |
| glass_fill | `#071017` |
| glass_border | `#12202A` |
| glass_top_edge | `#9FB6C4` |
| glass_bottom_shade | `#02060A` |
| primary_text | `#E9EEF3` |
| secondary_text | `#C3CDD7` |
| muted_text | `#7C8894` |
| accent | `#58C8D8` |
| accent_dim | `#1E3A44` |
| warning | `#D8A657` |
| critical | `#D8674F` |
| ready | `#7BD2C4` |
| throw | `#DCD8CC` |

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
| `env.base` | vector/vgradient | 0 | 0 | 1920 | 480 | 0 | static | 总是 |
| `env.horizon.glow` | vector/vgradient | 380 | 210 | 1160 | 96 | 1 | static | 总是 |
| `env.horizon.line` | vector/line | 520 | 300 | 880 | 1 | 2 | static | 总是 |
| `env.distant.ridge` | vector/polygon | 240 | 274 | 1440 | 26 | 2 | static | 总是 |
| `stage.ground` | vector/vgradient | 0 | 300 | 1920 | 180 | 3 | static | 总是 |
| `stage.ground.sheen` | vector/polygon | 500 | 300 | 920 | 180 | 4 | static | 总是 |
| `stage.contact.shadow` | vector/polygon | 622 | 414 | 677 | 34 | 5 | static | 总是 |
| `stage.reflection` | vector/vgradient | 682 | 436 | 557 | 32 | 6 | static | 总是 |
| `vehicle` | vehicle/ | 642 | 4 | 637 | 439 | 30 | dynamic | 总是 |
| `speed.arc` | vector/arc | 130 | 118 | 300 | 300 | 6 | static | 总是 |
| `speed.arc.active` | vector/arc | 130 | 118 | 300 | 300 | 7 | static | 总是 |
| `speed.mark.0` | vector/line | 126 | 118 | 10 | 1 | 8 | static | 总是 |
| `speed.mark.120` | vector/line | 126 | 118 | 10 | 1 | 8 | static | 总是 |
| `speed.mark.240` | vector/line | 126 | 118 | 10 | 1 | 8 | static | 总是 |
| `speed.value` | text/ | 120 | 105 | 300 | 140 | 40 | dynamic | 总是 |
| `speed.unit` | text/ | 124 | 250 | 120 | 26 | 40 | dynamic | 总是 |
| `gear.p` | text/ | 120 | 283 | 30 | 34 | 40 | dynamic | 总是 |
| `gear.r` | text/ | 164 | 283 | 30 | 34 | 40 | dynamic | 总是 |
| `gear.n` | text/ | 208 | 283 | 30 | 34 | 40 | dynamic | 总是 |
| `gear.d` | text/ | 252 | 283 | 30 | 34 | 40 | dynamic | 总是 |
| `gear.unknown` | text/ | 120 | 283 | 30 | 34 | 40 | dynamic | binding=gear、show_when_invalid=True |
| `driver.temperature` | text/ | 300 | 40 | 120 | 32 | 40 | dynamic | 总是 |
| `driver.status` | text/ | 120 | 337 | 220 | 30 | 40 | dynamic | 总是 |
| `speedlimit.glass.fill` | vector/roundrect | 316 | 240 | 76 | 76 | 24 | dynamic | binding=speed_limit、show_when_valid=True |
| `speedlimit.glass.edge` | vector/line | 318 | 240 | 72 | 1 | 25 | dynamic | binding=speed_limit、show_when_valid=True |
| `speedlimit.glass.shade` | vector/line | 318 | 315 | 72 | 1 | 25 | dynamic | binding=speed_limit、show_when_valid=True |
| `speedlimit.ring` | vector/roundrect | 324 | 248 | 60 | 60 | 25 | dynamic | binding=speed_limit、show_when_valid=True |
| `speedlimit.value` | text/ | 316 | 262 | 76 | 32 | 40 | dynamic | binding=speed_limit、show_when_valid=True |
| `energy.range` | text/ | 1606 | 138 | 200 | 74 | 40 | dynamic | 总是 |
| `energy.range.label` | text/ | 1606 | 216 | 200 | 24 | 40 | dynamic | 总是 |
| `energy.rail` | vector/vticks | 1758 | 264 | 10 | 132 | 6 | static | 总是 |
| `energy.rail.warn` | vector/vticks | 1758 | 264 | 10 | 132 | 7 | static | binding=actual_soc、lte=20 |
| `energy.soc` | text/ | 1606 | 268 | 140 | 36 | 40 | dynamic | 总是 |
| `energy.soc.label` | text/ | 1606 | 310 | 140 | 24 | 40 | dynamic | 总是 |
| `energy.power` | text/ | 1606 | 336 | 200 | 36 | 40 | dynamic | 总是 |
| `energy.power.label` | text/ | 1606 | 376 | 200 | 24 | 40 | dynamic | 总是 |
| `energy.trend` | vector/line | 1560 | 414 | 186 | 1 | 8 | dynamic | binding=power_history_valid、show_when_true=True |
| `top.clock` | text/ | 1606 | 40 | 200 | 32 | 40 | dynamic | 总是 |
| `nav.capsule.fill` | vector/roundrect | 650 | 16 | 620 | 64 | 20 | dynamic | binding=nav_manoeuvre、show_when_valid=True |
| `nav.capsule.edge` | vector/line | 652 | 16 | 616 | 1 | 21 | dynamic | binding=nav_manoeuvre、show_when_valid=True |
| `nav.capsule.shade` | vector/line | 652 | 79 | 616 | 1 | 21 | dynamic | binding=nav_manoeuvre、show_when_valid=True |
| `nav.icon` | text/ | 676 | 30 | 44 | 36 | 40 | dynamic | binding=nav_manoeuvre、show_when_valid=True |
| `nav.distance` | text/ | 724 | 30 | 120 | 36 | 40 | dynamic | binding=nav_manoeuvre、show_when_valid=True |
| `nav.instruction` | text/ | 850 | 30 | 400 | 36 | 40 | dynamic | binding=nav_manoeuvre、show_when_valid=True |
| `state.left.ground0` | vector/line | 560 | 424 | 120 | 1 | 12 | dynamic | binding=indicator_left、show_when_true=True |
| `state.left.ground1` | vector/line | 572 | 434 | 120 | 1 | 12 | dynamic | binding=indicator_left、show_when_true=True |
| `state.left.ground2` | vector/line | 584 | 444 | 120 | 1 | 12 | dynamic | binding=indicator_left、show_when_true=True |
| `state.right.ground0` | vector/line | 1250 | 424 | 120 | 1 | 12 | dynamic | binding=indicator_right、show_when_true=True |
| `state.right.ground1` | vector/line | 1262 | 434 | 120 | 1 | 12 | dynamic | binding=indicator_right、show_when_true=True |
| `state.right.ground2` | vector/line | 1274 | 444 | 120 | 1 | 12 | dynamic | binding=indicator_right、show_when_true=True |
| `state.brake.reflection` | vector/polygon | 642 | 424 | 637 | 40 | 11 | dynamic | binding=brake、show_when_true=True |
| `state.headlight.left` | vector/polygon | 250 | 320 | 170 | 100 | 10 | dynamic | binding=headlight、show_when_true=True |
| `state.headlight.right` | vector/polygon | 1500 | 320 | 170 | 100 | 10 | dynamic | binding=headlight、show_when_true=True |
| `warn.glass.fill` | vector/roundrect | 660 | 406 | 600 | 36 | 29 | dynamic | binding=warning_active、show_when_true=True |
| `warn.glass.edge` | vector/line | 662 | 406 | 596 | 1 | 30 | dynamic | binding=warning_active、show_when_true=True |
| `warn.glass.shade` | vector/line | 662 | 441 | 596 | 1 | 30 | dynamic | binding=warning_active、show_when_true=True |
| `warn.text` | text/ | 660 | 424 | 600 | 30 | 40 | dynamic | 总是 |

## 5. 状态反应

| 层 | id | 绑定 | 触发 | 透明度 |
|---|---|---|---|---|
| dynamic | `gear.unknown` | gear | show_when_invalid=True | 1.0 |
| dynamic | `speedlimit.glass.fill` | speed_limit | show_when_valid=True | 0.7 |
| dynamic | `speedlimit.glass.edge` | speed_limit | show_when_valid=True | 0.22 |
| dynamic | `speedlimit.glass.shade` | speed_limit | show_when_valid=True | 0.38 |
| dynamic | `speedlimit.ring` | speed_limit | show_when_valid=True | 0.85 |
| dynamic | `speedlimit.value` | speed_limit | show_when_valid=True | 1.0 |
| static | `energy.rail.warn` | actual_soc | lte=20 | 1.0 |
| dynamic | `energy.trend` | power_history_valid | show_when_true=True | 0.6 |
| dynamic | `nav.capsule.fill` | nav_manoeuvre | show_when_valid=True | 0.7 |
| dynamic | `nav.capsule.edge` | nav_manoeuvre | show_when_valid=True | 0.22 |
| dynamic | `nav.capsule.shade` | nav_manoeuvre | show_when_valid=True | 0.38 |
| dynamic | `nav.icon` | nav_manoeuvre | show_when_valid=True | 1.0 |
| dynamic | `nav.distance` | nav_manoeuvre | show_when_valid=True | 1.0 |
| dynamic | `nav.instruction` | nav_manoeuvre | show_when_valid=True | 1.0 |
| dynamic | `state.left.ground0` | indicator_left | show_when_true=True | 0.4 |
| dynamic | `state.left.ground1` | indicator_left | show_when_true=True | 0.4 |
| dynamic | `state.left.ground2` | indicator_left | show_when_true=True | 0.4 |
| dynamic | `state.right.ground0` | indicator_right | show_when_true=True | 0.4 |
| dynamic | `state.right.ground1` | indicator_right | show_when_true=True | 0.4 |
| dynamic | `state.right.ground2` | indicator_right | show_when_true=True | 0.4 |
| dynamic | `state.brake.reflection` | brake | show_when_true=True | 0.24 |
| dynamic | `state.headlight.left` | headlight | show_when_true=True | 0.08 |
| dynamic | `state.headlight.right` | headlight | show_when_true=True | 0.08 |
| dynamic | `warn.glass.fill` | warning_active | show_when_true=True | 0.7 |
| dynamic | `warn.glass.edge` | warning_active | show_when_true=True | 0.22 |
| dynamic | `warn.glass.shade` | warning_active | show_when_true=True | 0.38 |

## 6. 动画令牌（本轮只声明）

| 令牌 | 值 |
|---|---|
| state_fade_ms | 220 |
| navigation_fade_ms | 200 |
| navigation_slide_px | 12 |
| indicator_ground_pulse_ms | 420 |
| road_travel_ms | 900 |
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
