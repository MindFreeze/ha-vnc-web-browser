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
    depth=$(echo $display | jq -r '.depth // 16')
    view_only=$(echo $display | jq -r '.view_only // false')
    browser_args=$(echo $display | jq -r '.browser_args // ""')
    cdp_port=$(echo $display | jq -r '.cdp_port // empty')
    display_number=$((port - 5900))

    # Chrome DevTools Protocol setup.
    # Chromium M113+ silently ignores --remote-debugging-address=0.0.0.0 and binds
    # 127.0.0.1 (upstream WontFix: crbug.com/40261787). We work around it by binding
    # Chromium to an internal loopback port and forwarding via socat so the CDP
    # endpoint is reachable from sibling addons / the host.
    if [ -n "$cdp_port" ]; then
        internal_cdp_port=$((cdp_port + 100))
        # Strip any user-supplied remote-debugging flags to avoid port collisions
        browser_args=$(echo "$browser_args" | sed -E 's/--remote-debugging-port=[^ ]*//g; s/--remote-debugging-address=[^ ]*//g; s/--remote-allow-origins=[^ ]*//g')
        # Append our managed CDP flags. --remote-allow-origins is required for
        # WebSocket upgrades from non-localhost callers (Playwright, Puppeteer, etc).
        browser_args="$browser_args --remote-debugging-port=$internal_cdp_port --remote-allow-origins=*"
        # Forwarder: external 0.0.0.0:$cdp_port -> chromium 127.0.0.1:$internal_cdp_port
        echo "Starting CDP forwarder for display $display_number: 0.0.0.0:$cdp_port -> 127.0.0.1:$internal_cdp_port"
        socat TCP4-LISTEN:$cdp_port,fork,reuseaddr,bind=0.0.0.0 TCP4:127.0.0.1:$internal_cdp_port &
    fi

    # Split resolution into width and height
    width=$(echo $resolution | cut -d'x' -f1)
    height=$(echo $resolution | cut -d'x' -f2)

    # Build VNC server options
    vnc_opts="-geometry ${width}x${height} -depth ${depth} -nevershared -rfbport $port -alwaysshared"
    if [ "$view_only" = "true" ]; then
        vnc_opts="$vnc_opts -viewonly"
    fi

    # Start a new VNC server for this display
    if [ ! -f "/home/vnc_user/.vnc/passwd" ]; then
        echo "Starting VNC server without password for display $display_number"
        Xvnc :$display_number $vnc_opts &
    else
        echo "Starting VNC server with password for display $display_number"
        Xvnc :$display_number $vnc_opts -rfbauth /home/vnc_user/.vnc/passwd &
    fi

    # Wait a moment for the VNC server to start
    sleep 2

    # Set the display resolution
    DISPLAY=:$display_number xrandr --output default --mode ${width}x${height}

    # Start Chromium in kiosk mode for this display
    DISPLAY=:$display_number chromium --new-window --no-sandbox --disable-gpu --kiosk --window-size=${width},${height} --window-position=0,0 --no-first-run --no-default-browser-check --disable-translate --disable-infobars --disable-suggestions-service --disable-save-password-bubble --user-data-dir="/data/chromium-data-$display_number" --load-preferences="/home/vnc_user/chromium_preferences.json" $browser_args "$url" &
done <<< "$displays"

# Keep the script running
tail -f /dev/null 