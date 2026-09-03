#include "dashboard/original_mcu_adapter.h"
#include "dashboard/source_adapters.h"

#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <vector>

namespace {

int failures = 0;

#define CHECK(condition)                                                        \
    do {                                                                        \
        if (!(condition)) {                                                     \
            std::cerr << __FILE__ << ':' << __LINE__                            \
                      << " CHECK failed: " #condition << '\n';                 \
            ++failures;                                                        \
        }                                                                       \
    } while (false)

std::vector<std::uint8_t> makeFrame(
    std::uint8_t command,
    const std::vector<std::uint8_t>& payload) {
    std::vector<std::uint8_t> frame{
        dashboard::ProtocolParser::kHeader,
        command,
        static_cast<std::uint8_t>(payload.size())};
    frame.insert(frame.end(), payload.begin(), payload.end());
    frame.push_back(dashboard::ProtocolParser::checksum(
        command,
        payload.empty() ? nullptr : payload.data(),
        payload.size()));
    return frame;
}

void parserHandlesFragmentationAndNoise() {
    dashboard::ProtocolParser parser;
    const auto frame = makeFrame(0x04, {1, 2, 3});
    const std::uint8_t noise[] = {0x99, 0x00};
    CHECK(parser.feed(noise, sizeof(noise)).empty());
    CHECK(parser.feed(frame.data(), 2).empty());
    const auto frames = parser.feed(frame.data() + 2, frame.size() - 2);
    CHECK(frames.size() == 1);
    CHECK(frames[0].command == 0x04);
    CHECK(frames[0].payload == std::vector<std::uint8_t>({1, 2, 3}));
    CHECK(parser.stats().discarded_bytes == 2);
}

void parserRejectsBadChecksumAndResynchronizes() {
    dashboard::ProtocolParser parser;
    auto bad = makeFrame(0x01, {0xaa});
    bad.back() ^= 0xff;
    const auto good = makeFrame(0x07, {100, 50});
    bad.insert(bad.end(), good.begin(), good.end());
    const auto frames = parser.feed(bad.data(), bad.size());
    CHECK(frames.size() == 1);
    CHECK(frames[0].command == 0x07);
    CHECK(parser.stats().checksum_errors == 1);
}

void adapterDecodesMvpSignals() {
    dashboard::OriginalMcuAdapter adapter;
    const auto frame = makeFrame(
        0x04,
        {0x2c, 0x01, 0, 0, 0, 0, 0x90, 0x01, 73, 0, 0x56, 0x34, 0x12});
    adapter.feed(frame.data(), frame.size(), 4242);
    const auto& state = adapter.state();
    CHECK(state.speed.valid && state.speed.value == 300);
    CHECK(state.range.valid && state.range.value == 400);
    CHECK(state.soc.valid && state.soc.value == 73);
    CHECK(state.soc.quality == dashboard::SignalQuality::Estimated);
    CHECK(state.distance_raw.valid && state.distance_raw.value == 0x123456);
    CHECK(state.speed.timestamp_ms == 4242);
    CHECK(state.speed.source == dashboard::SignalSource::OriginalMcu);
}

void adapterDecodesGearAndConfigurableDoors() {
    dashboard::OriginalMcuAdapter adapter;
    // 2026-08-31 real-car validation confirmed high nibble 4 = Drive.
    const auto frame = makeFrame(0x01, {0, 0, 0, 0x35, 0x40});
    adapter.feed(frame.data(), frame.size(), 5000);
    const auto& state = adapter.state();
    CHECK(state.gear.valid);
    CHECK(state.gear.value == dashboard::Gear::Drive);
    CHECK(state.gear.quality == dashboard::SignalQuality::Confirmed);
    CHECK(state.door_fl.value);
    CHECK(state.door_fr.value);
    CHECK(!state.door_rl.value);
    CHECK(!state.door_rr.value);
    CHECK(state.frunk.value);
    CHECK(state.trunk.value);
    CHECK(state.door_fl.quality == dashboard::SignalQuality::Confirmed);
    CHECK(state.door_fr.quality == dashboard::SignalQuality::Inferred);
}

void adapterDoesNotGuessUnconfirmedGearCodes() {
    dashboard::OriginalMcuAdapter adapter;
    const auto frame = makeFrame(0x01, {0, 0, 0, 0, 0x30});
    adapter.feed(frame.data(), frame.size(), 5010);
    CHECK(adapter.state().gear.valid);
    CHECK(adapter.state().gear.value == dashboard::Gear::Unknown);
    CHECK(adapter.state().gear.quality == dashboard::SignalQuality::Unknown);
}

void adapterDecodesTiresAndTemperature() {
    dashboard::OriginalMcuAdapter adapter;
    const auto tires = makeFrame(0x12, {0, 100, 104, 108, 112});
    const auto temperature = makeFrame(0x07, {140, 55});
    adapter.feed(tires.data(), tires.size(), 6000);
    adapter.feed(temperature.data(), temperature.size(), 6010);
    const auto& state = adapter.state();
    CHECK(std::fabs(state.tire_fl.value - 2.50F) < 0.001F);
    CHECK(std::fabs(state.tire_fr.value - 2.60F) < 0.001F);
    CHECK(std::fabs(state.tire_rl.value - 2.70F) < 0.001F);
    CHECK(std::fabs(state.tire_rr.value - 2.80F) < 0.001F);
    CHECK(state.temperature_primary.value == 30);
    CHECK(state.temperature_secondary.value == 30);
}

void shortPayloadNeverPublishesInvalidData() {
    dashboard::OriginalMcuAdapter adapter;
    const auto short_frame = makeFrame(0x04, {1, 2});
    adapter.feed(short_frame.data(), short_frame.size(), 7000);
    CHECK(!adapter.state().speed.valid);
    CHECK(adapter.adapterStats().short_payloads == 1);
}

void tickInvalidatesStaleSignalsAndTracksHealth() {
    dashboard::OriginalMcuAdapter adapter;
    const auto frame = makeFrame(0x04, {88, 0, 0, 0, 0, 0, 150, 1, 71, 0, 0, 0, 0});
    adapter.feed(frame.data(), frame.size(), 1000);
    CHECK(adapter.state().speed.valid);
    CHECK(adapter.health().status == dashboard::DataSourceStatus::Connected);

    adapter.tick(1500);
    CHECK(adapter.state().speed.valid);

    adapter.tick(3000);
    CHECK(!adapter.state().speed.valid);
    CHECK(adapter.state().speed.stale);
    CHECK(adapter.health().status == dashboard::DataSourceStatus::Offline);
}

void resetClearsStateAndStats() {
    dashboard::OriginalMcuAdapter adapter;
    const auto frame = makeFrame(0x04, {88, 0, 0, 0, 0, 0, 150, 1, 71, 0, 0, 0, 0});
    adapter.feed(frame.data(), frame.size(), 1000);
    CHECK(adapter.state().speed.valid);
    CHECK(adapter.parserStats().valid_packets == 1);

    adapter.reset();
    CHECK(!adapter.state().speed.valid);
    CHECK(adapter.parserStats().valid_packets == 0);
    CHECK(adapter.parserStats().bytes_received == 0);
    CHECK(adapter.health().status == dashboard::DataSourceStatus::Offline);
}

void frameListenerReceivesParsedFrames() {
    dashboard::OriginalMcuAdapter adapter;
    int received = 0;
    std::uint8_t seen_command = 0;
    adapter.setFrameListener([&](const dashboard::ProtocolFrame& frame, std::uint64_t ts) {
        ++received;
        seen_command = frame.command;
        CHECK(ts == 4242);
    });

    const auto frame = makeFrame(0x04, {88, 0, 0, 0, 0, 0, 150, 1, 71, 0, 0, 0, 0});
    adapter.feed(frame.data(), frame.size(), 4242);
    CHECK(received == 1);
    CHECK(seen_command == 0x04);
}

void simulationAdapterUpdatesAndStales() {
    dashboard::SimulationAdapter sim;
    CHECK(sim.health().status == dashboard::DataSourceStatus::Offline);

    sim.setDriving(88, dashboard::Gear::Drive, 71, 406, 1000);
    CHECK(sim.health().status == dashboard::DataSourceStatus::Connected);
    CHECK(sim.state().speed.valid && sim.state().speed.value == 88);
    CHECK(sim.state().gear.value == dashboard::Gear::Drive);
    CHECK(sim.state().soc.value == 71);
    CHECK(sim.state().range.value == 406);
    CHECK(sim.state().speed.source == dashboard::SignalSource::Simulation);

    sim.setDoors(true, false, false, false, true, false, 1010);
    CHECK(sim.state().door_fl.value);
    CHECK(sim.state().frunk.value);
    CHECK(!sim.state().door_fr.value);

    sim.setTires(2.5F, 2.6F, 2.7F, 2.8F, 1020);
    CHECK(std::fabs(sim.state().tire_rl.value - 2.70F) < 0.001F);

    sim.tick(3000);
    CHECK(!sim.state().speed.valid);
    CHECK(sim.health().status == dashboard::DataSourceStatus::Offline);

    sim.disconnect(4000);
    CHECK(sim.health().status == dashboard::DataSourceStatus::Offline);
}

}  // namespace

int main() {
    parserHandlesFragmentationAndNoise();
    parserRejectsBadChecksumAndResynchronizes();
    adapterDecodesMvpSignals();
    adapterDecodesGearAndConfigurableDoors();
    adapterDoesNotGuessUnconfirmedGearCodes();
    adapterDecodesTiresAndTemperature();
    shortPayloadNeverPublishesInvalidData();
    tickInvalidatesStaleSignalsAndTracksHealth();
    resetClearsStateAndStats();
    frameListenerReceivesParsedFrames();
    simulationAdapterUpdatesAndStales();

    if (failures != 0) {
        std::cerr << failures << " test(s) failed\n";
        return EXIT_FAILURE;
    }
    std::cout << "All dashboard core tests passed\n";
    return EXIT_SUCCESS;
}
