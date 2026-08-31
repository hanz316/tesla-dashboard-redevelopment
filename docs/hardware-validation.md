# 实机验证报告（持续维护）

更新：2026-08-31（America/Toronto）

设备：`Zkswe_T113_SPINOR`，Wi-Fi ADB `10.0.0.216:5555`

## Build 0.2（build-0.2 @ f9b92ce）

| 项目 | 结果 |
|---|---|
| Commit | `f9b92ce`（含 UART/信号诊断日志） |
| T113 交叉编译 | PASS（ARM 32-bit EABI5，无 undefined symbol，无 `write`） |
| Mac 单元测试 | PASS |
| /tmp 部署 | PASS（`/tmp/EasyUI.cfg` + `/tmp/tesla-dashboard-mvp/lib/libzkgui.so`） |
| 进程存活 | PASS（重启后持续运行，无 crash loop） |
| 库加载确认 | PASS（`/proc/PID/maps` 指向 /tmp 新库） |
| /dev/ttyS5 | PASS（只读打开，flags `0404000` = O_RDONLY\|O_NONBLOCK） |
| Framebuffer | PASS（暗色仪表渲染，与 Build 0.1 基线一致） |
| 显示 FPS | 60 Hz（内核 disp `fps:60.2`）；UI 更新 100ms（10Hz）设计 |
| CPU | <1%（空闲时 0.6 ticks/s，车未通电状态） |
| RAM | VmSize 27252 kB / VmRSS ~3660 kB |
| FD | 82 个（框架 + 应用，无异常） |
| UART 数据流 | 待车通电验证（当前 bytes=0，车处于关闭状态） |
| Speed/Gear/SOC/Range/Doors/Tire | `NEEDS_REAL_CAR_ACTION`（车通电后验证） |

## 重要发现：framebuffer 读取方法

**`adb shell cat /dev/fb0 > local.raw` 会损坏二进制内容**（产生伪色块），
必须用：

```bash
adb shell 'cat /dev/fb0 > /tmp/fb.raw'
adb pull /tmp/fb.raw local.raw
```

早期"屏幕显示纯色块"的结论是该读取假象造成的误报；屏幕实际一直正常。

## 运行时诊断工具

应用每 5 秒向 `/tmp/dashboard_runtime.log` 写入：

- UART 统计：bytes / frames / crc / discard / applied / short / unknown / health
- 信号值：speed / gear / soc / range / doors / tires / temperature

用于无界面条件下的数据流与解码验证。

## 已知问题 / 下一步

- UART 数据流验证需车辆通电（accessory 或启动）。
- door/tire 物理位置 mapping 需实车逐项确认（仍为 `Inferred`）。
- 设备 `persist.sys.zkdebug=1` 为上轮调试遗留，暂未清除（未确认其影响）。
