# -*- coding: utf-8 -*-
"""DraveChat - een lokale AI-chat-helper van Dravenlock (PyQt6 + Ollama).

Praat met een klein taalmodel dat lokaal op je pc draait via Ollama, met een
eigen "Draven"-persoonlijkheid. De app kan Ollama zelf AAN- en UITZETTEN en
stopt Ollama netjes bij het afsluiten (instelbaar).

Vereist: Ollama geinstalleerd (https://ollama.com/download). Bij de eerste keer
haal je een model op met de knop 'Model ophalen'.

Tweetalig NL/EN, portable (instellingen in de app-map). Donationware.
"""
import json
import locale
import os
import shutil
import subprocess
import sys
import time
import urllib.request

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize
from PyQt6.QtGui import QIcon, QPixmap, QTextCursor, QAction
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QTextBrowser, QLineEdit, QPushButton,
                             QComboBox, QLabel, QCheckBox, QMessageBox,
                             QProgressBar, QDialog, QListWidget, QInputDialog)

OLLAMA = "http://127.0.0.1:11434"
NOWIN = 0x08000000 if os.name == "nt" else 0
SUGGESTED = ["llama3.2:3b", "llama3.2:1b", "qwen2.5:3b", "phi3:mini",
             "gemma2:2b"]


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
    "model": {"nl": "Model:", "en": "Model:"},
    "pull": {"nl": "Model ophalen", "en": "Get model"},
    "new": {"nl": "Nieuw gesprek", "en": "New chat"},
    "memory": {"nl": "🧠 Geheugen", "en": "🧠 Memory"},
    "mem_title": {"nl": "Wat Draven onthoudt", "en": "What Draven remembers"},
    "mem_hint": {"nl": "Feiten die Draven bij elk gesprek meeneemt "
                       "(bv. je naam, wat je maakt):",
                 "en": "Facts Draven brings into every chat "
                       "(e.g. your name, what you build):"},
    "mem_add": {"nl": "Toevoegen", "en": "Add"},
    "mem_del": {"nl": "Verwijderen", "en": "Remove"},
    "mem_new": {"nl": "Wat moet Draven onthouden?",
                "en": "What should Draven remember?"},
    "close": {"nl": "Sluiten", "en": "Close"},
    "remembered": {"nl": "Onthouden ✔  (%s)", "en": "Remembered ✔  (%s)"},
    "mem_tip": {"nl": "Tip: typ '/onthoud <feit>' of gebruik de 🧠-knop.",
                "en": "Tip: type '/remember <fact>' or use the 🧠 button."},
    "donate": {"nl": "♥ Doneren", "en": "♥ Donate"},
    "info": {"nl": "Info", "en": "Info"},
    "on": {"nl": "Ollama aanzetten", "en": "Start Ollama"},
    "off": {"nl": "Ollama uitzetten", "en": "Stop Ollama"},
    "st_on": {"nl": "● Ollama aan", "en": "● Ollama on"},
    "st_off": {"nl": "● Ollama uit", "en": "● Ollama off"},
    "closebox": {"nl": "Ollama volledig afsluiten bij sluiten",
                 "en": "Fully stop Ollama on close"},
    "thinking": {"nl": "Draven denkt...", "en": "Draven is thinking..."},
    "starting": {"nl": "Ollama starten...", "en": "Starting Ollama..."},
    "no_ollama": {
        "nl": "Ollama is niet gevonden. Installeer het eerst via "
              "https://ollama.com/download en probeer opnieuw.",
        "en": "Ollama was not found. Install it from "
              "https://ollama.com/download and try again."},
    "no_conn": {
        "nl": "Kan Ollama niet bereiken. Staat hij aan (knop rechtsboven) en is "
              "het model opgehaald?",
        "en": "Cannot reach Ollama. Is it on (top-right button) and is the "
              "model downloaded?"},
    "pulling": {"nl": "Model ophalen: %s", "en": "Pulling model: %s"},
    "pull_done": {"nl": "Model '%s' is klaar voor gebruik.",
                  "en": "Model '%s' is ready."},
    "greet": {
        "nl": "Hoi! Ik ben Draven, je lokale AI-helper. Kies een model, zorg "
              "dat Ollama aan staat en stel me gerust een vraag.",
        "en": "Hi! I'm Draven, your local AI helper. Pick a model, make sure "
              "Ollama is on and ask me anything."},
    "info_txt": {
        "nl": "DraveChat draait een klein AI-model lokaal via Ollama - je data "
              "blijft op je pc. De app kan Ollama aan/uit zetten en stopt hem "
              "bij het afsluiten.\n\nEerste keer: installeer Ollama "
              "(ollama.com/download), kies een model en klik 'Model ophalen'.\n\n"
              "Donationware - https://paypal.me/roger076 - service@dravenlock.nl",
        "en": "DraveChat runs a small AI model locally via Ollama - your data "
              "stays on your pc. The app can turn Ollama on/off and stops it on "
              "close.\n\nFirst time: install Ollama (ollama.com/download), pick "
              "a model and click 'Get model'.\n\n"
              "Donationware - https://paypal.me/roger076 - service@dravenlock.nl"},
}


