#pragma once

#include "dashboard/ui_framework_v6.h"

#include <string>

namespace dashboard {

// The parse/serialise/clamp half of settings persistence.
//
// The file half belongs to the platform: the instrument is only ever allowed
// to write in its own tmpfs area, so the store is kept as pure functions that
// can be tested on the host and cannot quietly grow a write path into /res.
//
// The rules that matter:
// * a missing or unreadable store leaves the defaults;
// * a value outside its range is clamped, never accepted and never zeroed -
//   a brightness of 0 would be an unreadable instrument;
// * the Developer screen can never be the default page.
struct SettingsStoreV6 {
    static std::string serialize(const DashboardSettings& settings);

    // Returns false when the text is not a settings record at all. Individual
    // unknown keys and unparsable values inside a record are ignored rather
    // than failing the whole read, so a store written by a newer build still
    // loads the fields this build understands.
    static bool parse(const std::string& text, DashboardSettings& out);

    static void clamp(DashboardSettings& settings);

    // Brightness bounds. The floor is not zero: at zero the instrument is
    // unreadable and the driver has no way back without the phone.
    static constexpr std::uint8_t kMinBrightness{10};
    static constexpr std::uint8_t kMaxBrightness{100};
};

}  // namespace dashboard
