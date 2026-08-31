// Product-focused 1920x480 dashboard simulator.
// Read-only UI development surface: IDataSource -> VehicleState -> renderer.

#include "dashboard/data_source.h"
#include "dashboard/original_mcu_adapter.h"
#include "dashboard/source_adapters.h"
#include "replay_source.h"

#include <SDL.h>
#include <SDL_ttf.h>

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <string>

namespace {

constexpr int kWidth = 1920;
constexpr int kHeight = 480;
constexpr int kFrameMs = 33; // 30 fps target on the T113-class platform.
constexpr int kTopCut = 116;
constexpr int kBottomCut = 51;
const char* kFontPath = "/System/Library/Fonts/Supplemental/Arial.ttf";

enum class ThemeId { Dark, Graphite };

struct Theme {
    SDL_Color background;
    SDL_Color panel;
    SDL_Color panel_border;
    SDL_Color primary;
    SDL_Color secondary;
    SDL_Color accent;
    SDL_Color success;
    SDL_Color warning;
    SDL_Color danger;
};

Theme themeFor(ThemeId id) {
    if (id == ThemeId::Graphite) {
        return Theme{
            {18, 21, 25, 255}, {25, 29, 34, 255}, {46, 52, 60, 255},
            {246, 247, 249, 255}, {156, 164, 174, 255}, {114, 174, 255, 255},
            {73, 205, 142, 255}, {239, 174, 71, 255}, {230, 82, 88, 255}};
    }
    return Theme{
        {10, 14, 18, 255}, {15, 21, 27, 255}, {34, 43, 52, 255},
        {244, 246, 248, 255}, {137, 148, 160, 255}, {61, 155, 255, 255},
        {61, 214, 140, 255}, {245, 166, 35, 255}, {229, 72, 77, 255}};
}

struct Fonts {
    TTF_Font* speed{nullptr};
    TTF_Font* hero{nullptr};
    TTF_Font* medium{nullptr};
    TTF_Font* small{nullptr};
    TTF_Font* tiny{nullptr};
};

struct MotionState {
    float speed{0.0F};
    float soc{0.0F};
    bool initialized{false};
};

float approach(float current, float target, float factor) {
    return current + (target - current) * factor;
}

SDL_Texture* textTexture(SDL_Renderer* renderer, TTF_Font* font, const std::string& text, SDL_Color color) {
    SDL_Surface* surface = TTF_RenderUTF8_Blended(font, text.c_str(), color);
    if (surface == nullptr) return nullptr;
    SDL_Texture* texture = SDL_CreateTextureFromSurface(renderer, surface);
    SDL_FreeSurface(surface);
    return texture;
}

void drawCentered(SDL_Renderer* renderer, TTF_Font* font, const std::string& text,
                  SDL_Color color, int cx, int cy) {
    SDL_Texture* texture = textTexture(renderer, font, text, color);
    if (texture == nullptr) return;
    int w = 0, h = 0;
    SDL_QueryTexture(texture, nullptr, nullptr, &w, &h);
    SDL_Rect dst{cx - w / 2, cy - h / 2, w, h};
    SDL_RenderCopy(renderer, texture, nullptr, &dst);
    SDL_DestroyTexture(texture);
}

void drawLeft(SDL_Renderer* renderer, TTF_Font* font, const std::string& text,
              SDL_Color color, int x, int cy) {
    SDL_Texture* texture = textTexture(renderer, font, text, color);
    if (texture == nullptr) return;
    int w = 0, h = 0;
    SDL_QueryTexture(texture, nullptr, nullptr, &w, &h);
    SDL_Rect dst{x, cy - h / 2, w, h};
    SDL_RenderCopy(renderer, texture, nullptr, &dst);
    SDL_DestroyTexture(texture);
}

void drawRight(SDL_Renderer* renderer, TTF_Font* font, const std::string& text,
               SDL_Color color, int x, int cy) {
    SDL_Texture* texture = textTexture(renderer, font, text, color);
    if (texture == nullptr) return;
    int w = 0, h = 0;
    SDL_QueryTexture(texture, nullptr, nullptr, &w, &h);
    SDL_Rect dst{x - w, cy - h / 2, w, h};
    SDL_RenderCopy(renderer, texture, nullptr, &dst);
    SDL_DestroyTexture(texture);
}

void roundedRect(SDL_Renderer* renderer, int x, int y, int w, int h, int radius, SDL_Color color) {
    SDL_SetRenderDrawColor(renderer, color.r, color.g, color.b, color.a);
    SDL_Rect a{x + radius, y, w - radius * 2, h};
    SDL_Rect b{x, y + radius, w, h - radius * 2};
    SDL_RenderFillRect(renderer, &a);
    SDL_RenderFillRect(renderer, &b);
    for (int yy = 0; yy < radius; ++yy) {
        for (int xx = 0; xx < radius; ++xx) {
            const int dx = radius - xx;
            const int dy = radius - yy;
            if (dx * dx + dy * dy <= radius * radius) {
                SDL_RenderDrawPoint(renderer, x + xx, y + yy);
                SDL_RenderDrawPoint(renderer, x + w - 1 - xx, y + yy);
                SDL_RenderDrawPoint(renderer, x + xx, y + h - 1 - yy);
                SDL_RenderDrawPoint(renderer, x + w - 1 - xx, y + h - 1 - yy);
            }
        }
    }
}

void line(SDL_Renderer* renderer, int x1, int y1, int x2, int y2, SDL_Color color) {
    SDL_SetRenderDrawColor(renderer, color.r, color.g, color.b, color.a);
    SDL_RenderDrawLine(renderer, x1, y1, x2, y2);
}

void drawShapeMask(SDL_Renderer* renderer) {
    SDL_SetRenderDrawColor(renderer, 0, 0, 0, 255);
    for (int y = 0; y < kHeight; ++y) {
        const int left = kTopCut + (kBottomCut - kTopCut) * y / kHeight;
        const int right = kWidth - left;
        if (left > 0) SDL_RenderDrawLine(renderer, 0, y, left, y);
        if (right < kWidth) SDL_RenderDrawLine(renderer, right, y, kWidth, y);
    }
}

std::string clockText() {
    std::time_t now = std::time(nullptr);
    std::tm local{};
    localtime_r(&now, &local);
    char buf[16];
    std::strftime(buf, sizeof(buf), "%H:%M", &local);
    return buf;
}

std::string tireText(const dashboard::Signal<float>& signal) {
    if (!signal.valid) return "--";
    char buf[16];
    std::snprintf(buf, sizeof(buf), "%.1f", static_cast<double>(signal.value));
    return buf;
}

bool anyDoorOpen(const dashboard::VehicleState& s) {
    return (s.door_fl.valid && s.door_fl.value) ||
           (s.door_fr.valid && s.door_fr.value) ||
           (s.door_rl.valid && s.door_rl.value) ||
           (s.door_rr.valid && s.door_rr.value) ||
           (s.frunk.valid && s.frunk.value) ||
           (s.trunk.valid && s.trunk.value);
}

bool closuresKnown(const dashboard::VehicleState& s) {
    return s.door_fl.valid && s.door_fr.valid && s.door_rl.valid &&
           s.door_rr.valid && s.frunk.valid && s.trunk.valid;
}

std::string openDoorText(const dashboard::VehicleState& s) {
    std::string out;
    if (s.door_fl.valid && s.door_fl.value) out += "FL  ";
    if (s.door_fr.valid && s.door_fr.value) out += "FR  ";
    if (s.door_rl.valid && s.door_rl.value) out += "RL  ";
    if (s.door_rr.valid && s.door_rr.value) out += "RR  ";
    if (s.frunk.valid && s.frunk.value) out += "FRUNK  ";
    if (s.trunk.valid && s.trunk.value) out += "TRUNK  ";
    if (out.size() >= 2) out.resize(out.size() - 2);
    return out;
}

struct SocView {
    bool valid{false};
    int value{0};
    bool fallback_mcu{false};
};

SocView chooseSoc(const dashboard::VehicleState& s) {
    if (s.actual_soc.valid) return SocView{true, static_cast<int>(s.actual_soc.value), false};
    if (s.soc.valid) return SocView{true, static_cast<int>(s.soc.value), true};
    return SocView{};
}

const char* gearStatus(const dashboard::VehicleState& s) {
    if (!s.gear.valid) return "NO DATA";
    switch (s.gear.value) {
        case dashboard::Gear::Park: return "PARK";
        case dashboard::Gear::Reverse: return "REVERSE";
        case dashboard::Gear::Neutral: return "NEUTRAL";
        case dashboard::Gear::Drive: return "READY";
        default: return "NO DATA";
    }
}

SDL_Color gearColor(const dashboard::VehicleState& s, const Theme& t) {
    if (!s.gear.valid) return t.secondary;
    if (s.gear.value == dashboard::Gear::Drive) return t.success;
    if (s.gear.value == dashboard::Gear::Reverse) return t.danger;
    return t.primary;
}

void renderDashboard(SDL_Renderer* renderer, const Fonts& fonts, const Theme& t,
                     const dashboard::IDataSource& source, MotionState& motion,
                     const std::string& mode) {
    const dashboard::VehicleState& s = source.state();
    const SocView soc = chooseSoc(s);

    const float target_speed = s.speed.valid ? static_cast<float>(s.speed.value) : motion.speed;
    const float target_soc = soc.valid ? static_cast<float>(soc.value) : motion.soc;
    if (!motion.initialized) {
        motion.speed = target_speed;
        motion.soc = target_soc;
        motion.initialized = true;
    } else {
        motion.speed = approach(motion.speed, target_speed, 0.24F);
        motion.soc = approach(motion.soc, target_soc, 0.14F);
    }

    SDL_SetRenderDrawColor(renderer, t.background.r, t.background.g, t.background.b, 255);
    SDL_RenderClear(renderer);

    // restrained chrome: one hairline and three content zones, no glow/gradients.
    line(renderer, 150, 6, 1770, 6, t.panel_border);
    line(renderer, 650, 84, 650, 408, t.panel_border);
    line(renderer, 1270, 84, 1270, 408, t.panel_border);

    // LEFT: speed is the dominant driving datum.
    drawLeft(renderer, fonts.tiny, "SPEED", t.secondary, 185, 74);
    if (s.speed.valid) {
        char speed[16];
        std::snprintf(speed, sizeof(speed), "%d", static_cast<int>(std::lround(motion.speed)));
        drawCentered(renderer, fonts.speed, speed, t.primary, 400, 218);
    } else {
        drawCentered(renderer, fonts.speed, "--", t.secondary, 400, 218);
    }
    drawCentered(renderer, fonts.small, "km/h", t.secondary, 400, 350);

    // gear uses typography instead of a decorative pill.
    drawLeft(renderer, fonts.tiny, "GEAR", t.secondary, 185, 420);
    drawLeft(renderer, fonts.medium,
             s.gear.valid ? dashboard::gearName(s.gear.value) : "--",
             s.gear.valid ? t.accent : t.secondary, 270, 420);

    // CENTER: state first, then closure state; tires are secondary.
    drawCentered(renderer, fonts.small, gearStatus(s), gearColor(s, t), 960, 60);
    roundedRect(renderer, 735, 108, 450, 206, 18, t.panel);
    line(renderer, 760, 134, 1160, 134, t.panel_border);

    if (!closuresKnown(s)) {
        drawCentered(renderer, fonts.hero, "VEHICLE", t.primary, 960, 192);
        drawCentered(renderer, fonts.small, "Door status unavailable", t.secondary, 960, 260);
    } else if (anyDoorOpen(s)) {
        drawCentered(renderer, fonts.hero, "OPEN", t.warning, 960, 190);
        drawCentered(renderer, fonts.small, openDoorText(s), t.warning, 960, 258);
    } else {
        drawCentered(renderer, fonts.hero, "CLOSED", t.primary, 960, 190);
        drawCentered(renderer, fonts.small, "All closures secured", t.success, 960, 258);
    }

    drawCentered(renderer, fonts.tiny,
                 "FL " + tireText(s.tire_fl) + "   FR " + tireText(s.tire_fr) +
                 "   RL " + tireText(s.tire_rl) + "   RR " + tireText(s.tire_rr) + "  bar",
                 t.secondary, 960, 356);

    // RIGHT: actual SOC wins; MCU SOC is visibly marked fallback because it is known unreliable.
    drawLeft(renderer, fonts.tiny, "ENERGY", t.secondary, 1340, 74);
    if (soc.valid) {
        char value[16];
        std::snprintf(value, sizeof(value), "%d%%", static_cast<int>(std::lround(motion.soc)));
        drawCentered(renderer, fonts.hero, value, t.primary, 1518, 174);
    } else {
        drawCentered(renderer, fonts.hero, "--%", t.secondary, 1518, 174);
    }
    if (soc.fallback_mcu) {
        drawCentered(renderer, fonts.tiny, "MCU SOC · unverified", t.warning, 1518, 232);
    } else if (soc.valid) {
        drawCentered(renderer, fonts.tiny, "Actual SOC", t.secondary, 1518, 232);
    } else {
        drawCentered(renderer, fonts.tiny, "SOC unavailable", t.secondary, 1518, 232);
    }

    const int bx = 1360, by = 276, bw = 316, bh = 12;
    roundedRect(renderer, bx, by, bw, bh, 6, t.panel_border);
    if (soc.valid) {
        const int fill = std::max(4, std::min(bw, static_cast<int>(bw * motion.soc / 100.0F)));
        roundedRect(renderer, bx, by, fill, bh, 6, t.accent);
    }

    drawLeft(renderer, fonts.tiny, "RANGE", t.secondary, 1360, 340);
    drawRight(renderer, fonts.medium,
              s.range.valid ? std::to_string(s.range.value) + " km" : "-- km",
              s.range.valid ? t.primary : t.secondary, 1676, 340);

    const dashboard::Signal<std::int16_t>& temp = s.temperature_primary;
    drawLeft(renderer, fonts.tiny, "OUTSIDE", t.secondary, 1360, 402);
    drawRight(renderer, fonts.small,
              temp.valid ? std::to_string(temp.value) + "°C" : "--°C",
              temp.valid ? t.primary : t.secondary, 1676, 402);

    // Footer is intentionally low-contrast: source/mode is diagnostic context, not driving content.
    drawLeft(renderer, fonts.tiny, source.name(), t.secondary, 96, 462);
    drawCentered(renderer, fonts.tiny, mode, t.secondary, 960, 462);
    drawRight(renderer, fonts.small, clockText(), t.primary, 1824, 452);

    drawShapeMask(renderer);
}

bool saveScreenshot(SDL_Renderer* renderer, const char* path) {
    SDL_Surface* surface = SDL_CreateRGBSurfaceWithFormat(
        0, kWidth, kHeight, 32, SDL_PIXELFORMAT_RGBA32);
    if (surface == nullptr) return false;
    const bool ok = SDL_RenderReadPixels(renderer, nullptr, SDL_PIXELFORMAT_RGBA32,
                                         surface->pixels, surface->pitch) == 0 &&
                    SDL_SaveBMP(surface, path) == 0;
    SDL_FreeSurface(surface);
    return ok;
}

} // namespace

