# Ana: macOS-friendly personal voice assistant.

from __future__ import annotations
import eel
import speedtest
import gc
import os
import re
import psutil
import subprocess
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
import xml.etree.ElementTree as ET
import traceback
from datetime import datetime
from pathlib import Path

import requests
import speech_recognition as sr

APP_DIRECTORY = Path(__file__).resolve().parent
NOTES_FILE = APP_DIRECTORY / "notes.txt"
NEWS_RSS_URL = (
    "https://news.google.com/rss/headlines/section/topic/WORLD"
    "?hl=en-IN&gl=IN&ceid=IN:en"
)
HTTP_HEADERS = {"User-Agent": "AnaVoiceAssistant/2.0 (macOS)"}

# Web / web folder compatibility check (Case-sensitivity fix)
web_folder = APP_DIRECTORY / "Web" if (APP_DIRECTORY / "Web").exists() else APP_DIRECTORY / "web"
eel.init(str(web_folder))

def log_to_ui(text: str, msg_type: str = "system"):
    """HTML UI par text aur log bhejta hai."""
    try:
        eel.add_log(text, msg_type)
    except Exception:
        pass

LANGUAGES = {
    "arabic": "ar", "bengali": "bn", "chinese": "zh-CN", "english": "en",
    "french": "fr", "german": "de", "gujarati": "gu", "hindi": "hi",
    "italian": "it", "japanese": "ja", "korean": "ko", "marathi": "mr",
    "portuguese": "pt", "punjabi": "pa", "russian": "ru", "spanish": "es",
    "tamil": "ta", "telugu": "te", "urdu": "ur",
}

recognizer = sr.Recognizer()
recognizer.dynamic_energy_threshold = False
recognizer.energy_threshold = 300
recognizer.pause_threshold = 0.6


def available_voice() -> str | None:
    preferred = os.environ.get("Ana_VOICE", "Kiyara")
    try:
        result = subprocess.run(
            ["say", "-v", "?"], capture_output=True, text=True, check=False
        )
        installed = {line.split()[0] for line in result.stdout.splitlines() if line.split()}
        if preferred in installed:
            return preferred
        for voice in ("Isha (Premium)", "Samantha", "Voice 1", "Kiyara (Premium)", "Tessa", "Victoria"):
            if voice in installed:
                return voice
    except OSError:
        pass
    return None

VOICE = available_voice()

def speak(message: object) -> None:
    text = str(message).strip()
    if not text:
        return
    print(f"Ana: {text}")
    log_to_ui(f"Ana: {text}", "Ana")
    command = ["say", "-r", "175"]
    if VOICE:
        command.extend(["-v", VOICE])
    try:
        subprocess.run(command + [text], check=False)
    except OSError as exc:
        print(f"[Speech error] {exc}")


def listen(prompt: str | None = None) -> str:
    """Fast listening - continuous listening with detailed error logging."""
    if prompt:
        speak(prompt)
    
    global recognizer

    try:
        with sr.Microphone() as source:
            print("Listening...")
            log_to_ui("Listening...", "system")
            # Dynamic energy adjustment for ambient noise
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=6)

        # Google Speech to Text
        words = recognizer.recognize_google(audio)
        print(f"You: {words}")
        log_to_ui(f"You: {words}", "user")
        gc.collect()
        return words.lower().strip()

    except sr.WaitTimeoutError:
        # Jab user input na de ya kuch na bole
        speak("I could not understand. Please try again.")

    except sr.UnknownValueError:
        # Jab user bole par aawaz samajh na aaye
        speak("I could not understand. Please try again.")

    except Exception as exc:
        print(f"[Mic Error Details]: {exc}")
        traceback.print_exc()
        log_to_ui("Microphone error detected.", "system")
    
    gc.collect()
    return ""


# Functions - perform which tasks.
def fetch_headlines(limit: int = 5) -> list[str]:
    """Google News RSS se requested number of English headlines laata hai."""
    # Request mein header aur timeout dena 403/block aur endless waiting se bachata hai.
    request = urllib.request.Request(NEWS_RSS_URL, headers=HTTP_HEADERS)
    with urllib.request.urlopen(request, timeout=10) as response:
        root = ET.fromstring(response.read())
    # RSS ke har `item` se sirf title text nikaal kar list return hoti hai.
    return [
        title.strip()
        for item in root.findall(".//item")[:limit]
        if (title := item.findtext("title"))
    ]


