#include "dashboard/page_projection_v6.h"

#include <algorithm>
#include <cstdio>
#include <ctime>
#include <vector>

namespace dashboard {
namespace {

template <typename T>
bool live(const Signal<T>& signal) {
    return signal.valid && !signal.stale;
}

template <typename T>
ProjectedValueV6 fromSignal(const Signal<T>& signal, Unit unit) {
    if (!live(signal)) {
        return ProjectedValueV6::unavailable(ProjectedValueV6::Kind::Number);
    }
    ProjectedValueV6 value = ProjectedValueV6::makeNumber(
        static_cast<double>(signal.value), unit, signal.source, signal.quality);
    return value;
}

ProjectedValueV6 fromFlag(const Signal<bool>& signal) {
    if (!live(signal)) {
        return ProjectedValueV6::unavailable(ProjectedValueV6::Kind::Flag);
    }
    return ProjectedValueV6::makeFlag(signal.value, signal.source, signal.quality);
}

ProjectedValueV6 textValue(std::string text, SignalSource source,
                           SignalQuality quality) {
    return ProjectedValueV6::makeText(std::move(text), source, quality);
}

bool readClosure(const Signal<bool>& signal, bool& open, bool& known) {
    if (!live(signal)) {
        known = false;
        return false;
    }
    open = signal.value;
    return true;
}

const char* warningText(WarningCode code) {
    switch (code) {
        case WarningCode::DoorOpenMoving: return "DOOR OPEN WHILE MOVING";
        case WarningCode::FrunkOpenMoving: return "FRUNK OPEN WHILE MOVING";
        case WarningCode::TrunkOpenMoving: return "TRUNK OPEN WHILE MOVING";
        case WarningCode::LowTire: return "TIRE PRESSURE LOW";
        case WarningCode::LowSoc: return "BATTERY LOW";
        case WarningCode::VehicleDataLost: return "VEHICLE DATA LOST";
        case WarningCode::None:
        default: return "";
    }
}

std::string formatDuration(std::uint64_t duration_ms) {
    const std::uint64_t total_minutes = duration_ms / 60000ULL;
    char text[32];
    std::snprintf(text, sizeof(text), "%llu:%02llu",
                  static_cast<unsigned long long>(total_minutes / 60ULL),
                  static_cast<unsigned long long>(total_minutes % 60ULL));
    return text;
}

std::string formatManeuverText(const NavigationState& navigation) {
    if (!live(navigation.next_maneuver)) return std::string();
    const char* verb = "CONTINUE";
    switch (navigation.next_maneuver.value) {
        case ManeuverType::Continue: verb = "CONTINUE"; break;
        case ManeuverType::TurnLeft: verb = "TURN LEFT"; break;
        case ManeuverType::TurnRight: verb = "TURN RIGHT"; break;
        case ManeuverType::SlightLeft: verb = "KEEP LEFT"; break;
        case ManeuverType::SlightRight: verb = "KEEP RIGHT"; break;
        case ManeuverType::UTurn: verb = "U-TURN"; break;
        case ManeuverType::ExitLeft: verb = "EXIT LEFT"; break;
        case ManeuverType::ExitRight: verb = "EXIT RIGHT"; break;
        case ManeuverType::Roundabout: verb = "ROUNDABOUT"; break;
        case ManeuverType::Arrive: verb = "ARRIVE"; break;
        case ManeuverType::Unknown:
        default: return std::string();
    }
    char text[96];
    if (live(navigation.next_turn_distance_m)) {
        std::snprintf(text, sizeof(text), "IN %.0f M %s",
                      static_cast<double>(navigation.next_turn_distance_m.value), verb);
    } else {
        std::snprintf(text, sizeof(text), "%s", verb);
    }
    return text;
}

std::string formatCapability(std::uint32_t capabilities) {
    if (capabilities == NavNone) return "NONE";
    std::string text;
    const auto add = [&text](const char* part) {
        if (!text.empty()) text += "+";
        text += part;
    };
    if (capabilities & NavigationCapability::BasicManeuver) add("BASIC_MANEUVER");
    if (capabilities & NavigationCapability::TripMetrics) add("TRIP_METRICS");
    if (capabilities & NavigationCapability::RouteGeometry) add("ROUTE_GEOMETRY");
    if (capabilities & NavigationCapability::LaneGuidance) add("LANE_GUIDANCE");
    return text;
}

std::string formatEta(const PageEnvironmentV6& environment,
                      std::uint64_t eta_epoch_s) {
    if (eta_epoch_s == 0) return std::string();
    std::time_t local = static_cast<std::time_t>(eta_epoch_s) +
                        static_cast<std::time_t>(environment.utc_offset_minutes) * 60;
    std::tm parts{};
#if defined(_WIN32)
    gmtime_s(&parts, &local);
#else
    gmtime_r(&local, &parts);
#endif
    char text[16];
    std::snprintf(text, sizeof(text), "%02d:%02d", parts.tm_hour, parts.tm_min);
    return text;
}

const char* uartHealthText(const PageEnvironmentV6& environment) {
    if (!environment.uart_connected) return "UART LOST";
    return environment.uart_receiving ? "UART OK" : "UART STALE";
}

}  // namespace

ProjectedValueV6 ProjectedValueV6::makeNumber(double value, Unit unit,
                                          SignalSource source,
                                          SignalQuality quality) {
    ProjectedValueV6 out;
    out.kind = Kind::Number;
    out.valid = true;
    out.number = value;
    out.unit = unit;
    out.source = source;
    out.quality = quality;
    return out;
}

ProjectedValueV6 ProjectedValueV6::makeFlag(bool value, SignalSource source,
                                        SignalQuality quality) {
    ProjectedValueV6 out;
    out.kind = Kind::Flag;
    out.valid = true;
    out.flag = value;
    out.source = source;
    out.quality = quality;
    return out;
}

ProjectedValueV6 ProjectedValueV6::makeText(std::string value, SignalSource source,
                                        SignalQuality quality) {
    ProjectedValueV6 out;
    out.kind = Kind::Text;
    out.valid = true;
    out.text = std::move(value);
    out.source = source;
    out.quality = quality;
    return out;
}

ProjectedValueV6 ProjectedValueV6::unavailable(Kind kind) {
    ProjectedValueV6 out;
    out.kind = kind;
    out.valid = false;
    return out;
}

const char* pageNameV6(DashboardPageV6 page) {
    switch (page) {
        case DashboardPageV6::Horizon: return "Horizon";
        case DashboardPageV6::Mono: return "Mono";
        case DashboardPageV6::Pulse: return "Pulse";
        case DashboardPageV6::Route: return "Route";
        case DashboardPageV6::Studio: return "Studio";
        case DashboardPageV6::Energy: return "Energy";
        case DashboardPageV6::Nocturne: return "Nocturne";
        case DashboardPageV6::Settings: return "Settings";
        case DashboardPageV6::Developer: return "Developer";
        default: return "?";
    }
}

std::vector<std::string> pageBindingNamesV6(DashboardPageV6 page) {
    std::vector<std::string> names;
    switch (page) {
        case DashboardPageV6::Horizon:
            names = {"actual_soc", "brake", "closures", "commander_detail",
                     "commander_link", "gear", "headlight", "indicator_left",
                     "indicator_right", "nav_distance", "nav_instruction",
                     "nav_manoeuvre", "position_light", "range", "speed",
                     "speed_limit", "temperature_primary", "uart_health",
                     "warning_active", "warning_text", "driver_status_text"};
            break;
        case DashboardPageV6::Mono:
            names = {"brake", "closures", "gear", "headlight", "indicator_left",
                     "indicator_right", "range", "speed", "uart_health",
                     "warning_active", "warning_text"};
            break;
        case DashboardPageV6::Pulse:
            names = {"accelerator_position", "battery_power", "battery_power_abs",
                     "brake", "commander_detail", "commander_link", "gear",
                     "headlight", "indicator_left", "indicator_right", "speed",
                     "uart_health", "warning_active", "warning_text"};
            break;
        case DashboardPageV6::Route:
            names = {"average_speed", "nav_capability", "nav_distance", "nav_eta",
                     "nav_manoeuvre", "trip_distance", "trip_time_text",
                     "uart_health", "warning_active", "warning_text"};
            break;
        case DashboardPageV6::Studio:
            // The vehicle layer binds the same door/lamp signals the 2D pages
            // do; the difference is that here they move a rendered car instead
            // of drawing a lamp character.
            names = {"closures_detail", "commander_detail", "commander_link",
                     "brake", "door_fl", "door_fr", "door_rl", "door_rr",
                     "frunk", "gear", "headlight", "indicator_left",
                     "indicator_right", "lights_detail", "tires_detail",
                     "trunk", "uart_health", "warning_active", "warning_text"};
            break;
        case DashboardPageV6::Energy:
            names = {"actual_soc", "battery_current", "battery_power",
                     "battery_voltage", "commander_detail", "commander_link",
                     "range", "total_charged_energy", "total_discharged_energy",
                     "uart_health", "warning_active", "warning_text"};
            break;
        case DashboardPageV6::Nocturne:
            names = {"range", "speed", "uart_health", "warning_text"};
            break;
        case DashboardPageV6::Settings:
            names = {"appearance_text", "brightness_text", "clock_text",
                     "default_page_text", "developer_mode_text",
                     "speed_unit_text", "temperature_unit_text",
                     "tire_pressure_unit_text", "warning_sound_text"};
            break;
        case DashboardPageV6::Developer:
            names = {"commander_detail", "commander_link", "dev_commander",
                     "dev_frame", "dev_gear", "dev_hint", "dev_memory",
                     "dev_parser", "dev_soc", "dev_uart", "developer_mode",
                     "uart_health", "warning_active", "warning_text"};
            break;
        default:
            break;
    }
    std::sort(names.begin(), names.end());
    return names;
}

PageProjectionV6 buildPageProjectionV6(DashboardPageV6 page,
                                       const VehicleState& state,
                                       const ProductStateV6& product,
                                       const DashboardSettings& settings,
                                       const PageEnvironmentV6& environment) {
    PageProjectionV6 out;
    const auto put = [&out](const char* name, ProjectedValueV6 value) {
        out[name] = std::move(value);
    };

    // Every page with a warning path binds the same three names, so they are
    // built once from the environment rather than per page.
    const auto projectedWarningText = [&environment]() -> ProjectedValueV6 {
        if (!environment.warning.active) {
            return ProjectedValueV6::unavailable(ProjectedValueV6::Kind::Text);
        }
        const char* text = warningText(environment.warning.code);
        if (text[0] == '\0') {
            return ProjectedValueV6::unavailable(ProjectedValueV6::Kind::Text);
        }
        return textValue(text, SignalSource::Unavailable, SignalQuality::Confirmed);
    };
    const ProjectedValueV6 warning_text = projectedWarningText();
    const ProjectedValueV6 warning_active = ProjectedValueV6::makeFlag(
        environment.warning.active, SignalSource::Unavailable,
        SignalQuality::Confirmed);
    const ProjectedValueV6 uart_health = textValue(
        uartHealthText(environment), SignalSource::OriginalMcu,
        SignalQuality::Confirmed);

    const auto commanderLinkValue = [&environment]() -> ProjectedValueV6 {
        switch (environment.commander_status) {
            case CommanderLinkStatus::Linked:
                return ProjectedValueV6::makeNumber(1.0, Unit::None,
                                                SignalSource::Commander,
                                                SignalQuality::Confirmed);
            case CommanderLinkStatus::Searching:
            case CommanderLinkStatus::NoFrames:
            case CommanderLinkStatus::Stale:
                return ProjectedValueV6::makeNumber(0.0, Unit::None,
                                                SignalSource::Commander,
                                                SignalQuality::Inferred);
            case CommanderLinkStatus::Disabled:
            default:
                return ProjectedValueV6::unavailable(ProjectedValueV6::Kind::Number);
        }
    }();
    const ProjectedValueV6 commander_detail = [&environment]() -> ProjectedValueV6 {
        if (!environment.commander_detail_known ||
            environment.commander_status == CommanderLinkStatus::Disabled) {
            return ProjectedValueV6::unavailable(ProjectedValueV6::Kind::Text);
        }
        return textValue(environment.commander_detail, SignalSource::Commander,
                         SignalQuality::Confirmed);
    }();

    const auto gearValue = [&state]() -> ProjectedValueV6 {
        if (!live(state.gear) || state.gear.value == Gear::Unknown) {
            // The mapping is unconfirmed on this car, so "no letter" is the
            // only honest answer until a gear value has actually been decoded.
            return ProjectedValueV6::unavailable(ProjectedValueV6::Kind::Number);
        }
        return ProjectedValueV6::makeNumber(static_cast<double>(state.gear.value),
                                       Unit::None, state.gear.source,
                                       state.gear.quality);
    }();

    const auto closuresText = [&state]() -> ProjectedValueV6 {
        struct Door {
            const char* label;
            const Signal<bool>* signal;
        };
        const Door doors[] = {
            {"FL", &state.door_fl}, {"FR", &state.door_fr},
            {"RL", &state.door_rl}, {"RR", &state.door_rr},
            {"FRUNK", &state.frunk}, {"TRUNK", &state.trunk},
        };
        std::string open_list;
        bool any_open = false;
        bool any_unknown = false;
        for (const Door& door : doors) {
            bool open = false;
            bool known = true;
            readClosure(*door.signal, open, known);
            if (!known) {
                // UNKNOWN is not CLOSED: a door whose signal is missing must
                // not let the screen say every door is shut.
                any_unknown = true;
                continue;
            }
            if (open) {
                if (!open_list.empty()) open_list += " ";
                open_list += door.label;
                any_open = true;
            }
        }
        if (any_unknown) {
            return ProjectedValueV6::unavailable(ProjectedValueV6::Kind::Text);
        }
        if (!any_open) {
            return textValue("ALL CLOSED", SignalSource::OriginalMcu,
                             SignalQuality::Inferred);
        }
        return textValue("OPEN " + open_list, SignalSource::OriginalMcu,
                         SignalQuality::Confirmed);
    }();

    const auto closuresDetail = [&state]() -> ProjectedValueV6 {
        if (!live(state.door_fl) && !live(state.door_fr) && !live(state.door_rl) &&
            !live(state.door_rr) && !live(state.frunk) && !live(state.trunk)) {
            return ProjectedValueV6::unavailable(ProjectedValueV6::Kind::Text);
        }
        struct Door {
            const char* label;
            const Signal<bool>* signal;
        };
        const Door doors[] = {
            {"FL", &state.door_fl}, {"FR", &state.door_fr},
            {"RL", &state.door_rl}, {"RR", &state.door_rr},
            {"FRUNK", &state.frunk}, {"TRUNK", &state.trunk},
        };
        std::string text;
        for (const Door& door : doors) {
            bool open = false;
            bool known = true;
            readClosure(*door.signal, open, known);
            if (!text.empty()) text += "  ";
            text += door.label;
            text += " ";
            text += known ? (open ? "OPEN" : "SHUT") : "?";
        }
        return textValue(text, SignalSource::OriginalMcu, SignalQuality::Confirmed);
    }();

    const auto lightsDetail = [&state]() -> ProjectedValueV6 {
        struct Lamp {
            const char* on_text;
            const Signal<bool>* signal;
        };
        const Lamp lamps[] = {
            {"HEADLIGHT ON", &state.headlights},
            {"HIGH BEAM ON", &state.high_beam},
            {"RUNNING ON", &state.position_light},
            {"AUTO LIGHT", &state.auto_light},
            {"BRAKE ON", &state.brake_light},
            {"INDICATOR L", &state.turn_signal_left},
            {"INDICATOR R", &state.turn_signal_right},
            {"HAZARD ON", &state.hazards},
        };
        std::string text;
        bool any_known = false;
        for (const Lamp& lamp : lamps) {
            if (!live(*lamp.signal)) continue;
            any_known = true;
            if (!lamp.signal->value) continue;
            if (!text.empty()) text += " · ";
            text += lamp.on_text;
        }
        if (!any_known) {
            return ProjectedValueV6::unavailable(ProjectedValueV6::Kind::Text);
        }
        if (text.empty()) text = "ALL LIGHTS OFF";
        return textValue(text, SignalSource::OriginalMcu, SignalQuality::Confirmed);
    }();

    const auto tiresDetail = [&state]() -> ProjectedValueV6 {
        if (!live(state.tire_fl) && !live(state.tire_fr) && !live(state.tire_rl) &&
            !live(state.tire_rr)) {
            return ProjectedValueV6::unavailable(ProjectedValueV6::Kind::Text);
        }
        const auto wheel = [](const Signal<float>& signal) {
            char text[16];
            if (!live(signal)) return std::string("?");
            std::snprintf(text, sizeof(text), "%.2f",
                          static_cast<double>(signal.value));
            return std::string(text);
        };
        std::string text = "F " + wheel(state.tire_fl) + " " + wheel(state.tire_fr) +
                           " · R " + wheel(state.tire_rl) + " " + wheel(state.tire_rr) +
                           " bar";
        return textValue(text, SignalSource::OriginalMcu, SignalQuality::Confirmed);
    }();

    switch (page) {
        case DashboardPageV6::Horizon: {
            put("speed", fromSignal(state.speed, Unit::KilometerPerHour));
            put("gear", gearValue);
            put("range", fromSignal(state.range, Unit::Kilometer));
            put("actual_soc", fromSignal(state.actual_soc, Unit::Percent));
            put("temperature_primary",
                fromSignal(state.temperature_primary, Unit::Celsius));
            put("closures", closuresText);
            put("indicator_left", fromFlag(state.turn_signal_left));
            put("indicator_right", fromFlag(state.turn_signal_right));
            put("headlight", fromFlag(state.headlights));
            put("brake", fromFlag(state.brake_light));
            put("position_light", fromFlag(state.position_light));
            // The speed limit comes from the module (its own decoding of the
            // car's bus); an absent limit hides the sign rather than inventing
            // one, so this value is valid only when a limit was actually read.
            put("speed_limit", fromSignal(state.speed_limit, Unit::KilometerPerHour));
            // Navigation is a placeholder interface: with no route data the
            // pill hides itself and no instruction is produced.
            {
                const bool nav_usable = product.navigation.available &&
                                        product.navigation.has(
                                            NavigationCapability::BasicManeuver);
                const std::string maneuver =
                    nav_usable ? formatManeuverText(product.navigation) : std::string();
                put("nav_manoeuvre",
                    maneuver.empty()
                        ? ProjectedValueV6::unavailable(ProjectedValueV6::Kind::Text)
                        : textValue(maneuver, SignalSource::PhoneBridge,
                                    SignalQuality::Confirmed));
                put("nav_distance",
                    nav_usable ? fromSignal(product.navigation.next_turn_distance_m,
                                            Unit::None)
                               : ProjectedValueV6::unavailable());
                const std::string instruction =
                    nav_usable ? product.navigation.road_name : std::string();
                put("nav_instruction",
                    instruction.empty()
                        ? ProjectedValueV6::unavailable(ProjectedValueV6::Kind::Text)
                        : textValue(instruction, SignalSource::PhoneBridge,
                                    SignalQuality::Confirmed));
            }
            // One short driver-facing word, and only when it is true: READY
            // means the car is on and no warning is up. It is not a place for
            // link or protocol state.
            if (environment.warning.active) {
                put("driver_status_text",
                    ProjectedValueV6::unavailable(ProjectedValueV6::Kind::Text));
            } else if (live(state.speed)) {
                put("driver_status_text",
                    textValue("READY", SignalSource::OriginalMcu,
                              SignalQuality::Inferred));
            } else {
                put("driver_status_text",
                    ProjectedValueV6::unavailable(ProjectedValueV6::Kind::Text));
            }
            put("warning_text", warning_text);
            put("warning_active", warning_active);
            put("uart_health", uart_health);
            put("commander_link", commanderLinkValue);
            put("commander_detail", commander_detail);
            break;
        }
        case DashboardPageV6::Mono: {
            put("speed", fromSignal(state.speed, Unit::KilometerPerHour));
            put("gear", gearValue);
            put("range", fromSignal(state.range, Unit::Kilometer));
            put("closures", closuresText);
            put("indicator_left", fromFlag(state.turn_signal_left));
            put("indicator_right", fromFlag(state.turn_signal_right));
            put("headlight", fromFlag(state.headlights));
            put("brake", fromFlag(state.brake_light));
            put("warning_text", warning_text);
            put("warning_active", warning_active);
            put("uart_health", uart_health);
            break;
        }
        case DashboardPageV6::Pulse: {
            const ProjectedValueV6 power = fromSignal(state.battery_power, Unit::Kilowatt);
            put("speed", fromSignal(state.speed, Unit::KilometerPerHour));
            put("gear", gearValue);
            put("battery_power", power);
            // The bar needs a magnitude: a discharging pack is a negative
            // number, and a bar of a negative length is not a reading.
            if (power.valid) {
                const double magnitude =
                    power.number < 0.0 ? -power.number : power.number;
                put("battery_power_abs", ProjectedValueV6::makeNumber(
                        magnitude, Unit::Kilowatt, power.source,
                        power.quality));
            } else {
                put("battery_power_abs",
                    ProjectedValueV6::unavailable(ProjectedValueV6::Kind::Number));
            }
            put("accelerator_position",
                fromSignal(state.accelerator_position, Unit::Percent));
            put("indicator_left", fromFlag(state.turn_signal_left));
            put("indicator_right", fromFlag(state.turn_signal_right));
            put("headlight", fromFlag(state.headlights));
            put("brake", fromFlag(state.brake_light));
            put("warning_text", warning_text);
            put("warning_active", warning_active);
            put("uart_health", uart_health);
            put("commander_link", commanderLinkValue);
            put("commander_detail", commander_detail);
            break;
        }
        case DashboardPageV6::Route: {
            const bool nav_usable = product.navigation.available &&
                                    product.navigation.has(NavigationCapability::BasicManeuver);
            std::string maneuver;
            if (nav_usable) maneuver = formatManeuverText(product.navigation);
            put("nav_manoeuvre", maneuver.empty()
                    ? ProjectedValueV6::unavailable(ProjectedValueV6::Kind::Text)
                    : textValue(maneuver, SignalSource::PhoneBridge,
                                SignalQuality::Confirmed));
            put("nav_distance",
                nav_usable ? fromSignal(product.navigation.next_turn_distance_m, Unit::None)
                           : ProjectedValueV6::unavailable(ProjectedValueV6::Kind::Number));
            const std::string eta = nav_usable
                ? formatEta(environment, product.navigation.eta_epoch_s.valid
                                             ? product.navigation.eta_epoch_s.value : 0)
                : std::string();
            put("nav_eta", eta.empty()
                    ? ProjectedValueV6::unavailable(ProjectedValueV6::Kind::Text)
                    : textValue(eta, SignalSource::PhoneBridge, SignalQuality::Confirmed));
            put("nav_capability",
                nav_usable ? textValue(formatCapability(product.navigation.capabilities),
                                       SignalSource::PhoneBridge, SignalQuality::Inferred)
                           : ProjectedValueV6::unavailable(ProjectedValueV6::Kind::Text));
            if (environment.trip_known) {
                put("trip_distance", ProjectedValueV6::makeNumber(
                        environment.trip_distance_km, Unit::Kilometer,
                        SignalSource::OriginalMcu, SignalQuality::Inferred));
                put("trip_time_text", textValue(
                        formatDuration(environment.trip_duration_ms),
                        SignalSource::OriginalMcu, SignalQuality::Inferred));
                put("average_speed", ProjectedValueV6::makeNumber(
                        environment.trip_average_kph, Unit::KilometerPerHour,
                        SignalSource::OriginalMcu, SignalQuality::Inferred));
            } else {
                put("trip_distance", ProjectedValueV6::unavailable());
                put("trip_time_text",
                    ProjectedValueV6::unavailable(ProjectedValueV6::Kind::Text));
                put("average_speed", ProjectedValueV6::unavailable());
            }
            put("warning_text", warning_text);
            put("warning_active", warning_active);
            put("uart_health", uart_health);
            break;
        }
        case DashboardPageV6::Studio: {
            const ProjectedValueV6 closures = closuresDetail;
            put("closures_detail", closures.valid
                    ? closures
                    : ProjectedValueV6::unavailable(ProjectedValueV6::Kind::Text));
            put("lights_detail", lightsDetail);
            put("tires_detail", tiresDetail);
            put("gear", gearValue);
            put("door_fl", fromFlag(state.door_fl));
            put("door_fr", fromFlag(state.door_fr));
            put("door_rl", fromFlag(state.door_rl));
            put("door_rr", fromFlag(state.door_rr));
            put("frunk", fromFlag(state.frunk));
            put("trunk", fromFlag(state.trunk));
            put("headlight", fromFlag(state.headlights));
            put("brake", fromFlag(state.brake_light));
            put("indicator_left", fromFlag(state.turn_signal_left));
            put("indicator_right", fromFlag(state.turn_signal_right));
            put("warning_text", warning_text);
            put("warning_active", warning_active);
            put("uart_health", uart_health);
            put("commander_link", commanderLinkValue);
            put("commander_detail", commander_detail);
            break;
        }
        case DashboardPageV6::Energy: {
            put("actual_soc", fromSignal(state.actual_soc, Unit::Percent));
            put("range", fromSignal(state.range, Unit::Kilometer));
            put("battery_power", fromSignal(state.battery_power, Unit::Kilowatt));
            put("battery_voltage", fromSignal(state.battery_voltage, Unit::Volt));
            put("battery_current", fromSignal(state.battery_current, Unit::Ampere));
            put("total_charged_energy",
                fromSignal(state.total_charged_energy, Unit::KilowattHour));
            put("total_discharged_energy",
                fromSignal(state.total_discharged_energy, Unit::KilowattHour));
            put("warning_text", warning_text);
            put("warning_active", warning_active);
            put("uart_health", uart_health);
            put("commander_link", commanderLinkValue);
            put("commander_detail", commander_detail);
            break;
        }
        case DashboardPageV6::Nocturne: {
            put("speed", fromSignal(state.speed, Unit::KilometerPerHour));
            put("range", fromSignal(state.range, Unit::Kilometer));
            put("warning_text", warning_text);
            put("uart_health", uart_health);
            break;
        }
        case DashboardPageV6::Settings: {
            const char* appearance = "AUTO";
            switch (settings.appearance) {
                case AppearanceMode::Day: appearance = "DAY"; break;
                case AppearanceMode::Night: appearance = "NIGHT"; break;
                case AppearanceMode::Auto: default: appearance = "AUTO"; break;
            }
            char brightness[16];
            std::snprintf(brightness, sizeof(brightness), "%u %%",
                          static_cast<unsigned>(settings.brightness_percent));
            const char* speed_unit =
                settings.distance_unit == DistanceUnit::Mile ? "mph" : "km/h";
            const char* temperature_unit =
                settings.temperature_unit == TemperatureUnit::Fahrenheit ? "°F" : "°C";
            const char* tire_unit = "bar";
            switch (settings.tire_pressure_unit) {
                case TirePressureUnit::Psi: tire_unit = "psi"; break;
                case TirePressureUnit::Kpa: tire_unit = "kPa"; break;
                case TirePressureUnit::Bar: default: tire_unit = "bar"; break;
            }
            put("appearance_text", textValue(appearance, SignalSource::Unavailable,
                                             SignalQuality::Confirmed));
            put("brightness_text", textValue(brightness, SignalSource::Unavailable,
                                             SignalQuality::Confirmed));
            put("speed_unit_text", textValue(speed_unit, SignalSource::Unavailable,
                                             SignalQuality::Confirmed));
            put("temperature_unit_text", textValue(temperature_unit,
                                                   SignalSource::Unavailable,
                                                   SignalQuality::Confirmed));
            put("tire_pressure_unit_text",
                textValue(tire_unit, SignalSource::Unavailable,
                          SignalQuality::Confirmed));
            put("clock_text", textValue(settings.clock_24h ? "24 h" : "12 h",
                                        SignalSource::Unavailable,
                                        SignalQuality::Confirmed));
            // The Developer screen is not a page the instrument boots into, so
            // a default of Developer is refused rather than drawn as a choice.
            if (settings.default_page == DashboardPageV6::Developer) {
                put("default_page_text",
                    ProjectedValueV6::unavailable(ProjectedValueV6::Kind::Text));
            } else {
                put("default_page_text",
                    textValue(pageNameV6(settings.default_page),
                              SignalSource::Unavailable, SignalQuality::Confirmed));
            }
            put("warning_sound_text",
                textValue(settings.warning_sound_enabled ? "ON" : "OFF",
                          SignalSource::Unavailable, SignalQuality::Confirmed));
            put("developer_mode_text",
                textValue(settings.developer_mode_enabled ? "ON" : "OFF",
                          SignalSource::Unavailable, SignalQuality::Confirmed));
            break;
        }
        case DashboardPageV6::Developer: {
            char text[160];
            if (environment.uart_connected) {
                std::snprintf(text, sizeof(text), "%s · /dev/ttyS5 38400 · READ-ONLY",
                              uartHealthText(environment));
            } else {
                std::snprintf(text, sizeof(text), "UART LOST · /dev/ttyS5 38400 · READ-ONLY");
            }
            put("dev_uart", textValue(text, SignalSource::OriginalMcu,
                                      SignalQuality::Confirmed));
            if (environment.parser_stats_known) {
                std::snprintf(text, sizeof(text),
                              "%llu frames · %llu checksum errors · %llu unknown cmds",
                              static_cast<unsigned long long>(environment.parser_frames),
                              static_cast<unsigned long long>(environment.parser_checksum_errors),
                              static_cast<unsigned long long>(environment.parser_unknown_commands));
                put("dev_parser", textValue(text, SignalSource::OriginalMcu,
                                            SignalQuality::Confirmed));
            } else {
                put("dev_parser",
                    ProjectedValueV6::unavailable(ProjectedValueV6::Kind::Text));
            }
            if (environment.commander_status == CommanderLinkStatus::Disabled) {
                put("dev_commander", textValue(
                        "CMDR disabled · no override", SignalSource::Commander,
                        SignalQuality::Confirmed));
            } else {
                std::snprintf(text, sizeof(text), "CMDR %s · %s",
                              commanderLinkName(environment.commander_status),
                              live(state.actual_soc) ? "SOC override active"
                                                     : "no SOC from Commander");
                put("dev_commander", textValue(text, SignalSource::Commander,
                                               SignalQuality::Confirmed));
            }
            {
                std::string mcu = "--";
                if (state.soc.valid) {
                    mcu = std::to_string(static_cast<unsigned>(state.soc.value));
                }
                std::string commander = "--";
                if (live(state.actual_soc)) {
                    commander = std::to_string(
                        static_cast<unsigned>(state.actual_soc.value));
                }
                std::snprintf(text, sizeof(text),
                              "SOC: MCU %s (rejected) → Commander %s",
                              mcu.c_str(), commander.c_str());
                put("dev_soc", textValue(text, SignalSource::Unavailable,
                                         SignalQuality::Confirmed));
            }
            put("dev_gear", textValue(
                    gearValue.valid ? "GEAR: decoded value, mapping unconfirmed"
                                    : "GEAR: mapping unconfirmed (0x02 byte 3 LIKELY)",
                    SignalSource::Unavailable, SignalQuality::Inferred));
            if (environment.frame_stats_known) {
                std::snprintf(text, sizeof(text),
                              "frame %.1f ms · %.0f fps · budget %.1f ms",
                              static_cast<double>(environment.frame_ms),
                              static_cast<double>(environment.fps),
                              static_cast<double>(environment.frame_budget_ms));
                put("dev_frame", textValue(text, SignalSource::Unavailable,
                                           SignalQuality::Confirmed));
            } else {
                put("dev_frame",
                    ProjectedValueV6::unavailable(ProjectedValueV6::Kind::Text));
            }
            if (environment.memory_stats_known) {
                std::snprintf(text, sizeof(text), "RSS %.1f MB · resident assets %.1f MB",
                              static_cast<double>(environment.rss_kb) / 1024.0,
                              static_cast<double>(environment.resident_assets_kb) / 1024.0);
                put("dev_memory", textValue(text, SignalSource::Unavailable,
                                            SignalQuality::Confirmed));
            } else {
                put("dev_memory",
                    ProjectedValueV6::unavailable(ProjectedValueV6::Kind::Text));
            }
            put("dev_hint", textValue(
                    "DEV/REPLAY · replay and simulation only, never live vehicle data",
                    SignalSource::Unavailable, SignalQuality::Confirmed));
            put("developer_mode", ProjectedValueV6::makeFlag(
                    environment.developer_mode, SignalSource::Unavailable,
                    SignalQuality::Confirmed));
            put("commander_link", commanderLinkValue);
            put("commander_detail", commander_detail);
            put("warning_text", warning_text);
            put("warning_active", warning_active);
            put("uart_health", uart_health);
            break;
        }
        default:
            break;
    }
    return out;
}

std::string formatSceneTextV6(const std::string& format,
                              const ProjectedValueV6& value,
                              const std::string& invalid_text) {
    if (!value.valid) return invalid_text;

    std::string rendered;
    if (value.kind == ProjectedValueV6::Kind::Text) {
        rendered = value.text;
    } else if (value.kind == ProjectedValueV6::Kind::Flag) {
        rendered = value.flag ? "1" : "0";
    } else {
        char buffer[64];
        if (value.number == static_cast<double>(static_cast<long long>(value.number))) {
            std::snprintf(buffer, sizeof(buffer), "%lld",
                          static_cast<long long>(value.number));
        } else {
            std::snprintf(buffer, sizeof(buffer), "%.1f", value.number);
        }
        rendered = buffer;
    }

    const std::size_t placeholder = format.find('{');
    if (placeholder == std::string::npos) {
        // A scene may carry a static string in `text`; then `format` is not a
        // format at all and the value stands alone.
        return rendered;
    }
    const std::size_t close = format.find('}', placeholder);
    if (close == std::string::npos) return rendered;
    const std::string spec = format.substr(placeholder, close - placeholder + 1);

    char buffer[96];
    if (spec == "{}") {
        std::snprintf(buffer, sizeof(buffer), "%s", rendered.c_str());
    } else if (spec == "{:.1f}") {
        std::snprintf(buffer, sizeof(buffer), "%.1f", value.number);
    } else if (spec == "{:.0f}") {
        std::snprintf(buffer, sizeof(buffer), "%.0f", value.number);
    } else {
        std::snprintf(buffer, sizeof(buffer), "%s", rendered.c_str());
    }
    std::string out = format;
    out.replace(placeholder, close - placeholder + 1, buffer);
    return out;
}

}  // namespace dashboard
