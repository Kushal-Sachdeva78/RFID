#include <WiFi.h>
#include <HTTPClient.h>
#include <SPI.h>
#include <MFRC522.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ILI9341.h>
#include <ctype.h>
#include <string.h>
#include <time.h>

// -----------------------------------------------------------------------------
// Network and backend configuration.
// Real Wi-Fi credentials and the backend URL live in arduino_secrets.h, which
// is gitignored. Copy arduino_secrets.example.h to arduino_secrets.h and fill it
// in. When the header is absent (for example in CI, which only compiles), these
// placeholders keep the sketch building. With an empty SSID the firmware runs
// fully offline: it still reads cards and renders, and buffers scans to send
// later once a backend URL and network are configured.
// -----------------------------------------------------------------------------
#if __has_include("arduino_secrets.h")
#include "arduino_secrets.h"
#endif
#ifndef WIFI_SSID
#define WIFI_SSID ""
#endif
#ifndef WIFI_PASSWORD
#define WIFI_PASSWORD ""
#endif
#ifndef BACKEND_BASE_URL
#define BACKEND_BASE_URL "http://192.168.1.100:8000"
#endif
#ifndef READER_LOCATION
#define READER_LOCATION "main_gate"
#endif

// -----------------------------------------------------------------------------
// Hardware pin assignments.
// These match the nets on the fabricated KiCad board (ESP32 DevKit V1). The
// earlier values (SS 10, RST 9, TFT_RST 8, BUZZER 6) were leftover from a
// different board: they point at GPIO 6 to 11, which are bonded to the internal
// SPI flash on the WROOM-32 and are not broken out on the DevKit header. The
// shared SPI bus (SCK 18, MOSI 23, MISO 19) is the VSPI default and is wired to
// both the RC522 and the TFT. Verify with a continuity check before flashing.
// -----------------------------------------------------------------------------
#define RFID_SS    14   // RC522 SS   -> ESP32 D14
#define RFID_RST   27   // RC522 RST  -> ESP32 D27
#define TFT_CS      5   // ILI9341 CS  -> ESP32 D5
#define TFT_DC     21   // ILI9341 DC  -> ESP32 D21
#define TFT_RST    22   // ILI9341 RST -> ESP32 D22
#define BUZZER     15   // Buzzer      -> ESP32 D15

// -----------------------------------------------------------------------------
// RFID reader + TFT display objects
// -----------------------------------------------------------------------------
MFRC522 rfid(RFID_SS, RFID_RST);
Adafruit_ILI9341 tft(TFT_CS, TFT_DC, TFT_RST);

// -----------------------------------------------------------------------------
// Timings and attendance thresholds
// -----------------------------------------------------------------------------
const uint16_t DISPLAY_MS   = 5000;   // how long to show a scan before idling
const uint8_t  LATE_HOUR    = 8;
const uint8_t  LATE_MIN     = 5;
const uint8_t  START_HOUR   = 7;      // simulated start-of-day clock (fallback only)
const uint8_t  START_MINUTE = 45;

// -----------------------------------------------------------------------------
// Real clock (NTP) and networking constants.
// India Standard Time is UTC+5:30 with no daylight saving, so a fixed offset is
// exact all year. If NTP never syncs, the firmware falls back to the simulated
// clock above so the demo still works with no network.
// -----------------------------------------------------------------------------
const long     GMT_OFFSET_SEC       = 19800;  // +5:30
const int      DST_OFFSET_SEC       = 0;
const char*    NTP_SERVER_1         = "pool.ntp.org";
const char*    NTP_SERVER_2         = "time.nist.gov";
const char*    TZ_SUFFIX            = "+05:30"; // for ISO 8601 timestamps

const uint32_t WIFI_CONNECT_TIMEOUT_MS = 8000;  // bounded wait at startup
const uint32_t NET_MAINT_INTERVAL_MS   = 15000; // reconnect / resync / flush cadence
const uint8_t  HTTP_RETRIES            = 2;
const uint16_t HTTP_RETRY_DELAY_MS     = 200;
const uint16_t HTTP_TIMEOUT_MS         = 4000;

