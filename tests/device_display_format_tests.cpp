#include "display_format.h"

// Keep the assertions live even in a Release build (NDEBUG).
#undef NDEBUG
#include <cassert>
#include <iostream>

using namespace dashboard;
using namespace dashboard::flythings;

namespace {

Signal<std::uint16_t> speed(bool valid, bool stale, std::uint16_t value) {
    Signal<std::uint16_t> signal;
    signal.value = value;
    signal.valid = valid;
    signal.stale = stale;
    return signal;
}

}  // namespace

int main() {
    // UNKNOWN is not zero. A cluster that prints "0" for a missing speed tells
    // the driver the car is stationary.
    assert(formatSpeed(speed(false, false, 0)) == "--");
    assert(formatSpeed(speed(false, true, 88)) == "--");
    assert(formatSpeed(speed(true, true, 88)) == "--");   // stale is not a value
    assert(formatSpeed(speed(true, false, 88)) == "88");
    std::cout << "speed: unknown and stale render as --, never 0\n";

    Signal<std::uint16_t> range;
    range.value = 253;
    range.valid = true;
    range.stale = false;
    assert(formatRange(range) == "253 km");
    range.valid = false;
    assert(formatRange(range) == "--");
    std::cout << "range: unknown renders as --\n";

    // SOC's mapping is REJECTED: the raw byte must never reach the screen, not
    // even a plausible-looking 97.
    Signal<std::uint8_t> soc;
    soc.value = 63;
    soc.valid = true;
    soc.stale = false;
    assert(formatSoc(soc) == "--");
    soc.value = 97;
    assert(formatSoc(soc) == "--");
    std::cout << "soc: rejected mapping always renders as --\n";

    Signal<float> fl, fr;
    fl.value = 2.825F;
    fl.valid = true;
    fl.stale = false;
    fr.value = 2.85F;
    fr.valid = true;
    fr.stale = false;
    // Rounding of a float32 pressure is not the contract; showing both wheels
    // and never fabricating a missing one is.
    const std::string both = formatTirePair(fl, fr, "F");
    assert(both.rfind("F ", 0) == 0);
    assert(both.find(" bar") != std::string::npos);
    assert(both.find("--") == std::string::npos);
    fr.valid = false;
    const std::string one = formatTirePair(fl, fr, "F");
    assert(one.find("--") != std::string::npos);
    assert(one.rfind("F ", 0) == 0);
    fl.valid = false;
    assert(formatTirePair(fl, fr, "F") == "F -- -- bar");
    std::cout << "tires: one unknown wheel does not hide the other\n";

    // Gear display follows the signal, and an unknown gear is not drawn.
    Signal<Gear> gear;
    gear.value = Gear::Drive;
    gear.valid = true;
    gear.stale = false;
    assert(gearIsDisplayable(gear));
    assert(std::string(gearPicturePath(gear.value)) ==
           "/home/white_gears_d.png");
    gear.value = Gear::Unknown;
    assert(!gearIsDisplayable(gear));
    assert(gearPicturePath(Gear::Unknown) == nullptr);
    gear.value = Gear::Drive;
    gear.stale = true;
    assert(!gearIsDisplayable(gear));
    std::cout << "gear: only a known, fresh gear is drawn\n";

    std::cout << "all device display format checks passed\n";
    return 0;
}
