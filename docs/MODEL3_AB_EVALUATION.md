# MODEL A vs MODEL B — 结构评估与 A/B 渲染检查点

日期：2026-09-15
分支：`feature/v6-cockpit`
Blender：**5.2.2 LTS**（`/Applications/Blender.app/Contents/MacOS/Blender`，CLI 可用）

> 本轮为**第一个正式视觉检查点**。生成 `horizon_model_A.png` /
> `horizon_model_B.png` 后即停止，不继续制作动画。

---

## 1. 两套模型身份

| | MODEL A | MODEL B |
|---|---|---|
| 名称 | Tesla 2018 Model 3 | Tesla M3 model |
| 上传者 | Ameer Studio | wintrez |
| Sketchfab | `3d-models/5ef9b845aaf44203b6d04e2c677e444f` | `3d-models/3a602469d7874d1397efa67182198705` |
| License | CC BY 4.0 | CC-BY 4.0 |
| 我们拿到的格式 | **FBX（作者原始格式）** | **BLEND** |

`assets/ATTRIBUTION.md` 已登记完整署名与哈希。

---

## 2. 原始文件信息

下载目录（`assets/source/download/`，**git-ignored，不入库**）：

```
model_a_ameer/source/tesla_car1.fbx              26,637,068 B
model_a_ameer/textures/                          22 个 PNG/JPEG
model_b_wintrez/teslaMSFullSketchfab001.blend    19,045,644 B
```

⚠️ **注意**：`assets/source/download/` 里另有 4 个 **333–353 字节**的文件
（`tesla-2018-model-3.zip`、`tesla-m3-model.zip`、`*.glb`），它们**不是模型**，
而是 Sketchfab 签名链接过期后返回的 S3 错误页
（`AccessDenied / Request has expired`）。真正的文件是用户后来解压/保存到
`~/Downloads/tesla-2018-model-3/` 与 `~/Downloads/source/` 的上述三个。
**MODEL A 的 GLB 从未成功下载**，所以第 7 节的 FBX vs GLB 比较无法进行。

## 3. SHA-256

| 文件 | SHA-256 |
|---|---|
| MODEL A FBX | `5992165a9d7aa1e95940bc11a809839a9248e0f9031d8a4e95df5c977ac788a5` |
| MODEL B BLEND | `d4efbdfcae3f47419ae00d852879d9173cb2495a70155d3d3b18d3da2091453d` |

## 4. Blender import 结果

两个文件都用 **Blender 5.2.2 CLI 成功导入**（非破坏性；未保存回源文件）。

| | MODEL A (FBX) | MODEL B (BLEND) |
|---|---|---|
| 导入 | ✅ 成功（FBX 7400） | ✅ 成功 |
| 场景单位 | METRIC / 1.0 | METRIC / 1.0 |
| 原始世界尺寸 (X,Y,Z) | 2.449 × 5.258 × 1.578 m | 7.327 × 16.407 × 5.090 m |
| 长度轴 | **Y**（车头 = +Y） | **Y**（车头 = −Y） |
| 归一化后尺寸 | **4.694 × 2.186 × 1.409 m**，贴地 z=0 | **4.694 × 2.096 × 1.456 m**，贴地 z=0 |
| 缩放系数 | 0.89266 | 0.28610 |

> 两个模型的长度轴与朝向**相反**，且 MODEL B 尺度约为真实尺寸的 3.5 倍；
> 归一化脚本按 `--nose` 参数处理，两者在 A/B 渲染中使用**完全相同的最终尺寸与朝向**。

## 5. object / mesh / material 数

| | MODEL A | MODEL B |
|---|---:|---:|
| 对象总数（含空物体） | 155 | 1 |
| Mesh 对象 | **107** | **1** |
| 材质 | **58** | 25 |
| 多边形 | 684,315 | 126,258 |
| 顶点 | 383,815 | 134,283 |
| 贴图文件 | 22（含 carpaint/tyre/rims/leather/lcd/vehiclelights 等） | 0（纯材质） |
| 集合名 | — | `M3`（佐证为 Model 3） |

## 6. 部件分离情况

### MODEL A — 大量部件已经是独立对象