const int      OFFLINE_BUFFER_SIZE     = 32;   // scans held while offline
const int      PENDING_PAYLOAD_MAX     = 384;  // bytes per buffered scan

// -----------------------------------------------------------------------------
// Attendance data structures
// -----------------------------------------------------------------------------
enum AttendanceStatus : uint8_t {
  STATUS_ABSENT = 0,
  STATUS_PRESENT,
  STATUS_LATE
};

struct Person {
  const char* uid;          // hexadecimal UID string (space separated)
  const char* name;
  const char* role;         // Teacher / Student etc.
  const char* className;    // Homeroom or department label
  const char* transport;    // Mode of transport
  uint16_t    photoColor;   // Solid colour used for the mock photo tile
  AttendanceStatus week[5]; // Monday..Friday status history
  int lastDayKey;           // tracks the simulated day when this card was last marked
};

Person roster[] = {
  {"B3 4B 6F 21", "Kushal Sachdeva", "Student",    "Grade 10A",  "Walk", ILI9341_BLUE,    {STATUS_ABSENT, STATUS_ABSENT, STATUS_ABSENT, STATUS_ABSENT, STATUS_ABSENT}, -1},
  {"A3 3F 7D 21", "Ms Aggarwal",    "Teacher",    "Mathematics", "Bus",  ILI9341_MAGENTA, {STATUS_ABSENT, STATUS_ABSENT, STATUS_ABSENT, STATUS_ABSENT, STATUS_ABSENT}, -1},
  {"93 CE 78 21", "Ms Singh",       "Teacher",    "Science",     "Car",  ILI9341_ORANGE,  {STATUS_ABSENT, STATUS_ABSENT, STATUS_ABSENT, STATUS_ABSENT, STATUS_ABSENT}, -1},
  {"03 BF 82 21", "Ms Bakshi",      "Principal",  "Admin",       "Car",  ILI9341_CYAN,    {STATUS_ABSENT, STATUS_ABSENT, STATUS_ABSENT, STATUS_ABSENT, STATUS_ABSENT}, -1}
};
const int ROSTER_COUNT = sizeof(roster) / sizeof(roster[0]);

// -----------------------------------------------------------------------------
// Global state used for simulated clock + display transitions
// -----------------------------------------------------------------------------
uint32_t bootMillis = 0;
uint32_t lastScreenUpdate = 0;
bool showingScan = false;
int initialisedDayKey = -1;

// Networking / clock state.
bool wifiConfigured = false;   // true when a non-empty SSID is compiled in
bool timeSynced = false;       // true once NTP has given us a real time
uint32_t lastNetMaintenance = 0;

// Offline buffer: scans that could not be posted are kept here and flushed
// (oldest first) once the backend is reachable again.
struct PendingEvent {
  char payload[PENDING_PAYLOAD_MAX];
};
PendingEvent offlineBuffer[OFFLINE_BUFFER_SIZE];
int offlineCount = 0;
bool offlineDropped = false;   // set if the buffer overflowed (oldest dropped)

// -----------------------------------------------------------------------------
// Utility helpers
// -----------------------------------------------------------------------------
String uidToString(const MFRC522::Uid& uid) {
  String s;
  for (byte i = 0; i < uid.size; i++) {
    if (uid.uidByte[i] < 0x10) s += "0";
    s += String(uid.uidByte[i], HEX);
    if (i != uid.size - 1) s += " ";
  }
  s.toUpperCase();
  return s;
}

void softClockNow(int& hour, int& minute, int& dayKey) {
  uint32_t elapsedMinutes = (millis() - bootMillis) / 60000UL;
  uint32_t startMinutes   = START_HOUR * 60UL + START_MINUTE;
  uint32_t totalMinutes   = startMinutes + elapsedMinutes;

  hour   = (totalMinutes / 60UL) % 24;
  minute = totalMinutes % 60UL;
  dayKey = totalMinutes / (24UL * 60UL);
}

