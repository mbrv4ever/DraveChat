# -*- coding: utf-8 -*-
"""DraveChat - een lokale AI-chat-helper van Dravenlock (PyQt6, GEEN Ollama).

Draait een klein taalmodel volledig zelf via llama-cpp-python: je laadt een
GGUF-modelbestand direct in de app - geen aparte server nodig. Met een eigen
"Draven"-persoonlijkheid, geheugen (feiten + gesprek) en een KENNIS-DATABASE
(RAG): notities die de app erbij zoekt zodat een klein model tóch slim over
jouw dingen antwoordt.

Eerste keer: klik 'Klein model downloaden' (of kies zelf een .gguf-bestand).
Toegankelijk: A- / A+ knoppen voor grotere tekst.

Tweetalig NL/EN, portable (alles in de app-map). Donationware.
"""
import json
import locale
import os
import queue
import re
import sys
import threading

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap, QTextCursor
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QTextBrowser, QLineEdit, QPushButton,
                             QLabel, QMessageBox, QProgressBar, QDialog,
                             QListWidget, QInputDialog, QFileDialog, QCheckBox,
                             QComboBox, QSlider)

# standaard klein model om te downloaden (klein + snel + weinig RAM)
DEFAULT_REPO = "bartowski/Llama-3.2-3B-Instruct-GGUF"
DEFAULT_FILE = "Llama-3.2-3B-Instruct-Q4_K_M.gguf"

# instelbare zoekmachines ({q} = de zoekterm). Startpage is standaard.
SEARCH_PRESETS = {
    "startpage": ("Startpage", "https://www.startpage.com/sp/search?query={q}"),
    "duckduckgo": ("DuckDuckGo", "https://html.duckduckgo.com/html/?q={q}"),
    "brave": ("Brave Search", "https://search.brave.com/search?q={q}"),
}
DEFAULT_SEARCH = SEARCH_PRESETS["startpage"][1]

# Sommige pc's hebben een oude AMD ROCm- of NVIDIA CUDA-omgevingsvariabele die
# naar een niet-bestaande map wijst. llama-cpp-python probeert die map bij het
# laden aan de DLL-zoekpaden toe te voegen en crasht dan (WinError 3). Ruim
# zulke kapotte variabelen op vóór de engine geladen wordt.
for _var in ("HIP_PATH", "HIP_PATH_57", "CUDA_PATH", "ROCM_PATH"):
    _p = os.environ.get(_var)
    if _p and not os.path.isdir(os.path.join(_p, "bin")):
        os.environ.pop(_var, None)


try:
    from uitspraak import uitspraak as _uitspraak
except Exception:
    try:
        from .uitspraak import uitspraak as _uitspraak
    except Exception:  # zonder uitspraak.py gewoon de tekst zelf
        def _uitspraak(t, taal="nl"):
            return t


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def cache_dir():
    d = os.path.join(app_dir(), "cache")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return d


def models_dir():
    d = os.path.join(cache_dir(), "models")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return d


def _lang():
    try:
        loc = (locale.getdefaultlocale()[0] or "")
    except Exception:
        loc = ""
    return "nl" if loc.lower().startswith("nl") else "en"


