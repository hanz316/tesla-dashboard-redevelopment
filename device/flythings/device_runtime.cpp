#include "device_runtime.h"

#include "dashboard/stale_policy.h"

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
constexpr std::uint64_t kUartHealthyWindowMs = 2500;

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

    pthread_mutex_lock(&mutex_);
    last_rx_ms_ = 0;
    rx_bytes_ = 0;
    read_errors_ = 0;
    pthread_mutex_unlock(&mutex_);

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
    const std::uint64_t now_ms = monotonicMilliseconds();

    pthread_mutex_lock(&mutex_);
    result.state = adapter_.state();
    result.parser = adapter_.parserStats();
    result.adapter = adapter_.adapterStats();
    result.uart_connected = uart_fd_ >= 0;
    result.last_rx_ms = last_rx_ms_;
    result.has_rx = last_rx_ms_ != 0;
    result.rx_bytes = rx_bytes_;
    result.read_errors = read_errors_;
    pthread_mutex_unlock(&mutex_);

    if (result.has_rx && now_ms >= result.last_rx_ms) {
        result.rx_age_ms = now_ms - result.last_rx_ms;
    }
    result.uart_healthy =
        result.uart_connected && result.has_rx &&
        result.rx_age_ms <= kUartHealthyWindowMs;

    const StaleSummary stale = invalidateStale(result.state, now_ms);
    result.stale_signals = stale.expired_signals;
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
            const std::uint64_t now_ms = monotonicMilliseconds();
            pthread_mutex_lock(&mutex_);
            adapter_.feed(buffer, static_cast<std::size_t>(count), now_ms);
            last_rx_ms_ = now_ms;
            rx_bytes_ += static_cast<std::uint64_t>(count);
            pthread_mutex_unlock(&mutex_);
            continue;
        }
        if (count < 0 && errno != EAGAIN && errno != EINTR) {
            pthread_mutex_lock(&mutex_);
            ++read_errors_;
            pthread_mutex_unlock(&mutex_);
            break;
        }
        usleep(20000);
    }

    pthread_mutex_lock(&mutex_);
    if (uart_fd_ >= 0) {
        close(uart_fd_);
        uart_fd_ = -1;
    }
    pthread_mutex_unlock(&mutex_);
}

bool DeviceRuntime::openVehicleUart() {
    // O_RDONLY is intentional. There is still no transmit/control path.
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
