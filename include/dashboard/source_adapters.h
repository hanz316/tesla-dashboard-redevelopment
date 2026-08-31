#pragma once

#include "dashboard/data_source.h"

#include <cstdint>

namespace dashboard {

// Base for placeholder sources that keep the interface contract but are
// not yet wired to real transports.
class PlaceholderDataSource : public IDataSource {
public:
    PlaceholderDataSource(const char* adapter_name, SignalSource adapter_source)
        : name_(adapter_name), source_(adapter_source) {
        health_.status = DataSourceStatus::Disabled;
    }

    const char* name() const override { return name_; }
    SignalSource source() const override { return source_; }
    const VehicleState& state() const override { return state_; }
    const DataSourceHealth& health() const override { return health_; }
    void tick(std::uint64_t now_ms) override;

protected:
    const char* name_;
    SignalSource source_;
    VehicleState state_;
    DataSourceHealth health_;
};

// ---------- Commander transport abstraction (reserved) ----------
// Two real transports are planned:
//   NativeBleTransport     dashboard acts as BLE GATT central
//   PhoneBridgeTransport   phone does BLE, dashboard gets data over Wi-Fi
// The adapter and UI do not care which one is active.
class ICommanderTransport {
public:
    virtual ~ICommanderTransport() = default;
    virtual bool connect() = 0;
    virtual void disconnect() = 0;
    virtual bool isConnected() const = 0;
    // Feeds decoded vehicle data into the adapter.
    virtual void poll(CommanderStatus& status) = 0;
};

class NativeBleTransport : public ICommanderTransport {
public:
    bool connect() override;
    void disconnect() override;
    bool isConnected() const override;
    void poll(CommanderStatus& status) override;
};

class PhoneBridgeTransport : public ICommanderTransport {
public:
    bool connect() override;
    void disconnect() override;
    bool isConnected() const override;
    void poll(CommanderStatus& status) override;
};

// CommanderAdapter: reserved integration point for the Commander protocol
// thread's SDK. Read-only in phase 1: it only reads/subscribes/queries,
// never writes vehicle controls or raw CAN TX.
class CommanderAdapter : public PlaceholderDataSource {
public:
    CommanderAdapter();

    void setTransport(ICommanderTransport* transport) { transport_ = transport; }
    const CommanderStatus& commanderStatus() const { return status_; }
    void tick(std::uint64_t now_ms) override;

private:
    ICommanderTransport* transport_{nullptr};
    CommanderStatus status_;
};

class PhoneBridgeAdapter final : public PlaceholderDataSource {
public:
    PhoneBridgeAdapter()
        : PlaceholderDataSource("PhoneBridgeAdapter", SignalSource::PhoneBridge) {}
};

class SimulationAdapter final : public IDataSource {
public:
    SimulationAdapter();

    const char* name() const override { return "SimulationAdapter"; }
    SignalSource source() const override { return SignalSource::Simulation; }
    const VehicleState& state() const override { return state_; }
    const DataSourceHealth& health() const override { return health_; }
    void tick(std::uint64_t now_ms) override;

    void setDriving(
        std::uint16_t speed,
        Gear gear,
        std::uint8_t soc,
        std::uint16_t range,
        std::uint64_t timestamp_ms);
    void setDoors(
        bool fl,
        bool fr,
        bool rl,
        bool rr,
        bool frunk,
        bool trunk,
        std::uint64_t timestamp_ms);
    void setTires(
        float fl,
        float fr,
        float rl,
        float rr,
        std::uint64_t timestamp_ms);

private:
    VehicleState state_;
    DataSourceHealth health_;
};

}  // namespace dashboard
