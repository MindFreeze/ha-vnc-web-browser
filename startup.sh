#!/bin/bash

# Read configuration from Home Assistant options (as root)
config=$(cat /data/options.json)

# Set VNC password from config
echo $(jq -r '.vnc_password' /data/options.json) | vncpasswd -f > /home/vnc_user/.vnc/passwd
chmod 600 /home/vnc_user/.vnc/passwd
chown vnc_user:vnc_user /home/vnc_user/.vnc/passwd

# Switch to vnc_user and run the VNC script
su -c "/home/vnc_user/run_vnc.sh '$config'" vnc_user
