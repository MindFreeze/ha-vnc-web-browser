# Home Assistant VNC Web Browser Addon

This addon allows you to display multiple web pages through VNC connections. Each web page runs in its own Chromium instance with a dedicated VNC server, making it perfect for displaying dashboards, cameras, or any other web content.

This is especially useful for older or low power devices that don't have a recent browser. You can use old tablets or e-ink devices as dashboards.

![P_20240928_170707](https://github.com/user-attachments/assets/dd021934-9a1b-4fa2-8569-2d08c59f34cf)

![P_20241219_162815](https://github.com/user-attachments/assets/2e463e6e-1c56-43d9-a331-051a47444930)

## Installation

1. Add https://github.com/MindFreeze/home-assistant-addons to the addon store repositories
2. Install the VNC Web Browser addon
3. Configure the addon as described below
4. Start the addon

## Configuration

Example configuration:

```yaml
displays:
  - url: "http://example1.com"
    resolution: "1920x1080"
    port: 5901
    depth: 16
    view_only: false
  - url: "http://example2.com"
    resolution: "1280x720"
    port: 5902
    depth: 16
    view_only: false
vnc_password: "your_secure_password"
```

### Configuration Options

- `displays`: List of displays to create
  - `url`: The URL to display in the browser
  - `resolution`: The resolution of the display (e.g., "1920x1080")
  - `port`: VNC port number (must be between 5901 and 5908). This is the port used in the docker container. You can map it to another port in the addon's network configuration
  - `depth`: Color depth in bits (8-32, defaults to 16). Common values are 8, 16, 24, or 32. There seem to be some issues with 8 bit depth so be careful with that value
  - `view_only`: Optional boolean to enable view-only mode (defaults to false). When enabled, keyboard and pointer events from VNC clients will be ignored
- `vnc_password`: Password for VNC connections (required)

## Usage

1. Configure your displays in the addon configuration
2. Start the addon
3. Connect to the VNC displays using any VNC client:
   - Host: Your Home Assistant IP address
   - Port: As configured per display (5901-5908)
   - Password: As configured in vnc_password

## Notes

- Each display runs in its own Chromium instance
- The addon supports up to 4 simultaneous displays
- Make sure your VNC client supports the resolution you configure
- The VNC password is not considered very secure so I would advise against exposing this outside your network

This addon is based on this POC https://github.com/MindFreeze/vnc-web
