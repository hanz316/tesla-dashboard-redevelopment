#include "dashboard/delta_animation.h"

#include <algorithm>

namespace dashboard {

DirtyRect DirtyRect::unionOf(const DirtyRect& a, const DirtyRect& b) {
    if (a.empty()) {
        return b;
    }
    if (b.empty()) {
        return a;
    }
    const int x0 = std::min(a.x, b.x);
    const int y0 = std::min(a.y, b.y);
    const int x1 = std::max(a.x + a.width, b.x + b.width);
    const int y1 = std::max(a.y + a.height, b.y + b.height);
    return DirtyRect{x0, y0, x1 - x0, y1 - y0};
}

void DeltaAnimationPlayer::load(const DeltaAnimationClip& clip) {
    clip_ = clip;
    frame_index_ = 0;
    elapsed_ms_ = 0;
    state_ = DeltaPlayState::Stopped;
}

void DeltaAnimationPlayer::play() {
    if (clip_.frames.empty()) {
        return;
    }
    state_ = DeltaPlayState::Playing;
}

void DeltaAnimationPlayer::pause() {
    if (state_ == DeltaPlayState::Playing) {
        state_ = DeltaPlayState::Paused;
    }
}

void DeltaAnimationPlayer::stop() {
    state_ = DeltaPlayState::Stopped;
    frame_index_ = 0;
    elapsed_ms_ = 0;
}

void DeltaAnimationPlayer::setFrame(std::uint32_t index) {
    if (clip_.frames.empty()) {
        frame_index_ = 0;
        return;
    }
    frame_index_ = std::min<std::uint32_t>(
        index, static_cast<std::uint32_t>(clip_.frames.size() - 1));
    elapsed_ms_ = 0;
    if (state_ == DeltaPlayState::Playing) {
        state_ = DeltaPlayState::Paused;
    }
}

std::uint32_t DeltaAnimationPlayer::frameDurationMs(
    const DeltaAnimationFrame& frame) const {
    if (frame.duration_ms != 0) {
        return frame.duration_ms;
    }
    const std::uint16_t fps = clip_.fps == 0 ? 30 : clip_.fps;
    return static_cast<std::uint32_t>(1000u / fps);
}

void DeltaAnimationPlayer::draw(IDeltaSurface& surface, int base_x,
                                int base_y) {
    if (clip_.frames.empty() || frame_index_ >= clip_.frames.size()) {
        return;
    }
    const DeltaAnimationFrame& frame = clip_.frames[frame_index_];
    if (frame.asset.empty() || frame.region.empty()) {
        return;  // this frame is identical to the base
    }
    DirtyRect dst = frame.region;
    dst.x += base_x;
    dst.y += base_y;
    surface.blitRegion(frame.asset, dst);
}

DirtyRect DeltaAnimationPlayer::tick(std::uint32_t dt_ms,
                                     IDeltaSurface& surface,
                                     int base_x, int base_y) {
    if (state_ != DeltaPlayState::Playing || clip_.frames.empty()) {
        return DirtyRect{};
    }

    // The clock must never be able to skip past the end of the clip, and the
    // last frame is held rather than wrapping.
    const std::size_t last = clip_.frames.size() - 1;
    elapsed_ms_ += dt_ms;
    DirtyRect touched;
    while (frame_index_ < last) {
        const std::uint32_t duration = frameDurationMs(clip_.frames[frame_index_]);
        if (elapsed_ms_ < duration) {
            break;
        }
        elapsed_ms_ -= duration;
        touched = DirtyRect::unionOf(touched, clip_.frames[frame_index_].region);
        ++frame_index_;
    }

    const DirtyRect current = clip_.frames[frame_index_].region;
    touched = DirtyRect::unionOf(touched, current);
    draw(surface, base_x, base_y);

    // Return SURFACE coordinates: the caller has to know which part of the
    // actual screen needs repainting, not which part of the clip moved.
    touched.x += base_x;
    touched.y += base_y;

    if (frame_index_ == last) {
        state_ = DeltaPlayState::Paused;
    }
    return touched;
}

DirtyRect DeltaAnimationPlayer::getDirtyRect() const {
    if (clip_.frames.empty() || frame_index_ >= clip_.frames.size()) {
        return DirtyRect{};
    }
    return clip_.frames[frame_index_].region;
}

DirtyRect DeltaAnimationPlayer::totalDirtyRect() const {
    DirtyRect total;
    for (const DeltaAnimationFrame& frame : clip_.frames) {
        total = DirtyRect::unionOf(total, frame.region);
    }
    return total;
}

DeltaTransportVerdict zkImageAnimDeltaVerdict() {
    // Deliberately not guessed. The device export list proves streaming
    // playback exists; it says nothing about per-frame size or position, and
    // the shipped SDK headers do not describe ZKImageAnim at all.
    return DeltaTransportVerdict::Unknown;
}

DeltaFallback recommendedDeltaFallback(DeltaTransportVerdict verdict) {
    switch (verdict) {
        case DeltaTransportVerdict::Supported:
            return DeltaFallback::None;
        case DeltaTransportVerdict::NeedsFixedCanvas:
            return DeltaFallback::FixedTightCanvas;
        case DeltaTransportVerdict::Unsupported:
        case DeltaTransportVerdict::Unknown:
            // Until the device answers, assume the cheaper-to-implement of the
            // two fallbacks and keep streaming: one tight canvas per clip.
            return DeltaFallback::FixedTightCanvas;
    }
    return DeltaFallback::FixedTightCanvas;
}

const char* deltaTransportVerdictName(DeltaTransportVerdict verdict) {
    switch (verdict) {
        case DeltaTransportVerdict::Supported:
            return "SUPPORTED";
        case DeltaTransportVerdict::NeedsFixedCanvas:
            return "NEEDS_FIXED_CANVAS";
        case DeltaTransportVerdict::Unsupported:
            return "NOT_SUPPORTED";
        case DeltaTransportVerdict::Unknown:
            return "UNKNOWN";
    }
    return "UNKNOWN";
}

const char* deltaFallbackName(DeltaFallback fallback) {
    switch (fallback) {
        case DeltaFallback::None:
            return "NONE";
        case DeltaFallback::FixedTightCanvas:
            return "FIXED_TIGHT_CANVAS";
        case DeltaFallback::CustomStreamedDecode:
            return "CUSTOM_STREAMED_DECODE";
    }
    return "NONE";
}

}  // namespace dashboard
