# Original MCU ProtocolTable

状态定义：

- `CONFIRMED`：汇编/资源或明确计算路径已验证
- `LIKELY`：强证据推断，但仍需实车事件录制确认
- `UNKNOWN`：仅发现 command 或字段访问
- `NEEDS REAL CAR TEST`：必须靠开门、换档、轮胎位置等受控动作确认

## 帧

```text
Header    1 byte   0x2E
Command   1 byte
Length    1 byte
Payload   Length bytes
Checksum  1 byte  ~(Command + Length + sum(Payload)) & 0xFF
```

## Command 表

| CMD | 字段 | 解码 | 状态 |
|---:|---|---|---|
| `0x01` | gear | `(payload[4] >> 4)`: `0=P,1=R,2=N,3=D` | CONFIRMED |
| `0x01` | door FL | `payload[3] bit 0` | LIKELY / NEEDS REAL CAR TEST |
| `0x01` | door FR | `payload[3] bit 2` | LIKELY / NEEDS REAL CAR TEST |
| `0x01` | door RL | `payload[3] bit 1` | LIKELY / NEEDS REAL CAR TEST |
| `0x01` | door RR | `payload[3] bit 3` | LIKELY / NEEDS REAL CAR TEST |
| `0x01` | trunk | `payload[3] bit 4` | LIKELY / NEEDS REAL CAR TEST |
| `0x01` | frunk | `payload[3] bit 5` | LIKELY / NEEDS REAL CAR TEST |
| `0x01` | lighting/auto light | other bits in payload 1/2/6 | UNKNOWN |
| `0x02` | UI handles command | unknown payload mapping | UNKNOWN |
| `0x04` | speed | LE16 `payload[0..1]` | CONFIRMED |
| `0x04` | range | LE16 `payload[6..7]` | CONFIRMED |
| `0x04` | SOC | `payload[8]` percent | CONFIRMED |
| `0x04` | distance raw | LE24 `payload[10..12]`; scale unknown | LIKELY |
| `0x05` | handled before main dispatch | mapping unknown | UNKNOWN |
| `0x06` | subcommands in `payload[0]` | values include `1,2,3,0x11,0x12,0x14,0x15` | UNKNOWN |
| `0x07` | temperature primary | `(payload[0] >> 1) - 40` °C | LIKELY |
| `0x07` | temperature secondary | `payload[1] - 25` °C | LIKELY |
| `0x0F` | handled | mapping unknown | UNKNOWN |
| `0x11` | speed limit/overspeed | payload-specific | LIKELY |
| `0x12` | tire pressures | `payload[1..4] * 0.025` bar | CONFIRMED |
| `0x12` | physical tire order | configurable mapping | NEEDS REAL CAR TEST |
| `0x15` | handled | mapping unknown | UNKNOWN |
| `0x38` | AP/ADAS/surrounding state | payload-specific | LIKELY |
| `0x7F` | long status/debug payload | mapping unknown | UNKNOWN |

## 写入/控制边界

原固件存在：

```cpp
sendProtocolTo(int port, uint8_t command, const uint8_t* payload, uint16_t len)
```

并在 UI 中主动发送 `0x20`、`0x81`、`0x88`、`0xE3` 等 command。`0x88` 与灯光/按摩/AP help 等控制 UI 有交叉引用。

新 MVP 不实现发送 API；目标进程以 `O_RDONLY` 打开 `/dev/ttyS5`，链接符号中不存在 `write`。所有控制 command 在 Phase 0-4 禁止执行。

## Door mapping 说明

原程序从 `payload[3]` 提取六个 bit 的顺序是 `4,0,2,5,1,3`，与 `trunk, FL, FR, frunk, RL, RR` 的常见布局高度吻合。由于没有实车逐门录制，这六个位置在代码中保留可配置 mapping，质量标记为 `Inferred`，不会伪装成 `Confirmed`。
