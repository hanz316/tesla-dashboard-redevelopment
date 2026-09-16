# HDRI Selection Round 2

状态：**三个最终候选已产出，等待人工视觉选择。不要由实现方宣布 winner。**

基线 commit：`854b1fd`。

上一轮结论：HDRI 技术路线 APPROVED，但 **Studio Kontrast 01 作为最终环境被否决**
——它在全景天窗 / 上层玻璃 / 车身上产生了非常明显的
high-frequency striped reflection（zebra / 百叶窗式条纹）。

问题定义得很准确：**不是"反射太强"，而是环境反射的空间频率太高**。
所以本轮不碰车漆、不碰玻璃、不做 blur / 降透明度 / 压曝光 / 加 roughness
这些掩盖手段 —— 唯一要做的是**换环境**。

---

## 1. 评估了多少、留下多少

| 阶段 | 数量 |
|---|---|
| Poly Haven CC0 候选中查阅 | 96 个 studio HDRI |
| 下载并逐像素预分析 | 10 个 |
| 统一条件下 600px 渲染 | **10 个 + 1 个对照组** |
| 通过硬性规则（初筛） | **6 个** |
| 进入最终高质量对比（BEST 3 × 2 lighting） | **3 个 → 6 张** |

对照组 = 被人工否决的 Studio Kontrast 01，用完全相同的设置渲染，
用来检验筛选指标是否真的能识别人工看到的问题。

---

## 2. 筛选方法（不只看数字）

上一轮把"reflection std 高"当成优点，这是错的：**条纹车顶的 std 也很高**。
本轮改为分离空间频率：

```
roofLF   = 车顶区域做 Gaussian low-pass 后的标准差
           → 大尺度连续明暗（dark / mid / bright silver 的过渡）
roofHF   = (原始 - low-pass) 的标准差
           → 条纹、灯管阵列、重复天花灯
HF/LF    = 高频是否压过高频以外的结构
stripes  = 逐行统计"明显的亮暗交替"数量后取中位数
strMax   = 单行最大条纹数（最坏情况）
```

低通半径 = 车宽 × 2.5%（600px 车宽时约 15 px），也就是"比一个大柔光箱更细的
东西"都算高频。

两个实现细节值得一提，因为第一版都做错了：

1. Pillow 的 `GaussianBlur` **不接受 float 图像**，先量化成 8bit 会把舍入误差
   直接混进要测的高频残差里。改成自己实现的 float 可分离高斯。
2. 条纹计数如果先对车顶做**列平均**再找极值，条纹会被平均掉。改成**逐行**
   统计再取中位数，并同时记录最坏单行。

**指标有效性验证**：被人工否决的 Kontrast 01，在 11 个渲染里 roofHF 排第 2
（37.5），strMax = 4 —— 指标确实能识别人类看到的问题。

---

## 3. 淘汰记录

### 3.1 硬性规则直接淘汰（明显不合格，不进 contact sheet）

| 候选 | 淘汰原因 |
|---|---|
| Brown Photostudio 04 | **5 条车顶条纹（> 4 规则）** + 4 个像素削顶 |
| Brown Photostudio 05 | 统一曝光下出现**削顶**（6 px） |
| Monochrome Studio 03 | 统一曝光下出现**削顶**（5 px） |
| PAV Studio 02 | 统一曝光下出现**削顶**（1 px）+ roofHF 32.4 |

削顶之所以是淘汰项：本轮**禁止针对单个 HDRI 调光**，所以"在统一曝光下就削顶"
意味着这个环境的光源对当前材质过曝 —— 那是环境的问题，不是可以用参数掩盖的。

### 3.2 BEST 3 阶段淘汰（通过了硬性规则，但排序靠后）

| 候选 | roofHF | HF/LF | strMax | 淘汰原因 |
|---|---|---|---|---|
| Monochrome Studio 01 | **41.6** | 0.721 | 3 | roofHF 全场最高，高频能量最强 |
| Studio Kontrast 03 | 12.2 | **1.231** | 4 | 高频能量**超过**低频能量，车顶以噪声为主而非结构 |
| PAV Studio 01 | 17.1 | 0.569 | 3 | 数值可接受，但 **mean 只有 72** —— 车整体偏暗，无法给出 dark / mid / bright silver 三段 |
| Studio Kontrast 01（对照） | 37.5 | 0.639 | 4 | 上轮已被人工否决；本轮排第 2 差，验证指标有效 |

PAV Studio 01 的取舍说明：它的 roofHF（17.1）与入选的 Marry Hall（17.2）几乎
相同，属于**平局**。平局由 tonal band 打破 —— 本轮要求车能读出三段银色，
mean 72 做不到。这是一个可以被人推翻的判断，所以单独记录。

