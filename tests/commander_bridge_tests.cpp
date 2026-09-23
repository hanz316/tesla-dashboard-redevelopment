#include "dashboard/commander_transport.h"

// Keep the assertions live even in a Release build (NDEBUG).
#undef NDEBUG
#include <arpa/inet.h>
#include <cassert>
#include <cmath>
#include <cstring>
#include <iostream>
#include <netinet/in.h>
#include <string>
#include <sys/socket.h>
#include <unistd.h>
#include <vector>

using namespace dashboard;

namespace {

// A gauge frame with just enough in it to be recognisable: speed 42, gear D,
// SOC 55 %, tire bytes that mean "no reading" on two of the four wheels.
std::vector<std::uint8_t> sampleGaugeFrame() {
    std::vector<std::uint8_t> payload(33, 0);
    const std::uint32_t first = 42U | (4U << 9) | (55U << 24);
    payload[0] = static_cast<std::uint8_t>(first & 0xFF);
    payload[1] = static_cast<std::uint8_t>((first >> 8) & 0xFF);
    payload[2] = static_cast<std::uint8_t>((first >> 16) & 0xFF);
    payload[3] = static_cast<std::uint8_t>((first >> 24) & 0xFF);
    payload[8] = 113;   // 2.825 bar
    payload[9] = 255;   // no reading
    payload[10] = 0;    // no reading
    payload[11] = 114;  // 2.85 bar
    return CommanderFrameV6::encode(176, payload);
}

int sendDatagram(std::uint16_t port, const std::vector<std::uint8_t>& bytes) {
    const int fd = ::socket(AF_INET, SOCK_DGRAM, 0);
    if (fd < 0) return -1;
    sockaddr_in target{};
    target.sin_family = AF_INET;
    target.sin_port = htons(port);
    ::inet_pton(AF_INET, "127.0.0.1", &target.sin_addr);
    const ssize_t sent = ::sendto(fd, bytes.data(), bytes.size(), 0,
                                  reinterpret_cast<sockaddr*>(&target),
                                  sizeof(target));
    ::close(fd);
    return static_cast<int>(sent);
}

// Polls until `expected` frames have been decoded or the attempt budget runs
// out. A datagram sent on loopback is not necessarily in the receive queue by
// the time the sending call returns, which is exactly why the device polls its
// socket in a loop instead of once.
int pollUntil(CommanderUdpListenerV6& listener, CommanderBridgeV6& bridge,
              std::uint64_t now_ms, int expected) {
    int total = 0;
    for (int attempt = 0; attempt < 100 && total < expected; ++attempt) {
        total += bridge.pollUdp(listener, now_ms);
        if (total < expected) ::usleep(2000);
    }
    return total;
}

}  // namespace

