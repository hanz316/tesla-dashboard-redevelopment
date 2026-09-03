#pragma once

#include "dashboard/vehicle_state.h"

#include <cstdint>
#include <vector>

namespace dashboard {

struct SourcePreference {
    SignalSource source{SignalSource::Unavailable};
    int priority{0};
};

struct ArbitrationPolicy {
    std::uint64_t freshness_ms{1000};
    std::vector<SourcePreference> preferences;
};

class SourceArbitrator {
public:
    template <typename T>
    const Signal<T>* choose(const std::vector<const Signal<T>*>& candidates,
                            const ArbitrationPolicy& policy,
                            std::uint64_t now_ms) const {
        const Signal<T>* best = nullptr;
        int best_priority = -2147483647;
        int best_quality = -1;
        std::uint64_t best_timestamp = 0;
        for (const Signal<T>* candidate : candidates) {
            if (!candidate || !candidate->valid || candidate->stale) continue;
            if (candidate->ageMs(now_ms) > policy.freshness_ms) continue;
            int priority = 0;
            for (const SourcePreference& preference : policy.preferences) {
                if (preference.source == candidate->source) {
                    priority = preference.priority;
                    break;
                }
            }
            const int quality = qualityRank(candidate->quality);
            if (!best || priority > best_priority ||
                (priority == best_priority && quality > best_quality) ||
                (priority == best_priority && quality == best_quality &&
                 candidate->timestamp_ms > best_timestamp)) {
                best = candidate;
                best_priority = priority;
                best_quality = quality;
                best_timestamp = candidate->timestamp_ms;
            }
        }
        return best;
    }

    static ArbitrationPolicy originalMcuPrimary(std::uint64_t freshness_ms) {
        ArbitrationPolicy p;
        p.freshness_ms = freshness_ms;
        p.preferences = {
            {SignalSource::OriginalMcu, 100},
            {SignalSource::Commander, 80},
            {SignalSource::Replay, 60},
            {SignalSource::Simulation, 40},
        };
        return p;
    }

    static ArbitrationPolicy commanderOnly(std::uint64_t freshness_ms) {
        ArbitrationPolicy p;
        p.freshness_ms = freshness_ms;
        p.preferences = {
            {SignalSource::Commander, 100},
            {SignalSource::Replay, 60},
            {SignalSource::Simulation, 40},
        };
        return p;
    }

private:
    static int qualityRank(SignalQuality quality) {
        switch (quality) {
            case SignalQuality::Confirmed: return 4;
            case SignalQuality::Inferred: return 3;
            case SignalQuality::Estimated: return 2;
            case SignalQuality::Unknown: default: return 1;
        }
    }
};

}  // namespace dashboard
