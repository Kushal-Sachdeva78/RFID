# Contributing

This is a prototype RFID attendance and entry/exit system for Vasant Valley School: ESP32 firmware
(`Main.ino`), a FastAPI backend, a static web dashboard and a KiCad PCB.

## How to engage

- **Questions and problems** — open an issue and say which part you are using (firmware, backend,
  dashboard or PCB), what you ran, and your host and board details.
- **Pull requests** — welcome for the backend, dashboard, firmware and docs. Before opening one:
  - Backend: `cd rfid_system/backend && pytest -q`
  - Firmware: `bash scripts/compile_firmware.sh` (needs `arduino-cli` with the ESP32 core; CI runs it)
- **Response time** — I aim to reply to every new issue within 24 hours
  (India Standard Time). If I'm slower than that, I'll say so on the issue
  rather than leave it silent.

## Ground rules

1. Use synthetic data only. The sample files in `rfid_system/backend/data/` are synthetic; never commit
   real student, staff or card data.
2. Never commit credentials. `arduino_secrets.h` and `firebase.config.js` are git-ignored; copy the
   example files (`arduino_secrets.example.h`, `rfid_system/frontend/firebase.config.example.js`) instead.
3. The pin assignments in `Main.ino` match the fabricated board (see the Hardware section of the
   README). If you change a pin, update the README and the KiCad design together.

## Code of conduct

Be respectful and constructive. This is a student project; good-faith questions
and careful, well-documented contributions are appreciated.
