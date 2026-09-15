# 仪表渲染/动画技术路线审计（RENDERING_CAPABILITY_AUDIT）

日期：2026-09-15
分支：`feature/v6-cockpit`（基线 commit 见 `git log`）
范围：**纯离线调查**。本次不使用 ADB/SSH/串口/真机；所有结论来自仓库内
固件备份、SDK、toolchain 与本地最小实验。

---

## 1. 现有硬件/软件事实（已验证，来自之前的实机调查）

| 项 | 值 | 来源 |
|---|---|---|
| 设备型号 | `Zkswe_T113_SPINOR` | `getprop` 备份 |
| firmware | `t113_zkswe_da` | 同上 |
| SoC | Allwinner T113（sun8i 家族） | 设备树/cmdline |
| CPU | 2× Cortex-A7（part `0xC07`），ARMv7 + NEON + VFPv4 | `/proc/cpuinfo` 备份 |
| RAM | MemTotal 249,964 kB（≈244 MiB），空闲约 183 MiB | `/proc/meminfo` 备份 |
| Flash | 32 MiB SPI NOR，6 分区 | `/proc/mtd` 备份 |
| 系统 | ZKOS（musl + Linux），FlyThings V2.1 / EasyUI 2.2.0 | 固件与实机 |
| 逻辑屏幕 | 1920×480，framebuffer `fb0` = 480×3840（双页 32bpp），rotate 270 | 实机验证 |
| 物理屏幕 | 梯形（上角切 116px / 下角切 51px），面板 180° 安装 | 触控描边标定（已确认） |
| 车辆数据 | `/dev/ttyS5` @38400 只读，40 fps，0 CRC 错误 | 实机验证 |

---

## 2. 本地固件发现（本次新证据）

### 2.1 启动/加载模型（关键）

```
/bin/zkgui  (宿主进程, NEEDED 列表包含:)
    libzkhw, libuapi, libstdc++, libz, libpng12, libjpeg, libfreetype,
    libts, libnanovg, libeasyui, libzknet, libzkhardware, libzkupgrade,
    libtsupdate, libcutils, liblog, libgcc_s, libc
        ↓ 以 EasyUI 框架启动，按 EasyUI.cfg 加载应用库
    libzkgui.so  ← 我们替换的就是这一层（/tmp 临时部署）
```

结论：`libnanovg.so` 与 `libeasyui.so` **由宿主进程全局加载**，因此我们的
`libzkgui.so` 可以使用它们导出的 API。

### 2.2 图形库清单（捕获的实机 `/lib`）

存在：`libeasyui.so`、`libnanovg.so`、`libfreetype.so.6.11.4`、
`libpng12.so.0.56.0`、`libjpeg.so.9.1.0`、`libgif.so`、`libz`、`libts`、
`libgomp.so.1`（OpenMP 运行时可多核利用）

**不存在**（在全部本地固件树、rootfs、OTA 包中检索确认）：

`EGL*`、`GLES*`、`libGL*`、`Mali*`、`libQt5*`、`libQt6*`、`Skia`、
`libdrm*`、`DirectFB`、`SDL*`、`OpenVG`、`Vulkan`

---

## 3. GPU / 渲染后端发现

### 3.1 芯片理论能力（公开资料，与固件现实严格区分）

公开资料对 T113 家族说法不一致：

- T113-i 变体被列为 **Mali-400 MP2 @600MHz**（第三方资料）
- T113-S3 变体被描述为双核 A7 + 128MB 内置 DDR3、**仅提到 2D 图形加速**，
  未列出 3D GPU（第三方资料；权威性有限）

本机 RAM 为 244 MiB（非 S3 内置 128MB），说明是支持外置 DDR 的变体。
**但具体型号与 GPU 是否存在，本地无法确证**，标记为
`UNVERIFIED_SOC_VARIANT`。

### 3.2 固件实际能力（决定性的本地证据）

