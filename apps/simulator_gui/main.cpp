// Tesla dashboard host simulator (1920x480, same core as the T113 build).
//
// Shares dashboard_core with the device build. Data comes either from a
// recorded real UART session (replay) or from synthetic frames.
//
// Keys:
//   Space  toggle replay / synthetic
//   S      freeze data feed (simulate stale -> values show "--")
//   Up/Dn  adjust synthetic speed
//   Esc    quit

#include "dashboard/original_mcu_adapter.h"
#include "dashboard/signal.h"
#include "replay_source.h"

#include <SDL.h>
#include <SDL_image.h>
#include <SDL_ttf.h>

#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <string>
#include <vector>

namespace {

constexpr int kWidth = 1920;
constexpr int kHeight = 480;
constexpr int kUiMs = 100;
constexpr std::uint64_t kStaleFeedWindowMs = 2500;

const char* kFontPath = "/System/Library/Fonts/Supplemental/Arial.ttf";

struct GearTextures {
    SDL_Texture* park{nullptr};
    SDL_Texture* reverse{nullptr};
    SDL_Texture* neutral{nullptr};
    SDL_Texture* drive{nullptr};
};

void destroyTexture(SDL_Texture*& texture) {
    if (texture != nullptr) {
        SDL_DestroyTexture(texture);
        texture = nullptr;
    }
}

SDL_Texture* loadScaledTexture(
    SDL_Renderer* renderer,
    const std::string& path,
    int target_w,
    int target_h) {
    SDL_Surface* surface = IMG_Load(path.c_str());
    if (surface == nullptr) {
        std::fprintf(stderr, "IMG_Load(%s): %s\n", path.c_str(), IMG_GetError());
        return nullptr;
    }
    SDL_Surface* scaled = SDL_CreateRGBSurfaceWithFormat(
        0, target_w, target_h, 32, SDL_PIXELFORMAT_RGBA32);
    if (scaled != nullptr) {
        SDL_BlitScaled(surface, nullptr, scaled, nullptr);
    }
    SDL_FreeSurface(surface);
    SDL_Texture* texture = SDL_CreateTextureFromSurface(renderer, scaled);
    SDL_FreeSurface(scaled);
    return texture;
}

SDL_Texture* renderText(
    SDL_Renderer* renderer,
    TTF_Font* font,
    const char* text,
    SDL_Color color) {
    SDL_Surface* surface = TTF_RenderUTF8_Blended(font, text, color);
    if (surface == nullptr) {
        std::fprintf(stderr, "TTF_RenderUTF8_Blended: %s\n", TTF_GetError());
        return nullptr;
    }
    SDL_Texture* texture = SDL_CreateTextureFromSurface(renderer, surface);
    SDL_FreeSurface(surface);
    return texture;
}

void drawTexture(
    SDL_Renderer* renderer,
    SDL_Texture* texture,
    int x,
    int y,
    int align_x = 0) {
    if (texture == nullptr) {
        return;
    }
    int w = 0;
    int h = 0;
    SDL_QueryTexture(texture, nullptr, nullptr, &w, &h);
    SDL_Rect dst{x - (align_x == 1 ? w : 0), y, w, h};
    SDL_RenderCopy(renderer, texture, nullptr, &dst);
}

const char* gearImageName(dashboard::Gear gear) {
    switch (gear) {
        case dashboard::Gear::Park:
            return "white_gears_p.png";
        case dashboard::Gear::Reverse:
            return "white_gears_r.png";
        case dashboard::Gear::Neutral:
            return "white_gears_n.png";
        case dashboard::Gear::Drive:
            return "white_gears_d.png";
        default:
            return nullptr;
    }
}

const char* uartLabel(
    bool connected,
    bool has_rx,
    std::uint64_t rx_age_ms) {
    if (!connected) {
        return "UART LOST";
    }
    if (!has_rx) {
        return "UART WAIT";
    }
    return rx_age_ms <= kStaleFeedWindowMs ? "UART OK" : "UART STALE";
}

std::string formatClock() {
    const std::time_t now = std::time(nullptr);
    std::tm local{};
    localtime_r(&now, &local);
    char buf[16];
    std::strftime(buf, sizeof(buf), "%H:%M", &local);
    return buf;
}

std::vector<std::uint8_t> makeFrame(
    std::uint8_t command,
    const std::vector<std::uint8_t>& payload) {
    std::vector<std::uint8_t> frame;
    frame.reserve(payload.size() + 4);
    frame.push_back(dashboard::ProtocolParser::kHeader);
    frame.push_back(command);
    frame.push_back(static_cast<std::uint8_t>(payload.size()));
    frame.insert(frame.end(), payload.begin(), payload.end());
    frame.push_back(dashboard::ProtocolParser::checksum(
        command,
        payload.empty() ? nullptr : payload.data(),
        payload.size()));
    return frame;
}

}  // namespace

