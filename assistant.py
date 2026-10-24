#!/usr/bin/env python3
"""A safe, beginner-friendly Windows desktop assistant starter."""

from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import threading
import urllib.error
import urllib.request
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus, urlparse
import tkinter as tk
from tkinter import ttk

try:
    import speech_recognition as speech_recognition
except ImportError:
    speech_recognition = None

try:
    import pyttsx3
except ImportError:
    pyttsx3 = None


APP_DIR = Path(__file__).resolve().parent
NOTES_FILE = APP_DIR / "notes.txt"

# Only these executables can be launched. Add your own trusted app here if needed.
APP_EXECUTABLES = {
    "calculator": "calc.exe",
    "notepad": "notepad.exe",
    "paint": "mspaint.exe",
    "file_explorer": "explorer.exe",
    "task_manager": "taskmgr.exe",
}

APP_ALIASES = {
    "calculator": "calculator",
    "calc": "calculator",
    "notepad": "notepad",
    "text editor": "notepad",
    "paint": "paint",
    "microsoft paint": "paint",
    "file explorer": "file_explorer",
    "explorer": "file_explorer",
    "files": "file_explorer",
    "task manager": "task_manager",
    "settings": "settings",
    "windows settings": "settings",
}

BROWSER_ALIASES = {
    "browser": "default",
    "web browser": "default",
    "default browser": "default",
    "internet": "default",
    "chrome": "chrome",
    "google chrome": "chrome",
    "edge": "edge",
    "microsoft edge": "edge",
    "firefox": "firefox",
    "mozilla firefox": "firefox",
}

SITE_URLS = {
    "google": "https://www.google.com",
    "google.com": "https://www.google.com",
    "youtube": "https://www.youtube.com",
    "youtube.com": "https://www.youtube.com",
    "gmail": "https://mail.google.com",
    "gmail.com": "https://mail.google.com",
    "maps": "https://maps.google.com",
    "google maps": "https://maps.google.com",
    "wikipedia": "https://www.wikipedia.org",
    "wikipedia.org": "https://www.wikipedia.org",
    "github": "https://github.com",
    "github.com": "https://github.com",
    "spotify": "https://open.spotify.com",
    "reddit": "https://www.reddit.com",
    "linkedin": "https://www.linkedin.com",
    "netflix": "https://www.netflix.com",
    "amazon": "https://www.amazon.in",
    "chatgpt": "https://chatgpt.com",
}


@dataclass
class LocalResult:
    """The result of a command handled locally instead of by the AI API."""

    reply: str


def load_local_env() -> None:
    """Load simple KEY=VALUE lines from .env without replacing OS variables."""
    env_path = APP_DIR / ".env"
    if not env_path.exists():
        return

    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


def _clean_phrase(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold().strip()).rstrip(".!? ")


def _strip_politeness(value: str) -> str:
    value = re.sub(r"^(?:hey\s+jarvis[, ]+|jarvis[, ]+)", "", value.strip(), flags=re.I)
    while True:
        shortened = re.sub(
            r"^(?:please\s+|can\s+you\s+|could\s+you\s+|would\s+you\s+)",
            "",
            value,
            flags=re.I,
        )
        if shortened == value:
            return value.strip()
        value = shortened.strip()


def _try_http_url(value: str) -> str | None:
    """Accept only ordinary HTTP(S) URLs or domain-like text; reject other schemes."""
    candidate = value.strip()
    if not candidate or any(ch.isspace() for ch in candidate):
        return None

    if candidate.lower().startswith("www."):
        candidate = "https://" + candidate
    elif not re.match(r"^https?://", candidate, flags=re.I):
        if not re.fullmatch(r"[A-Za-z0-9.-]+(?::\d+)?(?:/[^\s]*)?", candidate):
            return None
        if "." not in candidate.split("/", 1)[0]:
            return None
        candidate = "https://" + candidate

    try:
        parsed = urlparse(candidate)
    except ValueError:
        return None
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc or not parsed.hostname:
        return None
    return candidate


def _open_url(url: str, description: str) -> LocalResult:
    try:
        webbrowser.open_new_tab(url)
        return LocalResult(f"Opening {description} in your default browser.")
    except Exception as exc:
        return LocalResult(f"I couldn't open the browser: {exc}")


