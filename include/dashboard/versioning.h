#pragma once

#include <cstdint>
#include <string>

namespace dashboard {

struct SemanticVersion {
    std::uint16_t major{0};
    std::uint16_t minor{0};
    std::uint16_t patch{0};
};

struct DashboardVersions {
    SemanticVersion dashboard{0, 6, 0};
    SemanticVersion ui{6, 0, 0};
    SemanticVersion protocol{0, 2, 0};
    SemanticVersion vehicle_profile{0, 1, 0};
    SemanticVersion commander_module{0, 0, 0};
    SemanticVersion phone_bridge{0, 0, 0};
};

enum class OtaStage : std::uint8_t {
    Idle = 0,
    Downloaded,
    HashVerified,
    VersionValidated,
    Staged,
    ReadyToActivate,
    Failed,
};

struct OtaPackageState {
    OtaStage stage{OtaStage::Idle};
    std::string module_id;
    std::string sha256;
    SemanticVersion version;
    std::string staging_path;
    bool rollback_available{false};
};

// Contract only. Network download and activation are intentionally not part of
// Dashboard V6-H1. Future OTA must stage/verify/version-check and support
// rollback; it must never write bootloader/uboot or raw flash partitions.
class IOtaStagingService {
public:
    virtual ~IOtaStagingService() = default;
    virtual const OtaPackageState& state() const = 0;
    virtual bool validateStagedPackage() = 0;
    virtual void discardStagedPackage() = 0;
};

}  // namespace dashboard
