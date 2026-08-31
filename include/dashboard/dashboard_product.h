#pragma once

#include "dashboard/data_source.h"
#include "dashboard/product_state.h"
#include "dashboard/vehicle_state.h"

#include <cstdint>
#include <string>
#include <vector>

namespace dashboard {

enum class DashboardPage : std::uint8_t {
    Horizon = 0,
    Mono,
    Pulse,
    Route,
    Studio,
    Energy,
    Nocturne,
};

enum class DashboardTheme : std::uint8_t {
    Dark = 0,
    Graphite,
    Light,
    Auto,
};

struct ThemePalette {
    std::uint32_t background{0x0A0E12};
    std::uint32_t panel{0x0F151B};
    std::uint32_t panel_border{0x222B34};
    std::uint32_t primary{0xF4F6F8};
    std::uint32_t secondary{0x8994A0};
    std::uint32_t accent{0x3D9BFF};
    std::uint32_t success{0x3DD68C};
    std::uint32_t caution{0xF5A623};
    std::uint32_t danger{0xE5484D};
};

class ThemeManager {
public:
    void setTheme(DashboardTheme theme) { theme_ = theme; }
    DashboardTheme theme() const { return theme_; }
    DashboardTheme resolvedTheme(bool night) const;
    ThemePalette palette(bool night) const;

private:
    DashboardTheme theme_{DashboardTheme::Dark};
};

class PageManager {
public:
    DashboardPage page() const { return page_; }
    DashboardPage previousPage() const { return previous_page_; }
    void setPage(DashboardPage page);
    void next();
    void previous();
    float transitionProgress() const { return transition_progress_; }
    void tick(std::uint32_t delta_ms, bool motion_enabled);

private:
    DashboardPage page_{DashboardPage::Horizon};
    DashboardPage previous_page_{DashboardPage::Horizon};
    float transition_progress_{1.0F};
};

enum class MotionChannel : std::uint8_t {
    Speed = 0,
    Soc,
    Theme,
    Door,
};

class MotionEngine {
public:
    void setEnabled(bool enabled) { enabled_ = enabled; }
    bool enabled() const { return enabled_; }
    float animate(MotionChannel channel, float target, std::uint32_t delta_ms);
    void reset(MotionChannel channel, float value);

private:
    struct ChannelState {
        float value{0.0F};
        bool initialized{false};
    };
    ChannelState channels_[4];
    bool enabled_{true};
};

enum class WarningSeverity : std::uint8_t {
    Info = 0,
    Caution,
    Warning,
    Critical,
};

struct WarningItem {
    std::string id;
    std::string title;
    std::string detail;
    WarningSeverity severity{WarningSeverity::Info};
    bool persistent{false};
};

struct SafetyInputs {
    bool vehicle_link_connected{true};
    bool vehicle_link_has_data{true};
    std::uint64_t vehicle_link_age_ms{0};
};

class WarningManager {
public:
    void evaluate(const VehicleState& state, const SafetyInputs& inputs);
    const std::vector<WarningItem>& warnings() const { return warnings_; }
    const WarningItem* highest() const;

private:
    std::vector<WarningItem> warnings_;
};

enum class ContextCardKind : std::uint8_t {
    None = 0,
    Media,
    Navigation,
    Warning,
};

struct ContextDecision {
    ContextCardKind card{ContextCardKind::None};
    DashboardPage suggested_page{DashboardPage::Horizon};
    bool request_full_page{false};
};

class ContextRouter {
public:
    ContextDecision decide(
        const ProductState& product,
        const WarningManager& warnings,
        bool performance_timer_armed) const;
};

struct SafetyLayerState {
    bool speed_available{false};
    std::uint16_t speed_kph{0};
    bool gear_available{false};
    Gear gear{Gear::Unknown};
    bool soc_available{false};
    std::uint8_t soc_percent{0};
    bool soc_verified{false};
    const WarningItem* top_warning{nullptr};
};

SafetyLayerState buildSafetyLayer(
    const VehicleState& state,
    const WarningManager& warnings);

const char* dashboardPageName(DashboardPage page);

}  // namespace dashboard
