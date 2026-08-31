#include "replay_source.h"

#include <cstdio>
#include <fstream>

namespace dashboard {
namespace sim {

ReplaySource::ReplaySource(OriginalMcuAdapter& adapter, std::uint64_t start_ms)
    : adapter_(adapter), start_ms_(start_ms) {}

bool ReplaySource::load(const std::string& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) {
        return false;
    }
    std::vector<std::uint8_t> data(
        (std::istreambuf_iterator<char>(in)),
        std::istreambuf_iterator<char>());

    // Parse 2E CMD LEN PAYLOAD CHECKSUM frames; checksum = ~(CMD+LEN+sum)&0xFF.
    std::size_t i = 0;
    std::uint64_t frame_index = 0;
    while (i + 3 < data.size()) {
        if (data[i] != ProtocolParser::kHeader) {
            ++i;
            continue;
        }
        const std::uint8_t cmd = data[i + 1];
        const std::uint8_t len = data[i + 2];
        if (i + 3U + len + 1U > data.size()) {
            break;
        }
        const std::vector<std::uint8_t> payload(data.begin() + i + 3,
                                                data.begin() + i + 3 + len);
        const std::uint8_t cs = data[i + 3 + len];
        if (cs != ProtocolParser::checksum(cmd, payload.data(), payload.size())) {
            ++i;
            continue;
        }
        Frame frame;
        // Recorded sessions ran at roughly 40 frames/s; assign nominal timings.
        frame.time_ms = static_cast<std::uint64_t>(frame_index * 25);
        frame.raw.assign(data.begin() + i, data.begin() + i + 3 + len + 1);
        frames_.push_back(std::move(frame));
        i += 3U + len + 1U;
        ++frame_index;
    }
    first_frame_ms_ = frames_.empty() ? 0 : frames_[0].time_ms;
    next_index_ = 0;
    return !frames_.empty();
}

void ReplaySource::tick(std::uint64_t now_ms) {
    if (frames_.empty() || next_index_ >= frames_.size()) {
        return;
    }
    const std::uint64_t elapsed = now_ms >= start_ms_ ? now_ms - start_ms_ : 0;
    while (next_index_ < frames_.size()) {
        const std::uint64_t frame_time =
            frames_[next_index_].time_ms - first_frame_ms_;
        if (frame_time > elapsed) {
            break;
        }
        const Frame& frame = frames_[next_index_];
        adapter_.feed(frame.raw.data(), frame.raw.size(),
                      start_ms_ + frame_time);
        ++next_index_;
    }
}

void ReplaySource::reset() {
    next_index_ = 0;
}

}  // namespace sim
}  // namespace dashboard
