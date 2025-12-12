import sys
print("Running with:", sys.executable)
from tkinter import *
from customtkinter import *
from CTkListbox import *
from PIL import Image
import os
import json
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "hide"
import pygame

#Set config file for saving music directory on startup
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "player_config.json")

#save the last folder loaded
def save_config(music_folder):
    data = {
        "music_folder": music_folder
    }
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f)

#Load the folder on startup
def load_config():
    if not os.path.exists(CONFIG_FILE):
        return None

    try:
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
        return data.get("music_folder")
    except (json.JSONDecodeError, IOError):
        return None
    
# Helper to load saved folder (non-recursive, uses songs())
def load_music_from_folder(folder):
    global song_map, song_names, curr_index

    song_map = songs(folder)   # reuse existing logic
    if not song_map:
        set_status("No MP3s found in saved folder.")
        return

    song_names = list(song_map.keys())
    curr_index = 0 if song_names else -1

    playlist.delete(0, END)
    for name in song_names:
        playlist.insert(END, name)

    set_status(f"Loaded {len(song_names)} songs from last session.")

#Set Song length for progress bar
current_song_length = 0.0   # in seconds
is_playing = False          # whether playback is actively progressing

#Helper functions for messages
status_restore_job = None
current_song_title = None  # track what's playing (string)

#Store songs in cache
song_map = {}
song_names = []
curr_index = -1
song_lengths = {}

def set_status(msg: str):
    status_label.configure(text=msg)

def set_default_status():
    # what should be shown normally
    if current_song_title:
        set_status(f"Now Playing: {current_song_title}")
    else:
        set_status("Ready.")

def flash_status(msg: str, restore_ms: int = 3000):
    """Show msg now; restore default status after restore_ms."""
    global status_restore_job
    set_status(msg)

    # cancel any pending restore to avoid racing
    if status_restore_job is not None:
        window.after_cancel(status_restore_job)

    status_restore_job = window.after(restore_ms, set_default_status)

#return file_path to folder with music
def select_dir():
    dir_path = filedialog.askdirectory()
    return dir_path

#Create function to read songs from music folder
def songs(folder):
    """
    Initializes the pygame mixer, and
    creates a list of mp3 files contained within
    the folder used to house the music files.
    """

    try:
        pygame.mixer.init()
    except pygame.error as e:
        print("Audio initialization failed! ", e)
        return

    if not os.path.isdir(folder):
        print(f"Folder '{folder}' not found")
        return

    mp3_files = [file for file in os.listdir(folder) if file.endswith(".mp3")]
    
    if not mp3_files:
        print("No .mp3 files found!")
    
    songs = {file.replace('.mp3', ""): os.path.join(folder, file) for file in mp3_files}
    return songs

#def load_music loads the music from a directory to the listbox
def load_music():
    global song_map, song_names, curr_index

    folder = select_dir()
    print("Selected folder:", repr(folder))
    if not folder:
        print('Please select a folder')
        return
    
    song_map = songs(folder) #dict: name -> path
    song_names = list(song_map.keys())
    curr_index = 0 if song_names else -1
    
    playlist.delete(0, END)
    for song in song_names:
        playlist.insert(END, song)

    save_config(folder)  

#Create a play_music function to map to play_song button
def play_music(file_path, song_name=None):
    """
    Uses the filepath to open the folder 
    containing the mp3 files and uses
    pygame mixer to load mp3 file and play the song.
    """
    global current_song_length, is_playing

    #file_path = os.path.join(folder, song_name + '.mp3')

    if not os.path.exists(file_path):
        flash_status("File not found", 3000)
        return

    if file_path in song_lengths:
        current_song_length = song_lengths[file_path]
    else:
        try:
            #Get song length in seconds using Sound Object
            sound = pygame.mixer.Sound(file_path)
            current_song_length = sound.get_length()
            song_lengths[file_path] = current_song_length
        except pygame.error as e:
            print("Could not get song length:", e)
            current_song_length = 0.0

    pygame.mixer.music.load(file_path)
    pygame.mixer.music.play()

    progress_bar.set(0)
    is_playing = True

