# This file is part of Telegram Desktop,
# the official desktop application for the Telegram messaging service.
#
# For license and copyright information please follow this link:
# https://github.com/telegramdesktop/tdesktop/blob/master/LEGAL

cmake_minimum_required(VERSION 3.25...3.31)

set_property(GLOBAL PROPERTY USE_FOLDERS ON)

set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
    "${CMAKE_CURRENT_SOURCE_DIR}/version.txt")

if (EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/version.txt")
    file(STRINGS "${CMAKE_CURRENT_SOURCE_DIR}/version.txt" _ver_line LIMIT_COUNT 1)
    string(STRIP "${_ver_line}" APP_VERSION)
    if (APP_VERSION MATCHES "^([0-9]+)\\.([0-9]+)(\\.([0-9]+))?")
        set(_ver_major "${CMAKE_MATCH_1}")
        set(_ver_minor "${CMAKE_MATCH_2}")
        if (CMAKE_MATCH_4)
            set(_ver_patch "${CMAKE_MATCH_4}")
        else()
            set(_ver_patch "0")
        endif()
        math(EXPR _ver_full "(${_ver_major} * 1000000) + (${_ver_minor} * 1000) + ${_ver_patch}")
        set(APP_VERSION_FULL "${_ver_full}")
        set(_ver_str_major "${_ver_major}.${_ver_minor}")
        set(_ver_str "${_ver_major}.${_ver_minor}.${_ver_patch}")
        file(WRITE "${CMAKE_CURRENT_SOURCE_DIR}/Telegram/build/version"
"AppVersion         ${_ver_full}
AppVersionStrMajor ${_ver_str_major}
AppVersionStrSmall ${_ver_str}
AppVersionStr      ${_ver_str}
BetaChannel        0
AlphaVersion       0
AppVersionOriginal ${_ver_str}
")
    endif()

    if (EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/version.h.in")
        configure_file(
            "${CMAKE_CURRENT_SOURCE_DIR}/version.h.in"
            "${CMAKE_BINARY_DIR}/version_generated.h"
            @ONLY
        )
        configure_file(
            "${CMAKE_CURRENT_SOURCE_DIR}/version.h.in"
            "${CMAKE_CURRENT_SOURCE_DIR}/Telegram/SourceFiles/version_generated.h"
            @ONLY
        )
    endif()
endif()

include(cmake/validate_special_target.cmake)
include(cmake/version.cmake)
desktop_app_parse_version(Telegram/build/version)

if (NOT DEFINED CMAKE_CONFIGURATION_TYPES)
    set(configuration_types_init 1)
endif()

project(Telegram
    LANGUAGES C CXX
    VERSION ${desktop_app_version_cmake}
    DESCRIPTION "Official Telegram Desktop messenger"
    HOMEPAGE_URL "https://desktop.telegram.org"
)

set(CMAKE_BUILD_WITH_INSTALL_RPATH ON)

if (APPLE)
    enable_language(OBJC OBJCXX)
endif()

option(DESKTOP_APP_USE_COMPILER_CACHE "Enable ccache/sccache object file cache for faster builds" ON)
if (DESKTOP_APP_USE_COMPILER_CACHE)
    find_program(COMPILER_CACHE_PROGRAM NAMES sccache ccache)
    if (COMPILER_CACHE_PROGRAM)
        message(STATUS "Compiler cache enabled: ${COMPILER_CACHE_PROGRAM}")
        set(CMAKE_C_COMPILER_LAUNCHER "${COMPILER_CACHE_PROGRAM}")
        set(CMAKE_CXX_COMPILER_LAUNCHER "${COMPILER_CACHE_PROGRAM}")
        if (APPLE)
            set(CMAKE_OBJC_COMPILER_LAUNCHER "${COMPILER_CACHE_PROGRAM}")
            set(CMAKE_OBJCXX_COMPILER_LAUNCHER "${COMPILER_CACHE_PROGRAM}")
        endif()
        if (MSVC AND COMPILER_CACHE_PROGRAM MATCHES "sccache")
            if (POLICY CMP0141)
                cmake_policy(SET CMP0141 NEW)
            endif()
            set(CMAKE_MSVC_DEBUG_INFORMATION_FORMAT "$<$<CONFIG:Debug,RelWithDebInfo>:Embedded>")
        endif()
    endif()
endif()

if (configuration_types_init
    AND CMAKE_CONFIGURATION_TYPES
    AND NOT MinSizeRel IN_LIST CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_CONFIGURATION_TYPES "${CMAKE_CONFIGURATION_TYPES};MinSizeRel" CACHE STRING "" FORCE)
endif()

set_property(DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR} PROPERTY VS_STARTUP_PROJECT Telegram)

get_filename_component(third_party_loc "Telegram/ThirdParty" REALPATH)
get_filename_component(submodules_loc "Telegram" REALPATH)
get_filename_component(cmake_helpers_loc "cmake" REALPATH)

if (NOT DESKTOP_APP_USE_PACKAGED AND WIN32)
    set(Python3_EXECUTABLE ${CMAKE_CURRENT_SOURCE_DIR}/../ThirdParty/python/Scripts/python)
endif()

include(cmake/variables.cmake)
include(cmake/nice_target_sources.cmake)
include(cmake/target_compile_options_if_exists.cmake)
include(cmake/target_link_frameworks.cmake)
include(cmake/target_link_options_if_exists.cmake)
include(cmake/init_target.cmake)
include(cmake/generate_target.cmake)
if (WIN32)
    include(cmake/nuget.cmake)
    include(cmake/validate_d3d_compiler.cmake)
endif()
include(cmake/target_prepare_qrc.cmake)

include(cmake/options.cmake)

include(cmake/external/qt/package.cmake)

set(desktop_app_skip_libs
    glibmm
    variant
)

add_subdirectory(cmake)
add_subdirectory(Telegram)

set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
    "${CMAKE_SOURCE_DIR}/version.txt")

file(STRINGS "${CMAKE_SOURCE_DIR}/version.txt" _ver_line LIMIT_COUNT 1)
string(REGEX MATCH "^[^/]+" APP_VERSION "${_ver_line}")

configure_file(
    "${CMAKE_SOURCE_DIR}/version.h.in"
    "${CMAKE_BINARY_DIR}/version_generated.h"
    @ONLY
)

target_include_directories(Telegram PRIVATE "${CMAKE_BINARY_DIR}" "${CMAKE_CURRENT_SOURCE_DIR}/Telegram/SourceFiles")

#чтоб на душе был кайф