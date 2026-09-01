#pragma once

#include "dashboard/signal.h"

#include <cstdint>
#include <vector>

namespace dashboard {

enum class Gear : std::uint8_t { Unknown = 0, Park, Reverse, Neutral, Drive };
enum class AutopilotState : std::uint8_t { Unknown = 0, Off, Available, Active, Warning };

enum class SurroundingPositionMode : std::uint8_t {
    None = 0,
    Coarse,
    Precise,
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

    Signal<bool> turn_signal_left;
    Signal<bool> turn_signal_right;
    Signal<bool> hazards;
    Signal<bool> headlights;
    Signal<bool> high_beam;
    Signal<bool> position_light;
    Signal<bool> brake_light;
    Signal<bool> auto_light;
    Signal<std::uint32_t> lighting_raw;

    Signal<float> tire_fl;
    Signal<float> tire_fr;
    Signal<float> tire_rl;
    Signal<float> tire_rr;

    Signal<std::int16_t> temperature_primary;
    Signal<std::int16_t> temperature_secondary;
    Signal<float> ambient_temperature;
    Signal<float> cabin_temperature;
    Signal<float> battery_temperature;

    Signal<std::uint16_t> speed_limit;
    Signal<bool> overspeed;
    Signal<AutopilotState> autopilot_state;
    Signal<bool> blind_spot_left;
    Signal<bool> blind_spot_right;
    Signal<bool> front_dead_zone;
    Signal<bool> front_vehicle_present;
    Signal<bool> left_vehicle_present;
    Signal<bool> right_vehicle_present;
    Signal<bool> surrounding_vehicle_left;
    Signal<bool> surrounding_vehicle_right;
    Signal<SurroundingPositionMode> surrounding_position_mode;
    Signal<std::uint32_t> road_visualization_raw;

    // Commander / enhanced telemetry. These remain invalid until a real source updates them.
    Signal<float> accelerator_position;
    Signal<float> front_motor_power;
    Signal<float> rear_motor_power;
    Signal<float> battery_power;
    Signal<float> battery_voltage;
    Signal<float> battery_current;
    Signal<std::uint8_t> actual_soc;
    Signal<float> energy_remaining;
    Signal<float> energy_full_estimate;
    Signal<float> energy_reserve;
    Signal<float> total_charged_energy;
    Signal<float> total_discharged_energy;
    Signal<bool> battery_heating;
    Signal<float> max_cell_voltage;
    Signal<float> min_cell_voltage;
    Signal<float> cell_delta;
    std::vector<Signal<float>> cell_voltages;
    Signal<float> dcdc_input_voltage;
    Signal<float> dcdc_output_voltage;
    Signal<float> dcdc_output_current;
    Signal<float> dcdc_output_power;
    Signal<float> brake_temp_fl;
    Signal<float> brake_temp_fr;
    Signal<float> brake_temp_rl;
    Signal<float> brake_temp_rr;
    Signal<float> hvac_blower_rpm;
    Signal<float> hvac_power_demand;

    // Future Raw CAN fields.
    Signal<float> steering_angle;
    Signal<float> steering_rate;
    Signal<float> yaw_rate;
    Signal<float> wheel_speed_fl;
    Signal<float> wheel_speed_fr;
    Signal<float> wheel_speed_rl;
    Signal<float> wheel_speed_rr;
    Signal<float> motor_rpm_front;
    Signal<float> motor_rpm_rear;
    Signal<float> front_motor_temperature;
    Signal<float> rear_motor_temperature;
    Signal<float> brake_position;

    void invalidateStale(std::uint64_t now_ms,
                         const FreshnessPolicy& policy = FreshnessPolicy{});
};

inline const char* gearName(Gear gear) {
    switch (gear) {
        case Gear::Park: return "P";
        case Gear::Reverse: return "R";
        case Gear::Neutral: return "N";
        case Gear::Drive: return "D";
        default: return "?";
    }
}

}  // namespace dashboard
