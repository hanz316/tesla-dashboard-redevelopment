# 车辆资产生产管线（Blender → PNG 序列 → 运行时）

状态：管线已建立，**除 Blender 渲染步骤外全部本地验证通过**。
Blender 当前**未安装**（本仓库不自动安装），装上后即可端到端运行。

---

## 1. 目录结构

```
assets/
  source/blender/
    model3.blend                # 由 build_model3_scene.py 生成（含全部 action）
    model3.manifest.json        # action → 对象/帧范围，渲染脚本据此驱动
  rendered/vehicle/
    base/000.png                # 静态车辆（合成基底）
    door_fl/000..015.png        # 门开动画（16 帧）
    door_fr/ door_rl/ door_rr/
    frunk/000..013.png trunk/000..013.png
    brake_on/000.png headlight_on/000.png     # B 类静态叠加
    indicator_left/ indicator_right/ hazard/  # C 类 12 帧循环
  manifest.json                 # 资产 ID → 文件/序列（运行时与预览器共用）
  preview/                      # Mac 预览器输出（不提交，见 .gitignore）
tools/
  blender/build_model3_scene.py      # 构建场景 + 全部 action → model3.blend
  blender/render_vehicle_assets.py   # --action/--all 自动渲染 + 降采样 + 预算
  assets/generate_placeholder_frames.py  # 无 Blender 的占位渲染（同契约）
  assets/check_budget.py             # RAM/解码预算闸门
  assets/verify_alignment.py         # 画布/锚点/相机漂移校验
  assets/pack_atlas.py               # 可选：序列 → 图集
```

---

## 2. 物体拆分（固定，不得改名）

`Body`、`Glass`、`Wheel_FL/FR/RL/RR`、`Door_FL/FR/RL/RR`、`Frunk`、
`Trunk`、`Headlight_L/R`、`Brake_L/R`、`Indicator_L/R`、`Interior`

**所有状态共享同一模型、同一材质、同一灯光、同一相机、同一坐标系。**
禁止用不同图片"模拟"不同车辆状态。

---

## 3. Camera_Horizon（固定，禁止动画修改）

- 类型：正交（`ORTHO`），`ortho_scale = 5.55` —— 保证各状态构图完全一致
- 位置：`(-5.30, -4.55, 3.85)`，通过 `TRACK_TO` 约束看向 `(0, 0, 0.62)`
- 视角：**高位后 3/4 视角**，可见车顶、车尾、左右车身、四门、前/后备箱
- 构图：车辆居中，占画面约 0.75，刻意**不做汽车广告大图**
- 输出画布：`356×236`（与 V6 资产契约一致），可超采样后离线缩小

仪表中央显示区域预计 600–850 × 300–420 px；渲染按 356×236 生成，
运行时按需放大到目标框（`vehicle_visual.width/height`）。

---

## 4. 动画 Actions

| Action | 通道 | 帧数 | 类别 |
|---|---|---:|---|
| `Door_FL_Open` `Door_FR_Open` `Door_RL_Open` `Door_RR_Open` | 旋转 | 16 | A |
| `Frunk_Open` `Trunk_Open` | 旋转 | 14 | A |
| `Brake_On` `Headlight_On` | 发光强度 | 1 | B |
| `Indicator_Left` `Indicator_Right` `Hazard` | 发光强度（整周期）| 12 | C |

分类理由见 `docs/ANIMATION_STATE_STRATEGY.md`。

---

## 5. PNG 输出规范（硬性）

1. **透明背景**：`film_transparent = True`，PNG RGBA
2. **固定画布**：所有帧同一分辨率（356×236），**禁止逐帧自动裁切**
3. **固定锚点**：车辆在画布中的位置逐帧一致
4. **固定相机**：渲染期间不得改变 `Camera_Horizon` 变换
5. **固定包围盒**：只有运动部件变化，其余像素完全一致

校验：`python3 tools/assets/verify_alignment.py --all assets/rendered/vehicle`
（检查画布一致性、边缘裁切、运动区域占比；运动区域过大即判定相机漂移）

---

## 6. 渲染命令

```bash
# 1) 构建场景（生成 model3.blend + manifest）
blender -b -P tools/blender/build_model3_scene.py

# 2) 查看可用 action
blender -b -P tools/blender/render_vehicle_assets.py -- --list

# 3) 渲染单个 / 全部（自动降采样到 356×236 并跑预算检查）
blender -b -P tools/blender/render_vehicle_assets.py -- --action Door_FL_Open
blender -b -P tools/blender/render_vehicle_assets.py -- --all
```

**不需要手工在 GUI 点 Render。**

### 没有 Blender 时（当前状态）

```bash
python3 tools/assets/generate_placeholder_frames.py --all --budget
```

占位渲染器产出**完全相同契约**的帧（透明 RGBA / 固定画布 / 像素对齐），
用于验证下游管线与驱动 Mac 预览器；Blender 就绪后以真实几何重新渲染同一
目录即可替换。

---

## 7. 预算流水线

每次渲染后自动执行（`render_vehicle_assets.py` 内置，也可单独跑）：

```bash
python3 tools/assets/check_budget.py --sequence assets/rendered/vehicle/door_fl
```

报告内容：帧数、分辨率、压缩体积、单帧解码大小、全序列解码大小、
设备解码耗时估算、占 30fps 预算比例。

**目标设备基线**：1920×480、RAM ≈250MB（可用 ≈183MB）、纯 CPU 渲染、
30fps 目标；单动画解码占用上限 30% 帧预算。

当前占位序列实测（356×236）：

| 序列 | 帧数 | 单帧解码 | 全量解码 | 设备解码估算 | 占预算 |
|---|---:|---:|---:|---:|---:|
| door_* | 16 | 0.32 MB | 5.14 MB | 6.9 ms | 21% |
| frunk/trunk | 14 | 0.32 MB | 4.49 MB | 6.9 ms | 21% |
| indicator/hazard | 12 | 0.32 MB | 3.85 MB | 6.9 ms | 21% |
| brake/headlight | 1 | 0.32 MB | 0.32 MB | 6.9 ms | 21% |

→ 结论：**同时最多 1–2 个序列动画**；A 类只在过渡瞬间解码并释放。

---

## 8. 版本与许可

- 当前几何为**自建占位模型**，不下载任何第三方/许可不明的 Tesla 模型
- 正式 Model 3 资产的来源与许可在管线全部跑通后单独决策
- 占位资产在文档与代码中均标注 `placeholder`，不得当作最终美术
