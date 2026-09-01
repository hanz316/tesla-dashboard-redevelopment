#pragma once

#include "dashboard/data_source.h"

#include <cstdint>

namespace dashboard {

class PlaceholderDataSource : public IDataSource {
public:
    PlaceholderDataSource(const char* adapter_name, SignalSource adapter_source)
        : name_(adapter_name), source_(adapter_source) { health_.status = DataSourceStatus::Disabled; }
    const char* name() const override { return name_; }
    SignalSource source() const override { return source_; }
    const VehicleState& state() const override { return state_; }
    const DataSourceHealth& health() const override { return health_; }
    void tick(std::uint64_t now_ms) override { state_.invalidateStale(now_ms); }

protected:
    const char* name_;
    SignalSource source_;
    VehicleState state_;
    DataSourceHealth health_;
};

class CommanderAdapter final : public PlaceholderDataSource {
public:
    CommanderAdapter() : PlaceholderDataSource("CommanderAdapter", SignalSource::Commander) {}
};

class PhoneBridgeAdapter final : public PlaceholderDataSource {
public:
    PhoneBridgeAdapter() : PlaceholderDataSource("PhoneBridgeAdapter", SignalSource::PhoneBridge) {}
};

class SimulationAdapter final : public IDataSource {
public:
    SimulationAdapter();
    const char* name() const override { return "SimulationAdapter"; }
    SignalSource source() const override { return SignalSource::Simulation; }
    const VehicleState& state() const override { return state_; }
    const DataSourceHealth& health() const override { return health_; }
    void tick(std::uint64_t now_ms) override;

    void setDriving(std::uint16_t speed, Gear gear, std::uint8_t soc,
                    std::uint16_t range, std::uint64_t timestamp_ms);
    void setDoors(bool fl, bool fr, bool rl, bool rr, bool frunk, bool trunk,
                  std::uint64_t timestamp_ms);
    void setTires(float fl, float fr, float rl, float rr, std::uint64_t timestamp_ms);
    void setLighting(bool headlights, bool high_beam, bool brake, bool left,
                     bool right, bool hazards, std::uint64_t timestamp_ms);
    void setDriverAssistance(AutopilotState ap, bool blind_left, bool blind_right,
                             bool front_vehicle, bool left_vehicle, bool right_vehicle,
                             std::uint64_t timestamp_ms);
    void setEnhancedPower(float pack_kw, float front_kw, float rear_kw,
                          float accelerator_percent, std::uint64_t timestamp_ms);
    void disconnect(std::uint64_t timestamp_ms);

private:
    VehicleState state_;
    DataSourceHealth health_;
};

}  // namespace dashboard
