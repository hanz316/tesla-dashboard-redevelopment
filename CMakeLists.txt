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
    src/core/page_projection_v6.cpp
    src/core/commander_link.cpp
    src/core/commander_transport.cpp
    src/core/settings_store_v6.cpp
    src/core/input_router_v6.cpp
    src/core/horizon_v6.cpp
    src/core/v6_asset_catalog.cpp
    src/core/motion_quality.cpp
    src/core/delta_animation.cpp
    src/core/vehicle_visual_controller.cpp
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

    add_executable(dashboard_motion_quality_tests tests/motion_quality_tests.cpp)
    target_link_libraries(dashboard_motion_quality_tests PRIVATE dashboard_core)
    target_compile_options(dashboard_motion_quality_tests PRIVATE -Wall -Wextra -Wpedantic)
    add_test(NAME dashboard_motion_quality_tests COMMAND dashboard_motion_quality_tests)

    add_executable(dashboard_delta_animation_tests tests/delta_animation_tests.cpp)
    target_link_libraries(dashboard_delta_animation_tests PRIVATE dashboard_core)
    target_compile_options(dashboard_delta_animation_tests PRIVATE -Wall -Wextra -Wpedantic)
    add_test(NAME dashboard_delta_animation_tests COMMAND dashboard_delta_animation_tests)

    add_executable(dashboard_vehicle_visual_tests tests/vehicle_visual_controller_tests.cpp)
    target_link_libraries(dashboard_vehicle_visual_tests PRIVATE dashboard_core)
    target_compile_options(dashboard_vehicle_visual_tests PRIVATE -Wall -Wextra -Wpedantic)
    add_test(NAME dashboard_vehicle_visual_tests COMMAND dashboard_vehicle_visual_tests)

    # What each screen can draw, and what it draws when a signal is missing.
    add_executable(dashboard_page_projection_tests tests/page_projection_tests.cpp)
    target_link_libraries(dashboard_page_projection_tests PRIVATE dashboard_core)
    target_compile_options(dashboard_page_projection_tests PRIVATE -Wall -Wextra -Wpedantic)
    add_test(NAME dashboard_page_projection_tests COMMAND dashboard_page_projection_tests)

    add_executable(dashboard_settings_store_tests tests/settings_store_tests.cpp)
    target_link_libraries(dashboard_settings_store_tests PRIVATE dashboard_core)
    target_compile_options(dashboard_settings_store_tests PRIVATE -Wall -Wextra -Wpedantic)
    add_test(NAME dashboard_settings_store_tests COMMAND dashboard_settings_store_tests)

    add_executable(dashboard_input_router_tests tests/input_router_tests.cpp)
    target_link_libraries(dashboard_input_router_tests PRIVATE dashboard_core)
    target_compile_options(dashboard_input_router_tests PRIVATE -Wall -Wextra -Wpedantic)
    add_test(NAME dashboard_input_router_tests COMMAND dashboard_input_router_tests)

    # Auto-connect, the frame path and the phone-bridge receive path. The UDP
    # part uses a real socket on loopback, so the transport is exercised rather
    # than mocked.
    add_executable(dashboard_commander_bridge_tests tests/commander_bridge_tests.cpp)
    target_link_libraries(dashboard_commander_bridge_tests PRIVATE dashboard_core)
    target_compile_options(dashboard_commander_bridge_tests PRIVATE -Wall -Wextra -Wpedantic)
    add_test(NAME dashboard_commander_bridge_tests COMMAND dashboard_commander_bridge_tests)

    # The device's own view of the world, compiled from the same source the
    # T113 build uses, so the mapping from runtime snapshot to screen is not
    # only testable on the panel.
    add_executable(dashboard_device_environment_tests
        tests/device_environment_tests.cpp
        device/flythings/device_runtime.cpp
    )
    target_include_directories(dashboard_device_environment_tests PRIVATE
        device/flythings include)
    target_link_libraries(dashboard_device_environment_tests PRIVATE dashboard_core)
    target_compile_options(dashboard_device_environment_tests PRIVATE -Wall -Wextra -Wpedantic)
    add_test(NAME dashboard_device_environment_tests COMMAND dashboard_device_environment_tests)

    # Binds the committed scenes to the runtime projection. Host tool, no
    # vehicle data: it prints the names each page offers so the scene files can
    # be checked against them.
    add_executable(dashboard_page_dump apps/page_dump/main.cpp)
    target_link_libraries(dashboard_page_dump PRIVATE dashboard_core)
    target_compile_options(dashboard_page_dump PRIVATE -Wall -Wextra -Wpedantic)

    # The device benchmark plan is platform independent, so the state list, the
    # sequence playback maths, the frame statistics and the fallback decision
    # are verified on the host before the T113 is ever connected.
    add_executable(dashboard_device_bench_tests
        tests/device_bench_plan_tests.cpp
        device/bench/bench_plan.cpp
    )
    target_include_directories(dashboard_device_bench_tests PRIVATE device/bench)
    target_compile_options(dashboard_device_bench_tests PRIVATE -Wall -Wextra -Wpedantic)
    add_test(NAME dashboard_device_bench_tests COMMAND dashboard_device_bench_tests)

    # What the cluster shows for a signal that is not there. Host-compilable on
    # purpose: UNKNOWN != 0 is a rule, not a device detail.
    add_executable(dashboard_device_display_tests
        tests/device_display_format_tests.cpp
        device/flythings/display_format.cpp
    )
    target_include_directories(dashboard_device_display_tests PRIVATE
        device/flythings include)
    target_link_libraries(dashboard_device_display_tests PRIVATE dashboard_core)
    target_compile_options(dashboard_device_display_tests PRIVATE -Wall -Wextra -Wpedantic)
    add_test(NAME dashboard_device_display_tests COMMAND dashboard_device_display_tests)

    # Geometry rules for the taillight light guide. These run on the host: the
    # Blender-only pieces are stubbed, and the cavity is replaced by an analytic
    # distance function, so the rules that were expensive to learn (reject
    # geometry rather than force a minimum radius, count coverage in slabs,
    # attribute the limiting clearance sample) are checked without a GPU,
    # Blender or the source model.
    find_program(PYTHON3_EXECUTABLE python3)
    if(PYTHON3_EXECUTABLE)
        add_test(NAME dashboard_taillight_guide_tests
                 COMMAND "${PYTHON3_EXECUTABLE}"
                         "${CMAKE_CURRENT_SOURCE_DIR}/tests/taillight_guide_tests.py")
        add_test(NAME dashboard_vehicle_asset_tests
                 COMMAND "${PYTHON3_EXECUTABLE}"
                         "${CMAKE_CURRENT_SOURCE_DIR}/tests/vehicle_asset_manifest_tests.py")
        add_test(NAME dashboard_trunk_lighting_tests
                 COMMAND "${PYTHON3_EXECUTABLE}"
                         "${CMAKE_CURRENT_SOURCE_DIR}/tests/trunk_lighting_ownership_tests.py")
        add_test(NAME dashboard_uart_capture_tests
                 COMMAND "${PYTHON3_EXECUTABLE}"
                         "${CMAKE_CURRENT_SOURCE_DIR}/tests/uart_capture_parser_tests.py")
        add_test(NAME dashboard_deploy_safety_tests
                 COMMAND "${PYTHON3_EXECUTABLE}"
                         "${CMAKE_CURRENT_SOURCE_DIR}/tests/deploy_safety_tests.py")
        # The V6 page set is generated, but the runtime reads the committed
        # scenes. These checks run on the scenes so a stale generation or a
        # dropped rule is caught before the instrument ever sees it.
        add_test(NAME dashboard_v6_pages_tests
                 COMMAND "${PYTHON3_EXECUTABLE}"
                         "${CMAKE_CURRENT_SOURCE_DIR}/tests/v6_pages_tests.py")
        # The scenes name the values they bind; the runtime projection is C++.
        # This compares the two lists in both directions.
        add_test(NAME dashboard_v6_binding_coverage_tests
                 COMMAND "${PYTHON3_EXECUTABLE}"
                         "${CMAKE_CURRENT_SOURCE_DIR}/tests/v6_binding_coverage_tests.py"
                         "$<TARGET_FILE:dashboard_page_dump>")
        # The whole set through the states that decide whether an instrument is
        # trustworthy, not just the happy path.
        add_test(NAME dashboard_v6_pages_state_matrix_tests
                 COMMAND "${PYTHON3_EXECUTABLE}"
                         "${CMAKE_CURRENT_SOURCE_DIR}/tests/v6_pages_state_matrix_tests.py")
        # Horizon V2: the layout is the design source, the scene is generated
        # from it, and the screenshots have to agree with both.
        add_test(NAME dashboard_horizon_v2_tests
                 COMMAND "${PYTHON3_EXECUTABLE}"
                         "${CMAKE_CURRENT_SOURCE_DIR}/tests/horizon_v2_tests.py")
    else()
        message(WARNING "python3 not found: taillight guide regression tests disabled")
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
endif()