def T(k):
    d = TX.get(k, {})
    return d.get(LANG) or d.get("en") or k


SYS_PROMPT = {
    "nl": "Je bent Draven, de behulpzame AI-assistent van Dravenlock. Je bent "
          "vriendelijk, nuchter en beknopt. Antwoord in de taal van de "
          "gebruiker en geef praktische, eerlijke antwoorden.",
    "en": "You are Draven, the helpful AI assistant of Dravenlock. You are "
          "friendly, level-headed and concise. Reply in the user's language and "
          "give practical, honest answers.",
}
DONATE = "https://paypal.me/roger076"


# --------------------------------------------------------------- Ollama-beheer
class OllamaManager:
    def __init__(self):
        self.proc = None          # eigen 'ollama serve'-proces (indien gestart)
        self.started = False

    def is_up(self, timeout=0.6):
        try:
            urllib.request.urlopen(OLLAMA + "/api/tags", timeout=timeout)
            return True
        except Exception:
            return False

    def find_exe(self):
        exe = shutil.which("ollama")
        if exe:
            return exe
        for p in (os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe"),
                  os.path.expandvars(r"%ProgramFiles%\Ollama\ollama.exe")):
            if os.path.exists(p):
                return p
        return None

    def start(self, wait=15):
        if self.is_up():
            return True
        exe = self.find_exe()
        if not exe:
            return "noexe"
        try:
            self.proc = subprocess.Popen(
                [exe, "serve"], stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, creationflags=NOWIN)
            self.started = True
        except Exception:
            return False
        t0 = time.time()
        while time.time() - t0 < wait:
            if self.is_up():
                return True
            time.sleep(0.5)
        return False

    def stop(self, model=None, hard=False):
        exe = self.find_exe()
        # model uit het geheugen lossen (geeft RAM/VRAM vrij)
        if exe and model:
            try:
                subprocess.run([exe, "stop", model], timeout=6,
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, creationflags=NOWIN)
            except Exception:
                pass
        # ons eigen serve-proces afsluiten
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except Exception:
                pass
        self.proc = None
        self.started = False
        # volledig afsluiten (ook een als-app draaiende Ollama)
        if hard and os.name == "nt":
            for name in ("ollama app.exe", "ollama.exe"):
                try:
                    subprocess.run(["taskkill", "/F", "/IM", name],
                                   timeout=6, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, creationflags=NOWIN)
                except Exception:
                    pass

    def models(self):
        try:
            r = urllib.request.urlopen(OLLAMA + "/api/tags", timeout=2)
            data = json.loads(r.read().decode("utf-8"))
            return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []


