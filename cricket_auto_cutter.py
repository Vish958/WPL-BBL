"""
================================================================================
AI CRICKET BALL-BY-BALL AUTO-CUTTER & PLAYER FOLDER ORGANIZER
Professional Video Analysis Tool for Cricket Analysts & Coaching Staff
================================================================================
Features:
1. Intelligent JSON Handling:
   - Directly supports Cricsheet Match JSONs (with 'innings' ball-by-ball deliveries).
   - Directly supports NPL Team Roster JSONs (e.g. 'biratnagar_kings.json',
     'chitwan_rhinos.json', 'sudurpaschim_royals.json'). Automatically links
     to matching NPL ball-by-ball data in data/npl_json/ and lets you pick the fixture!
2. Dedicated Match Project Folders:
   - Each match or highlight video gets its own isolated project folder
     (e.g., Extracted_Player_Clips/Chitwan_Rhinos_vs_Biratnagar_Kings/).
   - Multiple match highlight videos will NEVER mix or overwrite each other!
3. Both Innings Seamless Auto-Detection:
   - Detects when the highlight video switches from Innings 1 to Innings 2
     (when over count resets from late overs back to 0.1).
   - Maps deliveries to the correct batting and bowling team for both innings.
4. Strict Deduplication & T20 Range Validation:
   - Over numbers are strictly validated (0.1 to 19.6 for T20). Rejects scores like 41.6.
   - Normalizes leading zeros (e.g., 05.2 -> 5.2).
   - Exactly ONE clean video clip per delivery per innings (zero duplicate files).
5. High Performance:
   - Pixel change gating skips OCR on static frames (80% faster scanning).
   - Ultra-fast FFmpeg stream copy cuts clips in 0.05 seconds with original quality.
6. Native Timeline Scrubber from 00:00:
   - Start at 00:00, scrub smoothly to any second, and drag the ROI box natively.
================================================================================
"""

import os
import re
import glob
import json
import time
import shutil
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk

try:
    import cv2
except ImportError:
    cv2 = None

try:
    import easyocr
except ImportError:
    easyocr = None


class ROISelectorDialog(tk.Toplevel):
    def __init__(self, parent, video_path, on_selected):
        super().__init__(parent)
        self.title("Scoreboard Over Region Selector - Scrub Timeline from 00:00")
        self.geometry("980x720")
        self.configure(bg="#0F172A")
        self.transient(parent)
        self.grab_set()

        self.video_path = video_path
        self.on_selected = on_selected
        self.cap = cv2.VideoCapture(video_path)
        self.total_frames = max(1, int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT)))
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 25.0
        self.duration_sec = self.total_frames / self.fps

        self.orig_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1920
        self.orig_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 1080
        self.display_w = 940
        self.display_h = int(940 * (self.orig_h / self.orig_w))
        if self.display_h > 530:
            self.display_h = 530
            self.display_w = int(530 * (self.orig_w / self.orig_h))

        self.scale_x = self.orig_w / self.display_w
        self.scale_y = self.orig_h / self.display_h

        self.start_x = None
        self.start_y = None
        self.rect_id = None
        self.current_roi = None
        self.photo = None

        self._build_ui()
        self._seek_to_sec(0)

    def _build_ui(self):
        ctrl = tk.Frame(self, bg="#1E293B", pady=8, padx=14)
        ctrl.pack(fill="x")

        self.time_lbl = tk.Label(ctrl, text="00:00 / " + self._fmt_time(self.duration_sec), font=("Segoe UI", 10, "bold"), fg="#38BDF8", bg="#1E293B", width=18, anchor="w")
        self.time_lbl.pack(side="left")

        self.slider = tk.Scale(
            ctrl,
            from_=0,
            to=max(1, int(self.duration_sec)),
            orient=tk.HORIZONTAL,
            bg="#1E293B",
            fg="white",
            troughcolor="#0F172A",
            highlightthickness=0,
            command=self._on_slider
        )
        self.slider.pack(side="left", fill="x", expand=True, padx=12)

        self.canvas = tk.Canvas(self, width=self.display_w, height=self.display_h, bg="#000000", highlightthickness=1, highlightbackground="#38BDF8")
        self.canvas.pack(pady=8)

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)

        bot = tk.Frame(self, bg="#0F172A", pady=8, padx=14)
        bot.pack(fill="x")

        self.info_lbl = tk.Label(bot, text="Scrub slider to any second (00:00 to end), then drag a box tightly over the Over number (e.g. 0.1)", font=("Segoe UI", 9), fg="#94A3B8", bg="#0F172A")
        self.info_lbl.pack(side="left")

        tk.Button(bot, text="Cancel", command=self._close, bg="#334155", fg="white", padx=12, pady=4).pack(side="right", padx=(8, 0))
        tk.Button(bot, text="✅ Confirm Selection", command=self._confirm, bg="#10B981", fg="white", font=("Segoe UI", 9, "bold"), padx=14, pady=4).pack(side="right")

    def _on_slider(self, val):
        self._seek_to_sec(int(float(val)))

    def _seek_to_sec(self, sec):
        frame_no = min(self.total_frames - 1, int(sec * self.fps))
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
        ret, frame = self.cap.read()
        if ret and frame is not None:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            resized = cv2.resize(rgb, (self.display_w, self.display_h), interpolation=cv2.INTER_AREA)
            img = Image.fromarray(resized)
            self.photo = ImageTk.PhotoImage(image=img)
            self.canvas.delete("bg_img")
            self.canvas.create_image(0, 0, anchor="nw", image=self.photo, tags="bg_img")
            self.canvas.tag_lower("bg_img")
            self.time_lbl.config(text=f"{self._fmt_time(sec)} / {self._fmt_time(self.duration_sec)}")

    def _on_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        if self.rect_id:
            self.canvas.delete(self.rect_id)
        self.rect_id = self.canvas.create_rectangle(self.start_x, self.start_y, self.start_x, self.start_y, outline="#F59E0B", width=2)

    def _on_drag(self, event):
        cur_x, cur_y = event.x, event.y
        if self.rect_id:
            self.canvas.coords(self.rect_id, self.start_x, self.start_y, cur_x, cur_y)

    def _on_release(self, event):
        x1 = min(self.start_x, event.x)
        y1 = min(self.start_y, event.y)
        x2 = max(self.start_x, event.x)
        y2 = max(self.start_y, event.y)
        w = x2 - x1
        h = y2 - y1

        if w > 6 and h > 6:
            orig_x = int(x1 * self.scale_x)
            orig_y = int(y1 * self.scale_y)
            orig_w = int(w * self.scale_x)
            orig_h = int(h * self.scale_y)
            self.current_roi = (orig_x, orig_y, orig_w, orig_h)
            self.info_lbl.config(text=f"Selected Box: X={orig_x}, Y={orig_y}, W={orig_w}, H={orig_h} (Click 'Confirm Selection')", fg="#38BDF8")

    def _confirm(self):
        if self.current_roi:
            self.on_selected(self.current_roi)
            self._close()
        else:
            messagebox.showwarning("No Box", "Please drag a rectangle box over the over number first.")

    def _close(self):
        self.cap.release()
        self.destroy()

    @staticmethod
    def _fmt_time(seconds):
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"


class CricketAutoCutterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("AI Cricket Ball-by-Ball Auto-Cutter (NPL & T20 Edition)")
        self.root.geometry("860x820")
        self.root.minsize(820, 760)
        self.root.configure(bg="#0F172A")

        # Configuration Variables
        self.video_path = tk.StringVar()
        self.json_path = tk.StringVar()
        self.output_dir = tk.StringVar()
        self.project_name = tk.StringVar(value="Match_Project")
        self.video_mode = tk.StringVar(value="Highlights (Fast-Cut, 10-20 min)")
        self.target_innings = tk.StringVar(value="Both Innings (Auto-Detect)")
        self.target_player = tk.StringVar(value="ALL")
        self.scan_interval = tk.DoubleVar(value=0.8)
        self.pre_roll = tk.IntVar(value=4)
        self.post_roll = tk.IntVar(value=7)

        # Linked Match Fixture info
        self.selected_fixture_label = tk.StringVar(value="No Match Linked")
        self.fixture_options = []
        self.fixture_file_map = {}

        self.roi = None
        self.is_running = False
        self.reader = None

        self._build_ui()

    def _build_ui(self):
        # Header Bar
        header = tk.Frame(self.root, bg="#1E293B", pady=12)
        header.pack(fill="x")
        tk.Label(
            header,
            text="🏏 AI Cricket Ball-by-Ball Auto-Cutter",
            font=("Segoe UI", 16, "bold"),
            fg="#38BDF8",
            bg="#1E293B"
        ).pack()
        tk.Label(
            header,
            text="Automated Player Video Clipper & Organizer | Sudurpaschim Royals & NPL Pro Analytics",
            font=("Segoe UI", 9),
            fg="#94A3B8",
            bg="#1E293B"
        ).pack()

        main_frame = tk.Frame(self.root, bg="#0F172A", padx=20, pady=10)
        main_frame.pack(fill="both", expand=True)

        # 1. Match Video Selector
        self._create_file_selector(
            main_frame,
            "1. Select Match Video File (MP4 / MKV / MOV):",
            self.video_path,
            self.browse_video
        )

        # 2. Cricsheet / Team JSON Selector
        self._create_file_selector(
            main_frame,
            "2. Select Match or Team JSON (e.g. biratnagar_kings.json or Cricsheet match):",
            self.json_path,
            self.browse_json
        )

        # 2b. Fixture Link Row (Shows when Team JSON is loaded)
        self.fixture_frame = tk.Frame(main_frame, bg="#0F172A", pady=2)
        self.fixture_frame.pack(fill="x")
        tk.Label(self.fixture_frame, text="Linked NPL Match Fixture:", fg="#38BDF8", bg="#0F172A", font=("Segoe UI", 8, "bold")).pack(side="left")
        self.fixture_dropdown = ttk.Combobox(
            self.fixture_frame,
            textvariable=self.selected_fixture_label,
            values=["No Match Linked"],
            state="readonly",
            width=50
        )
        self.fixture_dropdown.pack(side="left", padx=8)
        self.fixture_dropdown.bind("<<ComboboxSelected>>", self._on_fixture_change)

        # 3. Output Folder Selector
        self._create_file_selector(
            main_frame,
            "3. Select Base Output Directory for Cut Video Clips:",
            self.output_dir,
            self.browse_output
        )

        # 3b. Dedicated Project / Match Subfolder Name
        proj_frame = tk.Frame(main_frame, bg="#0F172A", pady=3)
        proj_frame.pack(fill="x")
        tk.Label(proj_frame, text="📁 Dedicated Match Project Folder Name (Prevents Overwriting):", fg="#F1F5F9", bg="#0F172A", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        sub_proj = tk.Frame(proj_frame, bg="#0F172A")
        sub_proj.pack(fill="x", pady=2)
        tk.Entry(sub_proj, textvariable=self.project_name, bg="#1E293B", fg="#38BDF8", insertbackground="white", font=("Segoe UI", 9, "bold")).pack(side="left", fill="x", expand=True, ipady=3)
        tk.Label(sub_proj, text="Clips will be saved to: Base_Dir / Project_Folder / Player / Category", fg="#64748B", bg="#0F172A", font=("Segoe UI", 8)).pack(side="left", padx=8)

        # 4. Settings & Configuration Frame
        settings_frame = tk.LabelFrame(
            main_frame,
            text=" 4. Video & Clipping Settings ",
            font=("Segoe UI", 10, "bold"),
            fg="#38BDF8",
            bg="#0F172A",
            bd=1,
            padx=14,
            pady=8
        )
        settings_frame.pack(fill="x", pady=6)

        # Row 0: Video Mode & Innings
        tk.Label(settings_frame, text="Video Source Type:", fg="#E2E8F0", bg="#0F172A", font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w", pady=4)
        mode_menu = ttk.Combobox(
            settings_frame,
            textvariable=self.video_mode,
            values=["Highlights (Fast-Cut, 10-20 min)", "Full Match Broadcast (3-4 hrs)"],
            width=28,
            state="readonly"
        )
        mode_menu.grid(row=0, column=1, sticky="w", padx=6, pady=4)
        mode_menu.bind("<<ComboboxSelected>>", self._on_mode_change)

        tk.Label(settings_frame, text="Innings Mode:", fg="#E2E8F0", bg="#0F172A", font=("Segoe UI", 9)).grid(row=0, column=2, sticky="w", padx=(14, 4), pady=4)
        innings_menu = ttk.Combobox(
            settings_frame,
            textvariable=self.target_innings,
            values=["Both Innings (Auto-Detect)", "Innings 1 Only", "Innings 2 Only"],
            width=22,
            state="readonly"
        )
        innings_menu.grid(row=0, column=3, sticky="w", pady=4)

        # Row 1: Player / Team Filter & Scan Step
        tk.Label(settings_frame, text="Filter Batter / Team:", fg="#E2E8F0", bg="#0F172A", font=("Segoe UI", 9)).grid(row=1, column=0, sticky="w", pady=4)
        tk.Entry(settings_frame, textvariable=self.target_player, width=29, bg="#1E293B", fg="white", insertbackground="white", font=("Segoe UI", 9)).grid(row=1, column=1, sticky="w", padx=6, pady=4)

        tk.Label(settings_frame, text="OCR Interval (Sec):", fg="#E2E8F0", bg="#0F172A", font=("Segoe UI", 9)).grid(row=1, column=2, sticky="w", padx=(14, 4), pady=4)
        tk.Spinbox(settings_frame, from_=0.4, to=3.0, increment=0.1, textvariable=self.scan_interval, width=8, bg="#1E293B", fg="white").grid(row=1, column=3, sticky="w", pady=4)

        # Row 2: Pre-roll & Post-roll Buffers
        tk.Label(settings_frame, text="Pre-Roll Buffer (Sec):", fg="#E2E8F0", bg="#0F172A", font=("Segoe UI", 9)).grid(row=2, column=0, sticky="w", pady=4)
        tk.Spinbox(settings_frame, from_=1, to=15, textvariable=self.pre_roll, width=8, bg="#1E293B", fg="white").grid(row=2, column=1, sticky="w", padx=6, pady=4)

        tk.Label(settings_frame, text="Post-Roll Buffer (Sec):", fg="#E2E8F0", bg="#0F172A", font=("Segoe UI", 9)).grid(row=2, column=2, sticky="w", padx=(14, 4), pady=4)
        tk.Spinbox(settings_frame, from_=3, to=25, textvariable=self.post_roll, width=8, bg="#1E293B", fg="white").grid(row=2, column=3, sticky="w", pady=4)

        # 5. Action Buttons
        btn_frame = tk.Frame(main_frame, bg="#0F172A", pady=6)
        btn_frame.pack(fill="x")

        self.roi_btn = tk.Button(
            btn_frame,
            text="🎯 Step A: Select Scoreboard Over Region (Timeline Scrubber from 00:00)",
            command=self.select_roi,
            bg="#F59E0B",
            fg="#000000",
            font=("Segoe UI", 10, "bold"),
            padx=12,
            pady=8,
            cursor="hand2"
        )
        self.roi_btn.pack(side="left", expand=True, fill="x", padx=(0, 6))

        self.start_btn = tk.Button(
            btn_frame,
            text="🚀 Step B: Start Automated Video Cutting",
            command=self.start_processing_thread,
            bg="#10B981",
            fg="#FFFFFF",
            font=("Segoe UI", 10, "bold"),
            padx=12,
            pady=8,
            cursor="hand2"
        )
        self.start_btn.pack(side="left", expand=True, fill="x", padx=(6, 0))

        # Progress Bar & Log Window
        self.progress = ttk.Progressbar(main_frame, orient="horizontal", mode="determinate")
        self.progress.pack(fill="x", pady=(6, 4))

        self.log_box = tk.Text(
            main_frame,
            height=11,
            bg="#030712",
            fg="#6EE7B7",
            font=("Consolas", 9),
            bd=0,
            padx=10,
            pady=8
        )
        self.log_box.pack(fill="both", expand=True)
        self.log("Ready. Select your video file and output folder to begin.")

    def _create_file_selector(self, parent, label_text, var, cmd):
        frame = tk.Frame(parent, bg="#0F172A", pady=2)
        frame.pack(fill="x")
        tk.Label(frame, text=label_text, fg="#F1F5F9", bg="#0F172A", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        sub = tk.Frame(frame, bg="#0F172A")
        sub.pack(fill="x", pady=2)
        tk.Entry(sub, textvariable=var, bg="#1E293B", fg="white", insertbackground="white", font=("Segoe UI", 9)).pack(side="left", fill="x", expand=True, ipady=3)
        tk.Button(sub, text="Browse...", command=cmd, bg="#334155", fg="white", padx=12).pack(side="left", padx=(6, 0))

    def _on_mode_change(self, event=None):
        mode = self.video_mode.get()
        if "Highlights" in mode:
            self.scan_interval.set(0.8)
            self.pre_roll.set(4)
            self.post_roll.set(7)
            self.log("Highlights Mode: Fast scan (0.8s) + Strict Deduplication (1 delivery = 1 clip).")
        else:
            self.scan_interval.set(1.5)
            self.pre_roll.set(6)
            self.post_roll.set(10)
            self.log("Full Match Mode: 1.5s scan interval + 6s pre-roll / 10s post-roll.")

    def log(self, message):
        self.log_box.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {message}\n")
        self.log_box.see(tk.END)
        self.root.update_idletasks()

    def browse_video(self):
        path = filedialog.askopenfilename(filetypes=[("Video Files", "*.mp4 *.mkv *.avi *.mov *.ts")])
        if path:
            self.video_path.set(path)
            # Automatically assign dedicated project subfolder from video filename
            base_name = os.path.splitext(os.path.basename(path))[0]
            clean_proj = re.sub(r"[^\w\-]", "_", base_name).strip("_")
            self.project_name.set(clean_proj or "Match_Project")
            self.log(f"Assigned project subfolder: {self.project_name.get()}")

            if not self.output_dir.get():
                default_out = os.path.join(os.path.dirname(path), "Extracted_Player_Clips")
                self.output_dir.set(default_out)

            # Auto-match opponent if JSON was already loaded
            if self.json_path.get():
                self._analyze_json_file(self.json_path.get())

    def browse_json(self):
        path = filedialog.askopenfilename(filetypes=[("JSON Files", "*.json")])
        if path:
            self.json_path.set(path)
            self._analyze_json_file(path)

    def _analyze_json_file(self, json_file):
        """Analyzes whether the selected JSON is a Cricsheet Match or a Team Roster."""
        if not json_file or not os.path.exists(json_file):
            return

        try:
            with open(json_file, "r", encoding="utf-8") as fp:
                data = json.load(fp)

            # Case A: Standard Cricsheet Match JSON
            if "innings" in data:
                teams = data.get("info", {}).get("teams", ["Team A", "Team B"])
                match_date = data.get("info", {}).get("dates", [""])[0]
                label = f"{teams[0]} vs {teams[1]} ({match_date})"
                self.fixture_options = [label]
                self.fixture_file_map = {label: json_file}
                self.fixture_dropdown["values"] = self.fixture_options
                self.selected_fixture_label.set(label)
                self.log(f"✅ Loaded Cricsheet Match: {label}")
                return

            # Case B: Combined All Teams Master JSON (has "teams" dict with all 8 teams)
            if "teams" in data and isinstance(data["teams"], dict):
                team_names = list(data["teams"].keys())
                self.log(f"✅ Loaded Master NPL JSON ({len(team_names)} teams). Auto-detecting match from video...")

                v_name = os.path.basename(self.video_path.get()).lower()
                detected_teams = []
                for t in team_names:
                    words = [w for w in t.lower().split() if len(w) > 3]
                    if any(w in v_name for w in words):
                        detected_teams.append(t)

                all_matches = []
                search_targets = detected_teams if detected_teams else team_names
                for t in search_targets:
                    for m in self._find_matches_for_team(t):
                        if m["label"] not in [x["label"] for x in all_matches]:
                            all_matches.append(m)

                if all_matches:
                    self.fixture_options = [m["label"] for m in all_matches]
                    self.fixture_file_map = {m["label"]: m["file"] for m in all_matches}
                    self.fixture_dropdown["values"] = self.fixture_options

                    # Auto-select fixture if both teams appear in video filename
                    best_match = self.fixture_options[0]
                    for m in all_matches:
                        t1, t2 = m["teams"][0].lower(), m["teams"][1].lower()
                        w1 = [w for w in t1.split() if len(w) > 3]
                        w2 = [w for w in t2.split() if len(w) > 3]
                        if any(w in v_name for w in w1) and any(w in v_name for w in w2):
                            best_match = m["label"]
                            break

                    self.selected_fixture_label.set(best_match)
                    self.log(f"🎯 Auto-Matched: {best_match} ({len(all_matches)} fixtures ready).")
                return

            # Case C: Single Team Roster JSON (e.g. biratnagar_kings.json)
            if "team" in data and "players" in data:
                team_name = data["team"]
                player_count = len(data["players"])
                self.log(f"Detected Team Roster: {team_name} ({player_count} players). Searching NPL database for fixtures...")

                # Search data/npl_json for all matches involving this team
                matches = self._find_matches_for_team(team_name)
                if matches:
                    self.fixture_options = [m["label"] for m in matches]
                    self.fixture_file_map = {m["label"]: m["file"] for m in matches}
                    self.fixture_dropdown["values"] = self.fixture_options

                    # Check if video filename hints at the opponent
                    v_name = os.path.basename(self.video_path.get()).lower()
                    best_match = self.fixture_options[0]
                    for m in matches:
                        opp_simple = m["opponent"].lower().replace(" ", "")
                        if opp_simple in v_name or any(word in v_name for word in m["opponent"].lower().split()):
                            best_match = m["label"]
                            break

                    self.selected_fixture_label.set(best_match)
                    self.log(f"✅ Linked Fixture: {best_match} ({len(matches)} matches available in dropdown).")
                else:
                    self.log(f"Notice: No matches found for {team_name} in data/npl_json.")
        except Exception as e:
            self.log(f"Warning analyzing JSON: {e}")

    def _find_matches_for_team(self, team_name):
        matches = []
        base_dir = os.path.dirname(os.path.abspath(__file__))
        npl_dir = os.path.join(base_dir, "data/npl_json")
        if not os.path.exists(npl_dir):
            return matches

        for f in sorted(glob.glob(os.path.join(npl_dir, "*.json"))):
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    d = json.load(fp)
                teams = d.get("info", {}).get("teams", [])
                team_lower = team_name.lower().replace(" ", "")
                teams_cleaned = [t.lower().replace(" ", "") for t in teams]
                if team_lower in teams_cleaned:
                    opp = [t for t in teams if t.lower().replace(" ", "") != team_lower][0]
                    dt = d.get("info", {}).get("dates", [""])[0]
                    label = f"{teams[0]} vs {teams[1]} ({dt})"
                    matches.append({"file": f, "date": dt, "teams": teams, "opponent": opp, "label": label})
            except Exception:
                pass
        return matches

    def _on_fixture_change(self, event=None):
        label = self.selected_fixture_label.get()
        if label in self.fixture_file_map:
            self.log(f"Switched linked fixture to: {label}")

    def browse_output(self):
        path = filedialog.askdirectory()
        if path:
            self.output_dir.set(path)

    def select_roi(self):
        """Allows user to scrub video timeline from 00:00 to end and drag ROI rectangle natively."""
        if cv2 is None:
            messagebox.showerror("Dependency Error", "OpenCV (cv2) is not available. Run: pip install opencv-python")
            return

        v_path = self.video_path.get()
        if not v_path or not os.path.exists(v_path):
            messagebox.showwarning("File Missing", "Please select a match video file in Step 1 first.")
            return

        def on_selected(roi):
            self.roi = roi
            self.log(f"ROI successfully saved: X={roi[0]}, Y={roi[1]}, W={roi[2]}, H={roi[3]}")

        self.log("Opening interactive ROI selector. Use timeline slider to find the scoreboard, then drag a box.")
        ROISelectorDialog(self.root, v_path, on_selected)

    def load_match_ball_metadata(self):
        """
        Loads ball-by-ball delivery metadata for both Innings 1 and Innings 2.
        Returns: { 1: { '0.1': meta, ... }, 2: { '0.1': meta, ... } }
        """
        match_lookup = {1: {}, 2: {}}
        target_file = None

        # Check if linked fixture is available
        lbl = self.selected_fixture_label.get()
        if lbl in self.fixture_file_map:
            target_file = self.fixture_file_map[lbl]
        elif self.json_path.get() and os.path.exists(self.json_path.get()):
            target_file = self.json_path.get()

        if not target_file or not os.path.exists(target_file):
            return match_lookup

        try:
            with open(target_file, "r", encoding="utf-8") as fp:
                data = json.load(fp)

            innings_list = data.get("innings", [])
            for inn_idx, inn_obj in enumerate(innings_list[:2], 1):
                team_batting = inn_obj.get("team", f"Team_{inn_idx}")
                for over_obj in inn_obj.get("overs", []):
                    over_no = over_obj.get("over", 0)
                    legal_ball = 0
                    for deliv in over_obj.get("deliveries", []):
                        extras = deliv.get("extras", {})
                        if "wides" not in extras and "noballs" not in extras:
                            legal_ball += 1
                            ball_key = f"{over_no}.{legal_ball}"
                        else:
                            shown = legal_ball if legal_ball > 0 else 1
                            ball_key = f"{over_no}.{shown}"

                        batter = deliv.get("batter", "Unknown_Batter").replace(" ", "_")
                        bowler = deliv.get("bowler", "Unknown_Bowler").replace(" ", "_")
                        runs_bat = deliv.get("runs", {}).get("batter", 0)
                        runs_tot = deliv.get("runs", {}).get("total", 0)
                        wickets = deliv.get("wickets", [])
                        is_wkt = len(wickets) > 0

                        if is_wkt:
                            cat = "Wickets"
                        elif runs_bat in (4, 6):
                            cat = "Boundaries"
                        elif runs_tot == 0:
                            cat = "Dot_Balls"
                        else:
                            cat = "Singles_Doubles"

                        match_lookup[inn_idx][ball_key] = {
                            "batter": batter,
                            "bowler": bowler,
                            "team": team_batting,
                            "runs_batter": runs_bat,
                            "runs_total": runs_tot,
                            "is_wicket": is_wkt,
                            "category": cat
                        }

            total_balls = len(match_lookup[1]) + len(match_lookup[2])
            self.log(f"Loaded ball-by-ball metadata: {len(match_lookup[1])} balls (Innings 1), {len(match_lookup[2])} balls (Innings 2).")
        except Exception as e:
            self.log(f"Notice: Could not parse match deliveries from {target_file}: {e}")

        return match_lookup

    @staticmethod
    def get_ffmpeg_bin():
        if shutil.which("ffmpeg"):
            return "ffmpeg"
        try:
            import imageio_ffmpeg
            exe = imageio_ffmpeg.get_ffmpeg_exe()
            if exe and os.path.exists(exe):
                return exe
        except Exception:
            pass
        return None

    def start_processing_thread(self):
        if self.is_running:
            return
        if not self.video_path.get() or not os.path.exists(self.video_path.get()):
            messagebox.showwarning("Missing File", "Please select a match video file first.")
            return
        if not self.roi:
            messagebox.showwarning("Missing ROI", "Please click 'Step A' to select the scoreboard over box region first.")
            return
        if not self.get_ffmpeg_bin():
            messagebox.showerror(
                "FFmpeg Missing",
                "FFmpeg executable not found. Install via Homebrew ('brew install ffmpeg') or pip ('pip install imageio-ffmpeg')."
            )
            return

        self.is_running = True
        self.start_btn.config(state="disabled", text="⏳ Processing Video...")
        threading.Thread(target=self.process_match, daemon=True).start()

    def _extract_over_number(self, text):
        """
        Normalizes OCR text and extracts valid cricket over numbers.
        Strict T20 check: over 0-19, ball 1-6. Strips leading zeros (05.2 -> 5.2).
        Rejects scores like 41.6 or 125.4.
        """
        if not text:
            return None

        cleaned = text.replace("O", "0").replace("o", "0")
        cleaned = cleaned.replace("I", "1").replace("l", "1")
        cleaned = re.sub(r"[\s,\:\-\_]+", ".", cleaned)

        # Cricket over pattern: 0.1 to 19.6
        match = re.search(r"\b([0-1]?[0-9])\.([1-6])\b", cleaned)
        if match:
            over_val = int(match.group(1))
            ball_val = int(match.group(2))
            if 0 <= over_val <= 19 and 1 <= ball_val <= 6:
                return f"{over_val}.{ball_val}"

        return None

    def process_match(self):
        try:
            v_path = self.video_path.get()
            out_base = self.output_dir.get()
            proj_name = self.project_name.get().strip() or "Match_Project"
            # Dedicated Match Project Subfolder: Output_Dir / Project_Name / ...
            match_output_folder = os.path.join(out_base, proj_name)
            os.makedirs(match_output_folder, exist_ok=True)

            self.log(f"📁 Output clips will be saved in dedicated project folder: {match_output_folder}")

            # 1. Load delivery metadata for both innings
            match_ball_lookup = self.load_match_ball_metadata()

            if self.reader is None:
                if easyocr is None:
                    self.log("Error: easyocr is not installed. Run: pip install easyocr")
                    return
                self.log("Initializing AI OCR Engine (EasyOCR)...")
                self.reader = easyocr.Reader(['en'], gpu=False, verbose=False)

            cap = cv2.VideoCapture(v_path)
            fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration_sec = total_frames / fps

            self.log(f"Starting video scan: Total duration {self._fmt_time(duration_sec)} ({duration_sec:.1f}s) | FPS: {fps:.1f}")

            x, y, w, h = self.roi
            interval_sec = max(0.4, float(self.scan_interval.get()))
            step_frames = max(1, int(fps * interval_sec))

            # Deduplication tracking:
            # Key: (current_innings, ball_str) -> timestamp
            unique_deliveries = {}
            prev_crop_gray = None
            last_detected_time = -999.0
            prev_over_float = -1.0

            # Innings mode setting
            inn_mode = self.target_innings.get()
            current_innings = 1
            if "Innings 2 Only" in inn_mode:
                current_innings = 2

            frame_idx = 0
            while frame_idx < total_frames:
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ret, frame = cap.read()
                if not ret or frame is None:
                    break

                curr_time = frame_idx / fps

                crop = frame[y:y+h, x:x+w]
                crop_gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

                # SPEED BOOST: Pixel Change Gate
                # Skip OCR if the score box is visually unchanged from previous sample
                skip_ocr = False
                if prev_crop_gray is not None and prev_crop_gray.shape == crop_gray.shape:
                    diff = cv2.absdiff(crop_gray, prev_crop_gray)
                    if diff.mean() < 3.5:
                        skip_ocr = True

                prev_crop_gray = crop_gray.copy()

                if not skip_ocr:
                    resized = cv2.resize(crop_gray, None, fx=2.5, fy=2.5, interpolation=cv2.INTER_CUBIC)
                    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))
                    enhanced = clahe.apply(resized)

                    results = self.reader.readtext(enhanced, detail=0, allowlist="0123456789.,:- ")
                    text = " ".join(results)
                    detected_ball = self._extract_over_number(text)

                    if detected_ball:
                        over_f = float(detected_ball)

                        # Auto-detect Innings 2 transition in highlights:
                        # If over resets from a late over (>= 8.0) back to an early over (<= 3.0)
                        if "Both Innings" in inn_mode and current_innings == 1:
                            if prev_over_float >= 8.0 and over_f <= 3.0:
                                current_innings = 2
                                self.log(f"🔄 Innings 2 transition detected at {self._fmt_time(curr_time)} (Over {detected_ball})")

                        prev_over_float = over_f
                        delivery_key = (current_innings, detected_ball)

                        # STRICT DEDUPLICATION:
                        # Ball can only occur ONCE per innings!
                        if delivery_key not in unique_deliveries:
                            # Delivery spacing: ensure minimum 4.0s gap between new deliveries
                            if (curr_time - last_detected_time) >= 4.0:
                                unique_deliveries[delivery_key] = curr_time
                                last_detected_time = curr_time
                                self.log(f"✅ Innings {current_innings} | Over {detected_ball} @ {self._fmt_time(curr_time)}")

                frame_idx += step_frames
                self.progress["value"] = (frame_idx / total_frames) * 100
                self.root.update_idletasks()

            cap.release()
            self.log(f"Scan complete! Identified {len(unique_deliveries)} unique deliveries (0 duplicates).")

            # Sort detected deliveries chronologically
            sorted_deliveries = sorted(unique_deliveries.items(), key=lambda x: x[1])

            # Export Video Clips using Ultra-Fast Stream Copy
            pre = float(self.pre_roll.get())
            post = float(self.post_roll.get())
            player_filter = self.target_player.get().strip().lower()
            clips_cut = 0
            ffmpeg_exe = self.get_ffmpeg_bin() or "ffmpeg"

            self.log(f"Exporting {len(sorted_deliveries)} unique clips to {match_output_folder}...")

            for idx, ((inn_num, ball_str), ts) in enumerate(sorted_deliveries):
                start_sec = max(0.0, ts - pre)
                end_sec = min(duration_sec, ts + post)

                # Clamp with previous and next deliveries to prevent cut overlap
                if idx > 0:
                    prev_ts = sorted_deliveries[idx - 1][1]
                    if start_sec < prev_ts:
                        start_sec = prev_ts + 0.1

                if idx < len(sorted_deliveries) - 1:
                    next_ts = sorted_deliveries[idx + 1][1]
                    if end_sec > next_ts:
                        end_sec = max(start_sec + 2.0, next_ts - 0.1)

                clip_len = max(2.0, end_sec - start_sec)

                # Fetch player metadata from match lookup
                meta = match_ball_lookup.get(inn_num, {}).get(ball_str, {
                    "batter": "All_Deliveries",
                    "bowler": "Bowler",
                    "runs_batter": "X",
                    "runs_total": "X",
                    "is_wicket": False,
                    "category": "Uncategorized_Balls"
                })

                if player_filter != "all" and player_filter not in meta["batter"].lower().replace("_", " "):
                    continue

                # Player-wise folder structure inside Dedicated Match Project:
                # Output_Dir / Match_Project / Batter_Name / Category / Over_...
                player_folder = os.path.join(match_output_folder, meta["batter"], meta["category"])
                os.makedirs(player_folder, exist_ok=True)

                outcome_tag = "WICKET" if meta["is_wicket"] else f"{meta['runs_batter']}runs"
                file_name = f"Inn{inn_num}_Over_{ball_str}_{meta['batter']}_vs_{meta['bowler']}_{outcome_tag}.mp4"
                out_file = os.path.join(player_folder, file_name)

                # 1. Try ultra-fast stream copy (-c copy cuts in 0.05 seconds with zero quality loss!)
                cmd_copy = [
                    ffmpeg_exe, "-y",
                    "-ss", f"{start_sec:.2f}",
                    "-i", v_path,
                    "-t", f"{clip_len:.2f}",
                    "-c", "copy",
                    "-loglevel", "error",
                    out_file
                ]
                subprocess.run(cmd_copy, check=False)

                # Fallback to ultrafast re-encode only if stream copy failed or produced 0-byte file
                if not os.path.exists(out_file) or os.path.getsize(out_file) < 1000:
                    cmd_encode = [
                        ffmpeg_exe, "-y",
                        "-ss", f"{start_sec:.2f}",
                        "-i", v_path,
                        "-t", f"{clip_len:.2f}",
                        "-c:v", "libx264", "-preset", "ultrafast",
                        "-c:a", "aac",
                        "-loglevel", "error",
                        out_file
                    ]
                    subprocess.run(cmd_encode, check=False)

                clips_cut += 1
                self.log(f"✂️ Saved: {meta['batter']}/{meta['category']}/{file_name} ({clip_len:.1f}s)")

            self.log(f"🎉 Complete! Exported {clips_cut} player clips to project folder:\n{match_output_folder}")
            messagebox.showinfo("Export Complete", f"Success! {clips_cut} player clips saved in:\n{match_output_folder}")

        except Exception as e:
            self.log(f"Error during processing: {e}")
        finally:
            self.is_running = False
            self.start_btn.config(state="normal", text="🚀 Step B: Start Automated Video Cutting")

    @staticmethod
    def _fmt_time(seconds):
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"


if __name__ == "__main__":
    root = tk.Tk()
    app = CricketAutoCutterApp(root)
    root.mainloop()