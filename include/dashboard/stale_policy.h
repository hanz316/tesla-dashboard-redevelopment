#pragma once

#include "dashboard/vehicle_state.h"

#include <cstdint>

namespace dashboard {

struct StaleTimeouts {
    std::uint64_t motion_ms{1500};
    std::uint64_t closures_ms{2500};
    std::uint64_t battery_ms{5000};
    std::uint64_t tires_ms{30000};
    std::uint64_t temperatures_ms{30000};
};

struct StaleSummary {
    std::uint32_t expired_signals{0};
    bool anyExpired() const { return expired_signals != 0; }
};

StaleSummary invalidateStale(
    VehicleState& state,
    std::uint64_t now_ms,
    const StaleTimeouts& timeouts = StaleTimeouts{});

}  // namespace dashboard
