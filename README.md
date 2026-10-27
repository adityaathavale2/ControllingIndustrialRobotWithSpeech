# Controlling an Industrial Robot with Speech

Voice-controlled interface for the **KUKA KR4 R600** industrial robot — 
Python application that converts spoken commands into robot motion via 
the OpenGLRobot COM API, validated on both simulation and physical hardware.

![Dashboard screenshot or hero image](results/dashboard.png)

## Overview

How well can a 6-axis industrial robot be driven by natural spoken 
language, and what does it cost in latency, accuracy, and safety?

This project builds a Python application that:
- Listens for a wake word, converts speech to text via Google STT
- Normalises the phrase against phonetic variants
- Drives the KUKA KR4 R600 through the OpenGLRobot COM API
- Enforces hard safety constraints (halt words, joint limits, step clamps)

Developed as coursework for **Industrial Robotics Laboratory**, 
M.Sc. Mechatronics at Ravensburg-Weingarten University of Applied Sciences (RWU).

## Key features

| Feature | Detail |
|---|---|
| Wake-word activation | "hello" / "hallo" required before any motion |
| Coordinate modes | WORLD, BASE, AXIS, TCP |
| Motion types | LIN (linear) and PTP (point-to-point) |
| Speed presets | LOW (25%), MID (50%), HIGH (100%) |
| Safety halt | Global "halt" / "stop" recognised in every state |
| Dashboard | Tkinter GUI with live pose, command reference, activity log |
| Fallback input | Manual typing + one-click quick buttons |

## System requirements

- Windows 10 or 11 (64-bit) — Windows only (does not run on macOS/Linux)
- Python 3.11.x (64-bit)
- OpenGLRobot with COM component `openglrobot.RobotWindowApi` registered
- Working microphone
- Internet connection (Google STT is a cloud call)

## Installation

```bash
pip install -r requirements.txt
```

Then install OpenGLRobot from official course channels and place the 
provided config and CAD assets as described in the Configuration section.

## Voice command reference

### Wake / system
| Command | Action |
|---|---|
| hello / hallo | Activate the robot |
| halt / stop | Freeze motion, exit current state |
| home | Return to home pose |
| switch / change | Open sub-menu (coord / speed / motion) |

### Coordinate selection
`world` · `base` · `axis` · `tcp`

### WORLD and BASE mode
Directions: `forward`, `backward`, `left`, `right`, `up`, `down`  
Axes: `x+/x-`, `y+/y-`, `z+/z-`

### AXIS mode
`a1 .. a6` (or "axis one" .. "axis six")  
Rotation: `cw` (clockwise), `acw` (anti-clockwise)

### TCP mode
`tool 1`, `tool 2`

## Safety model

- Wake-word gating — no movement before "hello"
- Global halt — "halt" / "stop" recognised in every state including sub-menus
- Step-size clamps per speed preset: 10/20/50 mm linear, 2/5/10° angular
- Joint-limit check before every axis rotation
- HOME pose validation on startup
- Manual override via GUI always available

## Known limitations

- Google STT requires internet; adds ~1-2 s latency per command
- `moveRobotLinear()` is always world-referenced; BASE mode applies 
  explicit `R = Rz @ Ry @ Rx` rotation
- Windows only (pywin32 and OpenGLRobot dependencies)

## Project structure

## Known limitations

- Google STT requires internet; adds ~1-2 s latency per command
- `moveRobotLinear()` is always world-referenced; BASE mode applies 
  explicit `R = Rz @ Ry @ Rx` rotation
- Windows only (pywin32 and OpenGLRobot dependencies)

## Project structure

```
ControllingIndustrialRobotWithSpeech/
├── src/
│ └── kuka_voice_control_v7.py
├── docs/
│ ├── Final_Report.pdf
│ ├── Interim_Report.pdf
│ ├── Statistics_Report.pdf
│ ├── SOP.docx
│ └── Offline_Implementation_Plan.pdf
├── requirements.txt
├── .gitignore
├── LICENSE
└── README.md
```


## Documentation

- **Final Report** — motivation, method, results
- **Interim Report** — technical progress presented to supervisor
- **Statistics Report** — recognition-accuracy study with histograms
- **SOP** — Standard Operating Procedure
- **Offline Implementation Plan** — Vosk migration proposal

## Authors

- **Aditya Athavale** — Axis coordinate system, system integration
- **[Groupmate 2]** — Base coordinate system
- **[Groupmate 3]** — TCP coordinate system

M.Sc. Mechatronics, Hochschule Ravensburg-Weingarten (RWU)

## Acknowledgements

Prof. Dr.-Ing. Konrad Woellhaf and Prof. Thomas Seywald for supervision 
and hardware access.

## Licence

Academic use only. The OpenGLRobot simulator, KR4_R600_Stud2.xml scene, 
and robot_cad meshes are the property of their respective owners and 
are not covered by this repository.

## Author

Aditya Athavale — M.Sc. Mechatronics, Ravensburg-Weingarten University of Applied Sciences

[GitHub](https://github.com/adityaathavale2) · [LinkedIn](https://www.linkedin.com/in/adityaathavale/)
