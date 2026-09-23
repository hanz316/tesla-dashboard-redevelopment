// Prints the binding contract of the V6 page set as JSON.
//
// Structure only: page ids, names and the binding names each page offers.
// There is no vehicle data here and no fixture - the point of this tool is to
// let the scene files be checked against the runtime projection, so that a
// renamed binding is a test failure rather than a widget that silently draws
// nothing on the panel.
//
// Usage:
//   dashboard_page_dump            # JSON on stdout

#include "dashboard/page_projection_v6.h"

#include <iostream>

namespace {

void printPage(dashboard::DashboardPageV6 page, bool& first) {
    const auto names = dashboard::pageBindingNamesV6(page);
    if (!first) std::cout << ",\n";
    first = false;
    std::cout << "    \"" << dashboard::pageNameV6(page) << "\": {\n"
              << "      \"binding_count\": " << names.size() << ",\n"
              << "      \"bindings\": [";
    for (std::size_t i = 0; i < names.size(); ++i) {
        if (i != 0) std::cout << ", ";
        std::cout << "\"" << names[i] << "\"";
    }
    std::cout << "]\n    }";
}

}  // namespace

int main() {
    using dashboard::DashboardPageV6;
    const DashboardPageV6 pages[] = {
        DashboardPageV6::Horizon, DashboardPageV6::Mono,
        DashboardPageV6::Pulse,   DashboardPageV6::Route,
        DashboardPageV6::Studio,  DashboardPageV6::Energy,
        DashboardPageV6::Nocturne, DashboardPageV6::Settings,
        DashboardPageV6::Developer,
    };

    std::cout << "{\n  \"schema\": \"v6-page-bindings v1\",\n  \"pages\": {\n";
    bool first = true;
    for (DashboardPageV6 page : pages) printPage(page, first);
    std::cout << "\n  }\n}\n";
    return 0;
}
