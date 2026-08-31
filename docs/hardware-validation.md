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

## 实车通电验证（2026-08-31 16:2x，车通电静止）

车通电后仪表重启，/tmp 清空回到 stock；重新部署 Build 0.2 后：

| 项目 | 结果 |
|---|---|
| UART 数据流 | **PASS**（约 40 fps，bytes 持续增长） |
| 帧解析 | **PASS**（2,356+3,736 帧，0 CRC 错误，0 丢弃） |
| 数据源状态 | **PASS**（health=Connected，UI 显示 DATA） |
| Speed | PASS（静止 0 km/h） |
| Gear | PASS（Park） |
| SOC | PASS（97%） |
| Range | PASS（254 km） |
| Doors | PASS 初步（driver door=open，bit0=FL 吻合；需关门动作复核） |
| Tire Pressure | 静止未上报（全零），需行驶/特定条件 |
| 主温 | PASS（22°C） |
| 原始录制 | `captures/uart-record-realcar-*.bin`，协议表已更新 |

### SOC 已知问题（MCU 数据本身）

- `0x04[8]` 恒定上报 97，**stock 原厂仪表也一直显示 97**，与 Tesla 实际
  电量（用户报告 63%）不一致 —— 第三方 MCU 固件缺陷，不是解码错误。
- Range（`0x04[6..7]`）为实时数据：观察期内 254→253→251 km 随用电下降，
  与车辆显示一致（±1 km）。
- 处理策略：MCU 的 SOC 标记为不可信；未来由 Commander 提供真实 SOC，
  经 source arbitration 覆盖（Primary=Commander for soc）。

## 重要发现：framebuffer 读取方法

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
