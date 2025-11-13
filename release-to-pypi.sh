#!/bin/bash
#
# PyPI Release Script for BinPackage
#
# This script automates the process of downloading wheel artifacts from
# GitHub Actions and preparing them for upload to PyPI.
#
# Usage:
#   ./release-to-pypi.sh <github-run-id>
#
# Example:
#   ./release-to-pypi.sh 11734985218
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check if run ID provided
if [ -z "$1" ]; then
    echo -e "${RED}Error: GitHub Actions run ID required${NC}"
    echo "Usage: $0 <github-run-id>"
    echo ""
    echo "Find the run ID with:"
    echo "  gh run list --workflow=wheels.yml --limit 5"
    exit 1
fi

RUN_ID=$1

echo -e "${BLUE}=== BinPackage PyPI Release Script ===${NC}"
echo ""
echo -e "${YELLOW}Run ID: ${RUN_ID}${NC}"
echo ""

# Step 1: Check if run completed successfully
echo -e "${BLUE}Step 1: Checking build status...${NC}"
RUN_STATUS=$(gh run view $RUN_ID --json status,conclusion --jq '.status,.conclusion')
STATUS=$(echo "$RUN_STATUS" | head -1)
CONCLUSION=$(echo "$RUN_STATUS" | tail -1)

if [ "$STATUS" != "completed" ]; then
    echo -e "${YELLOW}Warning: Build is still ${STATUS}${NC}"
    echo "Wait for the build to complete, then run this script again."
    exit 1
fi

if [ "$CONCLUSION" != "success" ]; then
    echo -e "${RED}Error: Build failed with conclusion: ${CONCLUSION}${NC}"
    echo "Fix the build errors before releasing."
    exit 1
fi

echo -e "${GREEN}✓ Build completed successfully${NC}"
echo ""

# Step 2: Download wheel artifacts
echo -e "${BLUE}Step 2: Downloading wheel artifacts...${NC}"
rm -rf dist-wheels dist-release
mkdir -p dist-wheels

gh run download $RUN_ID --dir dist-wheels

echo -e "${GREEN}✓ Artifacts downloaded${NC}"
echo ""

# Step 3: Build source distribution
echo -e "${BLUE}Step 3: Building source distribution...${NC}"

# Check if build tool is installed
if ! python -m build --version &> /dev/null; then
    echo "Installing build tool..."
    python -m pip install --quiet build
fi

python -m build --sdist --outdir dist-wheels/

echo -e "${GREEN}✓ Source distribution built${NC}"
echo ""

# Step 4: Collect all distributions
echo -e "${BLUE}Step 4: Collecting distributions for release...${NC}"
mkdir -p dist-release

# Copy wheels from all platforms
for platform_dir in dist-wheels/dist-*/; do
    if [ -d "$platform_dir" ]; then
        cp "$platform_dir"*.whl dist-release/ 2>/dev/null || true
    fi
done

# Copy source distribution
cp dist-wheels/*.tar.gz dist-release/ 2>/dev/null || true

# Count files
WHEEL_COUNT=$(ls -1 dist-release/*.whl 2>/dev/null | wc -l)
SDIST_COUNT=$(ls -1 dist-release/*.tar.gz 2>/dev/null | wc -l)

echo -e "${GREEN}✓ Collected distributions:${NC}"
echo "  - Wheels: ${WHEEL_COUNT}"
echo "  - Source distributions: ${SDIST_COUNT}"
echo ""

# Step 5: Verify distributions
echo -e "${BLUE}Step 5: Verifying distributions...${NC}"
echo ""
ls -lh dist-release/
echo ""

# Check if twine is installed
if ! python -m twine --version &> /dev/null; then
    echo "Installing twine..."
    python -m pip install --quiet twine
fi

# Run twine check
echo "Running twine check..."
python -m twine check dist-release/*

echo ""
echo -e "${GREEN}✓ All distributions verified${NC}"
echo ""

# Step 6: Instructions for upload
echo -e "${BLUE}=== Ready to Upload to PyPI ===${NC}"
echo ""
echo -e "${YELLOW}⚠️  IMPORTANT: Review the distributions above before uploading!${NC}"
echo ""
echo "To upload to PyPI, run ONE of these commands:"
echo ""
echo -e "${BLUE}Option 1: Test on TestPyPI first (recommended)${NC}"
echo "  python -m twine upload --repository testpypi dist-release/*"
echo ""
echo -e "${BLUE}Option 2: Upload directly to production PyPI${NC}"
echo "  python -m twine upload dist-release/*"
echo ""
echo "After uploading, verify the release at:"
echo "  https://pypi.org/project/islenska/"
echo ""
echo -e "${GREEN}✓ Release preparation complete!${NC}"
