#!/usr/bin/env bash
set -euo pipefail

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}Starting N-dark installation...${NC}"

# Ensure we are in the directory where the script lives (repo root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check required files
if [[ ! -f "config.tar.gz" ]]; then
    echo -e "${RED}Error: config.tar.gz not found in $SCRIPT_DIR${NC}"
    exit 1
fi

if [[ ! -f "default.png" ]]; then
    echo -e "${RED}Error: default.png not found in $SCRIPT_DIR${NC}"
    exit 1
fi

# 1. Extract config.tar.gz into a temporary directory
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

echo -e "${YELLOW}Extracting config.tar.gz...${NC}"
tar -xzf config.tar.gz -C "$TMP_DIR"

# 2. Move extracted folders into ~/.config (overwrite existing)
CONFIG_DIR="$HOME/.config"
mkdir -p "$CONFIG_DIR"

echo -e "${YELLOW}Installing configuration folders into ~/.config...${NC}"
for item in "$TMP_DIR"/*; do
    name=$(basename "$item")
    if [[ -d "$item" ]]; then
        # Remove existing folder if it exists, then move the new one
        rm -rf "$CONFIG_DIR/$name"
        mv "$item" "$CONFIG_DIR/"
        echo -e "  → Installed: ~/.config/$name"
    fi
done

# 3. Create ~/Pictures/wallpapers and copy default.png
PICTURES_DIR="$HOME/Pictures"
WALLPAPERS_DIR="$PICTURES_DIR/wallpapers"

echo -e "${YELLOW}Setting up wallpapers directory...${NC}"
mkdir -p "$WALLPAPERS_DIR"
cp -f "default.png" "$WALLPAPERS_DIR/"
echo -e "  → Copied default.png → ~/Pictures/wallpapers/default.png"

echo -e "${GREEN}Installation complete!${NC}"
echo -e "Configs are in ~/.config and wallpaper is in ~/Pictures/wallpapers/"
