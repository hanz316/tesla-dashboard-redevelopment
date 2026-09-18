#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace dashboard {
namespace bench {

// The device benchmark exercises the production rendering path with the real
// assets. This part is platform independent on purpose: it decides which
// assets a state needs, how a sequence advances, what counts as a dropped
// frame and what the report says - all of which can be verified on the host
// before the T113 is ever connected. Only the EasyUI/decoder calls live in
// bench_device.cpp.

enum class AssetKind : std::uint8_t { Image, Overlay, Sequence };

struct AssetRef {
    AssetKind kind{AssetKind::Image};
    std::string id;         // manifest asset id, e.g. "vehicle.base"
    std::string path;       // path under the deployed asset root
    std::uint32_t frames{1};
    std::uint32_t fps{30};
    bool loop{false};
};

struct BenchState {
    std::string name;                 // report name, e.g. "trunk_indicator_left"
    std::string description;
    std::vector<AssetRef> layers;     // draw order, base first
    std::uint32_t hold_ms{1500};      // how long to sustain the state
    bool plays_sequence{false};
};

// Every state the handoff requires, in draw order.
std::vector<BenchState> benchStates(const std::string& asset_root);

// Which frame a running sequence shows at a given time.
std::uint32_t sequenceFrame(const AssetRef& asset, std::uint64_t elapsed_ms);

struct FrameTimes {
    std::vector<double> samples_ms;
    std::uint64_t budget_ms{33};      // 30 fps

    void add(double frame_ms) { samples_ms.push_back(frame_ms); }
    std::size_t count() const { return samples_ms.size(); }
    double percentile(double fraction) const;
    double mean() const;
    double max() const;
    std::size_t dropped() const;      // frames over the budget
    double achievedFps() const;
    double budgetShare() const;       // mean frame time / budget
};

struct MemorySample {
    std::uint64_t time_ms{0};
    std::uint64_t rss_kib{0};
};

enum class Capability : std::uint8_t {
    Unsupported = 0,
    Supported,
    PartiallySupported,
    NotTested,
};

const char* capabilityName(Capability capability);

struct CapabilityResult {
    std::string name;                 // "variable_frame_size", ...
    Capability result{Capability::NotTested};
    std::string detail;
};

struct SequenceDecision {
    std::string mode;                 // "VARIABLE_DELTA" or "FIXED_TIGHT"
    std::string reason;
};

// The production rule: prefer variable delta only when the device proved it.
SequenceDecision chooseSequenceMode(
    const std::vector<CapabilityResult>& capabilities);

struct BenchReport {
    std::string device_model;
    std::string renderer_engine;
    std::uint64_t bits{0};            // uname -m style word size evidence
    std::vector<CapabilityResult> capabilities;
    SequenceDecision decision;
    std::vector<BenchState> states;
    std::vector<FrameTimes> frames;
    std::vector<MemorySample> memory;
    std::uint64_t peak_rss_kib{0};
    bool dev_mode{true};              // benchmark injects state, never live data
    std::string note;
};

std::string renderReportJson(const BenchReport& report);

}  // namespace bench
}  // namespace dashboard