int main() {
    // ------------------------------------------------- connect schedule
    {
        CommanderConnectScheduleV6 schedule;
        assert(!schedule.shouldAttempt(1000));      // nothing to connect to yet
        schedule.setEnabled(true, 1000);
        // Enabled: try immediately, then back off while it keeps failing.
        assert(schedule.shouldAttempt(1000));
        schedule.noteAttempt(1000);
        assert(!schedule.shouldAttempt(1000));
        assert(schedule.shouldAttempt(2000));
        assert(schedule.current_backoff_ms() == 1000);
        schedule.noteAttempt(2000);
        assert(schedule.current_backoff_ms() == 2000);
        schedule.noteAttempt(4000);
        assert(schedule.current_backoff_ms() == 4000);
        for (int i = 0; i < 10; ++i) schedule.noteAttempt(10000);
        // The interval stops growing at the cap instead of running away.
        assert(schedule.current_backoff_ms() == 30000);

        // A working link resets everything, and waits while it works.
        schedule.noteConnected(20000);
        assert(!schedule.shouldAttempt(20000));
        assert(schedule.attempts() == 0);
        assert(schedule.connected());

        // Losing a link that worked retries on the short interval, not the
        // long one an earlier outage had grown to.
        schedule.noteLinkLost(21000);
        assert(schedule.current_backoff_ms() == 1000);
        assert(schedule.shouldAttempt(22000));
        std::cout << "connect schedule backs off, resets and retries\n";
    }

    // ------------------------------------------------------- bridge state
    {
        CommanderBridgeV6 bridge;
        assert(!bridge.enabled());
        bridge.setEnabled(true, 1000);
        assert(bridge.shouldConnect(1000));
        bridge.noteConnectAttempt(1000);

        // Bytes arrive: the link turns real, and the readings land.
        const auto frame = sampleGaugeFrame();
        bridge.feed(frame.data(), frame.size(), 1100);
        assert(bridge.link().linked());
        assert(bridge.reader().frames() == 1);
        assert(bridge.gauge().speed_kph == 42);
        assert(bridge.state().speed.valid && bridge.state().speed.value == 42);
        assert(bridge.state().speed.source == SignalSource::Commander);
        assert(bridge.state().gear.value == Gear::Drive);
        // Only the wheels that reported are written.
        assert(std::fabs(bridge.state().tire_fl.value - 2.825F) < 0.001F);
        assert(std::fabs(bridge.state().tire_rr.value - 2.85F) < 0.001F);
        assert(!bridge.state().tire_fr.valid);
        assert(!bridge.state().tire_rl.valid);
        std::cout << "bridge decodes a live stream and keeps no-reading tires "
                     "unknown\n";
    }

    // ------------------------------------------------ silence is not a link
    {
        CommanderBridgeV6 bridge;
        bridge.setEnabled(true, 1000);
        bridge.noteTransportUp(1000);
        const auto frame = sampleGaugeFrame();
        bridge.feed(frame.data(), frame.size(), 1000);
        assert(bridge.link().linked());
        bridge.tick(4200);                       // beyond the frame timeout
        assert(bridge.link().status() == CommanderLinkStatus::Stale);
        assert(!bridge.state().speed.valid);     // and the reading expired
        assert(bridge.shouldConnect(5200));       // so reconnecting is due
        std::cout << "a silent link goes stale, expires its readings and "
                     "schedules a retry\n";
    }

    // ------------------------------------------------- real UDP path
    {
        CommanderUdpListenerV6 listener;
        // Port 0 would need getsockname to learn the port; use a fixed high
        // port that nothing else in the test suite binds, and bind loopback
        // explicitly (a socket on INADDR_ANY does not see loopback sends on
        // every platform). The instrument itself binds every interface.
        const std::uint16_t port = 45871;
        assert(listener.open(port, "127.0.0.1"));
        CommanderBridgeV6 bridge;
        bridge.setEnabled(true, 1000);
        bridge.noteTransportUp(1000);

        const auto frame = sampleGaugeFrame();
        assert(sendDatagram(port, frame) == static_cast<int>(frame.size()));

        assert(pollUntil(listener, bridge, 1200, 1) == 1);
        assert(bridge.state().speed.value == 42);
        assert(bridge.link().linked());
        assert(listener.datagrams() == 1);
        assert(listener.bytes() == frame.size());

        // Two frames in one datagram, and a frame split across two datagrams,
        // both work: the reader is a stream reader.
        std::vector<std::uint8_t> doubled = frame;
        doubled.insert(doubled.end(), frame.begin(), frame.end());
        assert(sendDatagram(port, doubled) == static_cast<int>(doubled.size()));
        assert(pollUntil(listener, bridge, 1300, 2) == 2);

        std::vector<std::uint8_t> first_half(frame.begin(), frame.begin() + 12);
        std::vector<std::uint8_t> rest(frame.begin() + 12, frame.end());
        assert(sendDatagram(port, first_half) > 0);
        assert(bridge.pollUdp(listener, 1400) == 0);
        assert(sendDatagram(port, rest) > 0);
        assert(pollUntil(listener, bridge, 1450, 1) == 1);
        std::cout << "the UDP receive path reassembles frames across datagrams\n";

        // And nothing is ever sent back: the listener has no send path at all,
        // which is what keeps a receive-only bridge from becoming a control
        // channel.
        listener.close();
        assert(!listener.isOpen());
    }

    std::cout << "all commander bridge checks passed\n";
    return 0;
}
