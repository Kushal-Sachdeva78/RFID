# RFID Entry–Exit System for Vasant Valley School

An RFID-based attendance and security system designed to automate **student and teacher entry/exit** using existing ID cards.  
This project aims to make attendance marking, late tracking, and gate verification **faster, paperless, and tamperproof**, while ensuring student safety and accountability.

---

## 🧩 Overview

The system replaces manual processes currently used for:
- Daily student attendance on Veracross (handled manually by class teachers)
- Manual late marking lines every morning
- Paper-based sign-out sheets for student exit
- Manual teacher attendance registers

Instead, it enables **RFID-based automated entry/exit tracking** linked to a **Firebase database**.

---

## 🚨 Problem

- Students currently wait in a “late line” where teachers manually check names and mark strikes for lateness.  
- Attendance is taken manually each morning by class teachers on Veracross.  
- Students are sometimes able to **leave school without permission** or fake entries on exit sheets.  
- Teacher sign-ins are done on **paper sheets**, wasting time and resources.  

---

## 💡 Solution

A tamperproof system using **RFID entry and exit scanners** integrated with a **Firebase database**, allowing:
- Automatic attendance marking when students tap their ID cards.
- Instant lateness detection (even by a second).
- Automatic strike tracking — on 3 strikes, the class teacher is informed.
- Gate-side verification for exit — showing if a student is authorized to leave (walk, car, or bus).
- Teacher attendance logging via the same system.

---

## ⚙️ What the System Does

- Students and teachers tap their existing **RFID ID cards** on entry and exit.  
- The ESP32 connects directly to Firebase to record:
  - Entry time
  - Mode of transport
  - Lateness status
- Guards (bhaiyas) can verify permissions instantly from a **display screen**.
- Students forgetting ID cards can manually sign in at the office (and receive a strike).  
- On 3 strikes in a learning cycle, a mail is sent to class teachers.

---

## 🛠️ Hardware Setup

| Component | Purpose |
|------------|----------|
| **ESP32** | Wi-Fi enabled microcontroller for database communication |
| **RC522 RFID Module** | Scans ID cards |
| **TFT / LCD Screen** | Displays messages for lateness and mode of transport |
| **Custom PCB** | Integrates all components into a single compact module |
| **3D Printed Case** | Protects and houses the hardware, designed by me |

---

## 🧠 Database

- The system uses **Google Firebase** for real-time data synchronization.
- Stores:
  - Student & teacher IDs
  - Entry/exit timestamps
  - Mode of transport
  - Strike counts
- Connected directly via ESP32’s Wi-Fi capabilities.

---

## 🧾 PCB Details

The PCB includes:
- ESP32 microcontroller sockets  
- RC522 connection header  
- Screen header for I2C/TFT pins  
- Buzzer and power control  
- USB and VIN power lines for standalone operation  

Once the PCB design files (`.sch`, `.brd`, `.gerber`) are uploaded, they’ll appear here.

---

## 💻 Code (Coming Soon)

> The firmware will be uploaded soon.  
> It will handle:
> - RFID scanning  
> - Firebase authentication  
> - Attendance and transport logic  
> - Screen display updates  

---

## 🧰 Requirements

- Students and teachers must bring their ID cards daily.
- Guards will handle morning scanning duty.
- Backup manual entry at the office for missing cards.

---

## 🏫 Project Vision

Aiming to make **Vasant Valley School** safer, smarter, and more efficient through student-led innovation — eliminating wasted time, paperwork, and unsafe exits with technology.

---

## 👤 Developed By
**Kushal Sachdeva**  
Vasant Valley School  
