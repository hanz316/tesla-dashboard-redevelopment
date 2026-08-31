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
#include <cstdlib>
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

// Physical screen is trapezoidal (wider in the middle, tapering at the
// top and bottom corners). These are the corner cut amounts in logical
// 1920x480 pixels; tune with --shape tl,tr,bl,br.
struct ScreenShape {
    // Calibrated on hardware (finger trace + user confirmation):
    // symmetric trapezoid, wider at the bottom.
    // top edge: x 116..1804 (1688 wide), bottom edge: x 51..1869 (1818 wide)
    int top_l{116};
    int top_r{116};
    int bottom_l{51};
    int bottom_r{51};
};

ScreenShape g_shape;

void adbWriteShape(const ScreenShape& shape) {
    const char* adb = std::getenv("ADB_BIN");
    std::string adb_path =
        adb != nullptr && adb[0] != '\0'
            ? adb
            : "/Users/hanssmacbookair/Library/Android/sdk/platform-tools/adb";
    char cmd[512];
    std::snprintf(
        cmd, sizeof(cmd),
        "%s -s 10.0.0.216:5555 shell "
        "\"echo %d,%d,%d,%d > /tmp/screen_shape.txt\"",
        adb_path.c_str(),
        shape.top_l, shape.top_r, shape.bottom_l, shape.bottom_r);
    const int rc = std::system(cmd);
    if (rc != 0) {
        std::fprintf(stderr, "adb write failed (rc=%d): %s\n", rc, cmd);
    }
}

void drawCalibration(SDL_Renderer* renderer, ScreenShape& shape) {
    // White background
    SDL_SetRenderDrawColor(renderer, 235, 235, 235, 255);
    SDL_RenderClear(renderer);
    // Mask
    SDL_SetRenderDrawColor(renderer, 0, 0, 0, 255);
    const int h = kHeight;
    for (int y = 0; y < h; ++y) {
        const int xl = shape.top_l + (shape.bottom_l - shape.top_l) * y / h;
        if (xl > 0) {
            SDL_RenderDrawLine(renderer, 0, y, xl, y);
        }
        const int xr =
            kWidth - shape.top_r -
            (shape.bottom_r - shape.top_r) * y / h;
        if (xr < kWidth) {
            SDL_RenderDrawLine(renderer, kWidth, y, xr, y);
        }
    }
    // Handles
    const int hs = 18;
    const SDL_Point handles[4] = {
        {shape.top_l, 0},
        {kWidth - shape.top_r, 0},
        {shape.bottom_l, h},
        {kWidth - shape.bottom_r, h},
    };
    SDL_SetRenderDrawColor(renderer, 220, 40, 40, 255);
    for (const auto& pt : handles) {
        SDL_Rect r{pt.x - hs / 2, pt.y - hs / 2, hs, hs};
        SDL_RenderFillRect(renderer, &r);
    }
    SDL_SetRenderDrawColor(renderer, 255, 255, 255, 255);
    for (const auto& pt : handles) {
        SDL_Rect r{pt.x - hs / 2 + 3, pt.y - hs / 2 + 3, hs - 6, hs - 6};
        SDL_RenderFillRect(renderer, &r);
    }
}

int handleDrag(
    SDL_Renderer* renderer,
    ScreenShape& shape,
    int mx,
    int my,
    int& active_handle) {
    const int h = kHeight;
    const SDL_Point handles[4] = {
        {shape.top_l, 0},
        {kWidth - shape.top_r, 0},
        {shape.bottom_l, h},
        {kWidth - shape.bottom_r, h},
    };
    const int ids[4] = {0, 1, 2, 3};
    if (active_handle < 0) {
        for (int i = 0; i < 4; ++i) {
            const int dx = mx - handles[i].x;
            const int dy = my - handles[i].y;
            if (dx * dx + dy * dy <= 40 * 40) {
                active_handle = i;
                break;
            }
        }
    }
    if (active_handle >= 0) {
        switch (active_handle) {
            case 0:
                shape.top_l = std::max(0, std::min(500, mx));
                break;
            case 1:
                shape.top_r = std::max(0, std::min(500, kWidth - mx));
                break;
            case 2:
                shape.bottom_l = std::max(0, std::min(500, mx));
                break;
            case 3:
                shape.bottom_r = std::max(0, std::min(500, kWidth - mx));
                break;
            default:
                break;
        }
        adbWriteShape(shape);
        return 1;
    }
    return 0;
}

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

