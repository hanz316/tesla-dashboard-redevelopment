#include "dashboard/input_router_v6.h"

#include "dashboard/page_projection_v6.h"

// Keep the assertions live even in a Release build (NDEBUG).
#undef NDEBUG
#include <cassert>
#include <iostream>
#include <set>

using namespace dashboard;

namespace {

bool same(const DashboardSettings& a, const DashboardSettings& b) {
    return a.appearance == b.appearance &&
           a.brightness_percent == b.brightness_percent &&
           a.distance_unit == b.distance_unit &&
           a.temperature_unit == b.temperature_unit &&
           a.tire_pressure_unit == b.tire_pressure_unit &&
           a.clock_24h == b.clock_24h &&
           a.default_page == b.default_page &&
           a.motion_quality == b.motion_quality &&
           a.warning_sound_enabled == b.warning_sound_enabled &&
           a.developer_mode_enabled == b.developer_mode_enabled;
}

}  // namespace

int main() {
    // Every setting can be stepped, one step changes it, and two steps forward
    // followed by two back return to where it started.
    {
        const auto rows = settingsRowsV6();
        assert(rows.size() == kSettingRowCountV6);
        std::set<int> seen;
        for (const SettingRowBoxV6& row : rows) {
            seen.insert(static_cast<int>(row.row));
            DashboardSettings original;
            // Brightness starts at its maximum, so a step up would clamp and
            // look like "nothing happened". Start it mid-range instead.
            original.brightness_percent = 60;
            DashboardSettings stepped = original;
            assert(cycleSettingV6(stepped, row.row, 1));
            assert(!same(stepped, original));
            assert(cycleSettingV6(stepped, row.row, 1));
            assert(cycleSettingV6(stepped, row.row, -1));
            assert(cycleSettingV6(stepped, row.row, -1));
            assert(same(stepped, original));
        }
        assert(seen.size() == static_cast<std::size_t>(kSettingRowCountV6));
        std::cout << "all nine settings are steppable\n";
    }

    // Brightness clamps in both directions and never reaches zero.
    {
        DashboardSettings settings;
        settings.brightness_percent = SettingsStoreV6::kMaxBrightness;
        assert(cycleSettingV6(settings, SettingRowV6::Brightness, 1));
        assert(settings.brightness_percent == SettingsStoreV6::kMaxBrightness);
        for (int i = 0; i < 40; ++i) {
            cycleSettingV6(settings, SettingRowV6::Brightness, -1);
        }
        assert(settings.brightness_percent == SettingsStoreV6::kMinBrightness);
        std::cout << "brightness clamps and never goes black\n";
    }

    // The default page cycles through the pages a driver can reach, and never
    // through the Developer screen.
    {
        DashboardSettings settings;
        const auto ring = swipeOrderV6();
        for (std::size_t i = 0; i < ring.size(); ++i) {
            assert(settings.default_page != DashboardPageV6::Developer);
            assert(cycleSettingV6(settings, SettingRowV6::DefaultPage, 1));
        }
        assert(settings.default_page == DashboardPageV6::Horizon);
        std::cout << "default page cycles the ring without Developer\n";
    }

    // Developer mode can be turned on and off.
    {
        DashboardSettings settings;
        assert(!settings.developer_mode_enabled);
        assert(cycleSettingV6(settings, SettingRowV6::DeveloperMode, 1));
        assert(settings.developer_mode_enabled);
        assert(cycleSettingV6(settings, SettingRowV6::DeveloperMode, -1));
        assert(!settings.developer_mode_enabled);
        std::cout << "developer mode toggles\n";
    }

    // A tap maps to the setting drawn at that point, and only on Settings.
    {
        assert(settingRowAtV6(400, 140) == static_cast<int>(SettingRowV6::Appearance));
        assert(settingRowAtV6(1400, 326) == static_cast<int>(SettingRowV6::DeveloperMode));
        assert(settingRowAtV6(960, 480) == -1);   // below the last row
        assert(settingRowAtV6(900, 140) == -1);   // between the two columns
        const InputActionV6 tap =
            routeTapV6(DashboardPageV6::Settings, 400, 140);
        assert(tap.kind == InputActionKindV6::ChangeSetting);
        assert(tap.row == SettingRowV6::Appearance);
        // A tap on a driving page is not a setting change.
        assert(routeTapV6(DashboardPageV6::Horizon, 400, 140).kind ==
               InputActionKindV6::None);
        std::cout << "taps reach the setting they land on\n";
    }

    // Swipes change pages past a threshold and never on a small brush.
    {
        // The content follows the finger: drag left -> next page.
        assert(swipeStepV6(-200, 10) == 1);
        assert(swipeStepV6(200, 10) == -1);
        assert(swipeStepV6(80, 0) == 0);
        assert(swipeStepV6(300, 320) == 0);
        const InputActionV6 forward =
            routeSwipeV6(DashboardPageV6::Horizon, -250, 5);
        assert(forward.kind == InputActionKindV6::StepPage && forward.step == 1);
        assert(routeSwipeV6(DashboardPageV6::Settings, 250, 5).step == -1);
        assert(routeSwipeV6(DashboardPageV6::Horizon, 5, 5).kind ==
               InputActionKindV6::None);
        std::cout << "swipes step pages past the threshold only\n";
    }

    // The editor and the page ring agree: a stepped setting always renders.
    {
        DashboardSettings settings;
        PageEnvironmentV6 environment;
        VehicleState state;
        for (int i = 0; i < 12; ++i) {
            cycleSettingV6(settings, SettingRowV6::DefaultPage, 1);
            const PageProjectionV6 page = buildPageProjectionV6(
                DashboardPageV6::Settings, state, ProductStateV6{}, settings,
                environment);
            assert(page.at("default_page_text").valid);
        }
        std::cout << "an edited setting always renders on the settings page\n";
    }

    std::cout << "all input router checks passed\n";
    return 0;
}
