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
