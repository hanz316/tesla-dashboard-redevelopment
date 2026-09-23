#pragma once

#include "dashboard/commander_module.h"
#include "dashboard/vehicle_state.h"

#include <cstddef>
#include <cstdint>
#include <string>

namespace dashboard {

// Link state of the enhanced telemetry source (Commander).
//
// The original MCU already carries speed, gear, range, doors, lamps and tire
// pressures, and those stay on the MCU path. The Commander is the only source
// for pack SOC, power, energy counters, cell voltages and the accelerator
// pedal, so its link state is a first-class thing the screens show rather than
// something that silently produces zeros.
enum class CommanderLinkStatus : std::uint8_t {
    Disabled = 0,   // the module is switched off in settings
    Searching,      // enabled, transport not connected yet
    Linked,         // transport connected and frames are arriving
    NoFrames,       // transport connected but nothing decodable yet
    Stale,          // was linked, frames stopped
};

const char* commanderLinkName(CommanderLinkStatus status);

// How the module decides a link is alive. Values are deliberately generous:
// the Commander pushes at a low rate, and a short dropout must not flap the
// screen between two states.
struct CommanderLinkPolicy {
    std::uint64_t frame_timeout_ms{3000};
    std::uint64_t reconnect_backoff_ms{1500};
};

class CommanderLink {
public:
    explicit CommanderLink(CommanderLinkPolicy policy = CommanderLinkPolicy{})
        : policy_(policy) {}

    void setEnabled(bool enabled, std::uint64_t now_ms);
    bool enabled() const { return enabled_; }

    // Called when the transport reports its own connection state. A transport
    // that is connected but silent stays NoFrames: "connected" is not "data".
    void setTransport(bool connected, std::uint64_t now_ms);

    void setModuleInfo(const CommanderModuleVersion& version,
                       const CommanderFeatureFlags& features);
    void noteFrame(std::uint64_t now_ms);
    void tick(std::uint64_t now_ms);

    CommanderLinkStatus status() const { return status_; }
    bool linked() const { return status_ == CommanderLinkStatus::Linked; }

    // 1 = linked, 0 = enabled but not delivering. Anything else is invalid, so
    // the screen shows its placeholder rather than a false "connected".
    bool linkValue(int& out) const;

    const CommanderModuleVersion& version() const { return version_; }
    const CommanderFeatureFlags& features() const { return features_; }
    bool module_info_known() const { return module_info_known_; }
    std::uint64_t frames() const { return frames_; }
    std::uint64_t dropped_frames() const { return dropped_frames_; }
    std::uint64_t last_frame_ms() const { return last_frame_ms_; }

    // "NativeBle · v1.2.0" - what the detail line under the badge shows.
    std::string detail(const char* transport_name) const;

private:
    CommanderLinkPolicy policy_;
    bool enabled_{false};
    bool transport_connected_{false};
    bool ever_linked_{false};
    bool module_info_known_{false};
    CommanderLinkStatus status_{CommanderLinkStatus::Disabled};
    CommanderModuleVersion version_;
    CommanderFeatureFlags features_;
    std::uint64_t frames_{0};
    std::uint64_t dropped_frames_{0};
    std::uint64_t last_frame_ms_{0};
    std::uint64_t enabled_since_ms_{0};
};

// ---------------------------------------------------------------- telemetry

// The frame format the dashboard decodes.
//
//   0xB5 | TYPE | LEN | PAYLOAD | CHK
//   CHK = ~(TYPE + LEN + sum(PAYLOAD)) & 0xFF
//
// This mirrors the original MCU framing so one checksum helper serves both
// links, and it is deliberately explicit about scaling: every multi-byte value
// is little-endian, and every scaled value states its unit in the field name.
//
// IMPORTANT: this is the dashboard-side contract, not a captured Commander
// firmware spec. It is the shape the module emits and the shape the screens
// were built against. When a real Commander is on the bench its actual output
// must be captured and this table re-verified; until then the decode path is
// tested against the contract, and no capture of a real Commander exists.
struct CommanderFrameHeader {
    static constexpr std::uint8_t kHeader = 0xB5;
    static constexpr std::size_t kOverhead = 4;  // header, type, len, checksum
};

enum class CommanderMessageType : std::uint8_t {
    Pack = 0x01,       // soc u8 %, voltage u16 0.1 V, current i16 0.1 A, power i16 0.1 kW
    Energy = 0x02,     // charged u32 0.1 kWh, discharged u32 0.1 kWh, remaining u16 0.1 kWh
    Cells = 0x03,      // count u8, then count x u16 millivolts
    Inputs = 0x04,     // accelerator u8 0.5 %, brake u8 0.5 %
    Info = 0x05,       // major u8, minor u8, patch u8, feature flags u8
    Temperatures = 0x06,  // battery i16 0.1 C, ambient i16 0.1 C, cabin i16 0.1 C
};

struct CommanderDecoderStats {
    std::uint64_t frames{0};
    std::uint64_t checksum_errors{0};
    std::uint64_t malformed{0};
    std::uint64_t unknown_types{0};
    std::uint64_t decoded{0};
};

class CommanderTelemetryDecoder {
public:
    // Decodes every complete frame in the buffer. Fields the frame does not
    // carry are left untouched, so a partial frame cannot clear a good value.
    // Only fields the Commander actually owns are written.
    void decode(const std::uint8_t* data, std::size_t length,
                VehicleState& out, std::uint64_t now_ms);

    const CommanderDecoderStats& stats() const { return stats_; }
    CommanderModuleVersion version() const { return version_; }
    CommanderFeatureFlags features() const { return features_; }
    bool module_info_known() const { return module_info_known_; }
    void resetStats() { stats_ = CommanderDecoderStats{}; }

    static std::uint8_t checksum(std::uint8_t type, std::uint8_t length,
                                 const std::uint8_t* payload);

private:
    void decodeMessage(std::uint8_t type, const std::uint8_t* payload,
                       std::uint8_t length, VehicleState& out,
                       std::uint64_t now_ms);

    CommanderDecoderStats stats_;
    CommanderModuleVersion version_;
    CommanderFeatureFlags features_;
    bool module_info_known_{false};
};

// Copies the enhanced fields onto the cluster's state.
//
// The Commander owns only what the original MCU does not carry. Speed, gear,
// range, the SOC byte, doors, lamps, tire pressures and trip data are read
// from the car by the cluster already; this function never overwrites them,
// so an enhanced source can never rewrite a directly read value.
void mergeCommanderInto(VehicleState& target, const VehicleState& commander);

}  // namespace dashboard
