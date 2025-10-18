#include <SPI.h>
#include <MFRC522.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ILI9341.h>
#include <LiquidCrystal.h>

#define RFID_SS   14
#define RFID_RST  27
#define TFT_CS    5
#define TFT_DC    21
#define TFT_RST   22
#define BUZZER    15
#define LCD_RS    32
#define LCD_E     33
#define LCD_D4    26
#define LCD_D5    25
#define LCD_D6    4
#define LCD_D7    2  

MFRC522 rfid(RFID_SS, RFID_RST);
Adafruit_ILI9341 tft(TFT_CS, TFT_DC, TFT_RST);
LiquidCrystal lcd(LCD_RS, LCD_E, LCD_D4, LCD_D5, LCD_D6, LCD_D7);

const int LATE_H = 8;
const int LATE_M = 5;
const uint16_t SHOW_MS = 3000;

struct Person {
  const char* uid;
  const char* name;
  const char* role;
  const char* transport;
  int lastDayMarked;
};

Person roster[] = {
  {"B3 4B 6F 21","Kushal Sachdeva","Student","walk",-1},
  {"A3 3F 7D 21","Ms Aggarwal","Teacher","bus",-1},
  {"93 CE 78 21","Ms Singh","Teacher","car",-1},
  {"03 BF 82 21","Ms Bakshi","Principle","car",-1},
};
const int N = sizeof(roster)/sizeof(roster[0]);

uint32_t boot_ms = 0;
int startHour = 8, startMin = 0;
void getSoftTime(int &hh, int &mm, int &dayKey) {
  uint32_t elapsed_min = (millis() - boot_ms) / 60000UL;
  uint32_t totalMin    = (uint32_t)startHour * 60 + startMin + elapsed_min;
  dayKey = totalMin / (24 * 60);
  hh = (totalMin / 60) % 24;
  mm = totalMin % 60;
}

String uidToString(const MFRC522::Uid &u) {
  String s;
  for (byte i = 0; i < u.size; i++) {
    if (u.uidByte[i] < 0x10) s += "0";
    s += String(u.uidByte[i], HEX);
    if (i != u.size - 1) s += " ";
  }
  s.toUpperCase();
  return s;
}

void beep(uint16_t ms=80){ 
  digitalWrite(BUZZER, HIGH); 
  delay(ms); 
  digitalWrite(BUZZER, LOW); 
}

bool isLate(const char* transport, int hh, int mm) {
  if (String(transport) == "bus") return false;
  if (hh > LATE_H) return true;
  if (hh == LATE_H && mm > LATE_M) return true;
  return false;
}

void drawIdle() {
  tft.fillScreen(ILI9341_BLACK);
  tft.setTextSize(3);
  tft.setTextColor(ILI9341_YELLOW);
  tft.setCursor(16, 56);  tft.println("Ready to");
  tft.setCursor(16, 96);  tft.println("SCAN");
}

void drawClock() {
  int hh, mm, dk; 
  getSoftTime(hh, mm, dk);
  tft.fillRect(240-70, 0, 70, 24, ILI9341_BLACK);
  tft.setCursor(240-66, 4);
  tft.setTextSize(2);
  tft.setTextColor(ILI9341_WHITE);
  if (hh < 10) tft.print('0'); tft.print(hh);
  tft.print(':');
  if (mm < 10) tft.print('0'); tft.print(mm);
}

void showPersonScreen(const Person& p, bool alreadyMarked, bool lateNow, int hh, int mm) {
  tft.fillScreen(ILI9341_BLACK);
  tft.setTextSize(2);

  tft.setCursor(16, 28);
  tft.setTextColor(ILI9341_CYAN);  tft.print("Name: ");
  tft.setTextColor(ILI9341_WHITE); tft.println(p.name);

  tft.setCursor(16, 56);
  tft.setTextColor(ILI9341_CYAN);  tft.print("Role: ");
  tft.setTextColor(ILI9341_WHITE); tft.println(p.role);

  tft.setCursor(16, 84);
  tft.setTextColor(ILI9341_CYAN);  tft.print("Mode: ");
  tft.setTextColor(ILI9341_WHITE); tft.println(p.transport);

  tft.setCursor(16, 112);
  if (alreadyMarked) { 
    tft.setTextColor(ILI9341_YELLOW); 
    tft.println("Already marked today"); 
  } else { 
    tft.setTextColor(lateNow ? ILI9341_ORANGE : ILI9341_GREEN); 
    tft.println(lateNow ? "Status: LATE" : "Status: ON TIME"); 
  }

  tft.setCursor(16, 140);
  tft.setTextColor(ILI9341_CYAN);  tft.print("Time: ");
  tft.setTextColor(ILI9341_WHITE);
  if (hh < 10) tft.print('0'); tft.print(hh); 
  tft.print(':'); 
  if (mm < 10) tft.print('0'); tft.print(mm);

  drawClock();
}

void setup() {
  Serial.begin(115200);
  pinMode(BUZZER, OUTPUT); digitalWrite(BUZZER, LOW);

  SPI.begin();
  tft.begin();
  tft.setRotation(0);    // portrait
  drawIdle(); drawClock();

  rfid.PCD_Init();
  lcd.begin(16, 2);

  boot_ms = millis();
}

void loop() {
  static uint32_t lastTick = 0;
  if (millis() - lastTick > 1000) { lastTick = millis(); drawClock(); }

  if (!rfid.PICC_IsNewCardPresent() || !rfid.PICC_ReadCardSerial()) return;

  String uid = uidToString(rfid.uid);

  int hh, mm, dayKey;
  getSoftTime(hh, mm, dayKey);

  int idx = -1;
  for (int i = 0; i < N; i++) if (uid == roster[i].uid) { idx = i; break; }

  if (idx == -1) {
    beep(40); delay(50); beep(40);
    tft.fillScreen(ILI9341_BLACK);
    tft.setTextSize(3); tft.setTextColor(ILI9341_RED);
    tft.setCursor(16, 90); tft.println("UNKNOWN");
    lcd.clear(); lcd.setCursor(0,0); lcd.print("Unknown Card");
    delay(SHOW_MS);
    lcd.clear(); drawIdle(); drawClock();
    rfid.PICC_HaltA();
    return;
  }

  beep(90);

  bool already = (roster[idx].lastDayMarked == dayKey);
  bool lateNow = isLate(roster[idx].transport, hh, mm);
  if (!already) roster[idx].lastDayMarked = dayKey;

  lcd.clear();
  {
    String nm = String(roster[idx].name);
    if (nm.length() > 16) nm = nm.substring(0,16);
    lcd.setCursor(0,0); lcd.print(nm);
  }
  lcd.setCursor(0,1); lcd.print("Mode: "); lcd.print(roster[idx].transport);

  showPersonScreen(roster[idx], already, lateNow, hh, mm);

  delay(SHOW_MS);
  lcd.clear();
  drawIdle(); drawClock();

  rfid.PICC_HaltA();
}
