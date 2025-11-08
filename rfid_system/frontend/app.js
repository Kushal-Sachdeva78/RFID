import {
  db,
  collection,
  addDoc,
  serverTimestamp,
  analyticsPromise,
} from "./firebase.js";

const configForm = document.getElementById("config-form");
const apiUrlInput = document.getElementById("api-url");
const healthStatus = document.getElementById("health-status");
const rosterBody = document.getElementById("roster-body");
const eventsBody = document.getElementById("events-body");
const refreshRosterBtn = document.getElementById("refresh-roster");
const refreshEventsBtn = document.getElementById("refresh-events");
const manualForm = document.getElementById("manual-form");
const manualUidInput = document.getElementById("manual-uid");
const manualStatusSelect = document.getElementById("manual-status");
const manualLocationInput = document.getElementById("manual-location");
const manualNotesInput = document.getElementById("manual-notes");
const manualMessage = document.getElementById("manual-message");

let apiBase = localStorage.getItem("rfid_api_base") || "http://localhost:8000";
apiUrlInput.value = apiBase;

analyticsPromise.catch((error) => {
  console.warn("Firebase analytics is unavailable", error);
});

async function pingBackend() {
  try {
    const res = await fetch(`${apiBase}/api/health`);
    if (!res.ok) throw new Error(`Status ${res.status}`);
    const payload = await res.json();
    healthStatus.textContent = `Online (${payload.status})`;
    healthStatus.classList.remove("error");
    healthStatus.classList.add("ok");
  } catch (error) {
    healthStatus.textContent = `Offline (${error.message})`;
    healthStatus.classList.remove("ok");
    healthStatus.classList.add("error");
  }
}

async function loadRoster() {
  try {
    const res = await fetch(`${apiBase}/api/roster`);
    if (!res.ok) throw new Error(`Status ${res.status}`);
    const payload = await res.json();
    rosterBody.innerHTML = "";
    payload.roster.forEach((person) => {
      const row = document.createElement("tr");
      row.innerHTML = `
        <td><code>${person.uid}</code></td>
        <td>${person.name}</td>
        <td>${person.role}</td>
        <td>${person.transport}</td>
      `;
      rosterBody.appendChild(row);
    });
  } catch (error) {
    rosterBody.innerHTML = `<tr><td colspan="4">Failed to load roster: ${error.message}</td></tr>`;
  }
}

async function loadEvents() {
  try {
    const res = await fetch(`${apiBase}/api/logs`);
    if (!res.ok) throw new Error(`Status ${res.status}`);
    const payload = await res.json();
    eventsBody.innerHTML = "";
    payload.events
      .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))
      .forEach((event) => {
        const row = document.createElement("tr");
        const details = [];
        if (event.details?.person) {
          details.push(`${event.details.person.name || "Unknown"} (${event.details.person.role || "-"})`);
        }
        if (event.details?.lateness?.late) {
          details.push(`Late by ${event.details.lateness.minutes || 0} minutes`);
        }
        row.innerHTML = `
          <td>${new Date(event.timestamp).toLocaleString()}</td>
          <td><code>${event.uid}</code></td>
          <td>${event.status}</td>
          <td>${event.reader_location}</td>
          <td>${details.join(" · ") || "-"}</td>
        `;
        eventsBody.appendChild(row);
      });
  } catch (error) {
    eventsBody.innerHTML = `<tr><td colspan="5">Failed to load events: ${error.message}</td></tr>`;
  }
}

async function submitManualEvent(event) {
  event.preventDefault();
  manualMessage.textContent = "";
  manualMessage.className = "message";

  const uid = manualUidInput.value.trim();
  if (!uid) {
    manualMessage.textContent = "Please enter an RFID tag UID.";
    manualMessage.className = "message error";
    return;
  }

  const status = manualStatusSelect.value;
  const readerLocation = manualLocationInput.value.trim() || "manual_station";
  const notes = manualNotesInput.value.trim() || null;

  const payload = {
    uid,
    status,
    reader_location: readerLocation,
    manual: true,
    notes,
  };

  try {
    const res = await fetch(`${apiBase}/api/logs`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      throw new Error(`Backend rejected the event (status ${res.status}).`);
    }

    const { event: savedEvent } = await res.json();
    manualMessage.textContent = `Recorded UID ${savedEvent.uid} at ${new Date(
      savedEvent.timestamp
    ).toLocaleString()}.`;
    manualMessage.className = "message success";
    manualForm.reset();
    manualUidInput.focus();
    loadEvents();

    try {
      await addDoc(collection(db, "manual_scans"), {
        uid: savedEvent.uid,
        status: savedEvent.status,
        reader_location: savedEvent.reader_location,
        notes,
        saved_at: serverTimestamp(),
      });
    } catch (firebaseError) {
      console.warn("Failed to sync manual event to Firebase", firebaseError);
    }
  } catch (error) {
    manualMessage.textContent = error.message;
    manualMessage.className = "message error";
  }
}

configForm.addEventListener("submit", (event) => {
  event.preventDefault();
  apiBase = apiUrlInput.value.trim().replace(/\/$/, "");
  localStorage.setItem("rfid_api_base", apiBase);
  pingBackend();
  loadRoster();
  loadEvents();
});

refreshRosterBtn.addEventListener("click", loadRoster);
refreshEventsBtn.addEventListener("click", loadEvents);
manualForm.addEventListener("submit", submitManualEvent);

pingBackend();
loadRoster();
loadEvents();
setInterval(loadEvents, 5000);
