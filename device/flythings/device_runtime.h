#pragma once

#include "dashboard/commander_link.h"
#include "dashboard/dashboard_services.h"
#include "dashboard/original_mcu_adapter.h"
#include "dashboard/page_projection_v6.h"

#include <pthread.h>

#include <cstddef>

namespace dashboard {
namespace flythings {

struct RuntimeSnapshot {
    VehicleState state;
    // The enhanced-telemetry fields, kept beside the MCU state rather than
    // merged into it, so a diagnostic can tell which link produced a value.
    VehicleState commander_state;
    ProtocolParserStats parser;
    AdapterStats adapter;
    std::uint64_t commander_frames{0};
    std::uint64_t commander_checksum_errors{0};
    std::uint64_t commander_dropped_partials{0};
    // Frames we asked the module for (gauge polls, pack polls) as opposed to
    // frames it sent us unasked.
    std::uint64_t commander_requests{0};
    bool commander_info_known{false};
    CommanderDeviceInfoV6 commander_info;
    CommanderGaugeV6 commander_gauge;
    CommanderPackV6 commander_pack;
    DataSourceHealth health;
    TripSummary trip;
    WarningState warning;
    bool uart_connected{false};
    bool uart_receiving{false};
    CommanderLinkStatus commander_status{CommanderLinkStatus::Disabled};
    bool commander_module_info_known{false};
    CommanderModuleVersion commander_version;
    std::string commander_detail;
};

class DeviceRuntime {
public:
    static DeviceRuntime& instance();

    bool start();
    void stop();
    RuntimeSnapshot snapshot();

    // Bytes from an enhanced-telemetry transport. Nothing in this build opens
    // one (the native BLE client is a platform task), so this is the seam a
    // transport thread will use; until then the link reports what it is:
    // disabled, or enabled and searching.
    void feedCommander(const std::uint8_t* data, std::size_t length);

    // Enables the enhanced-telemetry link. The transport itself is still a
    // placeholder, so an enabled link that cannot connect stays "searching"
    // instead of pretending to be offline-dashboard-clean.
    void setCommanderEnabled(bool enabled);

private:
    DeviceRuntime();
    ~DeviceRuntime();
    DeviceRuntime(const DeviceRuntime&) = delete;
    DeviceRuntime& operator=(const DeviceRuntime&) = delete;

    static void* threadEntry(void* context);
    void readLoop();
    bool openVehicleUart();
    static std::uint64_t monotonicMilliseconds();

    OriginalMcuAdapter adapter_;
    CommanderFrameReaderV6 commander_reader_;
    CommanderLink commander_link_;
    TripComputer trip_;
    WarningManager warnings_;
    VehicleState commander_state_;
    CommanderGaugeV6 commander_gauge_;
    CommanderPackV6 commander_pack_;
    CommanderDcdcV6 commander_dcdc_;
    CommanderDeviceInfoV6 commander_info_;
    std::uint64_t commander_frames_{0};
    std::uint64_t commander_checksum_errors_{0};
    std::uint64_t commander_dropped_partials_{0};
    std::uint64_t commander_module_frames_{0};
    pthread_mutex_t mutex_;
    pthread_t thread_{};
    int uart_fd_{-1};
    bool running_{false};
    bool thread_started_{false};
    std::uint64_t started_ms_{0};
    bool commander_transport_connected_{false};
};

// The projection environment for the current frame, built from the same
// counters the Developer screen shows. Free function so the host tests can
// build the device's view of the world without a device.
PageEnvironmentV6 buildDevicePageEnvironment(const RuntimeSnapshot& snapshot);

}  // namespace flythings
}  // namespace dashboard
