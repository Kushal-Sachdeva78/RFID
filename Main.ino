#include <WiFi.h>
#include <HTTPClient.h>
#include <SPI.h>
#include <MFRC522.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ILI9341.h>
#include <ctype.h>
#include <string.h>

// -----------------------------------------------------------------------------
// Hardware pin assignments (adjust to match your Teensy wiring)
// -----------------------------------------------------------------------------
#define RFID_SS    10
#define RFID_RST    9
#define TFT_CS     23
#define TFT_DC     22
#define TFT_RST     8
#define BUZZER      6

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
const uint8_t  START_HOUR   = 7;      // simulated start-of-day clock
const uint8_t  START_MINUTE = 45;

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
  return dayKey % 5; // Monday (0) .. Friday (4)
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
  drawIdleScreen();
}

void loop() {
  int hour, minute, dayKey;
  softClockNow(hour, minute, dayKey);
  ensureDayPrepared(dayKey);

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
}