def read_news() -> None:
    """Current world news English mein bolta hai."""
    speak("Here are the latest world headlines in English.")
    try:
        headlines = fetch_headlines()
        if not headlines:
            raise LookupError("RSS feed was empty")
        for number, headline in enumerate(headlines, start=1):
            # Final ` - Publisher` part hata dete hain, kyunki wo actual headline nahi hota.
            headline = headline.rsplit(" - ", 1)[0]
            speak(f"News number {number}. {headline}")
            time.sleep(0.35)
    except Exception as exc:
        # Network/RSS error terminal mein detailed print hota hai, user ko simple spoken reply milta hai.
        print(f"[News error] {exc}")
        speak("I could not fetch the news right now.")
        
def open_application(app_name: str = "") -> None:
    """App ko direct open karta hai, name na milne par poochhta hai."""
    if not app_name:
        app_name = listen("Which app should I open?")
    
    if app_name:
        clean_name = app_name.replace("app", "").replace("open", "").strip().title()
        
        # AppleScript se foreground activation
        script = f'tell application "{clean_name}" to activate'
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=False)
        
        if result.returncode == 0:
            speak(f"Opening {clean_name}.")
        else:
            # Fallback open command
            res_fallback = subprocess.run(["open", "-a", clean_name], check=False)
            if res_fallback.returncode == 0:
                speak(f"Opening {clean_name}.")
            else:
                speak(f"I could not open {clean_name}.")

def close_application(app_name: str = "") -> None:
    """App ko direct quit/close karta hai (Command+Q), name na milne par poochhta hai."""
    if not app_name:
        app_name = listen("Which app should I close?")
    
    if app_name:
        clean_name = app_name.replace("app", "").replace("close", "").replace("quit", "").strip().title()
        try:
            script = f'tell application "{clean_name}" to quit'
            result = subprocess.run(["osascript", "-e", script], check=False)
            
            if result.returncode == 0:
                speak(f"Closing {clean_name}.")
            else:
                speak(f"I could not close {clean_name}.")
        except Exception as exc:
            print(f"[Close App Error] {exc}")
            speak(f"I could not close {clean_name}.")
            
def open_whatsapp() -> None:
    """WhatsApp ko force-focus aur foreground launch karta hai."""
    try:
        # Step 1: Tell macOS to directly activate WhatsApp via AppleScript
        script = 'tell application "WhatsApp" to activate'
        res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=False)      
        # Step 2: Check if AppleScript succeeded
        if res.returncode == 0:
            speak("Opening WhatsApp.")
            return
        # Step 3: Fallback using open command with -b (Bundle Identifier)
        res_bundle = subprocess.run(["open", "-b", "net.whatsapp.WhatsApp"], check=False)
        if res_bundle.returncode == 0:
            speak("Opening WhatsApp.")
            return
        # Step 4: Final fallback using application path
        subprocess.run(["open", "/Applications/WhatsApp.app"], check=False)
        speak("Opening WhatsApp.")
    except Exception as exc:
        print(f"[WhatsApp Launch Error] {exc}")
        speak("I could not open WhatsApp.")
        
def close_whatsapp() -> None:
    """WhatsApp ko safely quit/close karta hai."""
    try:
        # AppleScript se application ko safely Quit karne ki command
        script = 'tell application "WhatsApp" to quit'
        subprocess.run(["osascript", "-e", script], check=False)
        speak("Closing WhatsApp.")
    except Exception as exc:
        print(f"[Close WhatsApp Error] {exc}")
        speak("I could not close WhatsApp.")

def get_internet_speed() -> None:
    """Download aur Upload speed calculate karke bolta hai."""
    speak("Testing internet speed. Please wait a moment.")
    try:
        st = speedtest.Speedtest()
        # Best server dhundne ke liye
        st.get_best_server()
        # Speeds ko bits per second se Mbps mein convert kar rahe hain
        download_speed = st.download() / 1_000_000
        upload_speed = st.upload() / 1_000_000
        result_text = f"Download speed is {download_speed:.1f} Mbps, and upload speed is {upload_speed:.1f} Mbps."
        speak(result_text)
    except Exception as exc:
        print(f"[Speedtest Error] {exc}")
        speak("I could not measure the internet speed right now.")
        
