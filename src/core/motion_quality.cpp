#include "dashboard/motion_quality.h"

namespace dashboard {
namespace {

// SAFE is the floor everywhere: it still animates, it just animates the
// cheapest thing the dashboard has (one sequence, 30 fps, 30 Hz UI).
MotionQualityPolicy safePolicy() {
    MotionQualityPolicy policy;
    policy.tier = MotionTier::Safe;
    policy.ui_update_hz = 30;
    policy.vehicle_animation_fps = 30;
    policy.max_simultaneous_sequences = 1;
    policy.engine_quality = MotionQuality::Off;
    policy.evidence_based = false;
    return policy;
}

}  // namespace

const char* motionTierName(MotionTier tier) {
    switch (tier) {
        case MotionTier::Safe:
            return "SAFE";
        case MotionTier::Balanced:
            return "BALANCED";
        case MotionTier::Full:
            return "FULL";
    }
    return "UNKNOWN";
}

MotionQualityPolicy evaluateMotionQuality(const MotionBenchmarkSample& sample,
                                          float frame_budget_ms) {
    // No on-device evidence -> no promotion. This is the branch that runs
    // today: the T113 has not been benchmarked yet, so the answer is SAFE and
    // the dashboard must not claim 60 fps anywhere.
    if (!sample.measured_on_device) {
        return safePolicy();
    }

    MotionQualityPolicy policy = safePolicy();
    policy.evidence_based = true;

    const float budget = frame_budget_ms > 0.0F ? frame_budget_ms : 33.3F;
    const float p99 = sample.p99_frame_ms > 0.0F ? sample.p99_frame_ms
                                                 : sample.avg_frame_ms;

    const bool holds_budget = p99 <= budget;
    const bool no_drops = sample.dropped_frames == 0;

    if (holds_budget && no_drops) {
        policy.tier = MotionTier::Full;
        policy.ui_update_hz = 60;
        policy.vehicle_animation_fps = 60;
        policy.max_simultaneous_sequences = 2;
        policy.engine_quality = MotionQuality::Full;
        return policy;
    }

    // BALANCED: the heavy vehicle sequence is stepped down to 30 fps while the
    // cheap vector/NanoVG layer keeps whatever rate still fits. A dropped
    // frame or two during a transition is tolerated; sustained overrun is not.
    if (p99 <= budget * 1.5F && sample.dropped_frames <= 2) {
        policy.tier = MotionTier::Balanced;
        policy.ui_update_hz = 60;
        policy.vehicle_animation_fps = 30;
        policy.max_simultaneous_sequences = 1;
        policy.engine_quality = MotionQuality::Low;
        return policy;
    }

    return policy;
}

MotionQualityPolicy worstCasePolicy(const MotionQualityPolicy& a,
                                    const MotionQualityPolicy& b) {
    const MotionQualityPolicy& worse = a.tier <= b.tier ? a : b;
    const MotionQualityPolicy& other = a.tier <= b.tier ? b : a;
    MotionQualityPolicy merged = worse;
    merged.ui_update_hz = worse.ui_update_hz < other.ui_update_hz
                              ? worse.ui_update_hz
                              : other.ui_update_hz;
    merged.vehicle_animation_fps =
        worse.vehicle_animation_fps < other.vehicle_animation_fps
            ? worse.vehicle_animation_fps
            : other.vehicle_animation_fps;
    merged.max_simultaneous_sequences =
        worse.max_simultaneous_sequences < other.max_simultaneous_sequences
            ? worse.max_simultaneous_sequences
            : other.max_simultaneous_sequences;
    merged.evidence_based = a.evidence_based && b.evidence_based;
    return merged;
}

}  // namespace dashboard