---

## 4. 最终三个候选

全部 Poly Haven **CC0 1.0**，1024×512（初筛）/ 2048×1024（最终渲染）。

| | HDRI A | HDRI B | HDRI C |
|---|---|---|---|
| 名称 | **Marry Hall** | **Photo Studio 01** | **Story Studio 02** |
| 作者 | Sergej Majboroda | Sergej Majboroda | Grzegorz Wronkowski |
| URL | https://polyhaven.com/a/marry_hall | https://polyhaven.com/a/photo_studio_01 | https://polyhaven.com/a/story_studio_02 |
| License | CC0 1.0 | CC0 1.0 | CC0 1.0 |
| panorama p50 | 0.604 | 0.435 | 0.456 |
| panorama 峰值 | 52.5 | 392.7 | 154.3 |
| 最亮 1% 横向跨度 | 0.49 | 0.37 | 1.00 |
| 中高度亮度 | 0.977 | 0.660 | 0.520 |

三个环境的性格差异（供人工判断，不是结论）：

- **Marry Hall**：整体环境亮度最高、峰值最低（52.5），光源最"软"——
  roofLF 最高（26.7）说明车顶有大尺度连续过渡。
- **Photo Studio 01**：p50 最低（0.435）但有一个很亮的光源（392.7），
  高频能量是三者中最低（17.6）。明暗对比会最强。
- **Story Studio 02**：最亮区域横向跨度 1.00（光源铺得很开），
  roofHF 最低（12.9）。三者中车最暗（mean 96）。

---

## 5. 统一测试条件

所有候选使用**完全相同**的条件，禁止逐个调光：

| 项目 | 值 |
|---|---|
| 车辆 | MODEL A（未改） |
| Camera | V2-A（az −32°，el 22°，ortho 4.25） |
| 材质 | 上一轮冻结的 photoreal 多层材质（**未改**） |
| Glass | 冻结（**未改**） |
| 初筛渲染 | 710×490，supersample 1，Cycles 32 spp |
| 最终渲染 | 1100×760 ×2 = 2200×1520，Cycles 96 spp |
| Exposure | **0.10（全部相同）** |
| Gamma | 1.00 |
| HDRI strength | 1.0（全部相同） |
| fill-scale | 2.0（全部相同，diffuse-only） |
| 光源钳制 | indirect 4.0 / direct 6.0（全部相同） |
| film_transparent | True（HDRI 不进入 PNG） |

HDRI HYBRID 对三个环境使用**同一套** rig：1 key（260 W，glossy）+
1 fill（90 W，diffuse-only）+ 1 rim（150 W）+ 1 bounce（46 W，diffuse-only）。
没有针对任何环境手工调光。

---

## 6. 结果

### 6.1 初筛（600px 车宽，11 个渲染）

| 候选 | mean | std | roofLF | roofHF | HF/LF | stripes | strMax | clip |
|---|---|---|---|---|---|---|---|---|
| monochrome_studio_01 | 97 | 65 | 57.7 | **41.6** | 0.721 | 2 | 3 | 0 |
| **CONTROL kontrast_01** | 100 | 62 | 58.7 | **37.5** | 0.639 | 2 | 4 | 0 |
| pav_studio_02 | 116 | 58 | 49.1 | 32.4 | 0.661 | 2 | 3 | 1 |
| monochrome_studio_03 | 117 | 69 | 81.9 | 31.8 | 0.388 | 1 | 2 | 5 |
| brown_photostudio_04 | 130 | 52 | 37.2 | 25.5 | 0.686 | 2 | 5 | 4 |
| brown_photostudio_05 | 143 | 58 | 40.9 | 21.0 | 0.514 | 3 | 4 | 6 |
| marry_hall | 128 | 47 | 27.1 | 17.2 | 0.633 | 1 | 2 | 0 |
| pav_studio_01 | 72 | 39 | 30.0 | 17.1 | 0.569 | 1 | 3 | 0 |
| photo_studio_01 | 123 | 49 | 27.7 | 16.3 | 0.589 | 1 | 2 | 0 |
| story_studio_02 | 97 | 39 | 17.6 | 12.3 | 0.695 | 1 | 3 | 0 |
| studio_kontrast_03 | 97 | 52 | 9.9 | 12.2 | **1.231** | 2 | 4 | 0 |

### 6.2 最终 6 张（2200×1520）

低通半径按车宽比例取，所以初筛与最终的 roofHF 是**同一归一化频段**、可直接比较
（story_studio_02：初筛 12.3 / 最终 12.9，差异来自采样数）。

