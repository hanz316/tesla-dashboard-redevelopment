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
        // Frames are built with the module's own framing: 55 7F, command,
        // length high/low, payload, checksum = sum(cmd, length, payload).
        const auto frameFor = [](std::uint8_t command,
                                 const std::vector<std::uint8_t>& payload) {
            return CommanderFrameV6::encode(command, payload);
        };

        CommanderFrameReaderV6 reader;
        std::vector<CommanderFrameReaderV6::Frame> received;
        const auto feedAll = [&reader, &received](const std::vector<std::uint8_t>& bytes,
                                                  std::uint64_t now) {
            CommanderFrameReaderV6::Frame frame;
            for (std::uint8_t byte : bytes) {
                if (reader.feed(byte, now, frame)) received.push_back(frame);
            }
        };
        const std::uint64_t t = 5'000;

        // The checksum is the module's rule, checked against a hand-summed
        // example rather than against itself.
        {
            const std::vector<std::uint8_t> payload = {1};
            // 160 + 0x00 + 0x01 + 1 = 162 = 0xA2
            assert(CommanderFrameV6::checksum(160, payload) == 0xA2);
            const auto encoded = frameFor(176, {1});
            assert(encoded.size() == CommanderFrameV6::kOverhead + 1);
            assert(encoded[0] == 0x55 && encoded[1] == 0x7F && encoded[2] == 176);
            assert(encoded[3] == 0x00 && encoded[4] == 0x01);
            assert(encoded[5] == 1);
            assert(encoded[6] == CommanderFrameV6::checksum(176, payload));
        }

        // A gauge frame (command 176) with the fields the screens read.
        {
            std::vector<std::uint8_t> payload(33, 0);
            // payload[0..3]: speed 88 (bits 0-8), gear 4 = D (bits 9-11),
            // turn 1 = left (12-13), autopilot 2 (14-15), door bits 0x5 =
            // driver + passenger (16-19), lamp bits 0x22 = low beam + brake
            // (20-23), SOC 63 (24-30).
            const std::uint32_t first = 88U | (4U << 9) | (1U << 12) | (2U << 14) |
                                        (0x5U << 16) | (0x2U << 20) | (63U << 24);
            payload[0] = static_cast<std::uint8_t>(first & 0xFF);
            payload[1] = static_cast<std::uint8_t>((first >> 8) & 0xFF);
            payload[2] = static_cast<std::uint8_t>((first >> 16) & 0xFF);
            payload[3] = static_cast<std::uint8_t>((first >> 24) & 0xFF);
            // payload[4..7]: trunk open (bit 5), sport (bit 3), range 253.0 km
            // (bits 6-31, /10). Bit 4 of payload[4] is the module's other
            // brake-lamp input: the client folds it into the lamp word as
            // bit 5.
            const std::uint32_t second = 0x1U | (1U << 4) | (1U << 5) |
                                         (1U << 3) | (2530U << 6);
            payload[4] = static_cast<std::uint8_t>(second & 0xFF);
            payload[5] = static_cast<std::uint8_t>((second >> 8) & 0xFF);
            payload[6] = static_cast<std::uint8_t>((second >> 16) & 0xFF);
            payload[7] = static_cast<std::uint8_t>((second >> 24) & 0xFF);
            // Tire pressures: 113 and 114 counts = 2.825 / 2.85 bar, and two
            // sensors that are not reporting (0 and 255).
            payload[8] = 113;
            payload[9] = 114;
            payload[10] = 0;
            payload[11] = 255;
            // payload[12..15]: accelerator 45 counts of 250 (18 %), rear motor
            // -18.5 kW (signed 11 bits, /2), front motor +11.0 kW.
            const int rear_count = -37;   // /2 = -18.5 kW
            const int front_count = 22;   // /2 = 11.0 kW
            const std::uint32_t third = 45U |
                ((static_cast<std::uint32_t>(rear_count) & 0x7FFU) << 8) |
                ((static_cast<std::uint32_t>(front_count) & 0x7FFU) << 19);
            payload[12] = static_cast<std::uint8_t>(third & 0xFF);
            payload[13] = static_cast<std::uint8_t>((third >> 8) & 0xFF);
            payload[14] = static_cast<std::uint8_t>((third >> 16) & 0xFF);
            payload[15] = static_cast<std::uint8_t>((third >> 24) & 0xFF);
            payload[17] = 0x40;  // imperial units bit set, nothing else
            payload[27] = 124;   // ambient 0.5 * 124 - 40 = 22.0 C
            // payload[28..31]: cell voltage 3.700 V (1850 = 0x073A),
            // rated range 253.0 km (157 counts * 1.61), battery temp 20.0 C
            // ((120) * 0.5 - 40).
            const std::uint32_t pack = 1850U | (157U << 12) | (120U << 22);
            payload[28] = static_cast<std::uint8_t>(pack & 0xFF);
            payload[29] = static_cast<std::uint8_t>((pack >> 8) & 0xFF);
            payload[30] = static_cast<std::uint8_t>((pack >> 16) & 0xFF);
            payload[31] = static_cast<std::uint8_t>((pack >> 24) & 0xFF);
            payload[32] = 0x00;

            feedAll(frameFor(176, payload), t);
            assert(received.size() == 1);
            assert(received[0].command == 176);

            CommanderGaugeV6 gauge;
            assert(decodeCommanderGaugeV6(received[0].payload, t, gauge));
            assert(gauge.speed_kph == 88);
            assert(gauge.gear == Gear::Drive);
            assert(gauge.turn == 1 && gauge.indicator_left && !gauge.indicator_right);
            assert(gauge.autopilot == 2);
            // Door bits are not in door order: driver is bit 0 and passenger
            // is bit 2, so 0x5 is driver + passenger, not driver + rear left.
            assert(gauge.door_fl && gauge.door_fr && !gauge.door_rl && !gauge.door_rr);
            assert(gauge.headlight && !gauge.high_beam && !gauge.fog_light);
            assert(gauge.brake_light);
            assert(gauge.soc_percent == 63);
            assert(gauge.trunk_open && !gauge.frunk_open);
            assert(gauge.sport_mode && !gauge.screen_on);
            assert(std::fabs(gauge.range_km - 253.0F) < 0.05F);
            assert(gauge.tire_valid[0] && gauge.tire_valid[1]);
            assert(!gauge.tire_valid[2] && !gauge.tire_valid[3]);
            assert(std::fabs(gauge.tire_bar[0] - 2.825F) < 0.001F);
            assert(std::fabs(gauge.tire_bar[1] - 2.85F) < 0.001F);
            assert(std::fabs(gauge.accelerator_percent - 18.0F) < 0.2F);
            assert(std::fabs(gauge.rear_motor_kw + 18.5F) < 0.01F);
            assert(std::fabs(gauge.front_motor_kw - 11.0F) < 0.01F);
            assert(std::fabs(gauge.ambient_temp_c - 22.0F) < 0.01F);
            assert(std::fabs(gauge.cell_voltage_v - 3.700F) < 0.001F);
            assert(std::fabs(gauge.rated_range_km - 252.77F) < 0.05F);
            assert(std::fabs(gauge.battery_temp_c - 20.0F) < 0.01F);
        }

        // A pack frame (command 208): voltage, current with the module's own
        // wrap fix, energy counters, cells, and the actual SOC the module
        // derives from remaining and full energy.
        {
            std::vector<std::uint8_t> payload(29, 0);
            const std::uint32_t volts = 39800;  // 398.00 V
            const std::uint32_t amps = 1200;    // -120.0 A
            payload[0] = static_cast<std::uint8_t>(volts & 0xFF);
            payload[1] = static_cast<std::uint8_t>((volts >> 8) & 0xFF);
            payload[2] = static_cast<std::uint8_t>(amps & 0xFF);
            payload[3] = static_cast<std::uint8_t>((amps >> 8) & 0xFF);
            const std::uint32_t discharged = 790100;  // 790.1 kWh
            const std::uint32_t charged = 812400;     // 812.4 kWh
            payload[4] = static_cast<std::uint8_t>(discharged & 0xFF);
            payload[5] = static_cast<std::uint8_t>((discharged >> 8) & 0xFF);
            payload[6] = static_cast<std::uint8_t>((discharged >> 16) & 0xFF);
            payload[7] = static_cast<std::uint8_t>((discharged >> 24) & 0xFF);
            payload[8] = static_cast<std::uint8_t>(charged & 0xFF);
            payload[9] = static_cast<std::uint8_t>((charged >> 8) & 0xFF);
            payload[10] = static_cast<std::uint8_t>((charged >> 16) & 0xFF);
            payload[11] = static_cast<std::uint8_t>((charged >> 24) & 0xFF);
            // Energy: remaining 37.50 kWh (1875 counts * 0.02), full
            // 75.00 kWh (3750 counts * 0.02).
            const std::uint32_t energy = 1875U | (3750U << 16);
            payload[12] = static_cast<std::uint8_t>(energy & 0xFF);
            payload[13] = static_cast<std::uint8_t>((energy >> 8) & 0xFF);
            payload[14] = static_cast<std::uint8_t>((energy >> 16) & 0xFF);
            payload[15] = static_cast<std::uint8_t>((energy >> 24) & 0xFF);
            const std::uint32_t reserve = 250;  // 2.50 kWh
            payload[16] = static_cast<std::uint8_t>(reserve & 0xFF);
            payload[17] = static_cast<std::uint8_t>((reserve >> 8) & 0xFF);
            // Cells: max 3.900 V (1950 counts), min 3.850 V (1925 counts).
            const std::uint32_t cells = 1950U | (1925U << 12);
            payload[18] = static_cast<std::uint8_t>(cells & 0xFF);
            payload[19] = static_cast<std::uint8_t>((cells >> 8) & 0xFF);
            payload[20] = static_cast<std::uint8_t>((cells >> 16) & 0xFF);
            // Capacity/range/temperature/SOC: factory 75.0 kWh, range 402.5 km
            // (250 * 1.61), battery temp 20.0 C, car SOC 63 (7 bits at 7).
            const std::uint32_t capacity = 750U | (250U << 10) | (120U << 22);
            payload[21] = static_cast<std::uint8_t>(capacity & 0xFF);
            payload[22] = static_cast<std::uint8_t>((capacity >> 8) & 0xFF);
            payload[23] = static_cast<std::uint8_t>((capacity >> 16) & 0xFF);
            // payload[24] is shared: its low seven bits are bits 24-30 of the
            // temperature/capacity word above, and its bit 7 is bit 0 of the
            // car's 16-bit SOC at payload[24..25]. A frame that sets one and
            // zeroes the other is not a frame this module would send.
            const std::uint32_t soc_and_temp = (63U << 7);
            payload[24] = static_cast<std::uint8_t>(((capacity >> 24) & 0x7FU) |
                                                    (soc_and_temp & 0x80U));
            payload[25] = static_cast<std::uint8_t>((soc_and_temp >> 8) & 0xFF);
            const std::uint32_t odometer = 123456U << 6;  // 12345.6 km
            payload[26] = static_cast<std::uint8_t>((odometer >> 8) & 0xFF);
            payload[27] = static_cast<std::uint8_t>((odometer >> 16) & 0xFF);
            payload[28] = static_cast<std::uint8_t>((odometer >> 24) & 0xFF);

            feedAll(frameFor(208, payload), t + 10);
            assert(received.size() == 2 && received[1].command == 208);
            CommanderPackV6 pack;
            assert(decodeCommanderPackV6(received[1].payload, t + 10, pack));
            assert(std::fabs(pack.pack_voltage_v - 398.00F) < 0.01F);
            assert(std::fabs(pack.pack_current_a + 120.0F) < 0.01F);
            assert(std::fabs(pack.pack_power_kw + 47.76F) < 0.05F);
            assert(std::fabs(pack.total_charged_kwh - 812.4F) < 0.01F);
            assert(std::fabs(pack.total_discharged_kwh - 790.1F) < 0.01F);
            assert(std::fabs(pack.remaining_kwh - 37.5F) < 0.01F);
            assert(std::fabs(pack.full_kwh - 75.0F) < 0.01F);
            assert(std::fabs(pack.reserve_kwh - 2.5F) < 0.01F);
            assert(std::fabs(pack.max_cell_v - 3.900F) < 0.001F);
            assert(std::fabs(pack.min_cell_v - 3.850F) < 0.001F);
            assert(std::fabs(pack.cell_delta_mv - 50.0F) < 0.1F);
            // (37.5 - 2.5) / (75 - 2.5) * 100 = 48.28 %
            assert(pack.actual_soc_known);
            assert(std::fabs(pack.actual_soc_percent - 48.28F) < 0.05F);
            // The car's own 7-bit SOC is reported separately and is not used
            // when the energy ratio is available.
            assert(pack.car_soc_percent == 63);
            assert(std::fabs(pack.battery_temp_c - 20.0F) < 0.01F);
            assert(std::fabs(pack.odometer_km - 12345.6F) < 0.1F);

            // The cluster's own reading, and the module's reading of the same
            // car, kept in separate states.
            VehicleState state;
            state.speed.update(55, t, SignalSource::OriginalMcu,
                               SignalQuality::Confirmed, Unit::KilometerPerHour);
            state.soc.update(97, t, SignalSource::OriginalMcu,
                             SignalQuality::Estimated, Unit::Percent);
            state.door_fl.update(false, t, SignalSource::OriginalMcu,
                                 SignalQuality::Confirmed, Unit::None);
            CommanderGaugeV6 gauge;
            gauge.valid = true;
            gauge.speed_kph = 250;   // the module's reading
            gauge.gear = Gear::Reverse;
            gauge.door_fl = true;
            CommanderDcdcV6 dcdc;
            VehicleState module_state;
            applyCommanderReadingsV6(gauge, pack, dcdc, module_state, t);
            assert(module_state.speed.value == 250);
            assert(module_state.speed.source == SignalSource::Commander);
            assert(module_state.gear.value == Gear::Reverse);
            assert(module_state.door_fl.value == true);
            assert(module_state.actual_soc.value == 48);  // the energy ratio
            assert(std::fabs(module_state.battery_voltage.value - 398.0F) < 0.01F);
            assert(std::fabs(module_state.battery_power.value + 47.76F) < 0.05F);
            // The cluster's own state is not touched by the module's decode.
            assert(state.speed.value == 55);
            assert(state.gear.value == Gear::Unknown);
            assert(state.soc.value == 97);   // the rejected byte stays where it is

            // The owner's rule: where both have a value, the module wins.
            const VehicleState arbitrated =
                buildArbitratedStateV6(state, module_state, t);
            assert(arbitrated.speed.value == 250);
            assert(arbitrated.speed.source == SignalSource::Commander);
            assert(arbitrated.gear.value == Gear::Reverse);
            assert(arbitrated.door_fl.value == true);
            assert(arbitrated.actual_soc.value == 48);
            // A stale module reading is not a vote: the car's value stands.
            VehicleState stale_commander = module_state;
            stale_commander.speed.markStale(t + 5000);
            const VehicleState fallen_back =
                buildArbitratedStateV6(state, stale_commander, t + 5000);
            assert(fallen_back.speed.value == 55);
            assert(fallen_back.speed.source == SignalSource::OriginalMcu);
            // With no module value at all, the cluster's own reading is used.
            const VehicleState mcu_only =
                buildArbitratedStateV6(state, VehicleState{}, t);
            assert(mcu_only.speed.value == 55);
            assert(!mcu_only.actual_soc.valid);   // and no SOC is invented
            // Turning the priority off is possible per signal, and then the
            // car's own reading wins even when the module has one.
            CommanderPriorityV6 mcu_first;
            mcu_first.speed = false;
            mcu_first.gear = false;
            const VehicleState overridden =
                buildArbitratedStateV6(state, module_state, t, mcu_first);
            assert(overridden.speed.value == 55);
        }

        // A corrupted frame is rejected and counted, and changes nothing.
        {
            auto bad = frameFor(176, std::vector<std::uint8_t>(33, 0));
            bad.back() ^= 0xFF;
            const std::uint64_t before = reader.frames();
            feedAll(bad, t + 20);
            assert(reader.frames() == before);
            assert(reader.checksum_errors() == 1);
        }

        // A partial frame that stops receiving is abandoned, exactly as the
        // module's own receiver does, instead of blocking the stream forever.
        {
            const auto frame = frameFor(176, std::vector<std::uint8_t>(33, 0));
            CommanderFrameReaderV6 partial;
            CommanderFrameReaderV6::Frame out;
            for (std::size_t i = 0; i + 2 < frame.size(); ++i) {
                partial.feed(frame[i], 1000, out);
            }
            assert(partial.frames() == 0);
            assert(partial.dropped_partials() == 0);
            partial.feed(frame[2], 1000 + CommanderFrameV6::kInterFrameGapMs + 1, out);
            assert(partial.dropped_partials() == 1);
        }

        // The instrument may only ask. Every control command is refused by
        // name, including the control word and the module's restart/reset.
        {
            assert(commanderCommandIsQueryV6(160));   // status
            assert(commanderCommandIsQueryV6(176));   // gauge
            assert(commanderCommandIsQueryV6(208));   // pack
            assert(commanderCommandIsQueryV6(209));
            assert(commanderCommandIsQueryV6(210));
            assert(commanderCommandIsQueryV6(193));
            const std::uint8_t control[] = {161, 162, 163, 164, 165, 166,
                                            167, 168, 169, 171, 173, 174,
                                            175, 185, 186, 187, 192, 240};
            for (std::uint8_t command : control) {
                assert(commanderCommandIsControlV6(command));
                assert(!commanderCommandIsQueryV6(command));
            }
            // An unknown command is not a query either.
            assert(!commanderCommandIsQueryV6(0x5A));
        }
        std::cout << "commander frames decode against the real protocol\n";
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
        assert(link.detail("NativeBle") == "NativeBle · HW 1 · FW 2 · BT 0");

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
