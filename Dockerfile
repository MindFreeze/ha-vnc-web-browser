FROM debian:bullseye-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC

RUN apt-get update && apt-get install -y \
    tightvncserver \
    chromium \
    x11-xserver-utils \
    xauth \
    openbox \
    jq \
    dbus-x11 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user and add to required groups
RUN useradd -m -s /bin/bash vnc_user && \
    mkdir -p /run/dbus && \
    chown vnc_user:vnc_user /run/dbus

# Set up VNC directory for the new user
USER vnc_user
RUN mkdir -p /home/vnc_user/.vnc

# Switch back to root to copy files and set permissions
USER root
COPY startup.sh /home/vnc_user/startup.sh
COPY run_vnc.sh /home/vnc_user/run_vnc.sh
COPY chromium_preferences.json /home/vnc_user/chromium_preferences.json
COPY xstartup /home/vnc_user/.vnc/xstartup
RUN chown vnc_user:vnc_user /home/vnc_user/startup.sh /home/vnc_user/run_vnc.sh /home/vnc_user/.vnc/xstartup && \
    chmod +x /home/vnc_user/startup.sh /home/vnc_user/run_vnc.sh /home/vnc_user/.vnc/xstartup

WORKDIR /home/vnc_user

# Set the USER environment variable
ENV USER=vnc_user

# Labels for Home Assistant
LABEL \
    io.hass.name="VNC Web Browser" \
    io.hass.description="Display multiple web pages through VNC" \
    io.hass.type="addon" \
    io.hass.version="0.0.2" \
    io.hass.arch="aarch64|amd64|armhf|armv7"

# Expose 8 sequential ports
EXPOSE 5901/tcp 5902/tcp 5903/tcp 5904/tcp

CMD ["/home/vnc_user/startup.sh"]