uint8_t currentWeekday(int dayKey) {
  // With a real clock, derive the weekday from the date. Monday maps to 0 and
  // Friday to 4; weekend days are clamped into the Friday column so the fixed
  // five column weekly grid never indexes out of bounds.
  if (timeSynced) {
    struct tm t;
    if (getLocalTime(&t, 0)) {
      uint8_t wd = (uint8_t)((t.tm_wday + 6) % 7); // Sun=0..Sat=6 -> Mon=0..Sun=6
      return wd > 4 ? 4 : wd;
    }
  }
  return dayKey % 5; // Monday (0) .. Friday (4) in the simulated fallback
}

bool arrivedLate(int hour, int minute, const char* transport) {
  if (transport != nullptr) {
    char first = transport[0];
    if (first == 'B' || first == 'b') {
      return false; // bus riders are exempt from lateness cutoffs
    }
  }
  if (hour > LATE_HOUR) return true;
  if (hour == LATE_HOUR && minute > LATE_MIN) return true;
  return false;
}

void toneOk() {
  digitalWrite(BUZZER, HIGH);
  delay(60);
  digitalWrite(BUZZER, LOW);
}

void toneError() {
  for (uint8_t i = 0; i < 2; ++i) {
    digitalWrite(BUZZER, HIGH);
    delay(40);
    digitalWrite(BUZZER, LOW);
    delay(40);
  }
}

String initialsOf(const char* name) {
  String initials;
  bool takeNext = true;
  for (const char* p = name; *p; ++p) {
    if (takeNext && isalpha(*p)) {
      initials += (char)toupper(*p);
      takeNext = false;
    }
    if (*p == ' ') {
      takeNext = true;
    }
    if (initials.length() == 2) break;
  }
  if (initials.length() == 0) {
    initials = "??";
  } else if (initials.length() == 1) {
    initials += initials[0];
  }
  return initials;
}

void ensureDayPrepared(int dayKey) {
  if (dayKey == initialisedDayKey) {
    return;
  }
  initialisedDayKey = dayKey;
  uint8_t weekday = currentWeekday(dayKey);
  for (int i = 0; i < ROSTER_COUNT; ++i) {
    if (roster[i].lastDayKey != dayKey) {
      roster[i].week[weekday] = STATUS_ABSENT;
    }
  }
}

// -----------------------------------------------------------------------------
// Drawing helpers
// -----------------------------------------------------------------------------
void drawIdleScreen() {
  tft.fillScreen(ILI9341_BLACK);
  tft.setTextColor(ILI9341_YELLOW);
  tft.setTextSize(3);
  tft.setCursor(30, 60);
  tft.println("TAP RFID");
  tft.setCursor(30, 110);
  tft.println("TO SIGN IN");
}

void drawClockOverlay(int hour, int minute) {
  tft.fillRect(180, 0, 140, 28, ILI9341_BLACK);
  tft.setTextColor(ILI9341_WHITE);
  tft.setTextSize(2);
  tft.setCursor(190, 6);
  if (hour < 10) tft.print('0');
  tft.print(hour);
  tft.print(':');
  if (minute < 10) tft.print('0');
  tft.print(minute);
}

void drawMockPhoto(uint16_t color, const String& initials) {
  const int x = 12;
  const int y = 16;
  const int w = 96;
  const int h = 96;

  tft.fillRoundRect(x, y, w, h, 12, color);
  tft.drawRoundRect(x, y, w, h, 12, ILI9341_WHITE);

  tft.setTextColor(ILI9341_WHITE);
  tft.setTextSize(4);
  int16_t x1, y1;
  uint16_t w1, h1;
  tft.getTextBounds(initials.c_str(), x, y, &x1, &y1, &w1, &h1);
  int textX = x + (w - (int)w1) / 2;
  int textY = y + (h + (int)h1) / 2 - 12;
  tft.setCursor(textX, textY);
  tft.print(initials);
}

