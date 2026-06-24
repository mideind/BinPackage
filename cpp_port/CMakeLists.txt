cmake_minimum_required(VERSION 3.14)
project(islenska_cpp VERSION 1.0.0 LANGUAGES CXX)

# Set C++ standard
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Options
option(BUILD_SHARED_LIBS "Build shared library" ON)
option(BUILD_TESTS "Build test programs" ON)

# Include directories
include_directories(
    ${CMAKE_CURRENT_SOURCE_DIR}/include
    ${CMAKE_CURRENT_SOURCE_DIR}/src
    ${CMAKE_CURRENT_SOURCE_DIR}/../src/islenska  # For access to original bin.cpp
)

# Source files
set(SOURCES
    src/islenska.cpp
    src/dawg.cpp
    src/lookup.cpp
    src/variants.cpp
    ../src/islenska/bin.cpp  # Reuse existing trie implementation
)

# Create library
add_library(islenska ${SOURCES})

# Set properties
set_target_properties(islenska PROPERTIES
    VERSION ${PROJECT_VERSION}
    SOVERSION 1
    PUBLIC_HEADER include/islenska.h
)

# Installation
install(TARGETS islenska
    EXPORT islenskaTargets
    LIBRARY DESTINATION lib
    ARCHIVE DESTINATION lib
    RUNTIME DESTINATION bin
    PUBLIC_HEADER DESTINATION include
)

# Platform-specific settings
if(WIN32)
    target_compile_definitions(islenska PRIVATE _CRT_SECURE_NO_WARNINGS)
    if(BUILD_SHARED_LIBS)
        target_compile_definitions(islenska PRIVATE ISLENSKA_EXPORTS)
    endif()
elseif(APPLE)
    set(CMAKE_MACOSX_RPATH ON)
endif()

# Test programs
if(BUILD_TESTS)
    add_executable(test_lookup test/test_lookup.cpp)
    target_link_libraries(test_lookup islenska)
    
    add_executable(test_variants test/test_variants.cpp)
    target_link_libraries(test_variants islenska)
endif()

# Package configuration
include(GNUInstallDirs)
include(CMakePackageConfigHelpers)

# Export targets
install(EXPORT islenskaTargets
    FILE islenskaTargets.cmake
    NAMESPACE islenska::
    DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/islenska
)

# Create package config file
configure_package_config_file(${CMAKE_CURRENT_SOURCE_DIR}/Config.cmake.in
    "${CMAKE_CURRENT_BINARY_DIR}/islenskaConfig.cmake"
    INSTALL_DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/islenska
)

# Create version file
write_basic_package_version_file(
    "${CMAKE_CURRENT_BINARY_DIR}/islenskaConfigVersion.cmake"
    VERSION ${PROJECT_VERSION}
    COMPATIBILITY AnyNewerVersion
)

# Install config files
install(FILES
    "${CMAKE_CURRENT_BINARY_DIR}/islenskaConfig.cmake"
    "${CMAKE_CURRENT_BINARY_DIR}/islenskaConfigVersion.cmake"
    DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/islenska
)