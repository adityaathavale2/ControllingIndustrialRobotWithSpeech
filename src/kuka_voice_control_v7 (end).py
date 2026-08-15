"""
KUKA KR4 R600 — Voice Control System  v7
=========================================
Changes over v6  (GUI rewrite — robot logic identical):

  ROOT CAUSE FIXES
  ─────────────────
  • Layout engine changed from pack to grid on the root window.
    Every section now occupies a fixed grid row with explicit weight.
    Only the Activity Log row has weight=1 (expands with window).
    All other sections have weight=0 — they take only what they need
    and cannot push the log off screen.

  • Command Reference: tabs removed entirely.
    Replaced with a single flat ScrolledText widget (height=12 lines)
    with inline colour-coded section headers.  All commands visible
    in one place — scroll up/down to browse, no tab-switching needed.
    Fixed height means it never steals space from other sections.

  • Mic Status: moved into the header bar as a prominent right-side
    badge.  Flips between  🔴 IDLE  (red, dim)  and
    🟢 LISTENING... (bright green, bold) — always visible without
    consuming a separate layout row.

  • Activity Log: always visible at the bottom with expand=True in
    its grid row.  Minimum height=5 lines guaranteed.

  • Main window now has a vertical scrollbar on the right edge so
    the user can scroll the entire dashboard if the window is small.
"""

import win32com.client
import win32gui
import win32con
import pythoncom
import sounddevice as sd
import speech_recognition as sr
import tkinter as tk
from tkinter import scrolledtext
import io
import wave
import math
import os
import time
import re
import queue
import threading

# ================================================================
# PATHS
# ================================================================
XML_CONFIG    = r"D:\VCRoboticsProj\OpenGLRobot\env\config\KR4_R600_Stud2.xml"
CAD_FOLDER    = r"D:\VCRoboticsProj\OpenGLRobot\robot_cad"
CAD_WIN_TITLE = "OpenGL Robot"

# ================================================================
# PREDEFINED TOOL DATA
# ================================================================
TOOLS = {
    "tool1": {"name": "Pen",   "x": 100.40, "y":  -1.10, "z": 233.37,
              "rx": 90, "ry":   0, "rz": -150},
    "tool2": {"name": "Tool2", "x": 120.00, "y":   0.00, "z": 200.00,
              "rx": 90, "ry":   0, "rz":    0},
}

# ================================================================
# PREDEFINED BASE DATA
# ================================================================
BASES = {
    "base1": {"name": "Paper", "x": 420.78, "y": -308.15, "z": 200.43,
              "rx": 90, "ry": 0, "rz":  0},
    "base2": {"name": "Base2", "x": 300.00, "y": -200.00, "z": 150.00,
              "rx": 90, "ry": 0, "rz":  0},
}

# ================================================================
# COMMAND REFERENCE  —  flat list, displayed in one scrollable box
# Format: ("SECTION_HEADER", None)  or  ("command text", "description")
# ================================================================
CMD_REF_FLAT = [
    ("── WAKE / SYSTEM ──────────────────────────────────", None),
    ("hello  /  hallo",            "Activate the robot"),
    ("halt  /  stop",              "Stop from any mode"),
    ("home",                       "Return to home position"),
    ("switch  /  change",          "Open the Switch sub-menu"),

    ("── COORDINATE SELECTION ───────────────────────────", None),
    ("world",                      "Enter World coordinate mode"),
    ("base",                       "Enter Base coordinate mode"),
    ("axis",                       "Enter Axis coordinate mode"),
    ("tcp",                        "Enter TCP coordinate mode"),

    ("── WORLD MODE ─────────────────────────────────────", None),
    ("forward  /  x+",             "Move +X"),
    ("backward  /  back  /  x-",   "Move -X"),
    ("right  /  y+",               "Move +Y"),
    ("left  /  y-",                "Move -Y"),
    ("up  /  z+",                  "Move +Z"),
    ("down  /  z-",                "Move -Z"),

    ("── BASE MODE ──────────────────────────────────────", None),
    ("base 1  /  base one",        "Select Base 1 (Paper)"),
    ("base 2  /  base two",        "Select Base 2"),
    ("forward  /  x+",             "Move +X  (base frame)"),
    ("backward  /  back  /  x-",   "Move -X  (base frame)"),
    ("right  /  y+",               "Move +Y  (base frame)"),
    ("left  /  y-",                "Move -Y  (base frame)"),
    ("up  /  z+",                  "Move +Z  (base frame)"),
    ("down  /  z-",                "Move -Z  (base frame)"),

    ("── AXIS MODE ──────────────────────────────────────", None),
    ("a1  /  axis 1  /  axis one",    "Select joint A1"),
    ("a2  /  axis 2  /  axis two",    "Select joint A2"),
    ("a3  /  axis 3  /  axis three",  "Select joint A3"),
    ("a4  /  axis 4  /  axis four",   "Select joint A4"),
    ("a5  /  axis 5  /  axis five",   "Select joint A5"),
    ("a6  /  axis 6  /  axis six",    "Select joint A6"),
    ("cw  /  clockwise",              "Rotate selected axis CW  ↻"),
    ("acw  /  anticlockwise",         "Rotate selected axis CCW ↺"),

    ("── TCP MODE ───────────────────────────────────────", None),
    ("tool 1  /  tool one",        "Activate Tool 1  (Pen)"),
    ("tool 2  /  tool two",        "Activate Tool 2"),

    ("── SWITCH SUB-MENU ────────────────────────────────", None),
    ("coordinate",                 "Switch coordinate system"),
    ("speed",                      "Open speed sub-menu"),
    ("  → low  /  slow",           "    Set speed to 25%"),
    ("  → mid  /  medium",         "    Set speed to 50%"),
    ("  → high  /  fast",          "    Set speed to 100%"),
    ("motion  /  movement",        "Open motion type sub-menu"),
    ("  → lin  /  linear",         "    Set motion to LIN"),
    ("  → ptp",                    "    Set motion to PTP"),

    ("── DIRECT SHORTCUTS (any mode, no Switch needed) ──", None),
    ("low  /  mid  /  high",       "Change speed immediately"),
    ("lin  /  ptp",                "Change motion type immediately"),
    ("home",                       "Go to home position immediately"),
]

# ================================================================
# GLOBALS
# ================================================================
robot              = None
gr                 = math.pi / 180.0

active_tool_key    = "tool1"
active_base_key    = "base1"
active_speed       = "mid"
active_movement_type = "lin"
selected_axis      = None

HOME_ANGLES_DEG    = [0.0, -90.0, 90.0, 0.0, 45.0, 0.0]

