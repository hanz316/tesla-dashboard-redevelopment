#include "dashboard/protocol_parser.h"

#include <algorithm>

namespace dashboard {

constexpr std::uint8_t ProtocolParser::kHeader;

void ProtocolParser::reset() {
    buffer_.clear();
    stats_ = ProtocolParserStats{};
}

std::uint8_t ProtocolParser::checksum(
    std::uint8_t command,
    const std::uint8_t* payload,
    std::size_t payload_size) {
    std::uint32_t sum = command + static_cast<std::uint8_t>(payload_size);
    for (std::size_t index = 0; index < payload_size; ++index) {
        sum += payload[index];
    }
    return static_cast<std::uint8_t>(~sum);
}

std::vector<ProtocolFrame> ProtocolParser::feed(
    const std::uint8_t* data,
    std::size_t size) {
    stats_.bytes_received += size;
    if (data != nullptr && size != 0) {
        buffer_.insert(buffer_.end(), data, data + size);
    }

    std::vector<ProtocolFrame> frames;
    while (!buffer_.empty()) {
        const auto header = std::find(buffer_.begin(), buffer_.end(), kHeader);
        if (header != buffer_.begin()) {
            const std::size_t discarded =
                static_cast<std::size_t>(std::distance(buffer_.begin(), header));
            stats_.discarded_bytes += discarded;
            buffer_.erase(buffer_.begin(), header);
        }
        if (buffer_.size() < 4) {
            break;
        }

        const std::uint8_t command = buffer_[1];
        const std::size_t payload_size = buffer_[2];
        const std::size_t frame_size = payload_size + 4;
        if (buffer_.size() < frame_size) {
            break;
        }

        const std::uint8_t expected = checksum(
            command,
            payload_size == 0 ? nullptr : &buffer_[3],
            payload_size);
        const std::uint8_t actual = buffer_[frame_size - 1];
        if (expected != actual) {
            ++stats_.checksum_errors;
            ++stats_.discarded_bytes;
            buffer_.erase(buffer_.begin());
            continue;
        }

        ProtocolFrame frame;
        frame.command = command;
        frame.payload.assign(buffer_.begin() + 3, buffer_.begin() + 3 + payload_size);
        frame.raw.assign(buffer_.begin(), buffer_.begin() + frame_size);
        frames.push_back(frame);
        ++stats_.valid_packets;
        ++stats_.command_count[command];
        buffer_.erase(buffer_.begin(), buffer_.begin() + frame_size);
    }
    return frames;
}

}  // namespace dashboard
