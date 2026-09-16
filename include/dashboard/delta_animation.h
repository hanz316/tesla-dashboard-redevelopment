#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace dashboard {

// Task Part 17: DeltaAnimationPlayer.
//
// Architecture only - nothing in the existing render path is replaced. The
// concept is:
//
//     static vehicle base  (drawn once, never re-decoded)
//     + per-frame local replacement region (a small PNG per frame)
//
// The compositing rule is RECTANGLE REPLACEMENT, not src-over. That matters:
// when a pixel becomes transparent (the door moves off it) a src-over blit
// would leave the old base pixel behind it. A straight replacement of the
// whole rectangle reproduces the original full-frame render exactly, which
// tools/assets/build_delta_animation.py verifies numerically.
struct DirtyRect {
    int x{0};
    int y{0};
    int width{0};
    int height{0};

    bool empty() const { return width <= 0 || height <= 0; }

    static DirtyRect unionOf(const DirtyRect& a, const DirtyRect& b);
};

struct DeltaAnimationFrame {
    DirtyRect region;             // destination on the base canvas
    std::uint32_t duration_ms{0}; // 0 = use the clip fps
    std::string asset;            // replacement-region PNG ("" = no change)
};

struct DeltaAnimationClip {
    std::string id;
    std::string base_asset;
    std::uint32_t canvas_width{0};
    std::uint32_t canvas_height{0};
    std::uint16_t fps{30};
    std::vector<DeltaAnimationFrame> frames;
};

// The platform primitive the player needs. EasyUI would implement this on top
// of the same streaming decoder ZKImageAnim already uses.
class IDeltaSurface {
public:
    virtual ~IDeltaSurface() = default;
    // Blit `asset` so that its top-left lands on dst.(x, y) of the surface.
    // Implementations must replace the destination rectangle, alpha included.
    virtual bool blitRegion(const std::string& asset, const DirtyRect& dst) = 0;
};

enum class DeltaPlayState : std::uint8_t {
    Stopped = 0,
    Playing,
    Paused,
};

class DeltaAnimationPlayer {
public:
    void load(const DeltaAnimationClip& clip);

    void play();
    void pause();
    void stop();
    // Manual frame selection; also pauses playback.
    void setFrame(std::uint32_t index);

    // Advances the clock and draws the current frame. Returns, in SURFACE
    // coordinates (i.e. already offset by base_x/base_y), the union of every
    // region that changed during this tick - empty if nothing moved.
    DirtyRect tick(std::uint32_t dt_ms, IDeltaSurface& surface,
                   int base_x, int base_y);

    // Draws the current frame immediately without advancing time.
    void draw(IDeltaSurface& surface, int base_x, int base_y);

    // Region of the CURRENT frame, in CLIP coordinates (no base offset).
    DirtyRect getDirtyRect() const;
    std::uint32_t frameIndex() const { return frame_index_; }
    std::uint32_t frameCount() const {
        return static_cast<std::uint32_t>(clip_.frames.size());
    }
    DeltaPlayState state() const { return state_; }
    const DeltaAnimationClip& clip() const { return clip_; }

    // Union of every frame's region: how much of the base the whole animation
    // can ever touch. Used to decide whether a fixed tight canvas is cheaper
    // than per-frame sized regions.
    DirtyRect totalDirtyRect() const;

private:
    std::uint32_t frameDurationMs(const DeltaAnimationFrame& frame) const;

    DeltaAnimationClip clip_;
    std::uint32_t frame_index_{0};
    std::uint32_t elapsed_ms_{0};
    DeltaPlayState state_{DeltaPlayState::Stopped};
};

// Can ZKImageAnim be used directly as the delta transport?
//
// The device export list (docs/RENDERING_CAPABILITY_AUDIT.md 9.1) proves
// ZKImageAnim is a streaming decoder + timer + per-frame read, so it does not
// need the whole sequence resident. What it does NOT tell us is whether one
// ZKImageAnim instance accepts frames of DIFFERENT sizes and can be drawn at a
// per-frame x/y. That is a real device question and it stays unanswered until
// it is measured, so the verdict is Unknown rather than assumed.
enum class DeltaTransportVerdict : std::uint8_t {
    Supported = 0,   // one instance, variable size + per-frame position
    NeedsFixedCanvas,// streaming works, but all frames must share a canvas
    Unsupported,     // ZKImageAnim cannot do it; custom decode required
    Unknown,         // not yet measured on the device
};

DeltaTransportVerdict zkImageAnimDeltaVerdict();

// The two documented fallbacks if ZKImageAnim cannot express per-frame
// regions. Both keep the streaming decoder and both avoid a full-sequence
// preload; neither is allowed to be adopted before it is tested on hardware.
enum class DeltaFallback : std::uint8_t {
    None = 0,
    // One fixed canvas sized to the union dirty rect. Every frame is stored
    // at that size with its own placement, so per-frame variable size is not
    // needed. Costs the union area on every frame instead of the exact
    // dirty area.
    FixedTightCanvas,
    // Own PNG stream + own compositor: decode a region PNG, blit it into the
    // frame surface, hand the surface to EasyUI as a plain image.
    CustomStreamedDecode,
};

DeltaFallback recommendedDeltaFallback(DeltaTransportVerdict verdict);
const char* deltaTransportVerdictName(DeltaTransportVerdict verdict);
const char* deltaFallbackName(DeltaFallback fallback);

}  // namespace dashboard