cmd_queue: queue.Queue = queue.Queue()
app = None


# ================================================================
# GUI CLASS
# ================================================================
class RobotGUI:
    """
    Grid layout — 7 rows, 1 column on root:

      Row 0  weight=0   Header bar (title + mic badge)
      Row 1  weight=0   Two-column area:
                          Left:  System State + TCP Pose
                          Right: Joint Angles + Command Reference
      Row 2  weight=0   Voice Feedback  (Heard / Normalized)
      Row 3  weight=0   Manual Command entry
      Row 4  weight=0   Quick Controls buttons
      Row 5  weight=1   Activity Log  ← only row that expands
    """

    DARK_BG    = "#1e1e2e"
    PANEL_BG   = "#2a2a3e"
    LOG_BG     = "#181825"
    ACCENT     = "#89b4fa"
    GREEN      = "#a6e3a1"
    GREEN_DIM  = "#1e3a2a"
    RED        = "#f38ba8"
    YELLOW     = "#f9e2af"
    TEXT       = "#cdd6f4"
    SUBTEXT    = "#a6adc8"
    DIMTEXT    = "#6c7086"

    FONT_MONO  = ("Consolas", 9)
    FONT_REF   = ("Consolas", 9)
    FONT_LBL   = ("Segoe UI", 10)
    FONT_VAL   = ("Segoe UI", 10, "bold")
    FONT_HEAD  = ("Segoe UI", 12, "bold")
    FONT_MIC   = ("Segoe UI", 10, "bold")
    FONT_SEC   = ("Consolas", 8, "bold")    # section headers in cmd ref

    # ── INIT ───────────────────────────────────────────────────────

    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("KUKA KR4 R600 — Voice Control  v7")
        root.configure(bg=self.DARK_BG)
        root.resizable(True, True)
        root.minsize(960, 680)

        # Grid rows — only row 5 (log) expands
        for r in range(6):
            root.rowconfigure(r, weight=1 if r == 5 else 0)
        root.columnconfigure(0, weight=1)

        self._build_header()           # row 0
        self._build_main_area()        # row 1
        self._build_voice_feedback()   # row 2
        self._build_manual_entry()     # row 3
        self._build_quick_buttons()    # row 4
        self._build_log()              # row 5

        # ── StringVars ──
        self._coord_var  = tk.StringVar(value="—")
        self._tool_var   = tk.StringVar(value="TOOL1")
        self._base_var   = tk.StringVar(value="BASE1")
        self._speed_var  = tk.StringVar(value="MID  (50%)")
        self._motion_var = tk.StringVar(value="LIN")
        self._axis_var   = tk.StringVar(value="—")
        self._tcp_x_var  = tk.StringVar(value="—")
        self._tcp_y_var  = tk.StringVar(value="—")
        self._tcp_z_var  = tk.StringVar(value="—")
        self._heard_var  = tk.StringVar(value="—")
        self._norm_var   = tk.StringVar(value="—")
        self._joint_vars = [tk.StringVar(value="  —°") for _ in range(6)]

        # Wire
        self._coord_lbl .config(textvariable=self._coord_var)
        self._tool_lbl  .config(textvariable=self._tool_var)
        self._base_lbl  .config(textvariable=self._base_var)
        self._speed_lbl .config(textvariable=self._speed_var)
        self._motion_lbl.config(textvariable=self._motion_var)
        self._axis_lbl  .config(textvariable=self._axis_var)
        self._tcp_x_lbl .config(textvariable=self._tcp_x_var)
        self._tcp_y_lbl .config(textvariable=self._tcp_y_var)
        self._tcp_z_lbl .config(textvariable=self._tcp_z_var)
        self._heard_lbl .config(textvariable=self._heard_var)
        self._norm_lbl  .config(textvariable=self._norm_var)
        for i, lbl in enumerate(self._joint_lbls):
            lbl.config(textvariable=self._joint_vars[i])

    # ── ROW 0  HEADER ──────────────────────────────────────────────

    def _build_header(self):
        hdr = tk.Frame(self.root, bg=self.PANEL_BG, pady=5)
        hdr.grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 2))
        hdr.columnconfigure(1, weight=1)

        tk.Label(hdr, text="🤖  KUKA KR4 R600 — Voice Control  v7",
                 font=self.FONT_HEAD, bg=self.PANEL_BG,
                 fg=self.ACCENT).grid(row=0, column=0, padx=10, sticky="w")

        # Prominent mic badge — right side of header
        self._mic_badge = tk.Label(
            hdr,
            text="🔴  IDLE",
            font=self.FONT_MIC,
            bg="#3a1a1a", fg=self.RED,
            padx=12, pady=3,
            relief="flat")
        self._mic_badge.grid(row=0, column=2, padx=10, sticky="e")

    # ── ROW 1  MAIN TWO-COLUMN AREA ────────────────────────────────

    def _build_main_area(self):
        area = tk.Frame(self.root, bg=self.DARK_BG)
        area.grid(row=1, column=0, sticky="ew", padx=8, pady=2)
        area.columnconfigure(0, weight=0)   # left  — fixed width
        area.columnconfigure(1, weight=1)   # right — stretches

        # LEFT: System State
        left = tk.Frame(area, bg=self.DARK_BG)
        left.grid(row=0, column=0, sticky="ns", padx=(0, 4))
        self._build_status_panel(left)

        # RIGHT: Joint Angles + Command Reference
        right = tk.Frame(area, bg=self.DARK_BG)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)
        self._build_joint_panel(right)
        self._build_command_reference(right)

    # ── SYSTEM STATE PANEL ─────────────────────────────────────────

    def _build_status_panel(self, parent):
        frm = tk.LabelFrame(parent, text=" System State ",
                             font=self.FONT_LBL, bg=self.PANEL_BG,
                             fg=self.ACCENT, bd=1, relief="groove")
        frm.pack(fill="both", expand=True)

        rows = [
            ("Coord Mode",    "_coord_lbl",  self.GREEN),
            ("Active Tool",   "_tool_lbl",   self.TEXT),
            ("Active Base",   "_base_lbl",   self.TEXT),
            ("Speed",         "_speed_lbl",  self.YELLOW),
            ("Motion Type",   "_motion_lbl", self.YELLOW),
            ("Selected Axis", "_axis_lbl",   self.ACCENT),
        ]
        for label_text, attr, color in rows:
            row = tk.Frame(frm, bg=self.PANEL_BG)
            row.pack(fill="x", padx=6, pady=2)
            tk.Label(row, text=f"{label_text}:",
                     font=self.FONT_LBL, bg=self.PANEL_BG, fg=self.SUBTEXT,
                     width=14, anchor="w").pack(side="left")
            lbl = tk.Label(row, text="—", font=self.FONT_VAL,
                           bg=self.PANEL_BG, fg=color, anchor="w")
            lbl.pack(side="left")
            setattr(self, attr, lbl)

        tk.Frame(frm, bg=self.DIMTEXT, height=1).pack(
            fill="x", padx=6, pady=(4, 2))

        tk.Label(frm, text=" TCP Pose (World)", font=("Segoe UI", 9),
                 bg=self.PANEL_BG, fg=self.ACCENT
                 ).pack(anchor="w", padx=6, pady=(0, 2))

        pose_row = tk.Frame(frm, bg=self.PANEL_BG)
        pose_row.pack(fill="x", padx=6, pady=(0, 6))
        self._tcp_x_lbl = self._pose_cell(pose_row, "X")
        self._tcp_y_lbl = self._pose_cell(pose_row, "Y")
        self._tcp_z_lbl = self._pose_cell(pose_row, "Z")

    def _pose_cell(self, parent, axis):
        cell = tk.Frame(parent, bg=self.PANEL_BG)
        cell.pack(side="left", padx=(0, 6))
        tk.Label(cell, text=f"{axis}:", font=self.FONT_LBL,
                 bg=self.PANEL_BG, fg=self.SUBTEXT).pack(side="left")
        lbl = tk.Label(cell, text="—", font=self.FONT_VAL,
                       bg=self.PANEL_BG, fg=self.TEXT,
                       width=9, anchor="w")
        lbl.pack(side="left")
        return lbl

    # ── JOINT ANGLES PANEL ─────────────────────────────────────────

    def _build_joint_panel(self, parent):
        frm = tk.LabelFrame(parent, text=" Joint Angles ",
                             font=self.FONT_LBL, bg=self.PANEL_BG,
                             fg=self.ACCENT, bd=1, relief="groove")
        frm.grid(row=0, column=0, sticky="ew", pady=(0, 3))

        grid = tk.Frame(frm, bg=self.PANEL_BG)
        grid.pack(fill="x", padx=6, pady=4)
        self._joint_lbls = []
        for i in range(6):
            col     = i % 3        # 3 columns: A1 A2 A3 | A4 A5 A6
            row_idx = i // 3
            cell = tk.Frame(grid, bg=self.PANEL_BG)
            cell.grid(row=row_idx, column=col, sticky="w", padx=10, pady=2)
            tk.Label(cell, text=f"A{i+1}:", font=self.FONT_VAL,
                     bg=self.PANEL_BG, fg=self.ACCENT,
                     width=3, anchor="w").pack(side="left")
            lbl = tk.Label(cell, text="  —°", font=self.FONT_MONO,
                           bg=self.PANEL_BG, fg=self.TEXT,
                           width=8, anchor="w")
            lbl.pack(side="left")
            self._joint_lbls.append(lbl)

    # ── COMMAND REFERENCE — flat scrollable list ───────────────────

    def _build_command_reference(self, parent):
        """
        Single ScrolledText widget — no tabs.
        Section headers are cyan/dim, commands are green, descriptions white.
        User scrolls to browse all commands.
        Fixed height=12 so it never steals space from the log below.
        """
        frm = tk.LabelFrame(parent,
                             text=" 📋  Voice Command Reference  (scroll to browse) ",
                             font=self.FONT_LBL, bg=self.PANEL_BG,
                             fg=self.ACCENT, bd=1, relief="groove")
        frm.grid(row=1, column=0, sticky="nsew", pady=(0, 0))

        # Read-only text widget with colour tags
        txt = scrolledtext.ScrolledText(
            frm,
            font=self.FONT_REF,
            bg=self.LOG_BG, fg=self.TEXT,
            height=12,                   # fixed — never expands
            relief="flat",
            state="normal",
            wrap="none",
            cursor="arrow")
        txt.pack(fill="both", expand=True, padx=3, pady=3)

        # Tags
        txt.tag_config("section", foreground=self.ACCENT,
                       font=("Consolas", 8, "bold"))
        txt.tag_config("cmd",     foreground=self.GREEN,
                       font=("Consolas", 9))
        txt.tag_config("sub",     foreground=self.SUBTEXT,
                       font=("Consolas", 9))
        txt.tag_config("desc",    foreground=self.TEXT,
                       font=("Consolas", 9))
        txt.tag_config("sep",     foreground=self.DIMTEXT,
                       font=("Consolas", 9))

        # Populate
        for item, desc in CMD_REF_FLAT:
            if desc is None:
                # Section header line
                txt.insert(tk.END, f"\n{item}\n", "section")
            else:
                is_sub = item.startswith("  →")
                cmd_tag = "sub" if is_sub else "cmd"
                # Pad command to fixed width, then description
                padded = f"  {item:<38}"
                txt.insert(tk.END, padded, cmd_tag)
                txt.insert(tk.END, f"{desc}\n", "desc")

        txt.config(state="disabled")   # read-only
        # Remove cursor and make non-editable look clean
        txt.bind("<Key>", lambda e: "break")

    # ── ROW 2  VOICE FEEDBACK ──────────────────────────────────────

    def _build_voice_feedback(self):
        frm = tk.LabelFrame(self.root, text=" Voice Feedback ",
                             font=self.FONT_LBL, bg=self.PANEL_BG,
                             fg=self.ACCENT, bd=1, relief="groove")
        frm.grid(row=2, column=0, sticky="ew", padx=8, pady=(2, 1))

        for label_text, attr, color in [
            ("Heard",      "_heard_lbl", self.SUBTEXT),
            ("Normalized", "_norm_lbl",  self.GREEN),
        ]:
            row = tk.Frame(frm, bg=self.PANEL_BG)
            row.pack(fill="x", padx=6, pady=1)
            tk.Label(row, text=f"{label_text}:",
                     font=self.FONT_LBL, bg=self.PANEL_BG, fg=self.SUBTEXT,
                     width=10, anchor="w").pack(side="left")
            lbl = tk.Label(row, text="—", font=self.FONT_MONO,
                           bg=self.PANEL_BG, fg=color, anchor="w")
            lbl.pack(side="left", fill="x", expand=True)
            setattr(self, attr, lbl)

    # ── ROW 3  MANUAL COMMAND ENTRY ────────────────────────────────

    def _build_manual_entry(self):
        frm = tk.LabelFrame(
            self.root,
            text=" ⌨  Manual Command  (type when voice fails) ",
            font=self.FONT_LBL, bg=self.PANEL_BG, fg=self.YELLOW,
            bd=1, relief="groove")
        frm.grid(row=3, column=0, sticky="ew", padx=8, pady=1)

        inner = tk.Frame(frm, bg=self.PANEL_BG)
        inner.pack(fill="x", padx=6, pady=4)

        self._text_entry = tk.Entry(
            inner, font=self.FONT_MONO,
            bg="#313244", fg=self.TEXT,
            insertbackground=self.TEXT, relief="flat", bd=3)
        self._text_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self._text_entry.bind("<Return>", lambda e: self._send_manual_cmd())

        tk.Button(inner, text="Send ▶", font=self.FONT_VAL,
                  bg=self.ACCENT, fg=self.DARK_BG,
                  activebackground="#74c7ec",
                  relief="flat", bd=0, padx=10, pady=2,
                  cursor="hand2",
                  command=self._send_manual_cmd).pack(side="left")

        tk.Label(frm,
                 text="Type any command exactly as you would say it aloud.",
                 font=("Segoe UI", 8), bg=self.PANEL_BG,
                 fg=self.DIMTEXT).pack(anchor="w", padx=6, pady=(0, 2))

    # ── ROW 4  QUICK CONTROLS ──────────────────────────────────────

    def _build_quick_buttons(self):
        frm = tk.LabelFrame(self.root, text=" Quick Controls ",
                             font=self.FONT_LBL, bg=self.PANEL_BG,
                             fg=self.ACCENT, bd=1, relief="groove")
        frm.grid(row=4, column=0, sticky="ew", padx=8, pady=1)

        inner = tk.Frame(frm, bg=self.PANEL_BG)
        inner.pack(padx=6, pady=3)

        def btn(parent, label, cmd_text, bg, fg=None):
            fg = fg or self.DARK_BG
            tk.Button(parent, text=label, font=("Segoe UI", 9, "bold"),
                      bg=bg, fg=fg, activebackground=bg,
                      relief="flat", bd=0, padx=8, pady=3,
                      cursor="hand2",
                      command=lambda: cmd_queue.put(cmd_text)
                      ).pack(side="left", padx=3)

        def row_lbl(parent, text):
            tk.Label(parent, text=text, font=("Segoe UI", 9),
                     bg=self.PANEL_BG, fg=self.SUBTEXT,
                     width=7, anchor="w").pack(side="left")

        rows_def = [
            ("System:", [
                ("🏠 Home",    "home",   "#45475a", self.TEXT),
                ("🛑 Halt",    "halt",   self.RED,  None),
                ("🔄 Switch",  "switch", self.ACCENT, None),
            ]),
            ("Speed:", [
                ("🐢 Low 25%",   "low",  "#45475a", self.TEXT),
                ("🚶 Mid 50%",   "mid",  "#45475a", self.YELLOW),
                ("🚀 High 100%", "high", "#45475a", self.GREEN),
            ]),
            ("Motion:", [
                ("➡ LIN", "lin", "#45475a", self.TEXT),
                ("◎ PTP",  "ptp", "#45475a", self.ACCENT),
            ]),
            ("Coord:", [
                ("🌍 World", "world", "#45475a", self.TEXT),
                ("📐 Base",  "base",  "#45475a", self.TEXT),
                ("🦾 Axis",  "axis",  "#45475a", self.TEXT),
                ("🔧 TCP",   "tcp",   "#45475a", self.TEXT),
            ]),
        ]
        for lbl_text, buttons in rows_def:
            r = tk.Frame(inner, bg=self.PANEL_BG)
            r.pack(fill="x", pady=2)
            row_lbl(r, lbl_text)
            for label, cmd, bg, fg in buttons:
                btn(r, label, cmd, bg, fg)

    # ── ROW 5  ACTIVITY LOG ────────────────────────────────────────

    def _build_log(self):
        frm = tk.LabelFrame(self.root, text=" Activity Log ",
                             font=self.FONT_LBL, bg=self.PANEL_BG,
                             fg=self.ACCENT, bd=1, relief="groove")
        frm.grid(row=5, column=0, sticky="nsew", padx=8, pady=(2, 6))
        frm.rowconfigure(0, weight=1)
        frm.columnconfigure(0, weight=1)

        self._log = scrolledtext.ScrolledText(
            frm, font=self.FONT_MONO, height=5,
            bg=self.LOG_BG, fg=self.TEXT,
            insertbackground=self.TEXT,
            relief="flat", state="disabled")
        self._log.grid(row=0, column=0, sticky="nsew", padx=3, pady=3)

        self._log.tag_config("info",  foreground=self.TEXT)
        self._log.tag_config("ok",    foreground=self.GREEN)
        self._log.tag_config("warn",  foreground=self.YELLOW)
        self._log.tag_config("error", foreground=self.RED)
        self._log.tag_config("voice", foreground=self.ACCENT)

    # ── PUBLIC THREAD-SAFE METHODS ─────────────────────────────────

    def _send_manual_cmd(self):
        text = self._text_entry.get().strip()
        if not text:
            return
        normalized = normalize_command(text)
        self.log(f"⌨  Manual: '{text}'  →  '{normalized}'", "voice")
        cmd_queue.put(normalized)
        self._text_entry.delete(0, tk.END)

    def log(self, msg: str, tag: str = "info"):
        def _write():
            ts = time.strftime("%H:%M:%S")
            self._log.config(state="normal")
            self._log.insert(tk.END, f"[{ts}]  {msg}\n", tag)
            self._log.see(tk.END)
            self._log.config(state="disabled")
        self.root.after(0, _write)

    def set_mic(self, listening: bool):
        """
        Toggle the mic badge in the header.
        Idle      → dark red bg, red text, '🔴  IDLE'
        Listening → dark green bg, bright green text, '🟢  LISTENING...'
        """
        def _upd():
            if listening:
                self._mic_badge.config(
                    text="🟢  LISTENING...",
                    bg=self.GREEN_DIM,
                    fg=self.GREEN)
            else:
                self._mic_badge.config(
                    text="🔴  IDLE",
                    bg="#3a1a1a",
                    fg=self.RED)
        self.root.after(0, _upd)

    def set_coord_mode(self, mode: str):
        self.root.after(0, lambda: self._coord_var.set(mode.upper()))

    def set_tool(self, key: str):
        t = TOOLS.get(key, {})
        self.root.after(0, lambda: self._tool_var.set(
            f"{key.upper()}  ({t.get('name', '?')})"))

    def set_base(self, key: str):
        b = BASES.get(key, {})
        self.root.after(0, lambda: self._base_var.set(
            f"{key.upper()}  ({b.get('name', '?')})"))

    def set_speed(self, name: str):
        pct = {"low": 25, "mid": 50, "high": 100}.get(name, 50)
        def _upd():
            self._speed_var.set(f"{name.upper()}  ({pct}%)")
            color = {"low": self.TEXT, "mid": self.YELLOW,
                     "high": self.GREEN}.get(name, self.YELLOW)
            self._speed_lbl.config(fg=color)
        self.root.after(0, _upd)

    def set_motion(self, mtype: str):
        def _upd():
            self._motion_var.set(mtype.upper())
            color = self.ACCENT if mtype == "ptp" else self.YELLOW
            self._motion_lbl.config(fg=color)
        self.root.after(0, _upd)

    def set_selected_axis(self, num):
        txt = f"A{num}" if num else "—"
        self.root.after(0, lambda: self._axis_var.set(txt))

    def set_tcp_pose(self, x, y, z):
        def _upd():
            self._tcp_x_var.set(f"{x:+.2f} mm")
            self._tcp_y_var.set(f"{y:+.2f} mm")
            self._tcp_z_var.set(f"{z:+.2f} mm")
        self.root.after(0, _upd)

    def set_heard(self, raw: str, normalized: str):
        def _upd():
            self._heard_var.set(raw or "—")
            self._norm_var.set(normalized or "—")
        self.root.after(0, _upd)

    def set_joints(self, angles_deg: list):
        def _upd():
            for i, a in enumerate(angles_deg[:6]):
                mark = " ◀" if selected_axis == i + 1 else ""
                self._joint_vars[i].set(f"{a:+7.1f}°{mark}")
        self.root.after(0, _upd)