void drawStatusIcon(int x, int y, int size, AttendanceStatus status) {
  tft.fillRect(x, y, size, size, ILI9341_BLACK);
  switch (status) {
    case STATUS_PRESENT:
      tft.drawRoundRect(x, y, size, size, 6, ILI9341_GREEN);
      tft.drawLine(x + 6, y + size / 2, x + size / 3, y + size - 6, ILI9341_GREEN);
      tft.drawLine(x + size / 3, y + size - 6, x + size - 6, y + 6, ILI9341_GREEN);
      break;
    case STATUS_LATE:
      tft.drawRoundRect(x, y, size, size, 6, ILI9341_YELLOW);
      tft.drawLine(x + 6, y + size / 2, x + size - 6, y + size / 2, ILI9341_YELLOW);
      break;
    case STATUS_ABSENT:
    default:
      tft.drawRoundRect(x, y, size, size, 6, ILI9341_RED);
      tft.drawLine(x + 6, y + 6, x + size - 6, y + size - 6, ILI9341_RED);
      tft.drawLine(x + size - 6, y + 6, x + 6, y + size - 6, ILI9341_RED);
      break;
  }
}

void drawWeeklyTable(const Person& person) {
  const char* DAY_NAMES[5] = {"Mon", "Tue", "Wed", "Thu", "Fri"};
  const int startX = 12;
  const int startY = 140;
  const int cellSize = 44;

  tft.setTextSize(2);
  for (int i = 0; i < 5; ++i) {
    int x = startX + i * (cellSize + 12);
    tft.setTextColor(ILI9341_WHITE);
    tft.setCursor(x, startY - 24);
    tft.print(DAY_NAMES[i]);
    drawStatusIcon(x, startY, cellSize, person.week[i]);
  }
}

void drawPersonCard(const Person& person, bool duplicate, bool late, int hour, int minute) {
  tft.fillScreen(ILI9341_BLACK);

  drawMockPhoto(person.photoColor, initialsOf(person.name));

  tft.setTextColor(ILI9341_CYAN);
  tft.setTextSize(2);
  tft.setCursor(120, 24);
  tft.print("Name: ");
  tft.setTextColor(ILI9341_WHITE);
  tft.println(person.name);

  tft.setTextColor(ILI9341_CYAN);
  tft.setCursor(120, 52);
  tft.print("Role: ");
  tft.setTextColor(ILI9341_WHITE);
  tft.println(person.role);
  if (person.className && strlen(person.className) > 0) {
    tft.setCursor(120, 72);
    tft.setTextColor(ILI9341_WHITE);
    tft.println(person.className);
  }

  tft.setTextColor(ILI9341_CYAN);
  tft.setCursor(120, 100);
  tft.print("Mode: ");
  tft.setTextColor(ILI9341_WHITE);
  tft.println(person.transport);

  tft.setCursor(120, 128);
  tft.setTextColor(ILI9341_CYAN);
  tft.print("Time: ");
  tft.setTextColor(ILI9341_WHITE);
  if (hour < 10) tft.print('0');
  tft.print(hour);
  tft.print(':');
  if (minute < 10) tft.print('0');
  tft.print(minute);

  tft.setCursor(120, 156);
  if (duplicate) {
    tft.setTextColor(ILI9341_YELLOW);
    tft.println("Already checked in");
  } else if (late) {
    tft.setTextColor(ILI9341_ORANGE);
    tft.println("Status: LATE");
  } else {
    tft.setTextColor(ILI9341_GREEN);
    tft.println("Status: ON TIME");
  }

  drawWeeklyTable(person);
  drawClockOverlay(hour, minute);
}

void drawUnknownCard(const String& uid) {
  tft.fillScreen(ILI9341_BLACK);
  tft.setTextColor(ILI9341_RED);
  tft.setTextSize(3);
  tft.setCursor(20, 80);
  tft.println("UNKNOWN CARD");
  tft.setTextSize(2);
  tft.setCursor(20, 130);
  tft.print(uid);
}

// -----------------------------------------------------------------------------
// Core attendance handling
// -----------------------------------------------------------------------------
void markAttendance(Person& person, bool late, int dayKey) {
  uint8_t weekday = currentWeekday(dayKey);
  person.week[weekday] = late ? STATUS_LATE : STATUS_PRESENT;
  person.lastDayKey = dayKey;
}

