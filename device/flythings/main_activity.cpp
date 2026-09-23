#include "main_activity.h"

#include "device_runtime.h"
#include "display_format.h"

#include <cstdio>
#include <ctime>
#include <string>

namespace {

constexpr int kRefreshTimer = 100;

// IDs recovered from the stock 1920x480 main.ftu binding code.
constexpr int kSpeedId = 0xc364;
constexpr int kRangeId = 0xc369;
constexpr int kSocId = 0xc399;
constexpr int kGearId = 0xc378;
constexpr int kDoorsId = 0xc35a;
constexpr int kTireFrontId = 0xc35f;
constexpr int kTireRearId = 0xc398;
constexpr int kClockId = 0xc38f;

char openMarker(const dashboard::Signal<bool>& value) {
    // Unknown is not closed: an unknown door renders as '?' rather than '-'.
    if (!value.valid || value.stale) {
        return '?';
    }
    return value.value ? 'O' : '-';
}

const char* sourceStatus(const dashboard::DataSourceHealth& health) {
    switch (health.status) {
        case dashboard::DataSourceStatus::Connected:
            return "DATA";
        case dashboard::DataSourceStatus::Connecting:
            return "WAIT";
        case dashboard::DataSourceStatus::Error:
            return "ERR";
        case dashboard::DataSourceStatus::Offline:
            return "STALE";
        case dashboard::DataSourceStatus::Disabled:
        default:
            return "OFF";
    }
}

// The value a page binds, or its placeholder. The device draws the same
// projection the Mac preview does, so "what the screen shows" has one rule.
std::string projected(const dashboard::PageProjectionV6& page,
                      const char* name, const std::string& format,
                      const std::string& invalid_text) {
    const auto it = page.find(name);
    if (it == page.end()) return invalid_text;
    return dashboard::formatSceneTextV6(format, it->second, invalid_text);
}

}  // namespace

REGISTER_ACTIVITY(mainActivity);

const char* mainActivity::getAppName() const {
    return "main.ftu";
}

void mainActivity::onCreate() {
    Activity::onCreate();
    speed_ = static_cast<ZKTextView*>(findControlByID(kSpeedId));
    range_ = static_cast<ZKTextView*>(findControlByID(kRangeId));
    soc_ = static_cast<ZKTextView*>(findControlByID(kSocId));
    gear_ = findControlByID(kGearId);
    doors_ = static_cast<ZKTextView*>(findControlByID(kDoorsId));
    tire_front_ = static_cast<ZKTextView*>(findControlByID(kTireFrontId));
    tire_rear_ = static_cast<ZKTextView*>(findControlByID(kTireRearId));
    clock_ = static_cast<ZKTextView*>(findControlByID(kClockId));
    registerTimer(kRefreshTimer, 100);
    updateDashboard();
}

void mainActivity::onResume() {
    Activity::onResume();
    updateDashboard();
}

bool mainActivity::onTimer(int id) {
    if (id == kRefreshTimer) {
        updateDashboard();
        return true;
    }
    return Activity::onTimer(id);
}

void mainActivity::updateDashboard() {
    const auto snapshot = dashboard::flythings::DeviceRuntime::instance().snapshot();
    char text[128];

    // Speed, gear, range, closures, lamps and tires are the car's own readings
    // and stay on the MCU path; only the enhanced fields are merged in, so the
    // Commander can add SOC without rewriting anything the cluster reads
    // directly.
    dashboard::VehicleState merged = snapshot.state;
    dashboard::mergeCommanderInto(merged, snapshot.commander_state);
    const dashboard::PageEnvironmentV6 environment =
        dashboard::flythings::buildDevicePageEnvironment(snapshot);
    const dashboard::DashboardSettings settings;
    const dashboard::PageProjectionV6 horizon = dashboard::buildPageProjectionV6(
        dashboard::DashboardPageV6::Horizon, merged, dashboard::ProductStateV6{},
        settings, environment);

    if (speed_ != nullptr) {
        speed_->setText(projected(horizon, "speed", "{}", "--").c_str());
    }
    if (range_ != nullptr) {
        range_->setText(projected(horizon, "range", "{} km", "-- km").c_str());
    }
    if (soc_ != nullptr) {
        // SOC comes from the Commander's actual_soc. The MCU's own SOC byte is
        // a rejected mapping on this car and is never printed as a percentage.
        soc_->setText(projected(horizon, "actual_soc", "{}%", "-- %").c_str());
    }
    if (gear_ != nullptr) {
        if (dashboard::flythings::gearIsDisplayable(snapshot.state.gear)) {
            gear_->setBackgroundPic(dashboard::flythings::gearPicturePath(
                snapshot.state.gear.value));
        }
        // An unknown gear deliberately changes nothing here: inventing "P"
        // would be a fabricated vehicle state. The gear state is reported in
        // the diagnostic line below instead, where "?" means unknown.
    }
    if (doors_ != nullptr) {
        const std::string closures = projected(horizon, "closures", "{}", "?");
        std::snprintf(
            text,
            sizeof(text),
            "%s | %c%c%c%c F%c T%c G:%s %s %s P:%llu CRC:%llu U:%llu C:%s %llu/%llu",
            closures.c_str(),
            openMarker(snapshot.state.door_fl),
            openMarker(snapshot.state.door_fr),
            openMarker(snapshot.state.door_rl),
            openMarker(snapshot.state.door_rr),
            openMarker(snapshot.state.frunk),
            openMarker(snapshot.state.trunk),
            dashboard::flythings::gearIsDisplayable(snapshot.state.gear)
                ? "shown" : "?",
            snapshot.uart_connected ? "UART" : "NO UART",
            sourceStatus(snapshot.health),
            static_cast<unsigned long long>(snapshot.parser.valid_packets),
            static_cast<unsigned long long>(snapshot.parser.checksum_errors),
            static_cast<unsigned long long>(snapshot.adapter.unknown_commands),
            dashboard::commanderLinkName(snapshot.commander_status),
            static_cast<unsigned long long>(snapshot.commander_stats.frames),
            static_cast<unsigned long long>(
                snapshot.commander_stats.checksum_errors));
        doors_->setText(text);
    }
    if (tire_front_ != nullptr) {
        tire_front_->setText(dashboard::flythings::formatTirePair(
            snapshot.state.tire_fl, snapshot.state.tire_fr, "F").c_str());
    }
    if (tire_rear_ != nullptr) {
        tire_rear_->setText(dashboard::flythings::formatTirePair(
            snapshot.state.tire_rl, snapshot.state.tire_rr, "R").c_str());
    }
    if (clock_ != nullptr) {
        const std::time_t now = std::time(nullptr);
        std::tm local{};
        localtime_r(&now, &local);
        std::strftime(text, sizeof(text), "%H:%M", &local);
        clock_->setText(text);
    }
}
