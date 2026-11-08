# Changelog

All notable changes to this repository are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). The entries below are taken from the
commit history.

## [Unreleased]

## [0.1.0] - 2026-11-09

First tagged release. The project is a prototype; the Status section of the README lists what is not done yet.

### Added

- README top block, contributing guide, issue forms and this changelog.
- Backend test harness with pytest, configuration, a swappable storage layer and a firmware build script (2026-07-23).
- Firmware: real NTP clock, backend posting with an offline buffer, and board pins (2026-07-23).
- Entry/exit direction, exit authorization and a manual fallback with roles (2026-07-23).
- Second-resolution lateness and three-strike teacher notification (2026-07-23).
- Laptop borrowing state machine with a dashboard and an end-to-end flow (2026-07-23).
- Synthetic sample data and the Firebase config pattern (2026-07-23).
- MIT license (2026-07-11).

### Changed

- README restructured to separate implemented work from the planned design (2026-07-18); badges link to
  their targets (2026-07-22); README and getting-started guide rewritten (2026-07-23).
- The KiCad footprint cache and editor backup archives are no longer tracked (2026-07-23).

## Earlier work (2025-09 to 2025-11)

- Initial ESP32 and RC522 firmware and the KiCad project (2025-09-20), then full-stack support: a backend,
  a dashboard with an SPI screen preview, offline dashboard testing and Teensy-focused TFT attendance
  firmware (2025-11-09).
