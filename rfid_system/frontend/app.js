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
const manualNameInput = document.getElementById("manual-name");
const manualRoleInput = document.getElementById("manual-role");
const manualClassInput = document.getElementById("manual-class");
const manualTransportInput = document.getElementById("manual-transport");
const manualPhotoInput = document.getElementById("manual-photo");
const manualMessage = document.getElementById("manual-message");
const scanPhoto = document.getElementById("scan-photo");
const scanName = document.getElementById("scan-name");
const scanRole = document.getElementById("scan-role");
const scanTransport = document.getElementById("scan-transport");
const scanTime = document.getElementById("scan-time");
const weekDaysRow = document.getElementById("week-days");
const weekStatusRow = document.getElementById("week-status");
const scanAuthorization = document.getElementById("scan-authorization");
const manualRecordedByInput = document.getElementById("manual-recorded-by");
const manualApiKeyInput = document.getElementById("manual-api-key");

let apiBase = localStorage.getItem("rfid_api_base") || "http://localhost:8000";
apiUrlInput.value = apiBase;

analyticsPromise.catch((error) => {
  console.warn("Firebase analytics is unavailable", error);
});

const WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const TRANSPORT_AUTHORIZATION = {
  walk: "Authorised to walk home",
  car: "Authorised to go by car",
  bus: "Authorised to take the bus",
};

function authorizationFor(transport) {
  if (!transport) return "Transport not on record";
  return (
    TRANSPORT_AUTHORIZATION[String(transport).trim().toLowerCase()] || `Transport: ${transport}`
  );
}

if (manualApiKeyInput) {
  manualApiKeyInput.value = localStorage.getItem("rfid_api_key") || "";
}
const rosterByUid = new Map();
let backendEvents = [];
const offlineEvents = [];

function getAllEvents() {
  return [...backendEvents, ...offlineEvents];
}

function upsertRosterEntry(uid, personDetails = {}) {
  if (!uid) return;
  const existing = rosterByUid.get(uid) || { uid };
  const merged = { ...existing, ...personDetails, uid };
  rosterByUid.set(uid, merged);
}

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
    return { icon: "-", label: "Late", css: "late" };
  }

  return { icon: "✖", label: "Absent", css: "absent" };
}

