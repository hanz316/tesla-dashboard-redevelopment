#include "dashboard/source_adapters.h"

namespace dashboard {

void VehicleState::invalidateStale(std::uint64_t now_ms, const FreshnessPolicy& policy) {
    speed.invalidateIfStale(now_ms, policy.driving_ms);
    gear.invalidateIfStale(now_ms, policy.driving_ms);
    soc.invalidateIfStale(now_ms, policy.driving_ms);
    range.invalidateIfStale(now_ms, policy.driving_ms);
    odometer.invalidateIfStale(now_ms, policy.driving_ms);
    distance_raw.invalidateIfStale(now_ms, policy.driving_ms);
    trip_distance.invalidateIfStale(now_ms, policy.vehicle_ms);
    trip_time.invalidateIfStale(now_ms, policy.vehicle_ms);
    average_speed.invalidateIfStale(now_ms, policy.vehicle_ms);
    max_speed.invalidateIfStale(now_ms, policy.vehicle_ms);
    start_soc.invalidateIfStale(now_ms, policy.vehicle_ms);
    soc_used.invalidateIfStale(now_ms, policy.vehicle_ms);
    door_fl.invalidateIfStale(now_ms, policy.vehicle_ms);
    door_fr.invalidateIfStale(now_ms, policy.vehicle_ms);
    door_rl.invalidateIfStale(now_ms, policy.vehicle_ms);
    door_rr.invalidateIfStale(now_ms, policy.vehicle_ms);
    frunk.invalidateIfStale(now_ms, policy.vehicle_ms);
    trunk.invalidateIfStale(now_ms, policy.vehicle_ms);
    turn_signal_left.invalidateIfStale(now_ms, policy.lighting_ms);
    turn_signal_right.invalidateIfStale(now_ms, policy.lighting_ms);
    hazards.invalidateIfStale(now_ms, policy.lighting_ms);
    headlights.invalidateIfStale(now_ms, policy.lighting_ms);
    high_beam.invalidateIfStale(now_ms, policy.lighting_ms);
    position_light.invalidateIfStale(now_ms, policy.lighting_ms);
    brake_light.invalidateIfStale(now_ms, policy.lighting_ms);
    auto_light.invalidateIfStale(now_ms, policy.lighting_ms);
    lighting_raw.invalidateIfStale(now_ms, policy.lighting_ms);
    tire_fl.invalidateIfStale(now_ms, policy.tire_ms);
    tire_fr.invalidateIfStale(now_ms, policy.tire_ms);
    tire_rl.invalidateIfStale(now_ms, policy.tire_ms);
    tire_rr.invalidateIfStale(now_ms, policy.tire_ms);
    temperature_primary.invalidateIfStale(now_ms, policy.temperature_ms);
    temperature_secondary.invalidateIfStale(now_ms, policy.temperature_ms);
    ambient_temperature.invalidateIfStale(now_ms, policy.temperature_ms);
    cabin_temperature.invalidateIfStale(now_ms, policy.temperature_ms);
    battery_temperature.invalidateIfStale(now_ms, policy.temperature_ms);
    speed_limit.invalidateIfStale(now_ms, policy.adas_ms);
    overspeed.invalidateIfStale(now_ms, policy.adas_ms);
    autopilot_state.invalidateIfStale(now_ms, policy.adas_ms);
    blind_spot_left.invalidateIfStale(now_ms, policy.adas_ms);
    blind_spot_right.invalidateIfStale(now_ms, policy.adas_ms);
    front_dead_zone.invalidateIfStale(now_ms, policy.adas_ms);
    front_vehicle_present.invalidateIfStale(now_ms, policy.adas_ms);
    left_vehicle_present.invalidateIfStale(now_ms, policy.adas_ms);
    right_vehicle_present.invalidateIfStale(now_ms, policy.adas_ms);
    surrounding_vehicle_left.invalidateIfStale(now_ms, policy.adas_ms);
    surrounding_vehicle_right.invalidateIfStale(now_ms, policy.adas_ms);
    surrounding_position_mode.invalidateIfStale(now_ms, policy.adas_ms);
    road_visualization_raw.invalidateIfStale(now_ms, policy.adas_ms);
    accelerator_position.invalidateIfStale(now_ms, policy.future_ms);
    front_motor_power.invalidateIfStale(now_ms, policy.future_ms);
    rear_motor_power.invalidateIfStale(now_ms, policy.future_ms);
    battery_power.invalidateIfStale(now_ms, policy.future_ms);
    battery_voltage.invalidateIfStale(now_ms, policy.future_ms);
    battery_current.invalidateIfStale(now_ms, policy.future_ms);
    actual_soc.invalidateIfStale(now_ms, policy.future_ms);
    energy_remaining.invalidateIfStale(now_ms, policy.future_ms);
    energy_full_estimate.invalidateIfStale(now_ms, policy.future_ms);
    energy_reserve.invalidateIfStale(now_ms, policy.future_ms);
    total_charged_energy.invalidateIfStale(now_ms, policy.future_ms);
    total_discharged_energy.invalidateIfStale(now_ms, policy.future_ms);
    battery_heating.invalidateIfStale(now_ms, policy.future_ms);
    max_cell_voltage.invalidateIfStale(now_ms, policy.future_ms);
    min_cell_voltage.invalidateIfStale(now_ms, policy.future_ms);
    cell_delta.invalidateIfStale(now_ms, policy.future_ms);
    for (auto& cell : cell_voltages) cell.invalidateIfStale(now_ms, policy.future_ms);
    dcdc_input_voltage.invalidateIfStale(now_ms, policy.future_ms);
    dcdc_output_voltage.invalidateIfStale(now_ms, policy.future_ms);
    dcdc_output_current.invalidateIfStale(now_ms, policy.future_ms);
    dcdc_output_power.invalidateIfStale(now_ms, policy.future_ms);
    brake_temp_fl.invalidateIfStale(now_ms, policy.future_ms);
    brake_temp_fr.invalidateIfStale(now_ms, policy.future_ms);
    brake_temp_rl.invalidateIfStale(now_ms, policy.future_ms);
    brake_temp_rr.invalidateIfStale(now_ms, policy.future_ms);
    hvac_blower_rpm.invalidateIfStale(now_ms, policy.future_ms);
    hvac_power_demand.invalidateIfStale(now_ms, policy.future_ms);
    steering_angle.invalidateIfStale(now_ms, policy.future_ms);
    steering_rate.invalidateIfStale(now_ms, policy.future_ms);
    yaw_rate.invalidateIfStale(now_ms, policy.future_ms);
    wheel_speed_fl.invalidateIfStale(now_ms, policy.future_ms);
    wheel_speed_fr.invalidateIfStale(now_ms, policy.future_ms);
    wheel_speed_rl.invalidateIfStale(now_ms, policy.future_ms);
    wheel_speed_rr.invalidateIfStale(now_ms, policy.future_ms);
    motor_rpm_front.invalidateIfStale(now_ms, policy.future_ms);
    motor_rpm_rear.invalidateIfStale(now_ms, policy.future_ms);
    front_motor_temperature.invalidateIfStale(now_ms, policy.future_ms);
    rear_motor_temperature.invalidateIfStale(now_ms, policy.future_ms);
    brake_position.invalidateIfStale(now_ms, policy.future_ms);
}

SimulationAdapter::SimulationAdapter() { health_.status = DataSourceStatus::Offline; }

void SimulationAdapter::tick(std::uint64_t now_ms) {
    state_.invalidateStale(now_ms);
    if (health_.status == DataSourceStatus::Connected &&
        now_ms > health_.last_update_ms + FreshnessPolicy{}.driving_ms) health_.status = DataSourceStatus::Offline;
}

static void simAlive(DataSourceHealth& health, std::uint64_t timestamp_ms) {
    health.status = DataSourceStatus::Connected;
    health.last_update_ms = timestamp_ms;
    ++health.packets;
}

void SimulationAdapter::setDriving(std::uint16_t speed_value, Gear gear_value,
                                   std::uint8_t soc_value, std::uint16_t range_value,
                                   std::uint64_t timestamp_ms) {
    state_.speed.update(speed_value, timestamp_ms, source(), SignalQuality::Confirmed, Unit::KilometerPerHour);
    state_.gear.update(gear_value, timestamp_ms, source(), SignalQuality::Confirmed, Unit::None);
    state_.soc.update(soc_value, timestamp_ms, source(), SignalQuality::Confirmed, Unit::Percent);
    state_.range.update(range_value, timestamp_ms, source(), SignalQuality::Confirmed, Unit::Kilometer);
    simAlive(health_, timestamp_ms);
}

void SimulationAdapter::setDoors(bool fl, bool fr, bool rl, bool rr, bool frunk_value,
                                 bool trunk_value, std::uint64_t timestamp_ms) {
    state_.door_fl.update(fl, timestamp_ms, source(), SignalQuality::Confirmed, Unit::None);
    state_.door_fr.update(fr, timestamp_ms, source(), SignalQuality::Confirmed, Unit::None);
    state_.door_rl.update(rl, timestamp_ms, source(), SignalQuality::Confirmed, Unit::None);
    state_.door_rr.update(rr, timestamp_ms, source(), SignalQuality::Confirmed, Unit::None);
    state_.frunk.update(frunk_value, timestamp_ms, source(), SignalQuality::Confirmed, Unit::None);
    state_.trunk.update(trunk_value, timestamp_ms, source(), SignalQuality::Confirmed, Unit::None);
    simAlive(health_, timestamp_ms);
}

void SimulationAdapter::setTires(float fl, float fr, float rl, float rr, std::uint64_t timestamp_ms) {
    state_.tire_fl.update(fl, timestamp_ms, source(), SignalQuality::Confirmed, Unit::Bar);
    state_.tire_fr.update(fr, timestamp_ms, source(), SignalQuality::Confirmed, Unit::Bar);
    state_.tire_rl.update(rl, timestamp_ms, source(), SignalQuality::Confirmed, Unit::Bar);
    state_.tire_rr.update(rr, timestamp_ms, source(), SignalQuality::Confirmed, Unit::Bar);
    simAlive(health_, timestamp_ms);
}

void SimulationAdapter::setLighting(bool headlights_value, bool high_beam_value, bool brake,
                                    bool left, bool right, bool hazards_value,
                                    std::uint64_t timestamp_ms) {
    state_.headlights.update(headlights_value, timestamp_ms, source(), SignalQuality::Confirmed, Unit::None);
    state_.high_beam.update(high_beam_value, timestamp_ms, source(), SignalQuality::Confirmed, Unit::None);
    state_.brake_light.update(brake, timestamp_ms, source(), SignalQuality::Confirmed, Unit::None);
    state_.turn_signal_left.update(left, timestamp_ms, source(), SignalQuality::Confirmed, Unit::None);
    state_.turn_signal_right.update(right, timestamp_ms, source(), SignalQuality::Confirmed, Unit::None);
    state_.hazards.update(hazards_value, timestamp_ms, source(), SignalQuality::Confirmed, Unit::None);
    simAlive(health_, timestamp_ms);
}

void SimulationAdapter::setDriverAssistance(AutopilotState ap, bool blind_left, bool blind_right,
                                            bool front_vehicle, bool left_vehicle, bool right_vehicle,
                                            std::uint64_t timestamp_ms) {
    state_.autopilot_state.update(ap, timestamp_ms, source(), SignalQuality::Confirmed, Unit::None);
    state_.blind_spot_left.update(blind_left, timestamp_ms, source(), SignalQuality::Confirmed, Unit::None);
    state_.blind_spot_right.update(blind_right, timestamp_ms, source(), SignalQuality::Confirmed, Unit::None);
    state_.front_vehicle_present.update(front_vehicle, timestamp_ms, source(), SignalQuality::Inferred, Unit::None);
    state_.left_vehicle_present.update(left_vehicle, timestamp_ms, source(), SignalQuality::Inferred, Unit::None);
    state_.right_vehicle_present.update(right_vehicle, timestamp_ms, source(), SignalQuality::Inferred, Unit::None);
    state_.surrounding_position_mode.update(SurroundingPositionMode::Coarse, timestamp_ms, source(), SignalQuality::Confirmed, Unit::None);
    simAlive(health_, timestamp_ms);
}

void SimulationAdapter::setEnhancedPower(float pack_kw, float front_kw, float rear_kw,
                                         float accelerator_percent, std::uint64_t timestamp_ms) {
    state_.battery_power.update(pack_kw, timestamp_ms, source(), SignalQuality::Confirmed, Unit::Kilowatt);
    state_.front_motor_power.update(front_kw, timestamp_ms, source(), SignalQuality::Confirmed, Unit::Kilowatt);
    state_.rear_motor_power.update(rear_kw, timestamp_ms, source(), SignalQuality::Confirmed, Unit::Kilowatt);
    state_.accelerator_position.update(accelerator_percent, timestamp_ms, source(), SignalQuality::Confirmed, Unit::Percent);
    simAlive(health_, timestamp_ms);
}

void SimulationAdapter::disconnect(std::uint64_t timestamp_ms) {
    health_.status = DataSourceStatus::Offline;
    health_.last_update_ms = timestamp_ms;
}

}  // namespace dashboard
