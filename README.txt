================================================================
 CONTROLLING AN INDUSTRIAL ROBOT WITH SPEECH
 KUKA KR4 R600 — Python Voice Control (OpenGLRobot + Real Hardware)
================================================================

Course        : Industrial Robotics Laboratory, Summer Semester 2026
Institution   : Hochschule Ravensburg-Weingarten (RWU), M.Sc. Mechatronics
Supervisors   : Prof. Dr.-Ing. Konrad Woellhaf, Prof. Thomas Seywald
Group         : 2B
Platform      : Windows 10/11 (64-bit)  —  Windows only

----------------------------------------------------------------
 1. PROJECT OVERVIEW
----------------------------------------------------------------
This project investigates how an industrial robot can be
controlled using natural spoken language. A Python application
listens to the operator, converts speech to text with Google
Speech Recognition, normalises the phrase, and drives the KUKA
KR4 R600 through the OpenGLRobot COM API. The same script has
been validated both in simulation (OpenGLRobot 3D CAD window)
and on the physical KUKA KR4 R600 in the RWU robotics lab.

The application answers the five questions posed by the
assignment:

  - Whether and how a robot can be controlled by voice
  - Which commands are necessary for a usable workflow
  - How performant the application must be (latency budget)
  - How safety is guaranteed (halt words, joint-limit checks,
    step-size clamping, wake-word gating)
  - How well an inexperienced user can cope with the system
    (evaluated in the accompanying Statistics Report)

----------------------------------------------------------------
 2. KEY FEATURES
----------------------------------------------------------------
  - Wake-word gated activation ("hello" / "hallo")
  - Four coordinate modes: WORLD, BASE, AXIS, TCP
  - Two motion types: LIN (linear) and PTP (point-to-point)
  - Three speed presets: LOW 25 %, MID 50 %, HIGH 100 %
  - Global HALT / STOP recognised in every state
  - Tkinter dashboard with:
      * live TCP pose and joint-angle readout
      * scrollable voice-command reference
      * activity log with colour-coded severity
      * manual-typing fallback and one-click quick buttons
      * prominent LISTENING / IDLE microphone badge
  - Phonetic-variant tables that repair common Google STT
    mishearings (e.g. "cord in eight" -> "coordinate",
    "bass" -> "base", "ay one" -> "a1")
  - Joint-limit checks before every axis rotation
  - CAD window auto-raise and always-on-top pinning
  - Zero-latency fast path via GUI buttons and text entry
    (bypasses the microphone entirely)

----------------------------------------------------------------
 3. REPOSITORY LAYOUT
----------------------------------------------------------------
  ControllingIndustrialRobotWithSpeech/
  |
  |-- src/
  |     kuka_voice_control_v7.py     Main application
  |
  |-- docs/
  |     Controlling_an_Industrial_Robot_with_Speech_updated.pdf
  |     KUKA_VoiceControl_Report_(konrad_meeting).pdf
  |     KUKA_VoiceControl_SOP.docx   Standard Operating Procedure
  |     Offline_Implementation_Plan.pdf   Vosk migration proposal
  |     Statistics_Report.pdf        Recognition-performance study
  |
  |-- config_examples/
  |     KR4_R600_Stud2.xml           (only if licence permits)
  |
  |-- requirements.txt
  |-- .gitignore
  |-- LICENSE
  |-- README.txt                     (this file)

  NOTE  —  The OpenGLRobot executable, its installer, and the
  robot_cad/ mesh folder are provided by the course supervisor
  and are NOT redistributed in this repository. Obtain them
  from the shared project drive before running the script.

----------------------------------------------------------------
 4. SYSTEM REQUIREMENTS
----------------------------------------------------------------
  - Windows 10 or 11 (64-bit).  Does not run on macOS / Linux.
  - Python 3.11.x (64-bit).  Add Python to PATH during install.
  - OpenGLRobot with the COM component
    "openglrobot.RobotWindowApi" registered.
  - Working microphone recognised by Windows Sound settings.
  - Internet connection (Google Speech-to-Text is a cloud call).
  - Optional: KUKA KR4 R600 hardware for live-robot demo.

----------------------------------------------------------------
 5. INSTALLATION
----------------------------------------------------------------
  Step 1  —  Install Python 3.11.x from https://python.org
             (ensure "Add Python to PATH" is ticked).

  Step 2  —  Install Python dependencies:

               pip install -r requirements.txt

             or, individually:

               pip install SpeechRecognition sounddevice
               pip install pywin32 numpy

  Step 3  —  Install OpenGLRobot from the course share.
             If COM errors appear on launch, reinstall the
             OpenGLRobot MSI as Administrator so the COM
             object is registered correctly.

  Step 4  —  Place the supplied files as follows:

               <yourpath>\OpenGLRobot\env\config\KR4_R600_Stud2.xml
               <yourpath>\OpenGLRobot\robot_cad\

----------------------------------------------------------------
 6. CONFIGURATION