#Create a function to update progress bar
def update_progress():
    """
    Periodically update the progress bar based on
    pygame.mixer.music.get_pos() and current_song_length.
    """
    if is_playing and current_song_length > 0:
        pos_ms = pygame.mixer.music.get_pos()   # milliseconds since play()
        if pos_ms >= 0:
            pos_sec = pos_ms / 1000.0
            fraction = min(pos_sec / current_song_length, 1.0)
            progress_bar.set(fraction)
        else:
            # pos_ms < 0 can mean finished or stopped
            progress_bar.set(0)

    # schedule the next update
    window.after(200, update_progress)  # update ~5 times per second

#Create a function to play selected song in playlist
def play_song():
    """
    Selects the song currently selected
    in the windows listbox and passes the song name
    to the play_music function to load and play the track.
    """

    global is_playing

    #Stop track currently playing
    pygame.mixer.music.stop()
    is_playing = False
    progress_bar.set(0)

    try:
        #Selects currently highlighted song
        song_title = playlist.get(playlist.curselection())
    except TclError:
        print("No song selected!")
        set_status("No song selected!")
        return
    
    print(f"Currently Playing: {song_title}")

    global current_song_title
    current_song_title = song_title
    set_status(f"Now Playing: {song_title}")   # immediate

    #Call play_music function
    play_music(song_map[song_title])

#Create a function to pause the currently playing song
def pause_song():
    global is_playing
    pygame.mixer.music.pause()
    is_playing = False    # freeze progress
    print("Music Paused")
    set_status("Music Paused.")

#Create a function to resume the currently playing song
def resume_song():
    global is_playing
    pygame.mixer.music.unpause()
    is_playing = True     # resume progress
    print("Music Resumed")
    flash_status("Music Resumed.", 3000)

#Create a function to stop playing the currently selected song
def stop_song():
    global is_playing, current_song_title
    pygame.mixer.music.stop()
    is_playing = False
    progress_bar.set(0)   # reset bar
    current_song_title=None #Set global variable to none to return 'Ready' message
    print("Music Stopped")
    flash_status("Music Stopped.", 3000)

#Create a function to clear selection for CTkListbox
def clear_selection():
    size = playlist.size()
    for i in range(size):
        playlist.deselect(i)

#Create a current function to get the index from CTkListbox
def get_current_index():
    sel = playlist.curselection()
    return sel  # already int or None

#play next song in playlist
def next_song():
    global curr_index
    if playlist.size() == 0:
        return

    # Sync index from UI if needed
    if curr_index is None:
        idx = get_current_index()
        curr_index = 0 if idx is None else idx

    next_index = curr_index + 1

    if next_index < playlist.size():
        curr_index = next_index
        clear_selection()
        playlist.select(curr_index)
        playlist.see(curr_index)
        play_song()
    else:
        flash_status("Reached end of playlist.", 3000)

#Play previous song in playlist
def prev_song():
    global curr_index
    if playlist.size() == 0:
        return

    if curr_index is None:
        idx = get_current_index()
        curr_index = (playlist.size() - 1) if idx is None else idx

    prev_index = curr_index - 1

    if prev_index >= 0:
        curr_index = prev_index
        clear_selection()
        playlist.select(curr_index)
        playlist.see(curr_index)
        play_song()
    else:
        flash_status("Reached beginning of playlist.", 3000)

current_volume = 0.5  # start loud

def set_volume(val):
    global current_volume
    # assume slider 0..100; adjust if yours is 0..1
    current_volume = float(val)
    pygame.mixer.music.set_volume(current_volume)

#========Create Window Interface====================

# windows = serves as a container to hold or contain widgets
window = CTk() #Create instance of a window: 'Tk'
#Set size of window using 'geometry' method
window.geometry("600x480")
#Set title of the window using 'title' method
window.title("Music Player") 

#Convert .png to 'Photo Image' 
icon = PhotoImage(file='icons/music_note_icon.png')
#Set icon image of window using 'iconphoto' function
window.iconphoto(True, icon)

#Set background color of window using 'configure' method
window.configure(fg_color="black")

