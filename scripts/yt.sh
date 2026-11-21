
#!/usr/bin/env bash

# ==========================================
# YouTube Video & Audio Downloader
# Requires: yt-dlp, ffmpeg, python3
# ==========================================

VIDEO_DIR="$HOME/Videos/yt"
AUDIO_DIR="$HOME/Music/yt"

# Colors
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
RESET='\033[0m'

clear

echo -e "${CYAN}"
echo "======================================"
echo "       YOUTUBE DOWNLOADER"
echo "======================================"
echo -e "${RESET}"

# ------------------------------------------
# Check dependencies
# ------------------------------------------

for cmd in yt-dlp ffmpeg python3; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo -e "${RED}Error: $cmd is not installed.${RESET}"
        exit 1
    fi
done

# ------------------------------------------
# Create download directories
# ------------------------------------------

mkdir -p "$VIDEO_DIR" "$AUDIO_DIR" || {
    echo -e "${RED}Could not create download directories.${RESET}"
    exit 1
}

# ------------------------------------------
# Ask for URL
# ------------------------------------------

read -rp "Paste YouTube URL: " URL

if [[ -z "$URL" ]]; then
    echo -e "${RED}No URL provided.${RESET}"
    exit 1
fi

echo
echo "What do you want to download?"
echo "1) Video"
echo "2) Audio"

read -rp "Select [1-2]: " TYPE

# ==========================================
# VIDEO DOWNLOAD
# ==========================================

case "$TYPE" in

    1)

        echo
        echo -e "${GREEN}Fetching ALL available video qualities...${RESET}"

        # Temporary metadata file
        INFO_FILE=$(mktemp) || exit 1
        trap 'rm -f "$INFO_FILE"' EXIT

        # Fetch complete format information
        if ! yt-dlp \
            --dump-single-json \
            --skip-download \
            --no-warnings \
            --no-playlist \
            "$URL" > "$INFO_FILE"; then

            echo -e "${RED}Could not fetch video information.${RESET}"
            exit 1
        fi

        # Extract ALL unique video heights
        QUALITY_OUTPUT=$(python3 - "$INFO_FILE" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as f:
    data = json.load(f)

heights = set()

for fmt in data.get("formats", []):
    if fmt.get("vcodec") != "none" and fmt.get("height"):
        heights.add(int(fmt["height"]))

for height in sorted(heights, reverse=True):
    print(height)
PY
        ) || {
            echo -e "${RED}Could not read video qualities.${RESET}"
            exit 1
        }

        if [[ -z "$QUALITY_OUTPUT" ]]; then
            echo -e "${RED}No video qualities found.${RESET}"
            exit 1
        fi

        mapfile -t QUALITIES <<< "$QUALITY_OUTPUT"

        echo
        echo -e "${CYAN}Available video resolutions:${RESET}"
        echo

        for i in "${!QUALITIES[@]}"; do
            echo "$((i+1))) ${QUALITIES[$i]}p"
        done

        echo
        read -rp "Select quality: " Q

        if ! [[ "$Q" =~ ^[0-9]+$ ]] ||
           (( Q < 1 || Q > ${#QUALITIES[@]} )); then

            echo -e "${RED}Invalid selection.${RESET}"
            exit 1
        fi

        HEIGHT="${QUALITIES[$((Q-1))]}"

        echo
        echo "Select video format:"
        echo "1) MP4"
        echo "2) MKV"

        read -rp "Select [1-2]: " FORMAT

        case "$FORMAT" in
            1) EXT="mp4" ;;
            2) EXT="mkv" ;;
            *)
                echo -e "${RED}Invalid format.${RESET}"
                exit 1
                ;;
        esac

        echo
        echo -e "${GREEN}Downloading ${HEIGHT}p video...${RESET}"
        echo

        yt-dlp \
            -f "bestvideo[height=${HEIGHT}]+bestaudio/best[height=${HEIGHT}]" \
            --merge-output-format "$EXT" \
            --embed-metadata \
            -o "$VIDEO_DIR/%(title)s.%(ext)s" \
            "$URL"

        STATUS=$?

        ;;

# ==========================================
# AUDIO DOWNLOAD
# ==========================================

    2)

        echo
        echo "Select audio quality:"
        echo
        echo "1) Best available"
        echo "2) 320 kbps"
        echo "3) 256 kbps"
        echo "4) 192 kbps"
        echo "5) 128 kbps"

        read -rp "Select [1-5]: " QUALITY

        case "$QUALITY" in
            1) BITRATE="0" ;;
            2) BITRATE="320" ;;
            3) BITRATE="256" ;;
            4) BITRATE="192" ;;
            5) BITRATE="128" ;;
            *)
                echo -e "${RED}Invalid selection.${RESET}"
                exit 1
                ;;
        esac

        echo
        echo "Select audio format:"
        echo
        echo "1) FLAC"
        echo "2) MP3"

        read -rp "Select [1-2]: " FORMAT

        case "$FORMAT" in

            1)
                EXT="flac"
                AUDIO_ARGS=(--audio-format flac)
                ;;

            2)
                EXT="mp3"
                AUDIO_ARGS=(--audio-format mp3 --audio-quality "${BITRATE}K")
                ;;

            *)
                echo -e "${RED}Invalid format.${RESET}"
                exit 1
                ;;
        esac

        # Best available MP3 conversion quality
        if [[ "$QUALITY" == "1" && "$EXT" == "mp3" ]]; then
            AUDIO_ARGS=(--audio-format mp3 --audio-quality 0)
        fi

        echo
        echo -e "${GREEN}Starting audio download...${RESET}"
        echo

        yt-dlp \
            -x \
            "${AUDIO_ARGS[@]}" \
            --embed-metadata \
            -o "$AUDIO_DIR/%(title)s.%(ext)s" \
            "$URL"

        STATUS=$?

        ;;

    *)

        echo -e "${RED}Invalid selection.${RESET}"
        exit 1
        ;;

esac

# ==========================================
# FINISH
# ==========================================

echo

if [[ "$STATUS" -eq 0 ]]; then
    echo -e "${GREEN}"
    echo "======================================"
    echo "          DOWNLOAD FINISHED"
    echo "======================================"
    echo -e "${RESET}"
else
    echo -e "${RED}"
    echo "======================================"
    echo "          DOWNLOAD FAILED"
    echo "======================================"
    echo -e "${RESET}"
    exit "$STATUS"
fi
