#include "dashboard/motion_quality.h"

// Keep the assertions live even in a Release build (NDEBUG).
#undef NDEBUG
#include <cassert>
#include <iostream>

using namespace dashboard;

int main() {
    // Host-Mac numbers and datasheet numbers must never promote the device.
    // This is the state the project is actually in today.
    {
        MotionBenchmarkSample host;
        host.vehicle_width_px = 600;
        host.animation_fps = 60;
        host.observed_fps = 60.0F;
        host.avg_frame_ms = 4.0F;
        host.p99_frame_ms = 6.0F;
        host.measured_on_device = false;

        const MotionQualityPolicy policy = evaluateMotionQuality(host);
        assert(policy.tier == MotionTier::Safe);
        assert(policy.vehicle_animation_fps == 30);
        assert(!policy.evidence_based);
        std::cout << "host-mac sample -> " << motionTierName(policy.tier)
                  << " (not promoted)\n";
    }

    // A real device sample that holds a 30 fps budget with no drops may run
    // the full tier, including 60 Hz UI.
    {
        MotionBenchmarkSample device;
        device.vehicle_width_px = 600;
        device.animation_fps = 30;
        device.observed_fps = 30.0F;
        device.avg_frame_ms = 21.0F;
        device.p95_frame_ms = 28.0F;
        device.p99_frame_ms = 31.0F;
        device.decode_ms = 10.0F;
        device.composite_ms = 8.0F;
        device.dropped_frames = 0;
        device.measured_on_device = true;

        const MotionQualityPolicy policy = evaluateMotionQuality(device, 33.3F);
        assert(policy.tier == MotionTier::Full);
        assert(policy.ui_update_hz == 60);
        assert(policy.vehicle_animation_fps == 60);
        assert(policy.engine_quality == MotionQuality::Full);
        std::cout << "healthy device sample -> " << motionTierName(policy.tier)
                  << "\n";
    }

    // Slight overrun: the heavy sequence drops to 30 fps, the cheap vector
    // layer is still allowed to run fast.
    {
        MotionBenchmarkSample device;
        device.measured_on_device = true;
        device.p99_frame_ms = 44.0F;
        device.dropped_frames = 1;

        const MotionQualityPolicy policy = evaluateMotionQuality(device, 33.3F);
        assert(policy.tier == MotionTier::Balanced);
        assert(policy.ui_update_hz == 60);
        assert(policy.vehicle_animation_fps == 30);
        assert(policy.engine_quality == MotionQuality::Low);
        std::cout << "borderline device sample -> "
                  << motionTierName(policy.tier) << "\n";
    }

    // Sustained overrun keeps SAFE and shuts the legacy motion engine off.
    {
        MotionBenchmarkSample device;
        device.measured_on_device = true;
        device.p99_frame_ms = 78.0F;
        device.dropped_frames = 9;

        const MotionQualityPolicy policy = evaluateMotionQuality(device, 33.3F);
        assert(policy.tier == MotionTier::Safe);
        assert(policy.engine_quality == MotionQuality::Off);
        std::cout << "overrun device sample -> " << motionTierName(policy.tier)
                  << "\n";
    }

    // One bad cell in the matrix has to be able to pull the whole policy down.
    {
        MotionBenchmarkSample good;
        good.measured_on_device = true;
        good.p99_frame_ms = 20.0F;
        MotionBenchmarkSample bad;
        bad.measured_on_device = true;
        bad.p99_frame_ms = 90.0F;
        bad.dropped_frames = 5;

        const MotionQualityPolicy merged = worstCasePolicy(
            evaluateMotionQuality(good, 33.3F),
            evaluateMotionQuality(bad, 33.3F));
        assert(merged.tier == MotionTier::Safe);
        assert(merged.vehicle_animation_fps == 30);
        std::cout << "worst-case merge -> " << motionTierName(merged.tier)
                  << "\n";
    }

    std::cout << "motion_quality_tests OK\n";
    return 0;
}
