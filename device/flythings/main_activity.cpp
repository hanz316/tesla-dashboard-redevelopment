#include "main_activity.h"

#include "device_runtime.h"

#include <cstdio>
#include <ctime>
#include <cstring>

namespace {

constexpr int kRefreshTimer = 100;
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
        case dashboard::Gear::Park: return "/home/white_gears_p.png";
        case dashboard::Gear::Reverse: return "/home/white_gears_r.png";
        case dashboard::Gear::Neutral: return "/home/white_gears_n.png";
        case dashboard::Gear::Drive: return "/home/white_gears_d.png";
        case dashboard::Gear::Unknown:
        default: return nullptr;
    }
}

bool closuresValid(const dashboard::VehicleState& state) {
    return state.door_fl.valid && state.door_fr.valid &&
        state.door_rl.valid && state.door_rr.valid &&
        state.frunk.valid && state.trunk.valid;
}

bool anyClosureOpen(const dashboard::VehicleState& state) {
    return state.door_fl.value || state.door_fr.value ||
        state.door_rl.value || state.door_rr.value ||
        state.frunk.value || state.trunk.value;
}

const char* uartLabel(const dashboard::flythings::RuntimeSnapshot& snapshot) {
    if (!snapshot.uart_connected) return "UART LOST";
    if (!snapshot.has_rx) return "UART WAIT";
    return snapshot.uart_healthy ? "UART OK" : "UART STALE";
}

void appendClosure(char* text, std::size_t size, const char* label, const dashboard::Signal<bool>& signal) {
    if (!signal.value) return;
    const std::size_t used = std::strlen(text);
    if (used < size) std::snprintf(text + used, size - used, " %s", label);
}

}  // namespace

REGISTER_ACTIVITY(mainActivity);

const char* mainActivity::getAppName() const { return "main.ftu"; }

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
        if (snapshot.state.speed.valid) std::snprintf(text, sizeof(text), "%u", snapshot.state.speed.value);
        else std::snprintf(text, sizeof(text), "--");
        speed_->setText(text);
    }
    if (range_ != nullptr) {
        if (snapshot.state.range.valid) std::snprintf(text, sizeof(text), "%u km", snapshot.state.range.value);
        else std::snprintf(text, sizeof(text), "-- km");
        range_->setText(text);
    }
    if (soc_ != nullptr) {
        if (snapshot.state.soc.valid) std::snprintf(text, sizeof(text), "%u%%", static_cast<unsigned>(snapshot.state.soc.value));
        else std::snprintf(text, sizeof(text), "--%%");
        soc_->setText(text);
    }
    if (gear_ != nullptr) {
        const char* picture = snapshot.state.gear.valid ? gearPicture(snapshot.state.gear.value) : nullptr;
        gear_->setBackgroundPic(picture != nullptr ? picture : "");
    }
    if (doors_ != nullptr) {
        if (!closuresValid(snapshot.state)) {
            std::snprintf(text, sizeof(text), "DOORS --  %s", uartLabel(snapshot));
        } else if (!anyClosureOpen(snapshot.state)) {
            std::snprintf(text, sizeof(text), "ALL CLOSED  %s", uartLabel(snapshot));
        } else {
            std::snprintf(text, sizeof(text), "OPEN");
            appendClosure(text, sizeof(text), "FL", snapshot.state.door_fl);
            appendClosure(text, sizeof(text), "FR", snapshot.state.door_fr);
            appendClosure(text, sizeof(text), "RL", snapshot.state.door_rl);
            appendClosure(text, sizeof(text), "RR", snapshot.state.door_rr);
            appendClosure(text, sizeof(text), "FRUNK", snapshot.state.frunk);
            appendClosure(text, sizeof(text), "TRUNK", snapshot.state.trunk);
            const std::size_t used = std::strlen(text);
            if (used < sizeof(text)) std::snprintf(text + used, sizeof(text) - used, "  %s", uartLabel(snapshot));
        }
        doors_->setText(text);
    }
    if (tire_front_ != nullptr) {
        if (snapshot.state.tire_fl.valid && snapshot.state.tire_fr.valid) {
            std::snprintf(text, sizeof(text), "FL %.2f  FR %.2f bar", snapshot.state.tire_fl.value, snapshot.state.tire_fr.value);
        } else if (snapshot.state.tire_fl.valid) {
            std::snprintf(text, sizeof(text), "FL %.2f  FR -- bar", snapshot.state.tire_fl.value);
        } else if (snapshot.state.tire_fr.valid) {
            std::snprintf(text, sizeof(text), "FL --  FR %.2f bar", snapshot.state.tire_fr.value);
        } else {
            std::snprintf(text, sizeof(text), "FL --  FR -- bar");
        }
        tire_front_->setText(text);
    }
    if (tire_rear_ != nullptr) {
        if (snapshot.state.tire_rl.valid && snapshot.state.tire_rr.valid) {
            std::snprintf(text, sizeof(text), "RL %.2f  RR %.2f bar", snapshot.state.tire_rl.value, snapshot.state.tire_rr.value);
        } else if (snapshot.state.tire_rl.valid) {
            std::snprintf(text, sizeof(text), "RL %.2f  RR -- bar", snapshot.state.tire_rl.value);
        } else if (snapshot.state.tire_rr.valid) {
            std::snprintf(text, sizeof(text), "RL --  RR %.2f bar", snapshot.state.tire_rr.value);
        } else {
            std::snprintf(text, sizeof(text), "RL --  RR -- bar");
        }
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
