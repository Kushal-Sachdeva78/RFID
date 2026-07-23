# RFID Entry-Exit System for Vasant Valley School

A prototype of an RFID-based attendance, entry-exit, and laptop-borrowing system
built around the school's existing ID cards: ESP32 firmware with an RC522 reader
and TFT status display, a custom KiCad PCB, a FastAPI backend with a test suite,
and a web dashboard with optional Firebase mirroring.

[![Firmware](https://img.shields.io/badge/Firmware-ESP32%20%2B%20RC522-blue)](Main.ino)
[![Backend](https://img.shields.io/badge/Backend-FastAPI-teal)](rfid_system/backend)
[![Tests](https://img.shields.io/badge/Tests-pytest-green)](.github/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

## Motivation

At Vasant Valley School, attendance is marked manually by class teachers,
latecomers wait in a morning "late line" for manual strike marking, student
exits run on paper sign-out sheets, and borrowing a laptop needs a paper chit
signed across several flights of stairs. This project prototypes a replacement:
students and staff tap their existing ID cards, and the system records who
arrived, when, whether they were late, which way they are authorised to travel
home, and who is holding which laptop.

## What is in this repo

| Component | Path | What it does |
| --- | --- | --- |
| ESP32 firmware | `Main.ino` | Reads RC522 taps, keeps a real clock over NTP (with a simulated fallback), renders a status card, weekly grid, and entry/exit banner on the ILI9341 TFT, and posts each scan to the backend over Wi-Fi with retry and an offline buffer. Pin assignments match the fabricated board. |
| Backend service | `rfid_system/backend` | A FastAPI REST API covering health, roster, attendance events (entry/exit direction and second-resolution lateness), an office manual fallback, three-strike teacher notification, and laptop borrowing. Pydantic v2, timezone-aware, a swappable storage layer, role-scoped API keys, and a pytest suite. |
| Web dashboard | `rfid_system/frontend` | A static dashboard showing the roster, attendance events with direction, a gate exit-authorization banner, manual entry, and a laptop borrowing panel. Optional Firebase mirroring of manual scans. |
| PCB design | `RFID KICAD/` | Full KiCad schematic and board layout integrating the ESP32 DevKit V1, RFID reader, display, buzzer, power switch, and battery holder, with exported Gerbers in `RFID KICAD/RFID_PCB/`. |

## Features

- Attendance to the second against a real clock, with the 08:05 cutoff and bus
  riders exempt from lateness. A repeat tap does not double-mark attendance.
- Entry and exit logging on a single gate reader (a per-day toggle), with the
  guard-facing display showing whether a departing student may walk, go by car,
  or take the bus.
- An office manual fallback for a forgotten or lost card, flagged manual and
  attributed to the staff member.
- Three late days in a learning cycle notify the class teacher through a
  pluggable notifier (a file/stdout default, or SMTP from environment
  variables). No credentials are committed.
- Laptop borrowing with a full state machine: a student requests, a teacher
  approves or denies, a tech-lab helper issues a numbered unit and records the
  return, and the dashboard shows outstanding loans and how long each is held.

## Hardware

| Component | Purpose |
| --- | --- |
| ESP32 DevKit V1 | Wi-Fi microcontroller running the firmware |
| RC522 RFID module (SPI) | Scans ID cards |
| ILI9341 320x240 TFT | Shows the scan result, lateness, direction, and transport authorization |
| Buzzer | Audible scan feedback |
| Custom PCB | Integrates the components (KiCad sources and Gerbers in this repo) |

The firmware pin defines match the nets on the fabricated board (RC522 SS on
GPIO14 and RST on GPIO27; TFT CS on GPIO5, DC on GPIO21, RST on GPIO22; buzzer on
GPIO15; shared SPI on GPIO18/23/19). Verify with a continuity check before
flashing a unit.

## Getting started

To run the software on a laptop with no hardware, follow
[`rfid_system/GETTING_STARTED.md`](rfid_system/GETTING_STARTED.md): it covers the
backend and its tests, the dashboard, compiling the firmware with `arduino-cli`,
the laptop borrowing flow, and optional Firebase setup.

Continuous integration (`.github/workflows/ci.yml`) runs the backend tests and a
firmware compile for the ESP32 DevKit V1 on every push.

## Status

Implemented in this prototype: the firmware (real clock, Wi-Fi posting, offline
buffer, corrected pins); the backend (attendance with direction and lateness,
manual fallback, three-strike notification, laptop borrowing) with a pytest
suite; the dashboard; and the complete PCB design.

Not yet done: Firebase Auth so the optional Firestore mirror can be enabled,
on-device roster caching so the gate can identify all cards while offline, and
real per-user authentication in place of the prototype role keys.

## Developed by

**Kushal Sachdeva**, Vasant Valley School

More of my work: [github.com/Kushal-Sachdeva78](https://github.com/Kushal-Sachdeva78),
including [autonomous RoboCup soccer robots](https://github.com/Kushal-Sachdeva78/VVS-Ballers-RoboCup)
and [EnerJee](https://github.com/Kushal-Sachdeva78/EnerJee), a renewable energy
planning platform.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
