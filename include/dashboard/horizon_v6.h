#pragma once

#include "dashboard/product_state_v6.h"
#include "dashboard/render_model_v6.h"
#include "dashboard/ui_framework_v6.h"
#include "dashboard/v6_cockpit.h"

#include <cstdint>

namespace dashboard {

struct HorizonMotionState {
    MotionValue speed;
    MotionValue soc;
    MotionValue ap_corridor;
    MotionValue blind_left;
    MotionValue blind_right;
    MotionValue context_progress;
    MotionValue vehicle_light;
    MotionValue energy_halo;
};

struct HorizonRenderInput {
    const VehicleState* vehicle{nullptr};
    const ProductStateV6* product{nullptr};
    std::uint32_t dt_ms{33};
    bool developer_mode{false};
    bool simulation_mode{false};
};

class HorizonRendererV6 {
public:
    explicit HorizonRendererV6(MotionQuality quality = MotionQuality::Full)
        : motion_(quality) {}

    void setMotionQuality(MotionQuality quality) { motion_.setQuality(quality); }
    MotionQuality motionQuality() const { return motion_.quality(); }
    const HorizonMotionState& motionState() const { return motion_state_; }

    RenderFrameV6 buildFrame(const HorizonRenderInput& input);

private:
    static RenderCommand image(const char* id, const char* asset, std::int16_t z,
                               float x, float y, float w, float h, float opacity = 1.0F);
    static RenderCommand text(const char* id, const std::string& value, std::int16_t z,
                              float x, float y, float w, float h, std::uint16_t font_px,
                              RenderColor color, TextAlign align = TextAlign::Left,
                              bool bold = false);
    static RenderCommand solid(const char* id, std::int16_t z, float x, float y,
                               float w, float h, RenderColor color);
    static RenderCommand line(const char* id, std::int16_t z, float x, float y,
                              float w, float h, RenderColor color);

    void appendEnvironment(RenderFrameV6& frame, const HorizonSceneState& scene,
                           float ap_alpha, float blind_left, float blind_right) const;
    void appendVehicle(RenderFrameV6& frame, const HorizonSceneState& scene,
                       float light_alpha, float energy_halo_alpha) const;
    void appendPrimaryData(RenderFrameV6& frame, const HorizonSceneState& scene,
                           float display_speed, float display_soc) const;
    void appendContextRail(RenderFrameV6& frame, const HorizonContextRailState& rail) const;
    void appendSafety(RenderFrameV6& frame, const SafetyLayerV6& safety) const;

    MotionEngine motion_;
    MotionValue speed_;
    MotionValue soc_;
    MotionValue ap_corridor_;
    MotionValue blind_left_;
    MotionValue blind_right_;
    MotionValue context_progress_;
    MotionValue vehicle_light_;
    MotionValue energy_halo_;
    HorizonMotionState motion_state_;
    WarningManager warnings_;
};

}  // namespace dashboard
