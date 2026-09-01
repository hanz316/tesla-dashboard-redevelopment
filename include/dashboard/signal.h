#pragma once

#include <cstdint>
#include <limits>

namespace dashboard {

enum class SignalSource : std::uint8_t {
    Unavailable = 0,
    OriginalMcu,
    Replay,
    Simulation,
    Commander,
    PhoneBridge,
};

enum class SignalQuality : std::uint8_t {
    Unknown = 0,
    Confirmed,
    Inferred,
    Estimated,
};

enum class Unit : std::uint8_t {
    None = 0,
    KilometerPerHour,
    Kilometer,
    Percent,
    Bar,
    Celsius,
    Volt,
    Ampere,
    Kilowatt,
    KilowattHour,
    Millivolt,
    Rpm,
    Degree,
    Raw,
};

template <typename T>
struct Signal {
    T value{};
    bool valid{false};
    bool stale{false};
    std::uint64_t timestamp_ms{0};
    SignalSource source{SignalSource::Unavailable};
    SignalQuality quality{SignalQuality::Unknown};
    Unit unit{Unit::None};

    void update(const T& next_value, std::uint64_t next_timestamp_ms,
                SignalSource next_source, SignalQuality next_quality, Unit next_unit) {
        value = next_value;
        valid = true;
        stale = false;
        timestamp_ms = next_timestamp_ms;
        source = next_source;
        quality = next_quality;
        unit = next_unit;
    }

    void invalidate(std::uint64_t next_timestamp_ms) {
        valid = false;
        stale = false;
        timestamp_ms = next_timestamp_ms;
        source = SignalSource::Unavailable;
        quality = SignalQuality::Unknown;
    }

    void markStale(std::uint64_t now_ms) {
        valid = false;
        stale = true;
        if (now_ms > timestamp_ms) {
            // Keep the original sample timestamp/source/quality for diagnostics.
        }
    }

    bool unavailable() const { return !valid && !stale; }

    std::uint64_t ageMs(std::uint64_t now_ms) const {
        if (timestamp_ms == 0) return std::numeric_limits<std::uint64_t>::max();
        return now_ms >= timestamp_ms ? now_ms - timestamp_ms : 0;
    }

    bool isStale(std::uint64_t now_ms, std::uint64_t timeout_ms) const {
        return valid && ageMs(now_ms) > timeout_ms;
    }

    void invalidateIfStale(std::uint64_t now_ms, std::uint64_t timeout_ms) {
        if (isStale(now_ms, timeout_ms)) markStale(now_ms);
    }
};

}  // namespace dashboard
