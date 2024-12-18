#!/bin/bash

# Read configuration from Home Assistant options (as root)
config=$(cat /data/options.json)

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

# Switch to vnc_user and run the VNC script
su -c "/home/vnc_user/run_vnc.sh '$config'" vnc_user
