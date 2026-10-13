cmake_minimum_required(VERSION 3.20)

# KineticOS Configurator, GTK 4 (gtkmm) application.
project(kinetic-configurator VERSION 0.4.0 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

include(GNUInstallDirs)
include(CTest)

if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    add_compile_options($<$<COMPILE_LANGUAGE:CXX>:-Wall> $<$<COMPILE_LANGUAGE:CXX>:-Wextra>
                        $<$<COMPILE_LANGUAGE:CXX>:-Wpedantic> $<$<COMPILE_LANGUAGE:CXX>:-Werror>)
endif()

option(KINETIC_CONFIGURATOR_ENABLE_SANITIZERS
    "Enable AddressSanitizer and UndefinedBehaviorSanitizer" OFF)
if(KINETIC_CONFIGURATOR_ENABLE_SANITIZERS AND CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    add_compile_options(-fsanitize=address,undefined -fno-omit-frame-pointer)
    add_link_options(-fsanitize=address,undefined)
endif()

find_package(PkgConfig REQUIRED)
pkg_check_modules(GTKMM REQUIRED IMPORTED_TARGET gtkmm-4.0>=4.20)
pkg_check_modules(ADWAITA REQUIRED IMPORTED_TARGET libadwaita-1>=1.6)
find_program(GLIB_COMPILE_RESOURCES glib-compile-resources REQUIRED)

set(KINETIC_REPO_ROOT ${PROJECT_SOURCE_DIR}/..)

# --- resources -----------------------------------------------------------------

set(RESOURCE_XML ${PROJECT_SOURCE_DIR}/data/kinetic.gresource.xml)
set(RESOURCE_C ${CMAKE_CURRENT_BINARY_DIR}/kinetic-resources.c)
set(RESOURCE_DEPS
    ${PROJECT_SOURCE_DIR}/data/style.css
    ${KINETIC_REPO_ROOT}/HELP.md
    ${KINETIC_REPO_ROOT}/packaging/icons/256x256/kinetic-configurator.png)
add_custom_command(
    OUTPUT ${RESOURCE_C}
    COMMAND ${GLIB_COMPILE_RESOURCES} --generate-source --target=${RESOURCE_C}
            --sourcedir=${PROJECT_SOURCE_DIR}/data --sourcedir=${KINETIC_REPO_ROOT}
            ${RESOURCE_XML}
    DEPENDS ${RESOURCE_XML} ${RESOURCE_DEPS}
    VERBATIM)
set_source_files_properties(${RESOURCE_C} PROPERTIES COMPILE_OPTIONS "-w")

# --- core (no widgets; testable) --------------------------------------------------

add_library(kinetic_core STATIC
    src/core/process.cpp
    src/core/process.h
    src/core/project.cpp
    src/core/project.h
    src/core/settings.cpp
    src/core/settings.h
    src/core/template_sync.cpp
    src/core/template_sync.h
    src/core/theme.cpp
    src/core/theme.h
    src/core/workspace.cpp
    src/core/workspace.h
)
target_include_directories(kinetic_core PUBLIC ${PROJECT_SOURCE_DIR}/src)
target_link_libraries(kinetic_core PUBLIC PkgConfig::GTKMM)

# --- application -----------------------------------------------------------------

add_executable(kinetic-configurator
    ${RESOURCE_C}
    src/main.cpp
    src/ui/buildconsole.cpp
    src/ui/buildconsole.h
    src/ui/chooser.cpp
    src/ui/chooser.h
    src/ui/helpwindow.cpp
    src/ui/helpwindow.h
    src/ui/pages.cpp
    src/ui/pages.h
    src/ui/themewatcher.cpp
    src/ui/themewatcher.h
    src/ui/window.cpp
    src/ui/window.h
)
target_compile_definitions(kinetic-configurator PRIVATE
    KINETIC_CONFIGURATOR_VERSION="${PROJECT_VERSION}")
target_link_libraries(kinetic-configurator PRIVATE kinetic_core PkgConfig::ADWAITA)

set(APP_ID com.weecraglinux.kinetic-configurator)
install(TARGETS kinetic-configurator RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR})
install(FILES ${KINETIC_REPO_ROOT}/packaging/${APP_ID}.desktop
    DESTINATION ${CMAKE_INSTALL_DATADIR}/applications)
install(FILES ${KINETIC_REPO_ROOT}/packaging/${APP_ID}.metainfo.xml
    DESTINATION ${CMAKE_INSTALL_DATADIR}/metainfo)
foreach(size 48 64 128 256)
    install(FILES ${KINETIC_REPO_ROOT}/packaging/icons/${size}x${size}/kinetic-configurator.png
        DESTINATION ${CMAKE_INSTALL_DATADIR}/icons/hicolor/${size}x${size}/apps)
endforeach()

# --- privileged helper (the only code that runs as root) --------------------------

add_executable(kinetic-configurator-helper src/helper/helper.cpp)
install(TARGETS kinetic-configurator-helper
    RUNTIME DESTINATION ${CMAKE_INSTALL_LIBEXECDIR}/kinetic-configurator)
install(FILES ${KINETIC_REPO_ROOT}/packaging/com.weecraglinux.kinetic-configurator.run-helper.policy
    DESTINATION ${CMAKE_INSTALL_DATADIR}/polkit-1/actions)

# --- tests -----------------------------------------------------------------------

if(BUILD_TESTING)
    foreach(test project template_sync workspace settings theme)
        add_executable(${test}_test tests/${test}_test.cpp)
        target_link_libraries(${test}_test PRIVATE kinetic_core)
        add_test(NAME ${test} COMMAND ${test}_test)
    endforeach()
    # g_test_skip() reports 77 under the TAP harness.
    set_tests_properties(project template_sync workspace settings theme
        PROPERTIES SKIP_RETURN_CODE 77)
endif()
