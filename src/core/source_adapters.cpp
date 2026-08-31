#include "dashboard/source_adapters.h"

namespace dashboard {

void PlaceholderDataSource::tick(std::uint64_t /*now_ms*/) {
    // Placeholders do not expire signals; real sources override this.
}

bool NativeBleTransport::connect() {
    // Reserved: requires BLE GATT central on T113 (blink vendor API) or
    // further integration work. Not implemented in phase 1.
    return false;
}

void NativeBleTransport::disconnect() {}

bool NativeBleTransport::isConnected() const {
    return false;
}

void NativeBleTransport::poll(CommanderStatus& status) {
    status.connected = false;
}

bool PhoneBridgeTransport::connect() {
    // Reserved: phone-side Commander BLE + Wi-Fi bridge to the dashboard.
    // Not implemented in phase 1.
    return false;
}

void PhoneBridgeTransport::disconnect() {}

bool PhoneBridgeTransport::isConnected() const {
    return false;
}

void PhoneBridgeTransport::poll(CommanderStatus& status) {
    status.connected = false;
}

CommanderAdapter::CommanderAdapter()
    : PlaceholderDataSource("CommanderAdapter", SignalSource::Commander) {}

void CommanderAdapter::tick(std::uint64_t now_ms) {
    if (transport_ != nullptr) {
        transport_->poll(status_);
        health_.status = status_.connected ? DataSourceStatus::Connected
                                          : DataSourceStatus::Offline;
        if (status_.connected) {
            health_.last_update_ms = now_ms;
            ++health_.packets;
        }
    } else {
        health_.status = DataSourceStatus::Disabled;
    }
}

SimulationAdapter::SimulationAdapter() {
    health_.status = DataSourceStatus::Offline;
}

void SimulationAdapter::tick(std::uint64_t now_ms) {
    if (health_.status == DataSourceStatus::Connected &&
        now_ms > health_.last_update_ms + 2500) {
        health_.status = DataSourceStatus::Offline;
    }
}

void SimulationAdapter::setDriving(
    std::uint16_t speed_value,
    Gear gear_value,
    std::uint8_t soc_value,
    std::uint16_t range_value,
    std::uint64_t timestamp_ms) {
    state_.speed.update(
        speed_value, timestamp_ms, source(), SignalQuality::Confirmed,
        Unit::KilometerPerHour);
    state_.gear.update(
        gear_value, timestamp_ms, source(), SignalQuality::Confirmed,
        Unit::None);
    state_.soc.update(
        soc_value, timestamp_ms, source(), SignalQuality::Confirmed,
        Unit::Percent);
    state_.range.update(
        range_value, timestamp_ms, source(), SignalQuality::Confirmed,
        Unit::Kilometer);
    health_.status = DataSourceStatus::Connected;
    health_.last_update_ms = timestamp_ms;
    ++health_.packets;
}

void SimulationAdapter::setDoors(
    bool fl,
    bool fr,
    bool rl,
    bool rr,
    bool frunk_value,
    bool trunk_value,
    std::uint64_t timestamp_ms) {
    state_.door_fl.update(fl, timestamp_ms, source(), SignalQuality::Confirmed, Unit::None);
    state_.door_fr.update(fr, timestamp_ms, source(), SignalQuality::Confirmed, Unit::None);
    state_.door_rl.update(rl, timestamp_ms, source(), SignalQuality::Confirmed, Unit::None);
    state_.door_rr.update(rr, timestamp_ms, source(), SignalQuality::Confirmed, Unit::None);
    state_.frunk.update(frunk_value, timestamp_ms, source(), SignalQuality::Confirmed, Unit::None);
    state_.trunk.update(trunk_value, timestamp_ms, source(), SignalQuality::Confirmed, Unit::None);
    health_.status = DataSourceStatus::Connected;
    health_.last_update_ms = timestamp_ms;
    ++health_.packets;
}

void SimulationAdapter::setTires(
    float fl,
    float fr,
    float rl,
    float rr,
    std::uint64_t timestamp_ms) {
    state_.tire_fl.update(fl, timestamp_ms, source(), SignalQuality::Confirmed, Unit::Bar);
    state_.tire_fr.update(fr, timestamp_ms, source(), SignalQuality::Confirmed, Unit::Bar);
    state_.tire_rl.update(rl, timestamp_ms, source(), SignalQuality::Confirmed, Unit::Bar);
    state_.tire_rr.update(rr, timestamp_ms, source(), SignalQuality::Confirmed, Unit::Bar);
    health_.status = DataSourceStatus::Connected;
    health_.last_update_ms = timestamp_ms;
    ++health_.packets;
}

}  // namespace dashboard
