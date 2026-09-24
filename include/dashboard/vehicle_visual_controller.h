#pragma once

#include "dashboard/vehicle_state.h"
#include "dashboard/vehicle_awareness.h"

#include <cstdint>
#include <string>
#include <vector>

namespace dashboard {

// Task: Vehicle State Assets -> Horizon.
//
// The one place where vehicle signals become visual state. The UI never reads
// UART, BLE, Commander or PhoneBridge: it reads this frame.
//
// Hard rule: UNKNOWN != OFF. A lamp whose signal is missing, invalid or stale
// is reported as `known == false`, which is NOT the same as a lamp that was
// reported off. A door whose signal is missing keeps the position it already
// had instead of snapping shut. Nothing here invents a vehicle state.

enum class VisualKnown : std::uint8_t { Unknown = 0, Known, NotApplicable };

struct LampVisual {
    bool lit{false};
    VisualKnown known{VisualKnown::Unknown};

    bool unknown() const { return known == VisualKnown::Unknown; }
};

enum class PanelMotion : std::uint8_t {
    Unknown = 0,
    Closed,
    Opening,
    Open,
    Closing,
};

struct PanelVisual {
    // 0 = closed, 1 = fully open. This is the value the renderer maps onto an
    // asset sequence frame index.
    float position{0.0F};
    PanelMotion motion{PanelMotion::Unknown};
    VisualKnown known{VisualKnown::Unknown};
    std::uint64_t animating_since_ms{0};

    bool moving() const {
        return motion == PanelMotion::Opening || motion == PanelMotion::Closing;
    }
};

// Which asset layers the renderer must draw for this frame, in draw order.
// BASE is always first; moving panels replace it on the same canvas; the
// lighting overlays go on top.
struct VisualLayer {
    std::string asset_id;
    std::uint32_t frame_index{0};
    bool replace_base{false};
};

struct VehicleVisualFrame {
    VehicleAwarenessFrame awareness;
    LampVisual brake;
    LampVisual left_indicator;
    LampVisual right_indicator;
    LampVisual hazard;
    LampVisual headlight;
    LampVisual running_light;

    PanelVisual door_fl;
    PanelVisual door_fr;
    PanelVisual door_rl;
    PanelVisual door_rr;
    PanelVisual frunk;
    PanelVisual trunk;

    std::vector<VisualLayer> layers;
    std::uint64_t timestamp_ms{0};

    // True when any part of the frame could not be established from a valid
    // signal. The cluster shows the unknown treatment rather than an implied
    // "everything is off".
    bool has_unknown() const;
};

struct PanelTiming {
    float open_duration_s{0.62F};
    float close_duration_s{0.54F};
};

class VehicleVisualController {
public:
    explicit VehicleVisualController(const FreshnessPolicy& policy = {});

    // Production is the default. Mock/replay state may only be injected when
    // Developer Mode was explicitly enabled; the production path refuses it.
    void setDeveloperMode(bool enabled);
    bool developerMode() const { return developer_mode_; }
    bool applyMockState(const VehicleState& mock, std::uint64_t now_ms);

    // Consumes canonical VehicleState only.
    const VehicleVisualFrame& update(const VehicleState& state,
                                     std::uint64_t now_ms);
    const VehicleVisualFrame& frame() const { return frame_; }

    void setPanelTiming(const std::string& panel, const PanelTiming& timing);
    const char* lastNote() const { return note_.c_str(); }

private:
    LampVisual lampFrom(const Signal<bool>& signal, std::uint64_t now_ms,
                        std::uint64_t timeout_ms, const char* name);
    PanelVisual panelStep(PanelVisual previous, const Signal<bool>& signal,
                          std::uint64_t now_ms, float dt_s,
                          std::uint64_t timeout_ms,
                          const PanelTiming& timing, const char* name);
    void buildLayers();

    FreshnessPolicy policy_;
    VehicleVisualFrame frame_;
    bool developer_mode_{false};
    bool has_state_{false};
    std::uint64_t mock_uses_{0};
    std::string note_;
    PanelTiming door_timing_;
    PanelTiming hood_timing_;
};

const char* panelMotionName(PanelMotion motion);

}  // namespace dashboard
