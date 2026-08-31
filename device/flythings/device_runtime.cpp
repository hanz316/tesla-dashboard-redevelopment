#include "device_runtime.h"

#include <cerrno>
#include <cstdint>
#include <fcntl.h>
#include <termios.h>
#include <time.h>
#include <unistd.h>

namespace dashboard {
namespace flythings {
namespace {

constexpr const char* kVehicleUart = "/dev/ttyS5";

}  // namespace

DeviceRuntime& DeviceRuntime::instance() {
    static DeviceRuntime runtime;
    return runtime;
}

DeviceRuntime::DeviceRuntime() {
    pthread_mutex_init(&mutex_, nullptr);
}

DeviceRuntime::~DeviceRuntime() {
    stop();
    pthread_mutex_destroy(&mutex_);
}

bool DeviceRuntime::start() {
    if (running_) {
        return true;
    }
    if (!openVehicleUart()) {
        return false;
    }

    running_ = true;
    if (pthread_create(&thread_, nullptr, &DeviceRuntime::threadEntry, this) != 0) {
        running_ = false;
        close(uart_fd_);
        uart_fd_ = -1;
        return false;
    }
    thread_started_ = true;
    return true;
}

void DeviceRuntime::stop() {
    running_ = false;
    if (thread_started_) {
        pthread_join(thread_, nullptr);
        thread_started_ = false;
    }
    if (uart_fd_ >= 0) {
        close(uart_fd_);
        uart_fd_ = -1;
    }
}

RuntimeSnapshot DeviceRuntime::snapshot() {
    RuntimeSnapshot result;
    pthread_mutex_lock(&mutex_);
    result.state = adapter_.state();
    result.parser = adapter_.parserStats();
    result.adapter = adapter_.adapterStats();
    result.uart_connected = uart_fd_ >= 0;
    pthread_mutex_unlock(&mutex_);
    return result;
}

void* DeviceRuntime::threadEntry(void* context) {
    static_cast<DeviceRuntime*>(context)->readLoop();
    return nullptr;
}

void DeviceRuntime::readLoop() {
    std::uint8_t buffer[1024];
    while (running_) {
        const ssize_t count = read(uart_fd_, buffer, sizeof(buffer));
        if (count > 0) {
            pthread_mutex_lock(&mutex_);
            adapter_.feed(
                buffer,
                static_cast<std::size_t>(count),
                monotonicMilliseconds());
            pthread_mutex_unlock(&mutex_);
            continue;
        }
        if (count < 0 && errno != EAGAIN && errno != EINTR) {
            break;
        }
        usleep(20000);
    }
}

bool DeviceRuntime::openVehicleUart() {
    // O_RDONLY is intentional: Phase 0-2 have no path that can transmit a
    // command to the original MCU or vehicle.
    uart_fd_ = open(kVehicleUart, O_RDONLY | O_NOCTTY | O_NONBLOCK);
    if (uart_fd_ < 0) {
        return false;
    }

    termios settings{};
    if (tcgetattr(uart_fd_, &settings) != 0) {
        close(uart_fd_);
        uart_fd_ = -1;
        return false;
    }
    cfmakeraw(&settings);
    cfsetispeed(&settings, B38400);
    cfsetospeed(&settings, B38400);
    settings.c_cflag |= static_cast<tcflag_t>(CLOCAL | CREAD | CS8);
    settings.c_cflag &= static_cast<tcflag_t>(~(PARENB | CSTOPB | CSIZE));
    settings.c_cflag |= CS8;
#ifdef CRTSCTS
    settings.c_cflag &= static_cast<tcflag_t>(~CRTSCTS);
#endif
    settings.c_cc[VMIN] = 0;
    settings.c_cc[VTIME] = 1;
    if (tcsetattr(uart_fd_, TCSANOW, &settings) != 0) {
        close(uart_fd_);
        uart_fd_ = -1;
        return false;
    }
    tcflush(uart_fd_, TCIFLUSH);
    return true;
}

std::uint64_t DeviceRuntime::monotonicMilliseconds() {
    timespec now{};
    clock_gettime(CLOCK_MONOTONIC, &now);
    return static_cast<std::uint64_t>(now.tv_sec) * 1000ULL +
        static_cast<std::uint64_t>(now.tv_nsec / 1000000L);
}

}  // namespace flythings
}  // namespace dashboard
