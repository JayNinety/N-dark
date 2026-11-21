#!/bin/bash

shopt -s nullglob nocaseglob

videos=( *.mkv *.mp4 *.avi *.mov *.wmv *.webm *.m4v *.flv *.mpg *.mpeg *.ts )

if [ ${#videos[@]} -eq 0 ]; then
    echo "No video files found in the current folder."
    exit 1
fi

echo "================================"
echo "       VIDEO CONVERTER"
echo "================================"
echo
echo "Available videos:"
echo

for i in "${!videos[@]}"; do
    printf "[%d] %s\n" "$((i + 1))" "${videos[$i]}"
done

echo
read -rp "Select a video (number): " selection

if ! [[ "$selection" =~ ^[0-9]+$ ]] ||
   (( selection < 1 || selection > ${#videos[@]} )); then
    echo "Invalid selection."
    exit 1
fi

input="${videos[$((selection - 1))]}"

echo
echo "Selected: $input"
echo

read -rp "Target resolution (e.g. 720, 480, 360): " resolution

if ! [[ "$resolution" =~ ^[0-9]+$ ]] || (( resolution < 2 )); then
    echo "Invalid resolution."
    exit 1
fi

output="${input%.*}.mp4"

if [[ "$input" == "$output" ]]; then
    output="${input%.*}_converted.mp4"
fi

echo
echo "================================"
echo "Converting video..."
echo "================================"
echo

if ffmpeg -i "$input" \
    -vf "scale=-2:${resolution}" \
    -c:v libx264 -profile:v baseline -level 3.0 \
    -pix_fmt yuv420p -crf 20 \
    -c:a aac -b:a 192k \
    -movflags +faststart \
    "$output"; then

    echo
    echo "================================"
    echo "Conversion successful!"
    echo "Output: $output"
    echo "================================"

else
    echo
    echo "================================"
    echo "Conversion failed!"
    echo "================================"
    exit 1
fi
