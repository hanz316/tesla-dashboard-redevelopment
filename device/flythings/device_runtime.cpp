#include "device_runtime.h"

#include <cerrno>
#include <cstdio>
#include <cstdint>
#include <cstring>
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
    result.commander_state = commander_state_;
    result.parser = adapter_.parserStats();
    result.adapter = adapter_.adapterStats();
    result.commander_stats = commander_decoder_.stats();
    result.health = adapter_.health();
    result.trip = trip_.summary(TripSlot::CurrentDrive);
    result.warning = warnings_.evaluate(adapter_.state());
    result.uart_connected = uart_fd_ >= 0;
    result.uart_receiving = uart_fd_ >= 0 &&
                            adapter_.parserStats().valid_packets > 0;
    result.commander_status = commander_link_.status();
    result.commander_module_info_known = commander_decoder_.module_info_known();
    result.commander_version = commander_decoder_.version();
    result.commander_detail = commander_link_.detail("NativeBle");
    pthread_mutex_unlock(&mutex_);
    return result;
}

void DeviceRuntime::feedCommander(const std::uint8_t* data, std::size_t length) {
    if (data == nullptr || length == 0) return;
    pthread_mutex_lock(&mutex_);
    const std::uint64_t now_ms = monotonicMilliseconds();
    if (!commander_transport_connected_) {
        // A transport that is delivering bytes is connected, whatever it
        // reported about its own socket.
        commander_transport_connected_ = true;
        commander_link_.setTransport(true, now_ms);
    }
    const std::uint64_t frames_before = commander_decoder_.stats().frames;
    commander_decoder_.decode(data, length, commander_state_, now_ms);
    if (commander_decoder_.stats().frames > frames_before) {
        commander_link_.noteFrame(now_ms);
    }
    if (commander_decoder_.module_info_known()) {
        commander_link_.setModuleInfo(commander_decoder_.version(),
                                      commander_decoder_.features());
    }
    pthread_mutex_unlock(&mutex_);
}

void DeviceRuntime::setCommanderEnabled(bool enabled) {
    pthread_mutex_lock(&mutex_);
    commander_link_.setEnabled(enabled, monotonicMilliseconds());
    pthread_mutex_unlock(&mutex_);
}

PageEnvironmentV6 buildDevicePageEnvironment(const RuntimeSnapshot& snapshot) {
    PageEnvironmentV6 environment;
    environment.uart_connected = snapshot.uart_connected;
    environment.uart_receiving = snapshot.uart_receiving;
    environment.commander_status = snapshot.commander_status;
    environment.commander_detail_known = snapshot.commander_module_info_known ||
                                         snapshot.commander_status !=
                                             CommanderLinkStatus::Disabled;
    environment.commander_detail = snapshot.commander_detail;
    environment.parser_stats_known = snapshot.uart_connected;
    environment.parser_frames = snapshot.parser.valid_packets;
    environment.parser_checksum_errors = snapshot.parser.checksum_errors;
    environment.parser_unknown_commands = snapshot.adapter.unknown_commands;
    environment.trip_known = snapshot.trip.valid;
    environment.trip_distance_km = snapshot.trip.distance_km;
    environment.trip_duration_ms = snapshot.trip.duration_ms;
    environment.trip_average_kph = snapshot.trip.average_speed_kph;
    environment.trip_max_kph = snapshot.trip.max_speed_kph;
    environment.warning = snapshot.warning;
    // Frame timing and RSS come from the render backend, which is not wired
    // yet; the Developer screen shows its placeholder until it is.
    environment.frame_stats_known = false;
    environment.memory_stats_known = false;
    return environment;
}

void* DeviceRuntime::threadEntry(void* context) {
    static_cast<DeviceRuntime*>(context)->readLoop();
    return nullptr;
}

