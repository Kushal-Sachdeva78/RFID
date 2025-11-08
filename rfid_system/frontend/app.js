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
const scanPhoto = document.getElementById("scan-photo");
const scanName = document.getElementById("scan-name");
const scanRole = document.getElementById("scan-role");
const scanTransport = document.getElementById("scan-transport");
const scanTime = document.getElementById("scan-time");
const weekDaysRow = document.getElementById("week-days");
const weekStatusRow = document.getElementById("week-status");

let apiBase = localStorage.getItem("rfid_api_base") || "http://localhost:8000";
apiUrlInput.value = apiBase;

analyticsPromise.catch((error) => {
  console.warn("Firebase analytics is unavailable", error);
});

const WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const rosterByUid = new Map();
let latestEventsCache = [];

function initialiseWeekdayHeader() {
  weekDaysRow.innerHTML = WEEKDAY_LABELS.map((label) => `<th>${label}</th>`).join("\n");
}

function formatStatus(status) {
  if (!status) return "";
  if (status === "late") return "Late arrival";
  return status
    .split("_")
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(" ");
}

function midnight(date) {
  const copy = new Date(date);
  copy.setHours(0, 0, 0, 0);
  return copy;
}

function startOfWeek(date) {
  const day = date.getDay();
  const mondayOffset = (day + 6) % 7; // convert Sun=0..Sat=6 to Mon-based offset
  const start = new Date(date);
  start.setDate(date.getDate() - mondayOffset);
  start.setHours(0, 0, 0, 0);
  return start;
}

function classifyDayStatus(events, uid, dayStart) {
  const dayEnd = new Date(dayStart);
  dayEnd.setDate(dayStart.getDate() + 1);

  const dayEvents = events.filter((event) => {
    if (event.uid !== uid) return false;
    const ts = new Date(event.timestamp);
    return ts >= dayStart && ts < dayEnd;
  });

  if (dayEvents.length === 0) {
    return { icon: "✖", label: "Absent", css: "absent" };
  }

  const hasAccepted = dayEvents.some((event) => event.status === "accepted");
  if (hasAccepted) {
    return { icon: "✔", label: "On time", css: "present" };
  }

  const hasDuplicate = dayEvents.some((event) => event.status === "duplicate");
  if (hasDuplicate) {
    return { icon: "✔", label: "On time", css: "present" };
  }

  const hasLate = dayEvents.some((event) => event.status === "late");
  if (hasLate) {
    return { icon: "–", label: "Late", css: "late" };
  }

  return { icon: "✖", label: "Absent", css: "absent" };
}

function renderLastScan(latestEvent) {
  if (!latestEvent) {
    scanPhoto.hidden = true;
    scanName.textContent = "Waiting for the first scan";
    scanRole.textContent = "Role / Class";
    scanTransport.textContent = "Transport mode";
    scanTime.textContent = "Timestamp";
    weekStatusRow.innerHTML = WEEKDAY_LABELS.map(() => `<td>–</td>`).join("\n");
    return;
  }

  const person = rosterByUid.get(latestEvent.uid) || latestEvent.details?.person || null;
  const timestamp = new Date(latestEvent.timestamp);

  scanName.textContent = person?.name || `UID ${latestEvent.uid}`;

  const rolePieces = [];
  if (person?.role) rolePieces.push(person.role);
  if (person?.class_name) rolePieces.push(person.class_name);
  scanRole.textContent = rolePieces.join(" • ") || "Role / Class";

  if (person?.transport) {
    scanTransport.textContent = `Transport: ${person.transport}`;
  } else {
    scanTransport.textContent = "Transport mode";
  }

  const statusLabel = formatStatus(latestEvent.status);
  scanTime.textContent = `${timestamp.toLocaleString()} • ${statusLabel}`;

  if (person?.photo_url) {
    scanPhoto.src = person.photo_url;
    scanPhoto.hidden = false;
  } else {
    scanPhoto.hidden = true;
  }

  const weekStart = startOfWeek(timestamp);
  const cells = [];
  for (let i = 0; i < WEEKDAY_LABELS.length; i += 1) {
    const dayStart = new Date(weekStart);
    dayStart.setDate(weekStart.getDate() + i);
    const { icon, css, label } = classifyDayStatus(latestEventsCache, latestEvent.uid, dayStart);
    const isToday = midnight(timestamp).getTime() === dayStart.getTime();
    cells.push(
      `<td><span class="status-icon ${css}" title="${label}"${
        isToday ? " aria-current=\"date\"" : ""
      }>${icon}</span></td>`
    );
  }
  weekStatusRow.innerHTML = cells.join("\n");
}

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
    rosterByUid.clear();
    payload.roster.forEach((person) => {
      const row = document.createElement("tr");
      row.innerHTML = `
        <td><code>${person.uid}</code></td>
        <td>${person.name}</td>
        <td>${person.role}</td>
        <td>${person.transport}</td>
      `;
      rosterBody.appendChild(row);
      rosterByUid.set(person.uid, person);
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
    latestEventsCache = payload.events;
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
    const latestEvent = payload.events.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))[0];
    renderLastScan(latestEvent);
  } catch (error) {
    eventsBody.innerHTML = `<tr><td colspan="5">Failed to load events: ${error.message}</td></tr>`;
    renderLastScan(null);
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

initialiseWeekdayHeader();
pingBackend();
loadRoster();
loadEvents();
setInterval(loadEvents, 5000);
manualUidInput.focus();