LANG = _lang()
TX = {
    "title": {"nl": "DraveChat - je eigen AI-helper",
              "en": "DraveChat - your own AI helper"},
    "you": {"nl": "Jij", "en": "You"},
    "draven": {"nl": "Draven", "en": "Draven"},
    "send": {"nl": "Verstuur", "en": "Send"},
    "placeholder": {"nl": "Typ je bericht...  (Enter = versturen)",
                    "en": "Type your message...  (Enter to send)"},
    "choose": {"nl": "Model kiezen (.gguf)", "en": "Choose model (.gguf)"},
    "download": {"nl": "Klein model downloaden", "en": "Download small model"},
    "new": {"nl": "Nieuw gesprek", "en": "New chat"},
    "donate": {"nl": "♥ Doneren", "en": "♥ Donate"},
    "info": {"nl": "Info", "en": "Info"},
    "memory": {"nl": "🧠 Geheugen", "en": "🧠 Memory"},
    "knowledge": {"nl": "📚 Kennis", "en": "📚 Knowledge"},
    "speak": {"nl": "🔊 Stem", "en": "🔊 Voice"},
    "online": {"nl": "🌐 Online zoeken", "en": "🌐 Web search"},
    "searching": {"nl": "🌐 Zoeken op internet (Startpage)...",
                  "en": "🌐 Searching the web (Startpage)..."},
    "voice_set": {"nl": "🔊 Steminstellingen", "en": "🔊 Voice settings"},
    "voice_title": {"nl": "Steminstellingen", "en": "Voice settings"},
    "voice_choice": {"nl": "Stem:", "en": "Voice:"},
    "voice_speed": {"nl": "Snelheid", "en": "Speed"},
    "voice_pitch": {"nl": "Toonhoogte (pitch)", "en": "Pitch"},
    "voice_test": {"nl": "Test stem", "en": "Test voice"},
    "voice_load": {"nl": "Stem laden/downloaden", "en": "Load/download voice"},
    "voice_loading": {"nl": "Stemmodel laden (1e keer: downloaden)...",
                      "en": "Loading voice model (first time: download)..."},
    "voice_ready": {"nl": "Stem klaar (%d stemmen).",
                    "en": "Voice ready (%d voices)."},
    "voice_fail": {"nl": "Stem laden mislukt (zie cache/error.log).",
                   "en": "Voice load failed (see cache/error.log)."},
    "test_line": {"nl": "Hallo, ik ben Draven, je eigen assistent.",
                  "en": "Hello, I am Draven, your own assistant."},
    "search_set": {"nl": "🔍 Zoekmachine", "en": "🔍 Search engine"},
    "search_title": {"nl": "Zoekmachine kiezen", "en": "Choose search engine"},
    "search_pick": {"nl": "Kies of vul je eigen zoek-URL in ({q} = zoekterm):",
                    "en": "Pick or enter your own search URL ({q} = query):"},
    "search_custom": {"nl": "Eigen URL (met {q})", "en": "Custom URL (with {q})"},
    "no_model": {"nl": "Nog geen model geladen", "en": "No model loaded"},
    "loading": {"nl": "Model laden...", "en": "Loading model..."},
    "downloading": {"nl": "Model downloaden (kan even duren)...",
                    "en": "Downloading model (may take a while)..."},
    "ready": {"nl": "Model klaar: %s", "en": "Model ready: %s"},
    "load_fail": {"nl": "Model laden mislukt: %s", "en": "Load failed: %s"},
    "need_model": {"nl": "Laad eerst een model (knop rechtsboven).",
                   "en": "Load a model first (top-right button)."},
    "no_llama": {
        "nl": "Module 'gpt4all' ontbreekt. Sluit af en start via "
              "Start-DraveChat.bat (die installeert de engine).",
        "en": "Module 'gpt4all' missing. Close and launch via Start-DraveChat.bat "
              "(it installs the engine)."},
    "no_hub": {"nl": "Module 'huggingface_hub' ontbreekt (zit in de Start-bat).",
               "en": "Module 'huggingface_hub' missing (in the Start bat)."},
    "engine_err": {
        "nl": "De AI-engine (gpt4all) kon niet laden. Sluit DraveChat en draai "
              "eenmalig Start-DraveChat.bat om de engine te installeren, en "
              "probeer opnieuw.\n\nDe volledige foutmelding staat in "
              "cache\\error.log.",
        "en": "The AI engine (gpt4all) could not load. Close DraveChat and run "
              "Start-DraveChat.bat once to install the engine, then try again.\n\n"
              "Full error is in cache\\error.log."},
    "dl_fail": {"nl": "Downloaden mislukt: %s", "en": "Download failed: %s"},
    "thinking": {"nl": "Draven denkt...", "en": "Draven is thinking..."},
    "mem_title": {"nl": "Wat Draven onthoudt", "en": "What Draven remembers"},
    "mem_hint": {"nl": "Feiten die Draven bij elk gesprek meeneemt:",
                 "en": "Facts Draven brings into every chat:"},
    "know_title": {"nl": "Kennis-database", "en": "Knowledge base"},
    "know_hint": {"nl": "Notities die de app erbij zoekt bij een vraag "
                        "(over jouw projecten, feiten, uitleg):",
                  "en": "Notes the app looks up for a question "
                        "(your projects, facts, explanations):"},
    "add": {"nl": "Toevoegen", "en": "Add"},
    "delete": {"nl": "Verwijderen", "en": "Remove"},
    "mem_new": {"nl": "Wat moet Draven onthouden?",
                "en": "What should Draven remember?"},
    "know_new": {"nl": "Nieuwe kennisnotitie:", "en": "New knowledge note:"},
    "close": {"nl": "Sluiten", "en": "Close"},
    "remembered": {"nl": "Onthouden ✔  (%s)", "en": "Remembered ✔  (%s)"},
    "greet": {
        "nl": "Hoi! Ik ben Draven, je lokale AI-helper - volledig op je eigen pc, "
              "zonder Ollama. Laad een model (knop rechtsboven) en stel me een "
              "vraag.",
        "en": "Hi! I'm Draven, your local AI helper - fully on your own pc, no "
              "Ollama. Load a model (top-right) and ask me anything."},
    "mem_tip": {"nl": "Tip: '/onthoud <feit>' onthoudt iets; 📚 voor kennis.",
                "en": "Tip: '/remember <fact>' remembers; 📚 for knowledge."},
    "info_txt": {
        "nl": "DraveChat draait een klein AI-model lokaal via llama-cpp-python - "
              "geen Ollama, geen server, je data blijft op je pc. Met geheugen en "
              "een kennis-database (RAG) zodat het slim over jouw dingen "
              "antwoordt.\n\nEerste keer: 'Klein model downloaden' of kies een "
              ".gguf-bestand.\n\nDonationware - https://paypal.me/roger076 - "
              "service@dravenlock.nl",
        "en": "DraveChat runs a small AI model locally via llama-cpp-python - no "
              "Ollama, no server, your data stays on your pc. With memory and a "
              "knowledge base (RAG) so it answers smartly about your things.\n\n"
              "First time: 'Download small model' or pick a .gguf file.\n\n"
              "Donationware - https://paypal.me/roger076 - service@dravenlock.nl"},
}


def T(k):
    d = TX.get(k, {})
    return d.get(LANG) or d.get("en") or k


SYS_PROMPT = {
    "nl": "Je bent Draven, een behulpzame, beknopte AI-assistent van Dravenlock. "
          "Antwoord kort en feitelijk in de taal van de gebruiker. Verzin geen "
          "details die niet gegeven of gevraagd zijn. Stel geen tegenvragen "
          "tenzij dat echt nodig is. Weet je iets niet, zeg dat kort.",
    "en": "You are Draven, a helpful, concise AI assistant of Dravenlock. "
          "Answer briefly and factually in the user's language. Do not invent "
          "details that were not given or asked. Do not ask counter-questions "
          "unless truly needed. If you don't know, say so briefly.",
}
DONATE = "https://paypal.me/roger076"


# --------------------------------------------------------------- werkthreads
class LoadWorker(QThread):
    done = pyqtSignal(object, str)      # (llm | None, foutmelding)

    def __init__(self, path):
        super().__init__()
        self.path = path

    def run(self):
        import traceback
        try:
            from gpt4all import GPT4All
        except Exception:
            self.done.emit(None, "IMPORT\n" + traceback.format_exc())
            return
        try:
            m = GPT4All(os.path.basename(self.path),
                        model_path=os.path.dirname(self.path),
                        allow_download=False, device="cpu",
                        n_ctx=4096, verbose=False)
            self.done.emit(m, "")
        except Exception:
            self.done.emit(None, "LOAD\n" + traceback.format_exc())


