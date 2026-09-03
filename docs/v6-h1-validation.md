# V6-H1 实机验证状态（Codex）

更新：2026-09-03

分支 `feature/v6-cockpit` @ `81614146f2f86049cad2afd3a8a9c6e0b12109e1`

## 已完成（无需实机）

| 项 | 结果 |
|---|---|
| Host configure + build | PASS |
| ctest（5 套件） | PASS（dashboard / v6 / services / ui_v6 / replay） |
| T113 全量交叉编译 | PASS（ELF 32-bit ARM EABI5，musl hard-float） |
| libzkgui.so 符号 | 无 undefined symbol；无 `write`/send/TX 符号 |
| dashboard_core 进入 lib | 数据路径（adapter/parser/vehicle_state）已链接；V6 服务对象在静态库内，待后端引用后进入 .so（预期） |
| SOC 语义 | MCU SOC 标记 `Estimated`；测试断言 quality==Estimated |
| Gear 语义 | 仅 0=P、4=D 为 Confirmed；未知 nibble → Unknown 不猜（代码+测试确认） |
| Replay 路径 | 测试通过（parser-faithful，seek/0.5x/1x/2x） |
| EasyUI API 勘察 | 已确认（见 `docs/render-backend-easyui-plan.md`）；控件 FTU 绑定、无运行时 addChild |
| 模拟器（控制台） | PASS；已修正合成帧 gear nibble 0x40=Drive |

## 阻塞（需用户操作）

| 项 | 原因 |
|---|---|
| /tmp 部署 | 仪表不在网络（adb 扫描无 5555） |
| P→D / 门 / speed / range 实车响应 | 需车通电 + 仪表连 Mac 同一 Wi-Fi |
| RenderFrameV6 实机首帧 | 需可编辑 V6 FTU（FlyThings IDE）+ 后端实现 |
| Motion OFF/LOW/FULL 实测 | 需实机部署 |
| framebuffer + 梯形安全区截图 | 需实机在线 |

## 下一步

1. 车通电、仪表连同一热点 → 我继续 /tmp 部署与信号验证
2. 制作 `v6_horizon.ftu` 控件池（规格见 render-backend-easyui-plan.md）
3. 实现 `EasyUIRenderBackendV6` → 实机首帧 → 性能实测
