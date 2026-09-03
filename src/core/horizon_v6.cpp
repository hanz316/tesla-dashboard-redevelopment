#include "dashboard/horizon_v6.h"

#include <algorithm>
#include <cmath>
#include <cstdio>

namespace dashboard {

namespace {

RenderColor rgba(std::uint8_t r, std::uint8_t g, std::uint8_t b, std::uint8_t a = 255) {
    return {r, g, b, a};
}

std::string formatUInt(std::uint32_t value) {
    char buffer[24];
    std::snprintf(buffer, sizeof(buffer), "%u", static_cast<unsigned>(value));
    return buffer;
}

std::string formatFloat1(float value) {
    char buffer[32];
    std::snprintf(buffer, sizeof(buffer), "%.1f", static_cast<double>(value));
    return buffer;
}

}  // namespace

RenderCommand HorizonRendererV6::image(const char* id, const char* asset, std::int16_t z,
                                       float x, float y, float w, float h, float opacity) {
    RenderCommand c;
    c.type = RenderCommandType::Image;
    c.id = id;
    c.asset_id = asset;
    c.z = z;
    c.rect = {x, y, w, h};
    c.transform.opacity = opacity;
    return c;
}

RenderCommand HorizonRendererV6::text(const char* id, const std::string& value, std::int16_t z,
                                      float x, float y, float w, float h, std::uint16_t font_px,
                                      RenderColor color, TextAlign align, bool bold) {
    RenderCommand c;
    c.type = RenderCommandType::Text;
    c.id = id;
    c.text = value;
    c.z = z;
    c.rect = {x, y, w, h};
    c.font_px = font_px;
    c.color = color;
    c.text_align = align;
    c.bold = bold;
    return c;
}

RenderCommand HorizonRendererV6::solid(const char* id, std::int16_t z, float x, float y,
                                       float w, float h, RenderColor color) {
    RenderCommand c;
    c.type = RenderCommandType::SolidRect;
    c.id = id;
    c.z = z;
    c.rect = {x, y, w, h};
    c.color = color;
    return c;
}

RenderCommand HorizonRendererV6::line(const char* id, std::int16_t z, float x, float y,
                                      float w, float h, RenderColor color) {
    RenderCommand c;
    c.type = RenderCommandType::Line;
    c.id = id;
    c.z = z;
    c.rect = {x, y, w, h};
    c.color = color;
    return c;
}

void HorizonRendererV6::appendEnvironment(RenderFrameV6& frame, const HorizonSceneState& scene,
                                          float ap_alpha, float blind_left, float blind_right) const {
    frame.commands.push_back(image("horizon.background", "horizon.environment.base", 0,
                                   0, 0, 1920, 480, 1.0F));
    frame.commands.push_back(image("horizon.road", "horizon.road.surface", 10,
                                   420, 118, 1080, 362, 1.0F));
    frame.commands.push_back(image("horizon.lanes", "horizon.road.lanes", 20,
                                   420, 118, 1080, 362, 0.88F));

    if (ap_alpha > 0.001F) {
        frame.commands.push_back(image("horizon.ap_corridor", "horizon.ap.corridor", 24,
                                       572, 128, 776, 352, ap_alpha));
    }
    if (blind_left > 0.001F) {
        frame.commands.push_back(image("horizon.blind_left", "horizon.blind.left", 26,
                                       450, 214, 270, 210, blind_left));
    }
    if (blind_right > 0.001F) {
        frame.commands.push_back(image("horizon.blind_right", "horizon.blind.right", 26,
                                       1200, 214, 270, 210, blind_right));
    }

    // Coarse slots are intentionally fixed zones. They do not imply exact position/distance.
    if (scene.surrounding.front) {
        frame.commands.push_back(image("horizon.surround.front", "horizon.vehicle.coarse.front", 30,
                                       888, 158, 144, 96, 0.78F));
    }
    if (scene.surrounding.left) {
        frame.commands.push_back(image("horizon.surround.left", "horizon.vehicle.coarse.left", 30,
                                       610, 248, 156, 104, 0.66F));
    }
    if (scene.surrounding.right) {
        frame.commands.push_back(image("horizon.surround.right", "horizon.vehicle.coarse.right", 30,
                                       1154, 248, 156, 104, 0.66F));
    }
}

void HorizonRendererV6::appendVehicle(RenderFrameV6& frame, const HorizonSceneState& scene,
                                      float light_alpha, float energy_halo_alpha) const {
    frame.commands.push_back(image("vehicle.shadow", "vehicle.shadow", 40,
                                   762, 286, 396, 162, 0.70F));
    if (std::fabs(energy_halo_alpha) > 0.01F) {
        const char* halo_asset = energy_halo_alpha >= 0.0F
            ? "vehicle.energy.drive" : "vehicle.energy.regen";
        frame.commands.push_back(image("vehicle.energy_halo", halo_asset, 42,
                                       748, 278, 424, 180,
                                       std::min(0.34F, std::fabs(energy_halo_alpha) * 0.34F)));
    }
    frame.commands.push_back(image("vehicle.body", "vehicle.body", 50,
                                   782, 202, 356, 236, 1.0F));
    frame.commands.push_back(image("vehicle.glass", "vehicle.glass", 52,
                                   782, 202, 356, 236, 1.0F));
    frame.commands.push_back(image("vehicle.roof", "vehicle.roof", 53,
                                   782, 202, 356, 236, 1.0F));

    if (scene.vehicle.headlights) {
        frame.commands.push_back(image("vehicle.front_lights", "vehicle.front_lights", 58,
                                       782, 202, 356, 236, std::max(0.55F, light_alpha)));
    }
    if (scene.vehicle.high_beam) {
        frame.commands.push_back(image("vehicle.high_beam", "vehicle.high_beam", 59,
                                       700, 124, 520, 316, std::max(0.55F, light_alpha)));
    }
    if (scene.vehicle.brake_lights) {
        frame.commands.push_back(image("vehicle.brake_lights", "vehicle.brake_lights", 59,
                                       782, 202, 356, 236, 1.0F));
    }
    if (scene.vehicle.left_indicator) {
        frame.commands.push_back(image("vehicle.left_indicator", "vehicle.indicator.left", 60,
                                       782, 202, 356, 236, 1.0F));
    }
    if (scene.vehicle.right_indicator) {
        frame.commands.push_back(image("vehicle.right_indicator", "vehicle.indicator.right", 60,
                                       782, 202, 356, 236, 1.0F));
    }

    if (scene.vehicle.door_fl) frame.commands.push_back(image("vehicle.door_fl", "vehicle.door.fl", 62, 782, 202, 356, 236));
    if (scene.vehicle.door_fr) frame.commands.push_back(image("vehicle.door_fr", "vehicle.door.fr", 62, 782, 202, 356, 236));
    if (scene.vehicle.door_rl) frame.commands.push_back(image("vehicle.door_rl", "vehicle.door.rl", 62, 782, 202, 356, 236));
    if (scene.vehicle.door_rr) frame.commands.push_back(image("vehicle.door_rr", "vehicle.door.rr", 62, 782, 202, 356, 236));
    if (scene.vehicle.frunk) frame.commands.push_back(image("vehicle.frunk", "vehicle.frunk", 62, 782, 202, 356, 236));
    if (scene.vehicle.trunk) frame.commands.push_back(image("vehicle.trunk", "vehicle.trunk", 62, 782, 202, 356, 236));
}

void HorizonRendererV6::appendPrimaryData(RenderFrameV6& frame, const HorizonSceneState& scene,
                                          float display_speed, float display_soc) const {
    const RenderColor primary = rgba(238, 242, 244);
    const RenderColor secondary = rgba(147, 160, 168);
    const RenderColor muted = rgba(94, 108, 116);

    frame.commands.push_back(text("speed.value",
                                  scene.speed_available ? formatUInt(static_cast<std::uint32_t>(std::lround(display_speed))) : "--",
                                  80, 178, 104, 280, 148, 126, primary, TextAlign::Center, true));
    frame.commands.push_back(text("speed.unit", "km/h", 80, 178, 244, 280, 32, 22,
                                  secondary, TextAlign::Center));
    frame.commands.push_back(text("gear.value", scene.gear_available ? gearName(scene.gear) : "--", 81,
                                  178, 286, 280, 44, 34, primary, TextAlign::Center, true));

    frame.commands.push_back(text("battery.soc",
                                  scene.soc_available ? formatUInt(static_cast<std::uint32_t>(std::lround(display_soc))) + "%" : "--",
                                  80, 1468, 88, 260, 72, 50, primary, TextAlign::Left, true));
    if (scene.range_available) {
        frame.commands.push_back(text("battery.range", formatUInt(scene.range) + " km", 80,
                                      1468, 156, 260, 40, 23, secondary, TextAlign::Left));
    }
    frame.commands.push_back(text("battery.label", "BATTERY", 80,
                                  1468, 58, 260, 28, 15, muted, TextAlign::Left, true));
}

void HorizonRendererV6::appendContextRail(RenderFrameV6& frame, const HorizonContextRailState& rail) const {
    const RenderColor primary = rgba(233, 238, 240);
    const RenderColor secondary = rgba(144, 157, 164);
    const RenderColor muted = rgba(91, 105, 113);
    frame.commands.push_back(image("context.glass", "horizon.context.glass", 70,
                                   1418, 36, 360, 372, 0.92F));

    if (rail.mode == HorizonContextRailState::Mode::Navigation && rail.navigation) {
        const NavigationState& nav = *rail.navigation;
        frame.commands.push_back(text("context.nav.label", "NAVIGATION", 76,
                                      1466, 208, 260, 24, 15, muted, TextAlign::Left, true));
        if (nav.next_turn_distance_m.valid && !nav.next_turn_distance_m.stale) {
            const float meters = nav.next_turn_distance_m.value;
            std::string distance = meters >= 1000.0F
                ? formatFloat1(meters / 1000.0F) + " km"
                : formatUInt(static_cast<std::uint32_t>(std::lround(meters))) + " m";
            frame.commands.push_back(text("context.nav.distance", distance, 78,
                                          1466, 240, 250, 44, 30, primary, TextAlign::Left, true));
        }
        if (!nav.road_name.empty()) {
            frame.commands.push_back(text("context.nav.road", nav.road_name, 78,
                                          1466, 282, 274, 36, 21, secondary, TextAlign::Left));
        }
        if (nav.has(NavigationCapability::TripMetrics)) {
            if (nav.remaining_time_s.valid && !nav.remaining_time_s.stale) {
                frame.commands.push_back(text("context.nav.time",
                                              formatUInt(nav.remaining_time_s.value / 60U) + " min", 78,
                                              1466, 330, 110, 30, 17, secondary, TextAlign::Left));
            }
            if (nav.remaining_distance_km.valid && !nav.remaining_distance_km.stale) {
                frame.commands.push_back(text("context.nav.remaining",
                                              formatFloat1(nav.remaining_distance_km.value) + " km", 78,
                                              1580, 330, 130, 30, 17, secondary, TextAlign::Left));
            }
        }
        return;
    }

    if (rail.mode == HorizonContextRailState::Mode::Trip) {
        frame.commands.push_back(text("context.trip.label", "TRIP", 76,
                                      1466, 208, 260, 24, 15, muted, TextAlign::Left, true));
        if (rail.trip_distance_available) {
            frame.commands.push_back(text("context.trip.distance", formatFloat1(rail.trip_distance_km) + " km", 78,
                                          1466, 244, 250, 42, 28, primary, TextAlign::Left, true));
        }
        if (rail.trip_duration_available) {
            frame.commands.push_back(text("context.trip.duration",
                                          formatUInt(static_cast<std::uint32_t>(rail.trip_duration_ms / 60000ULL)) + " min", 78,
                                          1466, 292, 120, 30, 17, secondary, TextAlign::Left));
        }
        if (rail.trip_avg_speed_available) {
            frame.commands.push_back(text("context.trip.avg", formatFloat1(rail.trip_avg_speed_kph) + " km/h avg", 78,
                                          1466, 328, 230, 30, 17, secondary, TextAlign::Left));
        }
        return;
    }

    if (rail.mode == HorizonContextRailState::Mode::Battery) {
        frame.commands.push_back(text("context.battery.label", "RANGE", 76,
                                      1466, 208, 260, 24, 15, muted, TextAlign::Left, true));
        if (rail.range_available) {
            frame.commands.push_back(text("context.battery.range", formatUInt(rail.range_km) + " km", 78,
                                          1466, 244, 250, 42, 28, primary, TextAlign::Left, true));
        }
    }
}

void HorizonRendererV6::appendSafety(RenderFrameV6& frame, const SafetyLayerV6& safety) const {
    frame.commands.push_back(line("safety.divider", 100, 86, 410, 1748, 1, rgba(46, 58, 65, 210)));

    if (safety.left_indicator) {
        frame.commands.push_back(image("safety.turn.left", "shared.turn.left", 110,
                                       106, 198, 48, 84, 1.0F));
    }
    if (safety.right_indicator) {
        frame.commands.push_back(image("safety.turn.right", "shared.turn.right", 110,
                                       1766, 198, 48, 84, 1.0F));
    }

    if (!safety.warning.active) return;
    if (safety.warning.severity == WarningSeverity::Critical) {
        frame.commands.push_back(image("warning.critical.backdrop", "shared.warning.critical_backdrop", 180,
                                       0, 0, 1920, 480, 0.96F));
        frame.commands.push_back(text("warning.critical.title", "VEHICLE DATA LOST", 190,
                                      550, 182, 820, 64, 42, rgba(248, 232, 230), TextAlign::Center, true));
        return;
    }

    const bool warning = safety.warning.severity >= WarningSeverity::Warning;
    frame.commands.push_back(image("warning.strip", warning ? "shared.warning.red" : "shared.warning.amber", 150,
                                   610, 382, 700, 72, 0.98F));
    std::string label;
    switch (safety.warning.code) {
        case WarningCode::DoorOpenMoving: label = "DOOR OPEN WHILE MOVING"; break;
        case WarningCode::FrunkOpenMoving: label = "FRUNK OPEN WHILE MOVING"; break;
        case WarningCode::TrunkOpenMoving: label = "TRUNK OPEN WHILE MOVING"; break;
        case WarningCode::LowTire: label = "LOW TIRE PRESSURE"; break;
        case WarningCode::LowSoc: label = "LOW BATTERY"; break;
        default: label = "VEHICLE WARNING"; break;
    }
    frame.commands.push_back(text("warning.label", label, 160,
                                  650, 396, 620, 44, 22, rgba(255, 246, 238), TextAlign::Center, true));
}

RenderFrameV6 HorizonRendererV6::buildFrame(const HorizonRenderInput& input) {
    RenderFrameV6 frame;
    if (!input.vehicle || !input.product) return frame;

    const VehicleState& vehicle = *input.vehicle;
    const ProductStateV6& product = *input.product;
    HorizonSceneState scene = buildHorizonScene(vehicle, warnings_);
    const SafetyLayerV6 safety = buildSafetyLayerV6(vehicle, warnings_);
    HorizonContextRailState rail = buildHorizonContextRail(vehicle, product);

    const float raw_speed = scene.speed_available ? static_cast<float>(scene.speed) : 0.0F;
    const float raw_soc = scene.soc_available ? static_cast<float>(scene.soc) : 0.0F;
    const float display_speed = motion_.update(speed_, raw_speed, input.dt_ms, 90, MotionPriority::Driving);
    const float display_soc = motion_.update(soc_, raw_soc, input.dt_ms, 700, MotionPriority::Page);
    const float ap_target = scene.mode == HorizonMode::ApActive ? 1.0F
                           : scene.mode == HorizonMode::ApAvailable ? 0.38F : 0.0F;
    const float ap = motion_.update(ap_corridor_, ap_target, input.dt_ms, 380, MotionPriority::Page);
    const float left = motion_.update(blind_left_, scene.mode == HorizonMode::LeftBlindSpot ? 1.0F : 0.0F,
                                      input.dt_ms, 220, MotionPriority::Warning);
    const float right = motion_.update(blind_right_, scene.mode == HorizonMode::RightBlindSpot ? 1.0F : 0.0F,
                                       input.dt_ms, 220, MotionPriority::Warning);
    const float lights = motion_.update(vehicle_light_,
        scene.vehicle.headlights || scene.vehicle.brake_lights || scene.vehicle.left_indicator || scene.vehicle.right_indicator
            ? 1.0F : 0.0F,
        input.dt_ms, 180, MotionPriority::Driving);
    const float halo = motion_.update(energy_halo_, scene.vehicle.energy_halo,
                                      input.dt_ms, 180, MotionPriority::Page);
    const float context_target = rail.mode == HorizonContextRailState::Mode::None ? 0.0F : 1.0F;
    motion_.update(context_progress_, context_target, input.dt_ms, 320, MotionPriority::Page);

    motion_state_.speed = speed_;
    motion_state_.soc = soc_;
    motion_state_.ap_corridor = ap_corridor_;
    motion_state_.blind_left = blind_left_;
    motion_state_.blind_right = blind_right_;
    motion_state_.context_progress = context_progress_;
    motion_state_.vehicle_light = vehicle_light_;
    motion_state_.energy_halo = energy_halo_;

    appendEnvironment(frame, scene, ap, left, right);
    appendVehicle(frame, scene, lights, halo);
    appendPrimaryData(frame, scene, display_speed, display_soc);
    appendContextRail(frame, rail);
    appendSafety(frame, safety);

    if (input.developer_mode && input.simulation_mode) {
        frame.commands.push_back(text("dev.simulation", "SIMULATION", 240,
                                      820, 18, 280, 30, 16, rgba(238, 168, 80), TextAlign::Center, true));
    }

    std::stable_sort(frame.commands.begin(), frame.commands.end(),
                     [](const RenderCommand& a, const RenderCommand& b) { return a.z < b.z; });
    return frame;
}

}  // namespace dashboard
