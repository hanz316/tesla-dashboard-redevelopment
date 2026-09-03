#include "dashboard/v6_asset_catalog.h"

namespace dashboard {

std::vector<AssetDescriptor> v6SharedAssetCatalog() {
    return {
        {"vehicle.shadow", "assets/v6/shared/vehicle/model3_shadow.png", 360U * 150U * 4U, true},
        {"vehicle.body", "assets/v6/shared/vehicle/model3_body_rear_2p5d.png", 356U * 236U * 4U, true},
        {"vehicle.glass", "assets/v6/shared/vehicle/model3_glass.png", 356U * 236U * 4U, true},
        {"vehicle.roof", "assets/v6/shared/vehicle/model3_roof.png", 356U * 236U * 4U, true},
        {"vehicle.front_lights", "assets/v6/shared/vehicle/model3_headlights.png", 356U * 236U * 4U, true},
        {"vehicle.high_beam", "assets/v6/shared/vehicle/model3_high_beam.png", 520U * 316U * 4U, true},
        {"vehicle.brake_lights", "assets/v6/shared/vehicle/model3_brake_lights.png", 356U * 236U * 4U, true},
        {"vehicle.indicator.left", "assets/v6/shared/vehicle/model3_indicator_left.png", 356U * 236U * 4U, true},
        {"vehicle.indicator.right", "assets/v6/shared/vehicle/model3_indicator_right.png", 356U * 236U * 4U, true},
        {"vehicle.door.fl", "assets/v6/shared/vehicle/model3_door_fl.png", 356U * 236U * 4U, true},
        {"vehicle.door.fr", "assets/v6/shared/vehicle/model3_door_fr.png", 356U * 236U * 4U, true},
        {"vehicle.door.rl", "assets/v6/shared/vehicle/model3_door_rl.png", 356U * 236U * 4U, true},
        {"vehicle.door.rr", "assets/v6/shared/vehicle/model3_door_rr.png", 356U * 236U * 4U, true},
        {"vehicle.frunk", "assets/v6/shared/vehicle/model3_frunk.png", 356U * 236U * 4U, true},
        {"vehicle.trunk", "assets/v6/shared/vehicle/model3_trunk.png", 356U * 236U * 4U, true},
        {"vehicle.energy.drive", "assets/v6/shared/vehicle/model3_energy_drive.png", 424U * 180U * 4U, false},
        {"vehicle.energy.regen", "assets/v6/shared/vehicle/model3_energy_regen.png", 424U * 180U * 4U, false},
        {"shared.turn.left", "assets/v6/shared/turn_left.png", 48U * 84U * 4U, true},
        {"shared.turn.right", "assets/v6/shared/turn_right.png", 48U * 84U * 4U, true},
        {"shared.warning.red", "assets/v6/shared/warning_red.png", 700U * 72U * 4U, true},
        {"shared.warning.amber", "assets/v6/shared/warning_amber.png", 700U * 72U * 4U, true},
        {"shared.warning.critical_backdrop", "assets/v6/shared/warning_critical_backdrop.jpg", 1920U * 480U * 3U, true},
    };
}

std::vector<AssetDescriptor> v6HorizonAssetCatalog() {
    return {
        {"horizon.environment.base", "assets/v6/horizon/environment_graphite.jpg", 1920U * 480U * 3U, false},
        {"horizon.road.surface", "assets/v6/horizon/road_surface.jpg", 1080U * 362U * 3U, false},
        {"horizon.road.lanes", "assets/v6/horizon/lanes.png", 1080U * 362U * 4U, false},
        {"horizon.ap.corridor", "assets/v6/horizon/ap_corridor.png", 776U * 352U * 4U, false},
        {"horizon.blind.left", "assets/v6/horizon/blind_zone_left.png", 270U * 210U * 4U, false},
        {"horizon.blind.right", "assets/v6/horizon/blind_zone_right.png", 270U * 210U * 4U, false},
        {"horizon.vehicle.coarse.front", "assets/v6/horizon/coarse_vehicle_front.png", 144U * 96U * 4U, false},
        {"horizon.vehicle.coarse.left", "assets/v6/horizon/coarse_vehicle_left.png", 156U * 104U * 4U, false},
        {"horizon.vehicle.coarse.right", "assets/v6/horizon/coarse_vehicle_right.png", 156U * 104U * 4U, false},
        {"horizon.context.glass", "assets/v6/horizon/context_glass.png", 360U * 372U * 4U, false},
    };
}

void registerV6HorizonAssets(AssetManager& manager) {
    for (const AssetDescriptor& asset : v6SharedAssetCatalog()) manager.registerAsset(asset);
    for (const AssetDescriptor& asset : v6HorizonAssetCatalog()) manager.registerAsset(asset);
}

}  // namespace dashboard
