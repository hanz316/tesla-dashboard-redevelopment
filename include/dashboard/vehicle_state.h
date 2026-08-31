#pragma once

#include "dashboard/signal.h"

#include <cstdint>

namespace dashboard {

enum class Gear : std::uint8_t {
    Unknown = 0,
    Park,
    Reverse,
    Neutral,
    Drive,
};

enum class AutopilotState : std::uint8_t {
    Unknown = 0,
    Off,
    Available,
    Active,
    Warning,
};

struct FreshnessPolicy {
    std::uint64_t driving_ms{1000};
    std::uint64_t vehicle_ms{2000};
    std::uint64_t lighting_ms{3000};
    std::uint64_t tire_ms{30000};
    std::uint64_t temperature_ms{30000};
    std::uint64_t adas_ms{2000};
    std::uint64_t future_ms{1000};
};

struct VehicleState {
    Signal<std::uint16_t> speed;
    Signal<Gear> gear;
    Signal<std::uint8_t> soc;
    Signal<std::uint16_t> range;
    Signal<std::uint32_t> odometer;

    // The original application reads a 24-bit value here, but its physical
    // scale still needs a real-car recording.  Keep it truthful as raw data.
    Signal<std::uint32_t> distance_raw;
    Signal<float> trip_distance;
    Signal<std::uint64_t> trip_time;
    Signal<float> average_speed;
    Signal<std::uint16_t> max_speed;
    Signal<std::uint8_t> start_soc;
    Signal<std::int16_t> soc_used;

    Signal<bool> door_fl;
    Signal<bool> door_fr;
    Signal<bool> door_rl;
    Signal<bool> door_rr;
    Signal<bool> frunk;
    Signal<bool> trunk;

    Signal<bool> headlights;
    Signal<bool> auto_light;
    Signal<std::uint32_t> lighting_raw;

    Signal<float> tire_fl;
    Signal<float> tire_fr;
    Signal<float> tire_rl;
    Signal<float> tire_rr;

    Signal<std::int16_t> temperature_primary;
    Signal<std::int16_t> temperature_secondary;

    Signal<std::uint16_t> speed_limit;
    Signal<bool> overspeed;
    Signal<AutopilotState> autopilot_state;
    Signal<bool> blind_spot_left;
    Signal<bool> blind_spot_right;
    Signal<bool> front_dead_zone;
    Signal<bool> surrounding_vehicle_left;
    Signal<bool> surrounding_vehicle_right;
    Signal<std::uint32_t> road_visualization_raw;

    Signal<float> battery_power;
    Signal<float> battery_voltage;
    Signal<float> battery_current;
    Signal<float> front_motor_power;
    Signal<float> rear_motor_power;
    Signal<float> battery_temperature;
    Signal<float> front_motor_temperature;
    Signal<float> rear_motor_temperature;
    Signal<float> steering_angle;
    Signal<float> steering_rate;
    Signal<float> accelerator_position;
    Signal<float> brake_position;
    Signal<float> yaw_rate;
    Signal<float> wheel_speed_fl;
    Signal<float> wheel_speed_fr;
    Signal<float> wheel_speed_rl;
    Signal<float> wheel_speed_rr;

    void invalidateStale(
        std::uint64_t now_ms,
        const FreshnessPolicy& policy = FreshnessPolicy{});
};

inline const char* gearName(Gear gear) {
    switch (gear) {
        case Gear::Park:
            return "P";
        case Gear::Reverse:
            return "R";
        case Gear::Neutral:
            return "N";
        case Gear::Drive:
            return "D";
        case Gear::Unknown:
        default:
            return "?";
    }
}

}  // namespace dashboard
