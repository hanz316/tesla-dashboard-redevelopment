#pragma once

#include "dashboard/product_state_v6.h"
#include "dashboard/v6_cockpit.h"

#include <cstdint>

namespace dashboard {

enum class DashboardPageV6 : std::uint8_t {
    Horizon = 0,
    Mono,
    Pulse,
    Route,
    Studio,
    Energy,
    Nocturne,
    Settings,
    Developer,
};

enum class AppearanceMode : std::uint8_t { Day = 0, Night, Auto };
enum class DistanceUnit : std::uint8_t { Kilometer = 0, Mile };
enum class TemperatureUnit : std::uint8_t { Celsius = 0, Fahrenheit };
enum class TirePressureUnit : std::uint8_t { Bar = 0, Psi, Kpa };

struct DashboardSettings {
    DashboardPageV6 default_page{DashboardPageV6::Horizon};
    AppearanceMode appearance{AppearanceMode::Auto};
    std::uint8_t brightness_percent{100};
    DistanceUnit distance_unit{DistanceUnit::Kilometer};
    TemperatureUnit temperature_unit{TemperatureUnit::Celsius};
    TirePressureUnit tire_pressure_unit{TirePressureUnit::Bar};
    bool clock_24h{true};
    MotionQuality motion_quality{MotionQuality::Full};
    bool warning_sound_enabled{true};
    bool developer_mode_enabled{false};
};

struct PageTransitionState {
    DashboardPageV6 current{DashboardPageV6::Horizon};
    DashboardPageV6 target{DashboardPageV6::Horizon};
    bool active{false};
    std::uint32_t elapsed_ms{0};
    std::uint32_t duration_ms{320};
    float progress{1.0F};
    float opacity{1.0F};
    float translation_x{0.0F};
    float scale{1.0F};
};

class PageManagerV6 {
public:
    explicit PageManagerV6(DashboardPageV6 initial = DashboardPageV6::Horizon);
    DashboardPageV6 current() const { return state_.current; }
    const PageTransitionState& state() const { return state_; }
    void request(DashboardPageV6 page, bool safety_interrupt = false);
    void update(std::uint32_t dt_ms, MotionQuality quality);

private:
    PageTransitionState state_;
};

enum class DataAvailabilityLevel : std::uint8_t {
    Available = 0,
    IndividualSignalUnavailable,
    EnhancedModuleUnavailable,
    CoreVehicleDataLost,
};

struct SafetyLayerV6 {
    bool speed_available{false};
    std::uint16_t speed_kph{0};
    bool gear_available{false};
    Gear gear{Gear::Unknown};
    bool soc_available{false};
    std::uint8_t soc_percent{0};
    bool left_indicator{false};
    bool right_indicator{false};
    bool hazards{false};
    WarningState warning;
    DataAvailabilityLevel availability{DataAvailabilityLevel::Available};
};

SafetyLayerV6 buildSafetyLayerV6(const VehicleState& state, const WarningManager& warnings);

struct HorizonContextRailState {
    enum class Mode : std::uint8_t { None = 0, Battery, Trip, Navigation };
    Mode mode{Mode::None};
    bool soc_available{false};
    std::uint8_t soc{0};
    bool range_available{false};
    std::uint16_t range_km{0};
    bool trip_distance_available{false};
    float trip_distance_km{0.0F};
    bool trip_duration_available{false};
    std::uint64_t trip_duration_ms{0};
    bool trip_avg_speed_available{false};
    float trip_avg_speed_kph{0.0F};
    const NavigationState* navigation{nullptr};
};

HorizonContextRailState buildHorizonContextRail(const VehicleState& vehicle,
                                                const ProductStateV6& product);

}  // namespace dashboard
