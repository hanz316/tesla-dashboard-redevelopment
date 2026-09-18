#pragma once

#include "dashboard/vehicle_state.h"

#include <string>

namespace dashboard {
namespace flythings {

// How a signal becomes text on the cluster.
//
// These are pure functions with no EasyUI dependency on purpose: they encode
// the rule that matters most on an instrument cluster - UNKNOWN is not zero -
// and that rule has to be testable on the host, not only on the device.
//
// A signal that is invalid or stale renders as "--". It never renders as 0,
// 0.0 or 0 %, because a driver reading "0 km/h" believes the car is stopped.
std::string formatSpeed(const Signal<std::uint16_t>& speed);
std::string formatRange(const Signal<std::uint16_t>& range);

// The original MCU's SOC byte is a documented REJECTED mapping (it read a stuck
// 97 % while the car was driving). Until a trustworthy source exists this
// always renders as unavailable rather than as a number nobody can trust.
std::string formatSoc(const Signal<std::uint8_t>& soc);

std::string formatTirePair(const Signal<float>& left, const Signal<float>& right,
                           const char* label);

// Gear is only shown when the signal is valid AND the value is one of the
// gears the protocol has actually been observed to carry. An unknown gear
// must not leave the previous picture on screen as if it were current.
const char* gearPicturePath(Gear gear);
bool gearIsDisplayable(const Signal<Gear>& gear);

}  // namespace flythings
}  // namespace dashboard
