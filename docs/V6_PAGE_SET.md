# V6 仪表页集：9 屏、功能、预算与指挥官接入

状态：**9 屏已在 Mac 端模拟完成并出图；T113 可编译；真机渲染尚未接线。**
分支：`feature/v6-cockpit`。

本文是"一共要做几套仪表、每套做什么"的唯一答案，也是把屏幕搬到真仪表时
的对接说明。场景文件（`scenes/v6_*.scene`）是 runtime 真正读的东西，
生成器（`tools/preview/build_v6_pages.py`）只是确保九屏共享同一套规则。

---

## 1. 一共几套

**7 套行车仪表 + 设置页 + 开发者页 = 9 屏。**

7 套行车仪表不是"同一布局换颜色"。它们在速度表达、车辆位置、能量表达和
空间层级上都不同，但读的是**同一份** `VehicleState`，遵守**同一套**安全规则。

| # | 屏 | 场景文件 | 定位 | 主要功能 |
|---|---|---|---|---|
| 1 | Horizon 地平线 | `v6_horizon.scene` | 主驾驶页 | 速度为核心；右栏续航/ SOC（仅指挥官）；左侧档位与门状态；顶部时间与温度；警告与 UART 状态只在真实触发时出现 |
| 2 | Mono 单色极简 | `v6_mono.scene` | 最省资源 / 夜间备用 | 无渐变池、无弧线，只有速度、档位、门状态、时间 |
| 3 | Pulse 脉冲 | `v6_pulse.scene` | 驾驶动态 | 速度弧 + 加速踏板条 + 电池功率条（功率/踏板来自指挥官） |
| 4 | Route 行程 / 导航 | `v6_route.scene` | 导航与行程 | 有导航能力模型时显示机动与距离；没有时明确 `NO ROUTE` 并提示手机导航兜底；行程指标始终可用（真实信号） |
| 5 | Studio 车辆陈列 | `v6_studio.scene` | 停车 / 检查 | 车辆渲染层 + 门/盖/灯的真实状态 + 胎压 + 档位 |
| 6 | Energy 能量 | `v6_energy.scene` | 能量细节 | SOC **只来自指挥官 `actual_soc`**，功率、电压、电流、累计充/放电 |
| 7 | Nocturne 夜行 | `v6_nocturne.scene` | 最暗最静 | 速度、续航、警告；无装饰 |
| 8 | Settings 设置 | `v6_settings.scene` | 设置 | 外观、亮度、速度单位、温度单位、胎压单位、时钟制式、默认页、警告音、开发者模式（共 9 项） |
| 9 | Developer 诊断 | `v6_developer.scene` | 诊断（不可作默认页） | UART / 解析器健康、指挥官链路与仲裁、映射可信度、帧时/RSS、DEV/REPLAY 横幅 |

### 1.1 导航与可达性

- 滑动环：`Horizon → Mono → Pulse → Route → Studio → Energy → Nocturne → Settings →`（回 Horizon）。
- **Developer 不在环里**，只能在设置里开启开发者模式后进入；设置里也不能把默认页
  设成 Developer（`SettingsStoreV6::clamp` 会拒绝，`page_projection_v6` 会画占位）。
- 安全中断（车辆数据整体丢失）只能落到行车页，落点是 Horizon。

---

## 2. 每屏读什么数据

屏幕不读 UART、不读 BLE、不读手机桥。它们只读 `VehicleState` +
`ProductStateV6` + `DashboardSettings`，由 `buildPageProjectionV6()` 投影成
每屏声明的绑定名。

```text
/dev/ttyS5 (38400, read-only) ──► OriginalMcuAdapter ─┐
Commander (BLE / PhoneBridge)  ──► CommanderLink ─────┤
                                                      ├─► VehicleState ─┐
Replay / Simulation ──────────────────────────────────┘                │
                                          ProductStateV6 (导航/媒体) ────┼─► buildPageProjectionV6() ─► 9 屏
                                          DashboardSettings ────────────┘
```

绑定名的完整清单由 `apps/page_dump` 输出，并由
`tests/v6_binding_coverage_tests.py` 与场景文件**双向**比对：
场景不得引用 runtime 产生不了的名字，runtime 也不得提供场景用不到的名字。
一次改名就是一次测试失败，而不是面板上一块永远画占位符的控件。

---

## 3. 安全规则（九屏共用，任何一屏都不例外）