void drawCentered(
    SDL_Renderer* renderer,
    SDL_Texture* texture,
    int cx,
    int cy) {
    if (texture == nullptr) {
        return;
    }
    int w = 0;
    int h = 0;
    SDL_QueryTexture(texture, nullptr, nullptr, &w, &h);
    SDL_Rect dst{cx - w / 2, cy - h / 2, w, h};
    SDL_RenderCopy(renderer, texture, nullptr, &dst);
}

void fillRoundedRect(
    SDL_Renderer* renderer,
    int x,
    int y,
    int w,
    int h,
    int radius) {
    SDL_Rect body{x + radius, y, w - 2 * radius, h};
    SDL_RenderFillRect(renderer, &body);
    body = SDL_Rect{x, y + radius, w, h - 2 * radius};
    SDL_RenderFillRect(renderer, &body);
    for (int cy = 0; cy < radius; ++cy) {
        for (int cx = 0; cx < radius; ++cx) {
            const int dx = radius - 1 - cx;
            const int dy = radius - 1 - cy;
            if (dx * dx + dy * dy <= radius * radius) {
                SDL_RenderDrawPoint(renderer, x + cx, y + cy);
                SDL_RenderDrawPoint(renderer, x + w - 1 - cx, y + cy);
                SDL_RenderDrawPoint(renderer, x + cx, y + h - 1 - cy);
                SDL_RenderDrawPoint(renderer, x + w - 1 - cx, y + h - 1 - cy);
            }
        }
    }
}

