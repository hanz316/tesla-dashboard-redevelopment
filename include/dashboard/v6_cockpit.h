#pragma once

#include "dashboard/vehicle_state.h"

#include <cstdint>
#include <map>
#include <string>
#include <vector>

namespace dashboard {

enum class MotionQuality : std::uint8_t { Off = 0, Low, Full };
enum class MotionPriority : std::uint8_t { Ambient = 0, Page, Warning, Driving, Critical };

enum class WarningSeverity : std::uint8_t { Info = 0, Caution, Warning, Critical };
enum class WarningCode : std::uint8_t {
    None = 0,
    DoorOpenMoving,
    FrunkOpenMoving,
    TrunkOpenMoving,
    LowTire,
    LowSoc,
    VehicleDataLost,
};

struct WarningState {
    WarningCode code{WarningCode::None};
    WarningSeverity severity{WarningSeverity::Info};
    bool active{false};
};

class WarningManager {
public:
    WarningState evaluate(const VehicleState& state) const;
};

struct MotionValue {
    float raw{0.0F};
    float display{0.0F};
    bool initialized{false};
};

class MotionEngine {
public:
    explicit MotionEngine(MotionQuality quality = MotionQuality::Full) : quality_(quality) {}
    void setQuality(MotionQuality quality) { quality_ = quality; }
    MotionQuality quality() const { return quality_; }
    float update(MotionValue& value, float raw, std::uint32_t dt_ms,
                 std::uint32_t duration_ms, MotionPriority priority);

private:
    MotionQuality quality_;
};

struct AssetDescriptor {
    std::string id;
    std::string path;
    std::uint32_t estimated_bytes{0};
    bool shared{false};
};

class AssetManager {
public:
    explicit AssetManager(std::uint32_t cache_budget_bytes = 32U * 1024U * 1024U)
        : budget_(cache_budget_bytes) {}

    void registerAsset(const AssetDescriptor& asset);
    bool acquire(const std::string& id);
    void release(const std::string& id);
    std::uint32_t estimatedResidentBytes() const { return resident_bytes_; }
    std::uint32_t budgetBytes() const { return budget_; }
    bool isResident(const std::string& id) const;

private:
    struct Entry {
        AssetDescriptor asset;
        std::uint32_t refs{0};
        bool resident{false};
    };
    std::map<std::string, Entry> entries_;
    std::uint32_t budget_{0};
    std::uint32_t resident_bytes_{0};
};

struct VehicleVisualModel {
    bool door_fl{false};
    bool door_fr{false};
    bool door_rl{false};
    bool door_rr{false};
    bool frunk{false};
    bool trunk{false};
    bool headlights{false};
    bool high_beam{false};
    bool brake_lights{false};
    bool left_indicator{false};
    bool right_indicator{false};
    bool front_axle_active{false};
    bool rear_axle_active{false};
    float energy_halo{-0.0F};

    void updateFrom(const VehicleState& state);
};

enum class HorizonMode : std::uint8_t {
    Normal = 0,
    ApAvailable,
    ApActive,
    NavigationContext,
    LeftBlindSpot,
    RightBlindSpot,
    DataDegraded,
};

struct CoarseVehicleSlots {
    bool front{false};
    bool left{false};
    bool right{false};
    bool precise_positions_available{false};
};

struct HorizonSceneState {
    HorizonMode mode{HorizonMode::Normal};
    VehicleVisualModel vehicle;
    CoarseVehicleSlots surrounding;
    bool speed_available{false};
    std::uint16_t speed{0};
    bool gear_available{false};
    Gear gear{Gear::Unknown};
    bool soc_available{false};
    std::uint8_t soc{0};
    bool range_available{false};
    std::uint16_t range{0};
    WarningState warning;
};

HorizonSceneState buildHorizonScene(const VehicleState& state,
                                    const WarningManager& warnings);

struct SourceCandidateBase {
    int priority{0};
    std::uint64_t freshness_ms{0};
};

template <typename T>
const Signal<T>* arbitrateSignal(const Signal<T>* primary,
                                 const Signal<T>* fallback,
                                 std::uint64_t now_ms,
                                 std::uint64_t freshness_ms) {
    if (primary && primary->valid && !primary->stale && primary->ageMs(now_ms) <= freshness_ms)
        return primary;
    if (fallback && fallback->valid && !fallback->stale && fallback->ageMs(now_ms) <= freshness_ms)
        return fallback;
    return nullptr;
}

}  // namespace dashboard
