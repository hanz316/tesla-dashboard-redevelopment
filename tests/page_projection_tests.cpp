#include "dashboard/page_projection_v6.h"

// Keep the assertions live even in a Release build (NDEBUG).
#undef NDEBUG
#include <algorithm>
#include <cassert>
#include <cmath>
#include <iostream>
#include <set>
#include <string>
#include <vector>

using namespace dashboard;

namespace {

constexpr std::uint64_t kNow = 1'000'000;

template <typename T>
Signal<T> fresh(T value) {
    Signal<T> signal;
    signal.update(value, kNow, SignalSource::OriginalMcu,
                  SignalQuality::Confirmed, Unit::None);
    return signal;
}

VehicleState mcuState() {
    VehicleState state;
    state.speed = fresh<std::uint16_t>(88);
    state.range = fresh<std::uint16_t>(253);
    state.gear = fresh<Gear>(Gear::Drive);
    state.door_fl = fresh<bool>(false);
    state.door_fr = fresh<bool>(false);
    state.door_rl = fresh<bool>(false);
    state.door_rr = fresh<bool>(false);
    state.frunk = fresh<bool>(false);
    state.trunk = fresh<bool>(false);
    state.headlights = fresh<bool>(true);
    state.position_light = fresh<bool>(true);
    state.brake_light = fresh<bool>(false);
    state.turn_signal_left = fresh<bool>(true);
    state.turn_signal_right = fresh<bool>(false);
    state.tire_fl = fresh<float>(2.83F);
    state.tire_fr = fresh<float>(2.85F);
    state.tire_rl = fresh<float>(2.93F);
    state.tire_rr = fresh<float>(2.75F);
    state.temperature_primary = fresh<std::int16_t>(22);
    // The MCU's SOC byte is present and known-untrusted: it is exactly the
    // value a screen must not print as a percentage.
    state.soc = fresh<std::uint8_t>(97);
    state.soc.quality = SignalQuality::Estimated;
    return state;
}

VehicleState commanderState(std::uint8_t soc, float power_kw) {
    VehicleState state;
    state.actual_soc.update(soc, kNow, SignalSource::Commander,
                            SignalQuality::Confirmed, Unit::Percent);
    state.battery_power.update(power_kw, kNow, SignalSource::Commander,
                               SignalQuality::Confirmed, Unit::Kilowatt);
    state.battery_voltage.update(372.5F, kNow, SignalSource::Commander,
                                 SignalQuality::Confirmed, Unit::Volt);
    state.battery_current.update(-33.2F, kNow, SignalSource::Commander,
                                 SignalQuality::Confirmed, Unit::Ampere);
    state.total_charged_energy.update(812.4F, kNow, SignalSource::Commander,
                                      SignalQuality::Confirmed, Unit::KilowattHour);
    state.total_discharged_energy.update(790.1F, kNow, SignalSource::Commander,
                                         SignalQuality::Confirmed, Unit::KilowattHour);
    state.accelerator_position.update(18.0F, kNow, SignalSource::Commander,
                                      SignalQuality::Confirmed, Unit::Percent);
    return state;
}

PageEnvironmentV6 environment() {
    PageEnvironmentV6 env;
    env.uart_connected = true;
    env.uart_receiving = true;
    env.commander_status = CommanderLinkStatus::Linked;
    env.commander_detail_known = true;
    env.commander_detail = "NativeBle · v1.2.0";
    env.parser_stats_known = true;
    env.parser_frames = 2637;
    env.parser_checksum_errors = 0;
    env.frame_stats_known = true;
    env.frame_ms = 18.4F;
    env.fps = 54.0F;
    env.memory_stats_known = true;
    env.rss_kb = 3696;
    env.resident_assets_kb = 1600;
    env.trip_known = true;
    env.trip_distance_km = 42.6F;
    env.trip_duration_ms = 58ULL * 60ULL * 1000ULL;
    env.trip_average_kph = 44.0F;
    return env;
}

const std::vector<DashboardPageV6> kAllPages = {
    DashboardPageV6::Horizon, DashboardPageV6::Mono,
    DashboardPageV6::Pulse,   DashboardPageV6::Route,
    DashboardPageV6::Studio,  DashboardPageV6::Energy,
    DashboardPageV6::Nocturne, DashboardPageV6::Settings,
    DashboardPageV6::Developer,
};

const ProjectedValueV6& value(const PageProjectionV6& projection, const char* name) {
    const auto it = projection.find(name);
    assert(it != projection.end());
    return it->second;
}

}  // namespace

