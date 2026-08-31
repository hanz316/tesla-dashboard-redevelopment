#pragma once

#include <cstdint>

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
    Raw,
};

template <typename T>
struct Signal {
    T value{};
    bool valid{false};
    std::uint64_t timestamp_ms{0};
    SignalSource source{SignalSource::Unavailable};
    SignalQuality quality{SignalQuality::Unknown};
    Unit unit{Unit::None};

    void update(
        const T& next_value,
        std::uint64_t next_timestamp_ms,
        SignalSource next_source,
        SignalQuality next_quality,
        Unit next_unit) {
        value = next_value;
        valid = true;
        timestamp_ms = next_timestamp_ms;
        source = next_source;
        quality = next_quality;
        unit = next_unit;
    }

    void invalidate(std::uint64_t next_timestamp_ms) {
        valid = false;
        timestamp_ms = next_timestamp_ms;
        source = SignalSource::Unavailable;
        quality = SignalQuality::Unknown;
    }
};

}  // namespace dashboard
