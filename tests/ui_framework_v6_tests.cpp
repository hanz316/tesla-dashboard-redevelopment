#include "dashboard/horizon_v6.h"
#include "dashboard/ui_framework_v6.h"

#include <algorithm>
#include <cassert>
#include <iostream>

using namespace dashboard;

static void setDriving(VehicleState& state, std::uint64_t timestamp_ms, std::uint16_t speed = 72) {
    state.speed.update(speed, timestamp_ms, SignalSource::Simulation,
                       SignalQuality::Confirmed, Unit::KilometerPerHour);
    state.gear.update(Gear::Drive, timestamp_ms, SignalSource::Simulation,
                      SignalQuality::Confirmed, Unit::None);
    state.soc.update(68, timestamp_ms, SignalSource::Simulation,
                     SignalQuality::Confirmed, Unit::Percent);
    state.range.update(284, timestamp_ms, SignalSource::Simulation,
                       SignalQuality::Confirmed, Unit::Kilometer);
}

static bool hasCommand(const RenderFrameV6& frame, const char* id) {
    return std::any_of(frame.commands.begin(), frame.commands.end(),
                       [id](const RenderCommand& c) { return c.id == id; });
}

int main() {
    WarningManager warnings;

    {
        PageManagerV6 pages;
        pages.request(DashboardPageV6::Pulse);
        pages.update(100, MotionQuality::Full);
        assert(pages.state().active);
        assert(pages.state().progress > 0.0F && pages.state().progress < 1.0F);
        pages.request(DashboardPageV6::Developer, true);
        assert(!pages.state().active);
        assert(pages.current() == DashboardPageV6::Developer);
    }

    {
        VehicleState state;
        setDriving(state, 1000);
        SafetyLayerV6 safety = buildSafetyLayerV6(state, warnings);
        assert(safety.speed_available);
        assert(safety.gear_available);
        assert(safety.soc_available);
        assert(safety.availability == DataAvailabilityLevel::EnhancedModuleUnavailable);
    }

    {
        VehicleState state;
        setDriving(state, 1000);
        state.soc.quality = SignalQuality::Estimated;
        SafetyLayerV6 safety = buildSafetyLayerV6(state, warnings);
        assert(!safety.soc_available); // known-untrusted Original MCU SOC semantics
        assert(safety.availability == DataAvailabilityLevel::IndividualSignalUnavailable);
    }

    {
        VehicleState state;
        setDriving(state, 1000);
        state.autopilot_state.update(AutopilotState::Active, 1000, SignalSource::Simulation,
                                     SignalQuality::Confirmed, Unit::None);
        state.front_vehicle_present.update(true, 1000, SignalSource::Simulation,
                                           SignalQuality::Inferred, Unit::None);
        state.surrounding_position_mode.update(SurroundingPositionMode::Coarse, 1000,
                                               SignalSource::Simulation,
                                               SignalQuality::Confirmed, Unit::None);
        ProductStateV6 product;
        HorizonRendererV6 renderer(MotionQuality::Full);
        RenderFrameV6 frame = renderer.buildFrame({&state, &product, 33, false, false});
        assert(frame.width == 1920 && frame.height == 480);
        assert(frame.safe_top_corner_cut == 116);
        assert(frame.safe_bottom_corner_cut == 51);
        assert(hasCommand(frame, "horizon.background"));
        assert(hasCommand(frame, "horizon.road"));
        assert(hasCommand(frame, "vehicle.body"));
        assert(hasCommand(frame, "horizon.surround.front"));
        assert(hasCommand(frame, "speed.value"));
        assert(!hasCommand(frame, "dev.simulation"));
    }

    {
        VehicleState state;
        setDriving(state, 1000);
        ProductStateV6 product;
        product.navigation.available = true;
        product.navigation.active = true;
        product.navigation.capabilities = BasicManeuver | TripMetrics;
        product.navigation.next_turn_distance_m.update(800.0F, 1000, SignalSource::PhoneBridge,
                                                        SignalQuality::Confirmed, Unit::Raw);
        product.navigation.remaining_time_s.update(1320, 1000, SignalSource::PhoneBridge,
                                                   SignalQuality::Confirmed, Unit::Raw);
        product.navigation.remaining_distance_km.update(18.4F, 1000, SignalSource::PhoneBridge,
                                                        SignalQuality::Confirmed, Unit::Kilometer);
        product.navigation.road_name = "VERY LONG STREET NAME";
        HorizonRendererV6 renderer;
        RenderFrameV6 frame = renderer.buildFrame({&state, &product, 33, false, false});
        assert(hasCommand(frame, "context.nav.distance"));
        assert(hasCommand(frame, "context.nav.road"));
        assert(hasCommand(frame, "context.nav.time"));
    }

    {
        VehicleState state;
        setDriving(state, 1000, 20);
        state.door_fl.update(true, 1000, SignalSource::Simulation,
                             SignalQuality::Confirmed, Unit::None);
        ProductStateV6 product;
        HorizonRendererV6 renderer;
        RenderFrameV6 frame = renderer.buildFrame({&state, &product, 33, false, false});
        assert(hasCommand(frame, "vehicle.door_fl"));
        assert(hasCommand(frame, "warning.strip"));
        assert(hasCommand(frame, "warning.label"));
    }

    {
        VehicleState state;
        setDriving(state, 1000);
        state.speed.markStale(2500);
        ProductStateV6 product;
        HorizonRendererV6 renderer;
        RenderFrameV6 frame = renderer.buildFrame({&state, &product, 33, false, false});
        assert(hasCommand(frame, "warning.critical.backdrop"));
        assert(hasCommand(frame, "warning.critical.title"));
    }

    {
        VehicleState state;
        setDriving(state, 1000);
        ProductStateV6 product;
        HorizonRendererV6 renderer;
        RenderFrameV6 frame = renderer.buildFrame({&state, &product, 33, true, true});
        assert(hasCommand(frame, "dev.simulation"));
    }

    std::cout << "ui framework v6 tests: PASS\n";
    return 0;
}