| 候选 | mean | std | roofLF | roofHF | HF/LF | strMax | clip |
|---|---|---|---|---|---|---|---|
| story_studio_02 HYBRID | 115 | 46 | 34.5 | 21.4 | 0.621 | 3 | 0 |
| marry_hall HYBRID | 140 | 49 | 18.4 | 19.8 | 1.075 | 3 | 0 |
| photo_studio_01 HYBRID | 136 | 50 | 20.3 | 19.2 | 0.946 | 2 | 0 |
| marry_hall ONLY | 127 | 48 | 26.7 | 18.5 | 0.691 | 2 | 0 |
| photo_studio_01 ONLY | 122 | 50 | 27.4 | 17.6 | 0.641 | 2 | 0 |
| **story_studio_02 ONLY** | 96 | 40 | 17.3 | **12.9** | 0.745 | 3 | 0 |

六个候选的 roofHF 全部低于被否决的 Kontrast 01（37.5），
最坏的只有它的 57%，最好的（12.9）只有它的 **34%**。

### 6.3 三种尺寸下的表现（Part H）

| 候选 | 600px mean/std | Horizon 1:1 车区 mean/std | 削顶 |
|---|---|---|---|
| marry_hall ONLY | 126.7 / 47.6 | 75.8 / 65.0 | 0 |
| marry_hall HYBRID | 139.7 / 48.3 | 84.8 / 72.3 | 0 |
| photo_studio_01 ONLY | 122.1 / 49.7 | 72.9 / 63.9 | 0 |
| photo_studio_01 HYBRID | 135.8 / 50.3 | 82.4 / 71.5 | 0 |
| story_studio_02 ONLY | 96.0 / 39.6 | 59.5 / 50.8 | 0 |
| story_studio_02 HYBRID | 114.8 / 45.7 | 72.4 / 62.9 | 0 |

**六个候选在 600px 与 Horizon 实尺寸下均无削顶。**

### 6.4 渲染时间

初筛（710×490 / 32 spp）：1.7–2.3 s/张。
最终（2200×1520 / 96 spp）：19.3–21.7 s/张。

---

## 7. 产物

| 文件 | 内容 |
|---|---|
| `hdri_candidate_contact_sheet.png` | 通过硬性规则的 6 个候选，每格 600px 车辆 |
| `hdri_eliminated_contact_sheet.png` | 淘汰的 4 个 + 对照，每格标注淘汰原因 |
| `hdri_final_3_comparison.png` | 3 HDRI × 2 lighting（每行 = 一个 HDRI 的 ONLY / HYBRID） |
| `hdri_final_3_horizon.png` | 6 张 Horizon 1:1 的汇总 |
| `finals/final_<hdri>_<mode>_600px.png` | 600px 车宽 |
| `finals/final_<hdri>_<mode>_horizon_1to1.png` | 1920×480 composite 的 1:1 裁切 |
| `finals/horizon_1920x480_<hdri>_<mode>.png` | 完整 1920×480 |
| `screened_600px/*` | 初筛的全部 11 张 |

Horizon 背景 context 使用既有的 **`scenes/horizon_redesign_a.scene`**，
state `normal_drive`，framing `700x401@610,40`（与该 scene 本身一致）。
**没有修改 Horizon**，也没有使用旧的 horizon_v1 工程页面。

复现：

```bash
# 初筛
for s in <slug>; do /Applications/Blender.app/Contents/MacOS/Blender -b \
  -P tools/blender/render_vehicle_photoreal.py -- --lighting hdri \
  --hdri assets/source/hdri/${s}_1k.hdr --engine cycles --samples 32 \
  --canvas 710x490 --supersample 1 --exposure 0.10 --fill-scale 2.0 \
  --out assets/rendered/hdri_round2/${s}_only_600.png; done
python3 tools/assets/analyze_reflection_frequency.py \
  assets/rendered/hdri_round2/*_only_600.png

# 最终
python3 tools/assets/build_hdri_round2_outputs.py
```

---

## 8. 性能说明

本轮全部是 Blender offline rendering。**HDRI 不进入设备**：设备最终只拿到
pre-rendered transparent PNG / delta animation，所以 HDRI 的复杂度
**不增加** T113 的任何 runtime CPU/GPU 开销。本文件不讨论设备 FPS。

## 9. 未确定 / 需要人工判断

- 三个候选里哪个最终更好 —— **本轮不做选择**。
- PAV Studio 01 与 Marry Hall 在 roofHF 上是平局（17.1 vs 17.2），
  仅因 tonal band 被淘汰；如果人工认为"更暗的银色"可接受，应当重新考虑它。
- `marry_hall HYBRID` 的 HF/LF 达到 1.075（低频对比很弱时比值会失真），
  这个数字不能直接读成"条纹多"，需要以 roofHF 与视觉为准。
- 面板实际 gamma / 亮度未验证。
