#include "dashboard/original_mcu_adapter.h"

#include <utility>

namespace dashboard {
namespace {

void updateBoolean(
    Signal<bool>& signal,
    bool value,
    std::uint64_t timestamp_ms,
    SignalSource source,
    SignalQuality quality) {
    signal.update(value, timestamp_ms, source, quality, Unit::None);
}

}  // namespace

OriginalMcuAdapter::OriginalMcuAdapter(OriginalMcuConfig config)
    : config_(std::move(config)) {
    health_.status = DataSourceStatus::Offline;
}

void OriginalMcuAdapter::feed(
    const std::uint8_t* data,
    std::size_t size,
    std::uint64_t timestamp_ms) {
    const auto frames = parser_.feed(data, size);
    for (const auto& frame : frames) {
        applyFrame(frame, timestamp_ms);
        if (frame_listener_) {
            frame_listener_(frame, timestamp_ms);
        }
        health_.status = DataSourceStatus::Connected;
        health_.last_update_ms = timestamp_ms;
        ++health_.packets;
    }
    health_.errors = parser_.stats().checksum_errors + stats_.short_payloads;
}

void OriginalMcuAdapter::tick(std::uint64_t now_ms) {
    state_.invalidateStale(now_ms);
    if (health_.status == DataSourceStatus::Connected &&
        now_ms > health_.last_update_ms + FreshnessPolicy{}.driving_ms) {
        health_.status = DataSourceStatus::Offline;
    }
}

void OriginalMcuAdapter::reset() {
    parser_.reset();
    state_ = VehicleState{};
    stats_ = AdapterStats{};
    health_ = DataSourceHealth{};
    health_.status = DataSourceStatus::Offline;
}

void OriginalMcuAdapter::applyFrame(
    const ProtocolFrame& frame,
    std::uint64_t timestamp_ms) {
    switch (frame.command) {
        case 0x01:
            applyCommand01(frame, timestamp_ms);
            break;
        case 0x04:
            applyCommand04(frame, timestamp_ms);
            break;
        case 0x07:
            applyCommand07(frame, timestamp_ms);
            break;
        case 0x12:
            applyCommand12(frame, timestamp_ms);
            break;
        default:
            ++stats_.unknown_commands;
            return;
    }
    ++stats_.applied_packets;
}

void OriginalMcuAdapter::applyCommand01(
    const ProtocolFrame& frame,
    std::uint64_t timestamp_ms) {
    if (frame.payload.size() < 5) {
        ++stats_.short_payloads;
        return;
    }

    // GEAR IS DELIBERATELY NOT DECODED HERE.
    //
    // The old mapping (payload[4] >> 4, 0 = Park, 4 = Drive) is marked
    // REJECTED_MAPPING: a controlled live capture on 2026-09-18 held this
    // payload nibble at 3 across P, R, N and D, so it does not carry the gear.
    // The live captures instead show CMD 0x02 byte 3 tracking the gear
    // (P=0x05, N=0x02, D=0x09, R=0xff) - observed once per gear, which is
    // LIKELY and not yet CONFIRMED_LIVE.
    //
    // Until a repeatable controlled capture confirms it, production gear stays
    // UNKNOWN. Filling it with Park would put a fabricated gear on a cluster.
    (void)timestamp_ms;

    const std::uint8_t doors = frame.payload[3];
    updateBoolean(
        state_.door_fl,
        bit(doors, config_.doors.door_fl),
        timestamp_ms,
        source(),
        config_.doors.door_fl == 0 ? SignalQuality::Confirmed : SignalQuality::Inferred);
    updateBoolean(
        state_.door_fr,
        bit(doors, config_.doors.door_fr),
        timestamp_ms,
        source(),
        SignalQuality::Inferred);
    updateBoolean(
        state_.door_rl,
        bit(doors, config_.doors.door_rl),
        timestamp_ms,
        source(),
        SignalQuality::Inferred);
    updateBoolean(
        state_.door_rr,
        bit(doors, config_.doors.door_rr),
        timestamp_ms,
        source(),
        SignalQuality::Inferred);
    updateBoolean(
        state_.frunk,
        bit(doors, config_.doors.frunk),
        timestamp_ms,
        source(),
        SignalQuality::Inferred);
    updateBoolean(
        state_.trunk,
        bit(doors, config_.doors.trunk),
        timestamp_ms,
        source(),
        SignalQuality::Inferred);
}

void OriginalMcuAdapter::applyCommand04(
    const ProtocolFrame& frame,
    std::uint64_t timestamp_ms) {
    if (frame.payload.size() < 13) {
        ++stats_.short_payloads;
        return;
    }

    state_.speed.update(
        littleEndian16(frame.payload, 0),
        timestamp_ms,
        source(),
        SignalQuality::Confirmed,
        Unit::KilometerPerHour);
    state_.range.update(
        littleEndian16(frame.payload, 6),
        timestamp_ms,
        source(),
        SignalQuality::Confirmed,
        Unit::Kilometer);

    // Byte mapping is confirmed, but two real-car recordings showed this value
    // frozen at 97 while Tesla actual SOC was ~63%. Preserve it for diagnostics
    // and fallback experiments, but never mark it as trusted actual SOC.
    state_.soc.update(
        frame.payload[8],
        timestamp_ms,
        source(),
        SignalQuality::Estimated,
        Unit::Percent);

    const std::uint32_t distance =
        static_cast<std::uint32_t>(frame.payload[10]) |
        (static_cast<std::uint32_t>(frame.payload[11]) << 8U) |
        (static_cast<std::uint32_t>(frame.payload[12]) << 16U);
    state_.distance_raw.update(
        distance,
        timestamp_ms,
        source(),
        SignalQuality::Inferred,
        Unit::Raw);
}

void OriginalMcuAdapter::applyCommand07(
    const ProtocolFrame& frame,
    std::uint64_t timestamp_ms) {
    if (frame.payload.size() < 2) {
        ++stats_.short_payloads;
        return;
    }

    state_.temperature_primary.update(
        static_cast<std::int16_t>((frame.payload[0] >> 1U) - 40),
        timestamp_ms,
        source(),
        SignalQuality::Inferred,
        Unit::Celsius);
    state_.temperature_secondary.update(
        static_cast<std::int16_t>(frame.payload[1]) - 25,
        timestamp_ms,
        source(),
        SignalQuality::Inferred,
        Unit::Celsius);
}

void OriginalMcuAdapter::applyCommand12(
    const ProtocolFrame& frame,
    std::uint64_t timestamp_ms) {
    if (frame.payload.size() < 5) {
        ++stats_.short_payloads;
        return;
    }

    std::array<float, 4> pressure{};
    for (std::size_t physical = 0; physical < pressure.size(); ++physical) {
        const std::uint8_t payload_index = config_.tires.physical_to_payload[physical];
        if (payload_index > 3) {
            ++stats_.short_payloads;
            return;
        }
        pressure[physical] =
            static_cast<float>(frame.payload[1 + payload_index]) * 0.025F;
    }

    state_.tire_fl.update(
        pressure[0], timestamp_ms, source(), SignalQuality::Confirmed, Unit::Bar);
    state_.tire_fr.update(
        pressure[1], timestamp_ms, source(), SignalQuality::Confirmed, Unit::Bar);
    state_.tire_rl.update(
        pressure[2], timestamp_ms, source(), SignalQuality::Confirmed, Unit::Bar);
    state_.tire_rr.update(
        pressure[3], timestamp_ms, source(), SignalQuality::Confirmed, Unit::Bar);
}

std::uint16_t OriginalMcuAdapter::littleEndian16(
    const std::vector<std::uint8_t>& payload,
    std::size_t offset) {
    return static_cast<std::uint16_t>(
        static_cast<std::uint16_t>(payload[offset]) |
        (static_cast<std::uint16_t>(payload[offset + 1]) << 8U));
}

bool OriginalMcuAdapter::bit(std::uint8_t value, std::uint8_t index) {
    return index < 8 && (value & static_cast<std::uint8_t>(1U << index)) != 0;
}

}  // namespace dashboard