// Premium dashboard layout (UI v1, dark Tesla-style).
void renderPremium(
    SDL_Renderer* renderer,
    TTF_Font* font_speed,
    TTF_Font* font_medium,
    TTF_Font* font_small,
    TTF_Font* font_tiny,
    const dashboard::VehicleState& state,
    bool uart_connected,
    bool has_rx,
    std::uint64_t rx_age_ms,
    const char* mode_label) {
    SDL_Color white{242, 244, 246, 255};
    SDL_Color dim{138, 148, 158, 255};
    SDL_Color blue{61, 155, 255, 255};
    SDL_Color green{61, 214, 140, 255};
    SDL_Color amber{245, 166, 35, 255};
    SDL_Color red{229, 72, 77, 255};

    // Background
    SDL_SetRenderDrawColor(renderer, 10, 14, 18, 255);
    SDL_RenderClear(renderer);

    // Subtle top accent line (inside the trapezoid top edge).
    SDL_SetRenderDrawColor(renderer, 26, 34, 42, 255);
    SDL_RenderDrawLine(renderer, 150, 4, 1770, 4);

    // ---- Speed (left, large) ----
    char text[64];
    std::snprintf(text, sizeof(text), "%s",
                  state.speed.valid
                      ? std::to_string(state.speed.value).c_str()
                      : "--");
    SDL_Texture* tex = renderText(
        renderer, font_speed, text, state.speed.valid ? white : dim);
    drawCentered(renderer, tex, 430, 170);
    destroyTexture(tex);
    tex = renderText(renderer, font_small, "km/h", dim);
    drawCentered(renderer, tex, 430, 330);
    destroyTexture(tex);

    // ---- Gear pill ----
    const char* gear_txt = "?";
    if (state.gear.valid) {
        gear_txt = dashboard::gearName(state.gear.value);
    }
    SDL_SetRenderDrawColor(renderer, 24, 32, 40, 255);
    fillRoundedRect(renderer, 130, 342, 140, 84, 16);
    SDL_SetRenderDrawColor(renderer, 38, 50, 62, 255);
    SDL_Rect border{130, 342, 140, 84};
    SDL_RenderDrawRect(renderer, &border);
    tex = renderText(renderer, font_medium, gear_txt, blue);
    drawCentered(renderer, tex, 200, 384);
    destroyTexture(tex);

    // ---- Center top: gear state / status ----
    const char* status = "NO DATA";
    SDL_Color status_color = dim;
    if (state.gear.valid) {
        switch (state.gear.value) {
            case dashboard::Gear::Park:
                status = "PARK";
                status_color = white;
                break;
            case dashboard::Gear::Reverse:
                status = "REVERSE";
                status_color = red;
                break;
            case dashboard::Gear::Neutral:
                status = "NEUTRAL";
                status_color = white;
                break;
            case dashboard::Gear::Drive:
                status = "DRIVE";
                status_color = green;
                break;
            default:
                break;
        }
    }
    tex = renderText(renderer, font_small, status, status_color);
    drawCentered(renderer, tex, 960, 52);
    destroyTexture(tex);

    // ---- Center: doors ----
    std::string doors_text = "DOORS --";
    SDL_Color doors_color = dim;
    const bool any_valid =
        state.door_fl.valid || state.door_fr.valid ||
        state.door_rl.valid || state.door_rr.valid ||
        state.frunk.valid || state.trunk.valid;
    if (any_valid) {
        std::string opened;
        bool open = false;
        if (state.door_fl.valid && state.door_fl.value) { open = true; opened += " FL"; }
        if (state.door_fr.valid && state.door_fr.value) { open = true; opened += " FR"; }
        if (state.door_rl.valid && state.door_rl.value) { open = true; opened += " RL"; }
        if (state.door_rr.valid && state.door_rr.value) { open = true; opened += " RR"; }
        if (state.frunk.valid && state.frunk.value) { open = true; opened += " FRUNK"; }
        if (state.trunk.valid && state.trunk.value) { open = true; opened += " TRUNK"; }
        doors_text = open ? ("OPEN" + opened) : "ALL CLOSED";
        doors_color = open ? amber : green;
    }
    tex = renderText(renderer, font_medium, doors_text.c_str(), doors_color);
    drawCentered(renderer, tex, 960, 150);
    destroyTexture(tex);

    // ---- Center bottom: tires ----
    auto tire = [&](const dashboard::Signal<float>& s) -> std::string {
        if (!s.valid) {
            return "--";
        }
        char buf[16];
        std::snprintf(buf, sizeof(buf), "%.1f", s.value);
        return buf;
    };
    std::snprintf(
        text, sizeof(text), "FL %s   FR %s   RL %s   RR %s  bar",
        tire(state.tire_fl).c_str(), tire(state.tire_fr).c_str(),
        tire(state.tire_rl).c_str(), tire(state.tire_rr).c_str());
    tex = renderText(renderer, font_tiny, text,
                     (state.tire_fl.valid || state.tire_fr.valid ||
                      state.tire_rl.valid || state.tire_rr.valid)
                         ? dim
                         : dim);
    drawCentered(renderer, tex, 960, 432);
    destroyTexture(tex);

    // ---- Right: SOC ----
    std::snprintf(text, sizeof(text), "%s",
                  state.soc.valid
                      ? (std::to_string(state.soc.value) + "%").c_str()
                      : "--%");
    tex = renderText(renderer, font_speed, text, state.soc.valid ? white : dim);
    drawCentered(renderer, tex, 1490, 170);
    destroyTexture(tex);

    // Battery bar
    const int bar_x = 1360;
    const int bar_y = 320;
    const int bar_w = 260;
    const int bar_h = 16;
    SDL_SetRenderDrawColor(renderer, 28, 36, 44, 255);
    fillRoundedRect(renderer, bar_x, bar_y, bar_w, bar_h, 8);
    if (state.soc.valid) {
        const int fill_w = std::max(
            4, bar_w * std::min(100, static_cast<int>(state.soc.value)) / 100);
        SDL_SetRenderDrawColor(renderer, 61, 155, 255, 255);
        fillRoundedRect(renderer, bar_x, bar_y, fill_w, bar_h, 8);
    }

    // Range
    std::snprintf(text, sizeof(text), "%s",
                  state.range.valid
                      ? (std::to_string(state.range.value) + " km").c_str()
                      : "-- km");
    tex = renderText(renderer, font_medium, text, state.range.valid ? white : dim);
    drawCentered(renderer, tex, 1490, 385);
    destroyTexture(tex);

    // ---- Top right: temperature ----
    if (state.temperature_primary.valid) {
        std::snprintf(text, sizeof(text), "%d°C",
                      static_cast<int>(state.temperature_primary.value));
        tex = renderText(renderer, font_small, text, dim);
        drawCentered(renderer, tex, 1700, 48);
        destroyTexture(tex);
    }

    // ---- Bottom right: clock ----
    const std::time_t now = std::time(nullptr);
    std::tm local{};
    localtime_r(&now, &local);
    std::strftime(text, sizeof(text), "%H:%M", &local);
    tex = renderText(renderer, font_medium, text, white);
    drawCentered(renderer, tex, 1730, 434);
    destroyTexture(tex);

    // ---- Bottom left: UART health ----
    const char* health = "UART LOST";
    SDL_Color health_color = red;
    if (uart_connected) {
        if (!has_rx) {
            health = "UART WAIT";
            health_color = amber;
        } else if (rx_age_ms <= kStaleFeedWindowMs) {
            health = "UART OK";
            health_color = green;
        } else {
            health = "UART STALE";
            health_color = amber;
        }
    }
    tex = renderText(renderer, font_tiny, health, health_color);
    drawCentered(renderer, tex, 210, 438);
    destroyTexture(tex);

    // Mode label (debug)
    tex = renderText(renderer, font_tiny, mode_label, dim);
    drawCentered(renderer, tex, 960, 470);
    destroyTexture(tex);
}

