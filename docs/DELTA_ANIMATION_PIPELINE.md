# Dirty Region / Delta Animation 管线（Parts 12-17）

状态：**POC 完成并已数值验证**。真机传输方式**未验证**。

上一轮的 benchmark 已经证明全透明画布解码是浪费：车只占画布约 30%，
但每帧都要解码整张画布。本轮把三件事做出来：

1. 每帧 alpha bounding box + padding + metadata（Part 12）
2. static base + per-frame replacement region（Part 13）
3. 自动重建验证（Part 14）

然后重新跑预算（Part 15、16），并给出运行时架构（Part 17）。

---

## 1. 为什么是"矩形替换"而不是"叠加"

开门后**像素会变成透明**（门移开，原处没有东西）。如果用 src-over 贴回去，
底下的旧 base 像素会留在原地 —— 门会拖出一条残影。

所以本管线用的是**矩形替换**：crop 区域包含"这一帧该区域完整正确的画面"
（RGBA 全部），运行时直接覆盖该矩形。因为 crop 就是从真实渲染帧里裁出来的，
替换在数学上应当**逐位相等**，工具会自动验证这一点。

## 2. 工具

### 2.1 `tools/assets/build_delta_animation.py`（Parts 12-14）

输入 closed base + 完整帧序列，输出：

```
base.png            关闭状态，整画布，只存一次
frames/NNN.png      只存与 base 不同的最小矩形（来自真实渲染帧）
animation.json      每帧 metadata + 验证 + 预算
```

每帧 metadata（Part 12 指定的字段）：

```json
{
  "frame": 7,
  "x": 151, "y": 150, "width": 308, "height": 246,
  "anchor_x": 151, "anchor_y": 150,
  "duration_ms": 33,
  "empty": false,
  "raw_bbox": [157, 156, 459, 396]
}
```

`anchor_*` 与 `x/y` 在当前实现里数值相同（crop 就放在它的原始位置），
之所以分开记录，是为了将来把多帧打进 atlas 时可以把 cell 放到图集别处。

### 2.2 `tools/assets/report_animation_budget.py`（Part 15）

对同一个动画比较三种策略：

| | 策略 | 含义 |
|---|---|---|
| **A** | full canvas | 解码整张画布 |
| **B** | alpha crop | 只解码整段动画的 alpha 联合包围盒 |
| **C** | difference crop | 只解码该帧的 dirty region |

### 2.3 验证（Part 14）

对每一帧真的执行一次运行时重建：

```python
rebuilt = base.copy()
rebuilt[y0:y1, x0:x1] = crop
assert (rebuilt == original_frame).all()
```

结果记录在 `animation.json` 的 `verification` 段。

---

## 3. 阈值：exact 与 near-equivalent

第一版用 `threshold = 0`（任何 1 级差异都算变化），结果 dirty region 占画布
**29.0%** —— 几乎等于 alpha crop，等于没省。原因是 EEVEE 在 1–3 级范围内
就有渲染噪声，"任何差异"会把矩形吹到整辆车。

实测对比（600px / 30fps open，20 帧）：

| threshold | avg region | 占画布 | 重建结果 |
|---|---|---|---|
| 0 | 118,363 px | 29.0% | **pixel-equal**（0 像素不同） |
| **4（采用）** | **39,252 px** | **9.6%** | 最坏 4,097 px 差 ≤4 级 |
| 12 | 27,048 px | 6.6% | 最坏 5,534 px 差 ≤12 级 |

采用 **threshold = 4**：最大误差 4/255，肉眼不可见，区域缩小到 1/3。
`animation.json` 里始终记录真实的最坏误差，不隐藏这个取舍。

---

## 4. 结果（Part 15 / 16）

全部 12 组（3 尺寸 × 30/60fps × open/close）都通过验证，最坏通道误差 **4**。

### 4.1 关键三组（open）

**400px / 30fps**（画布 513×354，20 帧，预算 33.3 ms）

| 策略 | 平均尺寸 | 峰值尺寸 | 平均像素/帧 | 解码 MB | PNG/帧 | 估计 ms/帧 | 占预算 |
|---|---|---|---|---|---|---|---|
| A full | 513×354 | 513×354 | 181,602 | 0.693 | 79.8 KB | 14.9 | 45% |
| B alpha crop | 310×179 | 310×179 | 55,490 | 0.212 | 79.8 KB | 4.5 | 14% |
| **C difference** | **203×112** | 274×129 | **22,791** | **0.087** | **31.3 KB** | **1.9** | **6%** |

**600px / 60fps**（画布 769×531，38 帧，预算 16.7 ms）

| 策略 | 平均尺寸 | 峰值尺寸 | 平均像素/帧 | 解码 MB | PNG/帧 | 估计 ms/帧 | 占预算 |
|---|---|---|---|---|---|---|---|
| A full | 769×531 | 769×531 | 408,339 | 1.558 | 161.7 KB | 33.4 | **200%** |
| B alpha crop | 462×266 | 462×266 | 122,892 | 0.469 | 161.7 KB | 10.1 | 60% |
| **C difference** | **195×185** | 308×246 | **36,131** | **0.138** | **45.7 KB** | **3.0** | **18%** |

**800px / 60fps**（画布 1026×709，38 帧，预算 16.7 ms）

| 策略 | 平均尺寸 | 峰值尺寸 | 平均像素/帧 | 解码 MB | PNG/帧 | 估计 ms/帧 | 占预算 |
|---|---|---|---|---|---|---|---|
| A full | 1026×709 | 1026×709 | 727,434 | 2.775 | 271.8 KB | 59.5 | **357%** |
| B alpha crop | 617×354 | 617×354 | 218,418 | 0.833 | 271.8 KB | 17.9 | 107% |
| **C difference** | **291×237** | 410×285 | **68,807** | **0.262** | **80.3 KB** | **5.6** | **34%** |