class DownloadWorker(QThread):
    done = pyqtSignal(str, str)         # (pad | "", foutmelding)

    def run(self):
        try:
            from huggingface_hub import hf_hub_download
        except Exception:
            self.done.emit("", "__nohub__")
            return
        try:
            hf_hub_download(repo_id=DEFAULT_REPO, filename=DEFAULT_FILE,
                            local_dir=models_dir())
            # gebruik altijd het concrete bestand in de modelmap (Windows-veilig)
            concrete = os.path.join(models_dir(), DEFAULT_FILE)
            self.done.emit(concrete, "")
        except Exception as e:
            self.done.emit("", str(e))


class ChatWorker(QThread):
    token = pyqtSignal(str)
    done = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, model, prompt):
        super().__init__()
        self.model = model
        self.prompt = prompt
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            for tok in self.model.generate(self.prompt, max_tokens=400,
                                           temp=0.35, top_p=0.9,
                                           repeat_penalty=1.2, streaming=True):
                if self._stop:
                    break
                if tok:
                    self.token.emit(tok)
            self.done.emit()
        except Exception as e:
            self.error.emit(str(e))


class SearchWorker(QThread):
    """Privacy-zoeken via de ingestelde zoekmachine; geeft snippets terug."""
    done = pyqtSignal(list)

    def __init__(self, query, url_template):
        super().__init__()
        self.query = query
        self.url_template = url_template or DEFAULT_SEARCH

    def run(self):
        import urllib.request
        import urllib.parse
        import html as _h
        out = []
        try:
            q = urllib.parse.quote(self.query)
            url = self.url_template.replace("{q}", q)
            req = urllib.request.Request(url, headers={
                "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                               "AppleWebKit/537.36 (KHTML, like Gecko) "
                               "Chrome/122.0 Safari/537.36"),
                "Accept-Language": "nl,en;q=0.8"})
            page = urllib.request.urlopen(req, timeout=12).read().decode(
                "utf-8", "replace")

            def clean(s):
                s = re.sub(r"(?is)<(script|style).*?</\1>", " ", s)
                s = re.sub(r"<[^>]+>", " ", s)
                return re.sub(r"\s+", " ", _h.unescape(s)).strip()

            # probeer per zoekmachine bekende snippet-klassen, anders generiek
            patterns = [
                r'<p[^>]*class="[^"]*description[^"]*"[^>]*>(.*?)</p>',
                r'<a[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>',
                r'<div[^>]*class="[^"]*snippet[^"]*"[^>]*>(.*?)</div>',
                r'<p[^>]*>(.*?)</p>',
            ]
            for pat in patterns:
                found = [clean(x) for x in re.findall(pat, page, re.S)]
                found = [f for f in found if len(f) > 40]
                if found:
                    for f in found[:5]:
                        out.append(("", f))
                    break
        except Exception:
            pass
        self.done.emit(out)


class TtsEngine:
    """Neuvoice-wrapper (ONNX, on-device). Downloadt het model bij 1e gebruik."""
    def __init__(self):
        self._tts = None
        self.sample_rate = 24000
        self.voices = []
        self.ready = False
        self.last_error = ""

    def ensure_ready(self):
        if self.ready and self._tts is not None:
            return True
        try:
            import neuvoice  # noqa: F401
        except Exception:
            if not getattr(sys, "frozen", False):
                import subprocess
                for pkg in ("onnxruntime", "neuvoice"):
                    try:
                        __import__(pkg)
                    except Exception:
                        try:
                            subprocess.run(
                                [sys.executable, "-m", "pip", "install",
                                 "--only-binary=:all:", pkg], check=False)
                        except Exception:
                            pass
        try:
            from neuvoice import TTS
            self._tts = TTS(auto_download=True)
            self.sample_rate = int(getattr(self._tts, "sample_rate", 24000))
            self.voices = list(self._tts.voice_style_names)
            self.ready = True
            self.last_error = ""
            return True
        except Exception as e:
            self.last_error = str(e)
            self.ready = False
            return False

    def pick(self, name):
        if not self.voices:
            return name or ""
        return name if name in self.voices else ("Leon" if "Leon" in self.voices else self.voices[0])

    def synth(self, text, voice, speed, lang):
        import numpy as np
        style = self._tts.get_voice_style(self.pick(voice))
        wav, _dur = self._tts.synthesize(_uitspraak(text, lang), voice_style=style,
                                         total_steps=8, speed=float(speed),
                                         lang=lang)
        arr = np.asarray(wav, dtype="float32").squeeze()
        return np.clip(arr, -1.0, 1.0)


class LoadTtsWorker(QThread):
    done = pyqtSignal(bool, list)

    def __init__(self, tts):
        super().__init__()
        self.tts = tts

    def run(self):
        ok = self.tts.ensure_ready()
        self.done.emit(ok, self.tts.voices if ok else [])


