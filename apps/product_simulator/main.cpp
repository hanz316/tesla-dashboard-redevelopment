// Standalone seven-page Tesla dashboard product simulator.
//
// This executable is intentionally independent from vehicle UART/replay and
// from FlyThings. It renders the complete product information architecture at
// 1920x480 using synthetic IDataSource-style state and ProductState fixtures.
// No vehicle control, BLE, UART write, CAN TX, or device deployment exists here.
//
// Keys:
//   Left/Right or 1..7  switch pages
//   T                  cycle theme (Dark/Graphite/Light)
//   M                  toggle motion A/B
//   C                  toggle simulated Commander telemetry
//   L / R              toggle turn indicators
//   O                  toggle driver door open
//   Up/Down            speed +/- 5 km/h
//   Esc                quit

#include "dashboard/dashboard_product.h"
#include "dashboard/signal.h"
#include "dashboard/source_adapters.h"

#include <SDL.h>
#include <SDL_ttf.h>

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <string>
#include <vector>

namespace {

constexpr int kWidth = 1920;
constexpr int kHeight = 480;
constexpr int kTopCut = 116;
constexpr int kBottomCut = 51;
constexpr int kFrameMs = 33;
constexpr const char* kDefaultFont = "/System/Library/Fonts/Supplemental/Arial.ttf";

struct Fonts {
    TTF_Font* hero{nullptr};
    TTF_Font* speed{nullptr};
    TTF_Font* title{nullptr};
    TTF_Font* medium{nullptr};
    TTF_Font* small{nullptr};
    TTF_Font* tiny{nullptr};
};

struct UiRuntime {
    dashboard::ThemeManager themes;
    dashboard::PageManager pages;
    dashboard::MotionEngine motion;
    dashboard::WarningManager warnings;
    dashboard::ContextRouter router;
    dashboard::ProductState product;
    dashboard::VehicleState vehicle;
    dashboard::SafetyInputs safety;
    bool commander_demo{false};
    bool left_signal{false};
    bool right_signal{false};
    bool door_open{false};
    std::uint16_t speed{72};
    dashboard::Gear gear{dashboard::Gear::Drive};
};

SDL_Color rgb(std::uint32_t value, std::uint8_t alpha = 255) {
    return SDL_Color{
        static_cast<std::uint8_t>((value >> 16) & 0xff),
        static_cast<std::uint8_t>((value >> 8) & 0xff),
        static_cast<std::uint8_t>(value & 0xff),
        alpha};
}

void setColor(SDL_Renderer* r, SDL_Color c) {
    SDL_SetRenderDrawColor(r, c.r, c.g, c.b, c.a);
}

SDL_Texture* makeText(SDL_Renderer* r, TTF_Font* font, const std::string& text, SDL_Color color) {
    SDL_Surface* surface = TTF_RenderUTF8_Blended(font, text.c_str(), color);
    if (!surface) return nullptr;
    SDL_Texture* texture = SDL_CreateTextureFromSurface(r, surface);
    SDL_FreeSurface(surface);
    return texture;
}

void drawText(SDL_Renderer* r, TTF_Font* font, const std::string& text,
              SDL_Color color, int x, int cy, int align = 0) {
    SDL_Texture* texture = makeText(r, font, text, color);
    if (!texture) return;
    int w = 0, h = 0;
    SDL_QueryTexture(texture, nullptr, nullptr, &w, &h);
    int dx = x;
    if (align == 1) dx -= w / 2;
    else if (align == 2) dx -= w;
    SDL_Rect dst{dx, cy - h / 2, w, h};
    SDL_RenderCopy(r, texture, nullptr, &dst);
    SDL_DestroyTexture(texture);
}

void fillRect(SDL_Renderer* r, int x, int y, int w, int h, SDL_Color color) {
    setColor(r, color);
    SDL_Rect rect{x, y, w, h};
    SDL_RenderFillRect(r, &rect);
}

void strokeRect(SDL_Renderer* r, int x, int y, int w, int h, SDL_Color color) {
    setColor(r, color);
    SDL_Rect rect{x, y, w, h};
    SDL_RenderDrawRect(r, &rect);
}

void fillRounded(SDL_Renderer* r, int x, int y, int w, int h, int radius, SDL_Color color) {
    setColor(r, color);
    SDL_Rect center{x + radius, y, std::max(0, w - radius * 2), h};
    SDL_Rect middle{x, y + radius, w, std::max(0, h - radius * 2)};
    SDL_RenderFillRect(r, &center);
    SDL_RenderFillRect(r, &middle);
    for (int yy = 0; yy < radius; ++yy) {
        for (int xx = 0; xx < radius; ++xx) {
            const int dx = radius - xx;
            const int dy = radius - yy;
            if (dx * dx + dy * dy <= radius * radius) {
                SDL_RenderDrawPoint(r, x + xx, y + yy);
                SDL_RenderDrawPoint(r, x + w - 1 - xx, y + yy);
                SDL_RenderDrawPoint(r, x + xx, y + h - 1 - yy);
                SDL_RenderDrawPoint(r, x + w - 1 - xx, y + h - 1 - yy);
            }
        }
    }
}

void line(SDL_Renderer* r, int x1, int y1, int x2, int y2, SDL_Color color) {
    setColor(r, color);
    SDL_RenderDrawLine(r, x1, y1, x2, y2);
}

std::string valueOrDash(const dashboard::Signal<float>& s, const char* suffix, int decimals = 1) {
    if (!s.valid) return std::string("--") + suffix;
    char buf[48];
    if (decimals == 0) std::snprintf(buf, sizeof(buf), "%.0f%s", s.value, suffix);
    else std::snprintf(buf, sizeof(buf), "%.1f%s", s.value, suffix);
    return buf;
}

std::string uintOrDash(const dashboard::Signal<std::uint8_t>& s, const char* suffix) {
    if (!s.valid) return std::string("--") + suffix;
    char buf[32];
    std::snprintf(buf, sizeof(buf), "%u%s", static_cast<unsigned>(s.value), suffix);
    return buf;
}

void drawTrapezoidMask(SDL_Renderer* r) {
    setColor(r, SDL_Color{0, 0, 0, 255});
    for (int y = 0; y < kHeight; ++y) {
        const int left = kTopCut + (kBottomCut - kTopCut) * y / kHeight;
        const int right = kWidth - kTopCut - (kBottomCut - kTopCut) * y / kHeight;
        if (left > 0) SDL_RenderDrawLine(r, 0, y, left, y);
        if (right < kWidth) SDL_RenderDrawLine(r, right, y, kWidth, y);
    }
}

void drawPageIndicator(SDL_Renderer* r, dashboard::DashboardPage page,
                       const dashboard::ThemePalette& p) {
    const int start = 840;
    for (int i = 0; i < 7; ++i) {
        SDL_Color c = rgb(i == static_cast<int>(page) ? p.accent : p.panel_border);
        const int w = i == static_cast<int>(page) ? 28 : 12;
        fillRounded(r, start + i * 35, 463, w, 3, 1, c);
    }
}

void drawStatusStrip(SDL_Renderer* r, const Fonts& f, const UiRuntime& ui,
                     const dashboard::ThemePalette& p) {
    int x = 1775;
    if (ui.product.commander.available) {
        drawText(r, f.tiny, ui.product.commander.connected ? "Commander ●" : "Commander ○",
                 rgb(ui.product.commander.connected ? p.success : p.secondary), x, 30, 2);
        x -= 170;
    }
    if (ui.product.phone.available) {
        char phone[48];
        std::snprintf(phone, sizeof(phone), "%s %d%%",
                      ui.product.phone.network_label.c_str(), ui.product.phone.battery_percent);
        drawText(r, f.tiny, phone, rgb(p.secondary), x, 30, 2);
        x -= 120;
    }
    if (ui.product.weather.available) {
        char temp[32];
        std::snprintf(temp, sizeof(temp), "%.0f°C", ui.product.weather.current_temperature_c);
        drawText(r, f.tiny, temp, rgb(p.secondary), x, 30, 2);
        x -= 65;
    }
    const std::time_t now = std::time(nullptr);
    std::tm local{};
    localtime_r(&now, &local);
    char clock[16];
    std::strftime(clock, sizeof(clock), "%H:%M", &local);
    drawText(r, f.tiny, clock, rgb(p.secondary), x, 30, 2);
}

void drawVehicleSilhouette(SDL_Renderer* r, const dashboard::VehicleState& s,
                           const dashboard::ThemePalette& p, int cx, int cy) {
    const SDL_Color body = rgb(p.panel_border);
    const SDL_Color edge = rgb(p.secondary);
    fillRounded(r, cx - 76, cy - 110, 152, 220, 38, body);
    strokeRect(r, cx - 76, cy - 110, 152, 220, edge);
    fillRounded(r, cx - 48, cy - 55, 96, 110, 22, rgb(p.panel));
    line(r, cx - 76, cy - 25, cx + 76, cy - 25, edge);
    line(r, cx - 76, cy + 25, cx + 76, cy + 25, edge);

    const SDL_Color open = rgb(p.caution);
    if (s.door_fl.valid && s.door_fl.value) line(r, cx - 77, cy - 54, cx - 124, cy - 80, open);
    if (s.door_fr.valid && s.door_fr.value) line(r, cx + 77, cy - 54, cx + 124, cy - 80, open);
    if (s.door_rl.valid && s.door_rl.value) line(r, cx - 77, cy + 42, cx - 124, cy + 72, open);
    if (s.door_rr.valid && s.door_rr.value) line(r, cx + 77, cy + 42, cx + 124, cy + 72, open);
    if (s.frunk.valid && s.frunk.value) line(r, cx - 45, cy - 111, cx + 45, cy - 140, open);
    if (s.trunk.valid && s.trunk.value) line(r, cx - 45, cy + 111, cx + 45, cy + 142, open);
}

void drawSafetyLayer(SDL_Renderer* r, const Fonts& f, const UiRuntime& ui,
                     const dashboard::ThemePalette& p, bool compact) {
    const dashboard::SafetyLayerState safety = dashboard::buildSafetyLayer(ui.vehicle, ui.warnings);

    // Turn signals are deliberately edge-weighted and lightweight.
    if (ui.vehicle.turn_signal_left.valid && ui.vehicle.turn_signal_left.value) {
        fillRounded(r, 78, 202, 10, 76, 5, rgb(p.success));
        drawText(r, f.medium, "‹", rgb(p.success), 108, 240, 1);
    }
    if (ui.vehicle.turn_signal_right.valid && ui.vehicle.turn_signal_right.value) {
        fillRounded(r, 1832, 202, 10, 76, 5, rgb(p.success));
        drawText(r, f.medium, "›", rgb(p.success), 1812, 240, 1);
    }

    if (!compact) {
        fillRounded(r, 92, 395, 250, 56, 16, rgb(p.panel));
        const std::string gear = safety.gear_available ? dashboard::gearName(safety.gear) : "--";
        const std::string speed = safety.speed_available ? std::to_string(safety.speed_kph) : "--";
        drawText(r, f.small, gear, rgb(p.accent), 120, 423, 0);
        drawText(r, f.small, speed + " km/h", rgb(p.primary), 175, 423, 0);

        fillRounded(r, 1585, 395, 245, 56, 16, rgb(p.panel));
        const std::string soc = safety.soc_available ? std::to_string(safety.soc_percent) + "%" : "--%";
        drawText(r, f.small, soc, rgb(p.primary), 1708, 423, 1);
        if (safety.soc_available && !safety.soc_verified)
            drawText(r, f.tiny, "MCU", rgb(p.secondary), 1790, 423, 1);
    }

    if (safety.top_warning) {
        const auto* warning = safety.top_warning;
        const bool critical = warning->severity == dashboard::WarningSeverity::Critical;
        const SDL_Color warningColor = critical ? rgb(p.danger) : rgb(p.caution);
        fillRounded(r, 670, 16, 580, 58, 14, warningColor);
        drawText(r, f.small, warning->title, SDL_Color{255, 255, 255, 255}, 960, 45, 1);
    }
}

void renderHorizon(SDL_Renderer* r, const Fonts& f, UiRuntime& ui,
                   const dashboard::ThemePalette& p, std::uint32_t dt) {
    const float speedTarget = ui.vehicle.speed.valid ? static_cast<float>(ui.vehicle.speed.value) : 0.0F;
    const float speed = ui.motion.animate(dashboard::MotionChannel::Speed, speedTarget, dt);
    const dashboard::Signal<std::uint8_t>& socSignal = ui.vehicle.actual_soc.valid ? ui.vehicle.actual_soc : ui.vehicle.soc;
    const float socTarget = socSignal.valid ? static_cast<float>(socSignal.value) : 0.0F;
    const float soc = ui.motion.animate(dashboard::MotionChannel::Soc, socTarget, dt);

    drawText(r, f.tiny, "HORIZON", rgb(p.secondary), 150, 30, 0);
    drawStatusStrip(r, f, ui, p);

    drawVehicleSilhouette(r, ui.vehicle, p, 430, 245);
    drawText(r, f.tiny, "VEHICLE", rgb(p.secondary), 430, 392, 1);

    const std::string gear = ui.vehicle.gear.valid ? dashboard::gearName(ui.vehicle.gear.value) : "--";
    drawText(r, f.medium, gear, rgb(p.accent), 930, 83, 1);
    drawText(r, f.speed, ui.vehicle.speed.valid ? std::to_string(static_cast<int>(std::round(speed))) : "--",
             ui.vehicle.speed.valid ? rgb(p.primary) : rgb(p.secondary), 930, 215, 1);
    drawText(r, f.small, "km/h", rgb(p.secondary), 930, 335, 1);

    drawText(r, f.hero, socSignal.valid ? std::to_string(static_cast<int>(std::round(soc))) + "%" : "--%",
             socSignal.valid ? rgb(p.primary) : rgb(p.secondary), 1488, 180, 1);
    drawText(r, f.medium, ui.vehicle.range.valid ? std::to_string(ui.vehicle.range.value) + " km" : "-- km",
             ui.vehicle.range.valid ? rgb(p.primary) : rgb(p.secondary), 1488, 286, 1);
    drawText(r, f.tiny, ui.vehicle.actual_soc.valid ? "ACTUAL SOC" : "MCU SOC · UNVERIFIED",
             rgb(p.secondary), 1488, 330, 1);
    fillRounded(r, 1458, 88, 7, 224, 3, rgb(p.panel_border));
    if (socSignal.valid) {
        const int h = std::max(3, static_cast<int>(224.0F * std::min(100.0F, soc) / 100.0F));
        fillRounded(r, 1458, 312 - h, 7, h, 3, rgb(p.accent));
    }

    const auto decision = ui.router.decide(ui.product, ui.warnings, false);
    fillRounded(r, 1170, 354, 600, 86, 16, rgb(p.panel));
    if (decision.card == dashboard::ContextCardKind::Navigation && ui.product.navigation.active) {
        drawText(r, f.small, ui.product.navigation.next_turn + "  " + ui.product.navigation.road_name,
                 rgb(p.primary), 1200, 378, 0);
        char nav[100];
        std::snprintf(nav, sizeof(nav), "%.1f km · %u min · ETA %s",
                      ui.product.navigation.remaining_distance_km,
                      ui.product.navigation.remaining_minutes,
                      ui.product.navigation.eta_text.c_str());
        drawText(r, f.tiny, nav, rgb(p.secondary), 1200, 416, 0);
    } else if (decision.card == dashboard::ContextCardKind::Media && ui.product.media.available) {
        drawText(r, f.small, ui.product.media.title, rgb(p.primary), 1200, 378, 0);
        drawText(r, f.tiny, ui.product.media.artist, rgb(p.secondary), 1200, 416, 0);
    } else {
        drawText(r, f.small, "Ready", rgb(p.primary), 1200, 378, 0);
        drawText(r, f.tiny, "No active context", rgb(p.secondary), 1200, 416, 0);
    }

    drawSafetyLayer(r, f, ui, p, true);
}

void renderMono(SDL_Renderer* r, const Fonts& f, UiRuntime& ui,
                const dashboard::ThemePalette& p, std::uint32_t dt) {
    const float speed = ui.motion.animate(
        dashboard::MotionChannel::Speed,
        ui.vehicle.speed.valid ? static_cast<float>(ui.vehicle.speed.value) : 0.0F, dt);
    drawText(r, f.tiny, "MONO", rgb(p.secondary), 150, 30, 0);
    drawStatusStrip(r, f, ui, p);
    drawText(r, f.medium, ui.vehicle.gear.valid ? dashboard::gearName(ui.vehicle.gear.value) : "--",
             rgb(p.secondary), 960, 88, 1);
    drawText(r, f.speed, ui.vehicle.speed.valid ? std::to_string(static_cast<int>(std::round(speed))) : "--",
             rgb(p.primary), 960, 215, 1);
    line(r, 820, 304, 1100, 304, rgb(p.panel_border));

    const dashboard::Signal<std::uint8_t>& soc = ui.vehicle.actual_soc.valid ? ui.vehicle.actual_soc : ui.vehicle.soc;
    drawText(r, f.medium, soc.valid ? std::to_string(soc.value) + "%" : "--%",
             rgb(p.primary), 610, 365, 1);
    drawText(r, f.medium, ui.vehicle.range.valid ? std::to_string(ui.vehicle.range.value) + " km" : "-- km",
             rgb(p.primary), 1310, 365, 1);

    bool closureOpen = false;
    const dashboard::Signal<bool>* closures[] = {
        &ui.vehicle.door_fl, &ui.vehicle.door_fr, &ui.vehicle.door_rl,
        &ui.vehicle.door_rr, &ui.vehicle.frunk, &ui.vehicle.trunk};
    for (const auto* s : closures) closureOpen = closureOpen || (s->valid && s->value);
    if (closureOpen) drawText(r, f.small, "CLOSURE OPEN", rgb(p.caution), 960, 418, 1);
    drawSafetyLayer(r, f, ui, p, true);
}

void renderPulse(SDL_Renderer* r, const Fonts& f, UiRuntime& ui,
                 const dashboard::ThemePalette& p, std::uint32_t dt) {
    (void)dt;
    drawText(r, f.tiny, "PULSE / PERFORMANCE", rgb(p.secondary), 150, 30, 0);
    drawStatusStrip(r, f, ui, p);

    drawText(r, f.tiny, "FRONT MOTOR", rgb(p.secondary), 270, 78, 1);
    drawText(r, f.medium, valueOrDash(ui.vehicle.front_motor_power, " kW"), rgb(p.primary), 270, 118, 1);
    drawText(r, f.tiny, "PACK POWER", rgb(p.secondary), 960, 78, 1);
    drawText(r, f.medium, valueOrDash(ui.vehicle.pack_power, " kW"), rgb(p.primary), 960, 118, 1);
    drawText(r, f.tiny, "REAR MOTOR", rgb(p.secondary), 1650, 78, 1);
    drawText(r, f.medium, valueOrDash(ui.vehicle.rear_motor_power, " kW"), rgb(p.primary), 1650, 118, 1);

    drawText(r, f.medium, ui.vehicle.gear.valid ? dashboard::gearName(ui.vehicle.gear.value) : "--",
             rgb(p.accent), 960, 166, 1);
    drawText(r, f.hero, ui.vehicle.speed.valid ? std::to_string(ui.vehicle.speed.value) : "--",
             rgb(p.primary), 960, 242, 1);
    drawText(r, f.tiny, "km/h", rgb(p.secondary), 960, 302, 1);

    line(r, 500, 340, 1420, 340, rgb(p.panel_border));
    line(r, 960, 328, 960, 352, rgb(p.secondary));
    drawText(r, f.tiny, "REGEN", rgb(p.secondary), 475, 340, 2);
    drawText(r, f.tiny, "POWER", rgb(p.secondary), 1445, 340, 0);
    if (ui.vehicle.pack_power.valid) {
        const float normalized = std::max(-1.0F, std::min(1.0F, ui.vehicle.pack_power.value / 180.0F));
        const int x = 960 + static_cast<int>(normalized * 420.0F);
        fillRounded(r, std::min(960, x), 336, std::max(5, std::abs(x - 960)), 8, 4,
                    normalized >= 0 ? rgb(p.accent) : rgb(p.success));
    }

    drawText(r, f.tiny, "ACCEL", rgb(p.secondary), 180, 385, 0);
    drawText(r, f.small, valueOrDash(ui.vehicle.accelerator_position, "%", 0), rgb(p.primary), 270, 385, 0);
    fillRounded(r, 180, 415, 320, 7, 3, rgb(p.panel_border));
    if (ui.vehicle.accelerator_position.valid) {
        const int w = static_cast<int>(3.2F * std::max(0.0F, std::min(100.0F, ui.vehicle.accelerator_position.value)));
        fillRounded(r, 180, 415, w, 7, 3, rgb(p.accent));
    }

    const dashboard::Signal<float>* brakes[] = {
        &ui.vehicle.brake_temp_fl, &ui.vehicle.brake_temp_fr,
        &ui.vehicle.brake_temp_rl, &ui.vehicle.brake_temp_rr};
    const char* labels[] = {"FL", "FR", "RL", "RR"};
    for (int i = 0; i < 4; ++i) {
        drawText(r, f.tiny, std::string(labels[i]) + " " + valueOrDash(*brakes[i], "°C", 0),
                 rgb(p.secondary), 690 + i * 180, 414, 1);
    }
    drawText(r, f.small, "0–100   --.-- s", rgb(p.primary), 1510, 400, 1);
    drawText(r, f.tiny, "READY", rgb(p.success), 1510, 430, 1);
    drawSafetyLayer(r, f, ui, p, false);
}

void renderRoute(SDL_Renderer* r, const Fonts& f, UiRuntime& ui,
                 const dashboard::ThemePalette& p) {
    drawText(r, f.tiny, "ROUTE", rgb(p.secondary), 150, 30, 0);
    drawStatusStrip(r, f, ui, p);
    const auto& n = ui.product.navigation;
    drawText(r, f.hero, n.active ? n.next_turn : "—", n.active ? rgb(p.primary) : rgb(p.secondary), 220, 110, 1);
    drawText(r, f.medium,
             n.active ? std::to_string(static_cast<int>(n.distance_to_turn_km * 1000.0F)) + " m" : "-- m",
             rgb(p.primary), 340, 95, 0);
    drawText(r, f.small, n.active ? n.road_name : "Navigation unavailable", rgb(p.secondary), 340, 137, 0);

    fillRounded(r, 260, 175, 960, 220, 24, rgb(p.panel));
    // Low-cost route strip: no map engine, only route polyline and progress.
    line(r, 340, 320, 520, 320, rgb(p.panel_border));
    line(r, 520, 320, 520, 255, rgb(p.panel_border));
    line(r, 520, 255, 750, 255, rgb(p.panel_border));
    line(r, 750, 255, 750, 215, rgb(p.panel_border));
    line(r, 750, 215, 1090, 215, rgb(p.accent));
    fillRounded(r, 500, 300, 40, 40, 20, rgb(p.accent));
    fillRounded(r, 1070, 195, 40, 40, 20, rgb(p.success));
    drawText(r, f.tiny, "YOU", rgb(p.primary), 520, 363, 1);
    drawText(r, f.tiny, "DEST", rgb(p.primary), 1090, 255, 1);

    fillRounded(r, 1290, 150, 430, 250, 24, rgb(p.panel));
    drawText(r, f.hero, n.active ? std::to_string(n.remaining_minutes) : "--", rgb(p.primary), 1505, 206, 1);
    drawText(r, f.small, "min", rgb(p.secondary), 1570, 206, 0);
    char remaining[64];
    std::snprintf(remaining, sizeof(remaining), "%.1f km", n.active ? n.remaining_distance_km : 0.0F);
    drawText(r, f.medium, n.active ? remaining : "-- km", rgb(p.primary), 1505, 280, 1);
    drawText(r, f.small, n.active ? "ETA " + n.eta_text : "ETA --:--", rgb(p.secondary), 1505, 330, 1);
    if (n.active && n.arrive_soc_percent >= 0)
        drawText(r, f.tiny, "Arrive " + std::to_string(n.arrive_soc_percent) + "%", rgb(p.secondary), 1505, 367, 1);
    if (n.active && n.traffic_delay_minutes > 0)
        drawText(r, f.tiny, "+" + std::to_string(n.traffic_delay_minutes) + " min traffic", rgb(p.caution), 1505, 392, 1);
    drawSafetyLayer(r, f, ui, p, false);
}

void renderStudio(SDL_Renderer* r, const Fonts& f, UiRuntime& ui,
                  const dashboard::ThemePalette& p) {
    drawText(r, f.tiny, "STUDIO", rgb(p.secondary), 150, 30, 0);
    drawStatusStrip(r, f, ui, p);
    fillRounded(r, 180, 105, 260, 260, 22, rgb(p.panel_border));
    fillRounded(r, 196, 121, 228, 228, 18, rgb(p.panel));
    drawText(r, f.medium, "ALBUM", rgb(p.secondary), 310, 235, 1);

    const auto& m = ui.product.media;
    drawText(r, f.title, m.available ? m.title : "No media", rgb(p.primary), 515, 112, 0);
    drawText(r, f.small, m.available ? m.artist : "PhoneBridge offline", rgb(p.secondary), 515, 158, 0);

    std::string previous = "";
    std::string current = ui.product.lyrics.matching ? "Matching lyrics…" : "Lyrics unavailable";
    std::string next = "";
    if (ui.product.lyrics.available && ui.product.lyrics.current_index >= 0 &&
        ui.product.lyrics.current_index < static_cast<int>(ui.product.lyrics.lines.size())) {
        const int i = ui.product.lyrics.current_index;
        current = ui.product.lyrics.lines[i].text;
        if (i > 0) previous = ui.product.lyrics.lines[i - 1].text;
        if (i + 1 < static_cast<int>(ui.product.lyrics.lines.size())) next = ui.product.lyrics.lines[i + 1].text;
    }
    drawText(r, f.small, previous, rgb(p.secondary, 130), 1110, 218, 1);
    drawText(r, f.title, current, rgb(p.primary), 1110, 270, 1);
    drawText(r, f.small, next, rgb(p.secondary, 130), 1110, 324, 1);

    fillRounded(r, 520, 392, 980, 5, 2, rgb(p.panel_border));
    if (m.available && m.duration_ms > 0) {
        const float progress = static_cast<float>(std::min(m.position_ms, m.duration_ms)) /
                               static_cast<float>(m.duration_ms);
        fillRounded(r, 520, 392, static_cast<int>(980.0F * progress), 5, 2, rgb(p.accent));
    }
    drawText(r, f.small, "◀    ▶/Ⅱ    ▶", rgb(p.primary), 620, 430, 0);
    const int offset = ui.product.lyrics.offset_ms;
    char offsetText[48];
    std::snprintf(offsetText, sizeof(offsetText), "Lyrics %+0.1fs", offset / 1000.0F);
    drawText(r, f.tiny, offsetText, rgb(p.secondary), 1430, 430, 2);
    drawSafetyLayer(r, f, ui, p, false);
}

void renderEnergy(SDL_Renderer* r, const Fonts& f, UiRuntime& ui,
                  const dashboard::ThemePalette& p) {
    drawText(r, f.tiny, "ENERGY / BMS", rgb(p.secondary), 150, 30, 0);
    drawStatusStrip(r, f, ui, p);

    drawText(r, f.small, "BATTERY", rgb(p.secondary), 280, 92, 1);
    drawText(r, f.medium, valueOrDash(ui.vehicle.pack_voltage, " V"), rgb(p.primary), 280, 145, 1);
    drawText(r, f.medium, valueOrDash(ui.vehicle.pack_current, " A"), rgb(p.primary), 280, 200, 1);
    drawText(r, f.medium, valueOrDash(ui.vehicle.pack_power, " kW"), rgb(p.primary), 280, 255, 1);
    drawText(r, f.small, "Actual SOC  " + uintOrDash(ui.vehicle.actual_soc, "%"), rgb(p.primary), 280, 325, 1);
    drawText(r, f.tiny, "Remaining  " + valueOrDash(ui.vehicle.energy_remaining, " kWh"), rgb(p.secondary), 280, 365, 1);

    drawText(r, f.small, "POWER FLOW", rgb(p.secondary), 850, 92, 1);
    fillRounded(r, 700, 160, 300, 74, 18, rgb(p.panel));
    drawText(r, f.small, "BATTERY", rgb(p.primary), 850, 197, 1);
    fillRounded(r, 1080, 125, 280, 68, 16, rgb(p.panel));
    fillRounded(r, 1080, 245, 280, 68, 16, rgb(p.panel));
    drawText(r, f.small, "FRONT MOTOR", rgb(p.primary), 1220, 159, 1);
    drawText(r, f.small, "REAR MOTOR", rgb(p.primary), 1220, 279, 1);
    line(r, 1000, 187, 1080, 159, rgb(ui.vehicle.pack_power.valid && ui.vehicle.pack_power.value < 0 ? p.success : p.accent));
    line(r, 1000, 207, 1080, 279, rgb(ui.vehicle.pack_power.valid && ui.vehicle.pack_power.value < 0 ? p.success : p.accent));

    drawText(r, f.small, "BMS", rgb(p.secondary), 1590, 92, 1);
    drawText(r, f.medium, "Max  " + valueOrDash(ui.vehicle.max_cell_voltage, " V", 1), rgb(p.primary), 1590, 145, 1);
    drawText(r, f.medium, "Min  " + valueOrDash(ui.vehicle.min_cell_voltage, " V", 1), rgb(p.primary), 1590, 200, 1);
    drawText(r, f.medium, "Δ  " + valueOrDash(ui.vehicle.cell_delta, " V", 1), rgb(p.primary), 1590, 255, 1);
    drawText(r, f.small, "Temp  " + valueOrDash(ui.vehicle.battery_temperature, "°C", 0), rgb(p.primary), 1590, 325, 1);

    // Cell deviation preview. Without Commander this intentionally stays empty.
    for (int i = 0; i < 28; ++i) {
        const int x = 1390 + i * 13;
        const int h = ui.commander_demo ? 18 + ((i * 7) % 34) : 4;
        fillRect(r, x, 390 - h, 7, h, ui.commander_demo ? rgb(p.accent) : rgb(p.panel_border));
    }
    drawSafetyLayer(r, f, ui, p, false);
}

void renderNocturne(SDL_Renderer* r, const Fonts& f, UiRuntime& ui,
                    const dashboard::ThemePalette& p, std::uint32_t dt) {
    (void)p;
    dashboard::ThemePalette night = p;
    night.background = 0x020304;
    night.panel = 0x080B0E;
    night.panel_border = 0x111820;
    night.secondary = 0x69737D;
    fillRect(r, 0, 0, kWidth, kHeight, rgb(night.background));
    const float speed = ui.motion.animate(
        dashboard::MotionChannel::Speed,
        ui.vehicle.speed.valid ? static_cast<float>(ui.vehicle.speed.value) : 0.0F, dt);
    drawText(r, f.tiny, "NOCTURNE", rgb(night.secondary), 150, 30, 0);
    drawText(r, f.medium, ui.vehicle.gear.valid ? dashboard::gearName(ui.vehicle.gear.value) : "--",
             rgb(night.secondary), 960, 102, 1);
    drawText(r, f.speed, ui.vehicle.speed.valid ? std::to_string(static_cast<int>(std::round(speed))) : "--",
             rgb(night.primary), 960, 220, 1);
    line(r, 500, 305, 800, 305, rgb(night.panel_border));
    line(r, 1120, 305, 1420, 305, rgb(night.panel_border));
    line(r, 800, 305, 900, 337, rgb(night.panel_border));
    line(r, 1120, 305, 1020, 337, rgb(night.panel_border));

    const dashboard::Signal<std::uint8_t>& soc = ui.vehicle.actual_soc.valid ? ui.vehicle.actual_soc : ui.vehicle.soc;
    drawText(r, f.medium, soc.valid ? std::to_string(soc.value) + "%" : "--%",
             rgb(night.primary), 570, 385, 1);
    drawText(r, f.medium, ui.vehicle.range.valid ? std::to_string(ui.vehicle.range.value) + " km" : "-- km",
             rgb(night.primary), 1350, 385, 1);
    if (ui.product.navigation.active) {
        char turn[128];
        std::snprintf(turn, sizeof(turn), "Next turn %.1f km", ui.product.navigation.distance_to_turn_km);
        drawText(r, f.small, turn, rgb(night.secondary), 960, 420, 1);
    }
    drawSafetyLayer(r, f, ui, night, true);
}

void renderPage(SDL_Renderer* r, const Fonts& f, UiRuntime& ui, std::uint32_t dt) {
    const bool night = ui.pages.page() == dashboard::DashboardPage::Nocturne;
    const dashboard::ThemePalette p = ui.themes.palette(night);
    fillRect(r, 0, 0, kWidth, kHeight, rgb(p.background));

    switch (ui.pages.page()) {
        case dashboard::DashboardPage::Horizon: renderHorizon(r, f, ui, p, dt); break;
        case dashboard::DashboardPage::Mono: renderMono(r, f, ui, p, dt); break;
        case dashboard::DashboardPage::Pulse: renderPulse(r, f, ui, p, dt); break;
        case dashboard::DashboardPage::Route: renderRoute(r, f, ui, p); break;
        case dashboard::DashboardPage::Studio: renderStudio(r, f, ui, p); break;
        case dashboard::DashboardPage::Energy: renderEnergy(r, f, ui, p); break;
        case dashboard::DashboardPage::Nocturne: renderNocturne(r, f, ui, p, dt); break;
    }
    drawPageIndicator(r, ui.pages.page(), p);
    drawTrapezoidMask(r);
}

void seedProduct(UiRuntime& ui) {
    ui.product.weather.available = true;
    ui.product.weather.location = "Toronto";
    ui.product.weather.current_temperature_c = 18.0F;
    ui.product.weather.condition = "Cloudy";
    ui.product.weather.high_c = 22.0F;
    ui.product.weather.low_c = 14.0F;

    ui.product.phone.available = true;
    ui.product.phone.battery_percent = 82;
    ui.product.phone.network_label = "LTE";

    ui.product.commander.available = true;
    ui.product.commander.connected = false;

    ui.product.media.available = true;
    ui.product.media.playing = true;
    ui.product.media.track_id = "demo-track";
    ui.product.media.title = "Midnight Drive";
    ui.product.media.artist = "Dashboard Studio";
    ui.product.media.duration_ms = 227000;
    ui.product.media.position_ms = 134000;

    ui.product.lyrics.available = true;
    ui.product.lyrics.track_id = "demo-track";
    ui.product.lyrics.lines = {
        {120000, "City lights disappear behind us"},
        {132000, "Every mile becomes a memory"},
        {145000, "Keep the horizon in your sight"}};
    ui.product.lyrics.current_index = 1;

    ui.product.navigation.active = true;
    ui.product.navigation.next_turn = "↰";
    ui.product.navigation.road_name = "Don Mills Rd";
    ui.product.navigation.distance_to_turn_km = 0.8F;
    ui.product.navigation.remaining_minutes = 22;
    ui.product.navigation.remaining_distance_km = 18.4F;
    ui.product.navigation.eta_text = "19:06";
    ui.product.navigation.arrive_soc_percent = 41;
    ui.product.navigation.traffic_delay_minutes = 4;
}

void updateVehicle(UiRuntime& ui, std::uint64_t now) {
    dashboard::SimulationAdapter sim;
    sim.setDriving(ui.speed, ui.gear, 68, 284, now);
    sim.setDoors(ui.door_open, false, false, false, false, false, now);
    sim.setTires(2.9F, 2.9F, 2.8F, 2.9F, now);
    ui.vehicle = sim.state();
    ui.vehicle.temperature_primary.update(18, now, dashboard::SignalSource::Simulation,
                                          dashboard::SignalQuality::Confirmed, dashboard::Unit::Celsius);
    ui.vehicle.turn_signal_left.update(ui.left_signal, now, dashboard::SignalSource::Simulation,
                                       dashboard::SignalQuality::Confirmed, dashboard::Unit::None);
    ui.vehicle.turn_signal_right.update(ui.right_signal, now, dashboard::SignalSource::Simulation,
                                        dashboard::SignalQuality::Confirmed, dashboard::Unit::None);

    if (ui.commander_demo) {
        ui.product.commander.connected = true;
        ui.vehicle.actual_soc.update(67, now, dashboard::SignalSource::Simulation,
                                     dashboard::SignalQuality::Confirmed, dashboard::Unit::Percent);
        ui.vehicle.front_motor_power.update(42.0F, now, dashboard::SignalSource::Simulation,
                                            dashboard::SignalQuality::Confirmed, dashboard::Unit::Raw);
        ui.vehicle.rear_motor_power.update(84.0F, now, dashboard::SignalSource::Simulation,
                                           dashboard::SignalQuality::Confirmed, dashboard::Unit::Raw);
        ui.vehicle.total_motor_power.update(126.0F, now, dashboard::SignalSource::Simulation,
                                            dashboard::SignalQuality::Confirmed, dashboard::Unit::Raw);
        ui.vehicle.pack_voltage.update(354.7F, now, dashboard::SignalSource::Simulation,
                                       dashboard::SignalQuality::Confirmed, dashboard::Unit::Raw);
        ui.vehicle.pack_current.update(86.4F, now, dashboard::SignalSource::Simulation,
                                       dashboard::SignalQuality::Confirmed, dashboard::Unit::Raw);
        ui.vehicle.pack_power.update(30.6F, now, dashboard::SignalSource::Simulation,
                                     dashboard::SignalQuality::Confirmed, dashboard::Unit::Raw);
        ui.vehicle.energy_remaining.update(51.2F, now, dashboard::SignalSource::Simulation,
                                           dashboard::SignalQuality::Confirmed, dashboard::Unit::Raw);
        ui.vehicle.accelerator_position.update(64.0F, now, dashboard::SignalSource::Simulation,
                                               dashboard::SignalQuality::Confirmed, dashboard::Unit::Percent);
        ui.vehicle.brake_temp_fl.update(73.0F, now, dashboard::SignalSource::Simulation,
                                        dashboard::SignalQuality::Confirmed, dashboard::Unit::Celsius);
        ui.vehicle.brake_temp_fr.update(76.0F, now, dashboard::SignalSource::Simulation,
                                        dashboard::SignalQuality::Confirmed, dashboard::Unit::Celsius);
        ui.vehicle.brake_temp_rl.update(61.0F, now, dashboard::SignalSource::Simulation,
                                        dashboard::SignalQuality::Confirmed, dashboard::Unit::Celsius);
        ui.vehicle.brake_temp_rr.update(63.0F, now, dashboard::SignalSource::Simulation,
                                        dashboard::SignalQuality::Confirmed, dashboard::Unit::Celsius);
        ui.vehicle.battery_temperature.update(29.0F, now, dashboard::SignalSource::Simulation,
                                              dashboard::SignalQuality::Confirmed, dashboard::Unit::Celsius);
        ui.vehicle.max_cell_voltage.update(4.137F, now, dashboard::SignalSource::Simulation,
                                           dashboard::SignalQuality::Confirmed, dashboard::Unit::Raw);
        ui.vehicle.min_cell_voltage.update(4.119F, now, dashboard::SignalSource::Simulation,
                                           dashboard::SignalQuality::Confirmed, dashboard::Unit::Raw);
        ui.vehicle.cell_delta.update(0.018F, now, dashboard::SignalSource::Simulation,
                                     dashboard::SignalQuality::Confirmed, dashboard::Unit::Raw);
    } else {
        ui.product.commander.connected = false;
    }
}

bool saveScreenshot(SDL_Renderer* r, const char* path) {
    SDL_Surface* surface = SDL_CreateRGBSurfaceWithFormat(0, kWidth, kHeight, 32, SDL_PIXELFORMAT_RGBA32);
    if (!surface) return false;
    const int rc = SDL_RenderReadPixels(r, nullptr, SDL_PIXELFORMAT_RGBA32,
                                        surface->pixels, surface->pitch);
    bool ok = rc == 0 && SDL_SaveBMP(surface, path) == 0;
    SDL_FreeSurface(surface);
    return ok;
}

TTF_Font* openFont(const char* path, int size) {
    return TTF_OpenFontIndex(path, size, 0);
}

void closeFonts(Fonts& f) {
    if (f.hero) TTF_CloseFont(f.hero);
    if (f.speed) TTF_CloseFont(f.speed);
    if (f.title) TTF_CloseFont(f.title);
    if (f.medium) TTF_CloseFont(f.medium);
    if (f.small) TTF_CloseFont(f.small);
    if (f.tiny) TTF_CloseFont(f.tiny);
}

}  // namespace

