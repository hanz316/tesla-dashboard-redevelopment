#include "dashboard/vehicle_visual_controller.h"

// Keep the assertions live even in a Release build (NDEBUG).
#undef NDEBUG
#include <cassert>
#include <iostream>

using namespace dashboard;

namespace {

Signal<bool> fresh(bool value, std::uint64_t timestamp_ms) {
    Signal<bool> signal;
    signal.update(value, timestamp_ms, SignalSource::OriginalMcu,
                  SignalQuality::Confirmed, Unit::None);
    return signal;
}

VehicleState allClosed(std::uint64_t now_ms) {
    VehicleState state;
    state.door_fl = fresh(false, now_ms);
    state.door_fr = fresh(false, now_ms);
    state.door_rl = fresh(false, now_ms);
    state.door_rr = fresh(false, now_ms);
    state.frunk = fresh(false, now_ms);
    state.trunk = fresh(false, now_ms);
    // Lamps too: a state where the lights carry no signal at all is the
    // unknown case, not the "everything off" case.
    state.brake_light = fresh(false, now_ms);
    state.turn_signal_left = fresh(false, now_ms);
    state.turn_signal_right = fresh(false, now_ms);
    state.hazards = fresh(false, now_ms);
    state.headlights = fresh(false, now_ms);
    state.position_light = fresh(false, now_ms);
    return state;
}

bool hasLayer(const VehicleVisualFrame& frame, const char* id) {
    for (const VisualLayer& layer : frame.layers) {
        if (layer.asset_id == id) return true;
    }
    return false;
}

}  // namespace

