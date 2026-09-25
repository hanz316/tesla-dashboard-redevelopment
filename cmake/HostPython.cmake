# Pixel regressions are required host checks. If the selected interpreter lacks
# their dependencies, use a build-local venv, never mutate system Python and
# never silently skip the tests. Offline builders can provision dependencies
# themselves and disable bootstrapping.
option(DASHBOARD_BOOTSTRAP_HOST_PYTHON "Install missing pixel-test dependencies into a build-local venv" ON)
execute_process(COMMAND "${PYTHON3_EXECUTABLE}" -c "import PIL, numpy"
                RESULT_VARIABLE _pixel_import OUTPUT_QUIET ERROR_QUIET)
if(NOT _pixel_import EQUAL 0)
    if(NOT DASHBOARD_BOOTSTRAP_HOST_PYTHON)
        message(FATAL_ERROR "Install tools/requirements-host.txt into PYTHON3_EXECUTABLE before configuring host tests")
    endif()
    set(_host_venv "${CMAKE_BINARY_DIR}/host-python")
    execute_process(COMMAND "${PYTHON3_EXECUTABLE}" -m venv "${_host_venv}"
                    RESULT_VARIABLE _venv_result)
    if(NOT _venv_result EQUAL 0)
        message(FATAL_ERROR "Unable to create host test Python environment")
    endif()
    if(WIN32)
        set(_host_python "${_host_venv}/Scripts/python.exe")
    else()
        set(_host_python "${_host_venv}/bin/python")
    endif()
    execute_process(COMMAND "${_host_python}" -m pip install
                    -r "${CMAKE_CURRENT_SOURCE_DIR}/tools/requirements-host.txt"
                    RESULT_VARIABLE _pip_result)
    if(NOT _pip_result EQUAL 0)
        message(FATAL_ERROR "Host pixel-test dependency installation failed")
    endif()
    set(PYTHON3_EXECUTABLE "${_host_python}")
endif()
