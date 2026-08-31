#!/bin/bash

config="$1"

chromium_pids=()
xvnc_pids=()
internal_cdp_ports=()
token_files=()

is_home_assistant_url() {
    local candidate="$1"
    case "$candidate" in
        *homeassistant*|*hassio*|*:8123/*|*:8123)
            return 0
            ;;
    esac
    return 1
}

append_store_token() {
    local candidate="$1"
    case "$candidate" in
        *storeToken=*)
            echo "$candidate"
            ;;
        *\?*)
            echo "${candidate%%\?*}?storeToken=true&${candidate#*\?}"
            ;;
        *)
            echo "${candidate}?storeToken=true"
            ;;
    esac
}

wait_for_url() {
    local candidate="$1"
    echo "Waiting for $candidate ..."
    for _ in $(seq 1 30); do
        if curl -skfL --max-time 2 -o /dev/null "$candidate"; then
            echo "$candidate is reachable"
            return 0
        fi
        sleep 2
    done
    echo "Timed out waiting for $candidate, starting Chromium anyway"
}

dump_and_close_browsers() {
    local i
    for i in "${!internal_cdp_ports[@]}"; do
        python3 /home/vnc_user/cdp_helper.py dump "${internal_cdp_ports[$i]}" "${token_files[$i]}" 2>/dev/null || true
        python3 /home/vnc_user/cdp_helper.py close "${internal_cdp_ports[$i]}" 2>/dev/null || true
    done
}

cleanup() {
    echo "Shutting down browsers..."
    dump_and_close_browsers
    for pid in "${chromium_pids[@]}"; do
        kill -TERM "$pid" 2>/dev/null || true
    done
    pkill -TERM -f '/data/chromium-data-' 2>/dev/null || true
    pkill -TERM chromium 2>/dev/null || true
    for _ in $(seq 1 40); do
        pgrep -f '/data/chromium-data-' >/dev/null 2>&1 || break
        sleep 0.5
    done
    for pid in "${xvnc_pids[@]}"; do
        kill -TERM "$pid" 2>/dev/null || true
    done
    pkill -f cdp_helper.py 2>/dev/null || true
    exit 0
}
trap cleanup SIGTERM SIGINT

# Start D-Bus
dbus-daemon --system --fork

# Remove any existing VNC lock files
rm -rf /tmp/.X*-lock /tmp/.X11-unix

# Extract display configurations
displays=$(echo "$config" | jq -c '.displays[]')

# Loop through each display configuration
while IFS= read -r display; do
    url=$(echo $display | jq -r '.url // empty')
    resolution=$(echo $display | jq -r '.resolution')
    port=$(echo $display | jq -r '.port')
    depth=$(echo $display | jq -r '.depth // 16')
    view_only=$(echo $display | jq -r '.view_only // false')
    browser_args=$(echo $display | jq -r '.browser_args // ""')
    cdp_port=$(echo $display | jq -r '.cdp_port // empty')
    display_number=$((port - 5900))
    user_data_dir="/data/chromium-data-$display_number"
    token_file="$user_data_dir/hassTokens.json"
    internal_cdp_port=$((9300 + display_number))

    # Always bind an internal CDP port so we can snapshot HA tokens.
    # Chromium M113+ silently ignores --remote-debugging-address=0.0.0.0 and binds
    # 127.0.0.1 (upstream WontFix: crbug.com/40261787). Optional socat still
    # publishes that loopback port when the user sets cdp_port.
    browser_args=$(echo "$browser_args" | sed -E 's/--remote-debugging-port=[^ ]*//g; s/--remote-debugging-address=[^ ]*//g; s/--remote-allow-origins=[^ ]*//g')
    if [ -n "$cdp_port" ]; then
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
    xvnc_pids+=($!)

    # Wait a moment for the VNC server to start
    sleep 2

    # Set the display resolution
    DISPLAY=:$display_number xrandr --output default --mode ${width}x${height}

    # Stale locks from a previous SIGKILL make Chromium skip the persistent profile.
    rm -f "$user_data_dir/SingletonLock" \
          "$user_data_dir/SingletonSocket" \
          "$user_data_dir/SingletonCookie"

    mkdir -p "$user_data_dir/Default"
    # Never keep site usernames/passwords on disk. HA stays logged in via
    # hassTokens only; --password-store=basic would otherwise leave Login Data
    # as weakly protected SQLite in the addon volume.
    rm -f "$user_data_dir/Default/Login Data" \
          "$user_data_dir/Default/Login Data-journal" \
          "$user_data_dir/Default/Login Data For Account" \
          "$user_data_dir/Default/Login Data For Account-journal"
    prefs="$user_data_dir/Default/Preferences"
    if [ ! -f "$prefs" ]; then
        cp /home/vnc_user/chromium_preferences.json "$prefs"
    else
        tmp="$prefs.tmp"
        jq '.credentials_enable_service = false
            | .profile.password_manager_enabled = false
            | .password_manager.enable_save_password_bubble = false
            | .password_manager.saving_enabled = false
            | .password_manager.enable_autosignin = false
            | .autofill.enabled = false
            | .autofill.profile_enabled = false
            | .autofill.credit_card_enabled = false' "$prefs" > "$tmp" && mv "$tmp" "$prefs"
    fi

    if [ -n "$url" ]; then
        wait_for_url "$url"
        if is_home_assistant_url "$url"; then
            url=$(append_store_token "$url")
        fi
    fi

    echo "Starting Chromium for display $display_number (profile $user_data_dir, CDP $internal_cdp_port)"

    # If we already have a token snapshot, start on about:blank so the persist
    # helper can inject hassTokens before HA's frontend runs. Otherwise open
    # the real URL so first-time login is not stuck on a blank kiosk.
    start_url="${url:-about:blank}"
    if [ -f "$token_file" ]; then
        start_url="about:blank"
    fi
    HOME=/data/home \
    XDG_CONFIG_HOME=/data/home/.config \
    XDG_CACHE_HOME=/data/home/.cache \
    CHROME_USER_DATA_DIR="$user_data_dir" \
    DISPLAY=:$display_number chromium \
        --new-window \
        --no-sandbox \
        --disable-gpu \
        --kiosk \
        --window-size=${width},${height} \
        --window-position=0,0 \
        --no-first-run \
        --no-default-browser-check \
        --disable-translate \
        --disable-infobars \
        --disable-suggestions-service \
        --disable-save-password-bubble \
        --password-store=basic \
        --enable-aggressive-domstorage-flushing \
        --disable-backgrounding-occluded-windows \
        --disable-renderer-backgrounding \
        --disable-background-timer-throttling \
        --disable-features=Translate,CalculateNativeWinOcclusion,PasswordCheck \
        --remote-debugging-port=$internal_cdp_port \
        --remote-allow-origins=* \
        --user-data-dir="$user_data_dir" \
        $browser_args \
        "$start_url" &
    chromium_pids+=($!)
    internal_cdp_ports+=($internal_cdp_port)
    token_files+=("$token_file")

    python3 /home/vnc_user/cdp_helper.py persist "$internal_cdp_port" "$token_file" "$url" &
done <<< "$displays"

# Stay up so SIGTERM can flush profiles. Restart wait if a child exits
# (e.g. Chromium crash) so the addon does not bounce.
while true; do
    wait -n || sleep 1
done
