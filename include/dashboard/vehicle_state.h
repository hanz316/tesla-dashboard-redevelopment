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

struct VehicleState {
    Signal<std::uint16_t> speed;
    Signal<Gear> gear;
    Signal<std::uint8_t> soc;
    Signal<std::uint16_t> range;

    // The original application reads a 24-bit value here, but its physical
    // scale still needs a real-car recording.  Keep it truthful as raw data.
    Signal<std::uint32_t> distance_raw;

    Signal<bool> door_fl;
    Signal<bool> door_fr;
    Signal<bool> door_rl;
    Signal<bool> door_rr;
    Signal<bool> frunk;
    Signal<bool> trunk;

    Signal<float> tire_fl;
    Signal<float> tire_fr;
    Signal<float> tire_rl;
    Signal<float> tire_rr;

    Signal<std::int16_t> temperature_primary;
    Signal<std::int16_t> temperature_secondary;

    // ---------- Commander / deep-Tesla signals (reserved, Build 0.2+) ----------
    // Populated by CommanderAdapter once the Commander SDK lands; the UI
    // reads these through the same Signal contract and never needs to know
    // the transport.

    // Driving / power
    Signal<float> accelerator_position;
    Signal<float> front_motor_power;    // kW
    Signal<float> rear_motor_power;     // kW
    Signal<float> total_motor_power;    // kW

    // Battery / BMS
    Signal<float> pack_voltage;         // V
    Signal<float> pack_current;         // A
    Signal<float> pack_power;           // kW
    Signal<float> energy_remaining;     // kWh
    Signal<float> energy_full_estimate; // kWh
    Signal<std::uint8_t> actual_soc;    // real SOC from Tesla (vs MCU's)
    Signal<float> battery_temperature;  // °C
    Signal<float> max_cell_voltage;     // V
    Signal<float> min_cell_voltage;     // V
    Signal<float> cell_delta;           // V

    // DC/DC
    Signal<float> dcdc_input_voltage;
    Signal<float> dcdc_output_voltage;
    Signal<float> dcdc_output_current;
    Signal<float> dcdc_output_power;

    // Brakes
    Signal<float> brake_temp_fl;
    Signal<float> brake_temp_fr;
    Signal<float> brake_temp_rl;
    Signal<float> brake_temp_rr;

    // Climate
    Signal<float> ambient_temperature;  // °C
    Signal<float> cabin_temperature;    // °C
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
