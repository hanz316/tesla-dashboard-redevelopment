#include "dashboard/dashboard_product.h"

#include <algorithm>
#include <cmath>

namespace dashboard {
namespace {

ThemePalette darkPalette() {
    return ThemePalette{};
}

ThemePalette graphitePalette() {
    ThemePalette p;
    p.background = 0x121519;
    p.panel = 0x191D22;
    p.panel_border = 0x2E343C;
    p.primary = 0xF6F7F9;
    p.secondary = 0x9CA4AE;
    p.accent = 0x72AEFF;
    p.success = 0x49CD8E;
    p.caution = 0xEFAE47;
    p.danger = 0xE65258;
    return p;
}

ThemePalette lightPalette() {
    ThemePalette p;
    p.background = 0xEEF2F5;
    p.panel = 0xFFFFFF;
    p.panel_border = 0xD7DEE5;
    p.primary = 0x11161C;
    p.secondary = 0x66717D;
    p.accent = 0x1577D4;
    p.success = 0x188A58;
    p.caution = 0xA86500;
    p.danger = 0xB4232C;
    return p;
}

int severityRank(WarningSeverity severity) {
    return static_cast<int>(severity);
}

bool anyOpen(const VehicleState& s) {
    return (s.door_fl.valid && s.door_fl.value) ||
        (s.door_fr.valid && s.door_fr.value) ||
        (s.door_rl.valid && s.door_rl.value) ||
        (s.door_rr.valid && s.door_rr.value) ||
        (s.frunk.valid && s.frunk.value) ||
        (s.trunk.valid && s.trunk.value);
}

}  // namespace

DashboardTheme ThemeManager::resolvedTheme(bool night) const {
    if (theme_ == DashboardTheme::Auto) {
        return night ? DashboardTheme::Dark : DashboardTheme::Light;
    }
    return theme_;
}

ThemePalette ThemeManager::palette(bool night) const {
    switch (resolvedTheme(night)) {
        case DashboardTheme::Graphite:
            return graphitePalette();
        case DashboardTheme::Light:
            return lightPalette();
        case DashboardTheme::Dark:
        case DashboardTheme::Auto:
        default:
            return darkPalette();
    }
}

void PageManager::setPage(DashboardPage page) {
    if (page == page_) return;
    previous_page_ = page_;
    page_ = page;
    transition_progress_ = 0.0F;
}

void PageManager::next() {
    const int value = (static_cast<int>(page_) + 1) % 7;
    setPage(static_cast<DashboardPage>(value));
}

void PageManager::previous() {
    const int current = static_cast<int>(page_);
    setPage(static_cast<DashboardPage>((current + 6) % 7));
}

void PageManager::tick(std::uint32_t delta_ms, bool motion_enabled) {
    if (!motion_enabled) {
        transition_progress_ = 1.0F;
        return;
    }
    if (transition_progress_ >= 1.0F) return;
    const float duration_ms = 320.0F;
    transition_progress_ = std::min(
        1.0F,
        transition_progress_ + static_cast<float>(delta_ms) / duration_ms);
}

float MotionEngine::animate(
    MotionChannel channel,
    float target,
    std::uint32_t delta_ms) {
    ChannelState& state = channels_[static_cast<int>(channel)];
    if (!state.initialized || !enabled_) {
        state.value = target;
        state.initialized = true;
        return state.value;
    }

    const float dt = std::min(100.0F, static_cast<float>(delta_ms));
    const float tau = channel == MotionChannel::Speed ? 85.0F : 160.0F;
    const float alpha = 1.0F - std::exp(-dt / tau);
    state.value += (target - state.value) * alpha;

    if (std::fabs(target - state.value) < 0.05F) {
        state.value = target;
    }
    return state.value;
}

void MotionEngine::reset(MotionChannel channel, float value) {
    ChannelState& state = channels_[static_cast<int>(channel)];
    state.value = value;
    state.initialized = true;
}

void WarningManager::evaluate(
    const VehicleState& state,
    const SafetyInputs& inputs) {
    warnings_.clear();

    if (!inputs.vehicle_link_connected ||
        !inputs.vehicle_link_has_data ||
        inputs.vehicle_link_age_ms > 5000) {
        warnings_.push_back(WarningItem{
            "vehicle-data-lost",
            "VEHICLE DATA LOST",
            "Core vehicle telemetry unavailable",
            WarningSeverity::Critical,
            true});
        return;
    }

    const bool moving = state.speed.valid && state.speed.value > 0;
    if (moving && state.trunk.valid && state.trunk.value) {
        warnings_.push_back(WarningItem{
            "trunk-open-moving",
            "TRUNK OPEN",
            "Stop safely and close the trunk",
            WarningSeverity::Warning,
            true});
    }
    if (moving && state.frunk.valid && state.frunk.value) {
        warnings_.push_back(WarningItem{
            "frunk-open-moving",
            "FRUNK OPEN",
            "Stop safely and close the frunk",
            WarningSeverity::Critical,
            true});
    }
    if (moving && anyOpen(state)) {
        warnings_.push_back(WarningItem{
            "door-open-moving",
            "DOOR OPEN",
            "A closure is open while moving",
            WarningSeverity::Warning,
            true});
    }

    const Signal<std::uint8_t>& soc =
        state.actual_soc.valid ? state.actual_soc : state.soc;
    if (state.actual_soc.valid && soc.value <= 5) {
        warnings_.push_back(WarningItem{
            "soc-critical",
            "BATTERY VERY LOW",
            "Charge as soon as possible",
            WarningSeverity::Critical,
            true});
    } else if (state.actual_soc.valid && soc.value <= 12) {
        warnings_.push_back(WarningItem{
            "soc-low",
            "BATTERY LOW",
            "Plan a charging stop",
            WarningSeverity::Caution,
            true});
    }
}

const WarningItem* WarningManager::highest() const {
    if (warnings_.empty()) return nullptr;
    return &*std::max_element(
        warnings_.begin(), warnings_.end(),
        [](const WarningItem& a, const WarningItem& b) {
            return severityRank(a.severity) < severityRank(b.severity);
        });
}

ContextDecision ContextRouter::decide(
    const ProductState& product,
    const WarningManager& warnings,
    bool performance_timer_armed) const {
    ContextDecision result;
    const WarningItem* top = warnings.highest();
    if (top != nullptr && top->severity >= WarningSeverity::Caution) {
        result.card = ContextCardKind::Warning;
        return result;
    }
    if (product.navigation.active) {
        result.card = ContextCardKind::Navigation;
        result.suggested_page = DashboardPage::Route;
        return result;
    }
    if (performance_timer_armed) {
        result.suggested_page = DashboardPage::Pulse;
        return result;
    }
    if (product.media.available) {
        result.card = ContextCardKind::Media;
    }
    return result;
}

SafetyLayerState buildSafetyLayer(
    const VehicleState& state,
    const WarningManager& warnings) {
    SafetyLayerState result;
    result.speed_available = state.speed.valid;
    result.speed_kph = state.speed.value;
    result.gear_available = state.gear.valid;
    result.gear = state.gear.value;

    if (state.actual_soc.valid) {
        result.soc_available = true;
        result.soc_percent = state.actual_soc.value;
        result.soc_verified = true;
    } else if (state.soc.valid) {
        result.soc_available = true;
        result.soc_percent = state.soc.value;
        result.soc_verified = false;
    }

    result.top_warning = warnings.highest();
    return result;
}

const char* dashboardPageName(DashboardPage page) {
    switch (page) {
        case DashboardPage::Horizon: return "HORIZON";
        case DashboardPage::Mono: return "MONO";
        case DashboardPage::Pulse: return "PULSE";
        case DashboardPage::Route: return "ROUTE";
        case DashboardPage::Studio: return "STUDIO";
        case DashboardPage::Energy: return "ENERGY";
        case DashboardPage::Nocturne: return "NOCTURNE";
        default: return "UNKNOWN";
    }
}

}  // namespace dashboard