// -----------------------------------------------------------------------------
// Real clock (NTP with simulated fallback)
// -----------------------------------------------------------------------------
void clockNow(int& hour, int& minute, int& second, int& dayKey) {
  if (timeSynced) {
    struct tm t;
    if (getLocalTime(&t, 0)) {
      hour = t.tm_hour;
      minute = t.tm_min;
      second = t.tm_sec;
      long localEpoch = (long)time(nullptr) + GMT_OFFSET_SEC;
      dayKey = (int)(localEpoch / 86400L);
      return;
    }
  }
  // Fallback: simulated clock (minute resolution); seconds from millis.
  softClockNow(hour, minute, dayKey);
  second = (int)((millis() / 1000UL) % 60UL);
}

String isoNow() {
  if (timeSynced) {
    struct tm t;
    if (getLocalTime(&t, 0)) {
      char buf[24];
      strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%S", &t);
      return String(buf) + TZ_SUFFIX;
    }
  }
  return String(""); // unknown: let the backend stamp arrival time
}

// -----------------------------------------------------------------------------
// Wi-Fi and NTP
// -----------------------------------------------------------------------------
void syncTime() {
  configTime(GMT_OFFSET_SEC, DST_OFFSET_SEC, NTP_SERVER_1, NTP_SERVER_2);
  struct tm t;
  if (getLocalTime(&t, 3000)) { // short bounded wait so the loop is not stalled
    timeSynced = true;
  }
}

void connectWifiBlocking() {
  if (!wifiConfigured) return;
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED && (millis() - start) < WIFI_CONNECT_TIMEOUT_MS) {
    delay(150);
  }
}

// -----------------------------------------------------------------------------
// Backend posting with retry and an offline buffer
// -----------------------------------------------------------------------------
bool postEvent(const String& payload) {
  if (WiFi.status() != WL_CONNECTED) return false;
  bool ok = false;
  HTTPClient http;
  http.setTimeout(HTTP_TIMEOUT_MS);
  String url = String(BACKEND_BASE_URL) + "/api/logs";
  for (uint8_t attempt = 0; attempt < HTTP_RETRIES && !ok; ++attempt) {
    if (!http.begin(url)) break;
    http.addHeader("Content-Type", "application/json");
    int code = http.POST(payload);
    http.end();
    if (code >= 200 && code < 300) {
      ok = true;
    } else {
      delay(HTTP_RETRY_DELAY_MS);
    }
  }
  return ok;
}

void bufferEvent(const String& payload) {
  if (offlineCount >= OFFLINE_BUFFER_SIZE) {
    // Buffer full: drop the oldest to make room for the newest scan.
    for (int i = 1; i < OFFLINE_BUFFER_SIZE; ++i) {
      offlineBuffer[i - 1] = offlineBuffer[i];
    }
    offlineCount = OFFLINE_BUFFER_SIZE - 1;
    offlineDropped = true;
  }
  strncpy(offlineBuffer[offlineCount].payload, payload.c_str(), PENDING_PAYLOAD_MAX - 1);
  offlineBuffer[offlineCount].payload[PENDING_PAYLOAD_MAX - 1] = '\0';
  offlineCount++;
}

void flushOfflineBuffer() {
  while (offlineCount > 0 && WiFi.status() == WL_CONNECTED) {
    if (!postEvent(String(offlineBuffer[0].payload))) {
      break; // still unreachable; keep the rest for the next attempt
    }
    for (int i = 1; i < offlineCount; ++i) {
      offlineBuffer[i - 1] = offlineBuffer[i];
    }
    offlineCount--;
  }
}

void sendOrBuffer(const String& payload) {
  if (!postEvent(payload)) {
    bufferEvent(payload);
  }
}

String jsonEscape(const char* s) {
  String out;
  if (s == nullptr) return out;
  for (const char* p = s; *p; ++p) {
    char c = *p;
    if (c == '"' || c == '\\') {
      out += '\\';
      out += c;
    } else if (c == '\n' || c == '\r' || c == '\t') {
      out += ' ';
    } else {
      out += c;
    }
  }
  return out;
}

