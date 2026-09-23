#include "dashboard/settings_store_v6.h"

// Keep the assertions live even in a Release build (NDEBUG).
#undef NDEBUG
#include <cassert>
#include <iostream>
#include <string>

using namespace dashboard;

namespace {

DashboardSettings nonDefaultSettings() {
    DashboardSettings settings;
    settings.appearance = AppearanceMode::Night;
    settings.brightness_percent = 65;
    settings.distance_unit = DistanceUnit::Mile;
    settings.temperature_unit = TemperatureUnit::Fahrenheit;
    settings.tire_pressure_unit = TirePressureUnit::Kpa;
    settings.clock_24h = false;
    settings.default_page = DashboardPageV6::Energy;
    settings.motion_quality = MotionQuality::Low;
    settings.warning_sound_enabled = false;
    settings.developer_mode_enabled = true;
    return settings;
}

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
    // A round trip keeps every field.
    {
        const DashboardSettings original = nonDefaultSettings();
        const std::string text = SettingsStoreV6::serialize(original);
        DashboardSettings loaded;
        assert(SettingsStoreV6::parse(text, loaded));
        assert(same(original, loaded));
        std::cout << "every setting survives a round trip\n";
    }

    // Unreadable input leaves the defaults rather than half-applying.
    {
        DashboardSettings settings = nonDefaultSettings();
        assert(!SettingsStoreV6::parse("", settings));
        assert(!SettingsStoreV6::parse("not a settings record", settings));
        assert(same(settings, nonDefaultSettings()));
        std::cout << "an empty or foreign record changes nothing\n";
    }

    // A newer build's field is ignored; the fields this build knows still load.
    {
        DashboardSettings settings;
        const std::string text = "v6-settings v1\nbrightness=44\nfuture_flag=on\n";
        assert(SettingsStoreV6::parse(text, settings));
        assert(settings.brightness_percent == 44);
        assert(settings.appearance == AppearanceMode::Auto);
        std::cout << "an unknown key does not fail the read\n";
    }

    // Brightness is clamped, never zeroed: a dark instrument is not a setting.
    {
        DashboardSettings settings;
        assert(SettingsStoreV6::parse("v6-settings v1\nbrightness=0\n", settings));
        assert(settings.brightness_percent == SettingsStoreV6::kMinBrightness);
        assert(SettingsStoreV6::parse("v6-settings v1\nbrightness=900\n", settings));
        assert(settings.brightness_percent == SettingsStoreV6::kMaxBrightness);
        std::cout << "brightness stays inside its usable range\n";
    }

    // Developer is not a page the instrument boots into.
    {
        DashboardSettings settings;
        assert(SettingsStoreV6::parse("v6-settings v1\ndefault_page=developer\n",
                                      settings));
        assert(settings.default_page == DashboardPageV6::Horizon);
        settings.default_page = DashboardPageV6::Developer;
        SettingsStoreV6::clamp(settings);
        assert(settings.default_page == DashboardPageV6::Horizon);
        std::cout << "the developer screen cannot be the default page\n";
    }

    // Every page except Developer is a legal default, including by name.
    {
        const char* names[] = {"horizon", "mono", "pulse", "route",
                               "studio",  "energy", "nocturne", "settings"};
        const DashboardPageV6 expected[] = {
            DashboardPageV6::Horizon, DashboardPageV6::Mono,
            DashboardPageV6::Pulse,   DashboardPageV6::Route,
            DashboardPageV6::Studio,  DashboardPageV6::Energy,
            DashboardPageV6::Nocturne, DashboardPageV6::Settings};
        for (std::size_t i = 0; i < sizeof(names) / sizeof(names[0]); ++i) {
            DashboardSettings settings;
            const std::string text = std::string("v6-settings v1\ndefault_page=") +
                                     names[i] + "\n";
            assert(SettingsStoreV6::parse(text, settings));
            assert(settings.default_page == expected[i]);
        }
        std::cout << "each page name is accepted as a default\n";
    }

    std::cout << "all settings store checks passed\n";
    return 0;
}