// Draws the trapezoid bezel mask: everything outside the visible screen
// shape is filled with black so UI elements stay inside the safe area.
void drawShapeMask(SDL_Renderer* renderer) {
    SDL_SetRenderDrawColor(renderer, 0, 0, 0, 255);
    const int h = kHeight;
    // top-left triangle
    for (int y = 0; y < h; ++y) {
        const int x_limit =
            g_shape.top_l +
            (g_shape.bottom_l - g_shape.top_l) * y / h;
        if (x_limit > 0) {
            SDL_RenderDrawLine(renderer, 0, y, x_limit, y);
        }
    }
    // top-right triangle
    for (int y = 0; y < h; ++y) {
        const int x_limit =
            kWidth - g_shape.top_r -
            (g_shape.bottom_r - g_shape.top_r) * y / h;
        if (x_limit < kWidth) {
            SDL_RenderDrawLine(renderer, kWidth, y, x_limit, y);
        }
    }
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
    bool calibrate_mode = false;
    const char* screenshot_path = "/tmp/dashboard_simulator.png";
    const char* replay_path = "captures/uart-record-realcar-geardoor.bin";
    ScreenShape shape;
    g_shape = shape;
    for (int i = 1; i < argc; ++i) {
        if (std::strcmp(argv[i], "--screenshot") == 0) {
            screenshot_mode = true;
            if (i + 1 < argc && argv[i + 1][0] != '-') {
                screenshot_path = argv[++i];
            }
        } else if (std::strcmp(argv[i], "--dump-state") == 0) {
            dump_state = true;
        } else if (std::strcmp(argv[i], "--calibrate") == 0) {
            calibrate_mode = true;
        } else if (std::strcmp(argv[i], "--shape") == 0 &&
                   i + 4 < argc) {
            g_shape.top_l = std::atoi(argv[++i]);
            g_shape.top_r = std::atoi(argv[++i]);
            g_shape.bottom_l = std::atoi(argv[++i]);
            g_shape.bottom_r = std::atoi(argv[++i]);
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
        kWidth,
        kHeight,
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

    SDL_Texture* offscreen = nullptr;
    if (screenshot_mode) {
        offscreen = SDL_CreateTexture(
            renderer, SDL_PIXELFORMAT_RGBA32, SDL_TEXTUREACCESS_TARGET,
            kWidth, kHeight);
        if (offscreen == nullptr) {
            std::fprintf(stderr, "SDL_CreateTexture(target): %s\n",
                         SDL_GetError());
            return 1;
        }
        SDL_SetRenderTarget(renderer, offscreen);
    }

    std::fprintf(stderr, "[sim] open fonts\n");
    TTF_Font* font_big =
        TTF_OpenFontIndex(kFontPath, 180, 0);
    TTF_Font* font_speed =
        TTF_OpenFontIndex(kFontPath, 170, 0);
    TTF_Font* font_label = TTF_OpenFontIndex(kFontPath, 42, 0);
    TTF_Font* font_medium = TTF_OpenFontIndex(kFontPath, 44, 0);
    TTF_Font* font_small = TTF_OpenFontIndex(kFontPath, 30, 0);
    TTF_Font* font_tiny = TTF_OpenFontIndex(kFontPath, 24, 0);
    if (font_big == nullptr || font_label == nullptr || font_small == nullptr ||
        font_speed == nullptr || font_medium == nullptr || font_tiny == nullptr) {
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
    int active_handle = -1;
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
            } else if (calibrate_mode && event.type == SDL_MOUSEBUTTONDOWN &&
                       event.button.button == SDL_BUTTON_LEFT) {
                handleDrag(
                    renderer, g_shape, event.button.x, event.button.y,
                    active_handle);
            } else if (calibrate_mode && event.type == SDL_MOUSEMOTION &&
                       (event.motion.state & SDL_BUTTON_LMASK)) {
                handleDrag(
                    renderer, g_shape, event.motion.x, event.motion.y,
                    active_handle);
            } else if (calibrate_mode && event.type == SDL_MOUSEBUTTONUP) {
                active_handle = -1;
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

        if (calibrate_mode) {
            drawCalibration(renderer, g_shape);
            char label[128];
            std::snprintf(
                label, sizeof(label),
                "trapezoid: TL=%d TR=%d BL=%d BR=%d  (drag handles; "
                "writes to device /tmp/screen_shape.txt)",
                g_shape.top_l, g_shape.top_r,
                g_shape.bottom_l, g_shape.bottom_r);
            TTF_Font* font_small =
                TTF_OpenFontIndex(kFontPath, 30, 0);
            if (font_small != nullptr) {
                SDL_Texture* tex = renderText(
                    renderer, font_small, label, SDL_Color{30, 30, 30, 255});
                drawTexture(renderer, tex, 30, 6);
                destroyTexture(tex);
                TTF_CloseFont(font_small);
            }
            SDL_RenderPresent(renderer);
            if (screenshot_mode) {
                SDL_Surface* surface = SDL_CreateRGBSurfaceWithFormat(
                    0, kWidth, kHeight, 32, SDL_PIXELFORMAT_RGBA32);
                if (surface != nullptr) {
                    SDL_RenderReadPixels(
                        renderer, nullptr, SDL_PIXELFORMAT_RGBA32,
                        surface->pixels, surface->pitch);
                    SDL_SaveBMP(surface, screenshot_path);
                    SDL_FreeSurface(surface);
                }
                running = false;
            }
            SDL_Delay(16);
            continue;
        }

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

            char mode_label[64];
            std::snprintf(
                mode_label, sizeof(mode_label), "%s / %s",
                synthetic ? "SYNTH" : "REPLAY",
                feed_frozen ? "FROZEN" : "LIVE");
            renderPremium(
                renderer, font_speed, font_medium, font_small, font_tiny,
                state, connected, last_feed_ms != 0, rx_age, mode_label);

            drawShapeMask(renderer);
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
                SDL_Surface* surface = SDL_CreateRGBSurfaceWithFormat(
                    0, kWidth, kHeight, 32, SDL_PIXELFORMAT_RGBA32);
                if (surface != nullptr) {
                    SDL_RenderReadPixels(
                        renderer, nullptr, SDL_PIXELFORMAT_RGBA32,
                        surface->pixels, surface->pitch);
                    SDL_SaveBMP(surface, screenshot_path);
                    SDL_FreeSurface(surface);
                    std::fprintf(stderr,
                                 "[sim] screenshot saved: %s (%dx%d)\n",
                                 screenshot_path, kWidth, kHeight);
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
    if (offscreen != nullptr) {
        SDL_SetRenderTarget(renderer, nullptr);
        SDL_DestroyTexture(offscreen);
    }
    TTF_CloseFont(font_big);
    TTF_CloseFont(font_label);
    TTF_CloseFont(font_small);
    SDL_DestroyRenderer(renderer);
    SDL_DestroyWindow(window);
    TTF_Quit();
    SDL_Quit();
    return 0;
}
