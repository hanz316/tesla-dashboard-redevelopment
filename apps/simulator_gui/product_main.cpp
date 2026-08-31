// Product-focused 1920x480 dashboard simulator.
// Phase 1: Horizon + Mono + shared Safety Layer + product managers.

#include "dashboard/dashboard_product.h"
#include "dashboard/original_mcu_adapter.h"
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
#include <vector>

namespace {

constexpr int kWidth = 1920;
constexpr int kHeight = 480;
constexpr int kFrameMs = 33;
constexpr int kTopCut = 116;
constexpr int kBottomCut = 51;
constexpr std::uint64_t kVehicleLinkStaleMs = 2500;
const char* kFontPath = "/System/Library/Fonts/Supplemental/Arial.ttf";

struct Fonts {
    TTF_Font* speed{nullptr};
    TTF_Font* hero{nullptr};
    TTF_Font* medium{nullptr};
    TTF_Font* small{nullptr};
    TTF_Font* tiny{nullptr};
};

SDL_Color color(std::uint32_t rgb, std::uint8_t alpha = 255) {
    return SDL_Color{
        static_cast<std::uint8_t>((rgb >> 16U) & 0xffU),
        static_cast<std::uint8_t>((rgb >> 8U) & 0xffU),
        static_cast<std::uint8_t>(rgb & 0xffU),
        alpha};
}

SDL_Texture* textTexture(
    SDL_Renderer* renderer,
    TTF_Font* font,
    const std::string& text,
    SDL_Color c) {
    SDL_Surface* surface = TTF_RenderUTF8_Blended(font, text.c_str(), c);
    if (surface == nullptr) return nullptr;
    SDL_Texture* texture = SDL_CreateTextureFromSurface(renderer, surface);
    SDL_FreeSurface(surface);
    return texture;
}

void drawCentered(
    SDL_Renderer* renderer,
    TTF_Font* font,
    const std::string& text,
    SDL_Color c,
    int cx,
    int cy) {
    SDL_Texture* texture = textTexture(renderer, font, text, c);
    if (texture == nullptr) return;
    int w = 0;
    int h = 0;
    SDL_QueryTexture(texture, nullptr, nullptr, &w, &h);
    SDL_Rect dst{cx - w / 2, cy - h / 2, w, h};
    SDL_RenderCopy(renderer, texture, nullptr, &dst);
    SDL_DestroyTexture(texture);
}

void drawLeft(
    SDL_Renderer* renderer,
    TTF_Font* font,
    const std::string& text,
    SDL_Color c,
    int x,
    int cy) {
    SDL_Texture* texture = textTexture(renderer, font, text, c);
    if (texture == nullptr) return;
    int w = 0;
    int h = 0;
    SDL_QueryTexture(texture, nullptr, nullptr, &w, &h);
    SDL_Rect dst{x, cy - h / 2, w, h};
    SDL_RenderCopy(renderer, texture, nullptr, &dst);
    SDL_DestroyTexture(texture);
}

void drawRight(
    SDL_Renderer* renderer,
    TTF_Font* font,
    const std::string& text,
    SDL_Color c,
    int x,
    int cy) {
    SDL_Texture* texture = textTexture(renderer, font, text, c);
    if (texture == nullptr) return;
    int w = 0;
    int h = 0;
    SDL_QueryTexture(texture, nullptr, nullptr, &w, &h);
    SDL_Rect dst{x - w, cy - h / 2, w, h};
    SDL_RenderCopy(renderer, texture, nullptr, &dst);
    SDL_DestroyTexture(texture);
}

void fillRect(SDL_Renderer* renderer, const SDL_Rect& r, SDL_Color c) {
    SDL_SetRenderDrawColor(renderer, c.r, c.g, c.b, c.a);
    SDL_RenderFillRect(renderer, &r);
}

void roundedRect(
    SDL_Renderer* renderer,
    int x,
    int y,
    int w,
    int h,
    int radius,
    SDL_Color c) {
    SDL_SetRenderDrawColor(renderer, c.r, c.g, c.b, c.a);
    SDL_Rect horizontal{x + radius, y, std::max(0, w - 2 * radius), h};
    SDL_Rect vertical{x, y + radius, w, std::max(0, h - 2 * radius)};
    SDL_RenderFillRect(renderer, &horizontal);
    SDL_RenderFillRect(renderer, &vertical);
    for (int dy = 0; dy < radius; ++dy) {
        for (int dx = 0; dx < radius; ++dx) {
            const int px = radius - 1 - dx;
            const int py = radius - 1 - dy;
            if (px * px + py * py <= radius * radius) {
                SDL_RenderDrawPoint(renderer, x + dx, y + dy);
                SDL_RenderDrawPoint(renderer, x + w - 1 - dx, y + dy);
                SDL_RenderDrawPoint(renderer, x + dx, y + h - 1 - dy);
                SDL_RenderDrawPoint(renderer, x + w - 1 - dx, y + h - 1 - dy);
            }
        }
    }
}

void outlineRect(SDL_Renderer* renderer, const SDL_Rect& r, SDL_Color c) {
    SDL_SetRenderDrawColor(renderer, c.r, c.g, c.b, c.a);
    SDL_RenderDrawRect(renderer, &r);
}

std::string clockText() {
    const std::time_t now = std::time(nullptr);
    std::tm local{};
    localtime_r(&now, &local);
    char buf[16];
    std::strftime(buf, sizeof(buf), "%H:%M", &local);
    return buf;
}

std::string speedText(bool valid, float speed) {
    if (!valid) return "--";
    char buf[16];
    std::snprintf(buf, sizeof(buf), "%.0f", speed);
    return buf;
}

std::string tireText(const dashboard::Signal<float>& signal) {
    if (!signal.valid) return "--";
    char buf[16];
    std::snprintf(buf, sizeof(buf), "%.1f", static_cast<double>(signal.value));
    return buf;
}

const char* gearLongName(dashboard::Gear gear) {
    switch (gear) {
        case dashboard::Gear::Park: return "PARK";
        case dashboard::Gear::Reverse: return "REVERSE";
        case dashboard::Gear::Neutral: return "NEUTRAL";
        case dashboard::Gear::Drive: return "DRIVE";
        default: return "NO DATA";
    }
}

bool anyClosureOpen(const dashboard::VehicleState& s) {
    return (s.door_fl.valid && s.door_fl.value) ||
        (s.door_fr.valid && s.door_fr.value) ||
        (s.door_rl.valid && s.door_rl.value) ||
        (s.door_rr.valid && s.door_rr.value) ||
        (s.frunk.valid && s.frunk.value) ||
        (s.trunk.valid && s.trunk.value);
}

std::string closureSummary(const dashboard::VehicleState& s) {
    const bool any_valid = s.door_fl.valid || s.door_fr.valid ||
        s.door_rl.valid || s.door_rr.valid || s.frunk.valid || s.trunk.valid;
    if (!any_valid) return "DOORS --";
    if (!anyClosureOpen(s)) return "ALL CLOSED";

    std::string result = "OPEN";
    if (s.door_fl.valid && s.door_fl.value) result += "  FL";
    if (s.door_fr.valid && s.door_fr.value) result += "  FR";
    if (s.door_rl.valid && s.door_rl.value) result += "  RL";
    if (s.door_rr.valid && s.door_rr.value) result += "  RR";
    if (s.frunk.valid && s.frunk.value) result += "  FRUNK";
    if (s.trunk.valid && s.trunk.value) result += "  TRUNK";
    return result;
}

void drawVehicleSilhouette(
    SDL_Renderer* renderer,
    const dashboard::VehicleState& state,
    const dashboard::ThemePalette& p) {
    const SDL_Color body = color(p.panel_border);
    const SDL_Color glass = color(p.secondary, 150);
    const SDL_Color open = color(p.caution);

    roundedRect(renderer, 735, 121, 450, 214, 70, body);
    roundedRect(renderer, 790, 146, 340, 164, 54, color(p.background));
    SDL_Rect cabin{838, 168, 244, 120};
    fillRect(renderer, cabin, glass);

    SDL_Rect nose{930, 108, 60, 26};
    SDL_Rect tail{930, 322, 60, 26};
    fillRect(renderer, nose, color(p.panel));
    fillRect(renderer, tail, color(p.panel));

    const SDL_Color normal = color(p.panel_border);
    SDL_Rect fl{715, 160, 44, 66};
    SDL_Rect fr{1161, 160, 44, 66};
    SDL_Rect rl{715, 238, 44, 66};
    SDL_Rect rr{1161, 238, 44, 66};
    fillRect(renderer, fl, state.door_fl.valid && state.door_fl.value ? open : normal);
    fillRect(renderer, fr, state.door_fr.valid && state.door_fr.value ? open : normal);
    fillRect(renderer, rl, state.door_rl.valid && state.door_rl.value ? open : normal);
    fillRect(renderer, rr, state.door_rr.valid && state.door_rr.value ? open : normal);
}

void drawTopStatus(
    SDL_Renderer* renderer,
    const Fonts& fonts,
    const dashboard::VehicleState& state,
    const dashboard::ProductState& product,
    const dashboard::ThemePalette& p) {
    const SDL_Color secondary = color(p.secondary);
    int left = 150;
    if (state.ambient_temperature.valid) {
        char buf[24];
        std::snprintf(buf, sizeof(buf), "%.0f°C", static_cast<double>(state.ambient_temperature.value));
        drawLeft(renderer, fonts.tiny, buf, secondary, left, 34);
        left += 76;
    } else if (state.temperature_primary.valid) {
        char buf[24];
        std::snprintf(buf, sizeof(buf), "%d°C", static_cast<int>(state.temperature_primary.value));
        drawLeft(renderer, fonts.tiny, buf, secondary, left, 34);
        left += 76;
    }

    int right = 1770;
    if (product.commander.available && product.commander.connected) {
        drawRight(renderer, fonts.tiny, "Commander  ●", color(p.success), right, 34);
        right -= 150;
    }
    if (product.phone.available && !product.phone.network_label.empty()) {
        drawRight(renderer, fonts.tiny, product.phone.network_label, secondary, right, 34);
        right -= 90;
    }
    drawRight(renderer, fonts.tiny, clockText(), color(p.primary), right, 34);
}

void drawContextCard(
    SDL_Renderer* renderer,
    const Fonts& fonts,
    const dashboard::ProductState& product,
    const dashboard::ContextDecision& decision,
    const dashboard::ThemePalette& p) {
    SDL_Rect card{1300, 300, 410, 118};
    roundedRect(renderer, card.x, card.y, card.w, card.h, 18, color(p.panel));
    outlineRect(renderer, card, color(p.panel_border));

    if (decision.card == dashboard::ContextCardKind::Navigation && product.navigation.active) {
        drawLeft(renderer, fonts.tiny, "NAVIGATION", color(p.accent), card.x + 22, card.y + 24);
        drawLeft(renderer, fonts.small,
                 product.navigation.remaining_minutes > 0
                     ? std::to_string(product.navigation.remaining_minutes) + " min"
                     : "-- min",
                 color(p.primary), card.x + 22, card.y + 62);
        std::string detail = product.navigation.remaining_distance_km > 0.0F
            ? std::to_string(static_cast<int>(std::round(product.navigation.remaining_distance_km))) + " km"
            : "-- km";
        if (!product.navigation.eta_text.empty()) detail += "  ·  ETA " + product.navigation.eta_text;
        drawLeft(renderer, fonts.tiny, detail, color(p.secondary), card.x + 22, card.y + 94);
        return;
    }

    if (decision.card == dashboard::ContextCardKind::Media && product.media.available) {
        drawLeft(renderer, fonts.tiny, "NOW PLAYING", color(p.accent), card.x + 22, card.y + 24);
        drawLeft(renderer, fonts.small,
                 product.media.title.empty() ? "--" : product.media.title,
                 color(p.primary), card.x + 22, card.y + 62);
        drawLeft(renderer, fonts.tiny,
                 product.media.artist.empty() ? "--" : product.media.artist,
                 color(p.secondary), card.x + 22, card.y + 94);
        return;
    }

    drawLeft(renderer, fonts.tiny, "CONTEXT", color(p.secondary), card.x + 22, card.y + 24);
    drawLeft(renderer, fonts.small, "Ready", color(p.primary), card.x + 22, card.y + 66);
}

void renderHorizon(
    SDL_Renderer* renderer,
    const Fonts& fonts,
    const dashboard::VehicleState& state,
    const dashboard::ProductState& product,
    const dashboard::ContextDecision& context,
    const dashboard::ThemePalette& p,
    dashboard::MotionEngine& motion,
    std::uint32_t delta_ms) {
    const float target_speed = state.speed.valid ? static_cast<float>(state.speed.value) : 0.0F;
    const float shown_speed = motion.animate(dashboard::MotionChannel::Speed, target_speed, delta_ms);
    const dashboard::Signal<std::uint8_t>& soc = state.actual_soc.valid ? state.actual_soc : state.soc;
    const float target_soc = soc.valid ? static_cast<float>(soc.value) : 0.0F;
    const float shown_soc = motion.animate(dashboard::MotionChannel::Soc, target_soc, delta_ms);

    drawTopStatus(renderer, fonts, state, product, p);

    drawLeft(renderer, fonts.tiny, "SPEED", color(p.secondary), 180, 90);
    drawCentered(renderer, fonts.speed,
                 speedText(state.speed.valid, shown_speed),
                 state.speed.valid ? color(p.primary) : color(p.secondary), 390, 215);
    drawCentered(renderer, fonts.small, "km/h", color(p.secondary), 390, 332);

    const std::string gear = state.gear.valid ? dashboard::gearName(state.gear.value) : "--";
    roundedRect(renderer, 180, 360, 102, 62, 15, color(p.panel));
    drawCentered(renderer, fonts.medium, gear,
                 state.gear.valid ? color(p.accent) : color(p.secondary), 231, 391);
    drawLeft(renderer, fonts.tiny,
             state.gear.valid ? gearLongName(state.gear.value) : "NO DATA",
             color(p.secondary), 306, 391);

    drawVehicleSilhouette(renderer, state, p);
    drawCentered(renderer, fonts.small, closureSummary(state),
                 anyClosureOpen(state) ? color(p.caution) : color(p.secondary),
                 960, 382);

    const std::string tires =
        "FL " + tireText(state.tire_fl) + "   FR " + tireText(state.tire_fr) +
        "   RL " + tireText(state.tire_rl) + "   RR " + tireText(state.tire_rr) + " bar";
    drawCentered(renderer, fonts.tiny, tires, color(p.secondary), 960, 430);

    drawLeft(renderer, fonts.tiny,
             state.actual_soc.valid ? "BATTERY" : "MCU SOC · unverified",
             state.actual_soc.valid ? color(p.secondary) : color(p.caution), 1320, 90);
    const std::string soc_text = soc.valid
        ? std::to_string(static_cast<int>(std::round(shown_soc))) + "%"
        : "--%";
    drawLeft(renderer, fonts.hero, soc_text,
             soc.valid ? color(p.primary) : color(p.secondary), 1320, 166);

    SDL_Rect track{1320, 245, 330, 8};
    fillRect(renderer, track, color(p.panel_border));
    if (soc.valid) {
        SDL_Rect fill{track.x, track.y,
                      static_cast<int>(track.w * std::max(0.0F, std::min(100.0F, shown_soc)) / 100.0F),
                      track.h};
        fillRect(renderer, fill, color(p.accent));
    }

    const std::string range = state.range.valid
        ? std::to_string(state.range.value) + " km range"
        : "-- km range";
    drawLeft(renderer, fonts.small, range,
             state.range.valid ? color(p.primary) : color(p.secondary), 1320, 280);

    drawContextCard(renderer, fonts, product, context, p);
}

void renderMono(
    SDL_Renderer* renderer,
    const Fonts& fonts,
    const dashboard::VehicleState& state,
    const dashboard::ProductState& product,
    const dashboard::ThemePalette& p,
    dashboard::MotionEngine& motion,
    std::uint32_t delta_ms) {
    const float target_speed = state.speed.valid ? static_cast<float>(state.speed.value) : 0.0F;
    const float shown_speed = motion.animate(dashboard::MotionChannel::Speed, target_speed, delta_ms);
    const dashboard::Signal<std::uint8_t>& soc = state.actual_soc.valid ? state.actual_soc : state.soc;

    drawTopStatus(renderer, fonts, state, product, p);

    drawCentered(renderer, fonts.medium,
                 state.gear.valid ? dashboard::gearName(state.gear.value) : "--",
                 state.gear.valid ? color(p.accent) : color(p.secondary), 960, 92);
    drawCentered(renderer, fonts.speed,
                 speedText(state.speed.valid, shown_speed),
                 state.speed.valid ? color(p.primary) : color(p.secondary), 960, 220);
    drawCentered(renderer, fonts.small, "km/h", color(p.secondary), 960, 328);

    SDL_SetRenderDrawColor(renderer,
                           color(p.panel_border).r,
                           color(p.panel_border).g,
                           color(p.panel_border).b,
                           255);
    SDL_RenderDrawLine(renderer, 820, 360, 1100, 360);

    drawRight(renderer, fonts.medium,
              soc.valid ? std::to_string(static_cast<unsigned>(soc.value)) + "%" : "--%",
              soc.valid ? color(p.primary) : color(p.secondary), 780, 405);
    drawLeft(renderer, fonts.medium,
             state.range.valid ? std::to_string(state.range.value) + " km" : "-- km",
             state.range.valid ? color(p.primary) : color(p.secondary), 1140, 405);

    if (anyClosureOpen(state)) {
        drawLeft(renderer, fonts.small, closureSummary(state), color(p.caution), 160, 238);
    }
}

void renderPlannedPage(
    SDL_Renderer* renderer,
    const Fonts& fonts,
    dashboard::DashboardPage page,
    const dashboard::ThemePalette& p) {
    drawCentered(renderer, fonts.medium, dashboard::dashboardPageName(page), color(p.primary), 960, 195);
    drawCentered(renderer, fonts.small, "Product page reserved · implementation follows roadmap",
                 color(p.secondary), 960, 250);
}

SDL_Color warningColor(
    dashboard::WarningSeverity severity,
    const dashboard::ThemePalette& p) {
    switch (severity) {
        case dashboard::WarningSeverity::Info: return color(p.accent);
        case dashboard::WarningSeverity::Caution: return color(p.caution);
        case dashboard::WarningSeverity::Warning:
        case dashboard::WarningSeverity::Critical: return color(p.danger);
        default: return color(p.secondary);
    }
}

void drawSafetyLayer(
    SDL_Renderer* renderer,
    const Fonts& fonts,
    const dashboard::SafetyLayerState& safety,
    dashboard::DashboardPage page,
    const dashboard::ThemePalette& p) {
    // On Horizon and Mono, speed/gear/SOC are already primary content. Other
    // pages receive a compact always-visible driving strip.
    if (page != dashboard::DashboardPage::Horizon && page != dashboard::DashboardPage::Mono) {
        roundedRect(renderer, 126, 382, 1668, 68, 14, color(p.panel));
        drawLeft(renderer, fonts.medium,
                 safety.gear_available ? dashboard::gearName(safety.gear) : "--",
                 safety.gear_available ? color(p.accent) : color(p.secondary), 160, 416);
        drawLeft(renderer, fonts.medium,
                 safety.speed_available ? std::to_string(safety.speed_kph) + " km/h" : "-- km/h",
                 safety.speed_available ? color(p.primary) : color(p.secondary), 260, 416);
        drawRight(renderer, fonts.medium,
                  safety.soc_available ? std::to_string(static_cast<unsigned>(safety.soc_percent)) + "%" : "--%",
                  safety.soc_available ? color(p.primary) : color(p.secondary), 1760, 416);
    }

    if (safety.top_warning != nullptr) {
        const dashboard::WarningItem& warning = *safety.top_warning;
        const SDL_Color wc = warningColor(warning.severity, p);
        if (warning.severity == dashboard::WarningSeverity::Critical) {
            SDL_Rect banner{430, 20, 1060, 76};
            roundedRect(renderer, banner.x, banner.y, banner.w, banner.h, 14, wc);
            drawCentered(renderer, fonts.medium, warning.title, color(0xFFFFFF), 960, 58);
        } else {
            SDL_Rect banner{590, 24, 740, 58};
            roundedRect(renderer, banner.x, banner.y, banner.w, banner.h, 13, color(p.panel));
            outlineRect(renderer, banner, wc);
            drawCentered(renderer, fonts.small, warning.title, wc, 960, 53);
        }
    }
}

void drawPageIndicator(
    SDL_Renderer* renderer,
    dashboard::DashboardPage page,
    const dashboard::ThemePalette& p) {
    const int center = 960;
    const int gap = 22;
    for (int i = 0; i < 7; ++i) {
        SDL_Rect dot{center + (i - 3) * gap - 8, 465, i == static_cast<int>(page) ? 16 : 6, 3};
        fillRect(renderer, dot,
                 i == static_cast<int>(page) ? color(p.accent) : color(p.panel_border));
    }
}

void drawShapeMask(SDL_Renderer* renderer) {
    SDL_SetRenderDrawColor(renderer, 0, 0, 0, 255);
    for (int y = 0; y < kHeight; ++y) {
        const int left = kTopCut + (kBottomCut - kTopCut) * y / kHeight;
        const int right = kWidth - kTopCut - (kBottomCut - kTopCut) * y / kHeight;
        if (left > 0) SDL_RenderDrawLine(renderer, 0, y, left, y);
        if (right < kWidth) SDL_RenderDrawLine(renderer, right, y, kWidth, y);
    }
}

std::vector<std::uint8_t> makeFrame(
    std::uint8_t command,
    const std::vector<std::uint8_t>& payload) {
    std::vector<std::uint8_t> frame{
        dashboard::ProtocolParser::kHeader,
        command,
        static_cast<std::uint8_t>(payload.size())};
    frame.insert(frame.end(), payload.begin(), payload.end());
    frame.push_back(dashboard::ProtocolParser::checksum(
        command, payload.empty() ? nullptr : payload.data(), payload.size()));
    return frame;
}

bool saveScreenshot(SDL_Renderer* renderer, const char* path) {
    SDL_Surface* surface = SDL_CreateRGBSurfaceWithFormat(
        0, kWidth, kHeight, 32, SDL_PIXELFORMAT_RGBA32);
    if (surface == nullptr) return false;
    const int rc = SDL_RenderReadPixels(
        renderer, nullptr, SDL_PIXELFORMAT_RGBA32, surface->pixels, surface->pitch);
    bool ok = false;
    if (rc == 0) ok = SDL_SaveBMP(surface, path) == 0;
    SDL_FreeSurface(surface);
    return ok;
}

void closeFonts(Fonts& fonts) {
    if (fonts.speed) TTF_CloseFont(fonts.speed);
    if (fonts.hero) TTF_CloseFont(fonts.hero);
    if (fonts.medium) TTF_CloseFont(fonts.medium);
    if (fonts.small) TTF_CloseFont(fonts.small);
    if (fonts.tiny) TTF_CloseFont(fonts.tiny);
    fonts = Fonts{};
}

}  // namespace

