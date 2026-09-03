#pragma once

#include "dashboard/data_source.h"

#include <cstddef>
#include <cstdint>

namespace dashboard {

struct CommanderFeatureFlags {
    bool enabled{false};
    bool raw_can{false};
    bool bms{false};
    bool cells{false};
    bool power{false};
};

struct CommanderModuleVersion {
    std::uint16_t major{0};
    std::uint16_t minor{0};
    std::uint16_t patch{0};
};

class ICommanderTransport {
public:
    virtual ~ICommanderTransport() = default;
    virtual const char* name() const = 0;
    virtual bool connected() const = 0;
    virtual std::size_t read(std::uint8_t* destination, std::size_t capacity) = 0;

    // No vehicle-control write surface is exposed in the dashboard module.
};

class NativeBleTransport : public ICommanderTransport {
public:
    const char* name() const override { return "NativeBleTransport"; }
    bool connected() const override { return false; }
    std::size_t read(std::uint8_t*, std::size_t) override { return 0; }
};

class PhoneBridgeTransport : public ICommanderTransport {
public:
    const char* name() const override { return "PhoneBridgeTransport"; }
    bool connected() const override { return false; }
    std::size_t read(std::uint8_t*, std::size_t) override { return 0; }
};

struct CommanderModuleState {
    CommanderFeatureFlags features;
    CommanderModuleVersion version;
    bool transport_connected{false};
};

}  // namespace dashboard