| 证据 | 观察 |
|---|---|
| 内核模块 | 只有 `8733bs`（Realtek BT/WiFi）。**无 Mali/GPU 模块** |
| 内核 cmdline | `cma=4M` — 仅 4MB CMA（Mali 通常需 16–256MB 预留） |
| 用户态 GL 栈 | 完全不存在（无 EGL/GLES/libGL/Mali） |
| 渲染库依赖 | `libeasyui.so` 的 NEEDED 仅 `libgcc_s.so.1` + `libc.so` |
| 渲染实现 | `libnanovg.so` 含 **AGG（Anti-Grain Geometry）纯软件光栅器**符号，并导出 `nvgCreateAGG` |
| 显示访问 | `libeasyui.so` 导出 `zk_disp_init/begin_flush/end_flush/flush_rects/set_rotate/enable_buffer` |

**判定：当前固件没有任何可用的 GPU 加速路径。渲染 100% 由 CPU 完成。**

即使 SoC 硅片内含 Mali，也没有内核驱动与用户态 GL 栈，且**无法从应用层
补齐**（需要厂商内核/驱动，属于系统级改造）。任何"理论上有 GPU"的假设
对本项目当前形态无效。

### 3.3 实际渲染管线（已确认）

```
libzkgui.so (应用)
   ↓ 控件/绘制调用
libeasyui.so  ── 控件系统 + 文本(FreeType) + 图片(PNG/JPEG/GIF) + zk_disp 显示
   ↓ nvg* 调用
libnanovg.so  ── NanoVG API + AGG 软件光栅器（路径/渐变/变换/图片）
   ↓ 像素写入
zk_disp_flush_rects → 显示（fb0 / display driver）
```

### 3.4 本地实验：我们能否直接使用 NanoVG？（**已实测可行**）

用 T113 交叉工具链把引用 `nvgCreateAGG/nvgBeginFrame/nvgEndFrame/nvgDeleteAGG`
的共享库与实机 `libnanovg.so` 链接：

```
结果：ELF 32-bit ARM EABI5 shared object
NEEDED: libnanovg.so  ✓
未解析符号 nvg* 由 libnanovg.so 在运行时提供  ✓
```

**结论：我们可以直接在自定义 libzkgui.so 中使用 NanoVG 矢量绘制**
（路径、贝塞尔、线性/径向/盒渐变、save/restore、translate/scale/rotate、
globalAlpha、图片 pattern）。注意：**实机 nanoVG 编译时未启用文字 API**
（无 `nvgText`/`nvgCreateFont`），文字必须走 EasyUI 控件或 FreeType。

---

## 4. Qt Quick / QML 可行性

| 检查项 | 结论 |
|---|---|
| 固件内 Qt runtime | **不存在**（全部固件树检索） |
| 交叉编译 Qt 5.x 最小集 | 理论可行，但需从源码构建 QtBase + QtDeclarative；GCC 6.4.1 + musl 需补丁；构建时间以小时计 |
| linuxfb 平台插件 | Qt 文档提供（无 GL 需求的 framebuffer 后端）——**属于文档事实，本项目未实验验证** |
| Qt Quick software backend | Qt 5.8+ 提供软件场景图后端（`QT_QUICK_BACKEND=software` / `QSGRendererInterface::Software`）——**文档事实，未验证** |
| eglfs | 不可用（无 EGL/GLES） |
| GPU 加速 | 不可用 |
| 性能（1920×480@30fps） | 软件后端理论上接近 EasyUI（同为 CPU 光栅），但 Qt Quick 场景图开销更大 |
| RAM | QtCore+QtGui+QtQml+QtQuick 约 15–25MB 库 + 场景图/纹理缓存，预估常驻 30–60MB；设备可用约 183MB，**可行但偏重** |
| 启动时间 | Qt 插件扫描 + QML 编译，冷启动明显慢于 EasyUI 原生控件 |
| 架构冲突（决定性） | 我们的代码运行在 **EasyUI 宿主进程 `/bin/zkgui` 内**的被 dlopen 库中；Qt 会与 EasyUI 争夺显示与事件循环。采用 Qt 等于**替换整个宿主应用**（持久化改造 + 失去 stock 框架生态），超出当前安全边界 |

**判定：`NOT_RECOMMENDED`**

---

## 5. Qt Design Studio 工作流可行性

依赖 Qt Quick（见上）。即便设计端体验好（可视化时间线、状态机），
**运行时仍是 Qt**，故继承第 4 节全部问题：无 Qt runtime、无 GPU、
宿主进程冲突、RAM/启动风险。

