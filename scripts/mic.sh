#!/usr/bin/env bash

# Exit on error
set -e

echo "🔍 Detecting input (microphone) devices..."

# Get list of input devices (PipeWire nodes with input capability)
mapfile -t devices < <(pw-cli ls Node | awk '
/id [0-9]+,/ {id=$2}
/node.name/ {name=$3}
/media.class = "Audio\/Source"/ {
    gsub(/"/, "", name)
    print id "|" name
}
')

# Check if any devices found
if [ ${#devices[@]} -eq 0 ]; then
    echo "❌ No audio input devices found."
    exit 1
fi

echo ""
echo "🎤 Available microphones:"
for i in "${!devices[@]}"; do
    IFS="|" read -r id name <<< "${devices[$i]}"
    echo "[$i] $name (ID: $id)"
done

echo ""
read -rp "Select a device number: " choice

# Validate input
if ! [[ "$choice" =~ ^[0-9]+$ ]] || [ "$choice" -ge "${#devices[@]}" ]; then
    echo "❌ Invalid selection."
    exit 1
fi

IFS="|" read -r selected_id selected_name <<< "${devices[$choice]}"

echo ""
echo "✅ Using device: $selected_name (ID: $selected_id)"
echo "🔊 Starting loopback..."

# Run pw-loopback
pw-loopback --latency 1024 --capture-props="node.id=$selected_id"
