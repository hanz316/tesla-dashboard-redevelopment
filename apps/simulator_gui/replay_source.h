#pragma once

#include "dashboard/original_mcu_adapter.h"

#include <cstdint>
#include <string>
#include <vector>

namespace dashboard {
namespace sim {

// Feeds a recorded raw UART stream into an OriginalMcuAdapter at the
// captured pace, so the host simulator displays real vehicle data.
class ReplaySource {
public:
    ReplaySource(OriginalMcuAdapter& adapter, std::uint64_t start_ms);

    // Loads a raw recording (e.g. captures/uart-record-realcar-*.bin).
    bool load(const std::string& path);
    std::size_t frameCount() const { return frames_.size(); }

    // Advance playback to now_ms, feeding any frames due since the last call.
    void tick(std::uint64_t now_ms);
    bool finished() const { return next_index_ >= frames_.size(); }
    void reset();

private:
    struct Frame {
        std::uint64_t time_ms{0};
        std::vector<std::uint8_t> raw;
    };

    OriginalMcuAdapter& adapter_;
    std::uint64_t start_ms_{0};
    std::uint64_t first_frame_ms_{0};
    std::vector<Frame> frames_;
    std::size_t next_index_{0};
};

}  // namespace sim
}  // namespace dashboard