额外成本：Qt Design Studio 产出的 `.ui.qml` 需要完整 QtQuick 运行时与
`QtQuick.Controls` 等模块，体积进一步上升。

**判定：`NOT_RECOMMENDED`**（在设备侧；设计灵感可借鉴，但不引入运行时）

---

## 6. Crank Storyboard 可行性

| 检查项 | 结论 |
|---|---|
| Designer 平台 | 官方为 Windows/Linux 为主；macOS 支持不明确 |
| Runtime | **商业授权**：Designer 商业 license + 目标 runtime 授权（EULA 明确提到 royalty-bearing runtime components） |
| 目标支持 | 支持嵌入式 Linux；需选用其"commercially supported"的目标组合（处理器/OS/renderer） |
| 渲染后端 | 通常 GLES 或以厂商适配为主；本机无 GLES |
| 与本项目集成 | 同样需要**替换 EasyUI 宿主应用** |
| 自动化/CLI | 项目文件可在仓库中版本化，但 runtime 闭源 |

**判定：`NOT_RECOMMENDED`**（授权成本 + 无 GL + 宿主替换；且违反"不购买/
不注册商业软件"的约束）

---

## 7. Rive 可行性

来自 rive-runtime 官方 README（本次核实）：

> "The built-in GPU renderer (RiveRenderer) has RenderContextImpl backends
> for **Metal, Vulkan, D3D11, D3D12, and OpenGL/WebGL**."
> "An abstract `Renderer` interface for hooking up an external vector renderer."
> Prerequisites: **A C++17 toolchain**；Linux 需 Vulkan/OpenGL 开发环境。

| 检查项 | 结论 |
|---|---|
| ARM32 支持 | 语言层面可（C++17），但需 GCC≥7 较稳；本工具链为 **GCC 6.4.1**（C++17 支持不完整） |
| 内置渲染后端 | 只有 Metal/Vulkan/D3D/OpenGL —— **本机全部不可用** |
| 软件渲染 | 官方内置无 CPU 光栅后端；仅有 SwiftShader 脚本（软件 Vulkan，2×A7 + 244MB 不现实） |
| 可行路径 | 自己实现 `rive::Renderer` 抽象接口（等于自写软件矢量光栅器） —— 工作量巨大且与 Horizon 现有渲染模型重复 |
| RAM/体积 | 未实测；C++17 + 数学库 + 解码，预估数 MB 级 |

**判定：`NOT_RECOMMENDED`**（内置后端全部依赖 GPU；自定义 Renderer 的
成本高于直接用已在设备上的 NanoVG）

> 备选：`UNKNOWN_UNTIL_DEVICE_TEST` 仅在"未来自研 software Renderer"时成立，
> 不建议在当前阶段投入。

---

## 8. Blender 离线动画管线

### 8.1 本机状态

**Blender 未安装**（`/Applications` 无 `Blender.app`，PATH 无 `blender`）。
按要求**未擅自安装**，仅记录。

### 8.2 管线设计（不依赖 Blender 也能验证后半段）

```
Blender 场景(Model3.blend)  ← 固定相机、分层 object
   ↓ (Python 脚本驱动, headless: blender -b -P render_animations.py)
各状态动画          Door_FL_Open / Door_FR_Open / ... / Hazard / Headlight_On
   ↓ 渲染设置：transparent film, PNG RGBA, 固定分辨率
PNG 序列  frames/frame_000.png … frame_0NN.png
   ↓ tools/assets/pack_atlas.py（本次已实现并实测）
图集 PNG + JSON 元数据（帧尺寸/列数/帧数/解码字节）
   ↓ 复制到 /res/ui/…（或 /tmp 临时资源目录）
运行期 EasyUI ZKImageAnim（流式逐帧解码）
```

### 8.3 本次已完成的离线 PoC（不含 Blender）

已实现 `tools/assets/pack_atlas.py` 并**用实机 stock 动画真实数据实测**：

```
输入: /res/ui/dash 里 dash3_recovery 的 101 张真实 PNG (237×351)
输出: 2607×3510 图集 + JSON
  source PNG 合计 888.8 KB
  atlas PNG       968.4 KB
  decoded RGBA   35,744 KB (≈34.9 MB)   ← 关键 RAM 数据
```

