#include "device_runtime.h"

// Keep the assertions live even in a Release build (NDEBUG).
#undef NDEBUG
#include <cassert>
#include <iostream>
#include <string>

// The device builds its own view of the world from the runtime snapshot. That
// mapping is what the nine screens read on the panel, so it is checked here on
// the host, with no EasyUI and no instrument attached.
//
// device_runtime.cpp is compiled into this test on purpose: it is the same
// file the T113 build uses.

using namespace dashboard;
using namespace dashboard::flythings;

namespace {

RuntimeSnapshot healthySnapshot() {
    RuntimeSnapshot snapshot;
    snapshot.uart_connected = true;
    snapshot.uart_receiving = true;
    snapshot.parser.valid_packets = 2637;
    snapshot.parser.checksum_errors = 0;
    snapshot.adapter.unknown_commands = 3;
    return snapshot;
}

std::string textOf(const PageProjectionV6& page, const char* name,
                   const char* format, const char* invalid) {
    const auto it = page.find(name);
    assert(it != page.end());
    return formatSceneTextV6(format, it->second, invalid);
}

}  // namespace

int main() {
    // A receiving link is "UART OK"; a silent one is stale, and a closed one
    // is lost. Three different screens, never the same picture.
    {
        RuntimeSnapshot snapshot = healthySnapshot();
        PageEnvironmentV6 environment = buildDevicePageEnvironment(snapshot);
        assert(environment.uart_connected && environment.uart_receiving);
        PageProjectionV6 page = buildPageProjectionV6(
            DashboardPageV6::Horizon, snapshot.state, ProductStateV6{},
            DashboardSettings{}, environment);
        assert(textOf(page, "uart_health", "{}", "?") == "UART OK");

        snapshot.uart_receiving = false;
        environment = buildDevicePageEnvironment(snapshot);
        page = buildPageProjectionV6(DashboardPageV6::Horizon, snapshot.state,
                                     ProductStateV6{}, DashboardSettings{},
                                     environment);
        assert(textOf(page, "uart_health", "{}", "?") == "UART STALE");

        snapshot.uart_connected = false;
        environment = buildDevicePageEnvironment(snapshot);
        page = buildPageProjectionV6(DashboardPageV6::Horizon, snapshot.state,
                                     ProductStateV6{}, DashboardSettings{},
                                     environment);
        assert(textOf(page, "uart_health", "{}", "?") == "UART LOST");
        std::cout << "the device reports the vehicle link as it really is\n";
    }

    // The Developer screen gets the real counters, not placeholders.
    {
        const RuntimeSnapshot snapshot = healthySnapshot();
        const PageEnvironmentV6 environment = buildDevicePageEnvironment(snapshot);
        const PageProjectionV6 page = buildPageProjectionV6(
            DashboardPageV6::Developer, snapshot.state, ProductStateV6{},
            DashboardSettings{}, environment);
        const std::string parser = textOf(page, "dev_parser", "{}", "PARSER --");
        assert(parser.find("2637 frames") == 0);
        assert(parser.find("3 unknown cmds") != std::string::npos);
        // Frame timing is not wired to a render backend yet, so that line must
        // still be its placeholder rather than a made-up number.
        assert(textOf(page, "dev_frame", "{}", "FRAME --") == "FRAME --");
        std::cout << "the developer screen shows real counters and no invented "
                     "frame timing\n";
    }

    // The enhanced link is disabled in this build: a transport thread has not
    // opened one, so the badge shows its placeholder rather than "CMDR".
    {
        const RuntimeSnapshot snapshot = healthySnapshot();
        assert(snapshot.commander_status == CommanderLinkStatus::Disabled);
        const PageEnvironmentV6 environment = buildDevicePageEnvironment(snapshot);
        const PageProjectionV6 page = buildPageProjectionV6(
            DashboardPageV6::Energy, snapshot.state, ProductStateV6{},
            DashboardSettings{}, environment);
        const auto link = page.find("commander_link");
        assert(link != page.end());
        assert(!link->second.valid);
        assert(textOf(page, "commander_link", "{}", "CMDR --") == "CMDR --");
        // And with no Commander there is no SOC: the MCU byte may not stand in.
        assert(!page.at("actual_soc").valid);
        std::cout << "an absent Commander shows as absent, not as a value\n";
    }

    // A Commander that is linked supplies SOC and power; the MCU readings are
    // untouched by the merge.
    {
        RuntimeSnapshot snapshot = healthySnapshot();
        snapshot.commander_status = CommanderLinkStatus::Linked;
        snapshot.commander_module_info_known = true;
        snapshot.commander_version = CommanderModuleVersion{1, 2, 0};
        snapshot.commander_detail = "NativeBle · v1.2.0";
        snapshot.state.speed.update(88, 1000, SignalSource::OriginalMcu,
                                    SignalQuality::Confirmed,
                                    Unit::KilometerPerHour);
        snapshot.state.soc.update(97, 1000, SignalSource::OriginalMcu,
                                  SignalQuality::Estimated, Unit::Percent);
        snapshot.commander_state.actual_soc.update(63, 1000,
                                                   SignalSource::Commander,
                                                   SignalQuality::Confirmed,
                                                   Unit::Percent);
        snapshot.commander_state.speed.update(250, 1000, SignalSource::Commander,
                                              SignalQuality::Confirmed,
                                              Unit::KilometerPerHour);

        VehicleState merged = snapshot.state;
        mergeCommanderInto(merged, snapshot.commander_state);
        assert(merged.speed.value == 88);      // the car's own reading wins
        assert(merged.actual_soc.value == 63); // the enhanced value lands

        const PageEnvironmentV6 environment = buildDevicePageEnvironment(snapshot);
        const PageProjectionV6 page = buildPageProjectionV6(
            DashboardPageV6::Energy, merged, ProductStateV6{},
            DashboardSettings{}, environment);
        assert(textOf(page, "actual_soc", "{}%", "-- %") == "63%");
        const PageProjectionV6 horizon = buildPageProjectionV6(
            DashboardPageV6::Horizon, merged, ProductStateV6{},
            DashboardSettings{}, environment);
        assert(textOf(horizon, "speed", "{}", "--") == "88");
        std::cout << "a linked Commander supplies SOC and cannot rewrite speed\n";
    }

    std::cout << "all device environment checks passed\n";
    return 0;
}
