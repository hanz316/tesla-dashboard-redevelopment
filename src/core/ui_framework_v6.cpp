#include "dashboard/ui_framework_v6.h"

#include <algorithm>

namespace dashboard {
namespace {

const Signal<std::uint8_t>* trustedSoc(const VehicleState& state) {
    if (state.actual_soc.valid && !state.actual_soc.stale) return &state.actual_soc;
    if (state.soc.valid && !state.soc.stale && state.soc.quality != SignalQuality::Estimated)
        return &state.soc;
    return nullptr;
}

}  // namespace

PageManagerV6::PageManagerV6(DashboardPageV6 initial) {
    state_.current = initial;
    state_.target = initial;
}

std::vector<DashboardPageV6> swipeOrderV6() {
    return {DashboardPageV6::Horizon, DashboardPageV6::Mono,
            DashboardPageV6::Pulse, DashboardPageV6::Route,
            DashboardPageV6::Studio, DashboardPageV6::Energy,
            DashboardPageV6::Nocturne, DashboardPageV6::Settings};
}

bool isDrivingPageV6(DashboardPageV6 page) {
    switch (page) {
        case DashboardPageV6::Horizon:
        case DashboardPageV6::Mono:
        case DashboardPageV6::Pulse:
        case DashboardPageV6::Route:
        case DashboardPageV6::Studio:
        case DashboardPageV6::Energy:
        case DashboardPageV6::Nocturne:
            return true;
        case DashboardPageV6::Settings:
        case DashboardPageV6::Developer:
        default:
            return false;
    }
}

bool pageIsReachableV6(DashboardPageV6 page, bool developer_mode_enabled) {
    if (page == DashboardPageV6::Developer) return developer_mode_enabled;
    return true;
}

DashboardPageV6 stepPageV6(DashboardPageV6 current, int step,
                           bool developer_mode_enabled) {
    const std::vector<DashboardPageV6> ring = swipeOrderV6();
    if (ring.empty()) return current;

    const auto position = [&ring](DashboardPageV6 page) {
        for (std::size_t i = 0; i < ring.size(); ++i) {
            if (ring[i] == page) return static_cast<int>(i);
        }
        return -1;
    };

    const int size = static_cast<int>(ring.size());
    int index = position(current);
    if (index < 0) {
        // Entering the ring from a screen that is not in it (Developer, or a
        // page from a future build): forwards starts at the first page,
        // backwards at the last.
        index = step >= 0 ? -1 : size;
    }
    int direction = step >= 0 ? 1 : -1;
    const int magnitude = step >= 0 ? step : -step;
    for (int i = 0; i < magnitude; ++i) {
        index = ((index + direction) % size + size) % size;
    }
    DashboardPageV6 candidate = ring[static_cast<std::size_t>(index)];
    if (!pageIsReachableV6(candidate, developer_mode_enabled)) {
        // The ring only contains reachable pages today; this guard keeps the
        // rule true if Developer is ever added to it.
        return current;
    }
    return candidate;
}

DashboardPageV6 safetyPageV6() {
    return DashboardPageV6::Horizon;
}

void PageManagerV6::requestNext(int step, bool developer_mode_enabled) {
    if (step == 0) return;
    request(stepPageV6(state_.current, step, developer_mode_enabled));
}

void PageManagerV6::request(DashboardPageV6 page, bool safety_interrupt) {
    if (page == state_.current && !state_.active) return;
    state_.target = page;
    if (safety_interrupt) {
        state_.current = page;
        state_.active = false;
        state_.elapsed_ms = state_.duration_ms;
        state_.progress = 1.0F;
        state_.opacity = 1.0F;
        state_.translation_x = 0.0F;
        state_.scale = 1.0F;
        return;
    }
    state_.active = true;
    state_.elapsed_ms = 0;
    state_.progress = 0.0F;
}

void PageManagerV6::update(std::uint32_t dt_ms, MotionQuality quality) {
    if (!state_.active) return;
    if (quality == MotionQuality::Off) {
        state_.current = state_.target;
        state_.active = false;
        state_.elapsed_ms = state_.duration_ms;
        state_.progress = 1.0F;
        state_.opacity = 1.0F;
        state_.translation_x = 0.0F;
        state_.scale = 1.0F;
        return;
    }

    state_.elapsed_ms = std::min(state_.duration_ms, state_.elapsed_ms + dt_ms);
    const float t = state_.duration_ms == 0 ? 1.0F
        : static_cast<float>(state_.elapsed_ms) / static_cast<float>(state_.duration_ms);
    const float eased = 1.0F - (1.0F - t) * (1.0F - t) * (1.0F - t);
    state_.progress = eased;
    const float movement = quality == MotionQuality::Low ? 8.0F : 18.0F;
    state_.translation_x = movement * (1.0F - eased);
    state_.scale = 0.98F + 0.02F * eased;
    state_.opacity = 0.72F + 0.28F * eased;
    if (state_.elapsed_ms >= state_.duration_ms) {
        state_.current = state_.target;
        state_.active = false;
        state_.progress = 1.0F;
        state_.translation_x = 0.0F;
        state_.scale = 1.0F;
        state_.opacity = 1.0F;
    }
}

SafetyLayerV6 buildSafetyLayerV6(const VehicleState& state, const WarningManager& warnings) {
    SafetyLayerV6 out;
    out.speed_available = state.speed.valid && !state.speed.stale;
    out.speed_kph = out.speed_available ? state.speed.value : 0;
    out.gear_available = state.gear.valid && !state.gear.stale && state.gear.value != Gear::Unknown;
    out.gear = out.gear_available ? state.gear.value : Gear::Unknown;
    const Signal<std::uint8_t>* soc = trustedSoc(state);
    out.soc_available = soc != nullptr;
    out.soc_percent = soc ? soc->value : 0;
    out.hazards = state.hazards.valid && !state.hazards.stale && state.hazards.value;
    out.left_indicator = out.hazards || (state.turn_signal_left.valid && !state.turn_signal_left.stale && state.turn_signal_left.value);
    out.right_indicator = out.hazards || (state.turn_signal_right.valid && !state.turn_signal_right.stale && state.turn_signal_right.value);
    out.warning = warnings.evaluate(state);

    if (out.warning.code == WarningCode::VehicleDataLost ||
        ((!state.speed.valid || state.speed.stale) &&
         (!state.gear.valid || state.gear.stale || state.gear.value == Gear::Unknown))) {
        out.availability = DataAvailabilityLevel::CoreVehicleDataLost;
    } else if (!out.speed_available || !out.gear_available || !out.soc_available) {
        out.availability = DataAvailabilityLevel::IndividualSignalUnavailable;
    } else if ((!state.battery_power.valid || state.battery_power.stale) &&
               (!state.front_motor_power.valid || state.front_motor_power.stale) &&
               (!state.rear_motor_power.valid || state.rear_motor_power.stale)) {
        out.availability = DataAvailabilityLevel::EnhancedModuleUnavailable;
    } else {
        out.availability = DataAvailabilityLevel::Available;
    }
    return out;
}

HorizonContextRailState buildHorizonContextRail(const VehicleState& vehicle,
                                                const ProductStateV6& product) {
    HorizonContextRailState out;
    if (product.navigation.available && product.navigation.active &&
        product.navigation.has(NavigationCapability::BasicManeuver)) {
        out.mode = HorizonContextRailState::Mode::Navigation;
        out.navigation = &product.navigation;
        return out;
    }

    if ((vehicle.trip_distance.valid && !vehicle.trip_distance.stale) ||
        (vehicle.trip_time.valid && !vehicle.trip_time.stale) ||
        (vehicle.average_speed.valid && !vehicle.average_speed.stale)) {
        out.mode = HorizonContextRailState::Mode::Trip;
        out.trip_distance_available = vehicle.trip_distance.valid && !vehicle.trip_distance.stale;
        out.trip_distance_km = out.trip_distance_available ? vehicle.trip_distance.value : 0.0F;
        out.trip_duration_available = vehicle.trip_time.valid && !vehicle.trip_time.stale;
        out.trip_duration_ms = out.trip_duration_available ? vehicle.trip_time.value : 0;
        out.trip_avg_speed_available = vehicle.average_speed.valid && !vehicle.average_speed.stale;
        out.trip_avg_speed_kph = out.trip_avg_speed_available ? vehicle.average_speed.value : 0.0F;
        return out;
    }

    const Signal<std::uint8_t>* soc = trustedSoc(vehicle);
    if (soc || (vehicle.range.valid && !vehicle.range.stale)) {
        out.mode = HorizonContextRailState::Mode::Battery;
        out.soc_available = soc != nullptr;
        out.soc = soc ? soc->value : 0;
        out.range_available = vehicle.range.valid && !vehicle.range.stale;
        out.range_km = out.range_available ? vehicle.range.value : 0;
        return out;
    }

    out.mode = HorizonContextRailState::Mode::None;
    return out;
}

}  // namespace dashboard
