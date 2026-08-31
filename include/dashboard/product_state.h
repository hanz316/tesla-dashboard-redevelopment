#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace dashboard {

struct MediaState {
    bool available{false};
    bool playing{false};
    std::string track_id;
    std::string title;
    std::string artist;
    std::string album;
    std::string artwork_uri;
    std::uint64_t duration_ms{0};
    std::uint64_t position_ms{0};
    std::uint64_t updated_at_ms{0};
};

struct LyricsLine {
    std::uint64_t start_ms{0};
    std::string text;
};

struct LyricsState {
    bool available{false};
    bool matching{false};
    std::string track_id;
    std::vector<LyricsLine> lines;
    int current_index{-1};
    std::int32_t offset_ms{0};
    std::uint64_t updated_at_ms{0};
};

struct WeatherState {
    bool available{false};
    std::string location;
    float current_temperature_c{0.0F};
    float feels_like_c{0.0F};
    float high_c{0.0F};
    float low_c{0.0F};
    float precipitation_percent{0.0F};
    float wind_kph{0.0F};
    std::string condition;
    std::uint64_t updated_at_ms{0};
};

struct NavigationState {
    bool active{false};
    std::string next_turn;
    std::string road_name;
    float distance_to_turn_km{0.0F};
    std::uint32_t remaining_minutes{0};
    float remaining_distance_km{0.0F};
    std::string eta_text;
    int arrive_soc_percent{-1};
    int traffic_delay_minutes{0};
    std::uint64_t updated_at_ms{0};
};

struct CommanderState {
    bool available{false};
    bool connected{false};
    bool authenticated{false};
    std::string firmware_version;
    float packet_rate_hz{0.0F};
    std::uint64_t updated_at_ms{0};
};

struct PhoneState {
    bool available{false};
    int battery_percent{-1};
    bool charging{false};
    std::string network_label;
    std::uint64_t updated_at_ms{0};
};

struct ProductState {
    MediaState media;
    LyricsState lyrics;
    WeatherState weather;
    NavigationState navigation;
    CommanderState commander;
    PhoneState phone;
};

}  // namespace dashboard