def get_system_info() -> None:
    """macOS version, RAM usage, aur Disk space ki details bolta hai."""
    try:
        # macOS Version
        os_version = subprocess.run(
            ["sw_vers", "-productVersion"], capture_output=True, text=True, check=False
        ).stdout.strip()
        # RAM Usage (RAM Details)
        ram = psutil.virtual_memory()
        ram_total = round(ram.total / (1024 ** 3), 1)  # GB mein
        ram_used_percent = ram.percent
        # Disk Storage Details
        disk = psutil.disk_usage("/")
        disk_free = round(disk.free / (1024 ** 3), 1)  # Free GB
        disk_total = round(disk.total / (1024 ** 3), 1)  # Total GB
        speak(
            f"You are running macOS version {os_version}. "
            f"Total RAM is {ram_total} GB with {ram_used_percent} percent used. "
            f"Free disk space is {disk_free} GB out of {disk_total} GB."
        )
    except Exception as exc:
        print(f"[System Info Error] {exc}")
        speak("I could not fetch complete system details right now.")

def save_note() -> None:
    """Voice note ko date/time ke saath notes.txt mein append karta hai."""
    note = listen("What should I write?")
    if note:
        # Timestamp se pata rahega ki note kab save hua tha.
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        with NOTES_FILE.open("a", encoding="utf-8") as file:
            file.write(f"[{timestamp}] {note}\n")
        speak("Your note has been saved.")


def get_weather() -> None:
    """City poochhkar wttr.in se current weather laata hai."""
    location = listen("Which city?")
    if not location:
        return
    try:
        # `quote()` city name mein spaces ko URL-safe banata hai; `%C+%t` = condition + temperature.
        url = f"https://wttr.in/{urllib.parse.quote(location)}?format=%C+%t"
        response = requests.get(url, headers=HTTP_HEADERS, timeout=10)
        response.raise_for_status()
        speak(f"The weather in {location} is {response.text.strip()}.")
    except requests.RequestException as exc:
        # Internet, timeout ya weather server failure ko safely handle karta hai.
        print(f"[Weather error] {exc}")
        speak("I could not get the weather right now.")


def translate(command: str) -> None:
    """`translate hello to Hindi` jaisa direct command ya voice prompts handle karta hai."""
    # Direct command mein text aur target language regex se nikalte hain.
    match = re.match(r"^translate\s+(.+?)\s+(?:to|into)\s+(.+)$", command, re.I)
    if match:
        text, requested_language = match.groups()
    else:
        # Sirf `translate` bola ho to baaki details assistant poochhta hai.
        text = listen("What should I translate?")
        requested_language = listen("Which language?")
    # `Hindi language` aur `Hindi`—dono se same `hi` code milta hai.
    language = LANGUAGES.get(re.sub(r"\blanguage\b", "", requested_language).strip().lower())
    if not text or not language:
        speak("Please name a supported language, for example Hindi, Spanish, or French.")
        return
    try:
        # Import yahan lazy rakha hai, taaki translation package issue ho to app startup fail na ho.
        from deep_translator import GoogleTranslator

        result = GoogleTranslator(source="auto", target=language).translate(text)
        speak(f"The translation is: {result}")
    except Exception as exc:
        # Translation service/network ka error safely user-friendly message mein convert hota hai.
        print(f"[Translation error] {exc}")
        speak("I could not translate that right now.")


# Active timers ko track karne ke liye global dictionary
active_timers = {}
timer_counter = 0

def set_timer() -> None:
    """User se minutes poochhkar timer start karta hai aur active list mein save karta hai."""
    global timer_counter
    answer = listen("How many minutes?")
    match = re.search(r"\d+", answer)
    if not match:
        speak("Please say the number of minutes.")
        return
    minutes = int(match.group())
    if minutes <= 0:
        speak("The timer must be at least one minute.")
        return
    timer_counter += 1
    t_id = timer_counter
    stop_event = threading.Event()

    def alarm():
        # Countdown loop jo har 1 sec mein check karega ki cancel toh nahi hua
        end_time = time.time() + (minutes * 60)
        while time.time() < end_time:
            if stop_event.is_set():
                return
            time.sleep(1)
        # Alarm sound & message
        subprocess.run(["afplay", "/System/Library/Sounds/Glass.aiff"], check=False)
        speak(f"Timer number {t_id} for {minutes} minutes is complete.")
        active_timers.pop(t_id, None)
    thread = threading.Thread(target=alarm, daemon=True)
    active_timers[t_id] = {
        "minutes": minutes,
        "thread": thread,
        "stop_event": stop_event,
        "start_time": time.time()
    }
    thread.start()
    speak(f"Timer number {t_id} set for {minutes} minutes.")

