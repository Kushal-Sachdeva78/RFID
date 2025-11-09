# Getting Started (Software Only)

Use this guide when you want to run the RFID system on a laptop without flashing the ESP32. It walks
through installing dependencies, starting the local backend, opening the dashboard, and connecting
the dashboard to Firebase for logging.

---

## 1. Prepare the Backend

1. Open a terminal and switch into the backend folder:
   ```bash
   cd rfid_system/backend
   ```
2. Create a Python virtual environment (recommended):
   ```bash
   python -m venv .venv
   ```
3. Activate it:
   - macOS / Linux:
     ```bash
     source .venv/bin/activate
     ```
   - Windows (PowerShell):
     ```powershell
     .venv\Scripts\Activate.ps1
     ```
4. Install the required packages:
   ```bash
   pip install -r requirements.txt
   ```
5. Start the API (it uses [FastAPI](https://fastapi.tiangolo.com/) with Uvicorn):
   ```bash
   uvicorn main:app --reload
   ```

The backend will listen on `http://127.0.0.1:8000`. Keep this terminal running.

---

## 2. Open the Dashboard

1. In a second terminal, serve the frontend files:
   ```bash
   cd rfid_system/frontend
   python -m http.server 5173
   ```
2. Browse to `http://localhost:5173`.
3. Inside the **Backend Connection** card, enter the backend URL (`http://127.0.0.1:8000`) and click
   **Connect**. The roster and attendance tables will load from the JSON data bundled with the repo.
4. Testing without the backend? Leave it stopped—the dashboard will note the offline status but still
   accepts manual scans so you can demo the SPI screen preview locally.

---

## 3. Simulate RFID Scans Manually

The **Manual RFID Entry** form lets you type any UID (for example `AA BB CC DD`) to simulate a scan.
Expand the **Optional display details** drawer to override the name, role, class, transport mode, and
photo that appear on the SPI preview.

Each submission will:

1. POST the event to the backend (`POST /api/logs`).
2. Refresh the dashboard tables so you can confirm the entry.
3. Update the **SPI Screen Preview** card with the student's photo, transport mode, and a colour-coded
   timetable for the current week.
4. (Optional) Mirror the event to Firebase Firestore if you configure Firebase in the next step.

Use this workflow to prototype the UI without the ESP32 connected. If the backend is offline, the
dashboard keeps the scan locally, highlights it in the events table, and updates the SPI preview so you
can keep testing.

> 💡 **Tip:** The backend understands the same statuses that the firmware sends. Choose the
> value that matches what you want to test:
> - `accepted` – normal entry/exit records (shows a green checkmark in the weekly grid).
> - `duplicate` – repeat scans that should not mark attendance again.
> - `late` – submissions that include lateness details from the ESP32 (shows a yellow dash).
> - `rejected` – scans from unregistered cards (the day stays red with an **X**).
>
> You can also add optional notes in the form to see how annotations appear in the events
> table and Firebase.

---

## 4. Configure Firebase (Optional)

The dashboard already imports Firebase modules and reads configuration values from
`rfid_system/frontend/firebase.js`. Replace the placeholder configuration with the details you
provided:

```javascript
// rfid_system/frontend/firebase.js
import { initializeApp } from "https://www.gstatic.com/firebasejs/10.7.1/firebase-app.js";
import {
  getFirestore,
  collection,
  addDoc,
  serverTimestamp,
} from "https://www.gstatic.com/firebasejs/10.7.1/firebase-firestore.js";

const firebaseConfig = {
  apiKey: "AIzaSyCu0eajMj6wsOZN6YAa5a4y1nJqbFGRQt4",
  authDomain: "rfid-a9353.firebaseapp.com",
  projectId: "rfid-a9353",
  storageBucket: "rfid-a9353.firebasestorage.app",
  messagingSenderId: "1032115456459",
  appId: "1:1032115456459:web:f969ac442b97e9f71bce4e",
  measurementId: "G-CPEZ5NSW66"
};

const app = initializeApp(firebaseConfig);
export const db = getFirestore(app);
export const manualScansCollection = collection(db, "manual_scans");
export const timestamp = serverTimestamp;
```

> ℹ️ The repository already contains this configuration—double-check it matches your Firebase
> dashboard and update it if the values change.

### Firestore Security Rules

Paste the rules below into the Firestore rules editor to protect the `manual_scans` collection while
still allowing dashboard reads:

```text
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /manual_scans/{document=**} {
      allow read: if true;
      allow write: if request.auth != null;
    }
  }
}
```

Adjust the `allow read`/`allow write` lines if your project needs different access levels.

---

## 5. Next Steps

- When you are ready to deploy to hardware, flash `Main.ino` onto the ESP32 with the Arduino IDE or
  PlatformIO.
- Update the backend roster data in `rfid_system/backend/data/roster.json` to reflect your actual
  IDs and names.
- Extend the frontend or backend to integrate with other systems (for example, exporting logs to
  Veracross or triggering alerts).

Keep this document handy whenever you set up the software on a new machine.