| 目标部件 | 找到的对象 | 顶点 |
|---|---|---|
| Body | `body`, `bodysills`, `chassis`, `base` | 28,401 + 6,434 + 6 + 14,219 |
| Glass | `glass`, `windscreen_ok` | 3,272 + 950 |
| **Door_FL** | **`door_lf`** | 19,934 |
| **Door_FR** | **`door_rf`** | 17,865 |
| **Door_RL** | **`door_lr`** | 14,082 |
| **Door_RR** | **`door_rr`** | 14,071 |
| **Frunk** | **`bonnet_ok`**, `chrome_bonnet_ok`, `frunkplastic` | 2,651 + 2,026 + 124 |
| **Trunk** | **`boot`**, `black_boot`, `tembus_boot_ok` | 6,947 + 3,158 + 1,438 |
| Interior | `Seat Leather white`（座椅）, `interiorlights` | 23,950 + 193 |
| 灯组 | `turn_indicat_l/r`, `indicator_lights_l/r`, `foglights_l/r`, `rear_lightsl/r`, `light_breake`, `lightrevese_boot`, `chrome_Lights_head_l` | 各自独立 |
| 轮毂/制动 | `hub_lf/rf/lb/rb`（4 个独立）, `wheels` + `wheels.001`（**每轴一个对象，含左右两轮**）, `suspensi`, `suspensi2`, `movsteer_1.0` | — |

### MODEL B — 单一合并网格

- 只有 **1 个 mesh 对象** `Full Car Extra`
- 内含 **61 个连通块（loose parts）**
- 按材质分布：`TireRubber` 28,960 面、`GlossyInterior` 32,850、`carpaint` 19,526、`BlackWash` 6,908、`innerLights` 4,672、`RedLight` 1,800 …
- **主车身是 1 个连通块**（17,495 顶点，尺寸 6.54×16.41×4.34），**四门焊接在车身里**
- 轮子/大灯内胆/尾灯/卡钳/玻璃是独立连通块（左右成对，坐标对称）

## 7. MODEL A 的 FBX vs GLB

**无法比较** —— MODEL A 的 GLB 未成功下载（见第 2 节，`.glb` 是 333 字节的
过期错误页）。因此本轮只评估 **FBX 原始格式**。

若后续需要 GLB 作对照，请重新在 Sketchfab 下载（链接有效期很短）。

## 8. 门动画准备度

| | 判定 |
|---|---|
| **MODEL A** | ✅ **READY**。四个门是独立对象，且**原点就在铰链处**：`door_lf` 原点相对自身包围盒中心沿长度轴偏移 **0.7117 m**，而门长 1.4299 m（半长 0.715 m）——完全吻合"原点位于门一端的铰链轴"的预期。后门同样是 0.5975 m / 门长 1.2819 m。**可直接用单轴旋转做开门动画，无需改拓扑** |
| **MODEL B** | ❌ **NOT READY**。四门焊接在 `Full Car Extra` 主车身连通块内；要做开门动画必须**从车身切出门板**（破坏性、需人工判断边界与密封条） |

## 9. frunk 准备度

- **MODEL A**：✅ `bonnet_ok`（前舱盖）+ `chrome_bonnet_ok` + `frunkplastic` 三个独立对象，可直接旋转
- **MODEL B**：❌ 属于主车身连通块，需切割

## 10. trunk 准备度

- **MODEL A**：✅ `boot` + `black_boot` + `tembus_boot_ok`，独立
- **MODEL B**：❌ 属于主车身连通块，需切割

## 11. 灯光准备度

- **MODEL A**：✅ 前后灯**逐个独立**：`chrome_Lights_head_l`（大灯）、`foglights_l/r`（雾灯）、`indicator_lights_l/r` + `turn_indicat_l/r`（转向灯）、`rear_lightsl/r`（尾灯）、`light_breake`（刹车灯）、`lightrevese_boot`（倒车灯）、`light_turn_lr_boot`/`light_turn_rr_boot`（尾灯转向）。材质名也按位置区分（`indicator lf`/`indicator rf`/`left rear light`/`right rear light`）
- **MODEL B**：🟡 灯组是独立连通块（`innerLights`、`RedLight`、`OrangeLights`、`innerLightMetals`），但**左右成对合并在同一连通块**、且都塞在同一个 mesh 对象里；要单独控制某一侧需要再拆分

## 12. glass / interior / wheel