### 4.2 节省幅度

| 变体 | 像素/解码节省 | PNG 字节节省 |
|---|---|---|
| 400px / 30fps open | −87.5% | −60.8% |
| 400px / 30fps close | −86.4% | −58.1% |
| 600px / 30fps open | −91.0% | −71.4% |
| 600px / 60fps open | −91.2% | −71.8% |
| 800px / 30fps open | −90.3% | −69.8% |
| 800px / 60fps open | −90.5% | −70.5% |
| 800px / 60fps close | −90.1% | −69.8% |

（全部 12 组在 `assets/rendered/door_fl_v3/*/*_delta/budget.json`。）

### 4.3 回答 Part 16：600/60 与 800/60 降低多少

| | 全画布 | alpha crop | difference crop | 相对全画布 |
|---|---|---|---|---|
| 600px / 60fps | 33.4 ms（200%） | 10.1 ms（60%） | **3.0 ms（18%）** | **−91.0%** |
| 800px / 60fps | 59.5 ms（357%） | 17.9 ms（107%） | **5.6 ms（34%）** | **−90.5%** |

> **ESTIMATED ONLY.** 这些是 Mac 单帧解码实测值按像素数外推、再乘 A7 相对系数
> 得到的估计。**真机数字仍然是 UNKNOWN UNTIL DEVICE TEST。**
> 另外：解码只占一帧成本的一部分，合成/上屏/UI 逻辑还没算进去，所以
> "解码占预算 18%"**不等于**"能跑 60fps"。

---

## 5. 运行时架构（Part 17）

`include/dashboard/delta_animation.h` + `src/core/delta_animation.cpp`。

```
DeltaAnimationClip   { id, base_asset, canvas, fps, frames[] }
DeltaAnimationFrame  { region{x,y,w,h}, duration_ms, asset }
IDeltaSurface        { blitRegion(asset, dst) }      ← 平台原语
DeltaAnimationPlayer { load/play/pause/stop/setFrame/draw/tick/getDirtyRect }
```

语义要点（都有测试覆盖，`tests/delta_animation_tests.cpp`）：

- `tick(dt, surface, base_x, base_y)` 返回**屏幕坐标**下本次 tick 真正需要
  重绘的并集矩形（跨帧时取并集，不是只返回当前帧）。
- `getDirtyRect()` 返回**clip 坐标**下当前帧的矩形。
- 时钟不会跳过片尾，最后一帧**保持**（不是循环）。
- `stop()` 回到 base 姿态并把索引归零，所以"关门后停在关闭状态"不需要重载。
- `totalDirtyRect()` = 所有帧矩形的并集，用于判断固定 tight canvas 是否便宜。

**没有改动任何现有渲染路径。** `IRenderBackendV6` / `HorizonRendererV6` /
EasyUI 后端都保持原样，这层是新增的。

### 5.1 ZKImageAnim 能不能直接做 delta transport？

```
BLE 式的回答方式（不做假设）：
ZKImageAnim delta transport verdict = UNKNOWN
```

已知（`docs/RENDERING_CAPABILITY_AUDIT.md` §9.1，来自实机导出符号）：
ZKImageAnim 是"解码器 + 定时器 + 逐帧读取"的**流式**播放器，
`createDecoder / readFrame / updateFrame / drawAnim`，
所以它**不需要**整段常驻 RAM。

**不知道**的是：同一个 ZKImageAnim 实例能否接受**尺寸不同**的帧，
以及能否把某一帧画在**任意 x/y**。导出符号列表回答不了这个问题，
SDK 头文件里也没有 ZKImageAnim。所以结论只能是 UNKNOWN。

### 5.2 两个 fallback（都要真机验证后才能采用）

| fallback | 做法 | 代价 |
|---|---|---|
| **FixedTightCanvas**（默认建议） | 每段动画用一个固定 canvas，尺寸 = 该动画的 union dirty rect；每帧仍只解码自己那块，但画布尺寸统一 | 每帧按 union 面积付解码成本：600/60 从 18% 回到约 60%（仍优于全画布 200%） |
| **CustomStreamedDecode** | 自己做 PNG 流式解码 + 自己合成进帧缓冲，再作为普通图像交给 EasyUI | 要实现解码与合成，但可以拿到真正的 per-frame 任意尺寸/位置 |

`recommendedDeltaFallback(UNKNOWN)` 目前返回 **FixedTightCanvas** ——
在拿到真机结论前，选实现代价低、且**继续流式**的那一个。

**不会**在没有真机验证前替换 ZKImageAnim。

---

## 6. 数据契约

`animation.json` 顶层：

| 字段 | 含义 |
|---|---|
| `id` / `kind` | 动画 id；`kind = "delta_animation"` |
| `base` | 静态底图文件名 |
| `canvas` | 整画布尺寸 |
| `fps` / `duration_ms` | 播放参数 |
| `padding` / `threshold` | 生成参数（必须随资产一起走，否则无法复现） |
| `compositing` | `"rectangle_replacement"` |
| `frames[]` | 每帧 region + anchor + duration |
| `stats` | 平均/峰值区域、画布占比、PNG 字节、解码估计 |
| `verification` | `pixel_equal` / `worst_mismatched_px` / `worst_channel_diff` |

## 7. 未验证 / 未做

- 真机解码与合成实测（**UNKNOWN UNTIL DEVICE TEST**）。
- ZKImageAnim 的 per-frame 尺寸/位置能力。
- 多矩形（把脏区分成 2-3 个矩形）能再省多少 —— 本轮只做单矩形，
  留作后续优化。
- atlas 打包（`anchor_*` 字段已为此预留）。
