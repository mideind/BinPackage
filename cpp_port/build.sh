#!/bin/bash

# Build script for Íslenska C++ library

# Create build directory
mkdir -p build
cd build

# Configure with CMake
echo "Configuring project..."
cmake -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTS=ON ..

# Build
echo "Building..."
make -j$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 1)

# Run tests if build succeeded
if [ $? -eq 0 ]; then
    echo ""
    echo "Build successful! Running tests..."
    echo ""
    
    if [ -f test_lookup ]; then
        echo "=== Running lookup test ==="
        ./test_lookup
    fi
    
    if [ -f test_variants ]; then
        echo ""
        echo "=== Running variants test ==="
        ./test_variants
    fi
else
    echo "Build failed!"
    exit 1
fi