1. **UNKNOWN ≠ 0 / OFF / CLOSED。** 信号无效时画节点自己的 `invalid_text`；
   缺一个门的信号时，`closures` 整体无效（显示 `CLOSURES ?`），绝不显示
   "全部关闭"。
2. **MCU 的 SOC 字节是 REJECTED_MAPPING**（实车曾在行驶中恒读 97%）。
   任何一屏都不画它；SOC 只来自指挥官 `actual_soc`。
3. **档位映射未确认**（0x01 nibble 已否决，0x02 byte 3 仅 LIKELY）。未确认
   档位一律无效，`GEAR_MAP` 里没有 `0 → P` 这种会把 unknown 画成字母的映射。
4. **没有伪造遥测。** mock 只存在于 `tools/preview/scene_preview.py` 的
   `MOCK_STATES`；生产路径没有任何模拟数据源。
5. **没有车辆控制写路径。** 目标库只引用 `open/read`。
6. **预览与 runtime 同规则。** 预览器在信号缺失时使用节点的 `invalid_text`，
   与 `formatSceneTextV6()` 一致，并有测试逐节点比对。

---

## 4. 性能预算（按真机约束定的，不是按桌面）

开销由**填充面积**主导，不是元素个数（`docs/HORIZON_REDESIGN.md` §7）：
1 px 刻度几乎免费，大面积渐变最贵。静态层因此烘焙进背景位图，每帧只画
文本与动态刻度。

| 项 | 上限 | 说明 |
|---|---|---|
| `static_fills` | 3 | 烘焙一次的背景/环境填充 |
| `static_text` | 14 | 与背景一起烘焙 |
| `conditional_fills` | 1 | 警告底板：同时出现两条警告本身就是错的 |
| `conditional_text` | 6 | 灯/指示/警告，平时为空 |
| `dynamic_paths` | 12 | 每帧真实工作量，决定 30 fps |
| `dynamic_text` | 12 | 同上（Developer 页放宽到 18） |
| `bitmaps` | 2 | 车辆层 + 烘焙背景 |
| `nodes` | 40 | 单屏节点总数 |

生成器在超预算时拒绝生成，`tests/v6_pages_tests.py` 再对**已提交的场景**复核
一遍。当前 9 屏全部通过；最贵的是 Studio（车辆位图）与 Pulse（4 条动态路径）。

真机 30/60 fps、NanoVG 渐变耗时、位图缓存是否可行仍是 **UNKNOWN UNTIL
DEVICE TEST**。

---

## 5. 指挥官（Commander）接入

指挥官是**增强遥测源**，不是第二个车辆接口。

### 5.1 它拥有什么

`mergeCommanderInto()` 只允许它写这些字段：

`actual_soc`、`energy_remaining/full/reserve`、`total_charged/discharged_energy`、
`battery_power/voltage/current`、`front/rear_motor_power`、
`accelerator_position`、`brake_position`、单体电压 `max/min/delta` +
`cell_voltages`、`battery/ambient/cabin_temperature`、`battery_heating`、
`dcdc_*`、`hvac_*`。

### 5.2 它**不可以**覆盖什么

速度、档位、续航、MCU 的 SOC 字节、车门/前备箱/后备箱、灯光、胎压、
行程与总里程 —— 这些是仪表**本来就直接读得到**的数据，沿用原车已有规则。
测试里专门让一个"不守规矩的指挥官"同时携带 `speed=250`、`gear=R`、
`range=1`、`door_fl=OPEN`、`tire_fl=0.1`、`headlights=OFF`，
断言合并后这些值一个都没变。

### 5.3 链路状态是真实的，不猜

`CommanderLinkStatus`：`Disabled / Searching / Linked / NoFrames / Stale`。

- 传输层"连上了"不等于有数据：`setTransport(true)` 之后仍是 `NoFrames`，
  直到真的解出一帧才变 `Linked`。
- 3 s 没有帧 → `Stale`，屏幕显示未连接（而不是继续显示旧值）。
- 未启用 → 徽标画占位符，不是"0 = 未连接"。

### 5.4 帧格式（dashboard 侧契约，**尚未与真实指挥官固件核对**）

```text
0xB5 | TYPE | LEN | PAYLOAD | CHK        CHK = ~(TYPE+LEN+sum(PAYLOAD)) & 0xFF
0x01 PACK     soc u8 %; voltage u16 0.1V; current i16 0.1A; power i16 0.1kW
0x02 ENERGY   charged u32 0.1kWh; discharged u32 0.1kWh; remaining u16 0.1kWh
0x03 CELLS    count u8; count × u16 mV
0x04 INPUTS   accelerator u8 0.5%; brake u8 0.5%
0x05 INFO     major/minor/patch u8; feature flags u8
0x06 TEMPS    battery/ambient/cabin i16 0.1°C
```

