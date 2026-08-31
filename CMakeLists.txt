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
    src/core/stale_policy.cpp
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

    add_executable(dashboard_stale_tests tests/stale_policy_tests.cpp)
    target_link_libraries(dashboard_stale_tests PRIVATE dashboard_core)
    target_compile_options(dashboard_stale_tests PRIVATE -Wall -Wextra -Wpedantic)
    add_test(NAME dashboard_stale_tests COMMAND dashboard_stale_tests)

    find_package(PkgConfig QUIET)
    if(PkgConfig_FOUND)
        pkg_check_modules(SDL2 QUIET sdl2)
        pkg_check_modules(SDL2_TTF QUIET SDL2_ttf)
        pkg_check_modules(SDL2_IMAGE QUIET SDL2_image)
    endif()
    if(SDL2_FOUND AND SDL2_TTF_FOUND AND SDL2_IMAGE_FOUND)
        add_executable(dashboard_simulator_gui
            apps/simulator_gui/main.cpp
            apps/simulator_gui/replay_source.cpp
        )
        target_link_libraries(dashboard_simulator_gui PRIVATE dashboard_core)
        target_include_directories(dashboard_simulator_gui PRIVATE
            apps/simulator_gui
            ${SDL2_INCLUDE_DIRS}
            ${SDL2_TTF_INCLUDE_DIRS}
            ${SDL2_IMAGE_INCLUDE_DIRS}
        )
        target_link_directories(dashboard_simulator_gui PRIVATE
            ${SDL2_LIBRARY_DIRS}
            ${SDL2_TTF_LIBRARY_DIRS}
            ${SDL2_IMAGE_LIBRARY_DIRS}
        )
        target_link_libraries(dashboard_simulator_gui PRIVATE
            ${SDL2_LIBRARIES}
            ${SDL2_TTF_LIBRARIES}
            ${SDL2_IMAGE_LIBRARIES}
        )
        target_compile_options(dashboard_simulator_gui PRIVATE
            -Wall -Wextra -Wpedantic
        )
    endif()
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

    add_executable(uart_rx_toggle tools/uart_rx_toggle.cpp)
    target_compile_options(uart_rx_toggle PRIVATE
        -Os -Wall -Wextra -Wpedantic -fstack-protector-strong
        -fno-exceptions -fno-rtti
    )
    target_link_options(uart_rx_toggle PRIVATE -static)

    add_executable(fb_calibrate tools/fb_calibrate.cpp)
    target_compile_options(fb_calibrate PRIVATE
        -Os -Wall -Wextra -Wpedantic -fstack-protector-strong
        -fno-exceptions -fno-rtti
    )
    target_link_options(fb_calibrate PRIVATE -static)

    add_executable(fb_touch_draw tools/fb_touch_draw.cpp)
    target_compile_options(fb_touch_draw PRIVATE
        -Os -Wall -Wextra -Wpedantic -fstack-protector-strong
        -fno-exceptions -fno-rtti
    )
    target_link_options(fb_touch_draw PRIVATE -static)
endif()
