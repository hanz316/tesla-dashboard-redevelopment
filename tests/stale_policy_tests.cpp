#include "dashboard/stale_policy.h"

#include <cstdlib>
#include <iostream>

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

void domainsExpireIndependently() {
    dashboard::VehicleState state;
    const auto source = dashboard::SignalSource::OriginalMcu;
    const auto quality = dashboard::SignalQuality::Confirmed;

    state.speed.update(
        88, 1000, source, quality, dashboard::Unit::KilometerPerHour);
    state.gear.update(
        dashboard::Gear::Drive, 1000, source, quality, dashboard::Unit::None);
    state.door_fl.update(
        false, 1000, source, quality, dashboard::Unit::None);
    state.soc.update(
        75, 1000, source, quality, dashboard::Unit::Percent);
    state.tire_fl.update(
        2.70F, 1000, source, quality, dashboard::Unit::Bar);

    auto summary = dashboard::invalidateStale(state, 2601);
    CHECK(summary.expired_signals == 2);
    CHECK(!state.speed.valid);
    CHECK(!state.gear.valid);
    CHECK(state.door_fl.valid);
    CHECK(state.soc.valid);
    CHECK(state.tire_fl.valid);

    summary = dashboard::invalidateStale(state, 3601);
    CHECK(summary.expired_signals == 1);
    CHECK(!state.door_fl.valid);
    CHECK(state.soc.valid);

    summary = dashboard::invalidateStale(state, 6001);
    CHECK(summary.expired_signals == 1);
    CHECK(!state.soc.valid);
    CHECK(state.tire_fl.valid);
}

void expirationPreservesDiagnostics() {
    dashboard::VehicleState state;
    state.speed.update(
        42,
        1234,
        dashboard::SignalSource::OriginalMcu,
        dashboard::SignalQuality::Confirmed,
        dashboard::Unit::KilometerPerHour);

    const auto summary = dashboard::invalidateStale(state, 4000);
    CHECK(summary.anyExpired());
    CHECK(!state.speed.valid);
    CHECK(state.speed.timestamp_ms == 1234);
    CHECK(state.speed.source == dashboard::SignalSource::OriginalMcu);
    CHECK(state.speed.quality == dashboard::SignalQuality::Confirmed);
    CHECK(state.speed.unit == dashboard::Unit::KilometerPerHour);
}

void clockRegressionDoesNotExpire() {
    dashboard::VehicleState state;
    state.speed.update(
        42,
        5000,
        dashboard::SignalSource::OriginalMcu,
        dashboard::SignalQuality::Confirmed,
        dashboard::Unit::KilometerPerHour);

    const auto summary = dashboard::invalidateStale(state, 4999);
    CHECK(!summary.anyExpired());
    CHECK(state.speed.valid);
}

}  // namespace

int main() {
    domainsExpireIndependently();
    expirationPreservesDiagnostics();
    clockRegressionDoesNotExpire();

    if (failures != 0) {
        std::cerr << failures << " test(s) failed\n";
        return EXIT_FAILURE;
    }
    std::cout << "All stale policy tests passed\n";
    return EXIT_SUCCESS;
}
