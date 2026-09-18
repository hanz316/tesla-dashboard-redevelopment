#include "bench_plan.h"

#include <algorithm>
#include <cmath>
#include <sstream>

namespace dashboard {
namespace bench {
namespace {

AssetRef image(const std::string& id, const std::string& root,
               const std::string& relative) {
    return AssetRef{AssetKind::Image, id, root + "/" + relative, 1, 30, false};
}

AssetRef overlay(const std::string& id, const std::string& root,
                 const std::string& relative) {
    return AssetRef{AssetKind::Overlay, id, root + "/" + relative, 1, 30,
                    false};
}

AssetRef sequence(const std::string& id, const std::string& root,
                  const std::string& directory, std::uint32_t frames,
                  std::uint32_t fps, bool loop) {
    return AssetRef{AssetKind::Sequence, id,
                    root + "/" + directory, frames, fps, loop};
}

std::string quote(const std::string& text) {
    std::string out = "\"";
    for (char c : text) {
        if (c == '"' || c == '\\') out.push_back('\\');
        out.push_back(c);
    }
    out.push_back('"');
    return out;
}

}  // namespace

std::vector<BenchState> benchStates(const std::string& root) {
    const AssetRef base = image("vehicle.base", root, "base/000.png");
    const AssetRef brake = overlay("vehicle.brake", root, "brake_on/000.png");
    const AssetRef headlight =
        overlay("vehicle.headlight", root, "headlight_on/000.png");
    const AssetRef running =
        overlay("vehicle.running", root, "running_on/000.png");
    const AssetRef ind_left =
        sequence("vehicle.indicator.left", root, "indicator_left", 12, 12, true);
    const AssetRef ind_right = sequence("vehicle.indicator.right", root,
                                        "indicator_right", 12, 12, true);
    const AssetRef hazard =
        sequence("vehicle.hazard", root, "hazard", 12, 12, true);
    const AssetRef door_fl =
        sequence("vehicle.door.fl", root, "door_fl", 16, 24, false);
    const AssetRef trunk =
        sequence("vehicle.trunk", root, "trunk", 14, 24, false);
    const AssetRef trunk_left =
        sequence("vehicle.trunk.ind_left", root, "trunk/ind_left", 14, 24,
                 false);
    const AssetRef trunk_right =
        sequence("vehicle.trunk.ind_right", root, "trunk/ind_right", 14, 24,
                 false);

    return {
        {"vehicle_base", "base only", {base}, 1500, false},
        {"brake", "base + brake overlay", {base, brake}, 1500, false},
        {"left_indicator", "base + left indicator loop",
         {base, ind_left}, 3000, true},
        {"right_indicator", "base + right indicator loop",
         {base, ind_right}, 3000, true},
        {"hazard", "base + hazard loop (both sides)", {base, hazard}, 3000,
         true},
        {"headlight", "base + headlight + rear running", {base, headlight,
                                                          running}, 1500, false},
        {"door_fl", "base replaced by the door_fl sequence",
         {door_fl}, 2000, true},
        {"trunk", "base replaced by the trunk sequence", {trunk}, 2000, true},
        {"trunk_indicator_left",
         "trunk moved with its own indicator lighting (TRUNK_MOVING)",
         {trunk_left}, 3000, true},
        {"trunk_indicator_right", "as above, right side",
         {trunk_right}, 3000, true},
        {"max_composition",
         "door sequence + trunk-attached indicator + fixed-body overlays",
         {door_fl, trunk_left, brake, headlight}, 3000, true},
    };
}

std::uint32_t sequenceFrame(const AssetRef& asset, std::uint64_t elapsed_ms) {
    if (asset.frames <= 1) return 0;
    const double fps = asset.fps > 0 ? static_cast<double>(asset.fps) : 30.0;
    std::uint64_t index =
        static_cast<std::uint64_t>((elapsed_ms / 1000.0) * fps);
    if (asset.loop) {
        return static_cast<std::uint32_t>(index % asset.frames);
    }
    const std::uint64_t last = asset.frames - 1;
    return static_cast<std::uint32_t>(std::min(index, last));
}

double FrameTimes::percentile(double fraction) const {
    if (samples_ms.empty()) return 0.0;
    std::vector<double> sorted = samples_ms;
    std::sort(sorted.begin(), sorted.end());
    const double index = fraction * (sorted.size() - 1);
    const std::size_t low = static_cast<std::size_t>(index);
    const std::size_t high = std::min(low + 1, sorted.size() - 1);
    const double weight = index - low;
    return sorted[low] * (1.0 - weight) + sorted[high] * weight;
}

double FrameTimes::mean() const {
    if (samples_ms.empty()) return 0.0;
    double total = 0.0;
    for (double sample : samples_ms) total += sample;
    return total / samples_ms.size();
}

double FrameTimes::max() const {
    if (samples_ms.empty()) return 0.0;
    return *std::max_element(samples_ms.begin(), samples_ms.end());
}

std::size_t FrameTimes::dropped() const {
    std::size_t count = 0;
    for (double sample : samples_ms) {
        if (sample > budget_ms) ++count;
    }
    return count;
}

double FrameTimes::achievedFps() const {
    const double average = mean();
    return average > 0.0 ? 1000.0 / average : 0.0;
}

double FrameTimes::budgetShare() const {
    return budget_ms > 0 ? mean() / budget_ms : 0.0;
}

const char* capabilityName(Capability capability) {
    switch (capability) {
        case Capability::Unsupported: return "UNSUPPORTED";
        case Capability::Supported: return "SUPPORTED";
        case Capability::PartiallySupported: return "PARTIALLY_SUPPORTED";
        case Capability::NotTested: return "NOT_TESTED";
    }
    return "NOT_TESTED";
}

SequenceDecision chooseSequenceMode(
    const std::vector<CapabilityResult>& capabilities) {
    bool variable = false;
    bool fixed_tight = false;
    for (const CapabilityResult& capability : capabilities) {
        if (capability.name == "variable_delta_sequence") {
            variable = capability.result == Capability::Supported;
        }
        if (capability.name == "fixed_tight_sequence") {
            fixed_tight = capability.result == Capability::Supported;
        }
    }
    if (variable) {
        return {"VARIABLE_DELTA",
                "the device reported the variable-delta sequence as "
                "supported, so the efficient path is used"};
    }
    if (fixed_tight) {
        return {"FIXED_TIGHT",
                "variable-delta was not proven on the device; the mandatory "
                "fixed-tight canvas fallback is used"};
    }
    return {"FIXED_TIGHT",
            "neither capability was proven; the conservative fallback is "
            "selected until the device reports otherwise"};
}

std::string renderReportJson(const BenchReport& report) {
    std::ostringstream out;
    out << "{\n";
    out << "  \"schema\": \"t113-vehicle-bench v1\",\n";
    out << "  \"device_model\": " << quote(report.device_model) << ",\n";
    out << "  \"renderer_engine\": " << quote(report.renderer_engine) << ",\n";
    out << "  \"word_size_bits\": " << report.bits << ",\n";
    out << "  \"dev_mode\": " << (report.dev_mode ? "true" : "false") << ",\n";
    out << "  \"note\": " << quote(report.note) << ",\n";
    out << "  \"capabilities\": [\n";
    for (std::size_t i = 0; i < report.capabilities.size(); ++i) {
        const CapabilityResult& capability = report.capabilities[i];
        out << "    {\"name\": " << quote(capability.name)
            << ", \"result\": " << quote(capabilityName(capability.result))
            << ", \"detail\": " << quote(capability.detail) << "}"
            << (i + 1 < report.capabilities.size() ? "," : "") << "\n";
    }
    out << "  ],\n";
    out << "  \"sequence_mode\": {\"mode\": " << quote(report.decision.mode)
        << ", \"reason\": " << quote(report.decision.reason) << "},\n";
    out << "  \"peak_rss_kib\": " << report.peak_rss_kib << ",\n";
    out << "  \"memory_samples\": [\n";
    for (std::size_t i = 0; i < report.memory.size(); ++i) {
        out << "    {\"time_ms\": " << report.memory[i].time_ms
            << ", \"rss_kib\": " << report.memory[i].rss_kib << "}"
            << (i + 1 < report.memory.size() ? "," : "") << "\n";
    }
    out << "  ],\n";
    out << "  \"states\": [\n";
    for (std::size_t i = 0; i < report.states.size(); ++i) {
        const BenchState& state = report.states[i];
        const FrameTimes& frames = report.frames[i];
        out << "    {\"name\": " << quote(state.name)
            << ", \"layers\": " << state.layers.size()
            << ", \"frames\": " << frames.count()
            << ", \"mean_ms\": " << frames.mean()
            << ", \"p50_ms\": " << frames.percentile(0.5)
            << ", \"p95_ms\": " << frames.percentile(0.95)
            << ", \"p99_ms\": " << frames.percentile(0.99)
            << ", \"max_ms\": " << frames.max()
            << ", \"dropped\": " << frames.dropped()
            << ", \"budget_ms\": " << frames.budget_ms
            << ", \"achieved_fps\": " << frames.achievedFps()
            << ", \"budget_share\": " << frames.budgetShare()
            << "}" << (i + 1 < report.states.size() ? "," : "") << "\n";
    }
    out << "  ]\n}\n";
    return out.str();
}

}  // namespace bench
}  // namespace dashboard
