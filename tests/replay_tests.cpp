#include "dashboard/protocol_parser.h"
#include "dashboard/replay.h"

#include <cassert>
#include <cstdint>
#include <iostream>
#include <vector>

using namespace dashboard;

static ReplayRecord makeRecord(std::uint64_t timestamp_ms, std::uint8_t command,
                               const std::vector<std::uint8_t>& payload) {
    ReplayRecord record;
    record.timestamp_ms = timestamp_ms;
    record.command = command;
    record.payload = payload;
    record.checksum = ProtocolParser::checksum(command, payload.data(), payload.size());
    record.raw.push_back(ProtocolParser::kHeader);
    record.raw.push_back(command);
    record.raw.push_back(static_cast<std::uint8_t>(payload.size()));
    record.raw.insert(record.raw.end(), payload.begin(), payload.end());
    record.raw.push_back(record.checksum);
    record.parse_ok = true;
    return record;
}

int main() {
    std::vector<ReplayRecord> records;

    records.push_back(makeRecord(1000, 0x01, {0, 0, 0, 0x01, 0x40, 0, 0, 0, 0}));

    std::vector<std::uint8_t> p04(13, 0);
    p04[0] = 72;
    p04[1] = 0;
    p04[6] = 0x1c;
    p04[7] = 0x01;
    p04[8] = 97;
    p04[10] = 0x03;
    p04[11] = 0x02;
    p04[12] = 0x01;
    records.push_back(makeRecord(1100, 0x04, p04));

    {
        ReplayAdapter replay;
        replay.load(records);
        replay.play(5000);
        replay.tick(5000);
        assert(replay.state().gear.valid);
        assert(replay.state().gear.value == Gear::Drive);
        assert(replay.state().door_fl.valid && replay.state().door_fl.value);
        replay.tick(5100);
        assert(replay.state().speed.valid && replay.state().speed.value == 72);
        assert(replay.state().range.valid && replay.state().range.value == 284);
        assert(replay.state().soc.valid && replay.state().soc.value == 97);
        assert(replay.state().soc.quality == SignalQuality::Estimated);
        assert(replay.state().soc.source == SignalSource::Replay);
        assert(!replay.playing());
    }

    {
        ReplayAdapter replay;
        replay.load(records);
        replay.setRate(2.0F);
        assert(replay.rate() == 2.0F);
        replay.restart(10000);
        replay.tick(10050);
        assert(replay.state().speed.valid && replay.state().speed.value == 72);

        replay.pause();
        replay.seek(1000, 12000);
        assert(replay.cursor() == 1);
        assert(replay.state().gear.valid && replay.state().gear.value == Gear::Drive);
        assert(!replay.state().speed.valid);

        // Paused tick uses recording time rather than host wall time, so the
        // reconstructed gear sample does not become stale simply because host
        // time is 12 seconds.
        replay.tick(30000);
        assert(replay.state().gear.valid && replay.state().gear.value == Gear::Drive);
    }

    {
        ReplayAdapter replay;
        replay.load(records);
        replay.seek(1100, 50000);
        assert(replay.cursor() == 2);
        assert(replay.state().gear.valid && replay.state().gear.value == Gear::Drive);
        assert(replay.state().speed.valid && replay.state().speed.value == 72);
    }

    {
        UartRecorder recorder;
        ProtocolFrame frame;
        frame.command = 0x12;
        frame.payload = {0, 100, 101, 102, 103};
        ReplayRecord source = makeRecord(2000, frame.command, frame.payload);
        frame.raw = source.raw;
        recorder.capture(frame, 2000, true);
        assert(recorder.records().size() == 1);
        assert(recorder.records()[0].checksum == source.checksum);
        assert(recorder.records()[0].raw == source.raw);
    }

    std::cout << "replay tests: PASS\n";
    return 0;
}
