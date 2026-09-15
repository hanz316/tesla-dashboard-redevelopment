# Tesla Model 3 3D 资产候选审查

日期：2026-09-15（实际联网检索，非推测）
检索来源：Sketchfab API v3、BlenderKit API、GitHub Search API、Poly Pizza、通用网页搜索

**结论先行**：不存在 **CC0** 的 Tesla Model 3 模型；可用且许可最宽松的是
Sketchfab 上的 **CC-BY 4.0** 资产（可商用、可修改、可再分发，**需署名**）。
一个"看起来最漂亮"的模型（684,315 faces）被 8 个不同账号重复上传，来源不可
验证，**必须排除**。

---

## 1. 检索结果概览

| 来源 | 结果 |
|---|---|
| Sketchfab（downloadable, "tesla model 3"）| 24 个可下载结果，绝大多数 CC-BY 4.0 |
| BlenderKit | 62 个 tesla 相关；Model 3 为**付费**（royalty_free）；免费的只有 Cybertruck（CC0）与 Model S |
| GitHub | 无可用 Model 3 网格资产（仅 1 个无许可证的 Blender 练习仓库）|
| Poly Pizza | 仅有 "Truck"/"Cybertruck"（CC-BY 3.0，低多边形，无拆件）|

---

## 2. 候选表

字段说明：`faces/verts` 取自 Sketchfab 公共 API；`拆件` 一列是**根据公开
描述**的初判，最终必须用 `tools/assets/inspect_model.py` 或
`tools/blender/part_report.py` 在真实文件上验证（见第 5 节）。

| # | 名称 | 作者 | URL | 格式 | faces / verts | 贴图/材质 | Interior | 门已拆 | trunk | frunk | 轮毂 | License | 商用 | 修改 | 再分发 | 可进 GitHub 仓库 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **Tesla M3 model** | wintrez | `sketchfab.com/3d-models/3a602469d7874d1397efa67182198705` | glTF/FBX/OBJ | 247,368 / 136,524 | 无贴图，纯材质（"Built in blender"）| ✗ | 待验证 | 待验证 | 待验证 | 待验证 | **CC-BY 4.0** | ✅ | ✅ | ✅（需署名）| ✅ 可（附署名）|
| 2 | **2024 Tesla Model 3 + Interior** | tonielpro520 | `.../61ddcbdbd3854c239e0c95bf60b00022` | glTF/FBX/OBJ | 167,747 / 100,509 | 未说明 | **✅ 有内饰** | 待验证 | 待验证 | 待验证 | 待验证 | **CC-BY 4.0** | ✅ | ✅ | ✅ | ✅ 可（附署名）|
| 3 | Tesla Model 3 2020 | ItsDiyor | `.../596bbf266fce430181e6d0e2b1903364` | glTF/FBX/OBJ | 176,714 / 97,643 | 未说明 | ✗ | 待验证 | 待验证 | 待验证 | 待验证 | **CC-BY 4.0** | ✅ | ✅ | ✅ | ✅ 可（附署名）|
| 4 | Tesla model 3 2024 | brandonleong28 | `.../36c52f3f89f6439c90310f14e8ff33f2` | glTF/FBX/OBJ | 179,692 / 102,586 | 未说明 | ✗ | 待验证 | 待验证 | 待验证 | 待验证 | **CC-BY 4.0** | ✅ | ✅ | ✅ | ✅ 可（附署名）|
| 5 | Tesla Model 3 | ZapupaNekra | `.../98e7bd5892464640baa9cf6afcd60c2c` | glTF/FBX/OBJ | 215,474 / 123,249 | 未说明 | ✗ | 待验证 | 待验证 | 待验证 | 待验证 | **CC-BY 4.0** | ✅ | ✅ | ✅ | ✅ 可（附署名）|
| 6 | Tesla Model 3 | rxlly | `.../4c8bbf44a65945d2896ef7be42ce217f` | glTF/FBX/OBJ | 174,801 / 99,303 | **"Un-Colored"（无材质）** | ✗ | 待验证 | 待验证 | 待验证 | 待验证 | **CC-BY 4.0** | ✅ | ✅ | ✅ | ✅ 可（附署名）|
| 7 | VEHICLE - TESLA MODEL 3 | Thcyrax | `.../43512c27667f412297bced6b9857a735` | glTF/Unity | **4,334 / 2,209** | 未说明，game-ready | ✗ | **描述明确："Wheel and car body are in separate meshes"**；旋转轴已配置 | ? | ? | ✅ 已拆 | **CC-BY 4.0** | ✅ | ✅ | ✅ | ✅ 可（附署名）|
| 8 | Tesla Model 3 | David_Holiday | `.../123c10f376ec4f18b93c73afc382808b` | glTF | 27,012 / 16,623 | 未说明 | ✗ | 待验证 | 待验证 | 待验证 | 待验证 | CC-BY 4.0 | ✅ | ✅ | ✅ | ⚠️ 描述是上传模板文本，质量与来源需先目视确认 |