即：**把 101 帧全量解码常驻内存会消耗约 35MB**（占设备 RAM 14%），
这直接否定"每个动画都做全量图集解码"的做法，并支持"流式解码"路线
（见第 9、11 节）。

### 8.4 待 Blender 可用时执行

`docs` 内已附带脚本规格（见 NEXT OFFLINE TASKS）：脚本需完成
替代模型 → 固定相机 → 单门 0→55° 动画 → 16 帧透明 PNG 输出。
一旦装有 Blender，可直接运行验证"Codex → Blender Python → 自动建场景 →
自动动画 → 自动渲染"闭环。

---

## 9. EasyUI 帧动画可行性（**本机已有原生支持，且 stock 正在使用**）

### 9.1 实机运行时证据

实机 `libeasyui.so` 导出的 `ZKImageAnim`（SDK 头文件里没有，属运行时
独有）：

```
ZKImageAnim(ZKBase*)                     公开构造
ZKImageAnim::play(const std::string&)    播放
ZKImageAnim::stop() / pause() / resume()
ZKImageAnim::setLoopCount(int)
ZKImageAnim::setStatusListener(IImageAnimStatusListener*)
ZKImageAnim::onTimer(int) / onDraw(ZKCanvas*)
ZKImageAnimPrivate::createDecoder(path)  建立解码器
ZKImageAnimPrivate::readFrame()          逐帧读取  ← 流式
ZKImageAnimPrivate::updateFrame()
ZKImageAnimPrivate::drawAnim(void*)
ZKImageAnimPrivate::notifyAnimStarted/Progress/End
```

**关键结论：这是"解码器 + 定时器 + 逐帧读取"的流式播放器**，不需要把
整段动画解码常驻 RAM。

### 9.2 stock 应用已经在这么做（最强可行性证据）

实机 `/res/ui/dash` 中存在：

| 序列 | 帧数 | 尺寸 | 单帧 PNG | 合计 |
|---|---:|---|---:|---:|
| `dash3_recovery` | 101 | 237×351 RGBA | 4.9 KB | 889 KB |
| `dash3_release` | 101 | 237×351 RGBA | 4.9 KB | 1001 KB |
| `dash_release` | 101 | 142×215 调色板 | 0.1 KB | 258 KB |
| `dash_recovery` | 99 | 142×215 调色板 | 0.1 KB | 244 KB |

**判定：`SUPPORTED`（已有原生实现 + 原厂自用，风险低）**

---

## 10. Scene UI 架构提案（避免硬编码坐标的 C++ 页面）

目标：设计参数与业务逻辑分离、Codex 可自动修改、ARM 友好、不需要
实现 QML 解析器。

### 10.1 分层

```
VehicleState (不变: MCU/Commander/PhoneBridge/Replay/Simulation → 仲裁 → 单一来源)
        ↓  只读绑定 (id → 信号)
SceneModel  (纯数据: 节点树 + 属性 + 绑定表达式)
        ↓
SceneRuntime (求值/动画/裁剪/可见性)  ← 平台无关, 可在 Mac 上跑
        ↓  IRenderBackendV6 (已有边界)
EasyUIBackendV6 (控件池 + ZKImageAnim + 可选 NanoVG 矢量层)
```

### 10.2 节点模型（示例）

```jsonc
// scenes/Horizon.scene
{
  "root": { "w": 1920, "h": 480, "safe": { "top_cut": 116, "bottom_cut": 51 } },
  "nodes": [
    { "id": "speed",    "type": "text",  "x": 430, "y": 170, "font": 170,
      "bind": { "text": "speed>0?speed:'--'", "color": "speed.quality" } },
    { "id": "vehicle",  "type": "sprite","x": 600, "y": 30,
      "asset": "vehicle/base", "anim": { "door_fl": "vehicle/door_fl_open" } },
    { "id": "soc_bar",  "type": "shape", "x": 1360, "y": 320, "w": 260, "h": 16,
      "bind": { "progress": "soc" } }
  ]
}
```

节点属性：`x y w h opacity visible z anchor asset state animation crop`
变换：`translate / scale / opacity`（EasyUI 无 rotation → 用预渲染帧替代）