int main(int argc, char** argv) {
    bool screenshot = false;
    const char* screenshot_path = "/tmp/dashboard_simulator.bmp";
    const char* replay_path = "captures/uart-record-realcar-geardoor.bin";
    for (int i = 1; i < argc; ++i) {
        if (std::strcmp(argv[i], "--screenshot") == 0) {
            screenshot = true;
            if (i + 1 < argc && argv[i + 1][0] != '-') screenshot_path = argv[++i];
        } else {
            replay_path = argv[i];
        }
    }

    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_TIMER) != 0 || TTF_Init() != 0) return 1;
    SDL_Window* window = SDL_CreateWindow(
        "Tesla Dashboard Product Simulator", SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
        kWidth, kHeight, SDL_WINDOW_RESIZABLE);
    if (window == nullptr) return 1;
    SDL_Renderer* renderer = SDL_CreateRenderer(
        window, -1, screenshot ? SDL_RENDERER_SOFTWARE
                               : (SDL_RENDERER_ACCELERATED | SDL_RENDERER_PRESENTVSYNC));
    if (renderer == nullptr) return 1;
    SDL_RenderSetLogicalSize(renderer, kWidth, kHeight);

    Fonts fonts;
    fonts.speed = TTF_OpenFont(kFontPath, 188);
    fonts.hero = TTF_OpenFont(kFontPath, 74);
    fonts.medium = TTF_OpenFont(kFontPath, 44);
    fonts.small = TTF_OpenFont(kFontPath, 30);
    fonts.tiny = TTF_OpenFont(kFontPath, 22);
    if (!fonts.speed || !fonts.hero || !fonts.medium || !fonts.small || !fonts.tiny) return 1;

    dashboard::OriginalMcuAdapter replay_adapter;
    dashboard::sim::ReplaySource replay(replay_adapter, 0);
    const bool replay_available = replay.load(replay_path);
    dashboard::SimulationAdapter simulation;

    bool use_sim = !replay_available;
    bool frozen = false;
    bool running = true;
    ThemeId theme_id = ThemeId::Dark;
    std::uint16_t synth_speed = 36;
    dashboard::Gear synth_gear = dashboard::Gear::Drive;
    std::uint64_t next_synth = 0;
    std::uint64_t next_frame = 0;
    std::uint64_t rendered = 0;
    MotionState motion;

    while (running) {
        SDL_Event event;
        while (SDL_PollEvent(&event)) {
            if (event.type == SDL_QUIT) running = false;
            if (event.type == SDL_KEYDOWN) {
                switch (event.key.keysym.sym) {
                    case SDLK_ESCAPE: running = false; break;
                    case SDLK_t:
                        theme_id = theme_id == ThemeId::Dark ? ThemeId::Graphite : ThemeId::Dark;
                        break;
                    case SDLK_s: frozen = !frozen; break;
                    case SDLK_SPACE:
                        if (replay_available) { use_sim = !use_sim; replay.reset(); motion.initialized = false; }
                        break;
                    case SDLK_UP: synth_speed = static_cast<std::uint16_t>(std::min(240, synth_speed + 5)); break;
                    case SDLK_DOWN: synth_speed = static_cast<std::uint16_t>(std::max(0, synth_speed - 5)); break;
                    case SDLK_p: synth_gear = dashboard::Gear::Park; break;
                    case SDLK_d: synth_gear = dashboard::Gear::Drive; break;
                    case SDLK_r: synth_gear = dashboard::Gear::Reverse; break;
                    default: break;
                }
            }
        }

        const std::uint64_t now = static_cast<std::uint64_t>(SDL_GetTicks());
        if (!frozen) {
            if (use_sim) {
                if (now >= next_synth) {
                    simulation.setDriving(synth_speed, synth_gear, 63, 253, now);
                    simulation.setDoors(false, false, false, false, false, false, now);
                    simulation.setTires(2.9F, 2.9F, 2.8F, 2.8F, now);
                    next_synth = now + 100;
                }
            } else {
                replay.tick(now);
            }
        }

        dashboard::IDataSource& source = use_sim
            ? static_cast<dashboard::IDataSource&>(simulation)
            : static_cast<dashboard::IDataSource&>(replay_adapter);
        source.tick(now);

        if (now >= next_frame) {
            next_frame = now + kFrameMs;
            std::string mode = use_sim ? "SIMULATION" : "REPLAY";
            if (frozen) mode += " · FROZEN";
            renderDashboard(renderer, fonts, themeFor(theme_id), source, motion, mode);
            SDL_RenderPresent(renderer);
            ++rendered;
            if (screenshot && rendered >= 4) {
                saveScreenshot(renderer, screenshot_path);
                running = false;
            }
        } else {
            SDL_Delay(1);
        }
    }

    TTF_CloseFont(fonts.speed);
    TTF_CloseFont(fonts.hero);
    TTF_CloseFont(fonts.medium);
    TTF_CloseFont(fonts.small);
    TTF_CloseFont(fonts.tiny);
    SDL_DestroyRenderer(renderer);
    SDL_DestroyWindow(window);
    TTF_Quit();
    SDL_Quit();
    return 0;
}