> 注：第 8 项另一个 737,161 faces 版本描述里写的是
> **"Lamborghini Aventador LP700"**，属复制粘贴的模板痕迹，可信度低。

### 检索的可复现性

上表可由脚本重新生成（无需登录）：

```bash
python3 tools/assets/find_model3.py --json /tmp/candidates.json
```

脚本会自动标记两类必须排除的候选：**重复网格**（同一 face/vertex 数出现在
多个账号）与**游戏提取/照片扫描**（描述关键词命中）。注意搜索结果也会返回
Model S/X/Cybertruck，需按车型过滤。

## 3. 明确排除的候选（重要）

| 模型 | 排除原因 |
|---|---|
| faces **684,315** / verts **364,387**（dannzjs、Ameer Studio、Justin.Brouwer、ChoochooLi Models、DisneyCars、TeslaFan、hiruja0119、**custom fortnite skin** 共 8 个账号）| **同一网格被 8 个账号重复上传**，原始作者不可考；其中一个账号名为 "custom fortnite skin"（游戏提取特征）。**许可证来源不可信，禁止使用** |
| "Tesla Model 3" by **Gerda**（624,288 faces，Free Standard）| 描述自述 **"comes from a BeamNG.Drive mod ... from modland.net"** → **游戏提取**，明确禁止 |
| "Day 288: Tesla Model 3" by alban（1,577,266 verts）| **照片扫描（SiteScape 展厅扫描）**：拓扑为三角汤、不可拆件、无 PBR 材质，不适合作为动画母体 |

## 4. 技术评分（满分 10）

评分依据：公开元数据 + 描述 + 我们管线的要求（轮廓准确、可拆件、可动画、
离线渲染、许可清晰）。**"可拆件"未经文件验证，因此该项按描述保守给分。**

| # | 候选 | Exterior | Topology | Separated Parts | Materials | Animation Readiness | Performance | License | 总分 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | wintrez Tesla M3 model | 8 | 7 | 5 | 8 | 6 | 7 | **10** | **51** |
| 2 | tonielpro520 2024 + Interior | 8 | 7 | 5 | 7 | 6 | 8 | **10** | **51** |
| 3 | ItsDiyor Model 3 2020 | 7 | 7 | 5 | 7 | 6 | 8 | **10** | 50 |
| 4 | brandonleong28 2024 | 8 | 7 | 5 | 7 | 6 | 8 | **10** | 51 |
| 5 | ZapupaNekra | 7 | 6 | 5 | 6 | 6 | 7 | **10** | 47 |
| 6 | rxlly | 7 | 7 | 5 | 4（无材质）| 6 | 8 | **10** | 47 |
| 7 | Thcyrax (low-poly) | 5 | 6 | **8**（已确认拆件）| 5 | 7 | **10** | **10** | 51 |
| 8 | David_Holiday | 6 | 6 | 5 | 6 | 6 | 9 | **10** | 48 |
| — | 684k 重复上传组 | 9 | 7 | ? | 9 | ? | 5 | **2（来源不可信）** | 排除 |

**评分说明**：`Separated Parts` 全部保守给 5，因为我们**尚未拿到文件**验证
（Sketchfab 下载需要账号认证，见第 5 节）。Thcyrax 因描述明确拆件给 8。

## 5. 下载与验证的限制（必须如实说明）

Sketchfab 的下载 API 需要账号认证：

```
GET https://api.sketchfab.com/v3/models/<uid>/download
→ {"detail":"Authentication credentials were not provided."}
```

我**没有擅自注册账号**。因此：

- 本文件的许可证、面数、作者信息全部来自**公开 API**（可复核）
- "是否已拆分四门/trunk/frunk" 这一列**必须拿到文件后才能确定**
- 我已在仓库准备好**自动检测工具**，文件一到即可得出结论（见下）

