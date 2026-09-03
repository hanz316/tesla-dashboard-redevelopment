#pragma once

#include "dashboard/render_model_v6.h"

#include <cstdint>

namespace dashboard {

struct RenderBackendStats {
    std::uint64_t frames{0};
    std::uint64_t commands_submitted{0};
    std::uint64_t missing_assets{0};
    std::uint64_t unsupported_commands{0};
    std::uint64_t frame_time_us{0};
};

class IRenderBackendV6 {
public:
    virtual ~IRenderBackendV6() = default;

    virtual const char* name() const = 0;
    virtual bool beginFrame(const RenderFrameV6& frame) = 0;
    virtual bool submit(const RenderCommand& command) = 0;
    virtual void endFrame() = 0;
    virtual void releasePageResources() = 0;
    virtual RenderBackendStats stats() const = 0;
};

// T113/EasyUI implementation deliberately lives behind this boundary. It may
// translate RenderCommand IDs to FTU controls or to platform-native image/text
// primitives, but it must not read UART/BLE/PhoneBridge or mutate VehicleState.
class NullRenderBackendV6 final : public IRenderBackendV6 {
public:
    const char* name() const override { return "NullRenderBackendV6"; }
    bool beginFrame(const RenderFrameV6&) override { return true; }
    bool submit(const RenderCommand&) override {
        ++stats_.commands_submitted;
        return true;
    }
    void endFrame() override { ++stats_.frames; }
    void releasePageResources() override {}
    RenderBackendStats stats() const override { return stats_; }

private:
    RenderBackendStats stats_;
};

class RenderPresenterV6 {
public:
    explicit RenderPresenterV6(IRenderBackendV6& backend) : backend_(backend) {}

    bool present(const RenderFrameV6& frame) {
        if (!backend_.beginFrame(frame)) return false;
        bool ok = true;
        for (const RenderCommand& command : frame.commands) {
            if (!command.visible) continue;
            if (!backend_.submit(command)) ok = false;
        }
        backend_.endFrame();
        return ok;
    }

private:
    IRenderBackendV6& backend_;
};

}  // namespace dashboard
