#pragma once

#include "dashboard/original_mcu_adapter.h"

#include <cstdint>
#include <pthread.h>

namespace dashboard {
namespace flythings {

struct RuntimeSnapshot {
    VehicleState state;
    ProtocolParserStats parser;
    AdapterStats adapter;
    bool uart_connected{false};
    bool uart_healthy{false};
    bool has_rx{false};
    std::uint64_t last_rx_ms{0};
    std::uint64_t rx_age_ms{0};
    std::uint64_t rx_bytes{0};
    std::uint64_t read_errors{0};
    std::uint32_t stale_signals{0};
};

class DeviceRuntime {
public:
    static DeviceRuntime& instance();

    bool start();
    void stop();
    RuntimeSnapshot snapshot();

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
    pthread_mutex_t mutex_;
    pthread_t thread_{};
    int uart_fd_{-1};
    bool running_{false};
    bool thread_started_{false};
    std::uint64_t last_rx_ms_{0};
    std::uint64_t rx_bytes_{0};
    std::uint64_t read_errors_{0};
};

}  // namespace flythings
}  // namespace dashboard
