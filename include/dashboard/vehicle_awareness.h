#pragma once

#include "dashboard/vehicle_state.h"

namespace dashboard {

// Semantics only. Protocol bytes never enter a renderer. Confirmed means the
// adapter mapping was validated; Inferred/Estimated cannot trigger production.
enum class AwarenessKnown : std::uint8_t { Unknown = 0, Known };
enum class BlindZoneState : std::uint8_t { Unknown = 0, None, Left, Right, Both };

struct AwarenessSide {
    AwarenessKnown known{AwarenessKnown::Unknown};
    bool present{false};
    bool indicator_attention{false};  // intent + presence, never collision risk
};

struct VehicleAwarenessFrame {
    AwarenessSide left;
    AwarenessSide right;
    BlindZoneState state{BlindZoneState::Unknown};
};

VehicleAwarenessFrame projectVehicleAwareness(const VehicleState& state,
    std::uint64_t now_ms, const FreshnessPolicy& policy, bool developer_mode);

}  // namespace dashboard