#label = an area widget that holds text and/or image within a window
#Create a label using constructor: 'Label'
label = CTkLabel(window,#pass window as argument to label that is within window
        text="Music Player",
        font=("Helvetica", 45, 'bold'),
        #fg_color='black',
        text_color='#00FFAA', #Color of text
)
#Add label to window using 'pack' method
label.pack(pady=(10, 0))

# Outer frame = green border, looks like a terminal window
playlist_outer = CTkFrame(
    window,
    fg_color="black",
    border_color="#00FFAA",    # bright green border
    border_width=3,
    corner_radius=0            # sharp edges = more retro
)
playlist_outer.pack(padx=20, pady=(5, 10), fill="x")

# Inner frame = padding + background behind label + listbox
playlist_inner = CTkFrame(
    playlist_outer,
    fg_color="black",
    border_color="#222222",
    border_width=4,
    corner_radius=0
)
playlist_inner.pack(padx=4, pady=4, fill="x")

# "Playlist" label, tight above the listbox
playlist_label = CTkLabel(
    playlist_inner,
    text="Playlist",
    font=("Helvetica", 20, "bold"),
    text_color="#00FFAA",
    fg_color="black",
    anchor="n",
)
playlist_label.pack(anchor="n", pady=(6, 2))  # <- very close to listbox

# The CTkListbox itself
playlist = CTkListbox(
    playlist_inner,
    width=400,
    height=260,
    font=("Helvetica", 18),
    fg_color="black",          # listbox background
    text_color="#00FFAA",      # if your version supports it; if not, it's ignored
    border_width=0,            # border handled by outer frame
    highlight_color="#003300",
    hover_color="#004400",
)
playlist.pack(padx=2, pady=(2, 4), fill="x")

#'Load Music' label, bottom right corner of listbox
load_music = CTkButton(
    playlist_inner,
    text="Load Music",
    command=load_music)
load_music.configure(font=("Helvetica", 16, "bold"),
    text_color='black',
    fg_color="#00FFAA",
    corner_radius=0,
    anchor="s")
load_music.pack(anchor="s", padx=6, pady=(2, 6))

#Call songs function to return list of available songs
#mp3_files = songs()

#Use insert method to add items to listbox
#for song in mp3_files:
#    playlist.insert(END, song)
#Adjust size of listbox dynamically
#playlist.configure(height=playlist.size())

#Create a progress bar under the listbox
progress_bar = CTkProgressBar(
    window,
    width=450,
    height=10,
    fg_color="black",
    progress_color="#00FF00",   # retro green
    border_width=1,
    border_color="#00FF00"
)
progress_bar.set(0)  # start at 0%
progress_bar.pack(pady=(2, 10))
#Call update progress
update_progress()

#Create a frame to hold action buttons
frame = CTkFrame(window) #Instance 'Frame' passed our window
#Configureure visals for frame 
frame.configure(fg_color='black')
frame.pack(pady=10) #Add frame to window

#Configureure fram to allow rows and columns
frame.grid_rowconfigure(0, weight=1)
frame.grid_rowconfigure(1, weight=1)
#frame.grid_rowconfigure(2, weight=1)
frame.grid_columnconfigure(0, weight=1)

#Create top row of the frame
frame_top = CTkFrame(frame, fg_color='black')
frame_top.grid(row=0, column=0, sticky='nsew', pady=(0, 5))

#Create middle row of the frame
frame_middle = CTkFrame(frame, fg_color='black')
frame_middle.grid(row=1, column=0, sticky='nsew', pady=(0, 5))

#Create bottom row of the frame
#frame_bottom = CTkFrame(frame, fg_color='black')
#frame_bottom.grid(row=2, column=0, sticky='nsew', pady=(0, 5))

#Each row has 3 columns for 3 buttons
for row_frame in (frame_top, frame_middle): #frame_bottom):
    row_frame.grid_columnconfigure(0, weight=1)
    row_frame.grid_columnconfigure(1, weight=1)
    #row_frame.grid_columnconfigure(2, weight=1)

#Button Style
button_style = {
    "font": ("Helvetica", 18, "bold"),
    "fg_color": "#00FFAA",    # main button color
    "hover_color": "#004400", # hover color
    "text_color": "black",
    "width": 100,
    "height": 32,
    "border_width": 0,
    "corner_radius": 0
}