def _browser_executable(browser: str) -> str | None:
    """Find a named Windows browser in common install locations."""
    if browser == "chrome":
        relative = Path("Google") / "Chrome" / "Application" / "chrome.exe"
        executable_name = "chrome.exe"
        roots = [os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"), os.environ.get("LOCALAPPDATA")]
    elif browser == "edge":
        relative = Path("Microsoft") / "Edge" / "Application" / "msedge.exe"
        executable_name = "msedge.exe"
        roots = [os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"), os.environ.get("LOCALAPPDATA")]
    else:
        relative = Path("Mozilla Firefox") / "firefox.exe"
        executable_name = "firefox.exe"
        roots = [os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"), os.environ.get("LOCALAPPDATA")]

    for root in roots:
        if root:
            candidate = Path(root) / relative
            if candidate.is_file():
                return str(candidate)
    return shutil.which(executable_name)


def _launch_browser(browser: str) -> LocalResult:
    if browser == "default":
        return _open_url("https://www.google.com", "your browser")
    if os.name != "nt":
        return LocalResult("Launching installed desktop browsers is supported by this Windows build.")

    executable = _browser_executable(browser)
    if not executable:
        label = {"chrome": "Google Chrome", "edge": "Microsoft Edge", "firefox": "Firefox"}.get(browser, browser)
        return LocalResult(f"I couldn't find {label}. Try ‘open browser’ to use your Windows default browser.")
    try:
        subprocess.Popen([executable], shell=False)
        label = {"chrome": "Google Chrome", "edge": "Microsoft Edge", "firefox": "Firefox"}.get(browser, browser)
        return LocalResult(f"Opening {label}.")
    except OSError as exc:
        return LocalResult(f"I couldn't launch that browser: {exc}")


def _launch_app(app_key: str) -> LocalResult:
    if os.name != "nt":
        return LocalResult("Opening local apps is supported by this Windows build.")

    if app_key == "settings":
        try:
            os.startfile("ms-settings:")  # type: ignore[attr-defined]
            return LocalResult("Opening Windows Settings.")
        except OSError as exc:
            return LocalResult(f"I couldn't open Windows Settings: {exc}")

    executable = APP_EXECUTABLES.get(app_key)
    if not executable:
        return LocalResult(f"There is no executable configured for ‘{app_key}’ yet.")
    try:
        subprocess.Popen([executable], shell=False)
        label = app_key.replace("_", " ").title()
        return LocalResult(f"Opening {label}.")
    except FileNotFoundError:
        return LocalResult(
            f"Windows couldn't find {executable}. It may not be installed, or its command may need a full path."
        )
    except OSError as exc:
        return LocalResult(f"I couldn't launch {app_key.replace('_', ' ')}: {exc}")


def handle_local_command(text: str) -> LocalResult | None:
    """Run a small set of safe local actions. Return None for general AI questions."""
    command = _strip_politeness(text)
    normalized = _clean_phrase(command)
    if not normalized:
        return LocalResult("I didn't catch that. Try typing a command or pressing Listen.")

    if normalized in {"help", "commands", "what can you do", "what can you do?"}:
        return LocalResult(
            "I can open Calculator, Notepad, Paint, File Explorer, Task Manager, or Windows Settings; "
            "open websites such as YouTube, Gmail, Google, and GitHub; search the web; tell the time/date; "
            "and save or show notes. Ask a general question for an AI answer after you configure an API key."
        )

    if normalized in {"hello", "hi", "hey", "good morning", "good afternoon", "good evening"}:
        return LocalResult("Hello! What would you like me to do?")

    if normalized in {"exit", "quit", "goodbye", "bye", "close assistant"}:
        return LocalResult("Goodbye! You can close this window whenever you're ready.")

    if normalized in {"time", "tell time", "what time is it", "what's the time", "what is the time"} or re.search(
        r"\b(?:what time is it|what is the time|what's the time|tell me the time|current time)\b", normalized
    ):
        return LocalResult(f"It is {datetime.now().strftime('%I:%M %p')}.")

    if normalized in {"date", "what is the date", "what's the date", "what day is it"} or re.search(
        r"\b(?:what is the date|what's the date|what day is it|today's date|current date)\b", normalized
    ):
        return LocalResult(f"Today is {datetime.now().strftime('%A, %B %d, %Y')}.")

    if normalized in {"show notes", "read notes", "list notes", "my notes"}:
        try:
            if not NOTES_FILE.exists():
                return LocalResult("You don't have any saved notes yet. Say ‘take a note’ followed by your note.")
            notes = NOTES_FILE.read_text(encoding="utf-8").strip()
            return LocalResult(notes or "Your notes file is empty.")
        except OSError as exc:
            return LocalResult(f"I couldn't read your notes: {exc}")

    note_match = re.match(
        r"^(?:take|write|save|add)\s+(?:a\s+)?note(?:\s+that)?\s*(?:[:,-]\s*)?(.+)$",
        command,
        flags=re.I,
    )
    if note_match:
        note = note_match.group(1).strip()
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            with NOTES_FILE.open("a", encoding="utf-8") as notes_file:
                notes_file.write(f"[{timestamp}] {note}\n")
            return LocalResult("Saved that note on this computer.")
        except OSError as exc:
            return LocalResult(f"I couldn't save your note: {exc}")

    search_match = re.match(
        r"^(?:search(?:\s+the\s+web)?(?:\s+for)?|google)\s+(.+)$",
        command,
        flags=re.I,
    )
    if search_match:
        query = search_match.group(1).strip().rstrip(".!?")
        if query:
            url = "https://www.google.com/search?q=" + quote_plus(query)
            return _open_url(url, f'a web search for “{query}”')

    open_match = re.match(r"^(?:open|launch|start|visit|go\s+to)\s+(.+)$", command, flags=re.I)
    if open_match:
        target = open_match.group(1).strip().rstrip(".!?")
        target = re.sub(r"\s+(?:please|now)$", "", target, flags=re.I).strip()
        target = re.sub(r"^(?:the|my)\s+", "", target, flags=re.I).strip()
        target = re.sub(r"^(?:website|webpage|site)\s+", "", target, flags=re.I).strip()
        target_lower = target.casefold().rstrip("/")

        if target_lower in SITE_URLS:
            return _open_url(SITE_URLS[target_lower], target)

        url = _try_http_url(target)
        if url:
            return _open_url(url, target)

        if target_lower in BROWSER_ALIASES:
            return _launch_browser(BROWSER_ALIASES[target_lower])

        if target_lower in APP_ALIASES:
            return _launch_app(APP_ALIASES[target_lower])

        supported = "Calculator, Notepad, Paint, File Explorer, Task Manager, Settings, or a website URL"
        return LocalResult(
            f"I don't have ‘{target}’ in my safe app list yet. I can open {supported}. "
            "You can add another trusted app in APP_EXECUTABLES and APP_ALIASES in assistant.py."
        )

    return None


def ask_ai(user_text: str, history: list[dict[str, str]]) -> str:
    """Send a text question to an optional OpenAI-compatible chat-completions API."""
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return (
            "I can run the local commands without an API key. To enable AI answers, copy .env.example to .env "
            "and add your OPENAI_API_KEY. An AI provider may charge for API use."
        )

    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/")
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    messages: list[dict[str, str]] = [
        {
            "role": "system",
            "content": (
                "You are Jarvis, a friendly and concise personal assistant. Answer clearly. "
                "You do not have access to the user's computer and must never claim you opened an app, "
                "changed a setting, or completed an action. Local actions are handled separately by the app."
            ),
        }
    ]
    messages.extend(history[-8:])
    messages.append({"role": "user", "content": user_text})
    body = json.dumps({"model": model, "messages": messages}).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=40) as response:
            result = json.loads(response.read().decode("utf-8"))
        content = result["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )
        answer = str(content).strip()
        return answer or "The AI provider returned an empty answer."
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        if len(detail) > 350:
            detail = detail[:350] + "…"
        return f"The AI provider returned HTTP {exc.code}. Check your API key, model, and base URL. {detail}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return f"I couldn't reach the AI service. Check your internet connection and API settings. ({exc})"
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        return f"The AI provider returned a response I couldn't understand. Check the model and API endpoint. ({exc})"


class SpeechOutput:
    """Speak replies on one worker thread so Tkinter remains responsive."""

    def __init__(self) -> None:
        self._queue: queue.Queue[str | None] = queue.Queue()
        self.available = pyttsx3 is not None
        if self.available:
            threading.Thread(target=self._worker, daemon=True, name="speech-output").start()

    def _worker(self) -> None:
        try:
            engine = pyttsx3.init()
        except Exception:
            self.available = False
            return
        while True:
            phrase = self._queue.get()
            if phrase is None:
                return
            try:
                engine.say(phrase)
                engine.runAndWait()
            except Exception:
                self.available = False

    def say(self, text: str) -> None:
        if self.available:
            self._queue.put(text)

    def stop(self) -> None:
        if self.available:
            self._queue.put(None)


class JarvisApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("J.A.R.V.I.S. — Personal Assistant")
        self.root.geometry("900x680")
        self.root.minsize(700, 520)
        self.root.configure(bg="#0b1020")
        self.busy = False
        self.ai_history: list[dict[str, str]] = []
        self.speech_output = SpeechOutput()
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self._append_message(
            "JARVIS",
            "Hello! I'm Jarvis, your Windows desktop assistant. Try ‘open Calculator’, ‘open YouTube’, "
            "‘search for …’, ‘what time is it?’, or ‘take a note …’. Click Listen to speak. "
            "Voice recognition uses an online service; see README.md for privacy details.",
            "assistant",
        )

    def _build_ui(self) -> None:
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        outer = tk.Frame(self.root, bg="#0b1020", padx=22, pady=18)
        outer.grid(row=0, column=0, sticky="nsew")
        outer.grid_columnconfigure(0, weight=1)
        outer.grid_rowconfigure(2, weight=1)

        header = tk.Frame(outer, bg="#0b1020")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        header.grid_columnconfigure(0, weight=1)
        tk.Label(
            header,
            text="J.A.R.V.I.S.",
            bg="#0b1020",
            fg="#67e8f9",
            font=("Segoe UI", 22, "bold"),
        ).grid(row=0, column=0, sticky="w")
        self.status_var = tk.StringVar(value="READY")
        tk.Label(
            header,
            textvariable=self.status_var,
            bg="#0b1020",
            fg="#86efac",
            font=("Segoe UI", 9, "bold"),
        ).grid(row=0, column=1, sticky="e", padx=(8, 0))

        tk.Label(
            outer,
            text="A small, safe starting point for your personal desktop assistant",
            bg="#0b1020",
            fg="#94a3b8",
            font=("Segoe UI", 10),
        ).grid(row=1, column=0, sticky="w", pady=(0, 12))

        chat_frame = tk.Frame(outer, bg="#111827", highlightbackground="#263247", highlightthickness=1)
        chat_frame.grid(row=2, column=0, sticky="nsew")
        chat_frame.grid_rowconfigure(0, weight=1)
        chat_frame.grid_columnconfigure(0, weight=1)
        self.chat = tk.Text(
            chat_frame,
            wrap="word",
            state="disabled",
            bg="#111827",
            fg="#e5e7eb",
            insertbackground="#e5e7eb",
            selectbackground="#164e63",
            relief="flat",
            borderwidth=0,
            padx=18,
            pady=16,
            font=("Segoe UI", 10),
            spacing1=2,
            spacing3=10,
        )
        self.chat.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(chat_frame, orient="vertical", command=self.chat.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.chat.configure(yscrollcommand=scroll.set)
        self.chat.tag_configure("user_label", foreground="#86efac", font=("Segoe UI", 10, "bold"))
        self.chat.tag_configure("assistant_label", foreground="#67e8f9", font=("Segoe UI", 10, "bold"))
        self.chat.tag_configure("message", foreground="#e5e7eb", font=("Segoe UI", 10))

        input_row = tk.Frame(outer, bg="#0b1020")
        input_row.grid(row=3, column=0, sticky="ew", pady=(14, 8))
        input_row.grid_columnconfigure(0, weight=1)
        self.entry = tk.Entry(
            input_row,
            bg="#172033",
            fg="#f8fafc",
            insertbackground="#f8fafc",
            relief="flat",
            font=("Segoe UI", 11),
            highlightthickness=1,
            highlightbackground="#334155",
            highlightcolor="#22d3ee",
        )
        self.entry.grid(row=0, column=0, sticky="ew", ipady=12, padx=(0, 8))
        self.entry.bind("<Return>", self._on_enter)
        self.entry.focus_set()

        self.listen_button = tk.Button(
            input_row,
            text="Listen",
            command=self.listen,
            bg="#1e293b",
            fg="#e2e8f0",
            activebackground="#334155",
            activeforeground="#ffffff",
            relief="flat",
            padx=16,
            pady=10,
            font=("Segoe UI", 10, "bold"),
            cursor="hand2",
        )
        self.listen_button.grid(row=0, column=1, padx=(0, 8))
        self.send_button = tk.Button(
            input_row,
            text="Send",
            command=self.send_message,
            bg="#0891b2",
            fg="#ffffff",
            activebackground="#0e7490",
            activeforeground="#ffffff",
            relief="flat",
            padx=20,
            pady=10,
            font=("Segoe UI", 10, "bold"),
            cursor="hand2",
        )
        self.send_button.grid(row=0, column=2)

        footer = tk.Frame(outer, bg="#0b1020")
        footer.grid(row=4, column=0, sticky="ew")
        self.speak_var = tk.BooleanVar(value=self.speech_output.available)
        self.speak_check = tk.Checkbutton(
            footer,
            text="Speak replies",
            variable=self.speak_var,
            bg="#0b1020",
            fg="#cbd5e1",
            activebackground="#0b1020",
            activeforeground="#ffffff",
            selectcolor="#172033",
            disabledforeground="#64748b",
            font=("Segoe UI", 9),
        )
        self.speak_check.pack(side="left")
        if not self.speech_output.available:
            self.speak_check.configure(state="disabled", text="Speech output unavailable (install pyttsx3)")
        tk.Label(
            footer,
            text="Local actions are allowlisted; no arbitrary shell commands are run.",
            bg="#0b1020",
            fg="#64748b",
            font=("Segoe UI", 9),
        ).pack(side="right")

    def _append_message(self, speaker: str, text: str, kind: str) -> None:
        self.chat.configure(state="normal")
        label_tag = "user_label" if kind == "user" else "assistant_label"
        self.chat.insert("end", f"{speaker}\n", label_tag)
        self.chat.insert("end", f"{text}\n\n", "message")
        self.chat.configure(state="disabled")
        self.chat.see("end")

    def _set_busy(self, busy: bool, status: str = "READY") -> None:
        self.busy = busy
        state = tk.DISABLED if busy else tk.NORMAL
        self.entry.configure(state=state)
        self.send_button.configure(state=state)
        self.listen_button.configure(state=state)
        self.status_var.set(status)
        if not busy:
            self.entry.focus_set()

    def _finish(self, reply: str) -> None:
        self._append_message("JARVIS", reply, "assistant")
        self._set_busy(False, "READY")
        if self.speak_var.get() and self.speech_output.available:
            self.speech_output.say(reply)

    def _on_enter(self, _event: tk.Event) -> str:
        self.send_message()
        return "break"

    def send_message(self) -> None:
        if self.busy:
            return
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, "end")
        self._append_message("YOU", text, "user")
        self._set_busy(True, "WORKING…")
        threading.Thread(target=self._run_text_request, args=(text,), daemon=True, name="assistant-request").start()

    def listen(self) -> None:
        if self.busy:
            return
        self._set_busy(True, "LISTENING…")
        threading.Thread(target=self._listen_and_process, daemon=True, name="assistant-microphone").start()

    def _listen_and_process(self) -> None:
        if speech_recognition is None:
            self.root.after(
                0,
                self._finish,
                "Voice input isn't installed. Install the requirements with `python -m pip install -r requirements.txt`, "
                "or type your request instead.",
            )
            return

        recognizer = speech_recognition.Recognizer()
        try:
            self.root.after(0, self.status_var.set, "LISTENING · speak now")
            with speech_recognition.Microphone() as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.4)
                audio = recognizer.listen(source, timeout=6, phrase_time_limit=10)
            language = os.environ.get("ASSISTANT_SPEECH_LANGUAGE", "en-IN")
            text = recognizer.recognize_google(audio, language=language)
        except speech_recognition.WaitTimeoutError:
            self.root.after(0, self._finish, "I didn't hear anything. Try again or type your request.")
            return
        except speech_recognition.UnknownValueError:
            self.root.after(0, self._finish, "I couldn't understand that. Please try again or type your request.")
            return
        except speech_recognition.RequestError as exc:
            self.root.after(
                0,
                self._finish,
                f"Online speech recognition failed. Check your internet connection. ({exc})",
            )
            return
        except Exception as exc:
            self.root.after(
                0,
                self._finish,
                "I couldn't access the microphone. Check Windows microphone permissions and install the audio "
                f"dependency from requirements.txt. ({exc})",
            )
            return

        self.root.after(0, self._append_message, "YOU", text, "user")
        self._run_text_request(text)

    def _run_text_request(self, text: str) -> None:
        try:
            local_result = handle_local_command(text)
            if local_result is not None:
                reply = local_result.reply
            else:
                has_api_key = bool(os.environ.get("OPENAI_API_KEY", "").strip())
                reply = ask_ai(text, self.ai_history)
                if has_api_key:
                    self.ai_history.extend(
                        [{"role": "user", "content": text}, {"role": "assistant", "content": reply}]
                    )
                    self.ai_history = self.ai_history[-12:]
        except Exception as exc:
            reply = f"Sorry, something went wrong while handling that request. ({exc})"
        self.root.after(0, self._finish, reply)

    def close(self) -> None:
        self.speech_output.stop()
        self.root.destroy()


def main() -> None:
    load_local_env()
    root = tk.Tk()
    JarvisApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
