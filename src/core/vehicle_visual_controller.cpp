#include "dashboard/vehicle_visual_controller.h"

#include <algorithm>
#include <cmath>

namespace dashboard {
namespace {

constexpr const char* kBaseLayer = "vehicle.base";
constexpr std::uint32_t kBaseFrame = 0;

float stepTowards(float value, float target, float delta) {
    if (value < target) return std::min(target, value + delta);
    if (value > target) return std::max(target, value - delta);
    return target;
}

}  // namespace

const char* panelMotionName(PanelMotion motion) {
    switch (motion) {
        case PanelMotion::Unknown: return "UNKNOWN";
        case PanelMotion::Closed: return "CLOSED";
        case PanelMotion::Opening: return "OPENING";
        case PanelMotion::Open: return "OPEN";
        case PanelMotion::Closing: return "CLOSING";
    }
    return "UNKNOWN";
}

bool VehicleVisualFrame::has_unknown() const {
    const LampVisual lamps[] = {brake, left_indicator, right_indicator,
                                hazard, headlight, running_light};
    for (const LampVisual& lamp : lamps) {
        if (lamp.unknown()) return true;
    }
    const PanelVisual panels[] = {door_fl, door_fr, door_rl, door_rr, frunk,
                                  trunk};
    for (const PanelVisual& panel : panels) {
        if (panel.known == VisualKnown::Unknown) return true;
    }
    return false;
}

VehicleVisualController::VehicleVisualController(const FreshnessPolicy& policy)
    : policy_(policy) {
    door_timing_ = PanelTiming{};
    hood_timing_ = PanelTiming{0.58F, 0.50F};
}

void VehicleVisualController::setDeveloperMode(bool enabled) {
    developer_mode_ = enabled;
}

bool VehicleVisualController::applyMockState(const VehicleState& mock,
                                             std::uint64_t now_ms) {
    if (!developer_mode_) {
        // Production must never fall back to mock data. Refusing here is the
        // last line of defence behind the asset-source rule in
        // assets/manifest.json (production_allows_placeholder = false).
        note_ = "mock state refused: developer mode is off";
        return false;
    }
    ++mock_uses_;
    update(mock, now_ms);
    note_ = "developer mode: mock state applied";
    return true;
}

void VehicleVisualController::setPanelTiming(const std::string& panel,
                                             const PanelTiming& timing) {
    if (panel == "frunk" || panel == "trunk") {
        hood_timing_ = timing;
    } else {
        door_timing_ = timing;
    }
}

LampVisual VehicleVisualController::lampFrom(const Signal<bool>& signal,
                                             std::uint64_t now_ms,
                                             std::uint64_t timeout_ms,
                                             const char* name) {
    LampVisual out;
    if (!signal.valid && !signal.stale) {
        note_ = std::string(name) + ": no signal (unknown, not off)";
        return out;                       // known stays Unknown, lit false
    }
    if (signal.stale) {
        note_ = std::string(name) + ": stale signal (unknown, not off)";
        return out;
    }
    if (signal.ageMs(now_ms) > timeout_ms) {
        note_ = std::string(name) + ": signal older than the policy window";
        return out;
    }
    out.lit = signal.value;
    out.known = VisualKnown::Known;
    return out;
}

PanelVisual VehicleVisualController::panelStep(PanelVisual previous,
                                               const Signal<bool>& signal,
                                               std::uint64_t now_ms,
                                               float dt_s,
                                               std::uint64_t timeout_ms,
                                               const PanelTiming& timing,
                                               const char* name) {
    PanelVisual out = previous;
    if (out.known == VisualKnown::Unknown) {
        out.motion = PanelMotion::Unknown;
    }
    if (!signal.valid || signal.stale || signal.ageMs(now_ms) > timeout_ms) {
        // A missing door signal holds the panel where it is. Snapping it shut
        // would draw a door that is physically open as closed.
        out.known = VisualKnown::Unknown;
        out.motion = out.motion == PanelMotion::Open ? PanelMotion::Open
                    : out.motion == PanelMotion::Closed ? PanelMotion::Closed
                    : PanelMotion::Unknown;
        note_ = std::string(name) + ": no fresh signal, holding position";
        return out;
    }
    const float target = signal.value ? 1.0F : 0.0F;
    const float duration =
        (target > out.position ? timing.open_duration_s
                               : timing.close_duration_s);
    const float per_second = duration > 0.0F ? 1.0F / duration : 1.0F;
    const float delta = per_second * std::max(0.0F, dt_s);
    const float next = stepTowards(out.position, target, delta);
    if (next != out.position) {
        if (out.animating_since_ms == 0) out.animating_since_ms = now_ms;
    }
    out.position = next;
    out.known = VisualKnown::Known;
    if (next <= 0.0F) {
        out.motion = PanelMotion::Closed;
        out.animating_since_ms = 0;
    } else if (next >= 1.0F) {
        out.motion = PanelMotion::Open;
        out.animating_since_ms = 0;
    } else {
        out.motion = target > next ? PanelMotion::Opening
                                   : PanelMotion::Closing;
    }
    return out;
}

const VehicleVisualFrame& VehicleVisualController::update(
    const VehicleState& state, std::uint64_t now_ms) {
    note_ = "ok";
    frame_.awareness = projectVehicleAwareness(state, now_ms, policy_, developer_mode_);
    const std::uint64_t light = policy_.lighting_ms;
    const std::uint64_t vehicle = policy_.vehicle_ms;

    frame_.brake = lampFrom(state.brake_light, now_ms, light, "brake");
    frame_.left_indicator =
        lampFrom(state.turn_signal_left, now_ms, light, "indicator_left");
    frame_.right_indicator =
        lampFrom(state.turn_signal_right, now_ms, light, "indicator_right");
    frame_.hazard = lampFrom(state.hazards, now_ms, light, "hazard");
    frame_.headlight = lampFrom(state.headlights, now_ms, light, "headlight");
    frame_.running_light =
        lampFrom(state.position_light, now_ms, light, "position_light");

    // Hazard drives both sides; it never erases an indicator that is already
    // on, and an unknown hazard signal does not turn anything off.
    if (frame_.hazard.known == VisualKnown::Known && frame_.hazard.lit) {
        frame_.left_indicator.lit = true;
        frame_.right_indicator.lit = true;
        frame_.left_indicator.known = VisualKnown::Known;
        frame_.right_indicator.known = VisualKnown::Known;
    }

    const std::uint64_t prev_stamp = frame_.timestamp_ms;
    const float dt_s = has_state_ && now_ms > prev_stamp
                           // A gap this large means the cluster was not
                           // rendering; the panel then simply arrives at its
                           // target instead of crawling there. Anything up to
                           // 2 s is treated as real elapsed time.
                           ? std::min(2.0F,
                                      static_cast<float>(now_ms - prev_stamp)
                                          / 1000.0F)
                           : 0.0F;

    frame_.door_fl = panelStep(frame_.door_fl, state.door_fl, now_ms, dt_s,
                               vehicle, door_timing_, "door_fl");
    frame_.door_fr = panelStep(frame_.door_fr, state.door_fr, now_ms, dt_s,
                               vehicle, door_timing_, "door_fr");
    frame_.door_rl = panelStep(frame_.door_rl, state.door_rl, now_ms, dt_s,
                               vehicle, door_timing_, "door_rl");
    frame_.door_rr = panelStep(frame_.door_rr, state.door_rr, now_ms, dt_s,
                               vehicle, door_timing_, "door_rr");
    frame_.frunk = panelStep(frame_.frunk, state.frunk, now_ms, dt_s, vehicle,
                             hood_timing_, "frunk");
    frame_.trunk = panelStep(frame_.trunk, state.trunk, now_ms, dt_s, vehicle,
                             hood_timing_, "trunk");

    frame_.timestamp_ms = now_ms;
    has_state_ = true;
    buildLayers();
    return frame_;
}

void VehicleVisualController::buildLayers() {
    frame_.layers.clear();
    frame_.layers.push_back({kBaseLayer, kBaseFrame, true});

    struct PanelLayer {
        const PanelVisual* panel;
        const char* asset;
        std::uint32_t frames;
    };
    const PanelLayer panels[] = {
        {&frame_.door_fl, "vehicle.door.fl", 16},
        {&frame_.door_fr, "vehicle.door.fr", 16},
        {&frame_.door_rl, "vehicle.door.rl", 16},
        {&frame_.door_rr, "vehicle.door.rr", 16},
        {&frame_.frunk, "vehicle.frunk", 14},
        {&frame_.trunk, "vehicle.trunk", 14},
    };
    for (const PanelLayer& panel : panels) {
        if (panel.panel->position <= 0.0F) continue;
        const float clamped = std::min(1.0F, panel.panel->position);
        const std::uint32_t index = static_cast<std::uint32_t>(
            std::lround(clamped * static_cast<float>(panel.frames - 1)));
        frame_.layers.push_back(
            {panel.asset, std::min(index, panel.frames - 1), true});
    }

    // Lighting overlays are drawn on top of whatever body layer is showing.
    if (frame_.brake.lit) frame_.layers.push_back({"vehicle.brake", 0, false});
    if (frame_.headlight.lit) {
        frame_.layers.push_back({"vehicle.headlight", 0, false});
    }
    if (frame_.running_light.lit) {
        frame_.layers.push_back({"vehicle.running", 0, false});
    }
    const bool left = frame_.left_indicator.lit;
    const bool right = frame_.right_indicator.lit;
    if (left && right) {
        frame_.layers.push_back({"vehicle.hazard", 0, false});
    } else if (left) {
        frame_.layers.push_back({"vehicle.indicator.left", 0, false});
    } else if (right) {
        frame_.layers.push_back({"vehicle.indicator.right", 0, false});
    }

    // Awareness is a semantic projection, so the renderer receives only
    // validated left/right presence. It never sees the UART candidate bits.
    if (frame_.awareness.left.present) {
        frame_.layers.push_back({"horizon.blind.left", 0, false});
    }
    if (frame_.awareness.right.present) {
        frame_.layers.push_back({"horizon.blind.right", 0, false});
    }
}

}  // namespace dashboard
