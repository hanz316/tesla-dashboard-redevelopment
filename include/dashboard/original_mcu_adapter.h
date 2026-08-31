#pragma once

#include "dashboard/protocol_parser.h"
#include "dashboard/vehicle_state.h"

#include <array>
#include <cstddef>
#include <cstdint>

namespace dashboard {

struct DoorBitMapping {
    // Reverse-engineered default from the original UI's extraction order.
    // It remains configurable until a real-car open/close recording confirms
    // every physical position.
    std::uint8_t door_fl{0};
    std::uint8_t door_fr{2};
    std::uint8_t door_rl{1};
    std::uint8_t door_rr{3};
    std::uint8_t frunk{5};
    std::uint8_t trunk{4};
};

struct TireByteMapping {
    std::array<std::uint8_t, 4> physical_to_payload{{0, 1, 2, 3}};
};

struct OriginalMcuConfig {
    DoorBitMapping doors;
    TireByteMapping tires;
};

struct AdapterStats {
    std::uint64_t applied_packets{0};
    std::uint64_t short_payloads{0};
    std::uint64_t unknown_commands{0};
};

class OriginalMcuAdapter {
public:
    explicit OriginalMcuAdapter(OriginalMcuConfig config = OriginalMcuConfig{});

    void feed(
        const std::uint8_t* data,
        std::size_t size,
        std::uint64_t timestamp_ms);
    void applyFrame(const ProtocolFrame& frame, std::uint64_t timestamp_ms);

    const VehicleState& state() const { return state_; }
    const ProtocolParserStats& parserStats() const { return parser_.stats(); }
    const AdapterStats& adapterStats() const { return stats_; }

    // Deliberately no send/control API.  Phase 0-2 are strictly read-only.

private:
    void applyCommand01(const ProtocolFrame& frame, std::uint64_t timestamp_ms);
    void applyCommand04(const ProtocolFrame& frame, std::uint64_t timestamp_ms);
    void applyCommand07(const ProtocolFrame& frame, std::uint64_t timestamp_ms);
    void applyCommand12(const ProtocolFrame& frame, std::uint64_t timestamp_ms);

    static std::uint16_t littleEndian16(
        const std::vector<std::uint8_t>& payload,
        std::size_t offset);
    static bool bit(std::uint8_t value, std::uint8_t index);

    OriginalMcuConfig config_;
    ProtocolParser parser_;
    VehicleState state_;
    AdapterStats stats_;
};

}  // namespace dashboard
