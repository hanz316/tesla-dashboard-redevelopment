#include "dashboard/source_adapters.h"

namespace dashboard {

void VehicleState::invalidateStale(
    std::uint64_t now_ms,
    const FreshnessPolicy& policy) {
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

    headlights.invalidateIfStale(now_ms, policy.lighting_ms);
    auto_light.invalidateIfStale(now_ms, policy.lighting_ms);
    lighting_raw.invalidateIfStale(now_ms, policy.lighting_ms);

    tire_fl.invalidateIfStale(now_ms, policy.tire_ms);
    tire_fr.invalidateIfStale(now_ms, policy.tire_ms);
    tire_rl.invalidateIfStale(now_ms, policy.tire_ms);
    tire_rr.invalidateIfStale(now_ms, policy.tire_ms);
    temperature_primary.invalidateIfStale(now_ms, policy.temperature_ms);
    temperature_secondary.invalidateIfStale(now_ms, policy.temperature_ms);

    speed_limit.invalidateIfStale(now_ms, policy.adas_ms);
    overspeed.invalidateIfStale(now_ms, policy.adas_ms);
    autopilot_state.invalidateIfStale(now_ms, policy.adas_ms);
    blind_spot_left.invalidateIfStale(now_ms, policy.adas_ms);
    blind_spot_right.invalidateIfStale(now_ms, policy.adas_ms);
    front_dead_zone.invalidateIfStale(now_ms, policy.adas_ms);
    surrounding_vehicle_left.invalidateIfStale(now_ms, policy.adas_ms);
    surrounding_vehicle_right.invalidateIfStale(now_ms, policy.adas_ms);
    road_visualization_raw.invalidateIfStale(now_ms, policy.adas_ms);

    battery_power.invalidateIfStale(now_ms, policy.future_ms);
    battery_voltage.invalidateIfStale(now_ms, policy.future_ms);
    battery_current.invalidateIfStale(now_ms, policy.future_ms);
    front_motor_power.invalidateIfStale(now_ms, policy.future_ms);
    rear_motor_power.invalidateIfStale(now_ms, policy.future_ms);
    battery_temperature.invalidateIfStale(now_ms, policy.future_ms);
    front_motor_temperature.invalidateIfStale(now_ms, policy.future_ms);
    rear_motor_temperature.invalidateIfStale(now_ms, policy.future_ms);
    steering_angle.invalidateIfStale(now_ms, policy.future_ms);
    steering_rate.invalidateIfStale(now_ms, policy.future_ms);
    accelerator_position.invalidateIfStale(now_ms, policy.future_ms);
    brake_position.invalidateIfStale(now_ms, policy.future_ms);
    yaw_rate.invalidateIfStale(now_ms, policy.future_ms);
    wheel_speed_fl.invalidateIfStale(now_ms, policy.future_ms);
    wheel_speed_fr.invalidateIfStale(now_ms, policy.future_ms);
    wheel_speed_rl.invalidateIfStale(now_ms, policy.future_ms);
    wheel_speed_rr.invalidateIfStale(now_ms, policy.future_ms);
}

SimulationAdapter::SimulationAdapter() {
    health_.status = DataSourceStatus::Offline;
}

void SimulationAdapter::tick(std::uint64_t now_ms) {
    state_.invalidateStale(now_ms);
    if (health_.status == DataSourceStatus::Connected &&
        now_ms > health_.last_update_ms + FreshnessPolicy{}.driving_ms) {
        health_.status = DataSourceStatus::Offline;
    }
}

void SimulationAdapter::setDriving(
    std::uint16_t speed_value,
    Gear gear_value,
    std::uint8_t soc_value,
    std::uint16_t range_value,
    std::uint64_t timestamp_ms) {
    state_.speed.update(speed_value, timestamp_ms, source(), SignalQuality::Confirmed, Unit::KilometerPerHour);
    state_.gear.update(gear_value, timestamp_ms, source(), SignalQuality::Confirmed, Unit::None);
    state_.soc.update(soc_value, timestamp_ms, source(), SignalQuality::Confirmed, Unit::Percent);
    state_.range.update(range_value, timestamp_ms, source(), SignalQuality::Confirmed, Unit::Kilometer);
    health_.status = DataSourceStatus::Connected;
    health_.last_update_ms = timestamp_ms;
    ++health_.packets;
}

void SimulationAdapter::setDoors(
    bool fl,
    bool fr,
    bool rl,
    bool rr,
    bool frunk_value,
    bool trunk_value,
    std::uint64_t timestamp_ms) {
    state_.door_fl.update(fl, timestamp_ms, source(), SignalQuality::Confirmed, Unit::None);
    state_.door_fr.update(fr, timestamp_ms, source(), SignalQuality::Confirmed, Unit::None);
    state_.door_rl.update(rl, timestamp_ms, source(), SignalQuality::Confirmed, Unit::None);
    state_.door_rr.update(rr, timestamp_ms, source(), SignalQuality::Confirmed, Unit::None);
    state_.frunk.update(frunk_value, timestamp_ms, source(), SignalQuality::Confirmed, Unit::None);
    state_.trunk.update(trunk_value, timestamp_ms, source(), SignalQuality::Confirmed, Unit::None);
    health_.status = DataSourceStatus::Connected;
    health_.last_update_ms = timestamp_ms;
    ++health_.packets;
}

void SimulationAdapter::setTires(
    float fl,
    float fr,
    float rl,
    float rr,
    std::uint64_t timestamp_ms) {
    state_.tire_fl.update(fl, timestamp_ms, source(), SignalQuality::Confirmed, Unit::Bar);
    state_.tire_fr.update(fr, timestamp_ms, source(), SignalQuality::Confirmed, Unit::Bar);
    state_.tire_rl.update(rl, timestamp_ms, source(), SignalQuality::Confirmed, Unit::Bar);
    state_.tire_rr.update(rr, timestamp_ms, source(), SignalQuality::Confirmed, Unit::Bar);
    health_.status = DataSourceStatus::Connected;
    health_.last_update_ms = timestamp_ms;
    ++health_.packets;
}

void SimulationAdapter::disconnect(std::uint64_t timestamp_ms) {
    health_.status = DataSourceStatus::Offline;
    health_.last_update_ms = timestamp_ms;
}

}  // namespace dashboard
