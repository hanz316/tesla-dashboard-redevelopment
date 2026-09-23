#include "dashboard/input_router_v6.h"

#include <cstdlib>

namespace dashboard {
namespace {

constexpr int kRowHeight = 52;

SettingRowBoxV6 box(SettingRowV6 row, const char* label, int x, int text_y) {
    SettingRowBoxV6 out;
    out.row = row;
    out.label = label;
    out.x = x;
    out.width = 680;
    out.height = kRowHeight;
    out.y = text_y - kRowHeight / 2;
    return out;
}

int sign(int value) { return value > 0 ? 1 : (value < 0 ? -1 : 0); }

int wrapIndex(int index, int size) {
    return ((index % size) + size) % size;
}

}  // namespace

std::vector<SettingRowBoxV6> settingsRowsV6() {
    // Matches scenes/v6_settings.scene: five rows in the left column, four in
    // the right. The box is the whole band (label and value), because a driver
    // aiming at "brightness" does not aim at one word.
    return {
        box(SettingRowV6::Appearance, "APPEARANCE", 160, 140),
        box(SettingRowV6::Brightness, "BRIGHTNESS", 160, 202),
        box(SettingRowV6::SpeedUnit, "SPEED UNIT", 160, 264),
        box(SettingRowV6::TemperatureUnit, "TEMPERATURE", 160, 326),
        box(SettingRowV6::TirePressureUnit, "TIRE PRESSURE", 160, 388),
        box(SettingRowV6::Clock, "CLOCK", 960, 140),
        box(SettingRowV6::DefaultPage, "DEFAULT PAGE", 960, 202),
        box(SettingRowV6::WarningSound, "WARNING SOUND", 960, 264),
        box(SettingRowV6::DeveloperMode, "DEVELOPER MODE", 960, 326),
    };
}

int settingRowAtV6(int x, int y) {
    const auto rows = settingsRowsV6();
    for (std::size_t i = 0; i < rows.size(); ++i) {
        const SettingRowBoxV6& row = rows[i];
        if (x >= row.x && x <= row.x + row.width &&
            y >= row.y && y <= row.y + row.height) {
            return static_cast<int>(i);
        }
    }
    return -1;
}

bool cycleSettingV6(DashboardSettings& settings, SettingRowV6 row, int direction) {
    if (direction == 0) return false;
    const int step = sign(direction);
    switch (row) {
        case SettingRowV6::Appearance: {
            const int count = 3;
            const int next = wrapIndex(static_cast<int>(settings.appearance) + step,
                                       count);
            settings.appearance = static_cast<AppearanceMode>(next);
            break;
        }
        case SettingRowV6::Brightness: {
            // A tap moves brightness in 10 % steps and lands on the clamp, so
            // the screen can always be brought back up.
            const int next = static_cast<int>(settings.brightness_percent) + 10 * step;
            const int clamped = next < static_cast<int>(SettingsStoreV6::kMinBrightness)
                ? SettingsStoreV6::kMinBrightness
                : (next > static_cast<int>(SettingsStoreV6::kMaxBrightness)
                       ? SettingsStoreV6::kMaxBrightness
                       : next);
            settings.brightness_percent = static_cast<std::uint8_t>(clamped);
            break;
        }
        case SettingRowV6::SpeedUnit:
            settings.distance_unit = settings.distance_unit == DistanceUnit::Kilometer
                ? DistanceUnit::Mile : DistanceUnit::Kilometer;
            break;
        case SettingRowV6::TemperatureUnit:
            settings.temperature_unit =
                settings.temperature_unit == TemperatureUnit::Celsius
                    ? TemperatureUnit::Fahrenheit : TemperatureUnit::Celsius;
            break;
        case SettingRowV6::TirePressureUnit: {
            const int next = wrapIndex(static_cast<int>(settings.tire_pressure_unit) + step,
                                       3);
            settings.tire_pressure_unit = static_cast<TirePressureUnit>(next);
            break;
        }
        case SettingRowV6::Clock:
            settings.clock_24h = !settings.clock_24h;
            break;
        case SettingRowV6::DefaultPage: {
            const std::vector<DashboardPageV6> ring = swipeOrderV6();
            int index = 0;
            for (std::size_t i = 0; i < ring.size(); ++i) {
                if (ring[i] == settings.default_page) {
                    index = static_cast<int>(i);
                    break;
                }
            }
            // The ring is exactly the pages a driver can land on, so cycling
            // through it can never offer the Developer screen as a default.
            settings.default_page =
                ring[static_cast<std::size_t>(wrapIndex(index + step,
                                                        static_cast<int>(ring.size())))];
            break;
        }
        case SettingRowV6::WarningSound:
            settings.warning_sound_enabled = !settings.warning_sound_enabled;
            break;
        case SettingRowV6::DeveloperMode:
            settings.developer_mode_enabled = !settings.developer_mode_enabled;
            break;
        default:
            return false;
    }
    SettingsStoreV6::clamp(settings);
    return true;
}

int swipeStepV6(int dx, int dy, int threshold) {
    const int magnitude = std::abs(dx);
    if (magnitude < threshold) return 0;
    // A mostly-vertical gesture is not a page change, however far it travelled.
    if (std::abs(dy) > magnitude) return 0;
    return dx > 0 ? -1 : 1;
}

InputActionV6 routeSwipeV6(DashboardPageV6 page, int dx, int dy) {
    (void)page;
    InputActionV6 action;
    const int step = swipeStepV6(dx, dy);
    if (step == 0) return action;
    action.kind = InputActionKindV6::StepPage;
    action.step = step;
    return action;
}

InputActionV6 routeTapV6(DashboardPageV6 page, int x, int y) {
    InputActionV6 action;
    if (page != DashboardPageV6::Settings) return action;
    const int row = settingRowAtV6(x, y);
    if (row < 0) return action;
    action.kind = InputActionKindV6::ChangeSetting;
    action.row = static_cast<SettingRowV6>(row);
    action.direction = 1;
    return action;
}

}  // namespace dashboard