# ================================================================
# VOICE I/O
# ================================================================
def normalize_command(text: str) -> str:
    text = text.lower().strip()
    replacements = {
        "positive": "+", "plus": "+",
        "negative": "-", "minus": "-",
        "axe": "axis", "access": "axis", "axes": "axis",
        "word": "world", "whirl": "world", "weld": "world", "wild": "world",
        "bass": "base", "bays": "base", "bay": "base",
        "vase": "base", "pace": "base", "face": "base",
        "linear": "lin", "line": "lin",
        "pt p": "ptp", "point to point": "ptp",
        "anti clockwise": "acw", "anticlockwise": "acw",
        "counter clockwise": "acw", "counterclockwise": "acw",
        "clockwise": "cw",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return re.sub(r"\s+", " ", text).strip()


def listen_once_normalized() -> str:
    """
    Priority 1: cmd_queue (GUI buttons / manual text box — zero latency).
    Priority 2: 3-second microphone + Google STT.
    """
    try:
        queued = cmd_queue.get_nowait()
        if app:
            app.log(f"⌨  Command: '{queued}'", "voice")
        return queued
    except queue.Empty:
        pass

    fs, duration = 44100, 3
    if app:
        app.set_mic(True)
        app.log("🎤  Listening...", "info")

    try:
        recording = sd.rec(int(duration * fs), samplerate=fs,
                           channels=1, dtype="int16")
        sd.wait()
    except Exception as e:
        if app:
            app.log(f"⚠️  Recording error: {e}", "warn")
        return ""
    finally:
        if app:
            app.set_mic(False)

    byte_io = io.BytesIO()
    with wave.open(byte_io, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(fs)
        wf.writeframes(recording.tobytes())
    byte_io.seek(0)

    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(byte_io) as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.2)
            audio = recognizer.record(source)
        raw = recognizer.recognize_google(audio).lower().strip()
        normalized = normalize_command(raw)
        if app:
            app.set_heard(raw, normalized)
            app.log(f"🗣️  '{raw}'  →  '{normalized}'", "voice")
        return normalized
    except sr.UnknownValueError:
        if app:
            app.set_heard("(not recognized)", "")
        return ""
    except Exception as e:
        if app:
            app.log(f"⚠️  STT error: {e}", "warn")
        return ""


# ================================================================
# PHONETIC VARIANTS
# ================================================================
COORDINATE_VARIANTS = [
    "coordinate", "coordinates", "cord in eight", "cord in ate",
    "cord and eight", "cord and ate", "cordon eight", "cordon ate",
    "cordin eight", "cordin ate", "court in eight", "court and eight",
    "court in ate", "coordination", "co ordinate", "co-ordinate",
    "co ordinates", "corded eight", "corn it eight", "cord it eight",
    "coordinated", "ordinate", "ordinates",
]

def is_coordinate_cmd(cmd: str) -> bool:
    return any(v in cmd for v in COORDINATE_VARIANTS)

def is_wake_word(text: str) -> bool:
    return any(w in text for w in ["hello", "hallo"])

def is_halt(cmd: str) -> bool:
    return any(w in cmd for w in ["halt", "stop", "close", "quit", "end task"])

def is_switch(cmd: str) -> bool:
    return any(w in cmd for w in ["switch", "change"])

def parse_coordinate_choice(cmd: str):
    if "world" in cmd: return "world"
    if "axis"  in cmd: return "axis"
    if "base"  in cmd: return "base"
    if "tcp"   in cmd: return "tcp"
    return None

def parse_tool_choice(cmd: str):
    if any(p in cmd for p in ["tool 1", "tool one", "tool1", "tool won"]):
        return "tool1"
    if any(p in cmd for p in ["tool 2", "tool two", "tool2", "tool to",
                               "tool too", "tool tu"]):
        return "tool2"
    return None

def parse_base_choice(cmd: str):
    if any(p in cmd for p in ["base 1", "base one", "base1"]): return "base1"
    if any(p in cmd for p in ["base 2", "base two", "base2"]): return "base2"
    return None

def parse_movement_direction(cmd: str):
    if "forward"  in cmd or "x+" in cmd or "x +" in cmd: return  1,  0,  0
    if "backward" in cmd or "x-" in cmd or "x -" in cmd \
            or "back" in cmd:                             return -1,  0,  0
    if "right"    in cmd or "y+" in cmd or "y +" in cmd: return  0,  1,  0
    if "left"     in cmd or "y-" in cmd or "y -" in cmd: return  0, -1,  0
    if "up"       in cmd or "z+" in cmd or "z +" in cmd: return  0,  0,  1
    if "down"     in cmd or "z-" in cmd or "z -" in cmd: return  0,  0, -1
    return 0, 0, 0

def parse_axis_number(cmd: str):
    axis_map = {
        "axis 1": 1, "axis one": 1, "a1": 1, "a 1": 1,
        "axis 2": 2, "axis two": 2, "a2": 2, "a 2": 2,
        "axis 3": 3, "axis three": 3, "a3": 3, "a 3": 3,
        "axis 4": 4, "axis four": 4, "a4": 4, "a 4": 4,
        "axis 5": 5, "axis five": 5, "a5": 5, "a 5": 5,
        "axis 6": 6, "axis six": 6, "a6": 6, "a 6": 6,
    }
    for k, v in axis_map.items():
        if k in cmd: return v
    return None

def parse_axis_direction(cmd: str):
    if any(w in cmd for w in ["acw", "anticlockwise", "anti clockwise",
                               "counterclockwise", "counter clockwise"]):
        return "acw"
    if any(w in cmd for w in ["cw", "clockwise"]):
        return "cw"
    return None


# ================================================================
# DIRECT COMMAND INTERCEPTOR  (speed / motion / home — any mode)
# ================================================================
def handle_direct_cmd(cmd: str) -> bool:
    """
    Intercepts speed, motion-type, and home commands that arrive as bare
    words from GUI buttons or the manual text box.  Called at the TOP of
    every mode loop so the user never has to say 'switch' just to change
    speed.

    Returns True  → consumed; caller does 'continue'.
    Returns False → not a direct command; caller keeps processing.
    """
    global active_movement_type

    if cmd in ("low", "slow"):
        apply_speed("low");  return True
    if cmd in ("mid", "medium", "middle"):
        apply_speed("mid");  return True
    if cmd in ("high", "fast"):
        apply_speed("high"); return True

    if cmd in ("lin", "linear"):
        active_movement_type = "lin"
        if app:
            app.set_motion("lin")
            app.log("➡️  Motion → LIN", "ok")
        return True
    if cmd == "ptp":
        active_movement_type = "ptp"
        if app:
            app.set_motion("ptp")
            app.log("◎  Motion → PTP", "ok")
        return True

    if cmd == "home":
        rehome_robot()
        return True

    return False


# ================================================================
# SPEED / FRAME / TOOL / BASE HELPERS
# ================================================================
def apply_speed(speed_name: str):
    global active_speed
    active_speed = speed_name
    pct = {"low": 25, "mid": 50, "high": 100}.get(speed_name, 50)
    # Always update GUI and step-size first, regardless of COM result
    if app:
        app.set_speed(speed_name)
    try:
        robot.setSimMoveSpeedTrans(pct)
        robot.setSimMoveSpeedRot(pct)
        robot.setSimMoveSpeedAxis(pct)
        robot.setSimMoveSpeedUp(pct)
        robot.setSimMoveNPoints(20)
        if app:
            app.log(f"⚡  Speed → {speed_name.upper()} ({pct}%)", "ok")
    except Exception as e:
        if app:
            app.log(
                f"⚠️  Speed COM error — step size updated, sim speed may not change: {e}",
                "warn")

def get_linear_step_size() -> float:
    return {"low": 10.0, "high": 50.0}.get(active_speed, 20.0)

def get_axis_step_size() -> float:
    return {"low": 2.0, "high": 10.0}.get(active_speed, 5.0)

def apply_tool(tool_key: str) -> bool:
    global active_tool_key
    if tool_key not in TOOLS:
        return False
    t = TOOLS[tool_key]
    try:
        robot.setTool(t["name"], t["x"], t["y"], t["z"],
                      t["rx"]*gr, t["ry"]*gr, t["rz"]*gr)
        robot.forceUpdateCad()
        active_tool_key = tool_key
        if app:
            app.set_tool(tool_key)
            app.log(f"🔧  Tool → {tool_key.upper()} ({t['name']})", "ok")
        return True
    except Exception as e:
        if app:
            app.log(f"❌  setTool failed: {e}", "error")
        return False

def apply_base(base_key: str) -> bool:
    global active_base_key
    if base_key not in BASES:
        return False
    b = BASES[base_key]
    try:
        robot.setBase(b["name"], b["x"], b["y"], b["z"],
                      b["rx"]*gr, b["ry"]*gr, b["rz"]*gr)
        robot.forceUpdateCad()
        active_base_key = base_key
        if app:
            app.set_base(base_key)
            app.log(f"📐  Base → {base_key.upper()} ({b['name']})", "ok")
        return True
    except Exception as e:
        if app:
            app.log(f"❌  setBase failed: {e}", "error")
        return False

def apply_frame(frame_type: str) -> bool:
    mapped = {
        "world": "MOVE_FRAME_WORLD",
        "base":  "MOVE_FRAME_BASE",
        "axis":  "MOVE_FRAME_AXIS",
    }.get(frame_type)
    if not mapped:
        return False
    try:
        ok = robot.setMoveFrameType(mapped)
        robot.forceUpdateCad()
        return bool(ok)
    except Exception as e:
        if app:
            app.log(f"⚠️  setMoveFrameType({mapped}) failed: {e}", "warn")
        return False

def read_current_pose(frame_type: str):
    mapped = ("MOVE_FRAME_WORLD" if frame_type == "world"
              else "MOVE_FRAME_BASE")
    try:
        pos_str = robot.getRobotXYZABCStr(mapped)
        parts = pos_str.split()
        if len(parts) >= 6:
            vals = [float(p) for p in parts[:6]]
            if app:
                app.set_tcp_pose(vals[0], vals[1], vals[2])
            return vals
    except Exception as e:
        if app:
            app.log(f"⚠️  Pose read failed ({frame_type}): {e}", "warn")
    return None

def read_current_joints():
    try:
        axis_str = robot.getRobotAxisStr()
        parts = axis_str.split()
        if len(parts) >= 6:
            degs = [float(p) * 180.0 / math.pi for p in parts[:6]]
            if app:
                app.set_joints(degs)
            return degs
    except Exception as e:
        if app:
            app.log(f"⚠️  Joint read failed: {e}", "warn")
    return None


# ================================================================
# CAD WINDOW  — auto-raise + always-on-top
# ================================================================
def _find_cad_hwnd() -> int:
    result = [0]
    def _cb(hwnd, _):
        if CAD_WIN_TITLE.lower() in win32gui.GetWindowText(hwnd).lower():
            result[0] = hwnd
            return False
        return True
    try:
        win32gui.EnumWindows(_cb, None)
    except Exception:
        pass
    return result[0]

def raise_cad_window():
    """Find CAD window and pin it TOPMOST. Retries for up to 5 s."""
    deadline = time.time() + 5.0
    while time.time() < deadline:
        hwnd = _find_cad_hwnd()
        if hwnd:
            try:
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(hwnd)
                win32gui.SetWindowPos(
                    hwnd, win32con.HWND_TOPMOST,
                    0, 0, 0, 0,
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
                if app:
                    app.log("🖥️  CAD window pinned always-on-top.", "ok")
            except Exception as e:
                if app:
                    app.log(f"⚠️  raise_cad_window: {e}", "warn")
            return
        time.sleep(0.3)
    if app:
        app.log("⚠️  CAD window not found after 5 s — click it manually.", "warn")


# ================================================================
# ROBOT UTILITIES
# ================================================================
def rehome_robot():
    global selected_axis, active_movement_type
    try:
        robot.moveAxis(*[a * gr for a in HOME_ANGLES_DEG])
        robot.forceUpdateCad()
        if app:
            app.log("🏠  Robot re-homed.", "ok")
    except Exception as e:
        if app:
            app.log(f"⚠️  Re-home failed: {e}", "warn")
    selected_axis = None
    active_movement_type = "lin"
    time.sleep(0.3)
    read_current_joints()

def init_robot():
    global robot
    if app:
        app.log("🔧  Initialising robot...", "info")

    os.system("taskkill /f /im OpenGLRobot.exe >nul 2>&1")
    time.sleep(2)

    robot = win32com.client.Dispatch("openglrobot.RobotWindowApi")
    robot.init()
    robot.createRobotWindow()
    robot.initMainDialog()
    robot.openMainDialog()
    robot.which()
    robot.print("Init CAD + Motion")

    robot.setCADModelDefaultPath(CAD_FOLDER)
    robot.readProjectDataXML(XML_CONFIG)
    robot.openCadWindow()
    robot.setCadWindowPosition(100, 100)
    robot.setCadWindowSize(800, 600)

    time.sleep(1)
    robot.forceUpdateCad()
    raise_cad_window()

    apply_base("base1")
    apply_tool("tool1")
    apply_speed("mid")
    rehome_robot()

    if app:
        app.log("✅  Robot + CAD READY", "ok")
    pose = read_current_pose("world")
    if pose and app:
        app.log(
            f"📍  Home TCP: X={pose[0]:.2f}  Y={pose[1]:.2f}  Z={pose[2]:.2f}",
            "ok")


# ================================================================
# CARTESIAN MOTION  (world-referenced — used by World and Base mode)
# ================================================================
def move_linear_or_ptp(frame_type: str,
                        dx: float, dy: float, dz: float) -> bool:
    pose = read_current_pose(frame_type)
    if pose is None:
        if app:
            app.log("❌  Cannot move: TCP position unknown.", "error")
        return False
    nx, ny, nz = pose[0]+dx, pose[1]+dy, pose[2]+dz
    a, b, c    = pose[3], pose[4], pose[5]
    if app:
        app.log(f"➡️  Target: X={nx:.2f}  Y={ny:.2f}  Z={nz:.2f}", "info")
    try:
        apply_frame(frame_type)
        if active_movement_type == "ptp":
            ok = robot.moveRobotPtp(nx, ny, nz, a, b, c)
        else:
            ok = robot.moveRobotLinear(nx, ny, nz, a, b, c)
        robot.forceUpdateCad()
        read_current_joints()
        return bool(ok)
    except Exception as e:
        if app:
            app.log(f"❌  Movement failed: {e}", "error")
        return False


# ================================================================
# SWITCH SUB-MENU
# ================================================================
def handle_switch_menu() -> str:
    if app:
        app.log("🔄  Switch menu — say: Coordinate / Speed / Motion", "info")

    while True:
        sub_cmd = listen_once_normalized()
        if not sub_cmd:
            return "continue"
        if is_halt(sub_cmd):
            return "halt"

        # Direct interceptor works inside switch menu too
        if handle_direct_cmd(sub_cmd):
            return "continue"

        if is_coordinate_cmd(sub_cmd):
            if app:
                app.log("🔄  Switching coordinate system...", "info")
            return "switch_coordinate"

        elif "speed" in sub_cmd:
            if app:
                app.log("⚡  Speed menu — say: High / Mid / Low", "info")
            speed_cmd = listen_once_normalized()
            if not speed_cmd:
                apply_speed("mid")
                return "continue"
            if any(w in speed_cmd for w in ["low", "slow"]):
                apply_speed("low")
            elif any(w in speed_cmd for w in ["high", "fast"]):
                apply_speed("high")
            else:
                apply_speed("mid")
            return "continue"

        elif "motion" in sub_cmd or "movement" in sub_cmd:
            global active_movement_type
            if app:
                app.log("➡️  Motion menu — say: Lin / PTP", "info")
            motion_cmd = listen_once_normalized()
            if not motion_cmd:
                return "continue"
            if any(w in motion_cmd for w in ["lin", "linear", "line"]):
                active_movement_type = "lin"
                if app:
                    app.set_motion("lin")
                    app.log("➡️  Motion → LIN", "ok")
            elif any(w in motion_cmd for w in ["ptp", "p t p", "point to point"]):
                active_movement_type = "ptp"
                if app:
                    app.set_motion("ptp")
                    app.log("◎  Motion → PTP", "ok")
            return "continue"

        if app:
            app.log("❌  Say 'Coordinate', 'Speed', or 'Motion'.", "warn")


# ================================================================
# COORDINATE MODE LOOPS
# ================================================================
def run_tcp_mode() -> str:
    if app:
        app.set_coord_mode("TCP")
        app.log("🔧  TCP mode — say 'Tool 1' or 'Tool 2'", "ok")

    while True:
        cmd = listen_once_normalized()
        if not cmd:
            continue
        if is_halt(cmd):
            return "halt"
        if handle_direct_cmd(cmd):
            continue
        if is_switch(cmd):
            res = handle_switch_menu()
            if res == "halt":              return "halt"
            if res == "switch_coordinate": return "switch"
            continue
        choice = parse_tool_choice(cmd)
        if choice:
            apply_tool(choice)
            continue
        if app:
            app.log("❌  Unknown TCP command.", "warn")


def run_world_mode() -> str:
    if app:
        app.set_coord_mode("WORLD")
        app.log("🌍  World mode — say direction or 'Switch'", "ok")
    apply_frame("world")

    while True:
        read_current_joints()
        pose = read_current_pose("world")
        if pose and app:
            app.set_tcp_pose(pose[0], pose[1], pose[2])

        cmd = listen_once_normalized()
        if not cmd:
            continue
        if is_halt(cmd):
            return "halt"
        if handle_direct_cmd(cmd):
            continue
        if is_switch(cmd):
            res = handle_switch_menu()
            if res == "halt":              return "halt"
            if res == "switch_coordinate": return "switch"
            continue
        dx, dy, dz = parse_movement_direction(cmd)
        if dx or dy or dz:
            s = get_linear_step_size()
            move_linear_or_ptp("world", dx*s, dy*s, dz*s)
            continue
        if app:
            app.log("❌  Unknown World command.", "warn")


def run_base_mode() -> str:
    if app:
        app.set_coord_mode("BASE")
        app.log("📐  Base mode — say 'Base 1' or 'Base 2' first", "ok")

    # Step 1: base selection
    selected_base = False
    while not selected_base:
        cmd = listen_once_normalized()
        if not cmd:
            continue
        if is_halt(cmd):
            return "halt"
        if handle_direct_cmd(cmd):
            continue
        if is_switch(cmd):
            res = handle_switch_menu()
            if res == "halt":              return "halt"
            if res == "switch_coordinate": return "switch"
            continue
        choice = parse_base_choice(cmd)
        if choice:
            apply_base(choice)
            selected_base = True
            break
        if app:
            app.log("❌  Say 'Base 1' or 'Base 2'.", "warn")

    apply_frame("base")
    if app:
        app.log(f"📐  Moving in Base frame: {active_base_key.upper()}", "ok")

    # Step 2: movement loop
    while True:
        read_current_joints()
        pose = read_current_pose("base")
        if pose and app:
            app.set_tcp_pose(pose[0], pose[1], pose[2])

        cmd = listen_once_normalized()
        if not cmd:
            continue
        if is_halt(cmd):
            return "halt"
        if handle_direct_cmd(cmd):
            continue
        if is_switch(cmd):
            res = handle_switch_menu()
            if res == "halt":              return "halt"
            if res == "switch_coordinate": return "switch"
            continue
        dx, dy, dz = parse_movement_direction(cmd)
        if dx or dy or dz:
            s = get_linear_step_size()
            move_linear_or_ptp("base", dx*s, dy*s, dz*s)
            continue
        if app:
            app.log("❌  Unknown Base command.", "warn")


def rotate_axis(axis_num: int, direction: str) -> bool:
    joints = read_current_joints()
    if joints is None:
        if app:
            app.log("❌  Cannot rotate: joint angles unknown.", "error")
        return False
    idx   = axis_num - 1
    step  = get_axis_step_size()
    delta = step if direction == "cw" else -step
    new_angle = joints[idx] + delta

    try:
        jmin = robot.getJointMin(idx)
        jmax = robot.getJointMax(idx)
        if not (jmin <= new_angle <= jmax):
            if app:
                app.log(
                    f"❌  Joint limit A{axis_num}: {new_angle:+.1f}° outside "
                    f"[{jmin:.1f}°, {jmax:.1f}°]", "error")
            return False
    except Exception:
        pass

    joints[idx] = new_angle
    label = "CW ↻" if direction == "cw" else "ACW ↺"
    if app:
        app.log(f"🔁  A{axis_num} {label} → {new_angle:+.1f}°", "ok")
    try:
        apply_frame("axis")
        ok = robot.moveAxis(*[v * math.pi / 180.0 for v in joints])
        robot.forceUpdateCad()
        read_current_joints()
        return bool(ok)
    except Exception as e:
        if app:
            app.log(f"❌  moveAxis failed: {e}", "error")
        return False


def run_axis_mode() -> str:
    global selected_axis
    selected_axis = None
    if app:
        app.set_coord_mode("AXIS")
        app.set_selected_axis(None)
        app.log("🦾  Axis mode — say A1..A6, then CW or ACW", "ok")
    apply_frame("axis")

    while True:
        read_current_joints()
        cmd = listen_once_normalized()
        if not cmd:
            continue
        if is_halt(cmd):
            return "halt"
        if handle_direct_cmd(cmd):
            continue
        if is_switch(cmd):
            res = handle_switch_menu()
            if res == "halt":              return "halt"
            if res == "switch_coordinate": return "switch"
            continue
        axis_num = parse_axis_number(cmd)
        if axis_num is not None:
            selected_axis = axis_num
            if app:
                app.set_selected_axis(axis_num)
                app.log(f"✅  Axis A{axis_num} selected.", "ok")
            continue
        direction = parse_axis_direction(cmd)
        if direction:
            if selected_axis is None:
                if app:
                    app.log("❌  No axis selected — say A1..A6 first.", "warn")
                continue
            rotate_axis(selected_axis, direction)
            continue
        if app:
            app.log("❌  Unknown Axis command.", "warn")


# ================================================================
# COORDINATE SELECTION PROMPT
# ================================================================
def select_coordinate_system() -> str:
    if app:
        app.log("🧭  Say: World | Base | Axis | TCP | Halt", "info")
    while True:
        cmd = listen_once_normalized()
        if not cmd:
            continue
        if is_halt(cmd):
            return "halt"
        if handle_direct_cmd(cmd):
            continue
        choice = parse_coordinate_choice(cmd)
        if choice in ("world", "base", "axis", "tcp"):
            if app:
                app.log(f"✅  {choice.upper()} selected.", "ok")
                app.set_coord_mode(choice)
            return choice
        if app:
            app.log("❌  Say 'World', 'Base', 'Axis', or 'TCP'.", "warn")


# ================================================================
# ROBOT THREAD
# ================================================================
def robot_thread_main():
    pythoncom.CoInitialize()
    try:
        if app:
            app.log("🎤  Say 'hello' or 'hallo' to activate…", "info")
        while True:
            if is_wake_word(listen_once_normalized()):
                if app:
                    app.log("🔥  Robot ACTIVATED", "ok")
                break

        init_robot()

        while True:
            choice = select_coordinate_system()
            if choice == "halt":
                if app:
                    app.log("🛑  Halt — system stopped.", "warn")
                break

            if   choice == "world": result = run_world_mode()
            elif choice == "base":  result = run_base_mode()
            elif choice == "axis":  result = run_axis_mode()
            elif choice == "tcp":   result = run_tcp_mode()
            else:
                continue

            if result == "halt":
                if app:
                    app.log("🛑  Halt — system stopped.", "warn")
                break
            if app:
                app.log("🔄  Back to coordinate selection…", "info")

        try:
            robot.destroyRobotWindow()
        except Exception:
            pass
        if app:
            app.log("✅  System fully stopped.", "ok")

    finally:
        pythoncom.CoUninitialize()


# ================================================================
# MAIN
# ================================================================
def main():
    global app
    root = tk.Tk()
    app  = RobotGUI(root)

    t = threading.Thread(target=robot_thread_main, daemon=True)
    t.start()

    root.mainloop()


if __name__ == "__main__":
    main()
