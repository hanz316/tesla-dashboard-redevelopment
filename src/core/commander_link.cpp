#include "dashboard/commander_link.h"

#include <algorithm>
#include <cstdio>

namespace dashboard {
namespace {

std::uint32_t readU16(const std::uint8_t* p) {
    return static_cast<std::uint32_t>(p[0]) |
           (static_cast<std::uint32_t>(p[1]) << 8);
}

std::uint32_t readU24(const std::uint8_t* p) {
    return static_cast<std::uint32_t>(p[0]) |
           (static_cast<std::uint32_t>(p[1]) << 8) |
           (static_cast<std::uint32_t>(p[2]) << 16);
}

std::uint32_t readU32(const std::uint8_t* p) {
    return static_cast<std::uint32_t>(p[0]) |
           (static_cast<std::uint32_t>(p[1]) << 8) |
           (static_cast<std::uint32_t>(p[2]) << 16) |
           (static_cast<std::uint32_t>(p[3]) << 24);
}

// Extracts `count` bits starting at `start`, as the module's client does with
// shifts and masks.
std::uint32_t bits(std::uint32_t value, unsigned start, unsigned count) {
    const std::uint32_t mask = count >= 32 ? 0xFFFFFFFFU : ((1U << count) - 1U);
    return (value >> start) & mask;
}

// The client's signed conversions: an 11 or 14 bit field is sign-extended by
// comparing against half its range.
int signExtend(std::uint32_t value, unsigned width) {
    const std::uint32_t half = 1U << (width - 1);
    return value >= half ? static_cast<int>(value) - static_cast<int>(1U << width)
                         : static_cast<int>(value);
}

Gear gearFromIndex(std::uint32_t index) {
    switch (index) {
        case 1: return Gear::Park;
        case 2: return Gear::Reverse;
        case 3: return Gear::Neutral;
        case 4: return Gear::Drive;
        default: return Gear::Unknown;
    }
}

template <typename T>
void set(Signal<T>& signal, const T& value, std::uint64_t now_ms,
         SignalQuality quality, Unit unit) {
    signal.update(value, now_ms, SignalSource::Commander, quality, unit);
}

template <typename T>
void copyIfValid(Signal<T>& target, const Signal<T>& source) {
    if (source.valid && !source.stale) {
        target = source;
    }
}

}  // namespace

const char* commanderLinkName(CommanderLinkStatus status) {
    switch (status) {
        case CommanderLinkStatus::Disabled: return "DISABLED";
        case CommanderLinkStatus::Searching: return "SEARCHING";
        case CommanderLinkStatus::Linked: return "LINKED";
        case CommanderLinkStatus::NoFrames: return "NO FRAMES";
        case CommanderLinkStatus::Stale: return "STALE";
        default: return "?";
    }
}

void CommanderLink::setEnabled(bool enabled, std::uint64_t now_ms) {
    if (enabled_ == enabled) return;
    enabled_ = enabled;
    if (!enabled) {
        status_ = CommanderLinkStatus::Disabled;
        transport_connected_ = false;
        return;
    }
    enabled_since_ms_ = now_ms;
    status_ = transport_connected_ ? CommanderLinkStatus::NoFrames
                                   : CommanderLinkStatus::Searching;
}

void CommanderLink::setTransport(bool connected, std::uint64_t now_ms) {
    transport_connected_ = connected;
    if (!enabled_) {
        status_ = CommanderLinkStatus::Disabled;
        return;
    }
    if (!connected) {
        status_ = CommanderLinkStatus::Searching;
        return;
    }
    // A connected transport only becomes Linked once frames actually arrive.
    // Claiming "linked" from a socket state is exactly the kind of guess this
    // screen set refuses to draw.
    status_ = last_frame_ms_ != 0 &&
                      (now_ms - last_frame_ms_) <= policy_.frame_timeout_ms
                  ? CommanderLinkStatus::Linked
                  : CommanderLinkStatus::NoFrames;
}

void CommanderLink::setModuleInfo(const CommanderModuleVersion& version,
                                  const CommanderFeatureFlags& features) {
    version_ = version;
    features_ = features;
    module_info_known_ = true;
}

void CommanderLink::noteFrame(std::uint64_t now_ms) {
    ++frames_;
    last_frame_ms_ = now_ms;
    ever_linked_ = true;
    if (enabled_) status_ = CommanderLinkStatus::Linked;
}

void CommanderLink::tick(std::uint64_t now_ms) {
    if (!enabled_) {
        status_ = CommanderLinkStatus::Disabled;
        return;
    }
    if (!transport_connected_) {
        status_ = CommanderLinkStatus::Searching;
        return;
    }
    if (last_frame_ms_ == 0) {
        status_ = CommanderLinkStatus::NoFrames;
        return;
    }
    const std::uint64_t age = now_ms >= last_frame_ms_ ? now_ms - last_frame_ms_ : 0;
    if (age > policy_.frame_timeout_ms) {
        status_ = ever_linked_ ? CommanderLinkStatus::Stale
                               : CommanderLinkStatus::NoFrames;
        ++dropped_frames_;
        return;
    }
    status_ = CommanderLinkStatus::Linked;
}

bool CommanderLink::linkValue(int& out) const {
    switch (status_) {
        case CommanderLinkStatus::Linked:
            out = 1;
            return true;
        case CommanderLinkStatus::Searching:
        case CommanderLinkStatus::NoFrames:
        case CommanderLinkStatus::Stale:
            out = 0;
            return true;
        case CommanderLinkStatus::Disabled:
        default:
            return false;
    }
}

std::string CommanderLink::detail(const char* transport_name) const {
    char text[96];
    const char* transport = transport_name != nullptr ? transport_name : "?";
    if (module_info_known_) {
        // The same separator the rest of the screens use between items.
        std::snprintf(text, sizeof(text), "%s · v%u.%u.%u", transport,
                      static_cast<unsigned>(version_.major),
                      static_cast<unsigned>(version_.minor),
                      static_cast<unsigned>(version_.patch));
    } else {
        std::snprintf(text, sizeof(text), "%s no module info", transport);
    }
    return text;
}

std::uint8_t CommanderFrameV6::checksum(std::uint8_t command,
                                        std::uint16_t length,
                                        const std::uint8_t* payload) {
    unsigned sum = command;
    sum += static_cast<unsigned>(length >> 8) & 0xFFU;
    sum += static_cast<unsigned>(length) & 0xFFU;
    for (std::uint16_t i = 0; i < length; ++i) {
        sum += payload[i];
    }
    return static_cast<std::uint8_t>(sum & 0xFFU);
}

std::uint8_t CommanderFrameV6::checksum(
    std::uint8_t command, const std::vector<std::uint8_t>& payload) {
    return checksum(command, static_cast<std::uint16_t>(payload.size()),
                    payload.empty() ? nullptr : payload.data());
}

std::vector<std::uint8_t> CommanderFrameV6::encode(
    std::uint8_t command, const std::vector<std::uint8_t>& payload) {
    std::vector<std::uint8_t> frame;
    frame.reserve(payload.size() + kOverhead);
    frame.push_back(kHeader0);
    frame.push_back(kHeader1);
    frame.push_back(command);
    frame.push_back(static_cast<std::uint8_t>((payload.size() >> 8) & 0xFFU));
    frame.push_back(static_cast<std::uint8_t>(payload.size() & 0xFFU));
    frame.insert(frame.end(), payload.begin(), payload.end());
    frame.push_back(checksum(command, payload));
    return frame;
}

bool commanderCommandIsQueryV6(std::uint8_t command) {
    switch (static_cast<CommanderCommandV6>(command)) {
        // Reads. Nothing here changes the car or the module's configuration.
        case CommanderCommandV6::ReadDeviceInfo:
        case CommanderCommandV6::Gauge:
        case CommanderCommandV6::ReadValue:
        case CommanderCommandV6::Battery:
        case CommanderCommandV6::BatteryCells:
        case CommanderCommandV6::Dcdc:
            return true;
        default:
            return false;
    }
}

bool commanderCommandIsControlV6(std::uint8_t command) {
    return !commanderCommandIsQueryV6(command);
}

void CommanderFrameReaderV6::reset() {
    state_ = State::Idle;
    command_ = 0;
    length_ = 0;
    index_ = 0;
    running_ = 0;
    payload_.clear();
}

bool CommanderFrameReaderV6::feed(std::uint8_t byte, std::uint64_t now_ms,
                                  Frame& frame) {
    ++bytes_;
    // The module's own receiver gives up on a partial frame after a gap, so a
    // reader that waited forever would be the only one still holding half a
    // frame from a minute ago.
    if (state_ != State::Idle && last_byte_ms_ != 0 &&
        now_ms - last_byte_ms_ > CommanderFrameV6::kInterFrameGapMs) {
        if (state_ != State::Idle) ++dropped_partials_;
        reset();
    }
    last_byte_ms_ = now_ms;

    switch (state_) {
        case State::Idle:
            if (byte == CommanderFrameV6::kHeader0) state_ = State::Header1;
            else ++malformed_;
            return false;
        case State::Header1:
            if (byte == CommanderFrameV6::kHeader1) {
                state_ = State::Command;
            } else if (byte == CommanderFrameV6::kHeader0) {
                // 55 55: stay waiting for the second header byte.
                ++malformed_;
            } else {
                ++malformed_;
                state_ = State::Idle;
            }
            return false;
        case State::Command:
            command_ = byte;
            running_ = byte;
            state_ = State::LengthHigh;
            return false;
        case State::LengthHigh:
            length_ = static_cast<std::uint16_t>(byte) << 8;
            running_ = static_cast<std::uint8_t>(running_ + byte);
            state_ = State::LengthLow;
            return false;
        case State::LengthLow: {
            length_ = static_cast<std::uint16_t>(length_ | byte);
            running_ = static_cast<std::uint8_t>(running_ + byte);
            index_ = 0;
            payload_.clear();
            if (length_ == 0) {
                state_ = State::Checksum;
                return false;
            }
            if (length_ > CommanderFrameV6::kMaxPayload) {
                // The module refuses an over-long length; so do we, rather
                // than allocating whatever a corrupt byte stream asked for.
                ++malformed_;
                state_ = State::Idle;
                return false;
            }
            payload_.reserve(length_);
            state_ = State::Payload;
            return false;
        }
        case State::Payload:
            payload_.push_back(byte);
            running_ = static_cast<std::uint8_t>(running_ + byte);
            ++index_;
            if (index_ >= length_) state_ = State::Checksum;
            return false;
        case State::Checksum:
            if (running_ == byte) {
                frame.command = command_;
                frame.payload = payload_;
                ++frames_;
                reset();
                return true;
            }
            ++checksum_errors_;
            reset();
            return false;
        default:
            reset();
            return false;
    }
}

bool decodeCommanderDeviceInfoV6(const std::vector<std::uint8_t>& payload,
                                 std::uint64_t now_ms,
                                 CommanderDeviceInfoV6& out) {
    // The client insists on at least 18 bytes before it will look at any of
    // this, so a short reply is not "mostly right": it is not the reply.
    if (payload.size() < 18) return false;
    out = CommanderDeviceInfoV6{};
    out.valid = true;
    out.timestamp_ms = now_ms;
    out.hardware_version = payload[0];
    out.bootloader_version = payload[1];
    out.firmware_version = payload[2];
    out.flags = payload[3];

    if (payload.size() < 24) return true;  // header only, no body yet

    switch (out.hardware_version) {
        case 4:
        case 10:
            out.charge_state = payload[19];
            out.has_battery_voltage = true;
            out.battery_voltage_v =
                static_cast<float>(readU16(&payload[20])) / 1000.0F;
            break;
        case 9:
            out.has_ambient_light = true;
            out.light_brightness = payload[18] > 100 ? 100 : payload[18];
            out.light_rgb[0] = payload[20];
            out.light_rgb[1] = payload[21];
            out.light_rgb[2] = payload[22];
            break;
        default:
            out.ap_restore_state = payload[18];
            out.state_bits = payload[19];
            out.runtime_s = static_cast<float>(readU16(&payload[20])) / 1000.0F;
            out.data0 = payload[22];
            out.data1 = payload[23];
            break;
    }
    return true;
}

bool decodeCommanderGaugeV6(const std::vector<std::uint8_t>& payload,
                            std::uint64_t now_ms, CommanderGaugeV6& out) {
    // The client reads payload[0..15] before it checks the message length, so
    // a shorter reply is not a partial gauge frame - it is not one at all.
    if (payload.size() < 16) return false;
    out = CommanderGaugeV6{};
    out.valid = true;
    out.timestamp_ms = now_ms;

    const std::uint32_t first = readU32(&payload[0]);
    out.speed_kph = static_cast<std::uint16_t>(bits(first, 0, 9));
    out.gear = gearFromIndex(bits(first, 9, 3));
    out.turn = static_cast<std::uint8_t>(bits(first, 12, 2));
    out.autopilot = static_cast<std::uint8_t>(bits(first, 14, 2));
    out.door_bits = static_cast<std::uint8_t>(bits(first, 16, 4));
    // Door bits are not in door order: the client paints
    // driver (1), rear left (2), passenger (4), rear right (8).
    out.door_fl = (out.door_bits & 0x1) != 0;
    out.door_rl = (out.door_bits & 0x2) != 0;
    out.door_fr = (out.door_bits & 0x4) != 0;
    out.door_rr = (out.door_bits & 0x8) != 0;
    out.light_bits = static_cast<std::uint8_t>(
        bits(first, 20, 4) | (bits(first, 27, 1) << 4) |
        ((payload[4] << 1) & 0x20));
    // Lamp meanings come from the client's icon set: 1 high beam, 2 low beam,
    // 4 position, 32 brake. Bits 8 and 16 are shown by the client for two
    // icons whose meaning the code does not state, so they stay unnamed.
    out.high_beam = (out.light_bits & 0x01) != 0;
    out.headlight = (out.light_bits & 0x02) != 0;
    out.fog_light = (out.light_bits & 0x04) != 0;
    out.brake_light = (out.light_bits & 0x20) != 0;
    out.indicator_left = (out.turn & 0x1) != 0;
    out.indicator_right = (out.turn & 0x2) != 0;
    out.soc_percent = static_cast<std::uint8_t>(bits(first, 24, 7));

    const std::uint32_t second = readU32(&payload[4]);
    out.frunk_open = bits(second, 1, 1) != 0;
    out.trunk_open = bits(second, 5, 1) != 0;
    out.screen_on = bits(second, 0, 1) == 0;
    out.dark_theme = bits(second, 2, 1) != 0;
    out.sport_mode = bits(second, 3, 1) != 0;
    out.range_km = static_cast<float>(bits(second, 6, 26)) / 10.0F;

    for (int i = 0; i < 4; ++i) {
        const std::uint8_t raw = payload[8 + i];
        // 0 and 255 mean "no reading", not zero pressure. A tire at 0 bar is
        // flat; a tire with no sensor is unknown, and the screen must not
        // confuse the two.
        out.tire_valid[i] = raw != 0 && raw != 255;
        out.tire_bar[i] = out.tire_valid[i] ? 0.025F * static_cast<float>(raw) : 0.0F;
    }

    const std::uint32_t third = readU32(&payload[12]);
    const float pedal = 100.0F * static_cast<float>(bits(third, 0, 8)) / 250.0F;
    out.accelerator_percent = pedal > 100.0F ? 100.0F : pedal;
    out.rear_motor_kw =
        static_cast<float>(signExtend(bits(third, 8, 11), 11)) / 2.0F;
    out.front_motor_kw =
        static_cast<float>(signExtend(bits(third, 19, 11), 11)) / 2.0F;

    if (payload.size() < 33) return true;
    out.has_extended = true;

    const std::uint32_t elevation_source =
        (static_cast<std::uint32_t>(payload[15]) << 16) |
        (static_cast<std::uint32_t>(payload[16]) << 8) |
        static_cast<std::uint32_t>(payload[17]);
    out.elevation_m =
        static_cast<float>(signExtend(bits(elevation_source, 6, 14), 14));
    out.battery_heating = static_cast<std::uint8_t>(bits(payload[17], 4, 2));
    out.imperial_units = bits(payload[17], 6, 1) != 0;
    out.hands_on_wheel = bits(payload[17], 7, 1) != 0;

    const std::uint32_t brakes = readU32(&payload[18]);
    out.brake_temp_c[0] = static_cast<float>(bits(brakes, 0, 10)) - 40.0F;
    out.brake_temp_c[1] = static_cast<float>(bits(brakes, 10, 10)) - 40.0F;
    out.brake_temp_c[2] = static_cast<float>(bits(brakes, 20, 10)) - 40.0F;
    out.brake_temp_c[3] =
        static_cast<float>((static_cast<std::uint32_t>(payload[22]) << 2) |
                           bits(brakes, 30, 2)) - 40.0F;

    const std::uint32_t hvac = readU32(&payload[23]);
    out.hvac_blower_rpm = 5.0F * static_cast<float>(bits(hvac, 0, 10));
    out.hvac_evaporator_w = 5.0F * static_cast<float>(bits(hvac, 10, 11));
    out.cabin_temp_c = 0.1F * static_cast<float>(bits(hvac, 21, 11)) - 40.0F;
    out.ambient_temp_c = 0.5F * static_cast<float>(payload[27]) - 40.0F;

    const std::uint32_t pack = readU32(&payload[28]);
    out.cell_voltage_v = 0.002F * static_cast<float>(bits(pack, 0, 12));
    out.rated_range_km = 1.61F * static_cast<float>(bits(pack, 12, 10));
    out.battery_temp_c = 0.5F * static_cast<float>(bits(pack, 22, 9)) - 40.0F;

    const std::uint32_t tail =
        (static_cast<std::uint32_t>(payload[32]) << 8) |
        static_cast<std::uint32_t>(payload[31]);
    // The client only shows a speed limit in the forward gears; in P and R the
    // same bits mean something else, so they are not reported as a limit.
    const bool forward_gear = out.gear == Gear::Reverse ||
                              out.gear == Gear::Neutral ||
                              out.gear == Gear::Drive;
    out.speed_limit_kph =
        forward_gear ? 5.0F * static_cast<float>(bits(tail, 7, 5)) : 0.0F;
    out.blind_spot_rear_left = static_cast<std::uint8_t>(bits(tail, 12, 2));
    out.blind_spot_rear_right = static_cast<std::uint8_t>(bits(tail, 14, 2));
    return true;
}

bool decodeCommanderPackV6(const std::vector<std::uint8_t>& payload,
                           std::uint64_t now_ms, CommanderPackV6& out) {
    // The client's last read is at payload[28], so that is the shortest
    // complete pack summary.
    if (payload.size() < 29) return false;
    out = CommanderPackV6{};
    out.valid = true;
    out.timestamp_ms = now_ms;

    out.pack_voltage_v = 0.01F * static_cast<float>(readU16(&payload[0]));
    // The client reads the current as -0.1 * value and then repairs one wrap:
    // anything below -3276.7 A gains 6553.6 A back.
    float current = -0.1F * static_cast<float>(readU16(&payload[2]));
    if (current < -3276.7F) current += 6553.6F;
    out.pack_current_a = current;
    out.pack_power_kw = out.pack_voltage_v * current / 1000.0F;
    out.total_discharged_kwh = 0.001F * static_cast<float>(readU32(&payload[4]));
    out.total_charged_kwh = 0.001F * static_cast<float>(readU32(&payload[8]));

    const std::uint32_t energy = readU32(&payload[12]);
    const float remaining = 0.02F * static_cast<float>(bits(energy, 0, 16));
    const float full = 0.02F * static_cast<float>(bits(energy, 16, 16));
    out.remaining_kwh = remaining;
    out.full_kwh = full;
    out.remaining_known = remaining > 0.0F;
    out.reserve_kwh = 0.01F * static_cast<float>(readU16(&payload[16]));

    const std::uint32_t cells = readU24(&payload[18]);
    out.max_cell_v = 0.002F * static_cast<float>(bits(cells, 0, 12));
    out.min_cell_v = 0.002F * static_cast<float>(bits(cells, 12, 12));
    out.cell_delta_mv = (out.max_cell_v - out.min_cell_v) * 1000.0F;

    const std::uint32_t capacity = readU32(&payload[21]);
    out.factory_capacity_kwh = 0.1F * static_cast<float>(bits(capacity, 0, 10));
    out.range_km = 1.61F * static_cast<float>(bits(capacity, 10, 10));

    const std::uint32_t soc_bytes = readU16(&payload[24]);
    out.car_soc_percent = static_cast<std::uint8_t>(bits(soc_bytes, 7, 7));

    // The actual SOC is the ratio the module itself computes, and only when
    // there is energy to compute it from: a ratio against an empty pack is not
    // a percentage, it is a division by zero wearing one.
    const float usable_full = full - out.reserve_kwh;
    if (remaining > 0.0F && usable_full > 0.0F) {
        float percent = (remaining - out.reserve_kwh) / usable_full * 100.0F;
        if (percent > 100.0F) percent = 100.0F;
        if (percent < 0.0F) percent = 0.0F;
        out.actual_soc_percent = percent;
        out.actual_soc_known = true;
    }

    out.battery_temp_c =
        0.5F * static_cast<float>(bits(capacity, 22, 9)) - 40.0F;
    out.heating = bits(capacity, 20, 2) == 2;
    out.odometer_km = static_cast<float>(bits(readU32(&payload[25]), 6, 26)) / 10.0F;
    return true;
}

bool decodeCommanderDcdcV6(const std::vector<std::uint8_t>& payload,
                           std::uint64_t now_ms, CommanderDcdcV6& out) {
    if (payload.size() < 8) return false;
    out = CommanderDcdcV6{};
    out.valid = true;
    out.timestamp_ms = now_ms;
    const std::uint32_t first = readU32(&payload[0]);
    out.output_voltage_v = 0.01F * static_cast<float>(bits(first, 0, 16));
    out.input_voltage_v = 0.1F * static_cast<float>(bits(first, 16, 16));
    const std::uint32_t second = readU32(&payload[4]);
    out.output_current_a = 0.1F * static_cast<float>(bits(second, 0, 16));
    out.output_power_w = out.output_voltage_v * out.output_current_a;
    return true;
}

void applyCommanderReadingsV6(const CommanderGaugeV6& gauge,
                              const CommanderPackV6& pack,
                              const CommanderDcdcV6& dcdc,
                              VehicleState& out, std::uint64_t now_ms) {
    if (gauge.valid) {
        set(out.accelerator_position, gauge.accelerator_percent, now_ms,
            SignalQuality::Confirmed, Unit::Percent);
        set(out.front_motor_power, gauge.front_motor_kw, now_ms,
            SignalQuality::Confirmed, Unit::Kilowatt);
        set(out.rear_motor_power, gauge.rear_motor_kw, now_ms,
            SignalQuality::Confirmed, Unit::Kilowatt);
        set(out.ambient_temperature, gauge.ambient_temp_c, now_ms,
            SignalQuality::Confirmed, Unit::Celsius);
        set(out.cabin_temperature, gauge.cabin_temp_c, now_ms,
            SignalQuality::Confirmed, Unit::Celsius);
        set(out.hvac_blower_rpm, gauge.hvac_blower_rpm, now_ms,
            SignalQuality::Confirmed, Unit::Rpm);
        set(out.hvac_power_demand, gauge.hvac_evaporator_w / 1000.0F, now_ms,
            SignalQuality::Confirmed, Unit::Kilowatt);
        set(out.brake_temp_fl, gauge.brake_temp_c[0], now_ms,
            SignalQuality::Confirmed, Unit::Celsius);
        set(out.brake_temp_fr, gauge.brake_temp_c[1], now_ms,
            SignalQuality::Confirmed, Unit::Celsius);
        set(out.brake_temp_rl, gauge.brake_temp_c[2], now_ms,
            SignalQuality::Confirmed, Unit::Celsius);
        set(out.brake_temp_rr, gauge.brake_temp_c[3], now_ms,
            SignalQuality::Confirmed, Unit::Celsius);
        if (gauge.battery_temp_c > -40.0F) {
            set(out.battery_temperature, gauge.battery_temp_c, now_ms,
                SignalQuality::Confirmed, Unit::Celsius);
        }
        if (gauge.speed_limit_kph > 0.0F) {
            set(out.speed_limit, static_cast<std::uint16_t>(gauge.speed_limit_kph),
                now_ms, SignalQuality::Confirmed, Unit::KilometerPerHour);
        } else {
            out.speed_limit.invalidate(now_ms);
        }
    }

    if (pack.valid) {
        set(out.battery_voltage, pack.pack_voltage_v, now_ms,
            SignalQuality::Confirmed, Unit::Volt);
        set(out.battery_current, pack.pack_current_a, now_ms,
            SignalQuality::Confirmed, Unit::Ampere);
        set(out.battery_power, pack.pack_power_kw, now_ms,
            SignalQuality::Confirmed, Unit::Kilowatt);
        set(out.total_charged_energy, pack.total_charged_kwh, now_ms,
            SignalQuality::Confirmed, Unit::KilowattHour);
        set(out.total_discharged_energy, pack.total_discharged_kwh, now_ms,
            SignalQuality::Confirmed, Unit::KilowattHour);
        if (pack.max_cell_v > 0.0F) {
            set(out.max_cell_voltage, pack.max_cell_v, now_ms,
                SignalQuality::Confirmed, Unit::Volt);
            set(out.min_cell_voltage, pack.min_cell_v, now_ms,
                SignalQuality::Confirmed, Unit::Volt);
            set(out.cell_delta, pack.max_cell_v - pack.min_cell_v, now_ms,
                SignalQuality::Confirmed, Unit::Volt);
        }
        if (pack.remaining_known) {
            set(out.energy_remaining, pack.remaining_kwh, now_ms,
                SignalQuality::Confirmed, Unit::KilowattHour);
            set(out.energy_full_estimate, pack.full_kwh, now_ms,
                SignalQuality::Confirmed, Unit::KilowattHour);
            set(out.energy_reserve, pack.reserve_kwh, now_ms,
                SignalQuality::Confirmed, Unit::KilowattHour);
        }
        if (pack.battery_temp_c > -40.0F) {
            set(out.battery_temperature, pack.battery_temp_c, now_ms,
                SignalQuality::Confirmed, Unit::Celsius);
        }
        set(out.battery_heating, pack.heating, now_ms, SignalQuality::Confirmed,
            Unit::None);
        set(out.odometer, static_cast<std::uint32_t>(pack.odometer_km),
            now_ms, SignalQuality::Confirmed, Unit::Kilometer);

        // SOC: the energy ratio when the module can compute it, otherwise the
        // car's own 7-bit SOC as the module reports it. Never the MCU byte.
        if (pack.actual_soc_known) {
            set(out.actual_soc, static_cast<std::uint8_t>(pack.actual_soc_percent),
                now_ms, SignalQuality::Confirmed, Unit::Percent);
        } else if (pack.car_soc_percent > 0) {
            set(out.actual_soc, pack.car_soc_percent, now_ms,
                SignalQuality::Inferred, Unit::Percent);
        }
    } else if (gauge.valid && gauge.soc_percent > 0) {
        set(out.actual_soc, gauge.soc_percent, now_ms, SignalQuality::Inferred,
            Unit::Percent);
    }

    if (dcdc.valid) {
        set(out.dcdc_input_voltage, dcdc.input_voltage_v, now_ms,
            SignalQuality::Confirmed, Unit::Volt);
        set(out.dcdc_output_voltage, dcdc.output_voltage_v, now_ms,
            SignalQuality::Confirmed, Unit::Volt);
        set(out.dcdc_output_current, dcdc.output_current_a, now_ms,
            SignalQuality::Confirmed, Unit::Ampere);
        set(out.dcdc_output_power, dcdc.output_power_w / 1000.0F, now_ms,
            SignalQuality::Confirmed, Unit::Kilowatt);
    }
}

void applyCommanderFallbackV6(const CommanderGaugeV6& gauge,
                              const CommanderFallbackV6& which,
                              VehicleState& out, std::uint64_t now_ms) {
    if (!gauge.valid) return;
    // Everything here is the module's decoding of the car standing in for the
    // car's own link. It is marked Inferred precisely because it is a second
    // decoder's opinion, not the reading the cluster was built around.
    constexpr SignalQuality quality = SignalQuality::Inferred;
    if (which.speed) {
        set(out.speed, gauge.speed_kph, now_ms, quality, Unit::KilometerPerHour);
    }
    if (which.gear && gauge.gear != Gear::Unknown) {
        set(out.gear, gauge.gear, now_ms, quality, Unit::None);
    }
    if (which.range && gauge.range_km > 0.0F) {
        set(out.range, static_cast<std::uint16_t>(gauge.range_km), now_ms,
            quality, Unit::Kilometer);
    }
    if (which.closures) {
        set(out.door_fl, gauge.door_fl, now_ms, quality, Unit::None);
        set(out.door_fr, gauge.door_fr, now_ms, quality, Unit::None);
        set(out.door_rl, gauge.door_rl, now_ms, quality, Unit::None);
        set(out.door_rr, gauge.door_rr, now_ms, quality, Unit::None);
        set(out.frunk, gauge.frunk_open, now_ms, quality, Unit::None);
        set(out.trunk, gauge.trunk_open, now_ms, quality, Unit::None);
    }
    if (which.tire_pressure) {
        if (gauge.tire_valid[0]) set(out.tire_fl, gauge.tire_bar[0], now_ms, quality, Unit::Bar);
        if (gauge.tire_valid[1]) set(out.tire_fr, gauge.tire_bar[1], now_ms, quality, Unit::Bar);
        if (gauge.tire_valid[2]) set(out.tire_rl, gauge.tire_bar[2], now_ms, quality, Unit::Bar);
        if (gauge.tire_valid[3]) set(out.tire_rr, gauge.tire_bar[3], now_ms, quality, Unit::Bar);
    }
}

void mergeCommanderInto(VehicleState& target, const VehicleState& commander) {
    // Enhanced-only fields. The MCU path owns speed, gear, range, the SOC byte,
    // closures, lighting, tires and trip data, so none of those appear here.
    copyIfValid(target.actual_soc, commander.actual_soc);
    copyIfValid(target.energy_remaining, commander.energy_remaining);
    copyIfValid(target.energy_full_estimate, commander.energy_full_estimate);
    copyIfValid(target.energy_reserve, commander.energy_reserve);
    copyIfValid(target.total_charged_energy, commander.total_charged_energy);
    copyIfValid(target.total_discharged_energy, commander.total_discharged_energy);
    copyIfValid(target.battery_power, commander.battery_power);
    copyIfValid(target.battery_voltage, commander.battery_voltage);
    copyIfValid(target.battery_current, commander.battery_current);
    copyIfValid(target.front_motor_power, commander.front_motor_power);
    copyIfValid(target.rear_motor_power, commander.rear_motor_power);
    copyIfValid(target.accelerator_position, commander.accelerator_position);
    copyIfValid(target.brake_position, commander.brake_position);
    copyIfValid(target.max_cell_voltage, commander.max_cell_voltage);
    copyIfValid(target.min_cell_voltage, commander.min_cell_voltage);
    copyIfValid(target.cell_delta, commander.cell_delta);
    copyIfValid(target.battery_temperature, commander.battery_temperature);
    copyIfValid(target.ambient_temperature, commander.ambient_temperature);
    copyIfValid(target.cabin_temperature, commander.cabin_temperature);
    copyIfValid(target.battery_heating, commander.battery_heating);
    copyIfValid(target.dcdc_input_voltage, commander.dcdc_input_voltage);
    copyIfValid(target.dcdc_output_voltage, commander.dcdc_output_voltage);
    copyIfValid(target.dcdc_output_current, commander.dcdc_output_current);
    copyIfValid(target.dcdc_output_power, commander.dcdc_output_power);
    copyIfValid(target.hvac_blower_rpm, commander.hvac_blower_rpm);
    copyIfValid(target.hvac_power_demand, commander.hvac_power_demand);
    copyIfValid(target.brake_temp_fl, commander.brake_temp_fl);
    copyIfValid(target.brake_temp_fr, commander.brake_temp_fr);
    copyIfValid(target.brake_temp_rl, commander.brake_temp_rl);
    copyIfValid(target.brake_temp_rr, commander.brake_temp_rr);
    copyIfValid(target.speed_limit, commander.speed_limit);
    if (!commander.cell_voltages.empty()) {
        target.cell_voltages = commander.cell_voltages;
    }
}

}  // namespace dashboard