class SpeakWorker(QThread):
    """Synthetiseert met neuvoice en speelt af. Pitch via afspeel-rate,
    tempo gecompenseerd zodat de snelheid natuurlijk blijft."""
    def __init__(self, tts, text, voice, speed, pitch, lang):
        super().__init__()
        self.tts = tts
        self.text = text
        self.voice = voice
        self.speed = speed
        self.pitch = pitch
        self.lang = lang

    def run(self):
        try:
            if not self.tts.ensure_ready():
                return
            import wave
            import tempfile
            pitch = max(0.7, min(1.4, float(self.pitch)))
            gen_speed = max(0.5, min(1.8, float(self.speed) / pitch))
            arr = self.tts.synth(self.text, self.voice, gen_speed, self.lang)
            pcm = (arr * 32767.0).astype("<i2")
            fr = int(self.tts.sample_rate * pitch)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
                path = tf.name
            with wave.open(path, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(fr)
                w.writeframes(pcm.tobytes())
            if os.name == "nt":
                import winsound
                winsound.PlaySound(None, winsound.SND_PURGE)
                winsound.PlaySound(path, winsound.SND_FILENAME)
            else:
                try:
                    import sounddevice as sd
                    import numpy as np
                    sd.play(np.frombuffer(pcm, dtype="<i2"), fr)
                    sd.wait()
                except Exception:
                    pass
            try:
                os.unlink(path)
            except Exception:
                pass
        except Exception:
            pass


class SpeakEngine:
    """Spreekt zinnen na elkaar uit via een wachtrij, zodat de stem de
    binnenkomende tekst op de voet volgt (geen wachten op het hele antwoord)."""
    def __init__(self, tts):
        self.tts = tts
        self.voice = ""
        self.speed = 1.0
        self.pitch = 1.0
        self.lang = "nl"
        self._q = queue.Queue()
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._loop, daemon=True)
        self._t.start()

    def configure(self, voice, speed, pitch, lang):
        self.voice = voice
        self.speed = float(speed)
        self.pitch = float(pitch)
        self.lang = lang

    def say(self, text):
        text = (text or "").strip()
        if text:
            self._q.put(text)

    def clear(self):
        try:
            while True:
                self._q.get_nowait()
        except queue.Empty:
            pass
        if os.name == "nt":
            try:
                import winsound
                winsound.PlaySound(None, winsound.SND_PURGE)
            except Exception:
                pass

    def _loop(self):
        while not self._stop.is_set():
            try:
                text = self._q.get(timeout=0.2)
            except queue.Empty:
                continue
            self._speak_one(text)

    def _speak_one(self, text):
        try:
            if not self.tts.ensure_ready():
                return
            import wave
            import tempfile
            pitch = max(0.7, min(1.4, self.pitch))
            gen_speed = max(0.5, min(1.8, self.speed / pitch))
            arr = self.tts.synth(text, self.voice, gen_speed, self.lang)
            pcm = (arr * 32767.0).astype("<i2")
            fr = int(self.tts.sample_rate * pitch)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
                path = tf.name
            with wave.open(path, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(fr)
                w.writeframes(pcm.tobytes())
            if os.name == "nt":
                import winsound
                winsound.PlaySound(path, winsound.SND_FILENAME)
            else:
                try:
                    import sounddevice as sd
                    import numpy as np
                    sd.play(np.frombuffer(pcm, dtype="<i2"), fr)
                    sd.wait()
                except Exception:
                    pass
            try:
                os.unlink(path)
            except Exception:
                pass
        except Exception:
            pass


# --------------------------------------------------------------- hoofdvenster
class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.model = None
        self.session = None
        self.worker = None
        self.loader = None
        self.downloader = None
        self.searcher = None
        self.tts = TtsEngine()
        self.tts_loader = None
        self.speaker = SpeakEngine(self.tts)
        self._say_buffer = ""
        self._pending_text = ""
        self._ctx = []
        self.cur = ""
        self.busy = False
        self.settings = self._load_settings()
        self.memory = self._load_list("memory.json")
        self.knowledge = self._load_list("knowledge.json")
        self.messages = self._load_history()
        self.scale = float(self.settings.get("scale", 1.25))

        self.setWindowTitle(T("title"))
        self.resize(900, 740)
        ic = os.path.join(app_dir(), "assets", "icon.ico")
        if os.path.exists(ic):
            self.setWindowIcon(QIcon(ic))
        self._build()
        self._apply_style()
        self._restore_or_greet()
        # bestaand model automatisch laden (opgeslagen pad, anders standaard in map)
        mp = self.settings.get("model_path", "")
        if not (mp and os.path.exists(mp)):
            cand = os.path.join(models_dir(), DEFAULT_FILE)
            mp = cand if os.path.exists(cand) else ""
        if mp and os.path.exists(mp):
            self._load_model(mp)
        else:
            self._set_status(T("no_model"))

    # ---------- opslag ----------
    def _settings_path(self):
        return os.path.join(cache_dir(), "settings.json")

    def _load_settings(self):
        d = {"model_path": "", "scale": 1.25, "speak": False, "online": False,
             "voice": "", "voice_speed": 1.0, "voice_pitch": 1.0,
             "search_url": DEFAULT_SEARCH, "search_name": "Startpage"}
        try:
            with open(self._settings_path(), "r", encoding="utf-8") as f:
                d.update(json.load(f))
        except Exception:
            pass
        return d

    def _save_settings(self):
        try:
            self.settings["scale"] = self.scale
            with open(self._settings_path(), "w", encoding="utf-8") as f:
                json.dump(self.settings, f)
        except Exception:
            pass

    def _load_list(self, name):
        try:
            with open(os.path.join(cache_dir(), name), "r",
                      encoding="utf-8") as f:
                return [str(x) for x in json.load(f) if str(x).strip()]
        except Exception:
            return []

    def _save_list(self, name, lst):
        try:
            with open(os.path.join(cache_dir(), name), "w",
                      encoding="utf-8") as f:
                json.dump(lst, f)
        except Exception:
            pass

    def _load_history(self):
        try:
            with open(os.path.join(cache_dir(), "history.json"), "r",
                      encoding="utf-8") as f:
                data = json.load(f)
            return [m for m in data if m.get("role") in ("user", "assistant")]
        except Exception:
            return []

    def _save_history(self):
        try:
            with open(os.path.join(cache_dir(), "history.json"), "w",
                      encoding="utf-8") as f:
                json.dump(self.messages[-40:], f)
        except Exception:
            pass

    # ---------- kennis / geheugen -> systeemprompt ----------
    def _retrieve(self, query, k=3):
        q = set(w for w in re.findall(r"\w+", query.lower()) if len(w) > 3)
        if not q:
            return []
        scored = []
        for note in self.knowledge:
            ws = set(w for w in re.findall(r"\w+", note.lower()) if len(w) > 3)
            sc = len(q & ws)
            if sc > 0:
                scored.append((sc, note))
        scored.sort(key=lambda t: t[0], reverse=True)
        return [n for _, n in scored[:k]]

    def _system(self, query=""):
        parts = [SYS_PROMPT.get(LANG, SYS_PROMPT["en"])]
        if self.memory:
            hdr = ("Wat je over de gebruiker onthoudt:" if LANG == "nl"
                   else "What you remember about the user:")
            parts.append(hdr + "\n" + "\n".join("- " + m for m in self.memory))
        hits = self._retrieve(query)
        if hits:
            hdr = ("Relevante kennis uit de database (gebruik als het klopt):"
                   if LANG == "nl" else
                   "Relevant knowledge from the database (use if correct):")
            parts.append(hdr + "\n" + "\n".join("- " + h for h in hits))
        return "\n\n".join(parts)

    # ---------- UI ----------
    def _build(self):
        cen = QWidget()
        self.setCentralWidget(cen)
        lay = QVBoxLayout(cen)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        top = QHBoxLayout()
        logo = QLabel()
        lp = os.path.join(app_dir(), "assets", "logo_t.png")
        if os.path.exists(lp):
            logo.setPixmap(QPixmap(lp).scaled(
                40, 40, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
        top.addWidget(logo)
        title = QLabel("DraveChat")
        title.setObjectName("title")
        top.addWidget(title)
        top.addStretch(1)
        self.choose_btn = QPushButton(T("choose"))
        self.choose_btn.clicked.connect(self._choose_model)
        top.addWidget(self.choose_btn)
        self.dl_btn = QPushButton(T("download"))
        self.dl_btn.clicked.connect(self._download_model)
        top.addWidget(self.dl_btn)
        lay.addLayout(top)

        self.status = QLabel(T("no_model"))
        self.status.setObjectName("status")
        lay.addWidget(self.status)

        opts = QHBoxLayout()
        self.speak_box = QCheckBox(T("speak"))
        self.speak_box.setChecked(bool(self.settings.get("speak", False)))
        self.speak_box.stateChanged.connect(self._save_opts)
        opts.addWidget(self.speak_box)
        self.online_box = QCheckBox(T("online"))
        self.online_box.setChecked(bool(self.settings.get("online", False)))
        self.online_box.stateChanged.connect(self._save_opts)
        opts.addWidget(self.online_box)
        vs = QPushButton(T("voice_set"))
        vs.clicked.connect(self.open_voice_settings)
        opts.addWidget(vs)
        ss = QPushButton(T("search_set"))
        ss.clicked.connect(self.open_search_settings)
        opts.addWidget(ss)
        opts.addStretch(1)
        lay.addLayout(opts)

        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(True)
        lay.addWidget(self.view, 1)

        self.prog = QProgressBar()
        self.prog.setRange(0, 0)
        self.prog.hide()
        lay.addWidget(self.prog)

        bottom = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText(T("placeholder"))
        self.input.returnPressed.connect(self._send)
        bottom.addWidget(self.input, 1)
        self.send_btn = QPushButton(T("send"))
        self.send_btn.clicked.connect(self._send)
        bottom.addWidget(self.send_btn)
        lay.addLayout(bottom)

        br = QHBoxLayout()
        for label, fn in ((T("new"), self._new_chat),
                          (T("memory"), self.open_memory),
                          (T("knowledge"), self.open_knowledge)):
            b = QPushButton(label)
            b.clicked.connect(fn)
            br.addWidget(b)
        b_small = QPushButton("A-")
        b_small.clicked.connect(lambda: self._set_scale(-0.1))
        br.addWidget(b_small)
        b_big = QPushButton("A+")
        b_big.clicked.connect(lambda: self._set_scale(0.1))
        br.addWidget(b_big)
        br.addStretch(1)
        b_don = QPushButton(T("donate"))
        b_don.clicked.connect(lambda: self._open(DONATE))
        br.addWidget(b_don)
        b_info = QPushButton(T("info"))
        b_info.clicked.connect(self._info)
        br.addWidget(b_info)
        lay.addLayout(br)

    def _apply_style(self):
        s = self.scale

        def px(n):
            return int(n * s)
        self.setStyleSheet("""
            QMainWindow, QWidget { background:#16131f; color:#e8e6f0; }
            QLabel { color:#cfc7e6; font-size:%dpx; }
            QLabel#title { color:#b59cff; font-size:%dpx; font-weight:bold; }
            QLabel#status { font-size:%dpx; font-weight:bold; color:#9b90c0; }
            QTextBrowser { background:#0e0c16; border:1px solid #4a3d66;
                border-radius:10px; padding:12px; font-size:%dpx; }
            QLineEdit { background:#0e0c16; color:#e8e6f0;
                border:1px solid #4a3d66; border-radius:8px;
                padding:%dpx; font-size:%dpx; }
            QPushButton { background:#2a2440; color:#efeaff;
                border:1px solid #5a4d86; border-radius:8px;
                padding:%dpx %dpx; font-weight:bold; font-size:%dpx; }
            QPushButton:hover { background:#463a6e; }
            QProgressBar { border:1px solid #4a3d66; border-radius:6px;
                background:#0e0c16; text-align:center; color:#e8e6f0;
                font-size:%dpx; }
            QProgressBar::chunk { background:#7F77DD; border-radius:6px; }
            QCheckBox { color:#cfc7e6; font-size:%dpx; }
            QComboBox { background:#0e0c16; color:#e8e6f0;
                border:1px solid #4a3d66; border-radius:8px;
                padding:%dpx; font-size:%dpx; }
        """ % (px(15), px(25), px(15), px(17), px(8), px(16),
               px(8), px(14), px(15), px(13), px(15), px(6), px(15)))
        f = self.view.font()
        f.setPointSizeF(11 * s)
        self.view.setFont(f)

    def _set_scale(self, delta):
        self.scale = max(0.8, min(2.4, self.scale + delta))
        self._save_settings()
        self._apply_style()

    def _save_opts(self):
        self.settings["speak"] = self.speak_box.isChecked()
        self.settings["online"] = self.online_box.isChecked()
        self._save_settings()
        if not self.speak_box.isChecked():
            self.speaker.clear()

    # ---------- steminstellingen ----------
    def open_voice_settings(self):
        dlg = QDialog(self)
        dlg.setWindowTitle(T("voice_title"))
        dlg.setStyleSheet(self.styleSheet())
        dlg.resize(480, 380)
        lay = QVBoxLayout(dlg)
        stat = QLabel("")

        lay.addWidget(QLabel(T("voice_choice")))
        combo = QComboBox()

        def fill():
            combo.clear()
            combo.addItems(self.tts.voices or [])
            cur = self.settings.get("voice", "")
            if cur:
                combo.setCurrentText(cur)
        fill()
        lay.addWidget(combo)

        loadb = QPushButton(T("voice_load"))

        def do_load():
            stat.setText(T("voice_loading"))
            loadb.setEnabled(False)
            self.tts_loader = LoadTtsWorker(self.tts)

            def ld_done(ok, voices):
                loadb.setEnabled(True)
                if ok:
                    stat.setText(T("voice_ready") % len(voices))
                    fill()
                else:
                    stat.setText(T("voice_fail"))
                    try:
                        with open(os.path.join(cache_dir(), "error.log"), "w",
                                  encoding="utf-8") as f:
                            f.write(self.tts.last_error)
                    except Exception:
                        pass
            self.tts_loader.done.connect(ld_done)
            self.tts_loader.start()
        loadb.clicked.connect(do_load)
        lay.addWidget(loadb)

        lay.addWidget(QLabel(T("voice_speed")))
        sp = QSlider(Qt.Orientation.Horizontal)
        sp.setRange(70, 140)
        sp.setValue(int(float(self.settings.get("voice_speed", 1.0)) * 100))
        lay.addWidget(sp)

        lay.addWidget(QLabel(T("voice_pitch")))
        pit = QSlider(Qt.Orientation.Horizontal)
        pit.setRange(70, 140)
        pit.setValue(int(float(self.settings.get("voice_pitch", 1.0)) * 100))
        lay.addWidget(pit)

        lay.addWidget(stat)

        def save_vals():
            self.settings["voice"] = combo.currentText()
            self.settings["voice_speed"] = sp.value() / 100.0
            self.settings["voice_pitch"] = pit.value() / 100.0
            self._save_settings()

        def test():
            save_vals()
            self.speaker.configure(self.settings.get("voice", ""),
                                   self.settings["voice_speed"],
                                   self.settings["voice_pitch"], LANG)
            self.speaker.clear()
            self.speaker.say(T("test_line"))

        row = QHBoxLayout()
        tb = QPushButton(T("voice_test"))
        tb.clicked.connect(test)
        row.addWidget(tb)
        cb = QPushButton(T("close"))
        cb.clicked.connect(lambda: (save_vals(), dlg.accept()))
        row.addWidget(cb)
        lay.addLayout(row)
        dlg.exec()
        save_vals()

    def open_search_settings(self):
        dlg = QDialog(self)
        dlg.setWindowTitle(T("search_title"))
        dlg.setStyleSheet(self.styleSheet())
        dlg.resize(560, 220)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(T("search_pick")))
        keys = list(SEARCH_PRESETS.keys())
        combo = QComboBox()
        for k in keys:
            combo.addItem(SEARCH_PRESETS[k][0])
        combo.addItem(T("search_custom"))
        urlbox = QLineEdit(self.settings.get("search_url", DEFAULT_SEARCH))
        cur = self.settings.get("search_url", DEFAULT_SEARCH)
        sel = len(keys)
        for i, k in enumerate(keys):
            if SEARCH_PRESETS[k][1] == cur:
                sel = i
                break
        combo.setCurrentIndex(sel)

        def on_pick(i):
            if i < len(keys):
                urlbox.setText(SEARCH_PRESETS[keys[i]][1])
        combo.currentIndexChanged.connect(on_pick)
        lay.addWidget(combo)
        lay.addWidget(urlbox)

        def save():
            u = urlbox.text().strip()
            if "{q}" not in u:
                u = DEFAULT_SEARCH
            self.settings["search_url"] = u
            i = combo.currentIndex()
            self.settings["search_name"] = (SEARCH_PRESETS[keys[i]][0]
                                            if i < len(keys) else "Eigen")
            self._save_settings()

        row = QHBoxLayout()
        cb = QPushButton(T("close"))
        cb.clicked.connect(lambda: (save(), dlg.accept()))
        row.addWidget(cb)
        lay.addLayout(row)
        dlg.exec()
        save()

    # ---------- chatweergave ----------
    def _append_html(self, html):
        self.view.append(html)
        self.view.ensureCursorVisible()

    def _greet(self):
        self._append_html("<i style='color:#9b90c0'>%s</i>" % T("greet"))
        self._append_html("<i style='color:#6f6690'>%s</i>" % T("mem_tip"))

    def _bubble(self, who, color, text):
        safe = (text.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace("\n", "<br>"))
        self._append_html("<b style='color:%s'>%s:</b> %s" % (color, who, safe))

    def _restore_or_greet(self):
        if self.messages:
            for m in self.messages:
                if m["role"] == "user":
                    self._bubble(T("you"), "#8fd0ff", m["content"])
                else:
                    self._bubble(T("draven"), "#b59cff", m["content"])
        else:
            self._greet()

    def _set_status(self, txt):
        self.status.setText(txt)

    # ---------- model laden / kiezen / downloaden ----------
    def _choose_model(self):
        path, _ = QFileDialog.getOpenFileName(
            self, T("choose"), models_dir(), "GGUF (*.gguf)")
        if path:
            self._load_model(path)

    def _download_model(self):
        self.dl_btn.setEnabled(False)
        self.choose_btn.setEnabled(False)
        self._set_status(T("downloading"))
        self.prog.show()
        self.downloader = DownloadWorker()
        self.downloader.done.connect(self._download_done)
        self.downloader.start()

    def _download_done(self, path, err):
        self.prog.hide()
        self.dl_btn.setEnabled(True)
        self.choose_btn.setEnabled(True)
        if err == "__nohub__":
            QMessageBox.information(self, "DraveChat", T("no_hub"))
            self._set_status(T("no_model"))
            return
        if not path:
            self._set_status(T("dl_fail") % err)
            return
        self._load_model(path)

    def _load_model(self, path):
        self._set_status(T("loading"))
        self.prog.show()
        self.loader = LoadWorker(path)
        self.loader.done.connect(lambda llm, e, p=path: self._load_done(llm, e, p))
        self.loader.start()

    def _load_done(self, llm, err, path):
        self.prog.hide()
        if llm is None:
            try:
                with open(os.path.join(cache_dir(), "error.log"), "w",
                          encoding="utf-8") as f:
                    f.write(err)
            except Exception:
                pass
            lines = [ln for ln in err.strip().splitlines() if ln.strip()]
            short = lines[-1][:80] if lines else "?"
            low = err.lower()
            if (err.startswith("IMPORT") or "winerror 3" in low
                    or "winerror 126" in low or "dll" in low):
                QMessageBox.information(self, "DraveChat", T("engine_err"))
            self._set_status(T("load_fail") % short)
            return
        self.model = llm
        self.settings["model_path"] = path
        self._save_settings()
        self._reset_session()
        self._set_status(T("ready") % os.path.basename(path))

    def _system_base(self):
        # alleen de persoonlijkheid; geheugen/kennis gaan per vraag mee (zie _send)
        return SYS_PROMPT.get(LANG, SYS_PROMPT["en"])

    def _reset_session(self):
        if self.model is None:
            return
        if self.session is not None:
            try:
                self.session.__exit__(None, None, None)
            except Exception:
                pass
            self.session = None
        persona = self._system_base()
        mp = self.settings.get("model_path", "").lower()
        # juiste chat-sjabloon per modelfamilie (voorkomt '###'-lekkage en
        # zorgt dat instructies/context netjes gevolgd worden)
        if "llama" in mp:
            sysp = ("<|start_header_id|>system<|end_header_id|>\n\n"
                    + persona + "<|eot_id|>")
            tmpl = ("<|start_header_id|>user<|end_header_id|>\n\n%1<|eot_id|>"
                    "<|start_header_id|>assistant<|end_header_id|>\n\n")
        elif "qwen" in mp:
            sysp = "<|im_start|>system\n" + persona + "<|im_end|>\n"
            tmpl = ("<|im_start|>user\n%1<|im_end|>\n"
                    "<|im_start|>assistant\n")
        else:
            sysp, tmpl = persona, None
        try:
            if tmpl:
                self.session = self.model.chat_session(system_prompt=sysp,
                                                       prompt_template=tmpl)
            else:
                self.session = self.model.chat_session(system_prompt=sysp)
            self.session.__enter__()
        except Exception:
            try:
                self.session = self.model.chat_session(system_prompt=persona)
                self.session.__enter__()
            except Exception:
                self.session = None

    # ---------- versturen ----------
    def _send(self):
        if self.busy:
            return
        text = self.input.text().strip()
        if not text:
            return
        low = text.lower()
        if low.startswith("/onthoud ") or low.startswith("/remember "):
            fact = text.split(" ", 1)[1].strip()
            if fact:
                self.memory.append(fact)
                self._save_list("memory.json", self.memory)
                self._bubble(T("draven"), "#b59cff", T("remembered") % fact)
            self.input.clear()
            return
        if self.model is None:
            self._bubble(T("draven"), "#ff9b9b", T("need_model"))
            return
        self.input.clear()
        self._bubble(T("you"), "#8fd0ff", text)
        self.messages.append({"role": "user", "content": text})
        self.busy = True
        self.send_btn.setEnabled(False)
        self.input.setEnabled(False)
        self.cur = ""
        self._append_html("<b style='color:#b59cff'>%s:</b> " % T("draven"))
        # stem klaarzetten (spreekt per zin uit tijdens het antwoord)
        self._say_buffer = ""
        if self.speak_box.isChecked():
            self.speaker.configure(
                self.settings.get("voice", ""),
                float(self.settings.get("voice_speed", 1.0)),
                float(self.settings.get("voice_pitch", 1.0)), LANG)
            self.speaker.clear()
        # geheugen (alle feiten) + relevante kennis (RAG) bij de vraag meegeven
        self._pending_text = text
        self._ctx = []
        if self.memory:
            lbl = "Over de gebruiker" if LANG == "nl" else "About the user"
            self._ctx.append(lbl + ": " + "; ".join(self.memory))
        hits = self._retrieve(text)
        if hits:
            lbl = "Relevante kennis" if LANG == "nl" else "Relevant knowledge"
            self._ctx.append(lbl + ": " + " | ".join(hits))
        # optioneel eerst online zoeken (Startpage), daarna pas antwoorden
        if self.online_box.isChecked():
            self.status.setText(T("searching"))
            self.searcher = SearchWorker(
                text, self.settings.get("search_url", DEFAULT_SEARCH))
            self.searcher.done.connect(self._search_done)
            self.searcher.start()
        else:
            self._start_chat(self._build_prompt(text, self._ctx))

    def _build_prompt(self, text, ctx):
        if ctx:
            pre = ("Gebruik onderstaande context als die klopt. Antwoord kort.\n"
                   if LANG == "nl" else
                   "Use the context below if correct. Answer briefly.\n")
            return pre + "\n".join(ctx) + "\n\n" + text
        return text

    def _search_done(self, results):
        mp = self.settings.get("model_path", "")
        if mp:
            self.status.setText(T("ready") % os.path.basename(mp))
        if results:
            lbl = ("Actuele webresultaten (Startpage)" if LANG == "nl"
                   else "Recent web results (Startpage)")
            lines = [("- " + ((t + ": ") if t else "") + d)
                     for t, d in results]
            self._ctx.append(lbl + ":\n" + "\n".join(lines))
        self._start_chat(self._build_prompt(self._pending_text, self._ctx))

    def _start_chat(self, prompt):
        self.worker = ChatWorker(self.model, prompt)
        self.worker.token.connect(self._on_token)
        self.worker.done.connect(self._on_done)
        self.worker.error.connect(self._on_error)
        self.worker.start()

    _STOPS = ("<|", "\nJij:", "\nUser:", "\nHuman:", "\nAntwoord:",
              "\nQuestion:", "\nVraag:", "\n###", "###")

    def _stop_cut(self, text):
        idx = None
        for m in self._STOPS:
            p = text.find(m)
            if p != -1:
                idx = p if idx is None else min(idx, p)
        return idx

    def _on_token(self, tok):
        if not self.busy:
            return
        self.cur += tok
        self.view.moveCursor(QTextCursor.MoveOperation.End)
        self.view.insertPlainText(tok)
        self.view.ensureCursorVisible()
        # model begint aan een nieuwe beurt / lekt tokens -> afkappen
        idx = self._stop_cut(self.cur)
        if idx is not None:
            extra = len(self.cur) - idx
            self.cur = self.cur[:idx].rstrip()
            cur = self.view.textCursor()
            cur.movePosition(QTextCursor.MoveOperation.End)
            for _ in range(extra):
                cur.deletePreviousChar()
            if self.worker and self.worker.isRunning():
                self.worker.stop()
            self._on_done()
            return
        # spreek complete zinnen meteen uit (stem volgt de tekst)
        if self.speak_box.isChecked():
            self._say_buffer += tok
            ends = list(re.finditer(r"[.!?\n]", self._say_buffer))
            if ends:
                sidx = ends[-1].end()
                chunk = self._say_buffer[:sidx].strip()
                self._say_buffer = self._say_buffer[sidx:]
                if chunk:
                    self.speaker.say(chunk)

    def _on_done(self):
        if not self.busy:
            return
        self.busy = False
        self.messages.append({"role": "assistant", "content": self.cur})
        self._save_history()
        self.send_btn.setEnabled(True)
        self.input.setEnabled(True)
        self.input.setFocus()
        # de laatste (nog niet afgesloten) zin ook uitspreken
        if self.speak_box.isChecked():
            rest = (self._say_buffer or "").strip()
            self._say_buffer = ""
            if rest:
                self.speaker.say(rest)

    def _on_error(self, msg):
        self._bubble(T("draven"), "#ff9b9b", msg[:120])
        self.busy = False
        self.send_btn.setEnabled(True)
        self.input.setEnabled(True)

    def _new_chat(self):
        self.messages = []
        self._save_history()
        self.view.clear()
        self._greet()
        self._reset_session()

    # ---------- geheugen / kennis dialogen ----------
    def _list_dialog(self, title, hint, lst, save_name, prompt):
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setStyleSheet(self.styleSheet())
        dlg.resize(500, 400)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(hint))
        widget = QListWidget()

        def fill():
            widget.clear()
            for m in lst:
                widget.addItem(m)
        fill()
        lay.addWidget(widget)

        def add():
            txt, ok = QInputDialog.getText(dlg, T("add"), prompt)
            if ok and txt.strip():
                lst.append(txt.strip())
                self._save_list(save_name, lst)
                fill()

        def rem():
            i = widget.currentRow()
            if 0 <= i < len(lst):
                del lst[i]
                self._save_list(save_name, lst)
                fill()

        row = QHBoxLayout()
        for label, fn in ((T("add"), add), (T("delete"), rem),
                          (T("close"), dlg.accept)):
            b = QPushButton(label)
            b.clicked.connect(fn)
            row.addWidget(b)
        lay.addLayout(row)
        dlg.exec()

    def open_memory(self):
        self._list_dialog(T("mem_title"), T("mem_hint"), self.memory,
                          "memory.json", T("mem_new"))

    def open_knowledge(self):
        self._list_dialog(T("know_title"), T("know_hint"), self.knowledge,
                          "knowledge.json", T("know_new"))

    # ---------- diversen ----------
    def _open(self, url):
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            pass

    def _info(self):
        QMessageBox.information(self, T("info"), T("info_txt"))

    def closeEvent(self, e):
        self._save_settings()
        self._save_history()
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(1500)
        if self.session is not None:
            try:
                self.session.__exit__(None, None, None)
            except Exception:
                pass
        e.accept()


def main():
    app = QApplication(sys.argv)
    w = Main()
    w.show()
    try:  # Dravenlock: stille update-check (uit te zetten; Ctrl+Shift+U = met de hand)
        import drave_update
        drave_update.start(w, 'DraveChat', '1.0.2')
    except Exception:
        pass
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