### 10.3 为什么不在设备上跑 QML

EasyUI 控件是 FTU 绑定、无运行时 addChild；直接实现 QML 解析器成本高且
收益低。上面这个"场景 JSON + 运行时求值"已经能覆盖需求（布局/状态/动画
声明式、业务无关、Codex 可批量改写）。

---

## 11. 性能 / RAM 风险量化

### 11.1 解码 RAM（本次实测换算）

| 资产形态 | 尺寸 | 帧数 | 解码常驻 |
|---|---|---:|---:|
| 全屏帧 | 1920×480 | 1 | 3.5 MB |
| 车辆元素 | 600×250 | 30 | 17.2 MB |
| stock 小元素 | 237×351 | 101 | 32.1 MB |
| stock 小元素 | 142×215 | 101 | 11.8 MB |
| 流式播放（一次 1 帧） | 237×351 | 1 | 0.32 MB |

**结论：禁止整段动画全量解码常驻；必须走流式或小窗口缓存。**

### 11.2 解码耗时

本机（Apple Silicon 单核）实测 237×351 PNG 解码 ≈ **0.227 ms/帧**。
按 Cortex-A7 相对慢 20–40× 估算，设备上约 **4.5–9.1 ms/帧**。

以 30 fps（33.3 ms 预算）计：单个动画元素约占 **14–27%** 帧预算。
→ 设计约束：**同时进行帧序列动画的元素不超过 1–2 个**；其余用
轻量属性动画（位移/透明度/进度），这类几乎零解码成本。

### 11.3 其它风险

| 风险 | 说明 | 缓解 |
|---|---|---|
| 全屏重绘 | CPU 光栅 1920×480 每帧 | 只重绘脏矩形；EasyUI 控件本身有局部刷新 |
| 文字重排 | 每帧 setText 触发文本位图重建 | 数值变化限频（10 Hz 足够），大字体缓存 |
| 矢量层 | NanoVG 路径填充成本随面积上升 | 静态矢量预渲染成 PNG；只让动态部分走 NanoVG |
| 启动时间 | 资源越多启动越慢 | 懒加载：共享层 + 当前页 + 安全提示 |
| 存储 | SPI NOR /res 有限（×分区 21.375MB 总量） | 用调色板 PNG（stock 单帧 0.1KB 级别）、复用帧 |

---

## 12. 现在（离线）就能做的

1. **Scene 系统落地**：`SceneModel` + `SceneRuntime` + 单元测试（平台无关，
   可完全在 Mac 上验证），复用 V6 的 `IRenderBackendV6` 边界
2. **Mac 预览后端**：把 `RenderFrameV6`/Scene 渲染到 SDL 窗口（本仓库已
   有 SDL 模拟器基础设施），实现"改场景 JSON → 立刻看效果"
3. **资产生产工具链**：`pack_atlas.py`（已实现）、帧命名规范、
   RAM/尺寸预算校验脚本（超预算即 CI 失败）
4. **Blender 脚本**：写好 `Model3` 场景生成 + 动画 + 渲染脚本（等 Blender
   可用直接跑）
5. **NanoVG 矢量层 PoC（Mac 端）**：用同版本 NanoVG 在 Mac 上渲染同一份
   矢量描述，验证设计
6. **FTU 控件池规格**（已完成：`docs/render-backend-easyui-plan.md`）
7. **性能模型**：把第 11 节预算固化成脚本，对每个新资产自动给出
   RAM/解码耗时评估

## 13. 必须等真机回来才能做的

1. NanoVG 在设备上的实际首帧（链接可行性已离线证明，仍需实机运行验证）
2. ZKImageAnim 在**我们的**应用里播放 PNG 序列的实测（stock 用的是它自己
   的资源与 FTU 配置）
3. 1920×480 全屏重绘 + 1–2 个帧序列动画的**实测 FPS / frame time / CPU / RSS**
4. 梯形安全区下的最终视觉确认与触控命中
5. `/tmp` 部署 + 断电回滚 + 长跑稳定性
6. 大字体文本重建成本、中文/多语言字体加载时间
7. 屏幕截图与色彩/亮度最终确认（面板 180° + 梯形裁切）

