#include "dashboard/v6_cockpit.h"

#include <algorithm>
#include <cmath>

namespace dashboard {

WarningState WarningManager::evaluate(const VehicleState& s) const {
    const bool speed_known = s.speed.valid;
    const bool moving = speed_known && s.speed.value > 0;

    if (!s.speed.valid && s.speed.stale)
        return {WarningCode::VehicleDataLost, WarningSeverity::Critical, true};

    if (moving && s.frunk.valid && s.frunk.value)
        return {WarningCode::FrunkOpenMoving, WarningSeverity::Critical, true};

    const bool any_door = (s.door_fl.valid && s.door_fl.value) ||
                          (s.door_fr.valid && s.door_fr.value) ||
                          (s.door_rl.valid && s.door_rl.value) ||
                          (s.door_rr.valid && s.door_rr.value);
    if (moving && any_door)
        return {WarningCode::DoorOpenMoving, WarningSeverity::Warning, true};

    if (moving && s.trunk.valid && s.trunk.value)
        return {WarningCode::TrunkOpenMoving, WarningSeverity::Warning, true};

    const auto low_tire = [](const Signal<float>& t) {
        return t.valid && t.value > 0.0F && t.value < 2.2F;
    };
    if (low_tire(s.tire_fl) || low_tire(s.tire_fr) || low_tire(s.tire_rl) || low_tire(s.tire_rr))
        return {WarningCode::LowTire, WarningSeverity::Caution, true};

    const Signal<std::uint8_t>& soc = s.actual_soc.valid ? s.actual_soc : s.soc;
    if (soc.valid && soc.value <= 10)
        return {WarningCode::LowSoc, WarningSeverity::Caution, true};

    return {};
}

float MotionEngine::update(MotionValue& value, float raw, std::uint32_t dt_ms,
                           std::uint32_t duration_ms, MotionPriority priority) {
    value.raw = raw;
    if (!value.initialized || quality_ == MotionQuality::Off ||
        priority == MotionPriority::Critical || priority == MotionPriority::Driving || duration_ms == 0) {
        value.display = raw;
        value.initialized = true;
        return value.display;
    }

    std::uint32_t effective = duration_ms;
    if (quality_ == MotionQuality::Low) effective = std::max<std::uint32_t>(50, duration_ms / 2);
    const float t = std::min(1.0F, static_cast<float>(dt_ms) / static_cast<float>(effective));
    const float eased = 1.0F - std::pow(1.0F - t, 3.0F);
    value.display += (raw - value.display) * eased;
    return value.display;
}

void AssetManager::registerAsset(const AssetDescriptor& asset) {
    auto it = entries_.find(asset.id);
    if (it == entries_.end()) entries_.insert({asset.id, Entry{asset, 0, false}});
    else it->second.asset = asset;
}

bool AssetManager::acquire(const std::string& id) {
    auto it = entries_.find(id);
    if (it == entries_.end()) return false;
    Entry& e = it->second;
    if (!e.resident) {
        if (e.asset.estimated_bytes > budget_ || resident_bytes_ + e.asset.estimated_bytes > budget_)
            return false;
        e.resident = true;
        resident_bytes_ += e.asset.estimated_bytes;
    }
    ++e.refs;
    return true;
}

void AssetManager::release(const std::string& id) {
    auto it = entries_.find(id);
    if (it == entries_.end()) return;
    Entry& e = it->second;
    if (e.refs > 0) --e.refs;
    if (e.refs == 0 && e.resident && !e.asset.shared) {
        resident_bytes_ -= e.asset.estimated_bytes;
        e.resident = false;
    }
}

bool AssetManager::isResident(const std::string& id) const {
    auto it = entries_.find(id);
    return it != entries_.end() && it->second.resident;
}

void VehicleVisualModel::updateFrom(const VehicleState& s) {
    door_fl = s.door_fl.valid && s.door_fl.value;
    door_fr = s.door_fr.valid && s.door_fr.value;
    door_rl = s.door_rl.valid && s.door_rl.value;
    door_rr = s.door_rr.valid && s.door_rr.value;
    frunk = s.frunk.valid && s.frunk.value;
    trunk = s.trunk.valid && s.trunk.value;
    headlights = s.headlights.valid && s.headlights.value;
    high_beam = s.high_beam.valid && s.high_beam.value;
    brake_lights = s.brake_light.valid && s.brake_light.value;
    left_indicator = (s.hazards.valid && s.hazards.value) ||
                     (s.turn_signal_left.valid && s.turn_signal_left.value);
    right_indicator = (s.hazards.valid && s.hazards.value) ||
                      (s.turn_signal_right.valid && s.turn_signal_right.value);
    front_axle_active = s.front_motor_power.valid && std::fabs(s.front_motor_power.value) > 0.5F;
    rear_axle_active = s.rear_motor_power.valid && std::fabs(s.rear_motor_power.value) > 0.5F;
    if (s.battery_power.valid) energy_halo = std::max(-1.0F, std::min(1.0F, s.battery_power.value / 250.0F));
    else energy_halo = 0.0F;
}

HorizonSceneState buildHorizonScene(const VehicleState& s, const WarningManager& warnings) {
    HorizonSceneState out;
    out.vehicle.updateFrom(s);
    out.speed_available = s.speed.valid;
    out.speed = s.speed.valid ? s.speed.value : 0;
    out.gear_available = s.gear.valid;
    out.gear = s.gear.valid ? s.gear.value : Gear::Unknown;
    const Signal<std::uint8_t>& soc = s.actual_soc.valid ? s.actual_soc : s.soc;
    out.soc_available = soc.valid;
    out.soc = soc.valid ? soc.value : 0;
    out.range_available = s.range.valid;
    out.range = s.range.valid ? s.range.value : 0;
    out.warning = warnings.evaluate(s);

    out.surrounding.front = s.front_vehicle_present.valid && s.front_vehicle_present.value;
    out.surrounding.left = (s.left_vehicle_present.valid && s.left_vehicle_present.value) ||
                           (s.surrounding_vehicle_left.valid && s.surrounding_vehicle_left.value);
    out.surrounding.right = (s.right_vehicle_present.valid && s.right_vehicle_present.value) ||
                            (s.surrounding_vehicle_right.valid && s.surrounding_vehicle_right.value);
    out.surrounding.precise_positions_available =
        s.surrounding_position_mode.valid && s.surrounding_position_mode.value == SurroundingPositionMode::Precise;

    if (out.warning.code == WarningCode::VehicleDataLost) out.mode = HorizonMode::DataDegraded;
    else if (s.blind_spot_left.valid && s.blind_spot_left.value) out.mode = HorizonMode::LeftBlindSpot;
    else if (s.blind_spot_right.valid && s.blind_spot_right.value) out.mode = HorizonMode::RightBlindSpot;
    else if (s.autopilot_state.valid && s.autopilot_state.value == AutopilotState::Active) out.mode = HorizonMode::ApActive;
    else if (s.autopilot_state.valid && s.autopilot_state.value == AutopilotState::Available) out.mode = HorizonMode::ApAvailable;
    else out.mode = HorizonMode::Normal;
    return out;
}

}  // namespace dashboard
