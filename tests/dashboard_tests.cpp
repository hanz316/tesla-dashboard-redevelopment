#include "dashboard/original_mcu_adapter.h"

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
    CHECK(state.distance_raw.valid && state.distance_raw.value == 0x123456);
    CHECK(state.speed.timestamp_ms == 4242);
    CHECK(state.speed.source == dashboard::SignalSource::OriginalMcu);
}

void adapterDecodesGearAndConfigurableDoors() {
    dashboard::OriginalMcuAdapter adapter;
    const auto frame = makeFrame(0x01, {0, 0, 0, 0x35, 0x30});
    adapter.feed(frame.data(), frame.size(), 5000);
    const auto& state = adapter.state();
    CHECK(state.gear.value == dashboard::Gear::Drive);
    CHECK(state.door_fl.value);
    CHECK(state.door_fr.value);
    CHECK(!state.door_rl.value);
    CHECK(!state.door_rr.value);
    CHECK(state.frunk.value);
    CHECK(state.trunk.value);
    CHECK(state.door_fl.quality == dashboard::SignalQuality::Inferred);
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

}  // namespace

int main() {
    parserHandlesFragmentationAndNoise();
    parserRejectsBadChecksumAndResynchronizes();
    adapterDecodesMvpSignals();
    adapterDecodesGearAndConfigurableDoors();
    adapterDecodesTiresAndTemperature();
    shortPayloadNeverPublishesInvalidData();

    if (failures != 0) {
        std::cerr << failures << " test(s) failed\n";
        return EXIT_FAILURE;
    }
    std::cout << "All dashboard core tests passed\n";
    return EXIT_SUCCESS;
}
