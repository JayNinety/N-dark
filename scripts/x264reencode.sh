#!/usr/bin/env bash

set -u

# Check dependencies
if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "Error: ffmpeg is not installed."
    exit 1
fi

# Find video files in the current directory
mapfile -d '' files < <(
    find . -maxdepth 1 -type f \
        \( -iname '*.mkv' -o -iname '*.mp4' \) \
        -print0 | sort -z
)

if [ "${#files[@]}" -eq 0 ]; then
    echo "No .mkv or .mp4 files found in the current folder."
    exit 1
fi

echo "Videos found:"
echo

for i in "${!files[@]}"; do
    filename="${files[$i]#./}"
    echo "[$((i + 1))] $filename"
done

echo
read -rp "Enter the number of the file you want to reencode: " choice

# Validate input
if ! [[ "$choice" =~ ^[0-9]+$ ]] || \
   (( choice < 1 || choice > ${#files[@]} )); then
    echo "Invalid selection."
    exit 1
fi

input="${files[$((choice - 1))]}"
input_name="${input#./}"

# Get filename without extension
base="${input_name%.*}"
extension="${input_name##*.}"

# Output filename
output="${base}[x264-8BIT].${extension}"

echo
echo "Input : $input_name"
echo "Output: $output"
echo

# Don't overwrite an existing output file
if [ -e "$output" ]; then
    echo "Error: output file already exists:"
    echo "$output"
    exit 1
fi

echo "Starting encode..."
echo

ffmpeg -hide_banner -i "$input" \
    -map 0 \
    -c:v libx264 \
    -pix_fmt yuv420p \
    -preset superfast \
    -crf 20 \
    -c:a copy \
    -c:s copy \
    -map_metadata 0 \
    "$output"

# Only delete original if FFmpeg succeeded
if [ $? -eq 0 ] && [ -f "$output" ]; then
    echo
    echo "Encode completed successfully."
    echo "Deleting original file..."
    rm -- "$input"

    echo
    echo "Done:"
    echo "$output"
else
    echo
    echo "ERROR: Encoding failed."
    echo "The original file was NOT deleted."
    rm -f -- "$output"
    exit 1
fi
