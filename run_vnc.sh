#!/bin/bash

config="$1"

# Start D-Bus
dbus-daemon --system --fork

# Remove any existing VNC lock files
rm -rf /tmp/.X*-lock /tmp/.X11-unix

# Extract display configurations
displays=$(echo "$config" | jq -c '.displays[]')

# Loop through each display configuration
while IFS= read -r display; do
    url=$(echo $display | jq -r '.url')
    resolution=$(echo $display | jq -r '.resolution')
    port=$(echo $display | jq -r '.port')
    display_number=$((port - 5900))

    # Split resolution into width and height
    width=$(echo $resolution | cut -d'x' -f1)
    height=$(echo $resolution | cut -d'x' -f2)

    # Start a new VNC server for this display
    if [ ! -f "/home/vnc_user/.vnc/passwd" ]; then
        echo "Starting VNC server without password for display $display_number"
        Xvnc :$display_number -geometry ${width}x${height} -depth 16 -nevershared -rfbport $port -alwaysshared &
    else
        echo "Starting VNC server with password for display $display_number"
        Xvnc :$display_number -geometry ${width}x${height} -depth 16 -nevershared -rfbport $port -alwaysshared -rfbauth /home/vnc_user/.vnc/passwd &
    fi

    # Wait a moment for the VNC server to start
    sleep 2

    # Start Chromium in kiosk mode for this display
    DISPLAY=:$display_number chromium --new-window --no-sandbox --disable-gpu --kiosk --no-first-run --no-default-browser-check --disable-translate --disable-infobars --disable-suggestions-service --disable-save-password-bubble --user-data-dir="/home/vnc_user/data-$display_number" --load-preferences="/home/vnc_user/chromium_preferences.json" "$url" &
done <<< "$displays"

# Keep the script running
tail -f /dev/null 