### 拿到文件后一键出结论

```bash
# glTF / GLB / OBJ（无需 Blender）
python3 tools/assets/inspect_model.py model.glb --json report.json

# FBX / BLEND（需要 Blender）
blender -b -P tools/blender/part_report.py -- --input model.fbx

# 导入 + 归一化 + 重命名为标准部件名
blender -b -P tools/blender/import_model3.py -- --input model.glb
```

`inspect_model.py` 会直接回答：`doors_separated / frunk_separated /
trunk_separated / wheels_separated / glass_separated / interior_present`，
并列出 `ambiguous`（例如只有 "door" 没有左右）与 `unmapped`。

## 6. 推荐

### BEST CANDIDATE

**#1 wintrez "Tesla M3 model"**（CC-BY 4.0，247k faces，纯材质无贴图）

理由：

- **许可证最清晰**：作者自述 "Built in blender"，非转载、非游戏提取
- **无贴图依赖**：对我们是最优情况——车身质感本来就要自己做 metallic paint，
  没有贴图反而避免了解包/重烘焙的一堆麻烦
- 面数适中（247k），离线渲染完全够用，且可 decimation
- 若它没有拆门，我们**可以自己拆**（见风险）——因为车辆本体是"干净的自制
  模型"，比游戏提取件更容易干净拆件

### BEST FULLY OPEN CANDIDATE

同上（#1）。**不存在 CC0 候选**；CC-BY 4.0 已是可用许可中最宽松的一档。

### 备选

- **#2 tonielpro520 "2024 Tesla Model 3 + Interior"** —— 需要内饰时选它
  （Highland 前脸与 2018 车型不同，注意与本车年份匹配）
- **#7 Thcyrax** —— 唯一**确认已拆件**的候选，但仅 4,334 faces，属于低多边形
  游戏风；可作为**管线联调用的替代件**（先跑通流程，再换高模）

## 7. License 是否允许我们使用（逐条回答）

CC-BY 4.0（creativecommons.org/licenses/by/4.0/）明确允许：

- ✅ **商用**（本仪表项目非商业，更无问题）
- ✅ **修改**（我们可以拆件、改材质、做动画）
- ✅ **再分发**（可以放进我们的 GitHub 仓库）
- ⚠️ **必须署名**：需在仓库中保留作者名、模型名、来源 URL、许可证名称

因此：**可以进仓库，但必须附署名文件**（见第 9 节下一步）。

⚠️ 另需注意：CC-BY 覆盖的是**模型的著作权**，不涉及 Tesla 的商标/外观设计
权利。个人自用改造无碍；若未来商业化销售硬件，需另行评估。

## 8. 能否直接拆四门 / frunk / trunk

**目前无法确认**（没有文件）。两种情形：

1. 模型已分件 → `import_model3.py` 直接重命名为标准名，立刻可做动画
2. 模型是单一网格 → 需要拆件，**我们不做自动不可逆切割**：
   - 先用 `part_report.py` 生成"哪些可依据材质/连通块自动拆"的报告
   - 人工确认视觉效果后再执行

对 #1（wintrez）的判断：作者说 "no textures, pure materials"，说明模型是
按材质分件的（车身/玻璃/轮胎各自材质），**大概率可以按材质干净拆分**，
但必须验证。

## 9. 下一步需要我做什么

1. **你下载模型**（Sketchfab 需要登录你的账号）：
   - 首选：wintrez "Tesla M3 model" → 下载 **glTF** 格式
   - 备选：tonielpro520（需要内饰时）
   - 放到 `assets/source/downloads/`（该目录已加入 .gitignore，不会进仓库）
2. 我拿到文件后立刻执行：
   `inspect_model.py` → `import_model3.py` → `part_report.py`
   → 给你拆件报告与是否可自动化的结论
3. 若许可确认可行，我建立 `assets/ATTRIBUTION.md` 并决定模型是否入仓库
   （体积大时可只保留在本地 + 哈希登记，管线照样工作）
4. 然后才进入 Blender 建模/材质/相机/动画正式流程

> 注：也可以由我继续寻找其他来源（如 CGTrader 免费区、Free3D），但那些站点
> 的免费资产多为"仅限个人使用、禁止再分发"，与 CC-BY 相比更受限；如需要我
> 可以再做一轮，但预期不会比 CC-BY 更好。
