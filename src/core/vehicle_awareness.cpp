#include "dashboard/vehicle_awareness.h"

namespace dashboard {
namespace {
bool usable(const Signal<bool>& signal, std::uint64_t now_ms,
            std::uint64_t timeout_ms, bool developer) {
    if (!signal.valid || signal.stale || signal.timestamp_ms > now_ms ||
        signal.ageMs(now_ms) > timeout_ms) return false;
    const bool synthetic = signal.source == SignalSource::Simulation ||
                           signal.source == SignalSource::Replay;
    if (synthetic) return developer;
    return signal.source != SignalSource::Unavailable &&
           signal.quality == SignalQuality::Confirmed;
}

AwarenessSide side(const Signal<bool>& blind, const Signal<bool>& adjacent,
                   const Signal<bool>& indicator, const Signal<bool>& hazard,
                   std::uint64_t now_ms, const FreshnessPolicy& policy,
                   bool developer) {
    AwarenessSide out;
    const bool b = usable(blind, now_ms, policy.adas_ms, developer);
    const bool a = usable(adjacent, now_ms, policy.adas_ms, developer);
    out.present = (b && blind.value) || (a && adjacent.value);
    if (out.present || (b && a)) out.known = AwarenessKnown::Known;
    out.indicator_attention = out.present &&
        ((usable(indicator, now_ms, policy.lighting_ms, developer) && indicator.value) ||
         (usable(hazard, now_ms, policy.lighting_ms, developer) && hazard.value));
    return out;
}
}  // namespace

VehicleAwarenessFrame projectVehicleAwareness(const VehicleState& state,
    std::uint64_t now_ms, const FreshnessPolicy& policy, bool developer_mode) {
    VehicleAwarenessFrame out;
    out.left = side(state.blind_spot_left, state.left_vehicle_present,
                    state.turn_signal_left, state.hazards, now_ms, policy, developer_mode);
    out.right = side(state.blind_spot_right, state.right_vehicle_present,
                     state.turn_signal_right, state.hazards, now_ms, policy, developer_mode);
    if (out.left.present && out.right.present) out.state = BlindZoneState::Both;
    else if (out.left.present) out.state = BlindZoneState::Left;
    else if (out.right.present) out.state = BlindZoneState::Right;
    else if (out.left.known == AwarenessKnown::Known && out.right.known == AwarenessKnown::Known)
        out.state = BlindZoneState::None;
    return out;
}
}  // namespace dashboard
