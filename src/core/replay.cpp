#include "dashboard/replay.h"

#include <algorithm>
#include <fstream>
#include <iomanip>
#include <sstream>

namespace dashboard {

namespace {

std::string bytesToHex(const std::vector<std::uint8_t>& bytes) {
    std::ostringstream out;
    out << std::hex << std::setfill('0');
    for (std::size_t i = 0; i < bytes.size(); ++i) {
        if (i) out << ' ';
        out << std::setw(2) << static_cast<unsigned>(bytes[i]);
    }
    return out.str();
}

bool hexToBytes(const std::string& text, std::vector<std::uint8_t>& out) {
    out.clear();
    std::istringstream in(text);
    std::string token;
    while (in >> token) {
        if (token.size() != 2) return false;
        unsigned value = 0;
        std::istringstream value_stream(token);
        value_stream >> std::hex >> value;
        if (!value_stream || value > 0xffU) return false;
        out.push_back(static_cast<std::uint8_t>(value));
    }
    return true;
}

}  // namespace

void UartRecorder::capture(const ProtocolFrame& frame, std::uint64_t timestamp_ms, bool parse_ok) {
    ReplayRecord record;
    record.timestamp_ms = timestamp_ms;
    record.command = frame.command;
    record.payload = frame.payload;
    record.raw = frame.raw;
    record.checksum = frame.raw.empty() ? 0 : frame.raw.back();
    record.parse_ok = parse_ok;
    records_.push_back(std::move(record));
}

bool UartRecorder::save(const std::string& path) const {
    std::ofstream out(path.c_str(), std::ios::out | std::ios::trunc);
    if (!out) return false;
    out << "# timestamp_ms\tcommand\tchecksum\tparse_ok\tpayload_hex\traw_hex\n";
    for (const auto& record : records_) {
        out << record.timestamp_ms << '\t'
            << static_cast<unsigned>(record.command) << '\t'
            << static_cast<unsigned>(record.checksum) << '\t'
            << (record.parse_ok ? 1 : 0) << '\t'
            << bytesToHex(record.payload) << '\t'
            << bytesToHex(record.raw) << '\n';
    }
    return static_cast<bool>(out);
}

bool UartRecorder::load(const std::string& path) {
    std::ifstream in(path.c_str());
    if (!in) return false;
    std::vector<ReplayRecord> parsed;
    std::string line;
    while (std::getline(in, line)) {
        if (line.empty() || line[0] == '#') continue;
        std::vector<std::string> fields;
        std::size_t start = 0;
        for (;;) {
            const std::size_t tab = line.find('\t', start);
            if (tab == std::string::npos) {
                fields.push_back(line.substr(start));
                break;
            }
            fields.push_back(line.substr(start, tab - start));
            start = tab + 1;
        }
        if (fields.size() != 6) return false;
        ReplayRecord record;
        try {
            record.timestamp_ms = static_cast<std::uint64_t>(std::stoull(fields[0]));
            record.command = static_cast<std::uint8_t>(std::stoul(fields[1]));
            record.checksum = static_cast<std::uint8_t>(std::stoul(fields[2]));
            record.parse_ok = std::stoul(fields[3]) != 0;
        } catch (...) {
            return false;
        }
        if (!hexToBytes(fields[4], record.payload) || !hexToBytes(fields[5], record.raw)) return false;
        parsed.push_back(std::move(record));
    }
    records_.swap(parsed);
    return true;
}

ReplayAdapter::ReplayAdapter()
    : adapter_([] {
          OriginalMcuConfig config;
          config.signal_source = SignalSource::Replay;
          return config;
      }()) {
    health_.status = DataSourceStatus::Offline;
}

void ReplayAdapter::load(std::vector<ReplayRecord> records) {
    records_ = std::move(records);
    std::sort(records_.begin(), records_.end(), [](const ReplayRecord& a, const ReplayRecord& b) {
        return a.timestamp_ms < b.timestamp_ms;
    });
    cursor_ = 0;
    playing_ = false;
    adapter_.reset();
    health_ = {};
    health_.status = records_.empty() ? DataSourceStatus::Offline : DataSourceStatus::Connected;
    recording_start_ms_ = records_.empty() ? 0 : records_.front().timestamp_ms;
}

void ReplayAdapter::setRate(float rate) {
    if (rate <= 0.0F) return;
    rate_ = std::max(0.5F, std::min(2.0F, rate));
}

void ReplayAdapter::play(std::uint64_t now_ms) {
    if (records_.empty()) return;
    if (cursor_ >= records_.size()) return;
    recording_start_ms_ = currentRecordingTimestamp();
    wall_start_ms_ = now_ms;
    playing_ = true;
    health_.status = DataSourceStatus::Connected;
}

void ReplayAdapter::pause() {
    playing_ = false;
}

void ReplayAdapter::restart(std::uint64_t now_ms) {
    adapter_.reset();
    cursor_ = 0;
    recording_start_ms_ = records_.empty() ? 0 : records_.front().timestamp_ms;
    wall_start_ms_ = now_ms;
    playing_ = !records_.empty();
}

void ReplayAdapter::rebuildTo(std::size_t end_exclusive) {
    adapter_.reset();
    const std::size_t end = std::min(end_exclusive, records_.size());
    for (std::size_t i = 0; i < end; ++i) {
        if (!records_[i].raw.empty())
            adapter_.feed(records_[i].raw.data(), records_[i].raw.size(), records_[i].timestamp_ms);
    }
    cursor_ = end;
}

void ReplayAdapter::seek(std::uint64_t recording_timestamp_ms, std::uint64_t now_ms) {
    // Rebuild all frames at or before the target so paused seek immediately
    // exposes the state of the selected recording time. The next tick resumes
    // from the first frame after the target, using the recording timeline.
    auto it = std::upper_bound(records_.begin(), records_.end(), recording_timestamp_ms,
        [](std::uint64_t timestamp, const ReplayRecord& record) {
            return timestamp < record.timestamp_ms;
        });
    rebuildTo(static_cast<std::size_t>(it - records_.begin()));
    recording_start_ms_ = recording_timestamp_ms;
    wall_start_ms_ = now_ms;
    if (cursor_ >= records_.size()) playing_ = false;
}

std::uint64_t ReplayAdapter::currentRecordingTimestamp() const {
    if (records_.empty()) return 0;
    if (cursor_ == 0) return recording_start_ms_;
    return records_[std::min(cursor_ - 1, records_.size() - 1)].timestamp_ms;
}

void ReplayAdapter::tick(std::uint64_t now_ms) {
    if (records_.empty()) {
        health_.status = DataSourceStatus::Offline;
        return;
    }

    if (!playing_ || cursor_ >= records_.size()) {
        // Never compare recording sample timestamps with host wall-clock time.
        adapter_.tick(currentRecordingTimestamp());
        if (cursor_ >= records_.size()) playing_ = false;
        return;
    }

    const double elapsed_wall = static_cast<double>(now_ms - wall_start_ms_);
    const std::uint64_t target = recording_start_ms_ +
        static_cast<std::uint64_t>(elapsed_wall * static_cast<double>(rate_));

    while (cursor_ < records_.size() && records_[cursor_].timestamp_ms <= target) {
        const ReplayRecord& record = records_[cursor_];
        if (!record.raw.empty()) adapter_.feed(record.raw.data(), record.raw.size(), record.timestamp_ms);
        health_.last_update_ms = now_ms;
        ++health_.packets;
        ++cursor_;
    }

    if (cursor_ >= records_.size()) playing_ = false;
    adapter_.tick(target);
}

}  // namespace dashboard
