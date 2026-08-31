# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.15.0] - 2026-08-31

### Added

- Pull-down to refresh on kiosk pages so devices without a keyboard can reload without F5. Disable per display with `pull_to_refresh: false`. Requires `view_only: false`.

## [0.14.0] - 2026-08-31

### Added

- Optional `ha_access_token` (global or per display) to log into a Home Assistant dashboard on first start without a username/password needed. Uses a user long-lived access token.

## [0.13.3] - 2026-08-31

### Fixed

- Home Assistant stays signed in after a restart.

## [0.13.0] - 2026-05-26

### Added

- Optional Chrome DevTools Protocol (CDP) support per display via `cdp_port` ([#11](https://github.com/MindFreeze/ha-vnc-web-browser/pull/11))
- Optional `browser_args` configuration to pass custom Chromium CLI arguments (e.g. dark mode, zoom level)
- CDP ports 9221–9224 (optional; only active when `cdp_port` is set on a display)
- Automatic `--remote-allow-origins=*` injection and socat forwarding so CDP works with Chromium M113+ loopback binding

### Changed

- Updated addon description to mention optional CDP access
- README documentation for CDP usage, security considerations, and VNC password requirements

## [0.12.0] - 2024-12-20

### Added

- Optional `view_only` setting per display to ignore keyboard and pointer input from VNC clients ([#1](https://github.com/MindFreeze/ha-vnc-web-browser/issues/1))

## [0.11.0] - 2024-12-19

### Added

- Persistent browser data per display so logins and sessions survive addon restarts ([#3](https://github.com/MindFreeze/ha-vnc-web-browser/issues/3))
- Password saving support in Chromium

## [0.10.1] - 2024-12-19

### Fixed

- Chromium no longer opens in a window smaller than the configured resolution

## [0.10.0] - 2024-12-19

### Added

- Configurable color depth per display (`depth`, 8–32 bits; defaults to 16)

## [0.9.18] - 2024-12-18

### Added

- Optional VNC password protection via `vnc_password`

## [0.9.2] - 2024-12-17

### Added

- Addon icon

## [0.9.1] - 2024-12-17

### Added

- Addon logo

## [0.9.0] - 2024-12-17

### Added

- Initial release: display up to four web pages over VNC, each in its own Chromium instance
- Per-display URL, resolution, and VNC port configuration

[0.15.0]: https://github.com/MindFreeze/ha-vnc-web-browser/compare/0.14.0...0.15.0
[0.14.0]: https://github.com/MindFreeze/ha-vnc-web-browser/compare/0.13.3...0.14.0
[0.13.3]: https://github.com/MindFreeze/ha-vnc-web-browser/compare/0.13.0...0.13.3
[0.13.0]: https://github.com/MindFreeze/ha-vnc-web-browser/compare/0.12.0...0.13.0
[0.12.0]: https://github.com/MindFreeze/ha-vnc-web-browser/compare/0.11.0...0.12.0
[0.11.0]: https://github.com/MindFreeze/ha-vnc-web-browser/compare/0.10.1...0.11.0
[0.10.1]: https://github.com/MindFreeze/ha-vnc-web-browser/compare/0.10.0...0.10.1
[0.10.0]: https://github.com/MindFreeze/ha-vnc-web-browser/compare/0.9.18...0.10.0
[0.9.18]: https://github.com/MindFreeze/ha-vnc-web-browser/compare/0.9.2...0.9.18
[0.9.2]: https://github.com/MindFreeze/ha-vnc-web-browser/compare/0.9.1...0.9.2
[0.9.1]: https://github.com/MindFreeze/ha-vnc-web-browser/compare/0.9.0...0.9.1
[0.9.0]: https://github.com/MindFreeze/ha-vnc-web-browser/releases/tag/0.9.0
