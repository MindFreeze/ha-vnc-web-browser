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
    browser_args: "--force-dark-mode"
  - url: "http://example2.com"
    resolution: "1280x720"
    port: 5902
    depth: 16
    view_only: false
    browser_args: ""
vnc_password: "your_secure_password"
```

### Configuration Options

- `displays`: List of displays to create
  - `url`: The URL to display in the browser
  - `resolution`: The resolution of the display (e.g., "1920x1080")
  - `port`: VNC port number (must be between 5901 and 5908). This is the port used in the docker container. You can map it to another port in the addon's network configuration
  - `depth`: Color depth in bits (8-32, defaults to 16). Common values are 8, 16, 24, or 32. There seem to be some issues with 8 bit depth so be careful with that value
  - `view_only`: Optional boolean to enable view-only mode (defaults to false). When enabled, keyboard and pointer events from VNC clients will be ignored
  - `browser_args`: Optional string containing additional CLI arguments to pass to Chromium. Common examples:
    - `"--force-dark-mode"` - Enable dark mode
    - `"--force-device-scale-factor=1.5"` - Set custom zoom level
    - `"--disable-features=Translate"` - Disable specific features
    - You can combine multiple arguments: `"--force-dark-mode --force-device-scale-factor=1.25"`
  - `cdp_port`: Optional integer (9221-9224) enabling Chrome DevTools Protocol on this display. See "Chrome DevTools Protocol" below.
- `vnc_password`: Password for VNC connections (required)

## Chrome DevTools Protocol (CDP)

Setting `cdp_port` on a display exposes Chromium's DevTools Protocol so external tools (Playwright, Puppeteer, browser automation agents) can drive the same browser session a user is watching over VNC. This is useful for AI agents that need a "teach me" mode where a human can take over via VNC mid-session.

Example:

```yaml
displays:
  - url: "https://example.com"
    resolution: "1280x720"
    port: 5901
    cdp_port: 9222
```

Then connect from Playwright:

```python
browser = await playwright.chromium.connect_over_cdp("ws://<addon-host>:9222")
```

`<addon-host>` is either the addon's internal hostname (e.g. `<repo-hash>-vnc-web-browser` for sibling addons on the hassio Docker network) or your Home Assistant host's LAN IP if you publish the port externally.

### Why CDP needs special handling

Chromium M113+ silently ignores `--remote-debugging-address=0.0.0.0` and binds 127.0.0.1 regardless (upstream marked WontFix: [crbug.com/40261787](https://issues.chromium.org/issues/40261787)). The addon works around this by binding Chromium to a loopback-only internal port and forwarding via `socat` so the CDP endpoint is reachable from outside the container. The `--remote-allow-origins=*` flag is also injected automatically — without it, modern Chromium rejects WebSocket upgrades from non-localhost callers with a 403.

Do **not** put `--remote-debugging-port` or `--remote-debugging-address` into `browser_args` when using `cdp_port`; those flags are stripped automatically to prevent collisions.

## Usage

1. Configure your displays in the addon configuration
2. Start the addon
3. Connect to the VNC displays using any VNC client:
   - Host: Your Home Assistant IP address
   - Port: As configured per display (5901-5908)
   - Password: As configured in vnc_password

Note: Devices without a keyboard like old kindles can't log in but you can use a VNC client on another device to connect to the same session and log in. The session data is saved so you shouldn't need to do this more than once.

## Notes

- Each display runs in its own Chromium instance
- The addon supports up to 4 simultaneous displays
- Make sure your VNC client supports the resolution you configure
- The VNC password is not considered very secure so I would advise against exposing this outside your network

This addon is based on this POC https://github.com/MindFreeze/vnc-web
