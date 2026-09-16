#include "dashboard/delta_animation.h"

// Keep the assertions live even in a Release build (NDEBUG), otherwise this
// whole file compiles to a no-op and CI would report a green test that
// verified nothing.
#undef NDEBUG
#include <cassert>
#include <iostream>
#include <string>
#include <vector>

using namespace dashboard;

namespace {

class RecordingSurface : public IDeltaSurface {
public:
    bool blitRegion(const std::string& asset, const DirtyRect& dst) override {
        blits.push_back(asset);
        rects.push_back(dst);
        return true;
    }
    std::vector<std::string> blits;
    std::vector<DirtyRect> rects;
};

DeltaAnimationClip makeClip(std::uint32_t fps = 30) {
    DeltaAnimationClip clip;
    clip.id = "door_fl_open";
    clip.base_asset = "base.png";
    clip.canvas_width = 769;
    clip.canvas_height = 531;
    clip.fps = static_cast<std::uint16_t>(fps);
    clip.frames.push_back({DirtyRect{0, 0, 0, 0}, 0, ""});          // closed
    clip.frames.push_back({DirtyRect{151, 150, 200, 120}, 0, "001.png"});
    clip.frames.push_back({DirtyRect{151, 150, 462, 266}, 0, "002.png"});
    return clip;
}

}  // namespace

int main() {
    // Dirty-rect union is the core primitive: it decides how much has to be
    // redrawn when several frames are skipped in a single tick.
    {
        const DirtyRect a{10, 10, 20, 20};
        const DirtyRect b{40, 5, 10, 10};
        const DirtyRect u = DirtyRect::unionOf(a, b);
        assert(u.x == 10 && u.y == 5);
        assert(u.width == 40 && u.height == 25);
        std::cout << "union = " << u.width << "x" << u.height << "\n";
        assert(DirtyRect::unionOf(DirtyRect{}, a).width == 20);
        assert(DirtyRect::unionOf(DirtyRect{}, DirtyRect{}).empty());
    }

    // A frame with no region is a frame identical to the base and must not
    // produce a blit at all.
    {
        DeltaAnimationPlayer player;
        player.load(makeClip());
        RecordingSurface surface;
        player.draw(surface, 0, 0);
        assert(surface.blits.empty());
    }

    // Playing: one frame per 1000/30 ms, and the region is translated by the
    // base position on the canvas.
    {
        DeltaAnimationPlayer player;
        player.load(makeClip(30));
        player.play();
        RecordingSurface surface;

        const DirtyRect first = player.tick(33, surface, 700, 40);
        assert(player.frameIndex() == 1);
        assert(first.x == 700 + 151 && first.y == 40 + 150);
        std::cout << "first dirty rect = " << first.x << "," << first.y << " "
                  << first.width << "x" << first.height << "\n";
        assert(surface.rects.size() == 1);
        assert(surface.rects[0].x == 851 && surface.rects[0].y == 190);

        const DirtyRect second = player.tick(40, surface, 700, 40);
        assert(player.frameIndex() == 2);
        // The union covers both the previous and the new region.
        assert(second.width == 462 && second.height == 266);
        std::cout << "tick union = " << second.width << "x" << second.height
                  << "\n";
    }

    // The clock must hold the last frame, never wrap, never overrun.
    {
        DeltaAnimationPlayer player;
        player.load(makeClip(30));
        player.play();
        RecordingSurface surface;
        for (int i = 0; i < 50; ++i) {
            player.tick(200, surface, 0, 0);
        }
        assert(player.frameIndex() == 2);
        assert(player.state() == DeltaPlayState::Paused);
    }

    // stop() must return to the base pose so the caller can leave the vehicle
    // closed without reloading anything.
    {
        DeltaAnimationPlayer player;
        player.load(makeClip(30));
        player.setFrame(2);
        assert(player.frameIndex() == 2);
        player.stop();
        assert(player.frameIndex() == 0);
        assert(player.state() == DeltaPlayState::Stopped);
        assert(player.getDirtyRect().empty());
    }

    // totalDirtyRect drives the fixed-tight-canvas fallback.
    {
        DeltaAnimationPlayer player;
        player.load(makeClip(30));
        const DirtyRect total = player.totalDirtyRect();
        assert(total.x == 151 && total.y == 150);
        assert(total.width == 462 && total.height == 266);
        std::cout << "total dirty rect = " << total.x << "," << total.y << " "
                  << total.width << "x" << total.height << "\n";
    }

    // The transport question must stay UNKNOWN until it is measured on the
    // device, and the fallback recommendation must be the streaming one.
    {
        const DeltaTransportVerdict verdict = zkImageAnimDeltaVerdict();
        assert(verdict == DeltaTransportVerdict::Unknown);
        assert(std::string(deltaTransportVerdictName(verdict)) == "UNKNOWN");
        const DeltaFallback fallback = recommendedDeltaFallback(verdict);
        assert(fallback == DeltaFallback::FixedTightCanvas);
        std::cout << "zkImageAnim delta verdict = "
                  << deltaTransportVerdictName(verdict) << " -> "
                  << deltaFallbackName(fallback) << "\n";
    }

    std::cout << "delta_animation_tests OK\n";
    return 0;
}