def show_timers() -> None:
    """Active timers ki list aur bacha hua time batata hai."""
    if not active_timers:
        speak("There are no active timers.")
        return
    speak(f"You have {len(active_timers)} active timer.")
    for t_id, data in list(active_timers.items()):
        elapsed = time.time() - data["start_time"]
        remaining = max(0, int((data["minutes"] * 60 - elapsed) / 60))
        speak(f"Timer number {t_id} has about {remaining} minutes remaining.")

def delete_timer(command: str = "") -> None:
    """Kisi specific timer ko cancel/delete karta hai."""
    if not active_timers:
        speak("There are no active timers to cancel.")
        return
    # Command mein se number dhoondna (jaise "delete timer 1")
    match = re.search(r"\d+", command)
    if match:
        t_id = int(match.group())
    else:
        # Agar number nahi bola toh poochhna
        if len(active_timers) == 1:
            t_id = list(active_timers.keys())[0]
        else:
            ans = listen("Which timer number should I cancel?")
            match_ans = re.search(r"\d+", ans)
            if match_ans:
                t_id = int(match_ans.group())
            else:
                speak("Timer number not recognized.")
                return
    if t_id in active_timers:
        active_timers[t_id]["stop_event"].set()  # Thread stop karna
        del active_timers[t_id]                  # List se delete karna
        speak(f"Timer number {t_id} has been cancelled.")
    else:
        speak(f"Timer number {t_id} was not found.")

def system_status() -> None:
    """Battery percentage aur charging/battery-power status bolta hai."""
    battery = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, check=False)
    battery_line = next((line.strip() for line in battery.stdout.splitlines() if "%" in line), "")
    
    if battery_line:
        match = re.search(r"(\d+)%", battery_line)
        if match:
            percentage = match.group(1)
            # Battery line mein "charging" ho to charging, nahi toh battery power report karte hain
            status = "charging" if "charging" in battery_line.lower() else "on battery power"
            speak(f"Battery is at {percentage} percent and is {status}.")
            return
    speak("I could not read the battery status.")

def system_cpu_status() -> None:
    """CPU percentage aur core details bolta hai."""
    try:
        # interval=1 sec dene se current actual CPU usage calculate hota hai
        cpu_usage = psutil.cpu_percent(interval=1)
        cpu_cores = psutil.cpu_count(logical=False)  # Physical cores count
        
        speak(f"Current CPU usage is at {cpu_usage} percent across {cpu_cores} cores.")
    except Exception as exc:
        print(f"[CPU Status Error] {exc}")
        speak("I could not read the CPU status right now.")
        
def read_notes() -> None:
    """Read saved notes from notes.txt file."""
    if not NOTES_FILE.exists() or NOTES_FILE.stat().st_size == 0:
        speak("You have no saved notes.")
        return
    try:
        with NOTES_FILE.open("r", encoding="utf-8") as file:
            lines = file.readlines()
            speak(f"You have {len(lines)} saved notes.")
            for line in lines[-3:]:  # Sirf aakhri 3 notes padhega
                speak(line.strip())
    except Exception as exc:
        print(f"[Read Notes Error] {exc}")
        speak("I could not read your notes.")
        
def open_website(site_name: str) -> None:
    """Directly open popular websites."""
    # Corrected Code:
    sites = {
        "google": "https://www.google.com",
        "github": "https://www.github.com",
        "chatgpt": "https://chatgpt.com",
        "reddit": "https://www.reddit.com",
        "linkedin": "https://www.linkedin.com",
        "youtube": "https://www.youtube.com"
    }
    url = sites.get(site_name.lower())
    if url:
        webbrowser.open(url)
        speak(f"Opening {site_name}.")
    else:
        speak(f"Opening {site_name}.")
        webbrowser.open(f"https://www.{site_name}.com")
        
