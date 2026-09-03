#include "dashboard/original_mcu_adapter.h"

#include <cstdint>
#include <iomanip>
#include <iostream>
#include <vector>

namespace {

std::vector<std::uint8_t> makeFrame(
    std::uint8_t command,
    const std::vector<std::uint8_t>& payload) {
    std::vector<std::uint8_t> frame;
    frame.reserve(payload.size() + 4);
    frame.push_back(dashboard::ProtocolParser::kHeader);
    frame.push_back(command);
    frame.push_back(static_cast<std::uint8_t>(payload.size()));
    frame.insert(frame.end(), payload.begin(), payload.end());
    frame.push_back(dashboard::ProtocolParser::checksum(
        command,
        payload.empty() ? nullptr : payload.data(),
        payload.size()));
    return frame;
}

const char* openClosed(const dashboard::Signal<bool>& signal) {
    return signal.valid && signal.value ? "OPEN" : "closed";
}

}  // namespace

int main() {
    dashboard::OriginalMcuAdapter adapter;

    // Deterministic MVP simulation: 88 km/h, 71% SOC, 406 km range,
    // Drive, left-front door open, and four tire pressures.
    const auto command04 = makeFrame(
        0x04,
        {88, 0, 0, 0, 0, 0, 150, 1, 71, 0, 0x34, 0x12, 0});
    // Real-car confirmed gear nibble: 0 = Park, 4 = Drive.
    const auto command01 = makeFrame(0x01, {0, 0, 0, 0x01, 0x40});
    const auto command12 = makeFrame(0x12, {0, 116, 114, 112, 118});

    adapter.feed(command04.data(), command04.size(), 1000);
    adapter.feed(command01.data(), command01.size(), 1010);
    adapter.feed(command12.data(), command12.size(), 1020);

    const auto& state = adapter.state();
    std::cout << "Tesla dashboard MVP simulation\n"
              << "Speed: " << state.speed.value << " km/h\n"
              << "Gear:  " << dashboard::gearName(state.gear.value) << "\n"
              << "SOC:   " << static_cast<unsigned>(state.soc.value) << "%\n"
              << "Range: " << state.range.value << " km\n"
              << "Doors: FL=" << openClosed(state.door_fl)
              << " FR=" << openClosed(state.door_fr)
              << " RL=" << openClosed(state.door_rl)
              << " RR=" << openClosed(state.door_rr)
              << " frunk=" << openClosed(state.frunk)
              << " trunk=" << openClosed(state.trunk) << "\n"
              << std::fixed << std::setprecision(2)
              << "Tires: " << state.tire_fl.value << " / "
              << state.tire_fr.value << " / "
              << state.tire_rl.value << " / "
              << state.tire_rr.value << " bar\n"
              << "Packets: " << adapter.parserStats().valid_packets
              << ", checksum errors: "
              << adapter.parserStats().checksum_errors << "\n";
    return 0;
}
