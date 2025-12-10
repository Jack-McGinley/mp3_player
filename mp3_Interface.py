from tkinter import *
import os
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "hide"
import pygame

#Create function to read songs from music folder
def songs():
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

    folder = "music" #<-- rename folder to folder containing mp3 files

    if not os.path.isdir(folder):
        print(f"Folder '{folder}' not found")
        return

    mp3_files = [file for file in os.listdir(folder) if file.endswith(".mp3")]

    if not mp3_files:
        print("No .mp3 files found!")
    
    return mp3_files

#Create a play_music function to map to play_song button
def play_music(folder, song_name):
    """
    Uses the filepath to open the folder 
    containing the mp3 files and uses
    pygame mixer to load mp3 file and play the song.
    """

    file_path = os.path.join(folder, song_name)

    if not os.path.exists(file_path):
        print("File not found")
        return

    pygame.mixer.music.load(file_path)
    pygame.mixer.music.play()

#Create a function to play selected song in playlist
def play_song():
    """
    Selects the song currently selected
    in the windows listbox and passes the song name
    to the play_music function to load and play the track.
    """

    try:
        #Selects currently highlighted song
        song_title = playlist.get(playlist.curselection())
    except TclError:
        print("No song selected!")
        return
    
    print(f"Currently Playing: {song_title}")

    #Call play_music function
    play_music(folder="music", song_name=song_title)

#Create a function to pause the currently playing song
def pause_song():
    pygame.mixer.music.pause()
    print("Music Paused")

#Create a function to resume the currently playing song
def resume_song():
    pygame.mixer.music.unpause()
    print("Music Resumed")

#Create a function to stop playing the currently selected song
def stop_song():
    pygame.mixer.music.stop()
    print("Music Stopped")

#========Create Window Interface====================

# windows = serves as a container to hold or contain widgets
window = Tk() #Create instance of a window: 'Tk'
#Set size of window using 'geometry' method
window.geometry("240x240")
#Set title of the window using 'title' method
window.title("Music Player") 

#Convert .png to 'Photo Image' 
icon = PhotoImage(file='music_note_icon.png')
#Set icon image of window using 'iconphoto' function
window.iconphoto(True, icon)

#Set background color of window using 'config' method
window.config(background="black")

#label = an area widget that holds text and/or image within a window
#Create a label using constructor: 'Label'
label = Label(window,#pass window as argument to label that is within window
              text="Music Player",
              font=("Courier New", 40, 'bold'),
              fg='#00FF00', #Color of text
              bg='black', #Color of label background
)
#Add label to window using 'pack' method
label.pack()

#Create a listbox to contain music selection, create instance: 'Listbox'
playlist = Listbox(window,
                   bg='white',
                   font=('Courier New', 12),
                   width=40)
#Add playlist listbox to window using 'pack' method
playlist.pack()
#Call songs function to return list of available songs
mp3_files = songs()
#Use insert method to add items to listbox
for song in mp3_files:
    playlist.insert(END, song)
#Adjust size of listbox dynamically
playlist.config(height=playlist.size())
#Create play button to play selected song from listbox playlist
playButton = Button(window, text='Play', command=play_song)
#Configure Buttom Visuals
playButton.config(font=('Courier New', 20),
                    bg='#c0c6c7',
                    activebackground='#99a3a3',
                )
playButton.pack(pady=10) #Add button to window, and create space between top and bottom

#Create a frame to hold action buttons
frame = Frame(window) #Instance 'Frame' passed our window
#Configure visals for frame 
frame.config(background='black')
frame.pack(pady=5) #Add frame to window

#Create a button to pause song
pauseButton = Button(frame, text='Pause', command=pause_song)
pauseButton.config(font=('Courier New', 20),
                    bg='#c0c6c7',
                    activebackground='#99a3a3',
                )
pauseButton.pack(side=LEFT, padx=5) #Add button to window

#Create a button to unpause song
resumeButton = Button(frame, text='Resume', command=resume_song)
resumeButton.config(font=('Courier New', 20),
                    bg='#c0c6c7',
                    activebackground='#99a3a3',
                )
resumeButton.pack(side=LEFT, padx=5) #Add button to window

#Create a button to stop song
stopButton = Button(frame, text='Stop', command=stop_song)
stopButton.config(font=('Courier New', 20),
                    bg='#c0c6c7',
                    activebackground='#99a3a3',
                )
stopButton.pack(side=LEFT, padx=5) #Add button to window

#Create a Button to close the program
quitButton = Button(window, text="Quit", command=quit)
quitButton.config(font=('Courier New', 20),
                    bg='#c0c6c7',
                    activebackground='#99a3a3',
                )
quitButton.pack(pady=5) #Add button to window

#Display window
window.mainloop() #Will listen for events