---

## 14. 最终推荐

### RECOMMENDED ARCHITECTURE

**Design:**
仓库内声明式场景文件（`scenes/*.scene`，JSON）+ 节点/绑定/动画模型；
Mac 端预览器实时渲染同一份场景，设计与实现同源、可版本化、Codex 可批量
修改。**不引入 QML/Qt 运行时。**

**3D Animation:**
Blender 离线生产（固定相机 + 分层 object：Body/Glass/Wheel_*/Door_*/
Frunk/Trunk/Headlight_*/Brake_*/Indicator_*）。Blender 当前未安装：
脚本先写好，装好后直接跑。

**Runtime Renderer:**
EasyUI（宿主既有框架）为主：

- 文本/数值 → `ZKTextView`（FreeType 渲染）
- 帧动画 → **`ZKImageAnim` 流式播放 PNG 序列**（原生、RAM 友好、stock 已验证）
- 矢量/HUD 细节 → 可选 `NanoVG(AGG)` 自绘层（**链接可行性已离线验证**）
- 呈现边界 → 复用 V6 `IRenderBackendV6`，不重写 Horizon/V6 状态逻辑

**Vehicle Backend:**
**完全保持不变**：MCU UART / Commander / PhoneBridge / Replay / Simulation
→ Source Arbitration → VehicleState。UI 与动画只消费 VehicleState，禁止
直接读 UART。

**Animation Format:**
透明 PNG 序列（首选，流式解码）→ 小尺寸/短序列可用图集（≤ 2–4MB 解码
预算）→ 简单状态变化用属性动画（位移/透明度/进度），零解码成本。
**明确放弃**：APNG/WebP-Animation（无运行时解码支持）、Rive `.riv`（无
可用后端）。

**Fallback:**
纯 EasyUI 控件 + 预渲染静态 PNG 状态图（Build 0.1 已验证路线）。
当动画预算超标时，退回"静态状态切换"而不是降帧率牺牲观感。

---

## NEXT OFFLINE TASKS

1. 实现 `SceneModel` / `SceneRuntime`（含单元测试），对接现有
   `IRenderBackendV6`
2. 实现 Mac 端 Scene 预览后端（SDL 窗口，1920×480，梯形遮罩）
3. 建立资产预算校验：`tools/assets/check_budget.py`（帧尺寸/帧数/解码 RAM/
   预估解码耗时，超限即失败）
4. 编写 Blender 脚本 `tools/blender/build_model3_scene.py` +
   `render_animations.py`（含 16 帧单门 PoC 模式）
5. 定义 `scenes/horizon_v1.scene` 初版（速度/档位/SOC/续航/车门/胎压/温度/
   警告/Context Rail），在 Mac 预览器里迭代
6. 准备 NanoVG 矢量层的最小 PoC（Mac 端渲染 + 交叉编译产物）
7. 把本审计的量化预算写进 `docs/`，作为后续提交的验收标准

## NEXT DEVICE TESTS（仪表回来后第一批）

1. `/tmp` 部署当前 V6 分支 → 确认进程/maps/只读 UART 不变
2. **ZKImageAnim 实测**：用 101 帧真实序列在我们自己的应用里播放，
   记录 FPS / frame time / CPU / RSS（对照 stock 基线）
3. **NanoVG 自绘实测**：在设备上 `nvgCreateAGG(1920,480)` + 画一帧到
   framebuffer，验证链接与呈现（离线已证明链接可行）
4. **全屏重绘基线**：1920×480 每秒 30 次静态重绘的 CPU/耗时上限
5. **混合负载**：1 个帧序列动画 + 文本数值 10Hz 更新时的 FPS/CPU/RSS
6. framebuffer 截图 + 梯形安全区视觉确认
7. 长跑（≥1 小时）稳定性与内存增长

---

## 附：本次新增的仓库产物

- `tools/assets/pack_atlas.py` —— PNG 序列 → 图集 + JSON（已用真实 stock
  帧实测）
- 本文件 `docs/RENDERING_CAPABILITY_AUDIT.md`

（离线实验记录：NanoVG 链接实验、ELF 动态符号解析脚本、
stock 帧动画 RAM/解码测量，见本文对应章节。）
