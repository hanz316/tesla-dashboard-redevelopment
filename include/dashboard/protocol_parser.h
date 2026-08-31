#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <vector>

namespace dashboard {

struct ProtocolFrame {
    std::uint8_t command{0};
    std::vector<std::uint8_t> payload;
    std::vector<std::uint8_t> raw;
};

struct ProtocolParserStats {
    std::uint64_t bytes_received{0};
    std::uint64_t valid_packets{0};
    std::uint64_t checksum_errors{0};
    std::uint64_t discarded_bytes{0};
    std::array<std::uint64_t, 256> command_count{};
};

class ProtocolParser {
public:
    static constexpr std::uint8_t kHeader = 0x2e;

    std::vector<ProtocolFrame> feed(const std::uint8_t* data, std::size_t size);
    const ProtocolParserStats& stats() const { return stats_; }
    std::size_t bufferedBytes() const { return buffer_.size(); }

    static std::uint8_t checksum(
        std::uint8_t command,
        const std::uint8_t* payload,
        std::size_t payload_size);

private:
    std::vector<std::uint8_t> buffer_;
    ProtocolParserStats stats_;
};

}  // namespace dashboard
