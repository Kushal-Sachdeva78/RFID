// Copy this file to arduino_secrets.h and fill in real values.
// arduino_secrets.h is gitignored so Wi-Fi credentials are never committed.
// Main.ino includes it automatically when present; when it is absent (for
// example in CI, which only compiles), the placeholders in Main.ino are used.
#ifndef ARDUINO_SECRETS_H
#define ARDUINO_SECRETS_H

#define WIFI_SSID        "your-wifi-ssid"
#define WIFI_PASSWORD    "your-wifi-password"

// Base URL of the FastAPI backend, with no trailing slash.
#define BACKEND_BASE_URL "http://192.168.1.100:8000"

// Identifier for this physical reader, recorded on every scan.
#define READER_LOCATION  "main_gate"

#endif
