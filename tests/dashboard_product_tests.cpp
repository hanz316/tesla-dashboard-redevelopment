#include "dashboard/dashboard_product.h"

#include <cstdlib>
#include <iostream>

namespace {

int failures = 0;

#define CHECK(x) do { if (!(x)) { std::cerr << __FILE__ << ':' << __LINE__ << " CHECK failed: " #x "\n"; ++failures; } } while (false)

void safetyPrefersActualSoc() {
    dashboard::VehicleState s;
    s.soc.update(97, 1, dashboard::SignalSource::OriginalMcu,
                 dashboard::SignalQuality::Confirmed, dashboard::Unit::Percent);
    s.actual_soc.update(68, 2, dashboard::SignalSource::Commander,
                        dashboard::SignalQuality::Confirmed, dashboard::Unit::Percent);
    dashboard::WarningManager warnings;
    warnings.evaluate(s, dashboard::SafetyInputs{});
    const auto safety = dashboard::buildSafetyLayer(s, warnings);
    CHECK(safety.soc_available);
    CHECK(safety.soc_percent == 68);
    CHECK(safety.soc_verified);
}

void fallbackSocIsMarkedUnverified() {
    dashboard::VehicleState s;
    s.soc.update(97, 1, dashboard::SignalSource::OriginalMcu,
                 dashboard::SignalQuality::Confirmed, dashboard::Unit::Percent);
    dashboard::WarningManager warnings;
    warnings.evaluate(s, dashboard::SafetyInputs{});
    const auto safety = dashboard::buildSafetyLayer(s, warnings);
    CHECK(safety.soc_available);
    CHECK(safety.soc_percent == 97);
    CHECK(!safety.soc_verified);
}

void movingOpenFrunkIsCritical() {
    dashboard::VehicleState s;
    s.speed.update(35, 1, dashboard::SignalSource::Simulation,
                   dashboard::SignalQuality::Confirmed, dashboard::Unit::KilometerPerHour);
    s.frunk.update(true, 1, dashboard::SignalSource::Simulation,
                   dashboard::SignalQuality::Confirmed, dashboard::Unit::None);
    dashboard::WarningManager warnings;
    warnings.evaluate(s, dashboard::SafetyInputs{});
    CHECK(warnings.highest() != nullptr);
    CHECK(warnings.highest()->severity == dashboard::WarningSeverity::Critical);
}

void vehicleLinkLossWins() {
    dashboard::VehicleState s;
    dashboard::WarningManager warnings;
    dashboard::SafetyInputs inputs;
    inputs.vehicle_link_connected = false;
    warnings.evaluate(s, inputs);
    CHECK(warnings.highest() != nullptr);
    CHECK(warnings.highest()->id == "vehicle-data-lost");
    CHECK(warnings.highest()->severity == dashboard::WarningSeverity::Critical);
}

void routerChangesContextNotPage() {
    dashboard::ProductState product;
    product.navigation.active = true;
    dashboard::WarningManager warnings;
    dashboard::VehicleState s;
    warnings.evaluate(s, dashboard::SafetyInputs{});
    dashboard::ContextRouter router;
    const auto decision = router.decide(product, warnings, false);
    CHECK(decision.card == dashboard::ContextCardKind::Navigation);
    CHECK(decision.suggested_page == dashboard::DashboardPage::Route);
    CHECK(!decision.request_full_page);
}

void motionCanBeDisabled() {
    dashboard::MotionEngine motion;
    motion.reset(dashboard::MotionChannel::Speed, 0.0F);
    const float animated = motion.animate(dashboard::MotionChannel::Speed, 100.0F, 33);
    CHECK(animated > 0.0F && animated < 100.0F);
    motion.setEnabled(false);
    CHECK(motion.animate(dashboard::MotionChannel::Speed, 100.0F, 33) == 100.0F);
}

void pagesCycle() {
    dashboard::PageManager pages;
    CHECK(pages.page() == dashboard::DashboardPage::Horizon);
    pages.next();
    CHECK(pages.page() == dashboard::DashboardPage::Mono);
    pages.previous();
    CHECK(pages.page() == dashboard::DashboardPage::Horizon);
}

}  // namespace

int main() {
    safetyPrefersActualSoc();
    fallbackSocIsMarkedUnverified();
    movingOpenFrunkIsCritical();
    vehicleLinkLossWins();
    routerChangesContextNotPage();
    motionCanBeDisabled();
    pagesCycle();
    if (failures != 0) return EXIT_FAILURE;
    std::cout << "Dashboard product tests passed\n";
    return EXIT_SUCCESS;
}
