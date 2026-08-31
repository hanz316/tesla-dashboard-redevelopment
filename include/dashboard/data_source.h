#pragma once

#include "dashboard/signal.h"
#include "dashboard/vehicle_state.h"

#include <array>
#include <cstdint>
#include <string>

namespace dashboard {

enum class DataSourceStatus : std::uint8_t {
    Disabled = 0,
    Offline,
    Connecting,
    Connected,
    Error,
};

struct DataSourceHealth {
    DataSourceStatus status{DataSourceStatus::Offline};
    std::uint64_t last_update_ms{0};
    std::uint64_t packets{0};
    std::uint64_t errors{0};
};

// Unified contract every data source implements. The UI only ever reads
// VehicleState through this interface, so sources can be swapped
// (Original MCU, Replay, Simulation, Commander, PhoneBridge) without UI
// changes.
class IDataSource {
public:
    virtual ~IDataSource() = default;

    virtual const char* name() const = 0;
    virtual SignalSource source() const = 0;
    virtual const VehicleState& state() const = 0;
    virtual const DataSourceHealth& health() const = 0;
    // Called periodically so the source can expire stale signals and
    // update its health status.
    virtual void tick(std::uint64_t now_ms) = 0;
};

// ---------- Source arbitration (Build 0.2 / Commander) ----------
//
// When multiple sources provide the same signal (Original MCU vs
// Commander), the UI should not show whichever wrote last. Each signal
// group declares a primary and fallback source; consumers merge by:
//   1. if primary signal is fresh -> use primary
//   2. else if fallback is fresh -> use fallback
//   3. else -> unavailable

enum class SignalGroup : std::uint8_t {
    Driving = 0,
    Gear,
    Battery,
    Doors,
    Tires,
    Temperatures,
    Adas,
};

struct SignalSourcePriority {
    SignalSource primary{SignalSource::OriginalMcu};
    SignalSource fallback{SignalSource::Unavailable};
};

// ---------- Commander status / raw CAN (reserved) ----------

struct CommanderStatus {
    bool connected{false};
    bool authenticated{false};
    std::string device_uid;
    std::string device_mac;
    std::string vin;
    std::string firmware_version;
    std::uint64_t last_packet_time_ms{0};
    float packet_rate_hz{0};
    int signal_quality{0};
    bool raw_can_active{false};
};

struct RawCanFrame {
    std::uint64_t timestamp_ms{0};
    int bus{0};
    std::uint32_t id{0};
    std::uint8_t dlc{0};
    std::array<std::uint8_t, 8> data{};
};

}  // namespace dashboard
