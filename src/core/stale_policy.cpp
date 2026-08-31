#include "dashboard/stale_policy.h"

namespace dashboard {
namespace {

template <typename T>
bool expireIfStale(Signal<T>& signal, std::uint64_t now_ms, std::uint64_t timeout_ms) {
    if (!signal.valid || now_ms < signal.timestamp_ms) {
        return false;
    }
    if ((now_ms - signal.timestamp_ms) <= timeout_ms) {
        return false;
    }

    // A stale signal becomes unavailable to consumers, but its last source,
    // quality and timestamp are deliberately preserved for diagnostics.
    signal.valid = false;
    return true;
}

}  // namespace

StaleSummary invalidateStale(
    VehicleState& state,
    std::uint64_t now_ms,
    const StaleTimeouts& timeouts) {
    StaleSummary result;

#define EXPIRE(signal, timeout) \
    do { if (expireIfStale((signal), now_ms, (timeout))) ++result.expired_signals; } while (false)

    EXPIRE(state.speed, timeouts.motion_ms);
    EXPIRE(state.gear, timeouts.motion_ms);

    EXPIRE(state.door_fl, timeouts.closures_ms);
    EXPIRE(state.door_fr, timeouts.closures_ms);
    EXPIRE(state.door_rl, timeouts.closures_ms);
    EXPIRE(state.door_rr, timeouts.closures_ms);
    EXPIRE(state.frunk, timeouts.closures_ms);
    EXPIRE(state.trunk, timeouts.closures_ms);

    EXPIRE(state.soc, timeouts.battery_ms);
    EXPIRE(state.range, timeouts.battery_ms);
    EXPIRE(state.distance_raw, timeouts.battery_ms);

    EXPIRE(state.tire_fl, timeouts.tires_ms);
    EXPIRE(state.tire_fr, timeouts.tires_ms);
    EXPIRE(state.tire_rl, timeouts.tires_ms);
    EXPIRE(state.tire_rr, timeouts.tires_ms);

    EXPIRE(state.temperature_primary, timeouts.temperatures_ms);
    EXPIRE(state.temperature_secondary, timeouts.temperatures_ms);

#undef EXPIRE
    return result;
}

}  // namespace dashboard