photo_Button_style = {
    "width": 50,
    "height": 50,
    "fg_color": "black",
    "hover_color": "#003300",
    "border_color": "#00FF00",
    "border_width": 1,
}

#Image for pause button
pause_icon = CTkImage(
    Image.open("icons/pause.png"),
    size=(26, 26)
)

#Image for play button
play_icon = CTkImage(
    Image.open("icons/play.png"),
    size=(26, 26)
)

#Image for previous button
prev_icon = CTkImage(
    Image.open("icons/previous.png"),
    size=(26, 26)
)

#Image for next button
next_icon = CTkImage(
    Image.open("icons/next.png"),
    size=(26, 26)
)

#Image for resume button
resume_icon = CTkImage(
    Image.open("icons/resume.png"),
    size=(26, 26)
)

#Image for resume button
stop_icon = CTkImage(
    Image.open("icons/stop.png"),
    size=(26, 26)
)

#Button Creation
prevButton = CTkButton(
    frame_top,
    text="",
    image=prev_icon,
    command=prev_song,
    **photo_Button_style
)

nextButton = CTkButton(
    frame_top,
    text="",
    image=next_icon,
    command=next_song,
    **photo_Button_style
)

playButton = CTkButton(
    frame_top,
    text="",
    image=play_icon,
    command=play_song,
    **photo_Button_style
)

resumeButton = CTkButton(
    frame_middle,
    text="",
    image=resume_icon,
    command=resume_song,
    **photo_Button_style
)

pauseButton = CTkButton(
    frame_middle,
    text="",
    image=pause_icon,
    command=pause_song,
    **photo_Button_style
)

stopButton = CTkButton(
    frame_middle,
    text="",
    image=stop_icon,
    command=stop_song,
    **photo_Button_style
)

#prevButton = CTkButton(frame_top, text="Previous", command=prev_song, **button_style)
prevButton.grid(row=0, column=0, sticky="n", padx=5, pady=2)

#playButton = CTkButton(frame_top, text="Play", command=play_song, **button_style)
playButton.grid(row=0, column=1, sticky="n", padx=5, pady=2)

#nextButton = CTkButton(frame_top, text="Next", command=next_song, **button_style)
nextButton.grid(row=0, column=2, sticky="n", padx=5, pady=2)

#pauseButton = CTkButton(frame_middle, text="Pause", command=pause_song, **button_style)
pauseButton.grid(row=0, column=0, sticky="n", padx=5, pady=2)

#resumeButton = CTkButton(frame_middle, text="Resume", command=resume_song, **button_style)
resumeButton.grid(row=0, column=1, sticky="n", padx=5, pady=2)

#stopButton = CTkButton(frame_middle, text="Stop", command=stop_song, **button_style)
stopButton.grid(row=0, column=2, sticky="n", padx=5, pady=2)

#Create a slider button for volume control
volume = CTkSlider(window,
    from_=0,
    to=10,
    orientation="Horizontal",
    fg_color='black',
    progress_color="#00FFAA",
    button_color="#003300",
    border_color="#00FF00",
    button_hover_color="#004400",
    button_length=15,
    width=200,
    height=10,
    border_width=1,
    command=set_volume
)
volume.pack(pady=5)

#Create a frame at the bottom of the window
bottom_bar = CTkFrame(window, fg_color="black")
bottom_bar.pack(side="bottom", fill="x", padx=5, pady=5)
bottom_bar.grid_columnconfigure(0, weight=1)
bottom_bar.grid_columnconfigure(1, weight=1)

quitButton = CTkButton(bottom_bar, text="QUIT", command=window.destroy, **button_style)
quitButton.grid(row=0, column=1, sticky="e", padx=(5, 5), pady=(0, 5))  

#Terminal Line
status_label = CTkLabel(
    bottom_bar,
    text="Ready.",
    font=("Helvetica", 18),
    text_color="#00FFAA",   # retro green
    fg_color="black",       # same background
    anchor="w"
)
status_label.grid(row=0, column=0, sticky="w", padx=(5, 5), pady=(0, 5))

last_folder = load_config()
if last_folder and os.path.isdir(last_folder):
    load_music_from_folder(last_folder)

#Display window
window.mainloop() #Will listen for events