int main() {
    const VehicleState mcu = mcuState();
    const VehicleState commander = commanderState(63, -12.4F);
    const ProductStateV6 product;
    const DashboardSettings settings;
    const PageEnvironmentV6 env = environment();

    // ------------------------------------------------------------------ set
    // The projection offers exactly the names the page declares, and the
    // declared names are unique and sorted. Renaming a binding on either side
    // fails here instead of drawing nothing on the panel.
    {
        for (DashboardPageV6 page : kAllPages) {
            const auto declared = pageBindingNamesV6(page);
            assert(!declared.empty());
            const std::set<std::string> declared_set(declared.begin(), declared.end());
            assert(declared_set.size() == declared.size());
            assert(std::is_sorted(declared.begin(), declared.end()));

            const PageProjectionV6 projection = buildPageProjectionV6(
                page, mcu, product, settings, env);
            std::set<std::string> produced;
            for (const auto& entry : projection) produced.insert(entry.first);
            assert(produced == declared_set);
        }
        std::cout << "every page offers exactly its declared bindings\n";
    }

    // -------------------------------------------------------- no data at all
    {
        const VehicleState empty;
        PageEnvironmentV6 dead;
        dead.uart_connected = false;
        for (DashboardPageV6 page : kAllPages) {
            if (page == DashboardPageV6::Settings) continue;  // settings are local
            const PageProjectionV6 projection = buildPageProjectionV6(
                page, empty, ProductStateV6{}, settings, dead);
            for (const auto& entry : projection) {
                const std::string name = entry.first;
                const ProjectedValueV6& value = entry.second;
                if (name == "uart_health") {
                    // The link state itself is known: it is "lost".
                    assert(value.valid && value.text == "UART LOST");
                    continue;
                }
                if (name == "warning_active") {
                    // The absence of a warning is a verdict, not telemetry: it
                    // is known even when every signal is missing.
                    assert(value.valid && !value.flag);
                    continue;
                }
                if (name == "developer_mode") {
                    // Whether developer mode is on is a local setting, known
                    // even when no vehicle data is arriving.
                    assert(value.valid && !value.flag);
                    continue;
                }
                if (name == "dev_hint" || name == "dev_gear" ||
                    name == "dev_soc" || name == "dev_commander" ||
                    name == "dev_uart") {
                    continue;  // diagnostic text describes the absence
                }
                assert(!value.valid);
            }
        }
        // And the formatter turns "not available" into the node's placeholder,
        // never into a zero.
        const ProjectedValueV6 missing =
            ProjectedValueV6::unavailable(ProjectedValueV6::Kind::Number);
        assert(formatSceneTextV6("{}", missing, "--") == "--");
        assert(formatSceneTextV6("{} km", missing, "-- km") == "-- km");
        std::cout << "with no telemetry every value is invalid and renders as "
                     "its placeholder\n";
    }

    // ---------------------------------------------------------------- SOC
    {
        // MCU SOC byte alone: nothing on the screen may show 97 %.
        const PageProjectionV6 horizon = buildPageProjectionV6(
            DashboardPageV6::Horizon, mcu, product, settings, env);
        assert(!value(horizon, "actual_soc").valid);
        const PageProjectionV6 energy_page = buildPageProjectionV6(
            DashboardPageV6::Energy, mcu, product, settings, env);
        assert(!value(energy_page, "actual_soc").valid);

        // With the Commander's actual_soc merged in, it is drawn.
        VehicleState merged = mcu;
        mergeCommanderInto(merged, commander);
        assert(merged.soc.value == 97);           // the MCU byte is untouched
        assert(merged.actual_soc.valid);
        assert(merged.actual_soc.value == 63);
        const PageProjectionV6 with_soc = buildPageProjectionV6(
            DashboardPageV6::Energy, merged, product, settings, env);
        assert(value(with_soc, "actual_soc").valid);
        assert(value(with_soc, "actual_soc").number == 63.0);
        assert(formatSceneTextV6("{}%", value(with_soc, "actual_soc"), "-- %") == "63%");
        std::cout << "SOC is drawn from the Commander only\n";
    }

    // ------------------------------------------------------------ merge rule
    {
        VehicleState target = mcu;
        VehicleState enhanced = commander;
        // A misbehaving enhanced source also carries directly read values.
        enhanced.speed = fresh<std::uint16_t>(250);
        enhanced.gear = fresh<Gear>(Gear::Reverse);
        enhanced.range = fresh<std::uint16_t>(1);
        enhanced.door_fl = fresh<bool>(true);
        enhanced.tire_fl = fresh<float>(0.1F);
        enhanced.headlights = fresh<bool>(false);
        mergeCommanderInto(target, enhanced);
        assert(target.speed.value == 88);          // still the car's own reading
        assert(target.gear.value == Gear::Drive);
        assert(target.range.value == 253);
        assert(target.door_fl.value == false);
        assert(std::fabs(target.tire_fl.value - 2.83F) < 0.001F);
        assert(target.headlights.value == true);
        assert(target.actual_soc.value == 63);     // enhanced data does land
        std::cout << "the Commander cannot overwrite a directly read value\n";
    }

    // -------------------------------------------------------------- closures
    {
        const PageProjectionV6 closed = buildPageProjectionV6(
            DashboardPageV6::Horizon, mcu, product, settings, env);
        assert(value(closed, "closures").valid);
        assert(value(closed, "closures").text == "ALL CLOSED");

        VehicleState open_door = mcu;
        open_door.door_fl = fresh<bool>(true);
        const PageProjectionV6 open_projection = buildPageProjectionV6(
            DashboardPageV6::Horizon, open_door, product, settings, env);
        assert(value(open_projection, "closures").text == "OPEN FL");

        // One unknown door: the page may not say "ALL CLOSED" any more.
        VehicleState unknown_door = mcu;
        unknown_door.door_fl = Signal<bool>{};
        const PageProjectionV6 unknown_projection = buildPageProjectionV6(
            DashboardPageV6::Horizon, unknown_door, product, settings, env);
        assert(!value(unknown_projection, "closures").valid);

        const PageProjectionV6 studio = buildPageProjectionV6(
            DashboardPageV6::Studio, unknown_door, product, settings, env);
        const std::string detail = value(studio, "closures_detail").text;
        assert(detail.find("FL ?") == 0);
        assert(detail.find("FR SHUT") != std::string::npos);
        std::cout << "an unknown closure is never drawn as closed\n";
    }

    // --------------------------------------------------------------- gear
    {
        const PageProjectionV6 drive = buildPageProjectionV6(
            DashboardPageV6::Horizon, mcu, product, settings, env);
        assert(value(drive, "gear").valid);
        assert(value(drive, "gear").number == static_cast<double>(Gear::Drive));

        VehicleState unknown_gear = mcu;
        unknown_gear.gear = Signal<Gear>{};
        const PageProjectionV6 unknown_projection = buildPageProjectionV6(
            DashboardPageV6::Horizon, unknown_gear, product, settings, env);
        assert(!value(unknown_projection, "gear").valid);
        assert(formatSceneTextV6("{}", value(unknown_projection, "gear"), "--") == "--");
        std::cout << "an unconfirmed gear stays unknown\n";
    }

    // ---------------------------------------------------- commander link state
    {
        PageEnvironmentV6 disabled = env;
        disabled.commander_status = CommanderLinkStatus::Disabled;
        const PageProjectionV6 off = buildPageProjectionV6(
            DashboardPageV6::Energy, mcu, product, settings, disabled);
        assert(!value(off, "commander_link").valid);
        assert(!value(off, "commander_detail").valid);

        PageEnvironmentV6 searching = env;
        searching.commander_status = CommanderLinkStatus::Searching;
        const PageProjectionV6 searching_projection = buildPageProjectionV6(
            DashboardPageV6::Energy, mcu, product, settings, searching);
        assert(value(searching_projection, "commander_link").valid);
        assert(value(searching_projection, "commander_link").number == 0.0);

        const PageProjectionV6 linked = buildPageProjectionV6(
            DashboardPageV6::Energy, mcu, product, settings, env);
        assert(value(linked, "commander_link").number == 1.0);
        assert(value(linked, "commander_detail").text == "NativeBle · v1.2.0");
        std::cout << "the Commander badge never claims a link it does not have\n";
    }

    // ---------------------------------------------------------------- route
    {
        PageEnvironmentV6 trip = env;  // trip metrics are present, nav is not
        const PageProjectionV6 route = buildPageProjectionV6(
            DashboardPageV6::Route, mcu, product, settings, trip);
        assert(!value(route, "nav_manoeuvre").valid);
        assert(formatSceneTextV6("{}", value(route, "nav_manoeuvre"), "NO ROUTE") ==
               "NO ROUTE");
        assert(value(route, "trip_distance").valid);
        assert(value(route, "trip_time_text").text == "0:58");
        assert(formatSceneTextV6("avg {:.0f} km/h", value(route, "average_speed"),
                                 "avg --") == "avg 44 km/h");

        ProductStateV6 nav;
        nav.navigation.available = true;
        nav.navigation.active = true;
        nav.navigation.capabilities = NavigationCapability::BasicManeuver;
        nav.navigation.next_maneuver = fresh<ManeuverType>(ManeuverType::TurnRight);
        nav.navigation.next_turn_distance_m = fresh<float>(300.0F);
        Signal<std::uint64_t> eta;
        eta.update(static_cast<std::uint64_t>(14 * 3600 + 32 * 60), kNow,
                   SignalSource::PhoneBridge, SignalQuality::Confirmed, Unit::None);
        nav.navigation.eta_epoch_s = eta;
        const PageProjectionV6 navigating = buildPageProjectionV6(
            DashboardPageV6::Route, mcu, nav, settings, trip);
        assert(value(navigating, "nav_manoeuvre").text == "IN 300 M TURN RIGHT");
        assert(formatSceneTextV6("{} m", value(navigating, "nav_distance"), "-- m") ==
               "300 m");
        assert(formatSceneTextV6("ETA {}", value(navigating, "nav_eta"), "ETA --") ==
               "ETA 14:32");
        std::cout << "route falls back to NO ROUTE and still shows trip metrics\n";
    }

    // ------------------------------------------------------------- settings
    {
        DashboardSettings custom;
        custom.appearance = AppearanceMode::Night;
        custom.brightness_percent = 80;
        custom.distance_unit = DistanceUnit::Mile;
        custom.temperature_unit = TemperatureUnit::Fahrenheit;
        custom.tire_pressure_unit = TirePressureUnit::Psi;
        custom.clock_24h = false;
        custom.warning_sound_enabled = false;
        custom.developer_mode_enabled = true;
        const PageProjectionV6 projection = buildPageProjectionV6(
            DashboardPageV6::Settings, mcu, product, custom, env);
        assert(value(projection, "appearance_text").text == "NIGHT");
        assert(value(projection, "brightness_text").text == "80 %");
        assert(value(projection, "speed_unit_text").text == "mph");
        assert(value(projection, "temperature_unit_text").text == "°F");
        assert(value(projection, "tire_pressure_unit_text").text == "psi");
        assert(value(projection, "clock_text").text == "12 h");
        assert(value(projection, "warning_sound_text").text == "OFF");
        assert(value(projection, "developer_mode_text").text == "ON");
        assert(value(projection, "default_page_text").text == "Horizon");

        DashboardSettings illegal;
        illegal.default_page = DashboardPageV6::Developer;
        const PageProjectionV6 refused = buildPageProjectionV6(
            DashboardPageV6::Settings, mcu, product, illegal, env);
        assert(!value(refused, "default_page_text").valid);
        std::cout << "settings render, and the Developer screen cannot be the "
                     "default page\n";
    }

    // ------------------------------------------------------------ developer
    {
        const PageProjectionV6 projection = buildPageProjectionV6(
            DashboardPageV6::Developer, mcu, product, settings, env);
        assert(value(projection, "dev_uart").text.find("READ-ONLY") !=
               std::string::npos);
        assert(value(projection, "dev_parser").text.find("2637 frames") == 0);
        assert(value(projection, "dev_frame").text.find("54 fps") !=
               std::string::npos);
        assert(value(projection, "dev_memory").text.find("3.6 MB") !=
               std::string::npos);
        assert(value(projection, "dev_hint").text.find("never live vehicle data") !=
               std::string::npos);
        assert(value(projection, "developer_mode").kind ==
               ProjectedValueV6::Kind::Flag);
        std::cout << "the developer screen reports counters, not vehicle state\n";
    }

    // ----------------------------------------------------------- navigation
    {
        const auto ring = swipeOrderV6();
        assert(ring.size() == 8);
        assert(ring.front() == DashboardPageV6::Horizon);
        assert(ring.back() == DashboardPageV6::Settings);
        for (DashboardPageV6 page : ring) {
            assert(pageIsReachableV6(page, false));
        }
        assert(!isDrivingPageV6(DashboardPageV6::Settings));
        assert(!isDrivingPageV6(DashboardPageV6::Developer));
        assert(isDrivingPageV6(safetyPageV6()));

        assert(stepPageV6(DashboardPageV6::Horizon, 1, false) == DashboardPageV6::Mono);
        assert(stepPageV6(DashboardPageV6::Horizon, -1, false) ==
               DashboardPageV6::Settings);
        assert(stepPageV6(DashboardPageV6::Settings, 1, false) ==
               DashboardPageV6::Horizon);
        // Developer is never a landing spot for a swipe.
        DashboardPageV6 page = DashboardPageV6::Settings;
        for (int i = 0; i < 32; ++i) {
            page = stepPageV6(page, 1, true);
            assert(page != DashboardPageV6::Developer);
        }
        assert(!pageIsReachableV6(DashboardPageV6::Developer, false));
        assert(pageIsReachableV6(DashboardPageV6::Developer, true));

        PageManagerV6 manager(DashboardPageV6::Horizon);
        manager.requestNext(1, false);
        manager.update(1000, MotionQuality::Full);
        assert(manager.current() == DashboardPageV6::Mono);
        manager.requestNext(-1, false);
        manager.update(1000, MotionQuality::Full);
        assert(manager.current() == DashboardPageV6::Horizon);
        manager.request(DashboardPageV6::Developer, true);
        manager.requestNext(1, true);
        manager.update(1000, MotionQuality::Full);
        assert(manager.current() == DashboardPageV6::Horizon);
        std::cout << "swipe order, developer gating and the safety page hold\n";
    }

    // ------------------------------------------------------- commander frames
    {
        CommanderTelemetryDecoder decoder;
        VehicleState decoded;
        const std::uint64_t t = 5'000;

        // Pack: soc 63 %, 372.5 V (3725 = 0x0E8D), -33.2 A (-332 = 0xFEB4),
        // -12.4 kW (-124 = 0xFF84). Multi-byte values are little-endian.
        std::vector<std::uint8_t> frame = {0xB5, 0x01, 0x07,
                                           63, 0x8D, 0x0E, 0xB4, 0xFE, 0x84, 0xFF};
        frame.push_back(CommanderTelemetryDecoder::checksum(0x01, 0x07, &frame[3]));
        decoder.decode(frame.data(), frame.size(), decoded, t);
        assert(decoder.stats().frames == 1);
        assert(decoder.stats().decoded == 1);
        assert(decoded.actual_soc.valid && decoded.actual_soc.value == 63);
        assert(decoded.actual_soc.source == SignalSource::Commander);
        assert(std::fabs(decoded.battery_voltage.value - 372.5F) < 0.01F);
        assert(std::fabs(decoded.battery_current.value + 33.2F) < 0.01F);
        assert(std::fabs(decoded.battery_power.value + 12.4F) < 0.01F);

        // A corrupted frame is rejected and counted, and changes nothing.
        std::vector<std::uint8_t> bad = frame;
        bad.back() ^= 0xFF;
        VehicleState untouched;
        decoder.decode(bad.data(), bad.size(), untouched, t);
        assert(decoder.stats().checksum_errors == 1);
        assert(!untouched.actual_soc.valid);

        // An unknown message type is counted, never guessed into a field.
        std::vector<std::uint8_t> unknown = {0xB5, 0x7F, 0x02, 1, 2};
        unknown.push_back(CommanderTelemetryDecoder::checksum(0x7F, 0x02, &unknown[3]));
        decoder.decode(unknown.data(), unknown.size(), decoded, t);
        assert(decoder.stats().unknown_types == 1);

        // A partial frame at the end of a read is not an error: the rest may
        // still arrive.
        const std::uint64_t errors_before = decoder.stats().checksum_errors +
                                            decoder.stats().malformed;
        decoder.decode(frame.data(), 5, decoded, t);
        assert(decoder.stats().checksum_errors + decoder.stats().malformed ==
               errors_before);

        // Cells and inputs.
        // 3856 mV (0x0F10) and 3872 mV (0x0F20).
        std::vector<std::uint8_t> cell_frame = {0xB5, 0x03, 0x05, 2, 0x10, 0x0F,
                                                0x20, 0x0F};
        cell_frame.push_back(
            CommanderTelemetryDecoder::checksum(0x03, 0x05, &cell_frame[3]));
        decoder.decode(cell_frame.data(), cell_frame.size(), decoded, t);
        assert(decoded.cell_voltages.size() == 2);
        assert(std::fabs(decoded.min_cell_voltage.value - 3.856F) < 0.001F);
        assert(std::fabs(decoded.max_cell_voltage.value - 3.872F) < 0.001F);
        assert(std::fabs(decoded.cell_delta.value - 0.016F) < 0.001F);

        std::vector<std::uint8_t> input_frame = {0xB5, 0x04, 0x02, 36, 0};  // 18.0 %
        input_frame.push_back(
            CommanderTelemetryDecoder::checksum(0x04, 0x02, &input_frame[3]));
        decoder.decode(input_frame.data(), input_frame.size(), decoded, t);
        assert(std::fabs(decoded.accelerator_position.value - 18.0F) < 0.001F);

        // Info frame: version and feature flags.
        std::vector<std::uint8_t> info_frame = {0xB5, 0x05, 0x04, 1, 2, 0, 0x0F};
        info_frame.push_back(
            CommanderTelemetryDecoder::checksum(0x05, 0x04, &info_frame[3]));
        decoder.decode(info_frame.data(), info_frame.size(), decoded, t);
        assert(decoder.module_info_known());
        assert(decoder.version().major == 1 && decoder.version().minor == 2);
        assert(decoder.features().power);
        std::cout << "commander frames decode, bad frames are rejected\n";
    }

    // -------------------------------------------------------- commander link
    {
        CommanderLink link;
        assert(link.status() == CommanderLinkStatus::Disabled);
        int value_out = -1;
        assert(!link.linkValue(value_out));   // disabled is not "0: not linked"

        link.setEnabled(true, kNow);
        assert(link.status() == CommanderLinkStatus::Searching);
        assert(link.linkValue(value_out) && value_out == 0);

        link.setTransport(true, kNow + 10);
        assert(link.status() == CommanderLinkStatus::NoFrames);  // connected != data
        link.noteFrame(kNow + 20);
        assert(link.linked() && link.linkValue(value_out) && value_out == 1);
        assert(link.detail("NativeBle").find("no module info") != std::string::npos);

        CommanderModuleVersion version{1, 2, 0};
        CommanderFeatureFlags flags;
        flags.enabled = true;
        link.setModuleInfo(version, flags);
        assert(link.detail("NativeBle") == "NativeBle · v1.2.0");

        link.tick(kNow + 20 + 4000);          // beyond the frame timeout
        assert(link.status() == CommanderLinkStatus::Stale);
        assert(link.linkValue(value_out) && value_out == 0);
        link.noteFrame(kNow + 9000);
        assert(link.linked());
        link.setEnabled(false, kNow + 9000);
        assert(link.status() == CommanderLinkStatus::Disabled);
        std::cout << "the commander link state machine is honest about silence\n";
    }

    std::cout << "all page projection checks passed\n";
    return 0;
}