String buildScanPayload(const String& uid, const char* status, const Person* person,
                        bool late, int lateMinutes) {
  String p = "{";
  p += "\"uid\":\"" + jsonEscape(uid.c_str()) + "\",";
  p += "\"status\":\"" + String(status) + "\",";
  p += "\"reader_location\":\"" + jsonEscape(READER_LOCATION) + "\"";
  String ts = isoNow();
  if (ts.length() > 0) {
    p += ",\"timestamp\":\"" + ts + "\"";
  }
  if (person != nullptr) {
    p += ",\"person\":{";
    p += "\"uid\":\"" + jsonEscape(uid.c_str()) + "\",";
    p += "\"name\":\"" + jsonEscape(person->name) + "\",";
    p += "\"role\":\"" + jsonEscape(person->role) + "\",";
    p += "\"transport\":\"" + jsonEscape(person->transport) + "\"";
    if (person->className != nullptr && strlen(person->className) > 0) {
      p += ",\"class_name\":\"" + jsonEscape(person->className) + "\"";
    }
    p += "}";
  }
  p += ",\"lateness\":{\"late\":";
  p += late ? "true" : "false";
  p += ",\"minutes\":" + String(lateMinutes) + "}";
  p += "}";
  return p;
}

void reportScan(const String& uid, const char* status, const Person* person,
                bool late, int lateMinutes) {
  if (!wifiConfigured) return; // no network configured: pure offline demo
  sendOrBuffer(buildScanPayload(uid, status, person, late, lateMinutes));
}

void maintainNetwork() {
  if (!wifiConfigured) return;
  if ((millis() - lastNetMaintenance) < NET_MAINT_INTERVAL_MS) return;
  lastNetMaintenance = millis();

  if (WiFi.status() != WL_CONNECTED) {
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD); // non-blocking reconnect attempt
    return;
  }
  if (!timeSynced) {
    syncTime();
  }
  flushOfflineBuffer();
}

// -----------------------------------------------------------------------------
// Arduino setup / loop
// -----------------------------------------------------------------------------
void setup() {
  pinMode(BUZZER, OUTPUT);
  digitalWrite(BUZZER, LOW);

  SPI.begin();
  rfid.PCD_Init();

  tft.begin();
  tft.setRotation(1); // landscape for wider layout

  bootMillis = millis();

  wifiConfigured = (strlen(WIFI_SSID) > 0);
  if (wifiConfigured) {
    connectWifiBlocking();
    if (WiFi.status() == WL_CONNECTED) {
      syncTime();
    }
  }

  drawIdleScreen();
}

void loop() {
  int hour, minute, second, dayKey;
  clockNow(hour, minute, second, dayKey);
  ensureDayPrepared(dayKey);
  maintainNetwork();

  if (showingScan && (millis() - lastScreenUpdate) > DISPLAY_MS) {
    showingScan = false;
    drawIdleScreen();
  }

  drawClockOverlay(hour, minute);

  if (!rfid.PICC_IsNewCardPresent() || !rfid.PICC_ReadCardSerial()) {
    return;
  }

  String uid = uidToString(rfid.uid);
  rfid.PICC_HaltA();

  int match = -1;
  for (int i = 0; i < ROSTER_COUNT; ++i) {
    if (uid == roster[i].uid) {
      match = i;
      break;
    }
  }

  if (match < 0) {
    toneError();
    drawUnknownCard(uid);
    lastScreenUpdate = millis();
    showingScan = true;
    reportScan(uid, "rejected", nullptr, false, 0);
    return;
  }

  Person& person = roster[match];
  bool alreadyToday = (person.lastDayKey == dayKey);
  bool late = arrivedLate(hour, minute, person.transport);

  if (!alreadyToday) {
    markAttendance(person, late, dayKey);
  }

  toneOk();
  drawPersonCard(person, alreadyToday, late, hour, minute);
  lastScreenUpdate = millis();
  showingScan = true;

  // Report to the backend after rendering so the display stays responsive.
  int lateMinutes = 0;
  if (late) {
    int nowMinutes = hour * 60 + minute;
    int cutoffMinutes = LATE_HOUR * 60 + LATE_MIN;
    lateMinutes = nowMinutes > cutoffMinutes ? (nowMinutes - cutoffMinutes) : 0;
  }
  const char* status = alreadyToday ? "duplicate" : (late ? "late" : "accepted");
  reportScan(uid, status, &person, late, lateMinutes);
}