int main() {
    const std::uint64_t t0 = 1'000'000;

    // A known-off lamp and an unknown lamp must not be the same thing.
    {
        VehicleVisualController controller;
        VehicleState state = allClosed(t0);
        state.brake_light = fresh(false, t0);
        state.turn_signal_left = fresh(false, t0);
        const VehicleVisualFrame& off = controller.update(state, t0);
        assert(off.brake.known == VisualKnown::Known);
        assert(!off.brake.lit);
        assert(!off.has_unknown());

        VehicleState missing = allClosed(t0);
        missing.brake_light.invalidate(t0);          // no signal at all
        const VehicleVisualFrame& unknown = controller.update(missing, t0);
        assert(unknown.brake.known == VisualKnown::Unknown);
        assert(!unknown.brake.lit);
        assert(unknown.has_unknown());
        std::cout << "UNKNOWN != OFF: unknown brake is reported unknown, not off\n";
    }

    // A stale signal is unknown too, and never silently becomes "off".
    {
        VehicleVisualController controller;
        VehicleState state = allClosed(t0);
        state.brake_light = fresh(true, t0);
        const VehicleVisualFrame& lit = controller.update(state, t0 + 10);
        assert(lit.brake.lit);
        const VehicleVisualFrame& stale =
            controller.update(state, t0 + 10 + FreshnessPolicy{}.lighting_ms + 1);
        assert(stale.brake.known == VisualKnown::Unknown);
        assert(!stale.brake.lit);
        std::cout << "stale brake is unknown, not off\n";
    }

    // Indicators are independent, hazard drives both, brake composes.
    {
        VehicleVisualController controller;
        VehicleState state = allClosed(t0);
        state.turn_signal_left = fresh(true, t0);
        state.turn_signal_right = fresh(false, t0);
        state.hazards = fresh(false, t0);
        const VehicleVisualFrame& left = controller.update(state, t0);
        assert(left.left_indicator.lit);
        assert(!left.right_indicator.lit);
        assert(hasLayer(left, "vehicle.indicator.left"));
        assert(!hasLayer(left, "vehicle.indicator.right"));

        state.hazards = fresh(true, t0 + 20);
        const VehicleVisualFrame& hazard = controller.update(state, t0 + 20);
        assert(hazard.left_indicator.lit && hazard.right_indicator.lit);
        assert(hasLayer(hazard, "vehicle.hazard"));

        state.brake_light = fresh(true, t0 + 40);
        state.turn_signal_left = fresh(true, t0 + 40);
        state.turn_signal_right = fresh(false, t0 + 40);
        state.hazards = fresh(false, t0 + 40);
        const VehicleVisualFrame& brake_left = controller.update(state, t0 + 40);
        assert(brake_left.brake.lit);
        assert(brake_left.left_indicator.lit);
        assert(!brake_left.right_indicator.lit);
        assert(hasLayer(brake_left, "vehicle.brake"));
        assert(hasLayer(brake_left, "vehicle.indicator.left"));
        std::cout << "indicator/brake/hazard composition holds\n";
    }

    // A door opens over its duration and stops at the terminal state.
    {
        VehicleVisualController controller;
        PanelTiming timing;
        timing.open_duration_s = 0.62F;
        timing.close_duration_s = 0.54F;
        controller.setPanelTiming("door_fl", timing);
        VehicleState state = allClosed(t0);
        state.door_fl = fresh(true, t0);
        const VehicleVisualFrame& start = controller.update(state, t0);
        assert(start.door_fl.motion == PanelMotion::Closed);
        const VehicleVisualFrame& mid = controller.update(state, t0 + 310);
        assert(mid.door_fl.motion == PanelMotion::Opening);
        assert(mid.door_fl.position > 0.0F && mid.door_fl.position < 1.0F);
        const VehicleVisualFrame& done = controller.update(state, t0 + 900);
        assert(done.door_fl.motion == PanelMotion::Open);
        assert(done.door_fl.position == 1.0F);
        assert(hasLayer(done, "vehicle.door.fl"));
        // Terminal state keeps a fixed asset frame rather than drifting.
        const VehicleVisualFrame& held = controller.update(state, t0 + 3000);
        assert(held.door_fl.position == 1.0F);
        std::cout << "door_fl opens to its terminal state and holds\n";
    }

    // A missing door signal holds the panel: it must not snap shut.
    {
        VehicleVisualController controller;
        VehicleState state = allClosed(t0);
        state.door_fl = fresh(true, t0);
        controller.update(state, t0);
        controller.update(state, t0 + 900);
        assert(controller.frame().door_fl.motion == PanelMotion::Open);
        VehicleState lost = allClosed(t0 + 1000);
        lost.door_fl.invalidate(t0 + 1000);
        const VehicleVisualFrame& held = controller.update(lost, t0 + 1000);
        assert(held.door_fl.known == VisualKnown::Unknown);
        assert(held.door_fl.position == 1.0F);
        assert(held.door_fl.motion == PanelMotion::Open);
        std::cout << "missing door signal holds the open door\n";
    }

    // Production refuses mock state; developer mode allows it.
    {
        VehicleVisualController controller;
        VehicleState mock = allClosed(t0);
        mock.brake_light = fresh(true, t0);
        assert(!controller.applyMockState(mock, t0));
        assert(!controller.developerMode());
        controller.setDeveloperMode(true);
        assert(controller.applyMockState(mock, t0));
        assert(controller.frame().brake.lit);
        std::cout << "mock state is refused in production and allowed in "
                     "developer mode\n";
    }

    // The base layer is always first and the lighting overlays are never
    // replacements of the body.
    {
        VehicleVisualController controller;
        VehicleState state = allClosed(t0);
        state.brake_light = fresh(true, t0);
        state.headlights = fresh(true, t0);
        const VehicleVisualFrame& frame = controller.update(state, t0);
        assert(!frame.layers.empty());
        assert(frame.layers.front().asset_id == "vehicle.base");
        for (std::size_t i = 0; i < frame.layers.size(); ++i) {
            const VisualLayer& layer = frame.layers[i];
            if (i == 0) continue;
            const bool replacement =
                layer.asset_id.rfind("vehicle.door", 0) == 0
                || layer.asset_id == "vehicle.frunk"
                || layer.asset_id == "vehicle.trunk";
            assert(layer.replace_base == replacement);
        }
        std::cout << "layer order and replacement flags are consistent\n";
    }

    std::cout << "all vehicle visual controller checks passed\n";
    return 0;
}
