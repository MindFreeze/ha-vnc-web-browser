#!/bin/bash

# Set VNC password only if it's not empty
vnc_password=$(jq -r '.vnc_password // empty' /data/options.json)

if [ -n "$vnc_password" ]; then
    # Create password file
    echo "$vnc_password" | vncpasswd -f > /home/vnc_user/.vnc/passwd
    chmod 600 /home/vnc_user/.vnc/passwd
    chown vnc_user:vnc_user /home/vnc_user/.vnc/passwd
else
    # Remove password file if it exists
    rm -f /home/vnc_user/.vnc/passwd
fi

# vnc_user must read options (including optional HA tokens) without putting
# them on the process command line.
chmod a+r /data/options.json 2>/dev/null || true
mkdir -p /data/home/.config /data/home/.cache
chown -R vnc_user:vnc_user /data/home
displays=$(jq -c '.displays[]' /data/options.json)
while IFS= read -r display; do
    port=$(echo "$display" | jq -r '.port')
    display_number=$((port - 5900))
    mkdir -p "/data/chromium-data-$display_number"
    chown -R vnc_user:vnc_user "/data/chromium-data-$display_number"
done <<< "$displays"

# Drop plaintext Chromium password DBs from earlier builds (Login Data is SQLite).
find /data \( \
    -name 'Login Data' -o \
    -name 'Login Data-journal' -o \
    -name 'Login Data For Account' -o \
    -name 'Login Data For Account-journal' \
\) -delete 2>/dev/null || true

# PID 1 ignores SIGTERM unless a handler is registered. Without this trap,
# Supervisor SIGKILLs the container after `timeout` and Chromium never
# flushes localStorage (HA "Remember me" tokens).
CHILD_PID=""
shutdown() {
    echo "Shutting down; saving Home Assistant tokens..."
    while IFS= read -r display; do
        disp_port=$(echo "$display" | jq -r '.port')
        display_number=$((disp_port - 5900))
        python3 /home/vnc_user/cdp_helper.py dump \
            $((9300 + display_number)) \
            "/data/chromium-data-$display_number/hassTokens.json" 2>/dev/null || true
        python3 /home/vnc_user/cdp_helper.py close $((9300 + display_number)) 2>/dev/null || true
    done <<< "$(jq -c '.displays[]' /data/options.json)"
    if [ -n "$CHILD_PID" ]; then
        kill -TERM "$CHILD_PID" 2>/dev/null || true
    fi
    pkill -TERM -u vnc_user chromium 2>/dev/null || true
    for _ in $(seq 1 40); do
        pgrep -u vnc_user chromium >/dev/null 2>&1 || break
        sleep 0.5
    done
    pkill -TERM -u vnc_user Xvnc 2>/dev/null || true
    if [ -n "$CHILD_PID" ]; then
        wait "$CHILD_PID" 2>/dev/null || true
    fi
    exit 0
}
trap shutdown SIGTERM SIGINT

su -c "/home/vnc_user/run_vnc.sh" vnc_user &
CHILD_PID=$!
wait "$CHILD_PID"
