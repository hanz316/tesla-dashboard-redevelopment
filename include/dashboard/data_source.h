#pragma once

#include "dashboard/signal.h"
#include "dashboard/vehicle_state.h"

#include <cstdint>

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

class IDataSource {
public:
    virtual ~IDataSource() = default;

    virtual const char* name() const = 0;
    virtual SignalSource source() const = 0;
    virtual const VehicleState& state() const = 0;
    virtual const DataSourceHealth& health() const = 0;
    virtual void tick(std::uint64_t now_ms) = 0;
};

}  // namespace dashboard
