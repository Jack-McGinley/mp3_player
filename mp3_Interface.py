import sys
print("Running with:", sys.executable)

import os
import json
from io import BytesIO
from tkinter import PhotoImage, filedialog

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "hide"

import pygame
from PIL import Image, ImageSequence
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC

from customtkinter import *
from CTkListbox import *


# =========================
# Paths / Config
# =========================
APP_DIR = os.path.dirname(__file__)
CONFIG_FILE = os.path.join(APP_DIR, "player_config.json")
ART_SIZE = (300, 300)


def save_config(music_folder: str) -> None:
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"music_folder": music_folder}, f)
    except OSError:
        pass


def load_config() -> str | None:
    if not os.path.exists(CONFIG_FILE):
        return None
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        folder = data.get("music_folder")
        return folder if isinstance(folder, str) else None
    except (json.JSONDecodeError, OSError):
        return None


# =========================
# Player State
# =========================
song_map: dict[str, str] = {}          # title -> filepath
song_names: list[str] = []             # titles in playlist order
song_lengths: dict[str, float] = {}    # filepath -> seconds cache

song_queue: list[str] = []             # queued titles

curr_index: int | None = None          # playlist cursor (THIS drives next/prev)
current_song_title: str | None = None

current_song_length = 0.0              # seconds
is_playing = False                     # progress is advancing?
play_start_offset = 0.0                # seconds into song (for skip)

status_restore_job = None

# ---- Queue visual restore state ----
playing_from_queue = False             # True only while the *current track* came from queue
restore_selection_index: int | None = None  # playlist selection to restore after queued track ends


# =========================
# UI vars (filled later)
# =========================
window: CTk
playlist: CTkListbox
progress_bar: CTkProgressBar
status_label: CTkLabel
next_song_label: CTkLabel
album_art_label: CTkLabel
middle_gif_label: CTkLabel
queue_display: CTkListbox

placeholder_gif: "GifPlayer"
equalizer_gif: "GifPlayer"


# =========================
# Helpers
# =========================
def display_title(full_title: str) -> str:
    s = full_title.strip()
    if " - " in s:
        return s.split(" - ", 1)[1].strip()
    if "-" in s:
        return s.split("-", 1)[1].strip()
    return s


def set_status(msg: str) -> None:
    status_label.configure(text=msg)


def set_next_line(msg: str) -> None:
    next_song_label.configure(text=msg)


def set_default_status() -> None:
    if current_song_title:
        set_status(f"▶ {display_title(current_song_title)}")
    else:
        set_status("Ready...")


def flash_status(msg: str, restore_ms: int = 2500) -> None:
    global status_restore_job
    set_status(msg)
    if status_restore_job is not None:
        window.after_cancel(status_restore_job)
    status_restore_job = window.after(restore_ms, set_default_status)


def select_dir() -> str | None:
    folder = filedialog.askdirectory()
    return folder if folder else None


def playlist_size() -> int:
    try:
        return playlist.size()
    except Exception:
        return len(song_names)


def playlist_get(i: int) -> str:
    try:
        return playlist.get(i)
    except Exception:
        return song_names[i]


def playlist_clear() -> None:
    playlist.delete(0, "end")


def playlist_insert_end(text: str) -> None:
    playlist.insert("end", text)


def playlist_get_selected_index() -> int | None:
    sel = playlist.curselection()
    if sel is None:
        return None
    if isinstance(sel, int):
        return sel
    if isinstance(sel, (tuple, list)):
        return sel[0] if sel else None
    return None


def playlist_select_index(i: int) -> None:
    # CTkListbox selection API varies by version; this covers common ones.
    try:
        playlist.selection_clear(0, "end")
        playlist.selection_set(i)
        playlist.see(i)
        return
    except Exception:
        pass
    try:
        playlist.deselect("all")
        playlist.select(i)
        playlist.see(i)
    except Exception:
        pass