function renderLastScan(latestEvent, eventsForWeek = []) {
  if (!latestEvent) {
    scanPhoto.hidden = true;
    scanName.textContent = "Waiting for the first scan";
    scanRole.textContent = "Role / Class";
    scanTransport.textContent = "Transport mode";
    scanTime.textContent = "Timestamp";
    scanAuthorization.hidden = true;
    weekStatusRow.innerHTML = WEEKDAY_LABELS.map(() => `<td>-</td>`).join("\n");
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

  // Guard-facing entry/exit banner. On exit it shows how the student is
  // authorised to travel home (walk, car, or bus).
  const direction = latestEvent.direction;
  if (direction === "exit") {
    scanAuthorization.textContent = `EXIT · ${authorizationFor(person?.transport)}`;
    scanAuthorization.className = "auth-banner exit";
    scanAuthorization.hidden = false;
  } else if (direction === "entry") {
    scanAuthorization.textContent = "ENTRY";
    scanAuthorization.className = "auth-banner entry";
    scanAuthorization.hidden = false;
  } else {
    scanAuthorization.hidden = true;
  }

  if (person?.photo_url) {
    scanPhoto.src = person.photo_url;
    scanPhoto.hidden = false;
  } else {
    scanPhoto.hidden = true;
  }

  const eventsSource = eventsForWeek.length > 0 ? eventsForWeek : getAllEvents();
  const weekStart = startOfWeek(timestamp);
  const cells = [];
  for (let i = 0; i < WEEKDAY_LABELS.length; i += 1) {
    const dayStart = new Date(weekStart);
    dayStart.setDate(weekStart.getDate() + i);
    const { icon, css, label } = classifyDayStatus(eventsSource, latestEvent.uid, dayStart);
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
        <td>${person.class_name || "-"}</td>
        <td>${person.transport}</td>
      `;
      rosterBody.appendChild(row);
      upsertRosterEntry(person.uid, person);
    });
  } catch (error) {
    rosterBody.innerHTML = `<tr><td colspan="5">Failed to load roster: ${error.message}</td></tr>`;
  }
}

let lastEventsError = null;

function renderEventsTable() {
  const events = getAllEvents().sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
  eventsBody.innerHTML = "";

  if (lastEventsError) {
    const warningRow = document.createElement("tr");
    warningRow.classList.add("warning-row");
    warningRow.innerHTML = `<td colspan="6">Backend unavailable (${lastEventsError.message}). Manual entries will be stored locally until the server is back.</td>`;
    eventsBody.appendChild(warningRow);
  }

  if (events.length === 0) {
    const emptyRow = document.createElement("tr");
    emptyRow.innerHTML = "<td colspan=\"6\">No events yet. Use the manual form to simulate a scan.</td>";
    eventsBody.appendChild(emptyRow);
    renderLastScan(null, events);
    return;
  }

  events.forEach((event) => {
    const row = document.createElement("tr");
    const details = [];
    if (event.details?.person) {
      const person = event.details.person;
      const name = person.name || "Unknown";
      const roleBits = [person.role, person.class_name].filter(Boolean).join(" • ");
      details.push(roleBits ? `${name} (${roleBits})` : name);
    }
    if (event.details?.lateness?.late) {
      details.push(`Late by ${event.details.lateness.minutes || 0} minutes`);
    }
    if (event.details?.notes) {
      details.push(event.details.notes);
    }
    if (event.offline) {
      details.push("Stored locally");
      row.classList.add("offline");
    }
    if (event.details?.manual || event.offline) {
      const recordedBy = event.details?.recorded_by;
      details.push(recordedBy ? `Manual entry by ${recordedBy}` : "Manual entry");
    }

    row.innerHTML = `
      <td>${new Date(event.timestamp).toLocaleString()}</td>
      <td><code>${event.uid}</code></td>
      <td>${event.status}</td>
      <td>${event.direction || "-"}</td>
      <td>${event.reader_location}</td>
      <td>${details.join(" · ") || "-"}</td>
    `;
    eventsBody.appendChild(row);
  });

  renderLastScan(events[0], events);
}

async function loadEvents() {
  try {
    const res = await fetch(`${apiBase}/api/logs`);
    if (!res.ok) throw new Error(`Status ${res.status}`);
    const payload = await res.json();
    backendEvents = payload.events.map((event) => {
      if (event.details?.person) {
        upsertRosterEntry(event.uid, event.details.person);
      }
      return event;
    });
    lastEventsError = null;
    renderEventsTable();
  } catch (error) {
    lastEventsError = error;
    renderEventsTable();
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
  const recordedBy = manualRecordedByInput.value.trim() || null;
  const apiKey = manualApiKeyInput.value.trim();
  if (apiKey) {
    localStorage.setItem("rfid_api_key", apiKey);
  } else {
    localStorage.removeItem("rfid_api_key");
  }

  const name = manualNameInput.value.trim();
  const role = manualRoleInput.value.trim();
  const className = manualClassInput.value.trim();
  const transport = manualTransportInput.value.trim();
  const photoUrl = manualPhotoInput.value.trim();

  const personDetails = { uid };
  if (name) personDetails.name = name;
  if (role) personDetails.role = role;
  if (className) personDetails.class_name = className;
  if (transport) personDetails.transport = transport;
  if (photoUrl) personDetails.photo_url = photoUrl;

  const hasDisplayDetails = Boolean(name || role || className || transport || photoUrl);

  const payload = {
    uid,
    status,
    reader_location: readerLocation,
    manual: true,
    recorded_by: recordedBy,
    notes,
  };

  if (hasDisplayDetails) {
    payload.person = personDetails;
  }

  try {
    const headers = { "Content-Type": "application/json" };
    if (apiKey) {
      headers["X-API-Key"] = apiKey;
    }
    const res = await fetch(`${apiBase}/api/manual-entry`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const message =
        res.status === 401 || res.status === 403
          ? `Staff API key required or not permitted (status ${res.status}).`
          : `Backend rejected the event (status ${res.status}).`;
      const error = new Error(message);
      error.status = res.status;
      throw error;
    }

    const { event: savedEvent } = await res.json();
    backendEvents.push(savedEvent);
    if (savedEvent.details?.person) {
      upsertRosterEntry(uid, savedEvent.details.person);
    } else if (hasDisplayDetails) {
      upsertRosterEntry(uid, personDetails);
    }
    lastEventsError = null;
    renderEventsTable();

    manualMessage.textContent = `Recorded UID ${savedEvent.uid} at ${new Date(savedEvent.timestamp).toLocaleString()}.`;
    manualMessage.className = "message success";
    manualForm.reset();
    manualUidInput.focus();

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
    if (error.status && error.status !== 404) {
      manualMessage.textContent = error.message;
      manualMessage.className = "message error";
      return;
    }

    const fallbackPerson = hasDisplayDetails ? personDetails : rosterByUid.get(uid) || null;
    if (fallbackPerson) {
      upsertRosterEntry(uid, fallbackPerson);
    }

    const offlineEvent = {
      uid,
      status,
      reader_location: readerLocation,
      timestamp: new Date().toISOString(),
      details: {
        person: fallbackPerson,
        notes,
        manual: true,
      },
      offline: true,
    };

    offlineEvents.push(offlineEvent);
    const offlineMessage =
      error.status === 404
        ? "Status 404 (API not found at this URL)"
        : error.message || "Backend offline";
    lastEventsError = new Error(offlineMessage);
    renderEventsTable();

    manualMessage.textContent =
      "Backend offline — stored the scan locally and updated the preview.";
    manualMessage.className = "message success";
    manualForm.reset();
    manualUidInput.focus();

    try {
      await addDoc(collection(db, "manual_scans"), {
        uid,
        status,
        reader_location: readerLocation,
        notes,
        saved_at: serverTimestamp(),
        offline: true,
      });
    } catch (firebaseError) {
      console.warn("Failed to sync manual event to Firebase", firebaseError);
    }

    console.warn("Manual event stored offline", error);
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
