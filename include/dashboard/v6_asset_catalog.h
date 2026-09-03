#pragma once

#include "dashboard/v6_cockpit.h"

#include <vector>

namespace dashboard {

std::vector<AssetDescriptor> v6SharedAssetCatalog();
std::vector<AssetDescriptor> v6HorizonAssetCatalog();
void registerV6HorizonAssets(AssetManager& manager);

}  // namespace dashboard
