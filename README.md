# RFID Entry-Exit System for Vasant Valley School

A working prototype of an RFID-based attendance and entry-exit system built around the school's existing ID cards: ESP32 firmware with an RC522 reader and TFT status display, a custom KiCad PCB, a FastAPI backend, and a live web dashboard with optional Firebase mirroring.

![Firmware](https://img.shields.io/badge/Firmware-ESP32%20%2B%20RC522-blue)
![Backend](https://img.shields.io/badge/Backend-FastAPI-teal)
![License](https://img.shields.io/badge/License-MIT-green)

## Motivation

At Vasant Valley School today, attendance is marked manually by class teachers, latecomers wait in a morning "late line" for manual strike marking, student exits run on paper sign-out sheets, and teachers sign in on paper registers. This project prototypes that replacement: students and teachers tap their existing RFID ID cards on entry, and the system records who arrived, when, whether they were late, and how they travel.

## What is in this repo

| Component | Path | What it does |
| --- | --- | --- |
| ESP32 firmware | `Main.ino` | Reads RC522 card taps, matches the UID against a roster, and renders a status card (colored initials tile, weekly grid, ON TIME / LATE / already checked in / unknown card) on a 320x240 ILI9341 TFT, with buzzer feedback. Lateness is computed against a configurable cutoff, with bus riders exempted. |
| Backend service | `rfid_system/backend` | A FastAPI REST API (`/api/health`, `/api/roster`, `/api/logs`) that stores roster data and attendance logs as JSON. |
| Web dashboard | `rfid_system/frontend` | A static browser dashboard that mirrors the TFT screen, supports manual UID entry for forgotten cards, polls the backend for live events, buffers offline, and can mirror manual scans to Firebase Firestore. |
| PCB design | `RFID KICAD/` | Full KiCad schematic and board layout integrating the ESP32 DevKit V1, RFID reader header, display headers, buzzer, power switch, and battery holder, with exported Gerber fabrication files in `RFID KICAD/RFID_PCB/`. |

## Hardware

| Component | Purpose |
| --- | --- |
| ESP32 DevKit V1 | Wi-Fi capable microcontroller running the firmware |
| RC522 RFID module (SPI) | Scans ID cards |
| ILI9341 320x240 TFT | Shows the scan result, lateness status, and transport mode |
| Buzzer | Audible scan feedback |
| Custom PCB | Integrates all components into a single module (KiCad sources and Gerbers in this repo) |
| 3D printed case | Protects and houses the hardware (design files not in this repo) |

## Getting started

To run the software stack on a laptop without flashing hardware, follow [`rfid_system/GETTING_STARTED.md`](rfid_system/GETTING_STARTED.md). It covers installing the Python dependencies, starting the FastAPI backend, serving the dashboard, simulating card taps by typing UIDs, and connecting the dashboard to Firebase.

To run the hardware demo, flash `Main.ino` to an ESP32 with the Arduino IDE or PlatformIO, with the MFRC522, Adafruit GFX, and Adafruit ILI9341 libraries installed.

## Status and roadmap

Implemented now: the standalone firmware demo (hardcoded roster, simulated clock), the backend and dashboard flow with Firestore mirroring for manual scans, and the complete PCB design.

Planned next, in line with the full design: posting scans from the ESP32 to the backend over Wi-Fi, real-time clock synchronization, automatic strike tracking with teacher notifications at three strikes, and gate-side exit authorization (walk, car, or bus).

## Developed by

**Kushal Sachdeva**, Vasant Valley School

More of my work: [github.com/Kushal-Sachdeva78](https://github.com/Kushal-Sachdeva78), including [autonomous RoboCup soccer robots](https://github.com/Kushal-Sachdeva78/VVS-Ballers-RoboCup) and [EnerJee](https://github.com/Kushal-Sachdeva78/EnerJee), a renewable energy planning platform.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