int main(int argc, char** argv) {
    bool screenshot = false;
    bool all_pages = false;
    const char* screenshot_path = "/tmp/tesla-dashboard-product.bmp";
    int initial_page = 1;
    for (int i = 1; i < argc; ++i) {
        if (std::strcmp(argv[i], "--screenshot") == 0) {
            screenshot = true;
            if (i + 1 < argc && argv[i + 1][0] != '-') screenshot_path = argv[++i];
        } else if (std::strcmp(argv[i], "--all-pages") == 0) {
            all_pages = true;
        } else if (std::strcmp(argv[i], "--page") == 0 && i + 1 < argc) {
            initial_page = std::max(1, std::min(7, std::atoi(argv[++i])));
        }
    }

    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_TIMER) != 0 || TTF_Init() != 0) {
        std::fprintf(stderr, "SDL/TTF init failed: %s\n", SDL_GetError());
        return 1;
    }
    SDL_Window* window = SDL_CreateWindow("Tesla Dashboard Product Simulator",
        SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED, kWidth, kHeight,
        SDL_WINDOW_RESIZABLE | (screenshot ? SDL_WINDOW_HIDDEN : 0));
    if (!window) return 1;
    SDL_Renderer* renderer = SDL_CreateRenderer(window, -1,
        screenshot ? SDL_RENDERER_SOFTWARE : (SDL_RENDERER_ACCELERATED | SDL_RENDERER_PRESENTVSYNC));
    if (!renderer) return 1;
    SDL_RenderSetLogicalSize(renderer, kWidth, kHeight);

    const char* fontPath = std::getenv("DASHBOARD_FONT");
    if (!fontPath || !*fontPath) fontPath = kDefaultFont;
    Fonts f;
    f.hero = openFont(fontPath, 96);
    f.speed = openFont(fontPath, 154);
    f.title = openFont(fontPath, 48);
    f.medium = openFont(fontPath, 38);
    f.small = openFont(fontPath, 28);
    f.tiny = openFont(fontPath, 20);
    if (!f.hero || !f.speed || !f.title || !f.medium || !f.small || !f.tiny) {
        std::fprintf(stderr, "Font open failed: %s\n", TTF_GetError());
        closeFonts(f);
        return 1;
    }

    UiRuntime ui;
    ui.themes.setTheme(dashboard::DashboardTheme::Dark);
    ui.pages.setPage(static_cast<dashboard::DashboardPage>(initial_page - 1));
    seedProduct(ui);
    ui.safety.vehicle_link_connected = true;
    ui.safety.vehicle_link_has_data = true;

    bool running = true;
    std::uint32_t previous = SDL_GetTicks();
    int allPageIndex = 0;
    while (running) {
        SDL_Event e;
        while (SDL_PollEvent(&e)) {
            if (e.type == SDL_QUIT) running = false;
            if (e.type == SDL_KEYDOWN) {
                switch (e.key.keysym.sym) {
                    case SDLK_ESCAPE: running = false; break;
                    case SDLK_LEFT: ui.pages.previous(); break;
                    case SDLK_RIGHT: ui.pages.next(); break;
                    case SDLK_t: {
                        const auto current = ui.themes.theme();
                        ui.themes.setTheme(current == dashboard::DashboardTheme::Dark
                            ? dashboard::DashboardTheme::Graphite
                            : current == dashboard::DashboardTheme::Graphite
                                ? dashboard::DashboardTheme::Light
                                : dashboard::DashboardTheme::Dark);
                        break;
                    }
                    case SDLK_m: ui.motion.setEnabled(!ui.motion.enabled()); break;
                    case SDLK_c: ui.commander_demo = !ui.commander_demo; break;
                    case SDLK_l: ui.left_signal = !ui.left_signal; break;
                    case SDLK_r: ui.right_signal = !ui.right_signal; break;
                    case SDLK_o: ui.door_open = !ui.door_open; break;
                    case SDLK_UP: ui.speed = static_cast<std::uint16_t>(std::min(240, static_cast<int>(ui.speed) + 5)); break;
                    case SDLK_DOWN: ui.speed = static_cast<std::uint16_t>(std::max(0, static_cast<int>(ui.speed) - 5)); break;
                    case SDLK_1: ui.pages.setPage(dashboard::DashboardPage::Horizon); break;
                    case SDLK_2: ui.pages.setPage(dashboard::DashboardPage::Mono); break;
                    case SDLK_3: ui.pages.setPage(dashboard::DashboardPage::Pulse); break;
                    case SDLK_4: ui.pages.setPage(dashboard::DashboardPage::Route); break;
                    case SDLK_5: ui.pages.setPage(dashboard::DashboardPage::Studio); break;
                    case SDLK_6: ui.pages.setPage(dashboard::DashboardPage::Energy); break;
                    case SDLK_7: ui.pages.setPage(dashboard::DashboardPage::Nocturne); break;
                    default: break;
                }
            }
        }

        const std::uint32_t now = SDL_GetTicks();
        const std::uint32_t dt = std::min<std::uint32_t>(100, now - previous);
        previous = now;
        updateVehicle(ui, now);
        ui.safety.vehicle_link_age_ms = 0;
        ui.warnings.evaluate(ui.vehicle, ui.safety);
        ui.pages.tick(dt, ui.motion.enabled());
        renderPage(renderer, f, ui, dt);
        SDL_RenderPresent(renderer);

        if (screenshot) {
            if (all_pages) {
                char path[512];
                std::snprintf(path, sizeof(path), "%s-page-%d.bmp", screenshot_path, allPageIndex + 1);
                if (!saveScreenshot(renderer, path)) std::fprintf(stderr, "screenshot failed: %s\n", path);
                ++allPageIndex;
                if (allPageIndex >= 7) running = false;
                else ui.pages.setPage(static_cast<dashboard::DashboardPage>(allPageIndex));
            } else {
                if (!saveScreenshot(renderer, screenshot_path)) std::fprintf(stderr, "screenshot failed\n");
                running = false;
            }
        } else {
            SDL_Delay(kFrameMs);
        }
    }

    closeFonts(f);
    SDL_DestroyRenderer(renderer);
    SDL_DestroyWindow(window);
    TTF_Quit();
    SDL_Quit();
    return 0;
}