int main(int argc, char** argv) {
    bool screenshot_mode = false;
    bool dump_state = false;
    const char* screenshot_path = "/tmp/dashboard-product.bmp";
    const char* replay_path = "captures/uart-record-realcar-geardoor.bin";

    for (int i = 1; i < argc; ++i) {
        if (std::strcmp(argv[i], "--screenshot") == 0) {
            screenshot_mode = true;
            if (i + 1 < argc && argv[i + 1][0] != '-') screenshot_path = argv[++i];
        } else if (std::strcmp(argv[i], "--dump-state") == 0) {
            dump_state = true;
        } else {
            replay_path = argv[i];
        }
    }

    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_TIMER) != 0) {
        std::fprintf(stderr, "SDL_Init: %s\n", SDL_GetError());
        return 1;
    }
    if (TTF_Init() != 0) {
        std::fprintf(stderr, "TTF_Init: %s\n", TTF_GetError());
        SDL_Quit();
        return 1;
    }

    SDL_Window* window = SDL_CreateWindow(
        "Tesla Dashboard Product Simulator",
        SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
        kWidth, kHeight,
        screenshot_mode ? SDL_WINDOW_HIDDEN : SDL_WINDOW_RESIZABLE);
    if (window == nullptr) return 1;

    SDL_Renderer* renderer = SDL_CreateRenderer(
        window, -1,
        screenshot_mode ? SDL_RENDERER_SOFTWARE
                        : (SDL_RENDERER_ACCELERATED | SDL_RENDERER_PRESENTVSYNC));
    if (renderer == nullptr) return 1;
    SDL_RenderSetLogicalSize(renderer, kWidth, kHeight);

    Fonts fonts;
    fonts.speed = TTF_OpenFont(kFontPath, 154);
    fonts.hero = TTF_OpenFont(kFontPath, 84);
    fonts.medium = TTF_OpenFont(kFontPath, 42);
    fonts.small = TTF_OpenFont(kFontPath, 28);
    fonts.tiny = TTF_OpenFont(kFontPath, 21);
    if (!fonts.speed || !fonts.hero || !fonts.medium || !fonts.small || !fonts.tiny) {
        std::fprintf(stderr, "TTF_OpenFont: %s\n", TTF_GetError());
        return 1;
    }

    dashboard::OriginalMcuAdapter adapter;
    dashboard::sim::ReplaySource replay(adapter, 0);
    const bool has_replay = replay.load(replay_path);

    dashboard::ThemeManager themes;
    dashboard::PageManager pages;
    dashboard::MotionEngine motion;
    dashboard::WarningManager warning_manager;
    dashboard::ContextRouter context_router;
    dashboard::ProductState product;

    bool running = true;
    bool synthetic = !has_replay;
    bool frozen = false;
    bool night = true;
    std::uint64_t last_frame_ms = SDL_GetTicks();
    std::uint64_t next_synth_ms = 0;
    std::uint64_t last_feed_ms = 0;
    std::uint16_t synth_speed = 0;
    std::uint8_t synth_soc = 68;
    std::uint16_t synth_range = 284;
    dashboard::Gear synth_gear = dashboard::Gear::Park;
    std::uint64_t frames = 0;

    while (running) {
        SDL_Event event;
        while (SDL_PollEvent(&event)) {
            if (event.type == SDL_QUIT) running = false;
            if (event.type != SDL_KEYDOWN) continue;
            switch (event.key.keysym.sym) {
                case SDLK_ESCAPE: running = false; break;
                case SDLK_LEFT: pages.previous(); break;
                case SDLK_RIGHT: pages.next(); break;
                case SDLK_1: pages.setPage(dashboard::DashboardPage::Horizon); break;
                case SDLK_2: pages.setPage(dashboard::DashboardPage::Mono); break;
                case SDLK_3: pages.setPage(dashboard::DashboardPage::Pulse); break;
                case SDLK_4: pages.setPage(dashboard::DashboardPage::Route); break;
                case SDLK_5: pages.setPage(dashboard::DashboardPage::Studio); break;
                case SDLK_6: pages.setPage(dashboard::DashboardPage::Energy); break;
                case SDLK_7: pages.setPage(dashboard::DashboardPage::Nocturne); break;
                case SDLK_t:
                    themes.setTheme(themes.theme() == dashboard::DashboardTheme::Dark
                                        ? dashboard::DashboardTheme::Graphite
                                        : dashboard::DashboardTheme::Dark);
                    break;
                case SDLK_m: motion.setEnabled(!motion.enabled()); break;
                case SDLK_s: frozen = !frozen; break;
                case SDLK_SPACE:
                    if (has_replay) {
                        synthetic = !synthetic;
                        replay.reset();
                    }
                    break;
                case SDLK_UP:
                    synth_speed = static_cast<std::uint16_t>(std::min(240, synth_speed + 5));
                    break;
                case SDLK_DOWN:
                    synth_speed = static_cast<std::uint16_t>(std::max(0, synth_speed - 5));
                    break;
                case SDLK_p: synth_gear = dashboard::Gear::Park; break;
                case SDLK_d: synth_gear = dashboard::Gear::Drive; break;
                case SDLK_r: synth_gear = dashboard::Gear::Reverse; break;
                case SDLK_n: synth_gear = dashboard::Gear::Neutral; break;
                default: break;
            }
        }

        const std::uint64_t now_ms = SDL_GetTicks();
        const std::uint32_t delta_ms = static_cast<std::uint32_t>(
            std::min<std::uint64_t>(100, now_ms >= last_frame_ms ? now_ms - last_frame_ms : 0));
        last_frame_ms = now_ms;

        if (!frozen) {
            if (synthetic) {
                if (now_ms >= next_synth_ms) {
                    const auto driving = makeFrame(
                        0x04,
                        {static_cast<std::uint8_t>(synth_speed & 0xff),
                         static_cast<std::uint8_t>(synth_speed >> 8),
                         0, 0, 0, 0,
                         static_cast<std::uint8_t>(synth_range & 0xff),
                         static_cast<std::uint8_t>(synth_range >> 8),
                         synth_soc, 0, 0x10, 0x30, 0x03});
                    adapter.feed(driving.data(), driving.size(), now_ms);
                    const auto gear = makeFrame(
                        0x01,
                        {0, 0, 0, 0,
                         static_cast<std::uint8_t>(static_cast<unsigned>(synth_gear) << 4)});
                    adapter.feed(gear.data(), gear.size(), now_ms);
                    next_synth_ms = now_ms + 100;
                    last_feed_ms = now_ms;
                }
            } else {
                replay.tick(now_ms);
                last_feed_ms = now_ms;
            }
        }

        adapter.tick(now_ms);
        pages.tick(delta_ms, motion.enabled());

        dashboard::SafetyInputs safety_inputs;
        safety_inputs.vehicle_link_connected = true;
        safety_inputs.vehicle_link_has_data = last_feed_ms != 0;
        safety_inputs.vehicle_link_age_ms =
            last_feed_ms != 0 && now_ms >= last_feed_ms ? now_ms - last_feed_ms : 0;
        if (frozen && last_feed_ms != 0 && now_ms >= last_feed_ms) {
            safety_inputs.vehicle_link_age_ms = now_ms - last_feed_ms;
        }
        if (safety_inputs.vehicle_link_age_ms > kVehicleLinkStaleMs) {
            safety_inputs.vehicle_link_has_data = false;
        }

        const dashboard::VehicleState& state = adapter.state();
        warning_manager.evaluate(state, safety_inputs);
        const dashboard::ContextDecision context =
            context_router.decide(product, warning_manager, false);
        const dashboard::SafetyLayerState safety =
            dashboard::buildSafetyLayer(state, warning_manager);
        const dashboard::ThemePalette palette = themes.palette(night);

        SDL_SetRenderDrawColor(
            renderer,
            color(palette.background).r,
            color(palette.background).g,
            color(palette.background).b,
            255);
        SDL_RenderClear(renderer);

        switch (pages.page()) {
            case dashboard::DashboardPage::Horizon:
                renderHorizon(renderer, fonts, state, product, context, palette, motion, delta_ms);
                break;
            case dashboard::DashboardPage::Mono:
                renderMono(renderer, fonts, state, product, palette, motion, delta_ms);
                break;
            default:
                renderPlannedPage(renderer, fonts, pages.page(), palette);
                break;
        }

        drawSafetyLayer(renderer, fonts, safety, pages.page(), palette);
        drawPageIndicator(renderer, pages.page(), palette);
        drawShapeMask(renderer);
        SDL_RenderPresent(renderer);
        ++frames;

        if (dump_state && frames >= 12) {
            std::fprintf(
                stderr,
                "[product] page=%s speed=%s gear=%s soc=%s warning=%s motion=%s\n",
                dashboard::dashboardPageName(pages.page()),
                state.speed.valid ? std::to_string(state.speed.value).c_str() : "--",
                state.gear.valid ? dashboard::gearName(state.gear.value) : "--",
                safety.soc_available ? std::to_string(static_cast<unsigned>(safety.soc_percent)).c_str() : "--",
                safety.top_warning ? safety.top_warning->title.c_str() : "none",
                motion.enabled() ? "on" : "off");
            running = false;
        }
        if (screenshot_mode && frames >= 4) {
            if (!saveScreenshot(renderer, screenshot_path)) {
                std::fprintf(stderr, "failed to save screenshot: %s\n", screenshot_path);
                return 1;
            }
            std::fprintf(stderr, "[product] screenshot saved: %s\n", screenshot_path);
            running = false;
        }

        const std::uint64_t after_render = SDL_GetTicks();
        const std::uint64_t spent = after_render >= now_ms ? after_render - now_ms : 0;
        if (!screenshot_mode && spent < static_cast<std::uint64_t>(kFrameMs)) {
            SDL_Delay(static_cast<std::uint32_t>(kFrameMs - spent));
        }
    }

    closeFonts(fonts);
    SDL_DestroyRenderer(renderer);
    SDL_DestroyWindow(window);
    TTF_Quit();
    SDL_Quit();
    return 0;
}