| 项 | MODEL A | MODEL B |
|---|---|---|
| Glass | ✅ `glass` + `windscreen_ok` 独立，且材质分开 | 🟡 玻璃是独立连通块（`glass`/`glassDark`），但在合并网格内 |
| Interior | ✅ **完整**：`Seat Leather white`（23,950 顶点座椅）、`Carpet`/`Carpet_Light`、`belt`/`chromeBELT`（安全带）、`movsteer_1.0`（方向盘）、`interiorlights` | 🟡 有内饰材质（`GlossyInterior` 32,850 面、`LightGrayInterior`、`BlackSuade`、`Wood`），但同样在合并网格内 |
| Wheel | 🟡 `hub_lf/rf/lb/rb` 四个独立 + `wheels`/`wheels.001` **每对象含同一轴左右两轮**（需拆 4 个才能做单轮动画；本仪表不需要单轮动画的话可直接用） | 🟡 轮胎与轮毂是独立连通块，按 ±X 对称分布，但都在合并网格内 |

---

## 13. MODEL A vs MODEL B 完整评分

评分基于**可客观核实的结构/元数据**；视觉质量项按几何密度与命名完整性保守给分，
**最终外观必须由你目视 A/B 图确认**（见第 17 节）。

| 评分项 | MODEL A | MODEL B | 说明 |
|---|---:|---:|---|
| 2018 Exterior Accuracy | **9** | 7 | A 的名字即 "Tesla 2018 Model 3"；B 年代未标注 |
| Overall Exterior Accuracy | 8 | **8** | 两者都是完整车身外形，无法仅凭结构定优劣 |
| Body Proportions | **9** | 8 | A 归一化后 4.694×2.186×1.409，比例贴近真实（含后视镜） |
| Topology | 7 | **7** | A 107 个独立件（边界清晰）；B 单网格但仅 126k 面（更轻） |
| Separated Parts | **10** | 2 | A 四门/盖/灯/座椅全独立；B 仅 1 对象 |
| Door Animation Readiness | **10** | 2 | A 原点已在铰链；B 需切车身 |
| Frunk Animation Readiness | **9** | 2 | A 独立盖件；B 需切割 |
| Trunk Animation Readiness | **9** | 2 | A 独立尾门；B 需切割 |
| Lighting Separation | **9** | 5 | A 逐灯独立；B 左右合并 |
| Glass Quality | **9** | 7 | A 独立且分材质；B 有 glass/glassDark 但合并在网格内 |
| Wheel Quality | 7 | **8** | A 每轴 2 轮合一（需再拆）；B 每轮独立连通块但合并 |
| Interior Quality | **9** | 7 | A 有完整座椅/地毯/安全带/方向盘；B 有内饰材质组 |
| Material Potential | 6 | **8** | B 无贴图、纯材质（25 个），更易做统一 PBR；A 有 58 材质 + 22 贴图（需清理） |
| Blender Import Quality | **10** | 7 | A 直接可用；B 有 `hide_render=True` 陷阱（见第 15 节） |
| Pipeline Compatibility | **10** | 5 | A 的部件命名可映射到标准名；B 单网格需先拆件 |
| License | 5 | **9** | A 来源不可考（8 账号重复上传）；B 单一可信作者 |
| **TOTAL** | **128 / 160** | **94 / 160** | |

## 14. 工程判断（不只按总分）

两个模型的问题**不是同一种问题**，所以结论不能只看分数：

- **MODEL A 的强项是"结构"**：四门/前盖/尾门/灯组/座椅全部独立，且门原点
  已经在铰链位置——这正好命中我们整条动画管线的要求。它的问题是
  **许可证来源不可考**（第 15 节）。
- **MODEL B 的强项是"来源干净 + 材质轻"**：单一作者、纯材质无贴图、
  126k 面（比 A 少 82%），非常适合做统一 PBR。但它的门焊在车身里，
  要动门就必须做**破坏性切割**——这正好触碰你明确禁止的"未经验证的
  不可逆 mesh surgery"。

**工程结论**：如果目标是"能开门的 Horizon 车辆"，**MODEL A 是唯一不需要
破坏性改造就能进入动画阶段的候选**；MODEL B 要走同一条路，等于先做一次
高风险的建模工作。若把"许可证完全可追溯"当作硬约束，则 MODEL B 更稳，
但要接受"门不能动、或必须人工切件"的代价。

## 15. 风险

