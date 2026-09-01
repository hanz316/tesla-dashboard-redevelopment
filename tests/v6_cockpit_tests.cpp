#include "dashboard/v6_cockpit.h"

#include <cassert>
#include <cstdint>
#include <iostream>

using namespace dashboard;

static void updateDriving(VehicleState& s, std::uint64_t ts, std::uint16_t speed) {
    s.speed.update(speed, ts, SignalSource::Simulation, SignalQuality::Confirmed, Unit::KilometerPerHour);
    s.gear.update(Gear::Drive, ts, SignalSource::Simulation, SignalQuality::Confirmed, Unit::None);
    s.soc.update(68, ts, SignalSource::Simulation, SignalQuality::Confirmed, Unit::Percent);
    s.range.update(284, ts, SignalSource::Simulation, SignalQuality::Confirmed, Unit::Kilometer);
}

int main() {
    {
        Signal<int> s;
        s.update(7, 100, SignalSource::OriginalMcu, SignalQuality::Confirmed, Unit::Raw);
        s.invalidateIfStale(1200, 1000);
        assert(!s.valid);
        assert(s.stale);
        assert(s.source == SignalSource::OriginalMcu);
        assert(!s.unavailable());
    }

    {
        MotionEngine motion(MotionQuality::Full);
        MotionValue v;
        assert(motion.update(v, 10.0F, 16, 120, MotionPriority::Driving) == 10.0F);
        const float next = motion.update(v, 100.0F, 16, 160, MotionPriority::Page);
        assert(next > 10.0F && next < 100.0F);
        assert(motion.update(v, 40.0F, 16, 160, MotionPriority::Critical) == 40.0F);
    }

    {
        AssetManager assets(10U * 1024U * 1024U);
        assets.registerAsset({"shared.vehicle", "assets/v6/shared/model3.png", 2U * 1024U * 1024U, true});
        assets.registerAsset({"horizon.road", "assets/v6/horizon/road.jpg", 4U * 1024U * 1024U, false});
        assert(assets.acquire("shared.vehicle"));
        assert(assets.acquire("horizon.road"));
        assert(assets.estimatedResidentBytes() == 6U * 1024U * 1024U);
        assets.release("horizon.road");
        assert(!assets.isResident("horizon.road"));
        assets.release("shared.vehicle");
        assert(assets.isResident("shared.vehicle"));
    }

    {
        VehicleState s;
        updateDriving(s, 1000, 72);
        s.autopilot_state.update(AutopilotState::Active, 1000, SignalSource::Simulation,
                                 SignalQuality::Confirmed, Unit::None);
        s.front_vehicle_present.update(true, 1000, SignalSource::Simulation,
                                       SignalQuality::Inferred, Unit::None);
        s.surrounding_position_mode.update(SurroundingPositionMode::Coarse, 1000,
                                           SignalSource::Simulation, SignalQuality::Confirmed, Unit::None);
        WarningManager warnings;
        HorizonSceneState scene = buildHorizonScene(s, warnings);
        assert(scene.mode == HorizonMode::ApActive);
        assert(scene.surrounding.front);
        assert(!scene.surrounding.precise_positions_available);
    }

    {
        VehicleState s;
        updateDriving(s, 1000, 20);
        s.door_fl.update(true, 1000, SignalSource::Simulation, SignalQuality::Confirmed, Unit::None);
        WarningManager warnings;
        WarningState w = warnings.evaluate(s);
        assert(w.active);
        assert(w.code == WarningCode::DoorOpenMoving);
        assert(w.severity == WarningSeverity::Warning);
    }

    {
        Signal<std::uint16_t> primary;
        Signal<std::uint16_t> fallback;
        primary.update(70, 1000, SignalSource::OriginalMcu, SignalQuality::Confirmed, Unit::KilometerPerHour);
        fallback.update(71, 1800, SignalSource::Commander, SignalQuality::Confirmed, Unit::KilometerPerHour);
        const auto* chosen = arbitrateSignal(&primary, &fallback, 1900, 500);
        assert(chosen == &fallback);
        primary.update(72, 1900, SignalSource::OriginalMcu, SignalQuality::Confirmed, Unit::KilometerPerHour);
        chosen = arbitrateSignal(&primary, &fallback, 1950, 500);
        assert(chosen == &primary);
    }

    std::cout << "v6 cockpit tests: PASS\n";
    return 0;
}
