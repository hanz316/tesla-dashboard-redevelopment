#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace dashboard {

enum class RenderCommandType : std::uint8_t {
    Image = 0,
    Text,
    SolidRect,
    GradientRect,
    Line,
    ClipPush,
    ClipPop,
};

enum class TextAlign : std::uint8_t { Left = 0, Center, Right };

struct RenderRect {
    float x{0.0F};
    float y{0.0F};
    float w{0.0F};
    float h{0.0F};
};

struct RenderColor {
    std::uint8_t r{255};
    std::uint8_t g{255};
    std::uint8_t b{255};
    std::uint8_t a{255};
};

struct RenderTransform {
    float translate_x{0.0F};
    float translate_y{0.0F};
    float scale_x{1.0F};
    float scale_y{1.0F};
    float rotation_deg{0.0F};
    float opacity{1.0F};
};

struct RenderCommand {
    RenderCommandType type{RenderCommandType::Image};
    std::int16_t z{0};
    std::string id;
    std::string asset_id;
    std::string text;
    RenderRect rect;
    RenderRect crop;
    RenderColor color;
    RenderColor color2;
    RenderTransform transform;
    TextAlign text_align{TextAlign::Left};
    std::uint16_t font_px{16};
    bool bold{false};
    bool visible{true};
};

struct RenderFrameV6 {
    std::uint16_t width{1920};
    std::uint16_t height{480};
    std::uint16_t safe_top_corner_cut{116};
    std::uint16_t safe_bottom_corner_cut{51};
    std::vector<RenderCommand> commands;

    void clear() { commands.clear(); }
};

}  // namespace dashboard
