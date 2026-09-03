cmake_minimum_required(VERSION 3.16)

project(tesla_dashboard_redevelopment VERSION 0.2.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

option(BUILD_HOST_TOOLS "Build the host simulator and tests" ON)
option(BUILD_FLYTHINGS_DEVICE "Build the T113 FlyThings libzkgui.so" OFF)

add_library(dashboard_core
    src/core/original_mcu_adapter.cpp
    src/core/protocol_parser.cpp
    src/core/vehicle_state.cpp
    src/core/v6_cockpit.cpp
    src/core/dashboard_services.cpp
    src/core/replay.cpp
    src/core/ui_framework_v6.cpp
    src/core/horizon_v6.cpp
)
set_target_properties(dashboard_core PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_include_directories(dashboard_core PUBLIC include)
target_compile_options(dashboard_core PRIVATE -Wall -Wextra -Wpedantic)

if(BUILD_HOST_TOOLS)
    add_executable(dashboard_simulator apps/simulator/main.cpp)
    target_link_libraries(dashboard_simulator PRIVATE dashboard_core)
    target_compile_options(dashboard_simulator PRIVATE -Wall -Wextra -Wpedantic)

    enable_testing()
    add_executable(dashboard_tests tests/dashboard_tests.cpp)
    target_link_libraries(dashboard_tests PRIVATE dashboard_core)
    target_compile_options(dashboard_tests PRIVATE -Wall -Wextra -Wpedantic)
    add_test(NAME dashboard_tests COMMAND dashboard_tests)

    add_executable(dashboard_v6_tests tests/v6_cockpit_tests.cpp)
    target_link_libraries(dashboard_v6_tests PRIVATE dashboard_core)
    target_compile_options(dashboard_v6_tests PRIVATE -Wall -Wextra -Wpedantic)
    add_test(NAME dashboard_v6_tests COMMAND dashboard_v6_tests)

    add_executable(dashboard_services_tests tests/dashboard_services_tests.cpp)
    target_link_libraries(dashboard_services_tests PRIVATE dashboard_core)
    target_compile_options(dashboard_services_tests PRIVATE -Wall -Wextra -Wpedantic)
    add_test(NAME dashboard_services_tests COMMAND dashboard_services_tests)

    add_executable(dashboard_ui_v6_tests tests/ui_framework_v6_tests.cpp)
    target_link_libraries(dashboard_ui_v6_tests PRIVATE dashboard_core)
    target_compile_options(dashboard_ui_v6_tests PRIVATE -Wall -Wextra -Wpedantic)
    add_test(NAME dashboard_ui_v6_tests COMMAND dashboard_ui_v6_tests)

    add_executable(dashboard_replay_tests tests/replay_tests.cpp)
    target_link_libraries(dashboard_replay_tests PRIVATE dashboard_core)
    target_compile_options(dashboard_replay_tests PRIVATE -Wall -Wextra -Wpedantic)
    add_test(NAME dashboard_replay_tests COMMAND dashboard_replay_tests)
endif()

if(BUILD_FLYTHINGS_DEVICE)
    set(FLYTHINGS_SDK_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/sdk/t113/packages")
    add_library(zkgui SHARED
        device/flythings/device_runtime.cpp
        device/flythings/main.cpp
        device/flythings/main_activity.cpp
    )
    target_include_directories(zkgui PRIVATE
        include
        device/flythings
        "${FLYTHINGS_SDK_ROOT}/easyui/include"
        "${FLYTHINGS_SDK_ROOT}/zkhardware/include"
        "${FLYTHINGS_SDK_ROOT}/zknet/include"
        "${FLYTHINGS_SDK_ROOT}/log/include"
    )
    target_compile_options(zkgui PRIVATE
        -Wall -Wextra -Wpedantic -fPIC -fstack-protector-strong
    )
    target_link_libraries(zkgui PRIVATE
        dashboard_core
        "${FLYTHINGS_SDK_ROOT}/easyui/lib/libeasyui.so"
        "${FLYTHINGS_SDK_ROOT}/zkhardware/lib/libzkhardware.so"
        "${FLYTHINGS_SDK_ROOT}/zknet/lib/libzknet.so"
        "${FLYTHINGS_SDK_ROOT}/log/lib/liblog.so"
        pthread
    )
    target_link_options(zkgui PRIVATE -Wl,-z,relro,-z,now)
    set_target_properties(zkgui PROPERTIES OUTPUT_NAME zkgui)

    add_executable(device_base64 tools/device_base64.cpp)
    target_compile_options(device_base64 PRIVATE
        -Os -Wall -Wextra -Wpedantic -fstack-protector-strong
        -fno-exceptions -fno-rtti -fno-unwind-tables
        -fno-asynchronous-unwind-tables
    )
    target_link_options(device_base64 PRIVATE -static)
endif()