# --------------------------------------------------------------- werkthreads
class ChatWorker(QThread):
    token = pyqtSignal(str)
    done = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, model, messages):
        super().__init__()
        self.model = model
        self.messages = messages
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        payload = {"model": self.model, "messages": self.messages,
                   "stream": True}
        try:
            req = urllib.request.Request(
                OLLAMA + "/api/chat",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"})
            resp = urllib.request.urlopen(req, timeout=120)
            for raw in resp:
                if self._stop:
                    break
                line = raw.decode("utf-8").strip()
                if not line:
                    continue
                obj = json.loads(line)
                tok = obj.get("message", {}).get("content", "")
                if tok:
                    self.token.emit(tok)
                if obj.get("done"):
                    break
            self.done.emit()
        except Exception as e:
            self.error.emit(str(e))


class PullWorker(QThread):
    progress = pyqtSignal(str)
    done = pyqtSignal(bool)

    def __init__(self, model):
        super().__init__()
        self.model = model

    def run(self):
        payload = {"name": self.model, "stream": True}
        try:
            req = urllib.request.Request(
                OLLAMA + "/api/pull",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"})
            resp = urllib.request.urlopen(req, timeout=None)
            for raw in resp:
                line = raw.decode("utf-8").strip()
                if not line:
                    continue
                obj = json.loads(line)
                st = obj.get("status", "")
                if "completed" in obj and "total" in obj and obj["total"]:
                    pct = int(obj["completed"] * 100 / obj["total"])
                    self.progress.emit("%s  %d%%" % (st, pct))
                elif st:
                    self.progress.emit(st)
                if obj.get("error"):
                    self.done.emit(False)
                    return
            self.done.emit(True)
        except Exception:
            self.done.emit(False)


class StartWorker(QThread):
    result = pyqtSignal(object)

    def __init__(self, mgr):
        super().__init__()
        self.mgr = mgr

    def run(self):
        self.result.emit(self.mgr.start())


# --------------------------------------------------------------- hoofdvenster
class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.mgr = OllamaManager()
        self.worker = None
        self.puller = None
        self.starter = None
        self.cur = ""
        self.busy = False
        self.settings = self._load_settings()
        self.memory = self._load_memory()
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
        # statusklok
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh_status)
        self.timer.start(3000)
        self._refresh_status()

    # ---- opslag ----
    def _settings_path(self):
        return os.path.join(cache_dir(), "settings.json")

    def _load_settings(self):
        d = {"model": SUGGESTED[0], "close_stop": True}
        try:
            with open(self._settings_path(), "r", encoding="utf-8") as f:
                d.update(json.load(f))
        except Exception:
            pass
        return d

    def _save_settings(self):
        try:
            self.settings["model"] = self.model_box.currentText().strip()
            self.settings["close_stop"] = self.close_box.isChecked()
            with open(self._settings_path(), "w", encoding="utf-8") as f:
                json.dump(self.settings, f)
        except Exception:
            pass

    # ---- geheugen (feiten) + gespreksgeschiedenis ----
    def _mem_path(self):
        return os.path.join(cache_dir(), "memory.json")

    def _hist_path(self):
        return os.path.join(cache_dir(), "history.json")

    def _load_memory(self):
        try:
            with open(self._mem_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
            return [str(x) for x in data if str(x).strip()]
        except Exception:
            return []

    def _save_memory(self):
        try:
            with open(self._mem_path(), "w", encoding="utf-8") as f:
                json.dump(self.memory, f)
        except Exception:
            pass

    def _load_history(self):
        try:
            with open(self._hist_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
            return [m for m in data if m.get("role") in ("user", "assistant")]
        except Exception:
            return []

    def _save_history(self):
        try:
            with open(self._hist_path(), "w", encoding="utf-8") as f:
                json.dump(self.messages[-40:], f)   # laatste 40 berichten
        except Exception:
            pass

    def _system(self):
        base = SYS_PROMPT.get(LANG, SYS_PROMPT["en"])
        if self.memory:
            facts = "\n".join("- " + m for m in self.memory)
            hdr = ("\n\nWat je over de gebruiker onthoudt (gebruik als relevant):"
                   if LANG == "nl" else
                   "\n\nWhat you remember about the user (use if relevant):")
            return base + hdr + "\n" + facts
        return base

    def _restore_or_greet(self):
        if self.messages:
            for m in self.messages:
                if m["role"] == "user":
                    self._bubble(T("you"), "#8fd0ff", m["content"])
                else:
                    self._bubble(T("draven"), "#b59cff", m["content"])
        else:
            self._greet()

    def open_memory(self):
        dlg = QDialog(self)
        dlg.setWindowTitle(T("mem_title"))
        dlg.setStyleSheet(self.styleSheet())
        dlg.resize(460, 380)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(T("mem_hint")))
        lst = QListWidget()

        def fill():
            lst.clear()
            for m in self.memory:
                lst.addItem(m)
        fill()
        lay.addWidget(lst)

        def add():
            txt, ok = QInputDialog.getText(dlg, T("mem_add"), T("mem_new"))
            if ok and txt.strip():
                self.memory.append(txt.strip())
                self._save_memory()
                fill()

        def rem():
            i = lst.currentRow()
            if 0 <= i < len(self.memory):
                del self.memory[i]
                self._save_memory()
                fill()

        row = QHBoxLayout()
        for label, fn in ((T("mem_add"), add), (T("mem_del"), rem),
                          (T("close"), dlg.accept)):
            b = QPushButton(label)
            b.clicked.connect(fn)
            row.addWidget(b)
        lay.addLayout(row)
        dlg.exec()

    # ---- UI ----
    def _build(self):
        cen = QWidget()
        self.setCentralWidget(cen)
        lay = QVBoxLayout(cen)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        # kopbalk
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
        top.addWidget(QLabel(T("model")))
        self.model_box = QComboBox()
        self.model_box.setEditable(True)
        self.model_box.addItems(SUGGESTED)
        self.model_box.setCurrentText(self.settings.get("model", SUGGESTED[0]))
        self.model_box.setMinimumWidth(150)
        top.addWidget(self.model_box)
        self.pull_btn = QPushButton(T("pull"))
        self.pull_btn.clicked.connect(self._pull)
        top.addWidget(self.pull_btn)
        lay.addLayout(top)

        # status + ollama-schakelaar
        row = QHBoxLayout()
        self.status = QLabel(T("st_off"))
        self.status.setObjectName("status")
        row.addWidget(self.status)
        self.toggle = QPushButton(T("on"))
        self.toggle.clicked.connect(self._toggle_ollama)
        row.addWidget(self.toggle)
        row.addStretch(1)
        self.close_box = QCheckBox(T("closebox"))
        self.close_box.setChecked(bool(self.settings.get("close_stop", True)))
        row.addWidget(self.close_box)
        lay.addLayout(row)

        # chatweergave
        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(True)
        lay.addWidget(self.view, 1)

        # voortgangsbalk (voor model ophalen)
        self.prog = QProgressBar()
        self.prog.setRange(0, 0)
        self.prog.hide()
        lay.addWidget(self.prog)

        # invoer
        bottom = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText(T("placeholder"))
        self.input.returnPressed.connect(self._send)
        bottom.addWidget(self.input, 1)
        self.send_btn = QPushButton(T("send"))
        self.send_btn.clicked.connect(self._send)
        bottom.addWidget(self.send_btn)
        lay.addLayout(bottom)

        # onderste knoppen
        br = QHBoxLayout()
        b_new = QPushButton(T("new"))
        b_new.clicked.connect(self._new_chat)
        br.addWidget(b_new)
        b_mem = QPushButton(T("memory"))
        b_mem.clicked.connect(self.open_memory)
        br.addWidget(b_mem)
        b_small = QPushButton("A-")
        b_small.setToolTip("Tekst kleiner")
        b_small.clicked.connect(lambda: self._set_scale(-0.1))
        br.addWidget(b_small)
        b_big = QPushButton("A+")
        b_big.setToolTip("Tekst groter")
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
            QLabel#status { font-size:%dpx; font-weight:bold; }
            QTextBrowser { background:#0e0c16; border:1px solid #4a3d66;
                border-radius:10px; padding:12px; font-size:%dpx; }
            QLineEdit, QComboBox { background:#0e0c16; color:#e8e6f0;
                border:1px solid #4a3d66; border-radius:8px;
                padding:%dpx; font-size:%dpx; }
            QPushButton { background:#2a2440; color:#efeaff;
                border:1px solid #5a4d86; border-radius:8px;
                padding:%dpx %dpx; font-weight:bold; font-size:%dpx; }
            QPushButton:hover { background:#463a6e; }
            QCheckBox { color:#bdb3da; font-size:%dpx; }
            QProgressBar { border:1px solid #4a3d66; border-radius:6px;
                background:#0e0c16; text-align:center; color:#e8e6f0;
                font-size:%dpx; }
            QProgressBar::chunk { background:#7F77DD; border-radius:6px; }
        """ % (px(15), px(25), px(15), px(17), px(8), px(16),
               px(8), px(14), px(15), px(14), px(13)))
        # ook het chat-lettertype direct zetten (voor bestaande tekst)
        f = self.view.font()
        f.setPointSizeF(11 * s)
        self.view.setFont(f)

    def _set_scale(self, delta):
        self.scale = max(0.8, min(2.4, self.scale + delta))
        self.settings["scale"] = self.scale
        self._save_settings()
        self._apply_style()

    # ---- chatweergave ----
    def _append_html(self, html):
        # elke aanroep = een nieuwe alinea (witruimte tussen berichten)
        self.view.append(html)
        self.view.ensureCursorVisible()

    def _greet(self):
        self._append_html("<i style='color:#9b90c0'>%s</i>" % T("greet"))
        self._append_html("<i style='color:#6f6690'>%s</i>" % T("mem_tip"))

    def _bubble(self, who, color, text):
        safe = (text.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace("\n", "<br>"))
        self._append_html(
            "<b style='color:%s'>%s:</b> %s" % (color, who, safe))

    # ---- versturen ----
    def _send(self):
        if self.busy:
            return
        text = self.input.text().strip()
        if not text:
            return
