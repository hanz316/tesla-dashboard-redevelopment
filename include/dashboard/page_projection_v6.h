#pragma once

#include "dashboard/commander_link.h"
#include "dashboard/product_state_v6.h"
#include "dashboard/ui_framework_v6.h"
#include "dashboard/vehicle_state.h"

#include <cstdint>
#include <map>
#include <string>
#include <vector>

namespace dashboard {

// One value a scene node can bind to.
//
// The screens use a bound value in three ways: as a number (speed, SOC, the
// fill of a bar), as a flag (a lamp, a rule that fires) and as a string (the
// link state that is compared with `equals`). One type covers all three so a
// page has a single table of values, and so the renderer never has to guess
// which kind a name is.
//
// `valid == false` is a first-class answer. It means "this signal is not
// available", which the scene renders as its own `invalid_text` - the rule
// that UNKNOWN is not 0, not OFF and not CLOSED.
struct ProjectedValueV6 {
    enum class Kind : std::uint8_t { Number = 0, Flag, Text };

    Kind kind{Kind::Number};
    bool valid{false};
    double number{0.0};
    bool flag{false};
    std::string text;
    Unit unit{Unit::None};
    SignalSource source{SignalSource::Unavailable};
    SignalQuality quality{SignalQuality::Unknown};

    static ProjectedValueV6 makeNumber(double value, Unit unit,
                                       SignalSource source, SignalQuality quality);
    static ProjectedValueV6 makeFlag(bool value, SignalSource source,
                                     SignalQuality quality);
    static ProjectedValueV6 makeText(std::string value, SignalSource source,
                                     SignalQuality quality);
    static ProjectedValueV6 unavailable(Kind kind = Kind::Number);
};

// Everything a page needs that is not in VehicleState itself: the health of
// each link, the counters the Developer screen shows and the trip summary.
struct PageEnvironmentV6 {
    // Vehicle UART. "connected with no recent frames" is a different screen
    // from "connected and receiving", so both are carried separately.
    bool uart_connected{false};
    bool uart_receiving{false};

    CommanderLinkStatus commander_status{CommanderLinkStatus::Disabled};
    bool commander_detail_known{false};
    std::string commander_detail;

    bool developer_mode{false};

    // Local time offset used to turn a navigation ETA (UTC seconds) into a
    // clock. The core has no timezone database on the device, so the offset is
    // supplied by the platform and a wrong offset shows a wrong ETA - it is
    // never guessed from the hardware clock.
    std::int32_t utc_offset_minutes{0};

    bool parser_stats_known{false};
    std::uint64_t parser_frames{0};
    std::uint64_t parser_checksum_errors{0};
    std::uint64_t parser_unknown_commands{0};

    bool frame_stats_known{false};
    float frame_ms{0.0F};
    float fps{0.0F};
    float frame_budget_ms{33.34F};

    bool memory_stats_known{false};
    std::uint32_t rss_kb{0};
    std::uint32_t resident_assets_kb{0};

    bool trip_known{false};
    float trip_distance_km{0.0F};
    std::uint64_t trip_duration_ms{0};
    float trip_average_kph{0.0F};
    float trip_max_kph{0.0F};

    WarningState warning;
};

// The values one page binds. Keys are the scene's `bind` and `signal` names,
// and they are exactly the names `pageBindingNamesV6()` declares for the page:
// the projection never offers a value the screen does not use, so a rename on
// either side is a test failure instead of a silently dead widget.
using PageProjectionV6 = std::map<std::string, ProjectedValueV6>;

// Names a page binds, sorted. This is the contract the scenes are checked
// against (see tests/page_projection_tests.cpp and tests/v6_pages_tests.py).
std::vector<std::string> pageBindingNamesV6(DashboardPageV6 page);

// Human-readable page name, matching the page set in docs/HORIZON_REDESIGN.md.
const char* pageNameV6(DashboardPageV6 page);

PageProjectionV6 buildPageProjectionV6(DashboardPageV6 page,
                                       const VehicleState& state,
                                       const ProductStateV6& product,
                                       const DashboardSettings& settings,
                                       const PageEnvironmentV6& environment);

// Applies a scene's `format` string to a projected value, or returns the
// node's `invalid_text` when the value is not available.
//
// The supported placeholders are the ones the nine screens actually use:
// `{}`, `{:.1f}`, `{:.0f}`. Keeping this engine beside the projection means
// "what the screen would show" is testable on the host, not only on the panel.
std::string formatSceneTextV6(const std::string& format,
                              const ProjectedValueV6& value,
                              const std::string& invalid_text);

}  // namespace dashboard
