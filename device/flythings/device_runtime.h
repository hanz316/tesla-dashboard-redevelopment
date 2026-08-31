#pragma once

#include "dashboard/original_mcu_adapter.h"

#include <pthread.h>

namespace dashboard {
namespace flythings {

struct RuntimeSnapshot {
    VehicleState state;
    ProtocolParserStats parser;
    AdapterStats adapter;
    bool uart_connected{false};
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
};

}  // namespace flythings
}  // namespace dashboard