| 风险 | 说明 | 缓解 |
|---|---|---|
| **MODEL A 来源不可考** | 该网格（684,315 面）在 Sketchfab 上被 **8 个不同账号**上传（dannzjs / Ameer Studio / Justin.Brouwer / ChoochooLi Models / DisneyCars / TeslaFan / hiruja0119 / custom fortnite skin）。原始作者无法确认；其中一个账号名带游戏皮肤特征。文件名/材质命名混有印尼语（`platnomor`、`hitam`）与俄语（`dvorleft`），符合"社区流传件"特征 | ① **不要把模型提交进仓库**（保持 git-ignored，仅登记哈希）；② 个人自用改造风险低；③ 若未来商业化销售硬件，必须换成来源可追溯的资产 |
| MODEL B 需要切割车身 | 门/盖与车身同属一个连通块 | 先做 `part_report.py` 报告 + 人工确认，再决定是否值得投入 |
| MODEL B 尺度异常 | 16.4 m（真实 4.69 m 的 3.5 倍） | 已在归一化中修正；若用原始文件必须重新归一化 |
| MODEL B 隐藏对象 | `Full Car Extra` 带 `hide_render=True`，直接渲染是**空帧**（本轮已实际踩到） | `ab_render.py` 已强制开启可见性并打印告警 |
| MODEL A 贴图 | 22 张贴图（含 `remap2/3.png` 重映射图），材质 58 个，直接用于 PBR 会偏"改装车"风格 | 第一轮已同时输出 `unified` 版本用于纯几何判断 |
| GLB 缺失 | MODEL A 的 GLB 未下载成功 | 需要时重新下载；不影响 FBX 路线 |

## 16. 推荐 master

```text
RECOMMENDED MASTER:       MODEL A（技术上）
RECOMMENDED SOURCE FORMAT: FBX（原始格式，结构最完整；GLB 未取得无法对照）
```

理由（结构证据，非视觉断言）：

1. 四门 + 前盖 + 尾门**已是独立对象**，且门原点已在铰链位置 → 动画零改造
2. 灯光逐个独立并带位置化材质名 → 刹车/转向/大灯可直接驱动
3. 含完整内饰与座椅，未来需要内饰视角时不必换模型
4. 归一化后尺寸贴近真实 Model 3

**但此推荐带一个明确前提**：许可证来源问题由你拍板。如果决定不接受该风险，
则维持 MODEL B 作为 master，并接受"门不可动"或追加人工切件工作。

## 17. 仍需人工视觉判断的项目

**我无法视觉判断以下内容** —— 必须由你看 A/B 图确认：

1. 哪一个更像你真实的 2018 Model 3（尤其前脸、比例、姿态）
2. 车身表面质量（是否有明显凹痕/褶皱/接缝错误）
3. 灯组造型准确度
4. 轮毂样式与实际车辆是否接近
5. 材质观感（A 的原始材质 vs B 的纯材质）
6. unified 版本下哪一个的几何更干净
7. 车辆在 Horizon 里的整体高级感

### 本轮产出的图片

| 文件 | 说明 |
|---|---|
| `assets/rendered/ab/model_A_original.png` | A，原始材质，1800×1280 透明 |
| `assets/rendered/ab/model_A_unified.png` | A，统一测试材质（银车漆/深玻璃/石墨轮/黑胎/灯关闭） |
| `assets/rendered/ab/model_B_original.png` | B，原始材质 |
| `assets/rendered/ab/model_B_unified.png` | B，统一测试材质 |
| **`assets/rendered/ab/horizon_model_A.png`** | **A 合成进 Horizon（1920×480）** |
| **`assets/rendered/ab/horizon_model_B.png`** | **B 合成进 Horizon（1920×480）** |

两张 Horizon 图的**唯一差异在车辆区域**（已用像素校验：车辆框外差异 = 0 像素），
速度 88 / D 挡 / SOC / 续航 / 时钟 / UART 等其他元素完全一致，使用同一 mock 状态。

## 18. 已完成的非破坏性保证

- 两个源文件**从未被修改**（所有操作在内存副本上进行，渲染脚本不保存 .blend）
- 未执行 decimate / join / separate / 修改拓扑 / 修改材质 / 修改 origin / 修改 pivot
- 唯一"改动"是渲染时**内存中**的可见性开关与归一化变换
