#pragma once

#include "dashboard/commander_link.h"
#include "dashboard/vehicle_state.h"

#include <cstdint>
#include <string>

namespace dashboard {

// How the instrument gets the module's bytes when it cannot be the BLE
// central itself.
//
// The cluster's Bluetooth stack has the LE and GATT machinery inside the
// platform daemon (`blink`), but the application-facing API only exposes the
// classic profiles. The module's own control software, however, is a BLE
// central already - it runs on the phone. So the shortest path that works
// today is: the phone keeps its BLE link to the module and forwards the frames
// it receives over Wi-Fi, and the instrument decodes them with exactly the
// same reader it would use for a direct link.
//
// The transport is deliberately receive-only. It binds a UDP port and never
// sends anything: no reply, no acknowledgement, no control command. Forwarding
// is the phone's job, and a listener that never writes cannot become a second
// control path by accident.
class CommanderUdpListenerV6 {
public:
    ~CommanderUdpListenerV6();

    // Binds the given UDP port. `bind_address` defaults to every interface,
    // which is what the instrument wants - the phone connects over Wi-Fi from
    // another host. A test passes "127.0.0.1", because a socket bound to
    // INADDR_ANY does not receive loopback traffic on every platform.
    // Returns false if the port cannot be bound; the caller keeps retrying on
    // its own schedule.
    bool open(std::uint16_t port, const char* bind_address = nullptr);
    void close();
    bool isOpen() const { return fd_ >= 0; }

    // Drains every datagram waiting on the socket, feeding them to `reader`.
    // Returns the number of complete, checksum-valid frames decoded. Bytes that
    // arrive in pieces are fine: the reader is a stream reader, and a datagram
    // that carries half a frame simply leaves the reader mid-frame, exactly as
    // a BLE packet would.
    int poll(CommanderFrameReaderV6& reader, std::uint64_t now_ms,
             CommanderFrameReaderV6::Frame* frames, int frame_capacity);

    std::uint64_t datagrams() const { return datagrams_; }
    std::uint64_t bytes() const { return bytes_; }
    std::uint64_t dropped_datagrams() const { return dropped_datagrams_; }
    std::string last_sender() const { return last_sender_; }

private:
    int fd_{-1};
    std::uint64_t datagrams_{0};
    std::uint64_t bytes_{0};
    std::uint64_t dropped_datagrams_{0};
    std::string last_sender_;
};

// Turns the frames a listener decoded into the module's readings, and keeps the
// link state machine honest while doing it.
//
// One object owns the whole receive path for the phone-bridge link: reader,
// link state, decoded readings and the connect schedule. The device runtime
// drives it; the host tests drive it too, over a real socket on loopback.
class CommanderBridgeV6 {
public:
    explicit CommanderBridgeV6(CommanderLinkPolicy link_policy = CommanderLinkPolicy{},
                               CommanderConnectPolicyV6 schedule_policy = {})
        : link_(link_policy), schedule_(schedule_policy) {}

    void setEnabled(bool enabled, std::uint64_t now_ms);
    bool enabled() const { return link_.enabled(); }
    bool shouldConnect(std::uint64_t now_ms) const {
        return schedule_.shouldAttempt(now_ms);
    }

    // The transport reports what it did, so auto-connect has something real to
    // back off from.
    void noteConnectAttempt(std::uint64_t now_ms) { schedule_.noteAttempt(now_ms); }
    void noteTransportUp(std::uint64_t now_ms);
    void noteTransportDown(std::uint64_t now_ms);
    void noteSilence(std::uint64_t now_ms);

    // Bytes straight off the wire (UDP datagram, socket read, or a BLE packet
    // if the cluster ever gets a direct link).
    void feed(const std::uint8_t* data, std::size_t length, std::uint64_t now_ms);

    // The same entry point, driven by the socket: drains everything waiting on
    // `listener` through this bridge's reader and applies the frames it
    // completes. Returns how many frames were decoded.
    int pollUdp(CommanderUdpListenerV6& listener, std::uint64_t now_ms);

    // Ages the link and the decoded readings. Call it every frame: a link that
    // stopped delivering must show up as stale, not as last-known-good.
    void tick(std::uint64_t now_ms);

    const CommanderLink& link() const { return link_; }
    const CommanderConnectScheduleV6& schedule() const { return schedule_; }
    const VehicleState& state() const { return state_; }
    const CommanderGaugeV6& gauge() const { return gauge_; }
    const CommanderPackV6& pack() const { return pack_; }
    const CommanderDcdcV6& dcdc() const { return dcdc_; }
    const CommanderDeviceInfoV6& info() const { return info_; }
    const CommanderFrameReaderV6& reader() const { return reader_; }

private:
    void applyFrame(const CommanderFrameReaderV6::Frame& frame,
                    std::uint64_t now_ms);

    CommanderFrameReaderV6 reader_;
    CommanderLink link_;
    CommanderConnectScheduleV6 schedule_;
    VehicleState state_;
    CommanderGaugeV6 gauge_;
    CommanderPackV6 pack_;
    CommanderDcdcV6 dcdc_;
    CommanderDeviceInfoV6 info_;
};

}  // namespace dashboard
