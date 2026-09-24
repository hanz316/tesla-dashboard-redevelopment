#pragma once

#include "dashboard/commander_module.h"
#include "dashboard/vehicle_state.h"

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace dashboard {

// Enhanced telemetry from the aftermarket control module.
//
// Source of the wire format below: the module's own control software, which
// the owner supplied as an unpacked mini program. The frame header, the length
// encoding, the checksum rule, the command numbers and the bit layouts in the
// decoders were read out of that code, and the offsets are quoted beside them.
// That makes this a decoded protocol rather than a guess - but it is decoded
// from the client, not confirmed against a live module, so anything the code
// does not state stays out of the decoders.
//
// The instrument only ever ASKS this module for data. The same command set
// carries the vehicle's controls (unlocking, seat memory, cutting a motor,
// restarting the module). Those are listed so they can be refused by name:
// see commanderCommandIsQueryV6().

// Link state of the enhanced telemetry source.
//
// The original MCU already carries speed, gear, range, doors, lamps and tire
// pressures, and those stay on the MCU path. The module is the source for pack
// SOC, pack power, energy counters, cell voltages and the accelerator pedal,
// so its link state is a first-class thing the screens show rather than
// something that silently produces zeros.
enum class CommanderLinkStatus : std::uint8_t {
    Disabled = 0,   // the module is switched off in settings
    Searching,      // enabled, transport not connected yet
    Linked,         // transport connected and frames are arriving
    NoFrames,       // transport connected but nothing decodable yet
    Stale,          // was linked, frames stopped
};

const char* commanderLinkName(CommanderLinkStatus status);

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

    // "NativeBle v1.2.0" - what the detail line under the badge shows.
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

// ------------------------------------------------------------------ framing

struct CommanderFrameV6 {
    // 55 7F CMD LEN_HI LEN_LO DATA... CHK
    static constexpr std::uint8_t kHeader0 = 0x55;
    static constexpr std::uint8_t kHeader1 = 0x7F;
    static constexpr std::size_t kHeaderBytes = 2;
    static constexpr std::size_t kLengthBytes = 2;
    static constexpr std::size_t kChecksumBytes = 1;
    static constexpr std::size_t kOverhead =
        kHeaderBytes + 1 + kLengthBytes + kChecksumBytes;
    // The module's own receiver refuses anything longer than this.
    static constexpr std::uint16_t kMaxPayload = 4096;
    // The module's receiver abandons a partial frame after this gap, which is
    // why a reader has to do the same instead of waiting forever.
    static constexpr std::uint64_t kInterFrameGapMs = 500;

    // Sum of the command, the two length bytes and the payload, low 8 bits.
    static std::uint8_t checksum(std::uint8_t command, std::uint16_t length,
                                 const std::uint8_t* payload);
    static std::uint8_t checksum(std::uint8_t command,
                                 const std::vector<std::uint8_t>& payload);

    // Builds a complete frame. Used by the phone bridge and by tests; the
    // instrument itself only reads.
    static std::vector<std::uint8_t> encode(
        std::uint8_t command, const std::vector<std::uint8_t>& payload = {});
};

enum class CommanderCommandV6 : std::uint8_t {
    ReadDeviceInfo = 160,   // 0xA0 status refresh
    ApAssist = 161,
    ButtonReport = 162,
    SaveParameters = 163,
    FactoryReset = 164,
    Restart = 165,
    ApRestoreState = 166,
    Control = 167,          // the control word: locks, seats, motors, ESP
    PasswordCheck = 168,
    PasswordChange = 169,
    WriteButtonAndParameters = 171,
    WarehouseReset = 173,
    Deactivate = 174,
    Activate = 175,
    Gauge = 176,            // 0xB0 dashboard stream: start [1], stop [0]
    AmbientLight = 185,
    ButtonPanel = 186,
    GenericButton = 187,
    Passthrough = 192,
    ReadValue = 193,
    Battery = 208,          // pack summary
    BatteryCells = 209,     // six cell voltages per message
    Dcdc = 210,
    BleHost = 240,
};

// A query asks the module to report something. A control asks the car to do
// something. The instrument is a display: it may only send queries.
bool commanderCommandIsQueryV6(std::uint8_t command);
bool commanderCommandIsControlV6(std::uint8_t command);

// A frame reader for the byte stream coming back from the module. It mirrors
// the module's own receiver, including the partial-frame timeout, because the
// module's replies are longer than one BLE packet and arrive in pieces.
class CommanderFrameReaderV6 {
public:
    struct Frame {
        std::uint8_t command{0};
        std::vector<std::uint8_t> payload;
    };

    // Feeds one byte. Returns true when that byte completed a valid frame.
    bool feed(std::uint8_t byte, std::uint64_t now_ms, Frame& frame);
    void reset();

    std::uint64_t frames() const { return frames_; }
    std::uint64_t checksum_errors() const { return checksum_errors_; }
    std::uint64_t dropped_partials() const { return dropped_partials_; }
    std::uint64_t malformed() const { return malformed_; }
    std::uint64_t bytes() const { return bytes_; }

private:
    enum class State : std::uint8_t {
        Idle = 0, Header1, Command, LengthHigh, LengthLow, Payload, Checksum,
    };
    State state_{State::Idle};
    std::uint8_t command_{0};
    std::uint16_t length_{0};
    std::uint16_t index_{0};
    std::uint8_t running_{0};
    std::vector<std::uint8_t> payload_;
    std::uint64_t last_byte_ms_{0};
    std::uint64_t frames_{0};
    std::uint64_t checksum_errors_{0};
    std::uint64_t dropped_partials_{0};
    std::uint64_t malformed_{0};
    std::uint64_t bytes_{0};
};

// ---------------------------------------------------------------- decoding

// Command 160, the module's own status: hardware revision, wiring, runtime,
// CAN channels. Module state, not car telemetry.
struct CommanderDeviceInfoV6 {
    bool valid{false};
    std::uint8_t hardware_version{0};    // payload[0]
    std::uint8_t bootloader_version{0};  // payload[1]
    std::uint8_t firmware_version{0};    // payload[2]
    std::uint8_t flags{0};               // payload[3]
    std::uint8_t ap_restore_state{0};    // payload[18]
    std::uint8_t state_bits{0};          // payload[19]
    float runtime_s{0.0F};               // payload[20..21], little-endian, /1000
    std::uint8_t data0{0};               // payload[22]
    std::uint8_t data1{0};               // payload[23]
    bool has_battery_voltage{false};
    float battery_voltage_v{0.0F};       // payload[20..21], little-endian, /1000
    std::uint8_t charge_state{0};        // payload[19]
    bool has_ambient_light{false};
    std::uint8_t light_brightness{0};    // payload[18], capped at 100
    std::uint8_t light_rgb[3]{0, 0, 0};  // payload[20..22]
    std::uint64_t timestamp_ms{0};

    bool wiring_fault() const { return (state_bits >> 7 & 1) != 0; }
    bool running() const { return (state_bits & 1) != 0; }
    std::uint8_t vehicle_type() const {
        return static_cast<std::uint8_t>(data0 >> 0 & 31);
    }
    bool vehicle_type_identified() const { return (data0 >> 7 & 1) != 0; }
    bool can_channel(std::uint8_t index) const {
        return index < 3 && ((data1 >> index) & 1) != 0;
    }
};

// Command 176, the dashboard stream: the module's decoding of the car's buses.
// Field offsets are quoted from the module's own parser.
struct CommanderGaugeV6 {
    bool valid{false};
    std::uint16_t speed_kph{0};   // payload[0..3] bits 0-8
    Gear gear{Gear::Unknown};     // bits 9-11: 1=P 2=R 3=N 4=D
    std::uint8_t turn{0};         // bits 12-13
    std::uint8_t autopilot{0};    // bits 14-15
    bool door_fl{false};
    bool door_fr{false};
    bool door_rl{false};
    bool door_rr{false};
    std::uint8_t door_bits{0};    // bits 16-19
    std::uint8_t light_bits{0};   // bits 20-23, 27 and payload[4] bit 1
    bool headlight{false};
    bool high_beam{false};
    bool fog_light{false};
    bool brake_light{false};
    bool indicator_left{false};
    bool indicator_right{false};
    std::uint8_t soc_percent{0};  // bits 24-30: the car's own 7-bit SOC
    bool frunk_open{false};       // payload[4..7] bit 1
    bool trunk_open{false};       // bit 5
    bool screen_on{false};        // bit 0
    bool dark_theme{false};       // bit 2
    bool sport_mode{false};       // bit 3
    // Measured on the car (2026-09-24 capture): this field reads the same
    // value as the pack summary's odometer (211040.4 km in the same second),
    // so it is the ODOMETER, not the "remaining range" the client's label
    // claims. Reading it as a range is how a 211 040 km range reaches a screen.
    float odometer_km{0.0F};      // bits 6-31, /10
    bool tire_valid[4]{false, false, false, false};
    float tire_bar[4]{0.0F, 0.0F, 0.0F, 0.0F};  // payload[8..11] * 0.025
    float accelerator_percent{0.0F};            // payload[12], 0-255 of 250 counts
    float rear_motor_kw{0.0F};                  // payload[12..15] bits 8-18, signed, /2
    float front_motor_kw{0.0F};                 // bits 19-29, signed, /2
    bool has_extended{false};                   // payload length >= 33
    float elevation_m{0.0F};                    // payload[15..17] bits 6-19, signed
    std::uint8_t battery_heating{0};            // payload[17] bits 4-5
    bool imperial_units{false};                 // payload[17] bit 6
    bool hands_on_wheel{false};                 // payload[17] bit 7
    float brake_temp_c[4]{0.0F, 0.0F, 0.0F, 0.0F};  // payload[18..22], 10-bit, -40
    float hvac_blower_rpm{0.0F};                // payload[23..26] bits 0-9, *5
    float hvac_evaporator_w{0.0F};              // bits 10-20, *5
    float cabin_temp_c{0.0F};                   // bits 21-31, *0.1, -40
    float ambient_temp_c{0.0F};                 // payload[27] *0.5, -40
    float cell_voltage_v{0.0F};                 // payload[28..31] bits 0-11, *0.002
    // The real remaining range: matches the pack summary's range exactly
    // (170.7 km from both sources in the same capture).
    float range_km{0.0F};                       // bits 12-21, *1.61
    float battery_temp_c{0.0F};                 // bits 22-30, *0.5, -40
    float speed_limit_kph{0.0F};                // payload[31..32] bits 7-11, *5
    // Candidate fields retained for diagnostics only. 0x38 mapping is not
    // live validated, so these must not be promoted to VehicleState semantics.
    std::uint8_t blind_spot_rear_left{0};       // candidate bits 12-13
    std::uint8_t blind_spot_rear_right{0};      // candidate bits 14-15
    std::uint64_t timestamp_ms{0};
};

bool decodeCommanderDeviceInfoV6(const std::vector<std::uint8_t>& payload,
                                 std::uint64_t now_ms,
                                 CommanderDeviceInfoV6& out);
bool decodeCommanderGaugeV6(const std::vector<std::uint8_t>& payload,
                            std::uint64_t now_ms, CommanderGaugeV6& out);

// Command 208, the pack summary. This is where a trustworthy SOC comes from:
// the module reports remaining and full energy, and the actual SOC is their
// ratio rather than a byte decoded by somebody else.
struct CommanderPackV6 {
    bool valid{false};
    float pack_voltage_v{0.0F};        // payload[0..1], *0.01
    float pack_current_a{0.0F};        // payload[2..3], *-0.1 with the module's wrap fix
    float pack_power_kw{0.0F};
    float total_charged_kwh{0.0F};     // payload[8..11], *0.001
    float total_discharged_kwh{0.0F};  // payload[4..7], *0.001
    float max_cell_v{0.0F};            // payload[18..20] bits 0-11, *0.002
    float min_cell_v{0.0F};            // bits 12-23, *0.002
    float cell_delta_mv{0.0F};
    bool remaining_known{false};
    float remaining_kwh{0.0F};         // payload[12..15] bits 0-15, *0.02
    float full_kwh{0.0F};              // bits 16-31, *0.02
    float reserve_kwh{0.0F};           // payload[16..17], *0.01
    float factory_capacity_kwh{0.0F};  // payload[21..24] bits 0-9, *0.1
    float range_km{0.0F};              // bits 10-19, *1.61 (agrees with 176)
    std::uint8_t car_soc_percent{0};   // payload[24..25] bits 7-13
    bool actual_soc_known{false};
    float actual_soc_percent{0.0F};    // (remaining - reserve) / (full - reserve)
    float battery_temp_c{0.0F};        // bits 22-31 of payload[21..24], *0.5, -40
    bool heating{false};
    float odometer_km{0.0F};           // payload[25..28] bits 6-31, /10
    std::uint64_t timestamp_ms{0};
};

bool decodeCommanderPackV6(const std::vector<std::uint8_t>& payload,
                           std::uint64_t now_ms, CommanderPackV6& out);

// Command 210, the DC/DC converter.
struct CommanderDcdcV6 {
    bool valid{false};
    float input_voltage_v{0.0F};   // payload[0..3] bits 16-31, *0.1
    float output_voltage_v{0.0F};  // bits 0-15, *0.01
    float output_current_a{0.0F};  // payload[4..7] bits 0-15, *0.1
    float output_power_w{0.0F};
    std::uint64_t timestamp_ms{0};
};

bool decodeCommanderDcdcV6(const std::vector<std::uint8_t>& payload,
                           std::uint64_t now_ms, CommanderDcdcV6& out);

// ------------------------------------------------------------ application

// Writes every decoded module reading onto a state of its own.
//
// This state is the module's opinion, kept beside the cluster's own readings
// rather than inside them: which of the two a screen shows is decided by
// buildArbitratedStateV6(), not by whoever wrote last.
void applyCommanderReadingsV6(const CommanderGaugeV6& gauge,
                              const CommanderPackV6& pack,
                              const CommanderDcdcV6& dcdc,
                              VehicleState& out, std::uint64_t now_ms);

// ----------------------------------------------------------------- priority

// Which source wins when both have a value for the same thing.
//
// The owner's rule for this car: **the module wins**. The cluster's own MCU
// reading is the fallback, used whenever the module has nothing to say (no
// value, or its value has gone stale). The module is the richer source - it
// decodes more buses than the original cluster - and it is the only source of
// the pack data, so it is the one that is trusted for what it carries.
//
// The switch exists per signal rather than as one flag so that a future
// disagreement can be argued about one field at a time instead of by
// rewriting the whole policy.
struct CommanderPriorityV6 {
    bool speed{true};
    bool gear{true};
    bool range{true};
    bool closures{true};
    bool lighting{true};
    bool tire_pressure{true};
    bool soc{true};
    bool odometer{true};
    bool temperature{true};
};

// The state a screen should read: the module's value wherever the module has
// one and the policy lets it through, the car's own reading everywhere else.
//
// Note what is deliberately NOT here: the MCU's SOC byte is never a candidate
// for the SOC field, because that mapping is rejected on this car. SOC comes
// from the module or it is unavailable - the byte does not get promoted by
// being the only thing left.
VehicleState buildArbitratedStateV6(const VehicleState& mcu,
                                    const VehicleState& commander,
                                    std::uint64_t now_ms,
                                    const CommanderPriorityV6& priority = {});

// ----------------------------------------------------------------- connect

// When the transport should try to (re)establish the link.
//
// Auto-connect is three rules: try as soon as the module is enabled, back off
// after a failure so a module that is not there does not get hammered, and
// start over as soon as a link actually works. Silence on a link that was
// working is a disconnect, not a state to sit in.
struct CommanderConnectPolicyV6 {
    std::uint64_t min_backoff_ms{1000};
    std::uint64_t max_backoff_ms{30000};
    // After this many failed attempts the interval stays at the maximum rather
    // than growing without bound.
    std::uint32_t attempts_before_cap{5};
};

class CommanderConnectScheduleV6 {
public:
    explicit CommanderConnectScheduleV6(CommanderConnectPolicyV6 policy = {})
        : policy_(policy) {}

    void setEnabled(bool enabled, std::uint64_t now_ms);
    bool enabled() const { return enabled_; }

    // True when the transport should open a connection now.
    bool shouldAttempt(std::uint64_t now_ms) const;
    // The transport reports the outcome.
    void noteAttempt(std::uint64_t now_ms);
    void noteConnected(std::uint64_t now_ms);
    void noteDisconnected(std::uint64_t now_ms);
    // Called when the link was working and stopped delivering frames.
    void noteLinkLost(std::uint64_t now_ms);

    std::uint32_t attempts() const { return attempts_; }
    std::uint64_t next_attempt_ms() const { return next_attempt_ms_; }
    std::uint64_t current_backoff_ms() const { return backoff_ms_; }
    bool connected() const { return connected_; }

private:
    CommanderConnectPolicyV6 policy_;
    bool enabled_{false};
    bool connected_{false};
    std::uint32_t attempts_{0};
    std::uint64_t backoff_ms_{0};
    std::uint64_t next_attempt_ms_{0};
};

// Copies the enhanced fields from one state onto another.
void mergeCommanderInto(VehicleState& target, const VehicleState& commander);

}  // namespace dashboard
