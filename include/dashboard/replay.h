#pragma once

#include "dashboard/data_source.h"
#include "dashboard/original_mcu_adapter.h"

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace dashboard {

struct ReplayRecord {
    std::uint64_t timestamp_ms{0};
    std::uint8_t command{0};
    std::vector<std::uint8_t> payload;
    std::vector<std::uint8_t> raw;
    std::uint8_t checksum{0};
    bool parse_ok{false};
};

class UartRecorder {
public:
    void clear() { records_.clear(); }
    void capture(const ProtocolFrame& frame, std::uint64_t timestamp_ms, bool parse_ok = true);
    const std::vector<ReplayRecord>& records() const { return records_; }
    bool save(const std::string& path) const;
    bool load(const std::string& path);

private:
    std::vector<ReplayRecord> records_;
};

class ReplayAdapter final : public IDataSource {
public:
    ReplayAdapter();

    const char* name() const override { return "ReplayAdapter"; }
    SignalSource source() const override { return SignalSource::Replay; }
    const VehicleState& state() const override { return adapter_.state(); }
    const DataSourceHealth& health() const override { return health_; }
    void tick(std::uint64_t now_ms) override;

    void load(std::vector<ReplayRecord> records);
    void play(std::uint64_t now_ms);
    void pause();
    void restart(std::uint64_t now_ms);
    void seek(std::uint64_t recording_timestamp_ms, std::uint64_t now_ms);
    void setRate(float rate);
    float rate() const { return rate_; }
    bool playing() const { return playing_; }
    std::size_t cursor() const { return cursor_; }
    std::uint64_t currentRecordingTimestamp() const;

private:
    void rebuildTo(std::size_t end_exclusive);

    OriginalMcuAdapter adapter_;
    DataSourceHealth health_;
    std::vector<ReplayRecord> records_;
    std::size_t cursor_{0};
    float rate_{1.0F};
    bool playing_{false};
    std::uint64_t wall_start_ms_{0};
    std::uint64_t recording_start_ms_{0};
};

}  // namespace dashboard