# =========================
# Album Art
# =========================
def load_album_art(mp3_path: str, size=(300, 300)) -> CTkImage | None:
    try:
        audio = MP3(mp3_path, ID3=ID3)
        if not audio.tags:
            return None

        apics = [t for t in audio.tags.values() if isinstance(t, APIC)]
        if not apics:
            return None

        front = [a for a in apics if getattr(a, "type", None) == 3]  # 3 == COVER_FRONT
        candidates = front if front else apics

        scored = []
        for a in candidates:
            try:
                with Image.open(BytesIO(a.data)) as im:
                    w, h = im.size
            except Exception:
                w = h = 0

            squareness = (min(w, h) / max(w, h)) if max(w, h) else 0.0
            pixels = w * h
            byte_len = len(a.data) if a.data else 0
            scored.append((squareness, pixels, byte_len, a))

        scored.sort(reverse=True)
        chosen = scored[0][3]

        img = Image.open(BytesIO(chosen.data)).convert("RGB")

        tw, th = size
        w, h = img.size
        side = min(w, h)
        img = img.crop(((w - side) // 2, (h - side) // 2, (w + side) // 2, (h + side) // 2))
        img = img.resize((tw, th))

        return CTkImage(img, size=size)
    except Exception:
        return None


# =========================
# GIF Player (freeze-frame control lives here)
# =========================
def load_gif_frames_and_delays(path: str, size: tuple[int, int]) -> tuple[list[CTkImage], list[int]]:
    frames: list[CTkImage] = []
    delays: list[int] = []
    im = Image.open(path)
    for frame in ImageSequence.Iterator(im):
        delay = max(20, int(frame.info.get("duration", 80)))
        pil = frame.convert("RGBA").resize(size)
        frames.append(CTkImage(pil, size=size))
        delays.append(delay)
    return frames, delays


class GifPlayer:
    def __init__(self, tk_root: CTk, target_label: CTkLabel, path: str, size: tuple[int, int]):
        self.tk_root = tk_root
        self.target_label = target_label
        self.frames, self.delays = load_gif_frames_and_delays(path, size)

        self.job = None
        self._seq = []
        self._pos = 0
        self._loop = False
        self._on_done = None

        self.seq_startup = None         
        self.seq_running = None        
        self.seq_stop = None

        # Default “freeze” frames if you ever want them
        self.pause_frame_index = 0

    def _sanitize_seq(self, seq):
        if not self.frames:
            return []
        n = len(self.frames)
        out = [i for i in seq if 0 <= i < n]
        return out

    def _show_frame(self, idx: int):
        frame = self.frames[idx]
        self.target_label.configure(image=frame)
        self.target_label.image = frame

    def play_sequence(self, seq, loop=False, on_done=None):
        """Play a sequence of frame indices."""
        if self.job is not None:
            self.tk_root.after_cancel(self.job)
            self.job = None

        seq = self._sanitize_seq(seq)
        if not seq:
            return

        self._seq = seq
        self._pos = 0
        self._loop = loop
        self._on_done = on_done

        def step():
            idx = self._seq[self._pos]
            self._show_frame(idx)

            delay = self.delays[idx] if idx < len(self.delays) else 80

            self._pos += 1
            if self._pos >= len(self._seq):
                if self._loop:
                    self._pos = 0
                else:
                    self.job = None
                    cb = self._on_done
                    self._on_done = None
                    if cb:
                        cb()
                    return

            self.job = self.tk_root.after(delay, step)

        step()

    def start(self, mode="running"):
        # If you never configured sequences, just animate all frames.
        if self.seq_running is None:
            self.play_sequence(list(range(len(self.frames))), loop=True)
            return

        if mode == "startup_then_running" and self.seq_startup:
            self.play_sequence(self.seq_startup, loop=False,
                                on_done=lambda: self.play_sequence(self.seq_running, loop=True))
        else:
            self.play_sequence(self.seq_running, loop=True)

    def stop(self, mode="pause"):
        if mode == "stop_reverse":
            # If stop seq not configured, just freeze instead.
            if self.seq_stop:
                self.play_sequence(self.seq_stop, loop=False)
            else:
                self.stop("pause")
            return

        # pause freeze
        if self.job is not None:
            self.tk_root.after_cancel(self.job)
            self.job = None

        if not self.frames:
            return

        idx = max(0, min(self.pause_frame_index, len(self.frames) - 1))
        self._show_frame(idx)


def start_placeholder_gif() -> None:
    placeholder_gif.start()


def stop_placeholder_gif() -> None:
    placeholder_gif.stop()


# =========================
# Audio + Playback
# =========================
def ensure_audio() -> bool:
    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        return True
    except pygame.error as e:
        flash_status(f"Audio init failed: {e}", 3000)
        return False


def scan_folder(folder: str) -> dict[str, str]:
    if not folder or not os.path.isdir(folder):
        return {}
    mp3_files = [f for f in os.listdir(folder) if f.lower().endswith(".mp3")]
    return {f[:-4]: os.path.join(folder, f) for f in mp3_files}


def load_music_from_folder(folder: str) -> None:
    global song_map, song_names, curr_index

    song_map = scan_folder(folder)
    song_names = list(song_map.keys())
    curr_index = 0 if song_names else None

    playlist_clear()
    for name in song_names:
        playlist_insert_end(name)

    refresh_queue_mini()
    update_next_line()

    if song_names:
        flash_status(f"Loaded {len(song_names)} songs.", 2000)
    else:
        flash_status("No MP3s found in that folder.", 2500)


def load_music_button() -> None:
    folder = select_dir()
    if not folder:
        flash_status("No folder selected.", 2000)
        return
    save_config(folder)
    load_music_from_folder(folder)


def play_music(file_path: str) -> None:
    global current_song_length, is_playing, play_start_offset

    if not ensure_audio():
        return

    if not os.path.exists(file_path):
        flash_status("File not found.", 2500)
        return

    play_start_offset = 0.0
    progress_bar.set(0)

    if file_path in song_lengths:
        current_song_length = song_lengths[file_path]
    else:
        try:
            sound = pygame.mixer.Sound(file_path)
            current_song_length = float(sound.get_length())
            song_lengths[file_path] = current_song_length
        except pygame.error:
            current_song_length = 0.0

    pygame.mixer.music.load(file_path)
    pygame.mixer.music.play()
    is_playing = True


# =========================
# Queue (single source of truth)
# =========================
def refresh_queue_mini() -> None:
    queue_display.delete(0, "end")
    if not song_queue:
        queue_display.insert("end", "(queue empty)")
        return

    MAX_ITEMS = 3
    for title in song_queue[:MAX_ITEMS]:
        queue_display.insert("end", display_title(title))
    if len(song_queue) > MAX_ITEMS:
        queue_display.insert("end", f"... +{len(song_queue) - MAX_ITEMS}")


def update_next_line() -> None:
    if song_queue:
        set_next_line(f"Next: {display_title(song_queue[0])}")
        return

    if playlist_size() == 0 or curr_index is None:
        set_next_line("No songs queued.")
        return

    nxt = (curr_index + 1) % playlist_size()
    set_next_line(f"Next: {display_title(playlist_get(nxt))}")


def add_selected_to_queue(event=None) -> None:
    idx = playlist_get_selected_index()
    if idx is None or idx < 0 or idx >= len(song_names):
        return
    song_queue.append(song_names[idx])
    refresh_queue_mini()
    update_next_line()
    flash_status("Added to queue.", 1200)


def pop_queue_next_index() -> int | None:
    """Pop next queued title and return its playlist index, or None."""
    while song_queue:
        title = song_queue.pop(0)
        refresh_queue_mini()
        update_next_line()
        try:
            return song_names.index(title)
        except ValueError:
            continue
    return None


def clear_queue(event=None) -> None:
    song_queue.clear()
    refresh_queue_mini()
    update_next_line()
    flash_status("Queue cleared.", 1500)


# =========================
# Playback control (QUEUE FIX + SELECTION SNAP BACK)
# =========================
def play_song(idx: int | None = None, update_cursor: bool = True) -> None:
    """
    - update_cursor=True  -> normal playlist behavior (moves curr_index)
    - update_cursor=False -> queue behavior (DOES NOT move curr_index)
    """
    global curr_index, current_song_title, is_playing, play_start_offset
    global playing_from_queue, restore_selection_index

    if playlist_size() == 0:
        flash_status("Playlist is empty.", 2000)
        return

    # stop current track
    try:
        pygame.mixer.music.stop()
    except Exception:
        pass
    is_playing = False
    play_start_offset = 0.0
    progress_bar.set(0)

    if idx is None:
        idx = playlist_get_selected_index()
        if idx is None:
            idx = 0

    # If this is a queue play, remember what selection to restore later
    if not update_cursor:
        playing_from_queue = True
        restore_selection_index = curr_index  # may be None if nothing played yet
    else:
        playing_from_queue = False
        restore_selection_index = None

    # Always show the selected/playing item visually while it plays
    playlist_select_index(idx)

    # Only update the playlist cursor if this is a "real" playlist play
    if update_cursor:
        curr_index = idx

    song_title = playlist_get(idx)
    current_song_title = song_title

    set_status(f"▶ {display_title(song_title)}")
    update_next_line()

    path = song_map.get(song_title)
    if not path:
        flash_status("Song path missing.", 2500)
        return

    play_music(path)
    equalizer_gif.start()

    art = load_album_art(path, size=ART_SIZE)
    if art is None:
        start_placeholder_gif()
    else:
        stop_placeholder_gif()
        album_art_label.configure(image=art)
        album_art_label.image = art


def next_song(event=None) -> None:
    """
    Priority:
      1) queue
      2) playlist cursor (curr_index) + 1
    """
    global curr_index

    if playlist_size() == 0:
        return

    q_idx = pop_queue_next_index()
    if q_idx is not None:
        # ✅ play queued item but DO NOT move playlist cursor
        play_song(q_idx, update_cursor=False)
        return

    if curr_index is None:
        play_song(0, update_cursor=True)
        return

    nxt = curr_index + 1
    if nxt >= playlist_size():
        nxt = 0

    play_song(nxt, update_cursor=True)


def prev_song(event=None) -> None:
    global curr_index
    if playlist_size() == 0:
        return

    if curr_index is None:
        play_song(0, update_cursor=True)
        return

    prv = curr_index - 1
    if prv < 0:
        prv = playlist_size() - 1

    play_song(prv, update_cursor=True)


def play_selected(event=None) -> None:
    idx = playlist_get_selected_index()
    if idx is not None:
        play_song(idx, update_cursor=True)


def pause_song() -> None:
    global is_playing
    try:
        pygame.mixer.music.pause()
    except Exception:
        return
    is_playing = False
    flash_status("Music paused.", 1500)
    equalizer_gif.stop("pause")   # freeze-frame for pause


def resume_song() -> None:
    global is_playing
    try:
        pygame.mixer.music.unpause()
    except Exception:
        return
    is_playing = True
    flash_status("Music resumed.", 1500)
    equalizer_gif.start()


def stop_song() -> None:
    global is_playing, current_song_title
    global playing_from_queue, restore_selection_index

    try:
        pygame.mixer.music.stop()
    except Exception:
        pass

    is_playing = False
    progress_bar.set(0)
    current_song_title = None
    set_default_status()

    playing_from_queue = False
    restore_selection_index = None

    start_placeholder_gif()
    equalizer_gif.stop("stop_reverse")    # freeze-frame for stop


def toggle_play_pause(event=None) -> None:
    if is_playing:
        pause_song()
    else:
        resume_song()


def skip_seconds(delta: float) -> None:
    global play_start_offset

    if current_song_length <= 0:
        return

    pos_ms = pygame.mixer.music.get_pos()
    pos_sec = max(0.0, pos_ms / 1000.0) if pos_ms >= 0 else 0.0
    current_abs = play_start_offset + pos_sec

    new_pos = max(0.0, min(current_abs + delta, current_song_length - 0.1))
    play_start_offset = new_pos

    pygame.mixer.music.play(start=new_pos)
    if not is_playing:
        pygame.mixer.music.pause()


current_volume = 0.5


def set_volume(val) -> None:
    """Slider is 0..10; pygame expects 0..1."""
    global current_volume
    try:
        current_volume = float(val) / 10.0
        current_volume = max(0.0, min(current_volume, 1.0))
        pygame.mixer.music.set_volume(current_volume)
    except Exception:
        pass


# =========================
# Progress (QUEUE SNAP-BACK happens here)
# =========================
def update_progress() -> None:
    global is_playing
    global playing_from_queue, restore_selection_index

    if is_playing and current_song_length > 0:
        pos_ms = pygame.mixer.music.get_pos()
        if pos_ms >= 0:
            pos_sec = play_start_offset + (pos_ms / 1000.0)
            fraction = min(pos_sec / current_song_length, 1.0)
            progress_bar.set(fraction)

            # End detection
            if pos_sec >= current_song_length - 0.2:
                is_playing = False

                # ✅ If the track that ended was from queue, restore selection first
                if playing_from_queue:
                    playing_from_queue = False
                    if restore_selection_index is not None and 0 <= restore_selection_index < playlist_size():
                        playlist_select_index(restore_selection_index)
                    restore_selection_index = None

                next_song()
        else:
            progress_bar.set(0)

    window.after(200, update_progress)


# =========================
# UI Build (same layout architecture)
# =========================
window = CTk()
window.geometry("850x720")
window.title("Music Player")
window.configure(fg_color="black")

icon = PhotoImage(file=os.path.join(APP_DIR, "icons/music_note_icon.png"))
window.iconphoto(True, icon)

label = CTkLabel(
    window,
    text="MUSIC PLAYER",
    font=("Monospace", 45, "bold"),
    text_color="#00FFAA",
)
label.pack(pady=(10, 2))

playlist_outer = CTkFrame(
    window,
    fg_color="black",
    border_color="#00FFAA",
    border_width=3,
    corner_radius=0
)
playlist_outer.grid_columnconfigure(0, weight=1)
playlist_outer.grid_rowconfigure(0, weight=1)
playlist_outer.pack(padx=20, pady=(5, 10), fill="x")

playlist_inner = CTkFrame(
    playlist_outer,
    fg_color="black",
    border_color="#222222",
    border_width=4,
    corner_radius=0
)
playlist_inner.columnconfigure(0, weight=3)
playlist_inner.columnconfigure(1, weight=2)
playlist_inner.rowconfigure(0, weight=1)
playlist_inner.grid(column=0, row=0, padx=4, pady=4, sticky="nsew")

playlist_left = CTkFrame(playlist_inner, fg_color="black", corner_radius=0)
playlist_left.grid(row=0, column=0, sticky="nsew", padx=(4, 2), pady=4)

playlist_label = CTkLabel(
    playlist_left,
    text="Playlist",
    font=("Helvetica", 20, "bold"),
    text_color="#00FFAA",
    fg_color="black",
    anchor="n",
)
playlist_label.pack(anchor="n", pady=(6, 2))

playlist = CTkListbox(
    playlist_left,
    width=400,
    height=220,
    font=("Helvetica", 18),
    fg_color="black",
    text_color="#00FFAA",
    border_width=0,
    highlight_color="#003300",
    hover_color="#004400",
)
playlist.pack(padx=2, pady=(2, 4), fill="x")

load_music_btn = CTkButton(playlist_left, text="Load Music", command=load_music_button)
load_music_btn.configure(
    font=("Helvetica", 16, "bold"),
    text_color="black",
    fg_color="#00FFAA",
    corner_radius=0,
    anchor="s",
)
load_music_btn.pack(anchor="s", padx=6, pady=(2, 6))

playlist_right = CTkFrame(
    playlist_inner,
    fg_color="black",
    border_color="#00FFAA",
    border_width=2,
    corner_radius=0
)
playlist_right.grid(row=0, column=1, sticky="nsew", padx=(2, 4), pady=4)
playlist_right.configure(width=260)
playlist_right.grid_propagate(False)

album_art_label = CTkLabel(playlist_right, text="")
album_art_label.pack(pady=(12, 8))

placeholder_gif = GifPlayer(window, album_art_label, os.path.join(APP_DIR, "gifs/placeholder.gif"), ART_SIZE)
start_placeholder_gif()

progress_bar = CTkProgressBar(
    window,
    width=500,
    height=10,
    fg_color="black",
    progress_color="#00FF00",
    border_width=1,
    border_color="#00FF00",
)
progress_bar.set(0)
progress_bar.pack(pady=(2, 10))

frame = CTkFrame(window, fg_color="black")
frame.pack(pady=10)
frame.grid_rowconfigure(0, weight=1)
frame.grid_rowconfigure(1, weight=1)
frame.grid_columnconfigure(0, weight=1)

frame_top = CTkFrame(frame, fg_color="black")
frame_top.grid(row=0, column=0, sticky="nsew", pady=(0, 5))

frame_middle = CTkFrame(frame, fg_color="black")
frame_middle.grid(row=1, column=0, sticky="nsew", pady=(0, 5))

for row_frame in (frame_top, frame_middle):
    row_frame.grid_columnconfigure(0, weight=1)
    row_frame.grid_columnconfigure(1, weight=1)
    row_frame.grid_columnconfigure(2, weight=1)

photo_Button_style = {
    "width": 50,
    "height": 50,
    "fg_color": "black",
    "hover_color": "#003300",
    "border_color": "#00FF00",
    "border_width": 1,
    "corner_radius": 0,
}

pause_icon = CTkImage(Image.open(os.path.join(APP_DIR, "icons/pause.png")), size=(26, 26))
play_icon = CTkImage(Image.open(os.path.join(APP_DIR, "icons/play.png")), size=(26, 26))
prev_icon = CTkImage(Image.open(os.path.join(APP_DIR, "icons/previous.png")), size=(26, 26))
next_icon = CTkImage(Image.open(os.path.join(APP_DIR, "icons/next.png")), size=(26, 26))
resume_icon = CTkImage(Image.open(os.path.join(APP_DIR, "icons/resume.png")), size=(26, 26))
stop_icon = CTkImage(Image.open(os.path.join(APP_DIR, "icons/stop.png")), size=(26, 26))

prevButton = CTkButton(frame_top, text="", image=prev_icon, command=prev_song, **photo_Button_style)
playButton = CTkButton(frame_top, text="", image=play_icon, command=lambda: play_song(None, update_cursor=True), **photo_Button_style)
nextButton = CTkButton(frame_top, text="", image=next_icon, command=next_song, **photo_Button_style)

pauseButton = CTkButton(frame_middle, text="", image=pause_icon, command=pause_song, **photo_Button_style)
resumeButton = CTkButton(frame_middle, text="", image=resume_icon, command=resume_song, **photo_Button_style)
stopButton = CTkButton(frame_middle, text="", image=stop_icon, command=stop_song, **photo_Button_style)

prevButton.grid(row=0, column=0, padx=5, pady=2)
playButton.grid(row=0, column=1, padx=5, pady=2)
nextButton.grid(row=0, column=2, padx=5, pady=2)
pauseButton.grid(row=0, column=0, padx=5, pady=2)
resumeButton.grid(row=0, column=1, padx=5, pady=2)
stopButton.grid(row=0, column=2, padx=5, pady=2)

volume = CTkSlider(
    window,
    from_=0,
    to=10,
    orientation="Horizontal",
    fg_color="black",
    progress_color="#00FF00",
    button_color="#003300",
    border_color="#00FF00",
    button_hover_color="#004400",
    button_length=2,
    width=200,
    height=10,
    border_width=1,
    command=set_volume,
)
volume.set(5)
volume.pack(pady=5)

bottom_bar = CTkFrame(window, fg_color="black")
bottom_bar.pack(side="bottom", fill="x", padx=5, pady=5)
bottom_bar.grid_columnconfigure(0, weight=1)
bottom_bar.grid_columnconfigure(1, weight=1)
bottom_bar.grid_columnconfigure(2, weight=1)
bottom_bar.grid_rowconfigure(0, weight=1)
bottom_bar.grid_rowconfigure(1, weight=1)

left_section = CTkFrame(bottom_bar, fg_color="black", width=200, height=80, border_width=1, border_color="#00FFAA", corner_radius=0)
left_section.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(5, 0), pady=5)
left_section.grid_propagate(False)

middle_section = CTkFrame(bottom_bar, fg_color="black", width=200, height=80, border_width=1, border_color="#00FFAA", corner_radius=0)
middle_section.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=(2, 2), pady=5)
middle_section.grid_propagate(False)

