#include "dashboard/commander_transport.h"

#include <arpa/inet.h>
#include <cerrno>
#include <cstddef>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>

namespace dashboard {
namespace {

constexpr int kMaxDatagram = 2048;

}  // namespace

CommanderUdpListenerV6::~CommanderUdpListenerV6() {
    close();
}

bool CommanderUdpListenerV6::open(std::uint16_t port, const char* bind_address) {
    close();
    fd_ = ::socket(AF_INET, SOCK_DGRAM, 0);
    if (fd_ < 0) return false;

    sockaddr_in address{};
    address.sin_family = AF_INET;
    if (bind_address == nullptr) {
        address.sin_addr.s_addr = htonl(INADDR_ANY);
    } else if (::inet_pton(AF_INET, bind_address, &address.sin_addr) != 1) {
        ::close(fd_);
        fd_ = -1;
        return false;
    }
    address.sin_port = htons(port);
    if (::bind(fd_, reinterpret_cast<sockaddr*>(&address), sizeof(address)) != 0) {
        ::close(fd_);
        fd_ = -1;
        return false;
    }
    const int flags = ::fcntl(fd_, F_GETFL, 0);
    if (flags >= 0) {
        ::fcntl(fd_, F_SETFL, flags | O_NONBLOCK);
    }
    return true;
}

void CommanderUdpListenerV6::close() {
    if (fd_ >= 0) {
        ::close(fd_);
        fd_ = -1;
    }
}

int CommanderUdpListenerV6::poll(CommanderFrameReaderV6& reader,
                                 std::uint64_t now_ms,
                                 CommanderFrameReaderV6::Frame* frames,
                                 int frame_capacity) {
    if (fd_ < 0) return 0;
    int decoded = 0;
    std::uint8_t buffer[kMaxDatagram];
    for (;;) {
        sockaddr_in sender{};
        socklen_t sender_length = sizeof(sender);
        const ssize_t received = ::recvfrom(
            fd_, buffer, sizeof(buffer), 0,
            reinterpret_cast<sockaddr*>(&sender), &sender_length);
        if (received < 0) {
            if (errno == EINTR) continue;
            // EAGAIN/EWOULDBLOCK is the normal "nothing waiting" answer.
            break;
        }
        if (received == 0) break;
        ++datagrams_;
        bytes_ += static_cast<std::uint64_t>(received);
        if (received == kMaxDatagram) {
            // A datagram at the buffer size may have been truncated, and a
            // truncated frame is not a frame.
            ++dropped_datagrams_;
            continue;
        }
        last_sender_ = inet_ntoa(sender.sin_addr);

        CommanderFrameReaderV6::Frame frame;
        for (ssize_t i = 0; i < received; ++i) {
            if (!reader.feed(buffer[i], now_ms, frame)) continue;
            if (frames != nullptr && decoded < frame_capacity) {
                frames[decoded] = frame;
            }
            ++decoded;
        }
    }
    return decoded;
}

void CommanderBridgeV6::setEnabled(bool enabled, std::uint64_t now_ms) {
    link_.setEnabled(enabled, now_ms);
    schedule_.setEnabled(enabled, now_ms);
}

void CommanderBridgeV6::noteTransportUp(std::uint64_t now_ms) {
    link_.setTransport(true, now_ms);
    schedule_.noteConnected(now_ms);
}

void CommanderBridgeV6::noteTransportDown(std::uint64_t now_ms) {
    link_.setTransport(false, now_ms);
    schedule_.noteDisconnected(now_ms);
}

void CommanderBridgeV6::noteSilence(std::uint64_t now_ms) {
    // Frames stopped. The transport may still believe it is connected, so the
    // schedule is told to try again rather than waiting for a socket event
    // that will never come.
    schedule_.noteLinkLost(now_ms);
    link_.tick(now_ms);
}

void CommanderBridgeV6::feed(const std::uint8_t* data, std::size_t length,
                             std::uint64_t now_ms) {
    if (data == nullptr || length == 0) return;
    CommanderFrameReaderV6::Frame frame;
    for (std::size_t i = 0; i < length; ++i) {
        if (!reader_.feed(data[i], now_ms, frame)) continue;
        link_.noteFrame(now_ms);
        schedule_.noteConnected(now_ms);
        applyFrame(frame, now_ms);
    }
}

int CommanderBridgeV6::pollUdp(CommanderUdpListenerV6& listener,
                               std::uint64_t now_ms) {
    CommanderFrameReaderV6::Frame frames[8];
    const int decoded =
        listener.poll(reader_, now_ms, frames, static_cast<int>(sizeof(frames) /
                                                               sizeof(frames[0])));
    for (int i = 0; i < decoded; ++i) {
        link_.noteFrame(now_ms);
        schedule_.noteConnected(now_ms);
        applyFrame(frames[i], now_ms);
    }
    return decoded;
}

void CommanderBridgeV6::applyFrame(const CommanderFrameReaderV6::Frame& frame,
                                   std::uint64_t now_ms) {
    switch (static_cast<CommanderCommandV6>(frame.command)) {
        case CommanderCommandV6::ReadDeviceInfo: {
            CommanderDeviceInfoV6 info;
            if (decodeCommanderDeviceInfoV6(frame.payload, now_ms, info)) {
                info_ = info;
                CommanderModuleVersion version;
                version.major = info.hardware_version;
                version.minor = info.firmware_version;
                version.patch = info.bootloader_version;
                CommanderFeatureFlags features;
                features.enabled = true;
                features.raw_can = info.can_channel(0);
                features.bms = pack_.valid;
                features.cells = pack_.valid;
                features.power = gauge_.has_extended;
                link_.setModuleInfo(version, features);
            }
            break;
        }
        case CommanderCommandV6::Gauge: {
            CommanderGaugeV6 gauge;
            if (decodeCommanderGaugeV6(frame.payload, now_ms, gauge)) {
                gauge_ = gauge;
                applyCommanderReadingsV6(gauge_, pack_, dcdc_, state_, now_ms);
            }
            break;
        }
        case CommanderCommandV6::Battery: {
            CommanderPackV6 pack;
            if (decodeCommanderPackV6(frame.payload, now_ms, pack)) {
                pack_ = pack;
                applyCommanderReadingsV6(gauge_, pack_, dcdc_, state_, now_ms);
            }
            break;
        }
        case CommanderCommandV6::Dcdc: {
            CommanderDcdcV6 dcdc;
            if (decodeCommanderDcdcV6(frame.payload, now_ms, dcdc)) {
                dcdc_ = dcdc;
                applyCommanderReadingsV6(gauge_, pack_, dcdc_, state_, now_ms);
            }
            break;
        }
        default:
            // A reply we did not ask for and do not decode is ignored, not
            // guessed at.
            break;
    }
}

void CommanderBridgeV6::tick(std::uint64_t now_ms) {
    const bool was_linked = link_.linked();
    link_.tick(now_ms);
    if (was_linked && !link_.linked()) {
        schedule_.noteLinkLost(now_ms);
        // Readings from a link that has gone must expire like any other stale
        // signal, or the screens keep showing a car that is no longer talking.
        state_.invalidateStale(now_ms);
    }
}

}  // namespace dashboard
