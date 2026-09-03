#pragma once

#include "dashboard/vehicle_state.h"

#include <cstdint>

namespace dashboard {

enum class TripSlot : std::uint8_t { CurrentDrive = 0, TripA, TripB, SinceCharge };

struct TripSummary {
    bool valid{false};
    float distance_km{0.0F};
    std::uint64_t duration_ms{0};
    float average_speed_kph{0.0F};
    float max_speed_kph{0.0F};
    bool soc_start_valid{false};
    std::uint8_t soc_start{0};
    bool soc_current_valid{false};
    std::uint8_t soc_current{0};
    bool soc_used_valid{false};
    std::int16_t soc_used{0};
};

class TripComputer {
public:
    void reset(TripSlot slot, std::uint64_t now_ms, const VehicleState& state);
    void update(std::uint64_t now_ms, const VehicleState& state);
    const TripSummary& summary(TripSlot slot) const;

private:
    struct SlotState {
        TripSummary summary;
        bool initialized{false};
        std::uint64_t start_ms{0};
        std::uint64_t last_ms{0};
        float last_speed_kph{0.0F};
        bool last_speed_valid{false};
    };

    SlotState slots_[4];
    static std::size_t index(TripSlot slot) { return static_cast<std::size_t>(slot); }
    static void initializeSlot(SlotState& slot, std::uint64_t now_ms, const VehicleState& state);
    static void updateSlot(SlotState& slot, std::uint64_t now_ms, const VehicleState& state);
};

enum class PerformancePreset : std::uint8_t {
    ZeroTo50 = 0,
    ZeroTo100,
    ZeroTo160,
    FiftyTo100,
    EightyTo120,
    HundredTo200,
    Custom,
};

enum class PerformanceTimerState : std::uint8_t { Idle = 0, Armed, Running, Finished, Invalid };

struct PerformanceWindow {
    float start_kph{0.0F};
    float finish_kph{100.0F};
};

struct PerformanceResult {
    PerformanceTimerState state{PerformanceTimerState::Idle};
    PerformanceWindow window;
    std::uint64_t elapsed_ms{0};
    std::uint64_t start_timestamp_ms{0};
    std::uint64_t finish_timestamp_ms{0};
    SignalQuality quality{SignalQuality::Unknown};
};

class PerformanceTimer {
public:
    void configure(PerformancePreset preset, PerformanceWindow custom = {});
    void arm();
    void cancel();
    void update(const Signal<std::uint16_t>& speed);
    const PerformanceResult& result() const { return result_; }

private:
    PerformanceResult result_;
    bool have_previous_{false};
    std::uint16_t previous_speed_{0};
    std::uint64_t previous_timestamp_ms_{0};

    static PerformanceWindow presetWindow(PerformancePreset preset, PerformanceWindow custom);
    static std::uint64_t interpolateCrossing(std::uint16_t previous_speed,
                                             std::uint64_t previous_timestamp_ms,
                                             std::uint16_t current_speed,
                                             std::uint64_t current_timestamp_ms,
                                             float threshold_kph);
};

}  // namespace dashboard