def set_volume(command: str) -> None:
    """Set volume level percentage directly."""
    match = re.search(r"\d+", command)
    if match:
        level = int(match.group())
        if 0 <= level <= 100:
            subprocess.run(["osascript", "-e", f"set volume output volume {level}"], check=False)
            speak(f"Volume set to {level} percent.")
        else:
            speak("Volume level must be between 0 and 100.")
    else:
        speak("Please specify a volume percentage.")
    
def read_clipboard() -> None:
    """Read the current content from macOS clipboard."""
    try:
        clipboard_text = subprocess.run(["pbpaste"], capture_output=True, text=True, check=False).stdout.strip()
        if clipboard_text:
            speak(f"Your clipboard contains: {clipboard_text}")
        else:
            speak("Your clipboard is empty.")
    except Exception as exc:
        print(f"[Clipboard Error] {exc}")
        speak("I could not read the clipboard.")




def respond(command: str) -> bool:
    # Lowercase karne se `NEWS`, `News`, aur `news`—teeno match ho sakte hain.
    command = command.lower().strip()
    if not command:
        return True

    # Neeche har `elif` ek voice-command keyword check karta hai aur related feature chalaata hai.
    if "what is your name" in command or "who are you" in command or "who r u" in command:
        speak("I am Ana, your personal assistant.")
    
    # SHOW TIMERS
    elif "show timer" in command or "check timer" in command or "list timer" in command or "how many timers" in command:
        show_timers()

    # DELETE / CANCEL TIMER
    elif "delete timer" in command or "cancel timer" in command or "stop timer" in command or "remove timer" in command:
        delete_timer(command)

    # SET TIMER
    elif "set a timer" in command or "timer" in command or "remind me" in command:
        set_timer()
        
    # News
    elif "news" in command or "headlines" in command:
        read_news()
        
    # Weather
    elif "weather" in command or "temperature" in command or "vedar" in command:
        get_weather()
        
    # Translator
    elif "translate" in command:
        translate(command)
        
    # Write new Note
    elif "write a note" in command or "take a note" in command:
        save_note()
    
     # Time and Date
    elif "time" in command:
        speak(datetime.now().strftime("It is %I:%M %p."))
    elif "date" in command or "day is it" in command:
        speak(datetime.now().strftime("Today is %A, %d %B %Y."))
        
    # CPU ke bare me jankari
    elif "cpu" in command or "processor" in command or "cpu usage" in command:
        system_cpu_status()
    
    # battery Status
    elif command.startswith("battery") or command.startswith("check battery") or "power status" in command:
        system_status()
    
    # Volume Controller   
    elif "mute" in command:
        # AppleScript macOS ke system audio ko mute karta hai.
        subprocess.run(["osascript", "-e", "set volume output muted true"], check=False)
        speak("Volume muted.")
    elif "unmute" in command:
        # AppleScript mute state ko hata kar audio wapas on karta hai.
        subprocess.run(["osascript", "-e", "set volume output muted false"], check=False)
        speak("Volume restored.")
    elif "volume up" in command:
        # Current Mac volume ko 10 points increase karta hai.
        subprocess.run(["osascript", "-e", "set volume output volume ((output volume of (get volume settings)) + 10)"], check=False)
        speak("Volume increased.")
    elif "volume down" in command:
        # Current Mac volume ko 10 points decrease karta hai.
        subprocess.run(["osascript", "-e", "set volume output volume ((output volume of (get volume settings)) - 10)"], check=False)
        speak("Volume decreased.")
        
    # Searching.....
    elif command.startswith("search"):
        # `search for Python` se `search for` hata kar asli search query nikaalte hain.
        query = re.sub(r"^search(?: for)?\s*", "", command).strip() or listen("What should I search for?")
        if query:
            # `quote()` spaces/special characters ko safe Google URL mein convert karta hai.
            webbrowser.open(f"https://www.google.com/search?q={urllib.parse.quote(query)}")
            speak(f"Searching for {query}.")
            
    # find Location
    elif command.startswith("where is") or command.startswith("find location"):
        # Location naam ko voice command se nikaal kar Apple Maps mein kholte hain.
        place = re.sub(r"^(where is|find location)\s*", "", command).strip() or listen("Which location?")
        if place:
            webbrowser.open(f"https://maps.apple.com/?q={urllib.parse.quote(place)}")
            speak(f"Showing {place} in Maps.")
            
    # Play anything on Youtube
    elif command.startswith("play"):
        # Song ko direct control nahi karte; YouTube search results browser mein open karte hain.
        song = command.removeprefix("play ").strip()
        webbrowser.open(f"https://www.youtube.com/results?search_query={urllib.parse.quote(song)}")
        speak(f"Here are YouTube results for {song}.")
        
    # take a Screenshot
    elif "take a screenshot" in command or "capture screen" in command:
        # Date/time waala unique filename har screenshot ko alag rakhta hai.
        filename = APP_DIRECTORY / f"screenshot-{datetime.now():%Y%m%d-%H%M%S}.png"
        # `screencapture` macOS ka built-in screenshot command hai.
        subprocess.run(["screencapture", str(filename)], check=False)
        speak("Screenshot saved.")
        
    # lock System
    elif "lock screen" in command or "lock system" in command or "lock mac" in command:
        speak("Locking the screen.")
        # Modern macOS ke liye direct AppleScript lock command
        subprocess.run(["osascript", "-e", 'tell application "System Events" to key code 12 using {command down, control down}'], check=False)
        
    # Internet Speed Check
    elif "internet speed" in command or "speed test" in command or "download speed" in command:
        get_internet_speed()
        
    # System ke bare me jankari
    elif "system info" in command or "system details" in command or "about system" in command or "about mac" in command:
        get_system_info()
        
    # RAM and Memory ki jankari
    elif "ram" in command or "memory" in command:
        try:
            ram = psutil.virtual_memory()
            speak(f"RAM usage is currently at {ram.percent} percent.")
        except Exception:
            speak("Could not read RAM details.")
            
    # Storage ke bare me jankari
    elif "storage" in command or "disk space" in command or "free space" in command:
        try:
            disk = psutil.disk_usage("/")
            disk_free = round(disk.free / (1024 ** 3), 1)
            speak(f"You have {disk_free} gigabytes of free storage left.")
        except Exception:
            speak("Could not read disk space.")

    # Saved Notes padhne ke liye
    elif "read notes" in command or "show notes" in command or "my notes" in command:
        read_notes()

    # Clipboard text padhne ke liye
    elif "read clipboard" in command or "what is copied" in command:
        read_clipboard()
        
    # 1. WhatsApp Specific Actions (सबसे पहले)
    elif "close whatsapp" in command or "quit whatsapp" in command:
        close_whatsapp()
    elif "open whatsapp" in command or "whatsapp" in command:
        open_whatsapp()

    # 2. Specific Websites (General Open से पहले)
    elif "open youtube" in command:
        open_website("youtube")
    elif "open google" in command:
        open_website("google")
    elif "open github" in command:
        open_website("github")
    elif "open chatgpt" in command:
        open_website("chatgpt")
    elif "open linkedin" in command:
        open_website("linkedin")

    # 3. General Open and Close (सबसे बाद में / Last में)
    elif command.startswith("open"):
        app_name = command.removeprefix("open").replace("app", "").strip()
        open_application(app_name)
    elif command.startswith("close") or command.startswith("quit"):
        app_name = command.removeprefix("close").removeprefix("quit").replace("app", "").strip()
        close_application(app_name)
        
    # Volume Percentage Set karne ke liye (e.g., "set volume to 50")
    elif "set volume" in command or "change volume" in command:
        set_volume(command)
      
    # Exit / Terminate  
    elif command in {"exit", "quit", "goodbye", "close"}:
        speak("Goodbye, Sir")
        # 1. Floating Window Close Call
        try:
            eel.close_window()
        except Exception:
            pass
        time.sleep(0.3)
        # 2. Hard Kill Process (Mac Mic indicator band ho jayega)
        os._exit(0)
        return False
    return True



def assistant_loop():
    """Continuous main loop."""
    time.sleep(0.5)
    speak("Hello! I am listening. How can I help you?")
    while True:
        command = listen()
        if command:
            if not respond(command):
                break
        time.sleep(0.1)

def main() -> None:
    threading.Thread(target=assistant_loop, daemon=True).start()
    try:
        eel.start('index.html', size=(380, 520), port=8000, mode='chrome')
    except EnvironmentError:
        eel.start('index.html', size=(380, 520), port=8000)

if __name__ == "__main__":
    main()