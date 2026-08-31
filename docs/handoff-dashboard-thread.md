# 仪表开发线程开工指引

（本文件是给 ChatGPT 仪表开发线程的任务说明书。先完整阅读
`docs/data-interfaces.md`、`docs/hardware-validation.md`、
`docs/device-capabilities.md` 再动手。）

## 1. 项目一句话

为 2018 Tesla Model 3 的第三方 1920×480 梯形屏幕仪表开发全新 UI 与功能，
数据来自原车 MCU（UART，已验证）与未来的 Commander（接口已预留）。

## 2. 仓库与代码位置

- GitHub：`hanz316/tesla-dashboard-redevelopment`，分支 `main`
- 你的工作区：**核心库 + 模拟器**（`include/`、`src/`、`apps/simulator_gui/`）
- 不要动：`device/flythings/`（T113 实机集成，Codex 负责）、
  `tools/`（硬件工具）、`docs/` 里已验证的事实

## 3. 你的角色

你负责仪表**产品开发**：UI、布局、主题、动画、Trip、Warning、设置、
性能表现。你不负责：

- 逆向 MCU/Commander 协议（别人负责）
- 实机部署/ABI/触摸/显示硬件（Codex 负责）
- 重新设计数据层（`dashboard_core` 已稳定，只增不改）

## 4. 数据怎么拿（重要）

统一入口 `IDataSource`（`include/dashboard/data_source.h`），UI 只读
`VehicleState`，不关心数据来自 MCU 还是 Commander：

```cpp
// 模拟器里的标准用法（见 apps/simulator_gui/main.cpp）
const auto& s = adapter.state();          // VehicleState
if (s.speed.valid) { /* 显示 s.speed.value */ }
else { /* 显示 "--" 或占位，禁止显示假 0 */ }
```

- 每个信号：`value / valid / timestamp / source / quality / unit`
- 信号清单与 Commander 预留字段：`include/dashboard/vehicle_state.h`
- 未接入的数据（Commander 字段）`valid=false`，UI 优雅降级
- 多源信号用 `SignalSourcePriority` 仲裁（Primary 新鲜优先）

## 5. 屏幕约束（必须遵守）

- 逻辑分辨率：**1920×480**
- 屏幕是**梯形**（实机标定）：上角切 116px、下角切 51px
- 背景可画满 1920×480，但**内容必须放在梯形安全区内**
  （顶部 x∈[116,1804]，底部 x∈[51,1869]）
- 安全区参考：模拟器 `drawShapeMask` / `ScreenShape`

## 6. 视觉规范

目标：**现代、高级、简洁、流畅、成品质感**。

- 基调：深灰近黑（#0A0E12）+ 白字 + 蓝点缀（#3D9BFF），
  绿=正常/READY、琥珀=警示、红=错误/REVERSE
- 避免：廉价安卓车机感、RGB 炫光、游戏 HUD、大面积渐变/glow、
  大量逐帧 PNG 动画
- 动画：稳定 30fps 起步（T113 性能有限），60fps 仅当有余量；
  优先数值过渡、状态切换等轻量动画

## 7. 任务优先级

1. **UI v1 完善**：在现有 `renderPremium` 基础上打磨布局/间距/字体/状态
2. **主题**：暗色为主 + 1 个备选主题（可切换）
3. **动画**：速度数字过渡、SOC 条平滑、车门/档位状态变化
4. **功能**：Trip（里程/均速/时间）、Warning 区、设置页（模拟器内）
5. **预留**：Commander 功率/BMS/刹车温度页（数据未接入时显示 `--`）、
   PhoneBridge 界面槽位

## 8. 交付与验证流程

1. 代码提交到 GitHub（`main` 或独立分支 + PR）
2. Codex 拉取 → 模拟器运行（真实 UART 录制回放 + 合成数据）→ 截图验证
3. 验证通过后转 FlyThings 实机版 → 装机实测

每次提交请保证：

- `cmake --build build` 通过、`ctest` 通过（新增逻辑要有测试）
- 模拟器 `--screenshot` 截图正常
- 不破坏 `dashboard_core` 既有接口

## 9. 安全边界（绝对禁止）

- 不发送任何车辆控制命令、不写 MCU、不写 Flash、不做 Raw CAN TX
- 不实现真实 Commander 协议（等 SDK）
- 不在 UI 暴露控制功能（第一阶段只读显示）
