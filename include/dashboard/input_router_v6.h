#pragma once

#include "dashboard/settings_store_v6.h"
#include "dashboard/ui_framework_v6.h"

#include <cstdint>
#include <vector>

namespace dashboard {

// Input on the instrument is four things: swipe between pages, tap a setting,
// tap to wake, and nothing else. There are no menus, no drag sliders and no
// on-screen keyboard, so the whole input surface can be described and tested
// without a touch screen attached.
//
// The hit boxes below come from scenes/v6_settings.scene. They are listed here
// rather than parsed so the editor and the layout can be checked against each
// other (tests/v6_pages_tests.py compares them with the scene).

enum class SettingRowV6 : std::uint8_t {
    Appearance = 0,
    Brightness,
    SpeedUnit,
    TemperatureUnit,
    TirePressureUnit,
    Clock,
    DefaultPage,
    WarningSound,
    DeveloperMode,
};

constexpr int kSettingRowCountV6 = 9;

struct SettingRowBoxV6 {
    SettingRowV6 row{SettingRowV6::Appearance};
    const char* label{""};
    int x{0};
    int y{0};
    int width{0};
    int height{0};
};

// The rows as they are laid out, in reading order (left column then right).
std::vector<SettingRowBoxV6> settingsRowsV6();

// Which setting a tap at (x, y) selects, or -1 when the tap hits no row.
int settingRowAtV6(int x, int y);

// Cycles a setting by one step. `direction` is +1 or -1; a zero step is a
// no-op. Every result is clamped, so the editor cannot produce a state the
// store would refuse to load (a black brightness, Developer as the default
// page).
bool cycleSettingV6(DashboardSettings& settings, SettingRowV6 row,
                    int direction);

// A swipe is a horizontal gesture past this many pixels. Below it, the gesture
// is not a page change: a brush against the screen must not swap the
// instrument's page while the car is moving.
constexpr int kSwipeThresholdPx{120};

// +1 for the next page, -1 for the previous one, 0 when the gesture is too
// small to mean either. The content follows the finger: a drag to the left
// (dx < 0) brings the next page in, a drag to the right (dx > 0) the previous.
int swipeStepV6(int dx, int dy, int threshold = kSwipeThresholdPx);

enum class InputActionKindV6 : std::uint8_t {
    None = 0,
    StepPage,
    ChangeSetting,
};

struct InputActionV6 {
    InputActionKindV6 kind{InputActionKindV6::None};
    int step{0};                                  // StepPage
    SettingRowV6 row{SettingRowV6::Appearance};    // ChangeSetting
    int direction{0};                              // ChangeSetting
};

// What a horizontal gesture means on a page. A swipe always changes pages,
// including on Settings, because the page ring is the only way between
// screens; the setting rows are stepped by tapping them.
InputActionV6 routeSwipeV6(DashboardPageV6 page, int dx, int dy);

// What a tap means on a page.
InputActionV6 routeTapV6(DashboardPageV6 page, int x, int y);

}  // namespace dashboard
