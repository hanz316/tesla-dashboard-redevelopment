#pragma once

#include <cstdint>

#include "dashboard/v6_cockpit.h"

namespace dashboard {

// Task Part P: MotionQualityManager.
//
// Contract and policy only. This header deliberately does NOT touch the
// runtime: MotionEngine / HorizonRendererV6 keep using the existing
// MotionQuality{Off,Low,Full} enum. What is new here is the missing piece
// above them - deciding which tier the device is actually allowed to run.
//
// Hard rule: FULL is never inferred from the SoC, from the datasheet, or
// from a host-Mac measurement. It is only ever granted from a sample that was
// measured on the real T113 unit. Everything else is UNKNOWN UNTIL DEVICE
// TEST and therefore runs SAFE.
enum class MotionTier : std::uint8_t {
    Safe = 0,
    Balanced,
    Full,
};

const char* motionTierName(MotionTier tier);

// One row of the benchmark matrix in docs/ANIMATION_PERFORMANCE_TEST_PLAN.md.
struct MotionBenchmarkSample {
    std::uint32_t vehicle_width_px{0};
    std::uint32_t animation_fps{0};
    float observed_fps{0.0F};
    float avg_frame_ms{0.0F};
    float p95_frame_ms{0.0F};
    float p99_frame_ms{0.0F};
    std::uint32_t dropped_frames{0};
    float decode_ms{0.0F};
    float composite_ms{0.0F};
    // False for host-Mac numbers and for anything copied out of a datasheet.
    bool measured_on_device{false};
};

struct MotionQualityPolicy {
    MotionTier tier{MotionTier::Safe};
    // Rate the lightweight NanoVG/vector layer may run at.
    std::uint32_t ui_update_hz{30};
    // Rate the pre-rendered vehicle frame sequences may run at.
    std::uint32_t vehicle_animation_fps{30};
    // How many PNG sequences may decode at the same time.
    std::uint32_t max_simultaneous_sequences{1};
    // Fallback for code that still takes the legacy three-state enum.
    MotionQuality engine_quality{MotionQuality::Full};
    bool evidence_based{false};
};

// Grades one measured sample. `frame_budget_ms` is the per-frame budget at the
// target rate (33.3 ms for 30 fps, 16.6 ms for 60 fps).
MotionQualityPolicy evaluateMotionQuality(const MotionBenchmarkSample& sample,
                                          float frame_budget_ms = 33.3F);

// Worst-case combination helper: the device runs one tier for everything, so
// a single sample that fails must be able to pull the whole policy down.
MotionQualityPolicy worstCasePolicy(const MotionQualityPolicy& a,
                                    const MotionQualityPolicy& b);

}  // namespace dashboard
