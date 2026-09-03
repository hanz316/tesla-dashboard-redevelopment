#pragma once

#include "dashboard/signal.h"

#include <cstdint>
#include <string>
#include <vector>

namespace dashboard {

enum NavigationCapability : std::uint32_t {
    NavNone = 0,
    BasicManeuver = 1u << 0,
    TripMetrics = 1u << 1,
    RouteGeometry = 1u << 2,
    LaneGuidance = 1u << 3,
};

enum class ManeuverType : std::uint8_t {
    Unknown = 0,
    Continue,
    TurnLeft,
    TurnRight,
    SlightLeft,
    SlightRight,
    UTurn,
    ExitLeft,
    ExitRight,
    Roundabout,
    Arrive,
};

struct NavigationPoint {
    float x{0.0F};
    float y{0.0F};
};

struct LaneGuidanceItem {
    bool left{false};
    bool straight{false};
    bool right{false};
    bool recommended{false};
};

struct NavigationState {
    bool available{false};
    bool active{false};
    std::uint32_t capabilities{NavNone};
    Signal<ManeuverType> next_maneuver;
    Signal<float> next_turn_distance_m;
    Signal<std::uint32_t> remaining_time_s;
    Signal<float> remaining_distance_km;
    Signal<std::uint64_t> eta_epoch_s;
    Signal<std::uint8_t> arrival_soc;
    std::string road_name;
    std::string destination_name;
    std::vector<NavigationPoint> route_geometry;
    std::vector<LaneGuidanceItem> lane_guidance;
    std::uint64_t timestamp_ms{0};

    bool has(NavigationCapability capability) const {
        return (capabilities & static_cast<std::uint32_t>(capability)) != 0;
    }
};

enum class LyricsTimingMode : std::uint8_t { None = 0, Line, Word };

struct LyricsWord {
    std::string text;
    std::uint32_t start_ms{0};
    std::uint32_t end_ms{0};
};

struct LyricsLine {
    std::string text;
    std::uint32_t start_ms{0};
    std::uint32_t end_ms{0};
    std::vector<LyricsWord> words;
};

struct LyricsState {
    bool available{false};
    LyricsTimingMode timing_mode{LyricsTimingMode::None};
    std::vector<LyricsLine> lines;
    std::int32_t active_index{-1};
    std::uint64_t timestamp_ms{0};
};

struct MediaState {
    bool available{false};
    bool playing{false};
    bool loading{false};
    std::string track_id;
    std::string title;
    std::string artist;
    std::string album;
    std::string album_art_asset;
    std::uint32_t dominant_rgb{0x202020};
    std::uint32_t secondary_rgb{0x303030};
    Signal<std::uint32_t> position_ms;
    Signal<std::uint32_t> duration_ms;
    LyricsState lyrics;
    std::uint64_t timestamp_ms{0};
};

struct ProductStateV6 {
    NavigationState navigation;
    MediaState media;
};

}  // namespace dashboard
