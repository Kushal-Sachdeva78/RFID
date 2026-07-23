# Getting Started

Run the RFID system on a laptop with no hardware, then optionally compile the
firmware and wire up Firebase. Every step below runs with no credentials.

---

## 1. Backend

```bash
cd rfid_system/backend
python -m venv .venv
# macOS / Linux:
source .venv/bin/activate
# Windows (PowerShell):
.venv\Scripts\Activate.ps1

pip install -r requirements.txt -r requirements-dev.txt
uvicorn main:app --reload
```

The API listens on `http://127.0.0.1:8000`. Check it with:

```bash
curl http://127.0.0.1:8000/api/health
```

Run the tests:

```bash
pytest -q
```

### Configuration (all optional, via environment variables)

| Variable | Default | Purpose |
| --- | --- | --- |
| `RFID_TZ_OFFSET_MINUTES` | `330` | Local timezone offset. Default is India Standard Time (UTC+5:30, no daylight saving). |
| `RFID_LATE_HOUR` / `RFID_LATE_MINUTE` | `8` / `5` | Lateness cutoff (08:05). |
| `RFID_LEARNING_CYCLES` | one cycle, 08 Jul to 15 Oct 2026 | JSON array of `{name, start, end}` date ranges for strike tracking. |
| `RFID_STRIKE_THRESHOLD` | `3` | Late days in a cycle before the class teacher is notified. |
| `RFID_MAX_CONCURRENT_LOANS` | `1` | Active laptop loans a student may hold at once. |
| `RFID_SCAN_DEBOUNCE_SECONDS` | `60` | A repeat tap inside this window is a duplicate, not an exit. |
| `RFID_NOTIFIER` | `log` | Notifier backend: `log` (file plus stdout), `smtp`, or `none`. |
| `RFID_API_KEYS` | unset | JSON object of `{"key": "role"}` enabling role checks (see below). |

### Roles (prototype-grade)

By default there is no authentication, so the repo runs with no credentials.
When `RFID_API_KEYS` is set, privileged endpoints require an `X-API-Key` header
mapped to a role. This is a single shared key per role, not per-user login, and
is documented as a prototype, not production security. Example:

```bash
export RFID_API_KEYS='{"office-key":"office","teacher-key":"teacher","helper-key":"helper","admin-key":"admin"}'
```

Role requirements: manual attendance entry and roster writes need `office`,
`teacher`, or `admin`; laptop register or repair needs `helper` or `admin`; loan
approve or deny needs `teacher`; issue or return needs `helper`. The `admin` role
is allowed everywhere. Device scans and student borrow requests are open.

### Notifications (three-strike rule)

Three late days within a learning cycle notify the student's class teacher. The
class teacher is looked up in `data/class_teachers.json` by class section. The
default notifier writes to `data/notifications.log` and stdout, so no email
credentials are needed. To send email instead, set `RFID_NOTIFIER=smtp` and the
`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, and `SMTP_FROM` variables.
No credentials are ever committed.

---

## 2. Dashboard

```bash
cd rfid_system/frontend
python -m http.server 5173
```

Browse to `http://localhost:5173`, enter the backend URL (`http://127.0.0.1:8000`)
in the Backend Connection card, and click Connect. The dashboard shows the roster,
attendance events with entry/exit direction, a gate preview with the exit
authorization banner, the manual entry form, and the laptop borrowing panel. If
the backend is stopped, manual scans are buffered locally.

---

## 3. Firmware (compile only)

The firmware target is the ESP32 DevKit V1. There is no hardware step here: a
clean compile is the gate.

```bash
arduino-cli core install esp32:esp32
arduino-cli lib install "MFRC522" "Adafruit GFX Library" "Adafruit ILI9341"
bash scripts/compile_firmware.sh
```

`scripts/compile_firmware.sh` stages `Main.ino` into `build/Main/` so the tracked
file is never moved. To run against hardware, copy `arduino_secrets.example.h` to
`arduino_secrets.h` (gitignored) and set your Wi-Fi and backend URL. With no
secrets file, or an empty SSID, the firmware runs fully offline.

---

## 4. Laptop borrowing flow

You can drive the whole flow from the dashboard Laptop Borrowing panel, or with
curl (with `RFID_API_KEYS` unset, no keys are needed):

```bash
B=http://127.0.0.1:8000
curl -s -X POST $B/api/laptops -H "Content-Type: application/json" -d '{"asset_code":"LT-042"}'
LOAN=$(curl -s -X POST $B/api/loans/request -H "Content-Type: application/json" -d '{"student_uid":"04 11 22 33"}' | python -c "import sys,json;print(json.load(sys.stdin)['id'])")
curl -s -X POST $B/api/loans/$LOAN/approve
curl -s -X POST $B/api/loans/$LOAN/issue -H "Content-Type: application/json" -d '{"asset_code":"LT-042"}'
curl -s $B/api/loans/outstanding
curl -s -X POST $B/api/loans/$LOAN/return
```

---

## 5. Firebase (optional)

Firestore mirroring of manual scans is optional. Copy the example config and fill
in your project:

```bash
cp rfid_system/frontend/firebase.config.example.js rfid_system/frontend/firebase.config.js
```

`firebase.config.js` is gitignored. When it is absent, the dashboard runs normally
with mirroring disabled. A Firebase web apiKey is not a secret (it ships to every
browser); the real protection is the Firestore rules below.

### Firestore security rules

These restrict access to authenticated clients. Wiring up Firebase Auth in the
dashboard is out of scope for this prototype, so mirroring is off until that is
added.

```text
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /manual_scans/{document=**} {
      allow read, write: if request.auth != null;
    }
  }
}
```
