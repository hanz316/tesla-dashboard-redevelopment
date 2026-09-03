#include "dashboard/dashboard_services.h"

#include <algorithm>
#include <cmath>

namespace dashboard {

void TripComputer::initializeSlot(SlotState& slot, std::uint64_t now_ms, const VehicleState& state) {
    slot.summary = {};
    slot.summary.valid = true;
    slot.initialized = true;
    slot.start_ms = now_ms;
    slot.last_ms = now_ms;
    slot.last_speed_valid = state.speed.valid && !state.speed.stale;
    slot.last_speed_kph = slot.last_speed_valid ? static_cast<float>(state.speed.value) : 0.0F;
    if (state.actual_soc.valid && !state.actual_soc.stale) {
        slot.summary.soc_start_valid = true;
        slot.summary.soc_start = state.actual_soc.value;
    } else if (state.soc.valid && !state.soc.stale) {
        slot.summary.soc_start_valid = true;
        slot.summary.soc_start = state.soc.value;
    }
}

void TripComputer::updateSlot(SlotState& slot, std::uint64_t now_ms, const VehicleState& state) {
    if (!slot.initialized) initializeSlot(slot, now_ms, state);
    if (now_ms < slot.last_ms) {
        slot.last_ms = now_ms;
        return;
    }

    const bool speed_valid = state.speed.valid && !state.speed.stale;
    if (slot.last_speed_valid && speed_valid && now_ms > slot.last_ms) {
        const float current_speed = static_cast<float>(state.speed.value);
        const float average_interval_speed = (slot.last_speed_kph + current_speed) * 0.5F;
        const float hours = static_cast<float>(now_ms - slot.last_ms) / 3600000.0F;
        slot.summary.distance_km += average_interval_speed * hours;
        slot.summary.duration_ms += now_ms - slot.last_ms;
        slot.summary.max_speed_kph = std::max(slot.summary.max_speed_kph, current_speed);
        if (slot.summary.duration_ms > 0) {
            const float total_hours = static_cast<float>(slot.summary.duration_ms) / 3600000.0F;
            slot.summary.average_speed_kph = total_hours > 0.0F ? slot.summary.distance_km / total_hours : 0.0F;
        }
    }

    slot.last_speed_valid = speed_valid;
    slot.last_speed_kph = speed_valid ? static_cast<float>(state.speed.value) : 0.0F;
    slot.last_ms = now_ms;

    if (state.actual_soc.valid && !state.actual_soc.stale) {
        slot.summary.soc_current_valid = true;
        slot.summary.soc_current = state.actual_soc.value;
    } else if (state.soc.valid && !state.soc.stale) {
        slot.summary.soc_current_valid = true;
        slot.summary.soc_current = state.soc.value;
    }
    if (slot.summary.soc_start_valid && slot.summary.soc_current_valid) {
        slot.summary.soc_used_valid = true;
        slot.summary.soc_used = static_cast<std::int16_t>(slot.summary.soc_start) -
                                static_cast<std::int16_t>(slot.summary.soc_current);
    }
}

void TripComputer::reset(TripSlot slot, std::uint64_t now_ms, const VehicleState& state) {
    initializeSlot(slots_[index(slot)], now_ms, state);
}

void TripComputer::update(std::uint64_t now_ms, const VehicleState& state) {
    for (auto& slot : slots_) updateSlot(slot, now_ms, state);
}

const TripSummary& TripComputer::summary(TripSlot slot) const {
    return slots_[index(slot)].summary;
}

PerformanceWindow PerformanceTimer::presetWindow(PerformancePreset preset, PerformanceWindow custom) {
    switch (preset) {
        case PerformancePreset::ZeroTo50: return {0.0F, 50.0F};
        case PerformancePreset::ZeroTo100: return {0.0F, 100.0F};
        case PerformancePreset::ZeroTo160: return {0.0F, 160.0F};
        case PerformancePreset::FiftyTo100: return {50.0F, 100.0F};
        case PerformancePreset::EightyTo120: return {80.0F, 120.0F};
        case PerformancePreset::HundredTo200: return {100.0F, 200.0F};
        case PerformancePreset::Custom: return custom;
    }
    return custom;
}

void PerformanceTimer::configure(PerformancePreset preset, PerformanceWindow custom) {
    result_ = {};
    result_.window = presetWindow(preset, custom);
    if (result_.window.finish_kph <= result_.window.start_kph) result_.state = PerformanceTimerState::Invalid;
    have_previous_ = false;
}

void PerformanceTimer::arm() {
    if (result_.window.finish_kph <= result_.window.start_kph) {
        result_.state = PerformanceTimerState::Invalid;
        return;
    }
    result_.state = PerformanceTimerState::Armed;
    result_.elapsed_ms = 0;
    result_.start_timestamp_ms = 0;
    result_.finish_timestamp_ms = 0;
    result_.quality = SignalQuality::Unknown;
    have_previous_ = false;
}

void PerformanceTimer::cancel() {
    result_.state = PerformanceTimerState::Idle;
    result_.elapsed_ms = 0;
    result_.start_timestamp_ms = 0;
    result_.finish_timestamp_ms = 0;
    result_.quality = SignalQuality::Unknown;
    have_previous_ = false;
}

std::uint64_t PerformanceTimer::interpolateCrossing(std::uint16_t previous_speed,
                                                     std::uint64_t previous_timestamp_ms,
                                                     std::uint16_t current_speed,
                                                     std::uint64_t current_timestamp_ms,
                                                     float threshold_kph) {
    if (current_timestamp_ms <= previous_timestamp_ms || current_speed == previous_speed)
        return current_timestamp_ms;
    const float span = static_cast<float>(static_cast<int>(current_speed) - static_cast<int>(previous_speed));
    const float fraction = std::max(0.0F, std::min(1.0F,
        (threshold_kph - static_cast<float>(previous_speed)) / span));
    const std::uint64_t dt = current_timestamp_ms - previous_timestamp_ms;
    return previous_timestamp_ms + static_cast<std::uint64_t>(std::llround(static_cast<double>(dt) * fraction));
}

void PerformanceTimer::update(const Signal<std::uint16_t>& speed) {
    if (result_.state == PerformanceTimerState::Idle ||
        result_.state == PerformanceTimerState::Finished ||
        result_.state == PerformanceTimerState::Invalid) return;

    if (!speed.valid || speed.stale || speed.quality == SignalQuality::Unknown) {
        if (result_.state == PerformanceTimerState::Running) result_.state = PerformanceTimerState::Invalid;
        return;
    }

    if (!have_previous_) {
        have_previous_ = true;
        previous_speed_ = speed.value;
        previous_timestamp_ms_ = speed.timestamp_ms;
        return;
    }

    if (speed.timestamp_ms <= previous_timestamp_ms_) {
        result_.state = PerformanceTimerState::Invalid;
        return;
    }

    const float start = result_.window.start_kph;
    const float finish = result_.window.finish_kph;
    const bool crossed_start = static_cast<float>(previous_speed_) <= start && static_cast<float>(speed.value) > start;
    const bool crossed_finish = static_cast<float>(previous_speed_) < finish && static_cast<float>(speed.value) >= finish;

    if (result_.state == PerformanceTimerState::Armed && crossed_start) {
        result_.start_timestamp_ms = interpolateCrossing(previous_speed_, previous_timestamp_ms_, speed.value,
                                                         speed.timestamp_ms, start);
        result_.state = PerformanceTimerState::Running;
        result_.quality = speed.quality;
    }

    if (result_.state == PerformanceTimerState::Running) {
        result_.elapsed_ms = speed.timestamp_ms >= result_.start_timestamp_ms
                                 ? speed.timestamp_ms - result_.start_timestamp_ms
                                 : 0;
        if (crossed_finish || static_cast<float>(speed.value) >= finish) {
            result_.finish_timestamp_ms = crossed_finish
                ? interpolateCrossing(previous_speed_, previous_timestamp_ms_, speed.value, speed.timestamp_ms, finish)
                : speed.timestamp_ms;
            if (result_.finish_timestamp_ms < result_.start_timestamp_ms) {
                result_.state = PerformanceTimerState::Invalid;
            } else {
                result_.elapsed_ms = result_.finish_timestamp_ms - result_.start_timestamp_ms;
                result_.state = PerformanceTimerState::Finished;
                if (speed.quality > result_.quality) result_.quality = speed.quality;
            }
        }
    }

    previous_speed_ = speed.value;
    previous_timestamp_ms_ = speed.timestamp_ms;
}

}  // namespace dashboard
