#include "dashboard/settings_store_v6.h"

#include "dashboard/page_projection_v6.h"

#include <algorithm>
#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <sstream>
#include <vector>

namespace dashboard {
namespace {

const char* appearanceName(AppearanceMode mode) {
    switch (mode) {
        case AppearanceMode::Day: return "day";
        case AppearanceMode::Night: return "night";
        case AppearanceMode::Auto: default: return "auto";
    }
}

const char* motionName(MotionQuality quality) {
    switch (quality) {
        case MotionQuality::Off: return "off";
        case MotionQuality::Low: return "low";
        case MotionQuality::Full: default: return "full";
    }
}

bool parseAppearance(const std::string& value, AppearanceMode& out) {
    if (value == "day") { out = AppearanceMode::Day; return true; }
    if (value == "night") { out = AppearanceMode::Night; return true; }
    if (value == "auto") { out = AppearanceMode::Auto; return true; }
    return false;
}

bool parseMotion(const std::string& value, MotionQuality& out) {
    if (value == "off") { out = MotionQuality::Off; return true; }
    if (value == "low") { out = MotionQuality::Low; return true; }
    if (value == "full") { out = MotionQuality::Full; return true; }
    return false;
}

bool parseBool(const std::string& value, bool& out) {
    if (value == "1" || value == "on" || value == "true") { out = true; return true; }
    if (value == "0" || value == "off" || value == "false") { out = false; return true; }
    return false;
}

bool parsePage(const std::string& value, DashboardPageV6& out) {
    const DashboardPageV6 pages[] = {
        DashboardPageV6::Horizon, DashboardPageV6::Mono,
        DashboardPageV6::Pulse,   DashboardPageV6::Route,
        DashboardPageV6::Studio,  DashboardPageV6::Energy,
        DashboardPageV6::Nocturne, DashboardPageV6::Settings,
        DashboardPageV6::Developer,
    };
    for (DashboardPageV6 page : pages) {
        const char* name = pageNameV6(page);
        std::string lowered;
        for (const char* c = name; *c != '\0'; ++c) {
            lowered += static_cast<char>(std::tolower(static_cast<unsigned char>(*c)));
        }
        if (value == lowered) {
            out = page;
            return true;
        }
    }
    return false;
}

std::vector<std::string> split(const std::string& text, char separator) {
    std::vector<std::string> parts;
    std::string current;
    for (char c : text) {
        if (c == separator) {
            parts.push_back(current);
            current.clear();
            continue;
        }
        if (c == '\n' || c == '\r') continue;
        current += c;
    }
    parts.push_back(current);
    return parts;
}

std::string pageNameLower(DashboardPageV6 page) {
    std::string lowered;
    for (const char* c = pageNameV6(page); *c != '\0'; ++c) {
        lowered += static_cast<char>(std::tolower(static_cast<unsigned char>(*c)));
    }
    return lowered;
}

}  // namespace

std::string SettingsStoreV6::serialize(const DashboardSettings& settings) {
    std::ostringstream out;
    out << "v6-settings v1\n";
    out << "appearance=" << appearanceName(settings.appearance) << "\n";
    out << "brightness=" << static_cast<unsigned>(settings.brightness_percent) << "\n";
    out << "distance_unit="
        << (settings.distance_unit == DistanceUnit::Mile ? "mile" : "km") << "\n";
    out << "temperature_unit="
        << (settings.temperature_unit == TemperatureUnit::Fahrenheit ? "f" : "c")
        << "\n";
    out << "tire_pressure_unit=";
    switch (settings.tire_pressure_unit) {
        case TirePressureUnit::Psi: out << "psi"; break;
        case TirePressureUnit::Kpa: out << "kpa"; break;
        case TirePressureUnit::Bar: default: out << "bar"; break;
    }
    out << "\n";
    out << "clock=" << (settings.clock_24h ? "24" : "12") << "\n";
    out << "default_page=" << pageNameLower(settings.default_page) << "\n";
    out << "motion=" << motionName(settings.motion_quality) << "\n";
    out << "warning_sound=" << (settings.warning_sound_enabled ? 1 : 0) << "\n";
    out << "developer_mode=" << (settings.developer_mode_enabled ? 1 : 0) << "\n";
    return out.str();
}

bool SettingsStoreV6::parse(const std::string& text, DashboardSettings& out) {
    if (text.empty()) return false;
    bool saw_record = false;
    for (const std::string& raw_line : split(text, '\n')) {
        const std::size_t equals = raw_line.find('=');
        if (equals == std::string::npos) continue;
        const std::string key = raw_line.substr(0, equals);
        const std::string value = raw_line.substr(equals + 1);
        saw_record = true;

        if (key == "appearance") {
            AppearanceMode mode;
            if (parseAppearance(value, mode)) out.appearance = mode;
        } else if (key == "brightness") {
            const long parsed = std::strtol(value.c_str(), nullptr, 10);
            // A stored 0 is clamped up, not ignored: the driver did set
            // something, and the floor is what keeps the panel readable.
            if (parsed >= 0) {
                out.brightness_percent = static_cast<std::uint8_t>(
                    std::min<long>(parsed, 255L));
            }
        } else if (key == "distance_unit") {
            if (value == "mile") out.distance_unit = DistanceUnit::Mile;
            else if (value == "km") out.distance_unit = DistanceUnit::Kilometer;
        } else if (key == "temperature_unit") {
            if (value == "f") out.temperature_unit = TemperatureUnit::Fahrenheit;
            else if (value == "c") out.temperature_unit = TemperatureUnit::Celsius;
        } else if (key == "tire_pressure_unit") {
            if (value == "psi") out.tire_pressure_unit = TirePressureUnit::Psi;
            else if (value == "kpa") out.tire_pressure_unit = TirePressureUnit::Kpa;
            else if (value == "bar") out.tire_pressure_unit = TirePressureUnit::Bar;
        } else if (key == "clock") {
            if (value == "24") out.clock_24h = true;
            else if (value == "12") out.clock_24h = false;
        } else if (key == "default_page") {
            DashboardPageV6 page;
            if (parsePage(value, page)) out.default_page = page;
        } else if (key == "motion") {
            MotionQuality quality;
            if (parseMotion(value, quality)) out.motion_quality = quality;
        } else if (key == "warning_sound") {
            bool enabled;
            if (parseBool(value, enabled)) out.warning_sound_enabled = enabled;
        } else if (key == "developer_mode") {
            bool enabled;
            if (parseBool(value, enabled)) out.developer_mode_enabled = enabled;
        }
    }
    if (!saw_record) return false;
    clamp(out);
    return true;
}

void SettingsStoreV6::clamp(DashboardSettings& settings) {
    settings.brightness_percent = std::max<std::uint8_t>(
        kMinBrightness, std::min<std::uint8_t>(kMaxBrightness,
                                               settings.brightness_percent));
    if (settings.default_page == DashboardPageV6::Developer) {
        settings.default_page = DashboardPageV6::Horizon;
    }
}

}  // namespace dashboard
