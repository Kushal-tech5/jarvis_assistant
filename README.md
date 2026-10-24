# J.A.R.V.I.S. — Windows Personal Assistant Starter

A small Python desktop assistant that can open a safe list of Windows apps and websites, search the web, save notes, tell the time/date, and answer general questions through an optional AI API. It includes a simple chat window, optional speech input, and spoken replies.

This is a useful **starter project**, not a full Siri/Jarvis replacement. It only performs the local actions explicitly listed in `assistant.py`; it does not control every app or run arbitrary computer commands.

## What it can do

- Open Calculator, Notepad, Paint, File Explorer, Task Manager, and Windows Settings.
- Open Google, YouTube, Gmail, Maps, Wikipedia, GitHub, Spotify, Reddit, LinkedIn, Netflix, Amazon, ChatGPT, or an ordinary `https://` website.
- Search Google from a spoken or typed request.
- Tell the current time/date and save/read simple notes in `notes.txt`.
- Answer general questions when you configure an OpenAI-compatible API key.
- Listen through your microphone and speak replies when the optional voice packages are installed.

## Requirements

- Windows 10/11
- Python 3.10 or newer (the standard Python installer includes Tkinter)
- A microphone for voice input; internet for online speech recognition and AI answers

## Install and run

Open **Command Prompt** in this folder and run:

```bat
py -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python assistant.py
```

You can also double-click `run.bat` after installing the requirements.

If the microphone button reports an audio/PyAudio error, try installing the audio extra again:

```bat
python -m pip install "SpeechRecognition[audio]"
```

Typing commands works even if voice input is unavailable.

## Enable AI answers (optional)

1. Copy `.env.example` to a new file named `.env` in this folder.
2. Add your provider's API key and choose a model supported by that provider:

```env
OPENAI_API_KEY=your-key-here
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
ASSISTANT_SPEECH_LANGUAGE=en-IN
```

The API key is optional for app opening, web search, time/date, and notes. The code uses an OpenAI-compatible `/chat/completions` endpoint; other compatible providers can be used by changing the base URL and model. API use may cost money according to your provider's terms. Keep `.env` private and never share it.

## Example commands

- `Open Calculator`
- `Could you open Notepad, please?`
- `Open YouTube`
- `Open https://example.com`
- `Search for beginner Python projects`
- `What time is it?`
- `Take a note: call the dentist tomorrow`
- `Show notes`
- `What is machine learning?` (requires an API key for a generated answer)

The first version understands English command phrases. You can change the voice-recognition language with `ASSISTANT_SPEECH_LANGUAGE` in `.env`, but the local command phrases themselves are currently English.

## Add another trusted Windows app

Add a stable app key and executable to `APP_EXECUTABLES`, then map the phrase you want to say in `APP_ALIASES`. For example, if VS Code is on your PATH:

```python
# In APP_EXECUTABLES:
"vscode": "Code.exe",

# In APP_ALIASES:
"vs code": "vscode",
"visual studio code": "vscode",
```

If it is not on PATH, use the full executable path, for example:

```python
"vscode": r"C:\Users\YourName\AppData\Local\Programs\Microsoft VS Code\Code.exe",
```

The assistant launches apps using a fixed allowlist and `shell=False`; it does **not** pass user text to Command Prompt or PowerShell.

## Privacy and limitations

- Voice input calls `SpeechRecognition`'s Google speech-recognition service. When you press **Listen**, the recorded audio is sent to that online service for transcription. Use typed input if you do not want to send audio.
- If you configure AI answers, the text of general questions and recent AI chat messages is sent to the API provider you selected. The app does not send your local notes to the AI automatically.
- Speech output uses installed system voices through `pyttsx3` and is intended to run locally.
- It does not read email, change system settings beyond opening the Settings window, send messages, manage files, or control arbitrary desktop apps. Add integrations deliberately and review permissions before expanding it.
