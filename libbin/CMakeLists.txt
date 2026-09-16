cmake_minimum_required(VERSION 3.20)
project(libbin CXX)

# libbin: the compressed BÍN dictionary and compounder of BinPackage as a
# self-contained C++ library with a C API (include/libbin/bin.h). The
# Python package builds the same sources through CFFI (src/islenska/bin_build.py);
# other consumers add this directory with add_subdirectory() or
# FetchContent and link the target libbin::bin.

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
  set(CMAKE_BUILD_TYPE Release)
endif()

# The sources are compiled once, as an object library, so that a consumer
# that ships a single static archive (an iOS xcframework, an Android JNI
# library) can fold them into its own target with
# $<TARGET_OBJECTS:libbin_objects> instead of linking a second archive.
add_library(libbin_objects OBJECT
  src/trie.cpp
  src/dawg.cpp
  src/dict.cpp
  src/api.cpp)
add_library(libbin::objects ALIAS libbin_objects)
target_include_directories(libbin_objects
  PUBLIC $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  PRIVATE src)
set_target_properties(libbin_objects PROPERTIES POSITION_INDEPENDENT_CODE ON)
if(NOT MSVC)
  target_compile_options(libbin_objects PRIVATE -Wall -Wextra)
endif()

add_library(bin STATIC $<TARGET_OBJECTS:libbin_objects>)
add_library(libbin::bin ALIAS bin)
target_include_directories(bin PUBLIC $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>)
set_target_properties(bin PROPERTIES OUTPUT_NAME bin)

# The test program needs the data files of a BinPackage checkout
# (src/islenska/resources/compressed.bin and the three DAWGs), which are
# built with tools/binpack.py and tools/dawgbuilder.py.
option(LIBBIN_TESTS "Build the libbin test program" ${PROJECT_IS_TOP_LEVEL})
if(LIBBIN_TESTS)
  enable_testing()
  add_executable(bin_test tests/bin_test.cpp)
  target_link_libraries(bin_test PRIVATE libbin::bin)
  add_test(NAME libbin COMMAND bin_test ${CMAKE_CURRENT_SOURCE_DIR}/../src/islenska/resources)
endif()