right_section = CTkFrame(bottom_bar, fg_color="black", width=200, height=80, border_width=1, border_color="#00FFAA", corner_radius=0)
right_section.grid(row=0, column=2, rowspan=2, sticky="nsew", padx=(0, 5), pady=5)
right_section.grid_propagate(False)

status_label = CTkLabel(left_section, text="Ready...", font=("Consolas", 14), text_color="#00FF00", fg_color="black", anchor="w")
status_label.grid(row=0, column=0, sticky="w", padx=(4, 2), pady=(2, 0))

next_song_label = CTkLabel(left_section, text="No songs queued.", font=("Consolas", 14), text_color="#00FF00", fg_color="black", anchor="w")
next_song_label.grid(row=1, column=0, sticky="w", padx=(4, 2), pady=(0, 2))

middle_gif_label = CTkLabel(middle_section, text="")
middle_gif_label.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=2, pady=2)

equalizer_gif = GifPlayer(window, middle_gif_label, os.path.join(APP_DIR, "gifs/equalizer.gif"), (269, 75))
#equalizer_gif.active_frame_indices = list(range(10, 25))  # only these animate when playing
equalizer_gif.seq_startup = list(range(0, 10))          # 0..9 (once)
equalizer_gif.seq_running = list(range(10, 26))         # 10..25 (loop)
equalizer_gif.seq_stop = list(range(12, 9, -1))       
equalizer_gif.pause_frame_index = 12
equalizer_gif.stop("stop_reverse")

queue_display = CTkListbox(
    right_section,
    width=252,
    height=68,
    font=("Consolas", 14),
    fg_color="black",
    text_color="#00FF00",
    corner_radius=0,
)
queue_display.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(1, 3), pady=(1, 3))
refresh_queue_mini()


# =========================
# Bindings
# =========================
playlist.bind("<Double-Button-1>", play_selected)
playlist.bind("<Button-3>", add_selected_to_queue)

window.bind("<space>", toggle_play_pause)
window.bind("<Tab>", lambda e: stop_song())
window.bind("<Escape>", lambda e: window.destroy())

window.bind("<Right>", lambda e: skip_seconds(10))
window.bind("<Left>", lambda e: skip_seconds(-10))

window.bind("<Control-Right>", next_song)
window.bind("<Control-Left>", prev_song)

window.bind("<c>", clear_queue)


# =========================
# Startup
# =========================
update_progress()

last_folder = load_config()
if last_folder and os.path.isdir(last_folder):
    load_music_from_folder(last_folder)

window.mainloop()