void DeviceRuntime::readLoop() {
    std::uint8_t buffer[1024];
    std::uint64_t last_report_ms = 0;
    while (running_) {
        const ssize_t count = read(uart_fd_, buffer, sizeof(buffer));
        if (count > 0) {
            const std::uint64_t now_ms = monotonicMilliseconds();
            pthread_mutex_lock(&mutex_);
            adapter_.feed(
                buffer,
                static_cast<std::size_t>(count),
                now_ms);
            pthread_mutex_unlock(&mutex_);
            // Raw UART recording (diagnostic only, tmpfs).
            // Enabled while /tmp/uart_record exists.
            if (access("/tmp/uart_record", F_OK) == 0) {
                FILE* rec = fopen("/tmp/uart_recording.bin", "a");
                if (rec != nullptr) {
                    std::fwrite(buffer, 1, static_cast<std::size_t>(count), rec);
                    std::fclose(rec);
                }
            }
            continue;
        }
        if (count < 0 && errno != EAGAIN && errno != EINTR) {
            break;
        }
        // Keep the freshness policy active even while no bytes arrive:
        // stale signals are invalidated and the source health is tracked.
        const std::uint64_t now_ms = monotonicMilliseconds();
        pthread_mutex_lock(&mutex_);
        adapter_.tick(now_ms);
        // The enhanced link ages the same way the vehicle link does: silent is
        // stale, not "last known good forever".
        commander_state_.invalidateStale(now_ms);
        commander_link_.tick(now_ms);
        // Trip accounting runs on the car's own speed, and only while that
        // speed is a live reading.
        trip_.update(now_ms, adapter_.state());
        if (now_ms >= last_report_ms + 5000) {
            const auto& ps = adapter_.parserStats();
            const auto& as = adapter_.adapterStats();
            FILE* log = fopen("/tmp/dashboard_runtime.log", "a");
            if (log != nullptr) {
                std::fprintf(
                    log,
                    "t=%llu bytes=%llu frames=%llu crc=%llu discard=%llu "
                    "applied=%llu short=%llu unknown=%llu health=%d\n",
                    static_cast<unsigned long long>(now_ms),
                    static_cast<unsigned long long>(ps.bytes_received),
                    static_cast<unsigned long long>(ps.valid_packets),
                    static_cast<unsigned long long>(ps.checksum_errors),
                    static_cast<unsigned long long>(ps.discarded_bytes),
                    static_cast<unsigned long long>(as.applied_packets),
                    static_cast<unsigned long long>(as.short_payloads),
                    static_cast<unsigned long long>(as.unknown_commands),
                    static_cast<int>(adapter_.health().status));
                const auto& st = adapter_.state();
                std::fprintf(
                    log,
                    "  sig speed=%u gear=%d soc=%u range=%u doors=%d%d%d%d%d%d "
                    "tires=%.2f/%.2f/%.2f/%.2f temp=%d/%d cmdr=%s cmdr_frames=%llu "
                    "cmdr_errors=%llu\n",
                    st.speed.valid ? static_cast<unsigned>(st.speed.value) : 0U,
                    st.gear.valid ? static_cast<int>(st.gear.value) : -1,
                    st.soc.valid ? static_cast<unsigned>(st.soc.value) : 0U,
                    st.range.valid ? static_cast<unsigned>(st.range.value) : 0U,
                    st.door_fl.valid && st.door_fl.value ? 1 : 0,
                    st.door_fr.valid && st.door_fr.value ? 1 : 0,
                    st.door_rl.valid && st.door_rl.value ? 1 : 0,
                    st.door_rr.valid && st.door_rr.value ? 1 : 0,
                    st.frunk.valid && st.frunk.value ? 1 : 0,
                    st.trunk.valid && st.trunk.value ? 1 : 0,
                    st.tire_fl.valid ? static_cast<double>(st.tire_fl.value) : 0.0,
                    st.tire_fr.valid ? static_cast<double>(st.tire_fr.value) : 0.0,
                    st.tire_rl.valid ? static_cast<double>(st.tire_rl.value) : 0.0,
                    st.tire_rr.valid ? static_cast<double>(st.tire_rr.value) : 0.0,
                    st.temperature_primary.valid
                        ? static_cast<int>(st.temperature_primary.value)
                        : 0,
                    st.temperature_secondary.valid
                        ? static_cast<int>(st.temperature_secondary.value)
                        : 0,
                    commanderLinkName(commander_link_.status()),
                    static_cast<unsigned long long>(commander_decoder_.stats().frames),
                    static_cast<unsigned long long>(
                        commander_decoder_.stats().checksum_errors));
                std::fclose(log);
            }
            last_report_ms = now_ms;
        }
        pthread_mutex_unlock(&mutex_);
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
