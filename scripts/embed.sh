#!/usr/bin/env bash

shopt -s nullglob

# Find MKV files
videos=( *.mkv *.mp4 )

if [ ${#videos[@]} -eq 0 ]; then
    echo "No .mkv/mp4 files found in the current folder."
    exit 1
fi

echo "Available episodes:"
for i in "${!videos[@]}"; do
    printf '[%d]%s\n' "$((i + 1))" "${videos[$i]}"
done

echo
read -rp "Select the episode number: " video_num

if ! [[ "$video_num" =~ ^[0-9]+$ ]] || (( video_num < 1 || video_num > ${#videos[@]} )); then
    echo "Invalid episode selection."
    exit 1
fi

video="${videos[$((video_num - 1))]}"

# Find ASS and SRT subtitle files
subtitles=( *.ass *.srt )

if [ ${#subtitles[@]} -eq 0 ]; then
    echo "No .ass or .srt subtitle files found in the current folder."
    exit 1
fi

echo
echo "Available subtitles:"
for i in "${!subtitles[@]}"; do
    printf '[%d]%s\n' "$((i + 1))" "${subtitles[$i]}"
done

echo
read -rp "Select the subtitle number: " subtitle_num

if ! [[ "$subtitle_num" =~ ^[0-9]+$ ]] || (( subtitle_num < 1 || subtitle_num > ${#subtitles[@]} )); then
    echo "Invalid subtitle selection."
    exit 1
fi

subtitle="${subtitles[$((subtitle_num - 1))]}"

# Output filename
output="${video%.mkv}[modified].mkv"

echo
echo "Video:    $video"
echo "Subtitle: $subtitle"
echo "Output:   $output"
echo
read -rp "Proceed? [y/N]: " confirm

if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi

echo
echo "Embedding subtitle without re-encoding..."
echo

# Add subtitle without re-encoding video/audio/subtitle.
ffmpeg -i "$video" -i "$subtitle" \
    -map 0 \
    -map 1:0 \
    -c copy \
    -metadata:s:s:0 language=eng \
    "$output"

if [ $? -eq 0 ]; then
    echo
    echo "Successfully created:"
    echo "$output"

    rm -- "$video"

    echo
    echo "Original file deleted:"
    echo "$video"
else
    echo
    echo "FFmpeg failed."
    echo "The original file was NOT deleted."

    # Remove incomplete output if one was created
    rm -f -- "$output"

    exit 1
fi