----------------------------------------------------------------
Open src\kuka_voice_control_v7.py and update the two path
constants near the top of the file to match the machine:

  XML_CONFIG    = r"D:\...\OpenGLRobot\env\config\KR4_R600_Stud2.xml"
  CAD_FOLDER    = r"D:\...\OpenGLRobot\robot_cad"

Always keep the leading  r  before the string so Windows
backslashes are treated literally. No other edits are needed.

----------------------------------------------------------------
 7. RUNNING
----------------------------------------------------------------
  cd <project_folder>\src
  python kuka_voice_control_v7.py

On a successful launch two windows appear:

  - The Tkinter dashboard (control GUI)
  - The OpenGLRobot 3D CAD window (auto-pinned on top)

The Activity Log will show:

  [OK]  Robot + CAD READY
  [OK]  CAD window pinned always-on-top.
  [SYS] Listening for wake word...

Say "hello" (or "hallo") to activate the robot. From there,
select a coordinate mode and issue movement commands.

----------------------------------------------------------------
 8. VOICE COMMAND REFERENCE (SUMMARY)
----------------------------------------------------------------
  WAKE / SYSTEM
    hello / hallo ....... activate
    halt / stop ......... freeze motion, exit current state
    home ................ return to home pose
    switch / change ..... open sub-menu (coord / speed / motion)

  COORDINATE SELECTION
    world | base | axis | tcp

  WORLD  and  BASE  mode  (directions)
    forward | backward (back) | left | right | up | down
    x+ / x-  y+ / y-  z+ / z-

  AXIS mode
    a1 .. a6      (or "axis one" .. "axis six")
    cw            rotate clockwise
    acw           rotate anti-clockwise

  TCP mode
    tool 1 | tool 2

  DIRECT SHORTCUTS (any mode, no "switch" needed)
    low | mid | high        change speed
    lin | ptp               change motion type
    home                    go to home

A full, scrollable list of every recognised phrase is shown
inside the dashboard's "Voice Command Reference" panel.

----------------------------------------------------------------
 9. SAFETY MODEL
----------------------------------------------------------------
  - Wake-word gating: no movement is executed before "hello".
  - Global halt: "halt" / "stop" is recognised in every state,
    including inside sub-menus.
  - Hard step-size clamps per speed preset (10 / 20 / 50 mm
    linear; 2 / 5 / 10 degrees per axis command).
  - Joint-limit check: rotations are refused when the next
    angle would fall outside getJointMin / getJointMax.
  - HOME sentinel: the first pose read is validated so the
    script never issues a move from an unknown TCP.
  - Manual override: buttons and text entry always work,
    so the operator is never trapped by a bad recogniser.

----------------------------------------------------------------
 10. KNOWN LIMITATIONS
----------------------------------------------------------------
  - Google STT requires an internet connection and adds
    roughly 1 - 2 seconds of latency per command. An offline
    Vosk-based v8 is documented in Offline_Implementation_Plan.pdf.
  - moveRobotLinear() is always world-referenced. Base mode
    performs an explicit R = Rz @ Ry @ Rx rotation on the
    direction vector to obtain the correct base-frame motion.
  - Windows only, because both pywin32 and OpenGLRobot are
    Windows-specific.

----------------------------------------------------------------
 11. DOCUMENTATION INDEX
----------------------------------------------------------------
  docs/Controlling_an_Industrial_Robot_with_Speech_updated.pdf
      Final project report — motivation, method, results.

  docs/KUKA_VoiceControl_Report_(konrad_meeting).pdf
      Interim technical report presented to Prof. Woellhaf.

  docs/KUKA_VoiceControl_SOP.docx
      Standard Operating Procedure — install, run, shut down.

  docs/Statistics_Report.pdf
      Recognition-accuracy study with histograms and
      per-command reliability figures.

  docs/Offline_Implementation_Plan.pdf
      Migration plan for replacing Google STT with Vosk.

----------------------------------------------------------------
 12. AUTHORS
----------------------------------------------------------------
  Aditya Athavale    (Axis coordinate system, integration)
  <Piyush Mehta>    (Base coordinate system)
  <Krishna Bhuva>    (TCP coordinate system)

  M.Sc. Mechatronics, Hochschule Ravensburg-Weingarten (RWU)
  Industrial Robotics Laboratory, Summer Semester 2026

----------------------------------------------------------------
 13. LICENCE AND USE
----------------------------------------------------------------
This code is released for academic and educational use in
connection with the RWU Industrial Robotics Laboratory. The
OpenGLRobot simulator, the KR4_R600_Stud2.xml scene, and the
robot_cad meshes are the property of their respective owners
and are NOT covered by this repository. Obtain them from the
course supervisor before running the software.

----------------------------------------------------------------
 14. ACKNOWLEDGEMENTS
----------------------------------------------------------------
  Prof. Dr.-Ing. Konrad Woellhaf and Prof. Thomas Seywald for
  supervision, hardware access, and the OpenGLRobot toolchain.

================================================================
 END OF README
================================================================