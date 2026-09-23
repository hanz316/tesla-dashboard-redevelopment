#include "dashboard/dashboard_services.h"

#include <cassert>
#include <cmath>
#include <iostream>

using namespace dashboard;

static void setSpeed(VehicleState& state, std::uint16_t speed, std::uint64_t timestamp_ms) {
    state.speed.update(speed, timestamp_ms, SignalSource::Simulation,
                       SignalQuality::Confirmed, Unit::KilometerPerHour);
}

int main() {
    {
        VehicleState state;
        state.soc.update(80, 0, SignalSource::Simulation, SignalQuality::Confirmed, Unit::Percent);
        setSpeed(state, 0, 1000);
        TripComputer trip;
        trip.reset(TripSlot::CurrentDrive, 1000, state);
        setSpeed(state, 60, 61000);
        state.soc.update(79, 61000, SignalSource::Simulation, SignalQuality::Confirmed, Unit::Percent);
        trip.update(61000, state);
        const TripSummary& s = trip.summary(TripSlot::CurrentDrive);
        assert(s.valid);
        assert(std::fabs(s.distance_km - 0.5F) < 0.02F); // trapezoidal integration 0->60 over 60 s
        assert(s.duration_ms == 60000);
        assert(s.soc_used_valid && s.soc_used == 1);
        assert(s.max_speed_kph == 60.0F);
    }

    {
        VehicleState state;
        TripComputer trip;
        setSpeed(state, 100, 1000);
        trip.reset(TripSlot::TripA, 1000, state);
        state.speed.markStale(3000);
        trip.update(3000, state);
        assert(trip.summary(TripSlot::TripA).distance_km == 0.0F);
    }

    {
        // The MCU's SOC byte is a rejected mapping; it may not become a
        // "percent used" readout on a trip.
        VehicleState state;
        state.soc.update(97, 0, SignalSource::OriginalMcu,
                         SignalQuality::Estimated, Unit::Percent);
        setSpeed(state, 0, 1000);
        TripComputer trip;
        trip.reset(TripSlot::CurrentDrive, 1000, state);
        setSpeed(state, 60, 61000);
        trip.update(61000, state);
        const TripSummary& rejected = trip.summary(TripSlot::CurrentDrive);
        assert(!rejected.soc_start_valid);
        assert(!rejected.soc_used_valid);
        assert(std::fabs(rejected.distance_km - 0.5F) < 0.02F);  // distance still works

        // With the Commander's actual_soc the accounting is real again.
        state.actual_soc.update(63, 61000, SignalSource::Commander,
                                SignalQuality::Confirmed, Unit::Percent);
        trip.update(121000, state);
        const TripSummary& trusted = trip.summary(TripSlot::CurrentDrive);
        assert(trusted.soc_current_valid && trusted.soc_current == 63);
        // The start of this trip was never known (the only SOC at reset was the
        // rejected byte), so "percent used" stays unavailable rather than
        // being computed against a guess.
        assert(!trusted.soc_used_valid);
    }

    {
        PerformanceTimer timer;
        timer.configure(PerformancePreset::ZeroTo100);
        timer.arm();
        Signal<std::uint16_t> speed;
        speed.update(0, 1000, SignalSource::Simulation, SignalQuality::Confirmed, Unit::KilometerPerHour);
        timer.update(speed);
        speed.update(20, 1200, SignalSource::Simulation, SignalQuality::Confirmed, Unit::KilometerPerHour);
        timer.update(speed);
        assert(timer.result().state == PerformanceTimerState::Running);
        speed.update(80, 2000, SignalSource::Simulation, SignalQuality::Confirmed, Unit::KilometerPerHour);
        timer.update(speed);
        speed.update(120, 2400, SignalSource::Simulation, SignalQuality::Confirmed, Unit::KilometerPerHour);
        timer.update(speed);
        assert(timer.result().state == PerformanceTimerState::Finished);
        assert(timer.result().start_timestamp_ms == 1000);
        assert(timer.result().finish_timestamp_ms == 2200); // 80->120, crossing 100 halfway
        assert(timer.result().elapsed_ms == 1200);
    }

    {
        PerformanceTimer timer;
        timer.configure(PerformancePreset::EightyTo120);
        timer.arm();
        Signal<std::uint16_t> speed;
        speed.update(70, 1000, SignalSource::Replay, SignalQuality::Confirmed, Unit::KilometerPerHour);
        timer.update(speed);
        speed.update(90, 1200, SignalSource::Replay, SignalQuality::Confirmed, Unit::KilometerPerHour);
        timer.update(speed);
        assert(timer.result().state == PerformanceTimerState::Running);
        speed.markStale(2500);
        timer.update(speed);
        assert(timer.result().state == PerformanceTimerState::Invalid);
    }

    {
        PerformanceTimer timer;
        timer.configure(PerformancePreset::Custom, {100.0F, 50.0F});
        timer.arm();
        assert(timer.result().state == PerformanceTimerState::Invalid);
    }

    std::cout << "dashboard services tests: PASS\n";
    return 0;
}