int main(int argc, char** argv) {
    bool screenshot_mode = false;
    bool dump_state = false;
    const char* screenshot_path = "/tmp/dashboard_simulator.png";
    const char* replay_path = "captures/uart-record-realcar-geardoor.bin";
    for (int i = 1; i < argc; ++i) {
        if (std::strcmp(argv[i], "--screenshot") == 0) {
            screenshot_mode = true;
            if (i + 1 < argc && argv[i + 1][0] != '-') {
                screenshot_path = argv[++i];
            }
        } else if (std::strcmp(argv[i], "--dump-state") == 0) {
            dump_state = true;
        } else {
            replay_path = argv[i];
        }
    }

    std::fprintf(stderr, "[sim] init SDL\n");
    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_TIMER) != 0) {
        std::fprintf(stderr, "SDL_Init: %s\n", SDL_GetError());
        return 1;
    }
    std::fprintf(stderr, "[sim] init TTF\n");
    if (TTF_Init() != 0) {
        std::fprintf(stderr, "TTF_Init: %s\n", TTF_GetError());
        return 1;
    }

    std::fprintf(stderr, "[sim] create window\n");
    SDL_Window* window = SDL_CreateWindow(
        "Tesla Dashboard Simulator (1920x480)",
        SDL_WINDOWPOS_CENTERED,
        SDL_WINDOWPOS_CENTERED,
        1152,
        288,
        SDL_WINDOW_RESIZABLE);
    if (window == nullptr) {
        std::fprintf(stderr, "SDL_CreateWindow: %s\n", SDL_GetError());
        return 1;
    }
    std::fprintf(stderr, "[sim] create renderer\n");
    SDL_Renderer* renderer = SDL_CreateRenderer(
        window, -1,
        screenshot_mode ? SDL_RENDERER_SOFTWARE
                        : (SDL_RENDERER_ACCELERATED | SDL_RENDERER_PRESENTVSYNC));
    if (renderer == nullptr) {
        std::fprintf(stderr, "SDL_CreateRenderer: %s\n", SDL_GetError());
        return 1;
    }
    SDL_RenderSetLogicalSize(renderer, kWidth, kHeight);
    SDL_ShowWindow(window);

    std::fprintf(stderr, "[sim] open fonts\n");
    TTF_Font* font_big =
        TTF_OpenFontIndex(kFontPath, 180, 0);
    TTF_Font* font_label = TTF_OpenFontIndex(kFontPath, 42, 0);
    TTF_Font* font_small = TTF_OpenFontIndex(kFontPath, 30, 0);
    if (font_big == nullptr || font_label == nullptr || font_small == nullptr) {
        std::fprintf(stderr, "TTF_OpenFont: %s\n", TTF_GetError());
        return 1;
    }
    std::fprintf(stderr, "[sim] fonts loaded: big=%d label=%d small=%d\n",
                 TTF_FontHeight(font_big),
                 TTF_FontHeight(font_label),
                 TTF_FontHeight(font_small));

    std::fprintf(stderr, "[sim] load gear textures\n");
    const std::string ui_dir = "captures/backup-10.80.6.196:5555-20260831T062456Z/res/ui/home/";
    GearTextures gears;
    gears.park = loadScaledTexture(renderer, ui_dir + "white_gears_p.png", 220, 120);
    gears.reverse = loadScaledTexture(renderer, ui_dir + "white_gears_r.png", 220, 120);
    gears.neutral = loadScaledTexture(renderer, ui_dir + "white_gears_n.png", 220, 120);
    gears.drive = loadScaledTexture(renderer, ui_dir + "white_gears_d.png", 220, 120);

    std::fprintf(stderr, "[sim] load replay\n");
    dashboard::OriginalMcuAdapter adapter;
    dashboard::sim::ReplaySource replay(adapter, 0);
    const bool has_replay = replay.load(replay_path);
    if (has_replay) {
        std::printf("replay loaded: %zu frames\n", replay.frameCount());
    } else {
        std::printf("no replay (%s); using synthetic data\n", replay_path);
    }

    SDL_Color white{240, 240, 240, 255};
    SDL_Color dim{150, 150, 150, 255};
    SDL_Color red{230, 80, 80, 255};

    bool running = true;
    bool synthetic = !has_replay;
    bool feed_frozen = false;
    std::uint64_t next_ui_ms = 0;
    std::uint64_t next_synth_ms = 0;
    std::uint64_t last_feed_ms = 0;
    std::uint16_t synth_speed = 0;
    std::uint8_t synth_soc = 63;
    std::uint16_t synth_range = 253;
    dashboard::Gear synth_gear = dashboard::Gear::Park;

    std::uint64_t render_count = 0;
    std::uint64_t dump_done = 0;
    while (running) {
        static bool entered = false;
        if (!entered) {
            entered = true;
            std::fprintf(stderr, "[sim] event loop started\n");
        }
        SDL_Event event;
        while (SDL_PollEvent(&event)) {
            if (event.type == SDL_QUIT) {
                running = false;
            } else if (event.type == SDL_KEYDOWN) {
                switch (event.key.keysym.sym) {
                    case SDLK_ESCAPE:
                        running = false;
                        break;
                    case SDLK_SPACE:
                        if (has_replay) {
                            synthetic = !synthetic;
                            replay.reset();
                        }
                        break;
                    case SDLK_s:
                        feed_frozen = !feed_frozen;
                        break;
                    case SDLK_UP:
                        synth_speed = static_cast<std::uint16_t>(
                            std::min(240, synth_speed + 5));
                        break;
                    case SDLK_DOWN:
                        synth_speed = static_cast<std::uint16_t>(
                            std::max(0, synth_speed - 5));
                        break;
                    default:
                        break;
                }
            }
        }

        const std::uint64_t now_ms =
            static_cast<std::uint64_t>(SDL_GetTicks());

        // Feed data (replay or synthetic), unless user froze the feed.
        if (!feed_frozen) {
            if (synthetic) {
                if (now_ms >= next_synth_ms) {
                    const auto cmd04 = makeFrame(
                        0x04,
                        {static_cast<std::uint8_t>(synth_speed & 0xff),
                         static_cast<std::uint8_t>(synth_speed >> 8),
                         0, 0, 0, 0,
                         static_cast<std::uint8_t>(synth_range & 0xff),
                         static_cast<std::uint8_t>(synth_range >> 8),
                         synth_soc, 0, 0x10, 0x30, 0x03,
                         static_cast<std::uint8_t>((now_ms / 40) & 0xff),
                         static_cast<std::uint8_t>((now_ms / 40) >> 8),
                         0, 0});
                    adapter.feed(cmd04.data(), cmd04.size(), now_ms);
                    const auto cmd01 = makeFrame(
                        0x01, {0, 0, 0, 0, static_cast<std::uint8_t>(
                                   static_cast<unsigned>(synth_gear) << 4),
                               0x3c, 0, 0, 5});
                    adapter.feed(cmd01.data(), cmd01.size(), now_ms);
                    next_synth_ms = now_ms + 100;
                }
            } else {
                replay.tick(now_ms);
            }
            last_feed_ms = now_ms;
        }

        // Update UI state every 100ms.
        if (now_ms >= next_ui_ms) {
            next_ui_ms = now_ms + kUiMs;
            const auto& state = adapter.state();
            const auto& parser = adapter.parserStats();
            const bool connected = true;
            const std::uint64_t rx_age =
                !feed_frozen && last_feed_ms != 0 && now_ms >= last_feed_ms
                    ? now_ms - last_feed_ms
                    : now_ms - last_feed_ms;

            SDL_SetRenderDrawColor(renderer, 10, 10, 12, 255);
            SDL_RenderClear(renderer);

            // Speed
            char speed_text[16];
            std::snprintf(speed_text, sizeof(speed_text), "%s",
                          state.speed.valid
                              ? std::to_string(state.speed.value).c_str()
                              : "--");
            SDL_Texture* speed_tex = renderText(
                renderer, font_big, speed_text,
                state.speed.valid ? white : dim);
            drawTexture(renderer, speed_tex, 260, 80, 1);
            destroyTexture(speed_tex);

            // Gear image below speed
            SDL_Texture* gear_tex = nullptr;
            if (state.gear.valid) {
                switch (state.gear.value) {
                    case dashboard::Gear::Park: gear_tex = gears.park; break;
                    case dashboard::Gear::Reverse: gear_tex = gears.reverse; break;
                    case dashboard::Gear::Neutral: gear_tex = gears.neutral; break;
                    case dashboard::Gear::Drive: gear_tex = gears.drive; break;
                    default: break;
                }
            }
            if (gear_tex != nullptr) {
                drawTexture(renderer, gear_tex, 120, 280);
            } else {
                SDL_Texture* no_gear = renderText(
                    renderer, font_label, "NO GEAR", dim);
                drawTexture(renderer, no_gear, 120, 300);
                destroyTexture(no_gear);
            }

            // SOC
            char soc_text[16];
            std::snprintf(soc_text, sizeof(soc_text), "%s",
                          state.soc.valid
                              ? (std::to_string(state.soc.value) + "%").c_str()
                              : "--%");
            SDL_Texture* soc_tex = renderText(
                renderer, font_big, soc_text,
                state.soc.valid ? white : dim);
            drawTexture(renderer, soc_tex, 1580, 80);
            destroyTexture(soc_tex);

            // Range
            char range_text[32];
            std::snprintf(range_text, sizeof(range_text), "%s",
                          state.range.valid
                              ? (std::to_string(state.range.value) + " km").c_str()
                              : "-- km");
            SDL_Texture* range_tex = renderText(
                renderer, font_label, range_text,
                state.range.valid ? white : dim);
            drawTexture(renderer, range_tex, 1580, 250);
            destroyTexture(range_tex);

            // Doors
            std::string doors_text = "DOORS --";
            const bool any_valid =
                state.door_fl.valid || state.door_fr.valid ||
                state.door_rl.valid || state.door_rr.valid ||
                state.frunk.valid || state.trunk.valid;
            if (any_valid) {
                bool open = false;
                std::string opened;
                if (state.door_fl.valid && state.door_fl.value) { open = true; opened += " FL"; }
                if (state.door_fr.valid && state.door_fr.value) { open = true; opened += " FR"; }
                if (state.door_rl.valid && state.door_rl.value) { open = true; opened += " RL"; }
                if (state.door_rr.valid && state.door_rr.value) { open = true; opened += " RR"; }
                if (state.frunk.valid && state.frunk.value) { open = true; opened += " FRUNK"; }
                if (state.trunk.valid && state.trunk.value) { open = true; opened += " TRUNK"; }
                doors_text = open ? ("OPEN" + opened) : "ALL CLOSED";
            }
            doors_text += "  " +
                std::string(uartLabel(connected, last_feed_ms != 0, rx_age));
            SDL_Texture* doors_tex = renderText(
                renderer, font_small, doors_text.c_str(), white);
            drawTexture(renderer, doors_tex, 60, 420);
            destroyTexture(doors_tex);

            // Tires
            char tires_text[96];
            std::snprintf(
                tires_text, sizeof(tires_text),
                "FL %s  FR %s  RL %s  RR %s",
                state.tire_fl.valid ? "2.60" : "--",
                state.tire_fr.valid ? "2.60" : "--",
                state.tire_rl.valid ? "2.60" : "--",
                state.tire_rr.valid ? "2.60" : "--");
            SDL_Texture* tires_tex = renderText(
                renderer, font_small, tires_text, dim);
            drawTexture(renderer, tires_tex, 700, 420);
            destroyTexture(tires_tex);

            // Clock
            SDL_Texture* clock_tex = renderText(
                renderer, font_label, formatClock().c_str(), white);
            drawTexture(renderer, clock_tex, 1760, 410);
            destroyTexture(clock_tex);

            // Health footer
            char health_text[96];
            std::snprintf(
                health_text, sizeof(health_text),
                "mode: %s  feed: %s  pkts: %llu  crc: %llu  unknown: %llu",
                synthetic ? "SYNTH" : "REPLAY",
                feed_frozen ? "FROZEN" : "LIVE",
                static_cast<unsigned long long>(parser.valid_packets),
                static_cast<unsigned long long>(parser.checksum_errors),
                static_cast<unsigned long long>(adapter.adapterStats().unknown_commands));
            SDL_Texture* health_tex = renderText(
                renderer, font_small, health_text, red);
            drawTexture(renderer, health_tex, 60, 445);
            destroyTexture(health_tex);

            SDL_RenderPresent(renderer);
            ++render_count;
            if (dump_state && dump_done == 0 &&
                render_count >= 12) {
                const auto& st = adapter.state();
                const auto& ps = adapter.parserStats();
                const auto& as = adapter.adapterStats();
                std::fprintf(
                    stderr,
                    "[sim-state] speed=%u gear=%d soc=%u range=%u "
                    "doors=%d%d%d%d%d%d tires=%.2f/%.2f/%.2f/%.2f "
                    "pkts=%llu crc=%llu unknown=%llu\n",
                    st.speed.valid ? static_cast<unsigned>(st.speed.value) : 0U,
                    st.gear.valid ? static_cast<int>(st.gear.value) : -1,
                    st.soc.valid ? static_cast<unsigned>(st.soc.value) : 0U,
                    st.range.valid ? static_cast<unsigned>(st.range.value) : 0U,
                    st.door_fl.valid && st.door_fl.value ? 1 : 0,
                    st.door_fr.valid && st.door_fr.value ? 1 : 0,
                    st.door_rl.valid && st.door_rl.value ? 1 : 0,
                    st.door_rr.valid && st.door_rr.value ? 1 : 0,
                    st.frunk.valid && st.frunk.value ? 1 : 0,
                    st.trunk.valid && st.trunk.value ? 1 : 0,
                    st.tire_fl.valid ? static_cast<double>(st.tire_fl.value) : 0.0,
                    st.tire_fr.valid ? static_cast<double>(st.tire_fr.value) : 0.0,
                    st.tire_rl.valid ? static_cast<double>(st.tire_rl.value) : 0.0,
                    st.tire_rr.valid ? static_cast<double>(st.tire_rr.value) : 0.0,
                    static_cast<unsigned long long>(ps.valid_packets),
                    static_cast<unsigned long long>(ps.checksum_errors),
                    static_cast<unsigned long long>(as.unknown_commands));
                dump_done = 1;
                running = false;
            }
            if (screenshot_mode && render_count >= 3) {
                int out_w = 0;
                int out_h = 0;
                SDL_GetRendererOutputSize(renderer, &out_w, &out_h);
                if (out_w <= 0 || out_h <= 0) {
                    out_w = kWidth;
                    out_h = kHeight;
                }
                SDL_Surface* surface = SDL_CreateRGBSurfaceWithFormat(
                    0, out_w, out_h, 32, SDL_PIXELFORMAT_RGBA32);
                if (surface != nullptr) {
                    SDL_RenderReadPixels(
                        renderer, nullptr, SDL_PIXELFORMAT_RGBA32,
                        surface->pixels, surface->pitch);
                    SDL_SaveBMP(surface, screenshot_path);
                    SDL_FreeSurface(surface);
                    std::fprintf(stderr,
                                 "[sim] screenshot saved: %s (%dx%d)\n",
                                 screenshot_path, out_w, out_h);
                }
                running = false;
            }
        } else {
            SDL_Delay(1);
        }
    }

    destroyTexture(gears.park);
    destroyTexture(gears.reverse);
    destroyTexture(gears.neutral);
    destroyTexture(gears.drive);
    TTF_CloseFont(font_big);
    TTF_CloseFont(font_label);
    TTF_CloseFont(font_small);
    SDL_DestroyRenderer(renderer);
    SDL_DestroyWindow(window);
    TTF_Quit();
    SDL_Quit();
    return 0;
}