多字节一律小端。未知 TYPE 只计数、不猜；校验错误丢帧并计数；读到半帧不算错误
（等下一块数据）。这些都是 dashboard 侧的解码契约：**真机必须抓一次真实
指挥官输出并复核这张表**，在那之前它只是我们自己定的接口，不是实车事实。

### 5.5 真机侧现状

`DeviceRuntime::feedCommander()` 是传输线程的接入点；本 build 里没有任何
东西打开 BLE，所以 `CommanderLink` 报的就是实情（未启用 / 搜索中）。
原生 BLE（FFF0/FFF1）客户端属于平台任务，见 `docs/device-capabilities.md`。

---

## 6. 验证状态：什么已经证过，什么还没有

| 项目 | 状态 | 依据 |
|---|---|---|
| 9 屏场景与预算 | 已验证（host） | `tests/v6_pages_tests.py` |
| 绑定名双向一致 | 已验证（host） | `tests/v6_binding_coverage_tests.py` |
| 投影规则（未知态、SOC、档位、门、指挥官徽标） | 已验证（host） | `tests/page_projection_tests.cpp` |
| 指挥官解码 / 校验 / 链路状态机 | 已验证（host，对契约） | `tests/page_projection_tests.cpp` |
| 合并规则不可反向覆盖 | 已验证（host） | 同上 |
| 设备侧环境映射（UART OK/STALE/LOST、计数器） | 已验证（host，编译同一份 device 源码） | `tests/device_environment_tests.cpp` |
| 设置持久化与钳制 | 已验证（host） | `tests/settings_store_tests.cpp` |
| T113 交叉编译 | 待本轮确认 | `scripts/build_t113.sh` |
| 真机 30/60 fps、渐变耗时、位图缓存 | **未知** | 需要真机 benchmark |
| 面板实际 gamma / 亮度 | **未知** | Mac 上的判断不代表梯形屏 |
| 真实指挥官固件输出 | **未知** | 需要抓一次 |

---

## 7. 搬到真仪表还缺什么

1. **EasyUI 渲染后端**：实现一个 `IRenderBackendV6` 适配器，把 scene 的
   node 类型（`vgradient/radial/line/arc/ticks/vbar/roundrect`）映射到
   NanoVG 路径，把文本节点映射到文本控件，把静态层烘焙成位图。
   这是移植的主要工作量，也是"30 fps 是否可达"的答案所在。
2. **车辆位图 + 门动画**：`ZKImageAnim` 能力探测（变帧尺寸 / 任意 x-y /
   变 delta / fixed-tight），决策规则已写在 `device/bench/bench_plan.cpp`。
3. **指挥官传输线程**：打开一次真实传输，把字节喂给 `feedCommander()`，
   抓取真实输出并复核 §5.4 的表。
4. **真机 benchmark**：帧时、CPU、RSS、解码常驻内存，写入 Developer 页
   （现在那里是占位符，不编数字）。
5. **实车复核**：档位（0x02 byte 3）、轮胎轮位顺序、`0x07` 温度可信度，
   这些仍标注为未确认，需要实车录制。

部署仍只允许 `/tmp` 临时路径；不写 `/res`、不写 Flash、不向 MCU 发送任何命令。

---

## 8. 复现命令

```bash
# 重新生成九屏场景 + 校验
python3 tools/preview/build_v6_pages.py
python3 tests/v6_pages_tests.py

# 渲染单屏（开发者 mock 状态）
python3 tools/preview/scene_preview.py --scene scenes/v6_horizon.scene \
  --state v6_pages_dev --out assets/checkpoints/v6_pages/preview \
  --out-name page_horizon

# host 全量测试（20 项）
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build -j
ctest --test-dir build --output-on-failure

# 每屏绑定契约（场景 ↔ runtime 投影）
./build/dashboard_page_dump | python3 -c "import json,sys; print(json.load(sys.stdin)['pages'].keys())"
python3 tests/v6_binding_coverage_tests.py build/dashboard_page_dump

# T113 目标
bash scripts/build_t113.sh && bash scripts/package_dev_bundle.sh
python3 tools/device/verify_elf_artifact.py --artifact build-t113/libzkgui.so
```
