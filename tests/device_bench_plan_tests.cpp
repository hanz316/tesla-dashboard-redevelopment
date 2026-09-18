#include "bench_plan.h"

// Keep the assertions live even in a Release build (NDEBUG).
#undef NDEBUG
#include <cassert>
#include <iostream>

using namespace dashboard::bench;

int main() {
    // The benchmark must cover exactly the states the handoff requires.
    const auto states = benchStates("/data/vehicle-bench/assets");
    const char* required[] = {"vehicle_base", "brake", "left_indicator",
                              "right_indicator", "hazard", "headlight",
                              "door_fl", "trunk", "trunk_indicator_left",
                              "trunk_indicator_right", "max_composition"};
    for (const char* name : required) {
        bool found = false;
        for (const BenchState& state : states) {
            if (state.name == name) found = true;
        }
        assert(found);
    }
    assert(states.size() == sizeof(required) / sizeof(required[0]));

    // Sequence playback: loops wrap, to_state sequences hold the last frame.
    const AssetRef loop{AssetKind::Sequence, "loop", "p", 12, 12, true};
    assert(sequenceFrame(loop, 0) == 0);
    assert(sequenceFrame(loop, 1000 / 12 + 1) == 1);
    assert(sequenceFrame(loop, 1000) == 0);          // wrapped at 12 fps
    const AssetRef once{AssetKind::Sequence, "once", "p", 16, 24, false};
    assert(sequenceFrame(once, 0) == 0);
    assert(sequenceFrame(once, 1000 / 24 + 1) == 1);
    assert(sequenceFrame(once, 100000) == 15);       // terminal state

    // Timing statistics and the 30 fps budget rule.
    FrameTimes times;
    for (int i = 0; i < 30; ++i) times.add(i < 28 ? 20.0 : 40.0);
    assert(times.count() == 30);
    assert(times.mean() > 21.0 && times.mean() < 22.0);
    assert(times.dropped() == 2);
    assert(times.percentile(0.5) == 20.0);
    assert(times.max() == 40.0);
    assert(times.achievedFps() > 45.0);
    assert(times.budgetShare() > 0.6 && times.budgetShare() < 0.7);

    // The fallback decision: variable delta only when the device proved it.
    std::vector<CapabilityResult> unproven = {
        {"variable_delta_sequence", Capability::Unsupported, "no symbols"},
        {"fixed_tight_sequence", Capability::Supported, "works"},
    };
    assert(chooseSequenceMode(unproven).mode == "FIXED_TIGHT");
    std::vector<CapabilityResult> proven = {
        {"variable_delta_sequence", Capability::Supported, "verified"},
        {"fixed_tight_sequence", Capability::Supported, "works"},
    };
    assert(chooseSequenceMode(proven).mode == "VARIABLE_DELTA");
    std::vector<CapabilityResult> nothing = {
        {"variable_delta_sequence", Capability::NotTested, ""},
        {"fixed_tight_sequence", Capability::NotTested, ""},
    };
    assert(chooseSequenceMode(nothing).mode == "FIXED_TIGHT");
    std::cout << "sequence mode rule: unproven -> FIXED_TIGHT, proven -> "
                 "VARIABLE_DELTA\n";

    // The report must be machine readable, must state that the state injection
    // is DEV/REPLAY, and must not claim an untested capability.
    BenchReport report;
    report.device_model = "Zkswe_T113_SPINOR";
    report.renderer_engine = "libeasyui";
    report.bits = 32;
    report.capabilities = unproven;
    report.decision = chooseSequenceMode(unproven);
    report.states = states;
    report.frames.resize(states.size());
    for (FrameTimes& f : report.frames) {
        f.budget_ms = 33;
        f.add(18.0);
        f.add(22.0);
    }
    report.memory = {{0, 40960}, {1000, 41200}};
    report.peak_rss_kib = 41200;
    report.note = "DEV/REPLAY state injection; no live vehicle data";
    const std::string json = renderReportJson(report);
    assert(json.find("\"schema\": \"t113-vehicle-bench v1\"") !=
           std::string::npos);
    assert(json.find("\"sequence_mode\": {\"mode\": \"FIXED_TIGHT\"") !=
           std::string::npos);
    assert(json.find("\"dev_mode\": true") != std::string::npos);
    assert(json.find("\"peak_rss_kib\": 41200") != std::string::npos);
    assert(json.find("\"name\": \"max_composition\"") != std::string::npos);
    assert(json.find("NOT_TESTED") == std::string::npos);
    std::cout << "device bench plan checks passed\n";
    return 0;
}
