#include "main_activity.h"

#include "device_runtime.h"

#include <cstdio>
#include <ctime>

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

const char* gearPicture(dashboard::Gear gear) {
    switch (gear) {
        case dashboard::Gear::Park:
            return "/home/white_gears_p.png";
        case dashboard::Gear::Reverse:
            return "/home/white_gears_r.png";
        case dashboard::Gear::Neutral:
            return "/home/white_gears_n.png";
        case dashboard::Gear::Drive:
            return "/home/white_gears_d.png";
        case dashboard::Gear::Unknown:
        default:
            return nullptr;
    }
}

char openMarker(const dashboard::Signal<bool>& value) {
    return value.valid && value.value ? 'O' : '-';
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

    if (speed_ != nullptr) {
        std::snprintf(
            text,
            sizeof(text),
            "%u",
            snapshot.state.speed.valid ? snapshot.state.speed.value : 0U);
        speed_->setText(text);
    }
    if (range_ != nullptr) {
        std::snprintf(
            text,
            sizeof(text),
            "%u km",
            snapshot.state.range.valid ? snapshot.state.range.value : 0U);
        range_->setText(text);
    }
    if (soc_ != nullptr) {
        std::snprintf(
            text,
            sizeof(text),
            "%u%%",
            snapshot.state.soc.valid
                ? static_cast<unsigned>(snapshot.state.soc.value)
                : 0U);
        soc_->setText(text);
    }
    if (gear_ != nullptr && snapshot.state.gear.valid) {
        const char* picture = gearPicture(snapshot.state.gear.value);
        if (picture != nullptr) {
            gear_->setBackgroundPic(picture);
        }
    }
    if (doors_ != nullptr) {
        std::snprintf(
            text,
            sizeof(text),
            "Doors %c%c%c%c F%c T%c %s P:%llu CRC:%llu U:%llu",
            openMarker(snapshot.state.door_fl),
            openMarker(snapshot.state.door_fr),
            openMarker(snapshot.state.door_rl),
            openMarker(snapshot.state.door_rr),
            openMarker(snapshot.state.frunk),
            openMarker(snapshot.state.trunk),
            snapshot.uart_connected ? "UART" : "NO UART",
            static_cast<unsigned long long>(snapshot.parser.valid_packets),
            static_cast<unsigned long long>(snapshot.parser.checksum_errors),
            static_cast<unsigned long long>(snapshot.adapter.unknown_commands));
        doors_->setText(text);
    }
    if (tire_front_ != nullptr) {
        std::snprintf(
            text,
            sizeof(text),
            "F %.2f %.2f bar",
            snapshot.state.tire_fl.valid ? snapshot.state.tire_fl.value : 0.0F,
            snapshot.state.tire_fr.valid ? snapshot.state.tire_fr.value : 0.0F);
        tire_front_->setText(text);
    }
    if (tire_rear_ != nullptr) {
        std::snprintf(
            text,
            sizeof(text),
            "R %.2f %.2f bar",
            snapshot.state.tire_rl.valid ? snapshot.state.tire_rl.value : 0.0F,
            snapshot.state.tire_rr.valid ? snapshot.state.tire_rr.value : 0.0F);
        tire_rear_->setText(text);
    }
    if (clock_ != nullptr) {
        const std::time_t now = std::time(nullptr);
        std::tm local{};
        localtime_r(&now, &local);
        std::strftime(text, sizeof(text), "%H:%M", &local);
        clock_->setText(text);
    }
}
