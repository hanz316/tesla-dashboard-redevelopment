#include "dashboard/commander_link.h"

#include <cstdio>

namespace dashboard {
namespace {

std::uint16_t readU16(const std::uint8_t* p) {
    return static_cast<std::uint16_t>(p[0] | (static_cast<std::uint16_t>(p[1]) << 8));
}

std::int16_t readI16(const std::uint8_t* p) {
    return static_cast<std::int16_t>(readU16(p));
}

std::uint32_t readU32(const std::uint8_t* p) {
    return static_cast<std::uint32_t>(p[0]) |
           (static_cast<std::uint32_t>(p[1]) << 8) |
           (static_cast<std::uint32_t>(p[2]) << 16) |
           (static_cast<std::uint32_t>(p[3]) << 24);
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
    status_ = last_frame_ms_ != 0 && (now_ms - last_frame_ms_) <= policy_.frame_timeout_ms
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
        std::snprintf(text, sizeof(text), "%s · v%u.%u.%u", transport,
                      static_cast<unsigned>(version_.major),
                      static_cast<unsigned>(version_.minor),
                      static_cast<unsigned>(version_.patch));
    } else {
        std::snprintf(text, sizeof(text), "%s · no module info", transport);
    }
    return text;
}

std::uint8_t CommanderTelemetryDecoder::checksum(std::uint8_t type,
                                                 std::uint8_t length,
                                                 const std::uint8_t* payload) {
    unsigned sum = static_cast<unsigned>(type) + static_cast<unsigned>(length);
    for (std::uint8_t i = 0; i < length; ++i) {
        sum += payload[i];
    }
    return static_cast<std::uint8_t>(~sum & 0xFFU);
}

void CommanderTelemetryDecoder::decode(const std::uint8_t* data,
                                       std::size_t length,
                                       VehicleState& out,
                                       std::uint64_t now_ms) {
    if (data == nullptr) return;
    std::size_t pos = 0;
    while (pos + CommanderFrameHeader::kOverhead <= length) {
        if (data[pos] != CommanderFrameHeader::kHeader) {
            ++stats_.malformed;
            ++pos;
            continue;
        }
        const std::uint8_t type = data[pos + 1];
        const std::uint8_t payload_length = data[pos + 2];
        const std::size_t frame_length = 3 + static_cast<std::size_t>(payload_length) + 1;
        if (pos + frame_length > length) {
            // Incomplete tail: a transport may hand us a partial frame. Waiting
            // for the rest is correct; counting it as an error is not.
            break;
        }
        const std::uint8_t* payload = data + pos + 3;
        const std::uint8_t expected = checksum(type, payload_length, payload);
        const std::uint8_t actual = data[pos + 3 + payload_length];
        if (expected != actual) {
            ++stats_.checksum_errors;
            ++pos;  // resync on the next header candidate
            continue;
        }
        ++stats_.frames;
        decodeMessage(type, payload, payload_length, out, now_ms);
        pos += frame_length;
    }
}

void CommanderTelemetryDecoder::decodeMessage(std::uint8_t raw_type,
                                              const std::uint8_t* payload,
                                              std::uint8_t length,
                                              VehicleState& out,
                                              std::uint64_t now_ms) {
    const auto type = static_cast<CommanderMessageType>(raw_type);
    switch (type) {
        case CommanderMessageType::Pack: {
            if (length < 7) { ++stats_.malformed; return; }
            out.actual_soc.update(payload[0], now_ms, SignalSource::Commander,
                                  SignalQuality::Confirmed, Unit::Percent);
            out.battery_voltage.update(
                static_cast<float>(readU16(payload + 1)) / 10.0F, now_ms,
                SignalSource::Commander, SignalQuality::Confirmed, Unit::Volt);
            out.battery_current.update(
                static_cast<float>(readI16(payload + 3)) / 10.0F, now_ms,
                SignalSource::Commander, SignalQuality::Confirmed, Unit::Ampere);
            out.battery_power.update(
                static_cast<float>(readI16(payload + 5)) / 10.0F, now_ms,
                SignalSource::Commander, SignalQuality::Confirmed, Unit::Kilowatt);
            break;
        }
        case CommanderMessageType::Energy: {
            if (length < 10) { ++stats_.malformed; return; }
            out.total_charged_energy.update(
                static_cast<float>(readU32(payload)) / 10.0F, now_ms,
                SignalSource::Commander, SignalQuality::Confirmed, Unit::KilowattHour);
            out.total_discharged_energy.update(
                static_cast<float>(readU32(payload + 4)) / 10.0F, now_ms,
                SignalSource::Commander, SignalQuality::Confirmed, Unit::KilowattHour);
            out.energy_remaining.update(
                static_cast<float>(readU16(payload + 8)) / 10.0F, now_ms,
                SignalSource::Commander, SignalQuality::Confirmed, Unit::KilowattHour);
            break;
        }
        case CommanderMessageType::Cells: {
            if (length < 1) { ++stats_.malformed; return; }
            const std::uint8_t count = payload[0];
            if (count == 0 || length < static_cast<std::uint8_t>(1 + 2 * count)) {
                ++stats_.malformed;
                return;
            }
            out.cell_voltages.assign(count, Signal<float>{});
            float lowest = 0.0F;
            float highest = 0.0F;
            for (std::uint8_t i = 0; i < count; ++i) {
                const float volts = static_cast<float>(readU16(payload + 1 + 2 * i)) / 1000.0F;
                out.cell_voltages[i].update(volts, now_ms, SignalSource::Commander,
                                            SignalQuality::Confirmed, Unit::Volt);
                if (i == 0 || volts < lowest) lowest = volts;
                if (i == 0 || volts > highest) highest = volts;
            }
            out.max_cell_voltage.update(highest, now_ms, SignalSource::Commander,
                                        SignalQuality::Confirmed, Unit::Volt);
            out.min_cell_voltage.update(lowest, now_ms, SignalSource::Commander,
                                        SignalQuality::Confirmed, Unit::Volt);
            out.cell_delta.update(highest - lowest, now_ms, SignalSource::Commander,
                                  SignalQuality::Confirmed, Unit::Volt);
            break;
        }
        case CommanderMessageType::Inputs: {
            if (length < 2) { ++stats_.malformed; return; }
            out.accelerator_position.update(payload[0] * 0.5F, now_ms,
                                            SignalSource::Commander,
                                            SignalQuality::Confirmed, Unit::Percent);
            out.brake_position.update(payload[1] * 0.5F, now_ms,
                                      SignalSource::Commander,
                                      SignalQuality::Confirmed, Unit::Percent);
            break;
        }
        case CommanderMessageType::Info: {
            if (length < 4) { ++stats_.malformed; return; }
            version_.major = payload[0];
            version_.minor = payload[1];
            version_.patch = payload[2];
            features_.enabled = true;
            features_.raw_can = (payload[3] & 0x01U) != 0;
            features_.bms = (payload[3] & 0x02U) != 0;
            features_.cells = (payload[3] & 0x04U) != 0;
            features_.power = (payload[3] & 0x08U) != 0;
            module_info_known_ = true;
            break;
        }
        case CommanderMessageType::Temperatures: {
            if (length < 6) { ++stats_.malformed; return; }
            out.battery_temperature.update(
                static_cast<float>(readI16(payload)) / 10.0F, now_ms,
                SignalSource::Commander, SignalQuality::Confirmed, Unit::Celsius);
            out.ambient_temperature.update(
                static_cast<float>(readI16(payload + 2)) / 10.0F, now_ms,
                SignalSource::Commander, SignalQuality::Confirmed, Unit::Celsius);
            out.cabin_temperature.update(
                static_cast<float>(readI16(payload + 4)) / 10.0F, now_ms,
                SignalSource::Commander, SignalQuality::Confirmed, Unit::Celsius);
            break;
        }
        default:
            // An unknown type is counted, not guessed at. A future Commander
            // firmware adding a message must not be read as a known one.
            ++stats_.unknown_types;
            return;
    }
    ++stats_.decoded;
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
    if (!commander.cell_voltages.empty()) {
        target.cell_voltages = commander.cell_voltages;
    }
}

}  // namespace dashboard
