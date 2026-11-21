#!/usr/bin/env bash

# Rename recovered MKV files using their embedded MediaInfo title.
#
# Requirements:
#   - bash
#   - mediainfo
#
# Usage:
#   ./rename-mkv.sh
#   ./rename-mkv.sh /path/to/recovered/files
#
# By default this is a DRY RUN.
# To actually rename files:
#   ./rename-mkv.sh /path/to/recovered/files --rename

set -u

DIRECTORY="."
DO_RENAME=false

# -----------------------------
# Parse arguments
# -----------------------------

for arg in "$@"; do
    case "$arg" in
        --rename)
            DO_RENAME=true
            ;;
        --help|-h)
            echo "Usage: $0 [directory] [--rename]"
            echo
            echo "Without --rename, only shows what would happen."
            echo "Use --rename to actually rename files."
            exit 0
            ;;
        *)
            DIRECTORY="$arg"
            ;;
    esac
done

# -----------------------------
# Check dependencies
# -----------------------------

if ! command -v mediainfo >/dev/null 2>&1; then
    echo "Error: mediainfo is not installed."
    echo
    echo "Debian/Ubuntu:"
    echo "  sudo apt install mediainfo"
    echo
    echo "Arch:"
    echo "  sudo pacman -S mediainfo"
    exit 1
fi

if [[ ! -d "$DIRECTORY" ]]; then
    echo "Error: directory does not exist: $DIRECTORY"
    exit 1
fi

# -----------------------------
# Sanitize filename
# -----------------------------

sanitize_filename() {
    local name="$1"

    # Remove characters that are problematic in filenames.
    name="${name//\//-}"
    name="${name//\\/-}"
    name="${name//:/ -}"
    name="${name//\?/-}"
    name="${name//\*/-}"
    name="${name//\"/-}"
    name="${name//</-}"
    name="${name//>/-}"
    name="${name//|/-}"

    # Remove leading/trailing whitespace.
    name="$(printf '%s' "$name" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"

    # Collapse repeated spaces.
    name="$(printf '%s' "$name" | sed 's/[[:space:]][[:space:]]*/ /g')"

    # Avoid filenames ending in a dot or space.
    name="$(printf '%s' "$name" | sed 's/[. ]*$//')"

    printf '%s' "$name"
}

# -----------------------------
# Process files
# -----------------------------

find "$DIRECTORY" -maxdepth 1 -type f -iname '*.mkv' -print0 |
while IFS= read -r -d '' file; do

    directory="$(dirname "$file")"
    old_name="$(basename "$file")"

    # Get the embedded container title.
    title="$(mediainfo --Inform='General;%Title%' "$file" 2>/dev/null)"

    # Remove CR/LF just in case.
    title="$(printf '%s' "$title" | tr -d '\r\n')"

    if [[ -z "$title" ]]; then
        echo "SKIP: No embedded title:"
        echo "      $old_name"
        echo
        continue
    fi

    title="$(sanitize_filename "$title")"

    if [[ -z "$title" ]]; then
        echo "SKIP: Invalid/empty title:"
        echo "      $old_name"
        echo
        continue
    fi

    new_file="$directory/$title.mkv"

    # Already has the desired name.
    if [[ "$file" == "$new_file" ]]; then
        echo "OK:   $old_name"
        continue
    fi

    # Avoid overwriting an existing file.
    if [[ -e "$new_file" ]]; then
        echo "SKIP: Target already exists:"
        echo "      $old_name"
        echo "   -> $title.mkv"
        echo
        continue
    fi

    if [[ "$DO_RENAME" == true ]]; then
        if mv -- "$file" "$new_file"; then
            echo "RENAMED:"
            echo "   $old_name"
            echo "-> $title.mkv"
        else
            echo "ERROR: Failed to rename:"
            echo "   $old_name"
        fi
    else
        echo "WOULD RENAME:"
        echo "   $old_name"
        echo "-> $title.mkv"
    fi

    echo

done
