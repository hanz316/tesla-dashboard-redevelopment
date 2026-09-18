#include "display_format.h"

#include <cstdio>

namespace dashboard {
namespace flythings {
namespace {

constexpr const char* kUnavailable = "--";

template <typename T>
bool shown(const Signal<T>& signal) {
    // A stale signal is NOT the last value: the link stopped delivering, so the
    // number on screen would be a guess.
    return signal.valid && !signal.stale;
}

}  // namespace

std::string formatSpeed(const Signal<std::uint16_t>& speed) {
    if (!shown(speed)) {
        return kUnavailable;
    }
    char text[32];
    std::snprintf(text, sizeof(text), "%u", static_cast<unsigned>(speed.value));
    return text;
}

std::string formatRange(const Signal<std::uint16_t>& range) {
    if (!shown(range)) {
        return kUnavailable;
    }
    char text[32];
    std::snprintf(text, sizeof(text), "%u km",
                  static_cast<unsigned>(range.value));
    return text;
}

std::string formatSoc(const Signal<std::uint8_t>& soc) {
    (void)soc;
    // Always unavailable: the mapping is REJECTED_MAPPING until a real source
    // of SOC is identified. Printing the raw byte would be printing a number
    // that has been measured wrong on this car.
    return kUnavailable;
}

std::string formatTirePair(const Signal<float>& left, const Signal<float>& right,
                           const char* label) {
    char text[64];
    if (shown(left) && shown(right)) {
        std::snprintf(text, sizeof(text), "%s %.2f %.2f bar", label,
                      static_cast<double>(left.value),
                      static_cast<double>(right.value));
        return text;
    }
    if (shown(left)) {
        std::snprintf(text, sizeof(text), "%s %.2f -- bar", label,
                      static_cast<double>(left.value));
        return text;
    }
    if (shown(right)) {
        std::snprintf(text, sizeof(text), "%s -- %.2f bar", label,
                      static_cast<double>(right.value));
        return text;
    }
    std::snprintf(text, sizeof(text), "%s %s %s bar", label, kUnavailable,
                  kUnavailable);
    return text;
}

const char* gearPicturePath(Gear gear) {
    switch (gear) {
        case Gear::Park:
            return "/home/white_gears_p.png";
        case Gear::Reverse:
            return "/home/white_gears_r.png";
        case Gear::Neutral:
            return "/home/white_gears_n.png";
        case Gear::Drive:
            return "/home/white_gears_d.png";
        case Gear::Unknown:
        default:
            return nullptr;
    }
}

bool gearIsDisplayable(const Signal<Gear>& gear) {
    if (!shown(gear)) {
        return false;
    }
    // The gear mapping itself is still LIKELY at best (CMD 0x02 byte 3,
    // observed once per gear), so a gear is only drawn when the value is one
    // the decoder actually produced. Unknown stays unknown.
    return gearPicturePath(gear.value) != nullptr;
}

}  // namespace flythings
}  // namespace dashboard
