#!/usr/bin/env python3
"""
TV Terminal Emulator — Wayland / GTK 3.0 + VTE
Optimized for Android TV / remote-controlled use.
Brazilian ABNT2 on-screen keyboard with numbers & symbols layers.

Look: a translucent terminal "window" and a transparent keyboard floating over
a blurred screenshot of the desktop. The blur is computed ONCE at launch
(screenshot -> downscale twice -> upscale -> cached PNG in /tmp), never in
real time.

Remote keybinds: open the ⚙ button (bottom right) or map "Open key binds menu"
to a remote key. Config: ~/.config/tv-terminal/keybinds.json
Emergency shortcut for the binds menu: Ctrl+Shift+K.

Usage:  tv_terminal.py [--reuse-backdrop]
"""

import os
import sys
import json
import math
import shutil
import signal
import subprocess
from pathlib import Path

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Vte", "2.91")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, Gdk, Vte, GLib, Pango, GdkPixbuf
import cairo

# ---------------------------------------------------------------------------
# Paths / constants
# ---------------------------------------------------------------------------

BLUR_CACHE_DIR = Path("/tmp/tv-terminal-cache")
BACKDROP_FILE = BLUR_CACHE_DIR / "backdrop-blurred.png"
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "tv-terminal"
BINDS_FILE = CONFIG_DIR / "keybinds.json"

BACKDROP_DARKEN = 0.30     # black overlay on the blurred screenshot
BACKDROP_MAX_SIDE = 640    # blur works on a bounded size, then upscales
PANEL_ALPHA = 0.55         # terminal background opacity
PANEL_RADIUS = 12

FONT_MIN = 12
FONT_MAX = 48
FONT_STEP = 2

# ---------------------------------------------------------------------------
# Layout definitions (Brazilian ABNT2 inspired)
# ---------------------------------------------------------------------------

LAYER_LETTERS = [
    ["Esc", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "=", "Bksp", "Exit"],
    ["Tab", "q", "w", "e", "r", "t", "y", "u", "i", "o", "p", "´", "[", "]", "Del"],
    ["Caps", "a", "s", "d", "f", "g", "h", "j", "k", "l", "ç", "~", "'", "Enter"],
    ["Shift", "\\", "z", "x", "c", "v", "b", "n", "m", ",", ".", ";", "/", "Home", "End"],
    ["Ctrl", "Alt", "123", " ", "Sym", "←", "↓", "↑", "→", "PgUp", "PgDn"],
]

LAYER_NUMBERS = [
    ["Esc", "!", "@", "#", "$", "%", "¨", "&", "*", "(", ")", "_", "+", "Bksp", "Exit"],
    ["Tab", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "`", "{", "}", "Del"],
    ["Caps", "º", "ª", "£", "¢", "¬", "§", "°", "±", "×", "÷", "^", "'", "Enter"],
    ["Shift", "|", "?", "!", ":", ";", ",", ".", "-", "=", "/", "\\", '"', "Home", "End"],
    ["Ctrl", "Alt", "ABC", " ", "Sym", "←", "↓", "↑", "→", "PgUp", "PgDn"],
]

LAYER_SYMBOLS = [
    ["Esc", "¹", "²", "³", "£", "¢", "¬", "§", "°", "±", "×", "÷", "≠", "Bksp", "Exit"],
    ["Tab", "¿", "¡", "«", "»", "‹", "›", "“", "”", "‘", "’", "…", "–", "—", "Del"],
    ["Caps", "á", "é", "í", "ó", "ú", "â", "ê", "ô", "ã", "õ", "ü", "ñ", "Enter"],
    ["Shift", "à", "è", "ì", "ò", "ù", "ä", "ë", "ï", "ö", "ü", "ÿ", "ç", "Home", "End"],
    ["Ctrl", "Alt", "ABC", " ", "123", "←", "↓", "↑", "→", "PgUp", "PgDn"],
]

SHIFT_MAP = {
    "1": "!", "2": "@", "3": "#", "4": "$", "5": "%",
    "6": "¨", "7": "&", "8": "*", "9": "(", "0": ")",
    "-": "_", "=": "+",
    "q": "Q", "w": "W", "e": "E", "r": "R", "t": "T",
    "y": "Y", "u": "U", "i": "I", "o": "O", "p": "P",
    "´": "`", "[": "{", "]": "}",
    "a": "A", "s": "S", "d": "D", "f": "F", "g": "G",
    "h": "H", "j": "J", "k": "K", "l": "L", "ç": "Ç",
    "~": "^", "'": '"',
    "\\": "|", "z": "Z", "x": "X", "c": "C", "v": "V",
    "b": "B", "n": "N", "m": "M", ",": "<", ".": ">",
    ";": ":", "/": "?",
}

DEAD_KEYS = {
    "´": "acute",
    "`": "grave",
    "~": "tilde",
    "^": "circumflex",
    "¨": "diaeresis",
}

ACCENT_MAP = {
    ("acute", "a"): "á", ("acute", "e"): "é", ("acute", "i"): "í",
    ("acute", "o"): "ó", ("acute", "u"): "ú", ("acute", "c"): "ć",
    ("acute", "A"): "Á", ("acute", "E"): "É", ("acute", "I"): "Í",
    ("acute", "O"): "Ó", ("acute", "U"): "Ú",
    ("grave", "a"): "à", ("grave", "e"): "è", ("grave", "i"): "ì",
    ("grave", "o"): "ò", ("grave", "u"): "ù",
    ("grave", "A"): "À", ("grave", "E"): "È", ("grave", "I"): "Ì",
    ("grave", "O"): "Ò", ("grave", "U"): "Ù",
    ("tilde", "a"): "ã", ("tilde", "o"): "õ", ("tilde", "n"): "ñ",
    ("tilde", "A"): "Ã", ("tilde", "O"): "Õ", ("tilde", "N"): "Ñ",
    ("circumflex", "a"): "â", ("circumflex", "e"): "ê", ("circumflex", "o"): "ô",
    ("circumflex", "A"): "Â", ("circumflex", "E"): "Ê", ("circumflex", "O"): "Ô",
    ("diaeresis", "a"): "ä", ("diaeresis", "e"): "ë", ("diaeresis", "i"): "ï",
    ("diaeresis", "o"): "ö", ("diaeresis", "u"): "ü",
    ("diaeresis", "A"): "Ä", ("diaeresis", "E"): "Ë", ("diaeresis", "I"): "Ï",
    ("diaeresis", "O"): "Ö", ("diaeresis", "U"): "Ü",
}

SPECIAL_KEYS = {
    "Esc", "Tab", "Bksp", "Enter", "Shift", "Caps", "Ctrl", "Alt",
    "123", "ABC", "Sym", " ", "←", "↓", "↑", "→",
    "Exit", "Del", "Home", "End", "PgUp", "PgDn",
}

WIDER_KEYS = {
    "Bksp", "Enter", "Shift", "Caps", "Tab", "Exit", "Del",
    "Home", "End", "PgUp", "PgDn", "123", "ABC", "Sym",
}

KEY_SEQUENCES = {
    "Esc": "\x1b", "Tab": "\t", "Bksp": "\x7f", "Del": "\x1b[3~",
    "Enter": "\r", "←": "\x1b[D", "→": "\x1b[C", "↑": "\x1b[A", "↓": "\x1b[B",
    "Home": "\x1b[H", "End": "\x1b[F", "PgUp": "\x1b[5~", "PgDn": "\x1b[6~",
    " ": " ",
}

# ---------------------------------------------------------------------------
# Remote keybinds
# ---------------------------------------------------------------------------

# (group title, [(action id, label), ...])
ACTION_GROUPS = [
    ("On-screen keyboard navigation", [
        ("nav_up", "Move up"),
        ("nav_down", "Move down"),
        ("nav_left", "Move left"),
        ("nav_right", "Move right"),
        ("select", "Select / press key"),
        ("layer_cycle", "Next layer (ABC / 123 / Sym)"),
    ]),
    ("Keyboard control", [
        ("osk_lock", "Disable / enable keyboard input (external keyboard)"),
        ("osk_toggle", "Hide / show keyboard"),
    ]),
    ("Send a key to the terminal", [
        ("send_esc", "Esc"),
        ("send_tab", "Tab"),
        ("send_bksp", "Backspace"),
        ("send_del", "Delete"),
        ("send_enter", "Enter"),
        ("send_ctrl_c", "Ctrl+C"),
        ("send_ctrl_d", "Ctrl+D"),
        ("send_home", "Home"),
        ("send_end", "End"),
        ("send_pgup", "Page Up"),
        ("send_pgdn", "Page Down"),
    ]),
    ("App", [
        ("zoom_in", "Zoom in"),
        ("zoom_out", "Zoom out"),
        ("open_binds", "Open this menu"),
        ("refresh_backdrop", "Refresh blurred background"),
        ("exit", "Exit"),
    ]),
]

ACTION_LABELS = {a: l for _, items in ACTION_GROUPS for a, l in items}

DEFAULT_BINDS = {
    "nav_up": ["Up", "KP_Up"],
    "nav_down": ["Down", "KP_Down"],
    "nav_left": ["Left", "KP_Left"],
    "nav_right": ["Right", "KP_Right"],
    "select": ["Return", "KP_Enter", "Select", "space", "KP_Space"],
}

SEND_SEQUENCES = {
    "send_esc": "\x1b", "send_tab": "\t", "send_bksp": "\x7f",
    "send_del": "\x1b[3~", "send_enter": "\r",
    "send_ctrl_c": "\x03", "send_ctrl_d": "\x04",
    "send_home": "\x1b[H", "send_end": "\x1b[F",
    "send_pgup": "\x1b[5~", "send_pgdn": "\x1b[6~",
}

# Only meaningful while the on-screen keyboard is active (shown AND not disabled).
OSK_ONLY_ACTIONS = {"nav_up", "nav_down", "nav_left", "nav_right", "select", "layer_cycle"}

# Old behaviour: +/- on a real keyboard zoom, but only while the OSK is active
# (otherwise they must be typed into the terminal).
LEGACY_ZOOM_IN = {"plus", "KP_Add", "equal"}
LEGACY_ZOOM_OUT = {"minus", "KP_Subtract"}

PURE_MODIFIERS = {
    "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R",
    "Super_L", "Super_R", "Meta_L", "Meta_R", "Hyper_L", "Hyper_R",
    "ISO_Level3_Shift", "ISO_Level5_Shift", "Caps_Lock", "Num_Lock", "Scroll_Lock",
}

PRETTY_KEYS = {
    "Return": "Enter", "KP_Enter": "Num Enter", "Select": "OK/Select",
    "space": "Space", "KP_Space": "Num Space", "Escape": "Esc",
    "BackSpace": "Backspace", "Delete": "Del", "Prior": "PgUp", "Next": "PgDn",
    "KP_Add": "Num +", "KP_Subtract": "Num −", "KP_Up": "Num ↑",
    "KP_Down": "Num ↓", "KP_Left": "Num ←", "KP_Right": "Num →",
    "Up": "↑", "Down": "↓", "Left": "←", "Right": "→",
    "plus": "+", "minus": "−", "equal": "=",
    "XF86AudioRaiseVolume": "Vol +", "XF86AudioLowerVolume": "Vol −",
    "XF86AudioMute": "Mute", "XF86AudioPlay": "Play", "XF86AudioPause": "Pause",
    "XF86AudioNext": "Next track", "XF86AudioPrev": "Prev track",
    "XF86Back": "Back", "XF86Forward": "Forward", "XF86HomePage": "Home page",
    "XF86Red": "Red", "XF86Green": "Green", "XF86Yellow": "Yellow", "XF86Blue": "Blue",
}

MOD_BLOCK_MASK = (
    Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.MOD1_MASK |
    Gdk.ModifierType.SUPER_MASK | Gdk.ModifierType.META_MASK
)


def key_name_from_event(event):
    """Stable name for a key: keysym name, or kc<hardware code> for unnamed remote keys."""
    name = Gdk.keyval_name(Gdk.keyval_to_lower(event.keyval))
    if not name or name in ("VoidSymbol", "NoSymbol"):
        return f"kc{event.hardware_keycode}"
    return name


def pretty_key(name):
    if name in PRETTY_KEYS:
        return PRETTY_KEYS[name]
    if name.startswith("kc") and name[2:].isdigit():
        return f"Key #{name[2:]}"
    if name.startswith("XF86"):
        return name[4:]
    return name.upper() if len(name) == 1 else name


def load_binds():
    binds = {a: [] for a in ACTION_LABELS}
    for a, keys in DEFAULT_BINDS.items():
        binds[a] = list(keys)
    try:
        data = json.loads(BINDS_FILE.read_text(encoding="utf-8"))
        saved = data.get("binds", {})
        for a in ACTION_LABELS:
            if a in saved and isinstance(saved[a], list):
                binds[a] = [k for k in saved[a] if isinstance(k, str)]
    except FileNotFoundError:
        pass
    except Exception as e:
        print("keybinds load error:", e, file=sys.stderr)
    return binds


def save_binds(binds):
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        BINDS_FILE.write_text(
            json.dumps({"binds": binds}, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except Exception as e:
        print("keybinds save error:", e, file=sys.stderr)


# ---------------------------------------------------------------------------
# Blurred desktop backdrop (screenshot once -> blur once -> cache in /tmp)
# ---------------------------------------------------------------------------

def pixbuf_blur_darken(pixbuf, darken=0.65, do_blur=True):
    """Smoother multi-pass downscale blur + black overlay (still cheap)."""
    w, h = pixbuf.get_width(), pixbuf.get_height()
    if w < 1 or h < 1:
        return pixbuf
    src = pixbuf
    if do_blur:
        s1w, s1h = max(1, w // 30), max(1, h // 30)
        mid = pixbuf.scale_simple(s1w, s1h, GdkPixbuf.InterpType.BILINEAR)
        s2w, s2h = max(1, w // 50), max(1, h // 50)
        small = mid.scale_simple(s2w, s2h, GdkPixbuf.InterpType.BILINEAR)
        mid2 = small.scale_simple(s1w, s1h, GdkPixbuf.InterpType.BILINEAR)
        src = mid2.scale_simple(w, h, GdkPixbuf.InterpType.BILINEAR)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    cr = cairo.Context(surface)
    Gdk.cairo_set_source_pixbuf(cr, src, 0, 0)
    cr.paint()
    d = max(0.0, min(1.0, float(darken)))
    cr.set_source_rgba(0.0, 0.0, 0.0, d)
    cr.paint()
    return Gdk.pixbuf_get_from_surface(surface, 0, 0, w, h)


def build_blurred_backdrop(src_pixbuf, darken=BACKDROP_DARKEN, max_side=BACKDROP_MAX_SIDE):
    """Blur once and store the result in /tmp. Raw screenshots are never kept."""
    pixbuf = src_pixbuf
    w, h = pixbuf.get_width(), pixbuf.get_height()
    if max(w, h) > max_side:
        s = max_side / float(max(w, h))
        pixbuf = pixbuf.scale_simple(
            max(1, int(w * s)), max(1, int(h * s)), GdkPixbuf.InterpType.BILINEAR
        )
    processed = pixbuf_blur_darken(pixbuf, darken=darken, do_blur=True)
    try:
        BLUR_CACHE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
        processed.savev(str(BACKDROP_FILE), "png", [], [])
    except Exception as e:
        print("blur cache save error:", e, file=sys.stderr)
    return processed


def load_cached_backdrop():
    try:
        if BACKDROP_FILE.is_file():
            return GdkPixbuf.Pixbuf.new_from_file(str(BACKDROP_FILE))
    except Exception:
        pass
    return None


def _run_capture(cmd, dest):
    try:
        subprocess.run(cmd, timeout=6, check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.isfile(dest) and os.path.getsize(dest) > 0:
            return GdkPixbuf.Pixbuf.new_from_file(dest)
    except Exception:
        pass
    return None


def capture_screenshot():
    """Grab the current desktop (must run BEFORE our window is shown)."""
    display = Gdk.Display.get_default()
    if display is None:
        return None
    monitor = display.get_primary_monitor() or display.get_monitor(0)
    geom = monitor.get_geometry() if monitor else None
    is_wayland = "Wayland" in type(display).__name__

    BLUR_CACHE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    raw = str(BLUR_CACHE_DIR / "shot-raw.png")

    attempts = []
    if is_wayland:
        if shutil.which("grim"):
            cmd = ["grim"]
            if geom:
                cmd += ["-g", f"{geom.x},{geom.y} {geom.width}x{geom.height}"]
            attempts.append(cmd + [raw])
        if shutil.which("gnome-screenshot"):
            attempts.append(["gnome-screenshot", "-f", raw])
        if shutil.which("spectacle"):
            attempts.append(["spectacle", "-b", "-n", "-f", "-o", raw])
    else:
        # X11: read the root window directly
        try:
            root = Gdk.get_default_root_window()
            if root is not None and geom is not None:
                pb = Gdk.pixbuf_get_from_window(root, geom.x, geom.y, geom.width, geom.height)
                if pb is not None:
                    return pb
        except Exception:
            pass
        if shutil.which("scrot"):
            attempts.append(["scrot", "-o", raw])
        if shutil.which("import"):
            attempts.append(["import", "-window", "root", raw])

    result = None
    for cmd in attempts:
        try:
            os.remove(raw)
        except OSError:
            pass
        result = _run_capture(cmd, raw)
        if result is not None:
            break
    try:
        os.remove(raw)   # don't leave an unblurred screenshot in /tmp
    except OSError:
        pass
    return result


def prepare_backdrop(reuse_cache=False):
    """Returns a blurred pixbuf (or None -> gradient fallback)."""
    if reuse_cache:
        cached = load_cached_backdrop()
        if cached is not None:
            return cached
    shot = capture_screenshot()
    if shot is not None:
        return build_blurred_backdrop(shot)
    return load_cached_backdrop()


# ---------------------------------------------------------------------------
# Helpers – scale UI to the current display
# ---------------------------------------------------------------------------

def get_display_size():
    display = Gdk.Display.get_default()
    if display is None:
        return 1920, 1080
    monitor = display.get_primary_monitor() or display.get_monitor(0)
    if monitor is None:
        return 1920, 1080
    geom = monitor.get_geometry()
    return geom.width, geom.height


def rounded_rect(cr, x, y, w, h, r):
    r = max(0.0, min(r, w / 2.0, h / 2.0))
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


def build_css(screen_w, screen_h):
    scale = min(screen_w / 1920.0, screen_h / 1080.0)
    scale = max(0.75, min(scale, 1.35))

    key_h = int(40 * scale)
    key_font = int(21 * scale)
    key_min_w = int(42 * scale)
    space_min_w = int(200 * scale)
    radius = int(6 * scale)
    side_key = int(44 * scale)
    pad_v = int(6 * scale)
    pad_h = int(8 * scale)
    term_pad_v = int(10 * scale)
    term_pad_h = int(16 * scale)
    toast_font = int(16 * scale)
    menu_font = int(19 * scale)

    css = f"""
window, window.background {{
    background-color: transparent;
    background-image: none;
}}

vte-terminal {{
    padding: {term_pad_v}px {term_pad_h}px;
}}

.keyboard {{
    background: transparent;
    padding: {pad_v}px {pad_h}px {pad_v + 6}px {pad_h}px;
}}

/* ---- semi-transparent dark keys ---- */
.key, .side-key {{
    background-image: none;
    background-color: rgba(14, 16, 22, 0.72);
    color: #e8ecf4;
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: {radius}px;
    font-family: "Fira Sans", "DejaVu Sans", "Noto Sans", sans-serif;
    font-weight: 600;
    box-shadow: none;
    text-shadow: none;
    padding: 2px 4px;
    outline: none;
}}
.key {{
    font-size: {key_font}px;
    min-height: {key_h}px;
    min-width: {key_min_w}px;
}}
.side-key {{
    font-size: {key_font}px;
    min-height: {side_key}px;
    min-width: {side_key}px;
    padding: 2px;
}}
.key:hover, .side-key:hover {{
    background-color: rgba(44, 52, 70, 0.80);
    border-color: rgba(120, 160, 255, 0.35);
}}
.key:active, .side-key:active {{
    background-color: rgba(30, 40, 62, 0.85);
}}
.key:disabled, .side-key:disabled {{
    color: #e8ecf4;
    background-color: rgba(14, 16, 22, 0.72);
}}

/* remote focus highlight */
.key.focused, .side-key.focused {{
    background-color: rgba(228, 232, 240, 0.92);
    border-color: rgba(255, 255, 255, 0.95);
    color: #0d1017;
    box-shadow: 0 0 14px rgba(170, 205, 255, 0.45);
}}

.key.special {{ background-color: rgba(18, 20, 27, 0.78); }}
.key.special.focused {{ background-color: rgba(228, 232, 240, 0.92); }}

.key.layer, .side-key.enter-key {{
    background-color: rgba(24, 38, 62, 0.74);
    color: #8fb8ff;
}}
.key.layer.focused, .side-key.enter-key.focused {{
    background-color: rgba(160, 200, 255, 0.92);
    color: #0a1424;
}}
.side-key.enter-key {{ min-width: {int(side_key * 1.4)}px; }}

.key.exit {{
    background-color: rgba(62, 18, 22, 0.74);
    border-color: rgba(255, 110, 110, 0.20);
    color: #ff9d9d;
}}
.key.exit.focused {{
    background-color: rgba(255, 130, 130, 0.92);
    color: #2a0a0a;
}}

.key.modifier-active {{
    background-color: rgba(36, 86, 50, 0.80);
    border-color: rgba(110, 220, 130, 0.35);
    color: #b6ffbf;
}}

.key.space {{ min-width: {space_min_w}px; }}

.side-key.zoom-key {{
    color: #cfe8cf;
    font-size: {key_font + 2}px;
}}

/* keyboard input disabled (external keyboard mode): still visible, dimmed */
.osk-locked .key, .osk-locked .side-key.dpad {{
    opacity: 0.38;
}}

.side-panel {{ background: transparent; padding: 4px; }}

/* ---- toast ---- */
.toast {{
    background-color: rgba(8, 10, 14, 0.72);
    color: #e8ecf4;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: {radius + 2}px;
    padding: 6px 14px;
    font-size: {toast_font}px;
    font-weight: 600;
}}

/* ---- keybinds menu ---- */
.binds-panel {{
    background-color: rgba(10, 12, 18, 0.90);
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: {radius + 6}px;
    padding: 18px 22px;
}}
.binds-title {{
    color: #ffffff;
    font-size: {int(menu_font * 1.25)}px;
    font-weight: 700;
}}
.binds-hint {{
    color: #8a93a6;
    font-size: {int(menu_font * 0.78)}px;
}}
.binds-group {{
    color: #8fb8ff;
    font-size: {int(menu_font * 0.80)}px;
    font-weight: 700;
    padding: 10px 6px 2px 6px;
}}
.bind-row {{
    background-color: rgba(255, 255, 255, 0.04);
    border-radius: {radius}px;
    padding: 6px 12px;
}}
.bind-row.focused {{
    background-color: rgba(228, 232, 240, 0.92);
}}
.bind-row label {{
    color: #e8ecf4;
    font-size: {menu_font}px;
}}
.bind-row .bind-key {{ color: #9fd4ff; font-weight: 700; }}
.bind-row.capturing .bind-key {{ color: #ffd479; }}
.bind-row.focused label {{ color: #0d1017; }}
.bind-row.focused .bind-key {{ color: #0b3a78; }}
.bind-row.capturing.focused .bind-key {{ color: #7a4a00; }}
"""
    return css.encode("utf-8"), scale


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

class TVTerminal(Gtk.Window):
    def __init__(self, backdrop_pixbuf=None):
        super().__init__(title="TV Terminal")
        self.connect("destroy", Gtk.main_quit)
        self.connect("key-press-event", self.on_window_key)

        self.screen_w, self.screen_h = get_display_size()
        css_data, self.scale = build_css(self.screen_w, self.screen_h)

        self.set_default_size(min(self.screen_w, 1920), min(self.screen_h, 1080))
        self.fullscreen()

        # ---- RGBA window; we paint the blurred backdrop ourselves ----
        screen = Gdk.Screen.get_default()
        visual = screen.get_rgba_visual() if screen else None
        self.rgba_ok = bool(visual) and screen.is_composited()
        if self.rgba_ok:
            self.set_visual(visual)
        self.set_app_paintable(True)

        self.backdrop_pixbuf = backdrop_pixbuf
        self._backdrop_surface = None
        self._backdrop_size = (0, 0)
        if self.rgba_ok:
            # Painted BEHIND already-drawn content (DEST_OVER) so the translucent
            # terminal / keys blend with the blur regardless of how VTE clears.
            self.connect_after("draw", self.on_window_draw)
        else:
            self.connect("draw", self.on_window_draw)

        # ---- state ----
        self.current_layer = "letters"
        self.shift_active = False
        self.caps_active = False
        self.ctrl_active = False
        self.alt_active = False
        self.pending_dead = None
        self.focus_row = 0
        self.focus_col = 0
        self.key_buttons = []

        self.font_size = max(16, int(22 * self.scale))

        # focus_zone: "kb" | "dpad" | "zoom"
        self.focus_zone = "kb"
        self.dpad_focus = "enter"
        self.zoom_focus = 0          # 0 = zoom in, 1 = zoom out, 2 = binds menu
        self.dpad_buttons = {}
        self.zoom_buttons = []

        # keyboard modes
        self.osk_locked = False      # input disabled (external keyboard), still visible
        self.osk_visible = True

        # keybinds
        self.binds = load_binds()
        self._rebuild_lookup()
        self.binds_open = False
        self.binds_index = 0
        self.binds_rows = []
        self.capture_action = None
        self._capture_timeout = None
        self._toast_timeout = None

        provider = Gtk.CssProvider()
        provider.load_from_data(css_data)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        # ---- root: overlay (toast + menu) over the main column ----
        self.overlay = Gtk.Overlay()
        self.add(self.overlay)

        self.vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.overlay.add(self.vbox)

        # ---- Terminal panel (rounded, translucent) ----
        m = int(12 * self.scale)
        self.term_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.term_panel.set_margin_start(m)
        self.term_panel.set_margin_end(m)
        self.term_panel.set_margin_top(m)
        self.term_panel.set_margin_bottom(int(6 * self.scale))
        self.term_panel.connect("draw", self.on_panel_draw_before)
        self.term_panel.connect_after("draw", self.on_panel_draw_after)
        self.vbox.pack_start(self.term_panel, True, True, 0)

        self.terminal = Vte.Terminal()
        self.terminal.set_cursor_blink_mode(Vte.CursorBlinkMode.ON)
        self.terminal.set_scroll_on_output(True)
        self.terminal.set_scroll_on_keystroke(True)
        self.terminal.set_mouse_autohide(True)
        self.apply_font()

        alpha = PANEL_ALPHA if self.rgba_ok else 1.0
        self.terminal.set_color_background(Gdk.RGBA(0.04, 0.05, 0.08, alpha))
        self.terminal.set_color_foreground(Gdk.RGBA(0.88, 0.92, 0.92, 1.0))
        self.terminal.set_color_cursor(Gdk.RGBA(0.30, 0.90, 0.65, 1.0))

        self.terminal.spawn_async(
            Vte.PtyFlags.DEFAULT,
            os.environ.get("HOME", "/"),
            [os.environ.get("SHELL", "/bin/bash")],
            [], GLib.SpawnFlags.DEFAULT, None, None, -1, None, None,
        )
        self.terminal.connect("child-exited", lambda *a: Gtk.main_quit())
        self.term_panel.pack_start(self.terminal, True, True, 0)

        # ---- Keyboard area: [D-pad] [main keys] [zoom + binds] ----
        self.kb_outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.kb_outer.get_style_context().add_class("keyboard")
        self.kb_outer.set_hexpand(True)
        self.vbox.pack_start(self.kb_outer, False, False, 0)

        self.dpad_box = self.build_dpad()
        self.kb_outer.pack_start(self.dpad_box, False, False, 4)

        center_wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        center_wrap.set_hexpand(True)
        self.kb_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.kb_box.set_halign(Gtk.Align.CENTER)
        self.kb_box.set_valign(Gtk.Align.CENTER)
        center_wrap.pack_start(self.kb_box, True, True, 0)
        self.kb_outer.pack_start(center_wrap, True, True, 0)

        self.zoom_box = self.build_zoom()
        self.kb_outer.pack_end(self.zoom_box, False, False, 4)

        self.build_keyboard()
        self.update_focus_visual()

        # ---- toast ----
        self.toast = Gtk.Label(label="")
        self.toast.get_style_context().add_class("toast")
        self.toast.set_halign(Gtk.Align.END)
        self.toast.set_valign(Gtk.Align.START)
        self.toast.set_margin_top(m + int(10 * self.scale))
        self.toast.set_margin_end(m + int(14 * self.scale))
        self.toast.set_no_show_all(True)
        self.overlay.add_overlay(self.toast)
        self.overlay.set_overlay_pass_through(self.toast, True)

        # ---- keybinds menu ----
        self.binds_panel = self.build_binds_panel()
        self.overlay.add_overlay(self.binds_panel)

        self.show_all()
        self.toast.hide()
        self.binds_panel.hide()
        self.terminal.grab_focus()

    # ------------------------------------------------------------------
    # Backdrop / drawing
    # ------------------------------------------------------------------
    def _make_backdrop_surface(self, w, h):
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        cr = cairo.Context(surf)
        if self.backdrop_pixbuf is not None:
            pw = self.backdrop_pixbuf.get_width()
            ph = self.backdrop_pixbuf.get_height()
            cr.scale(w / float(pw), h / float(ph))
            Gdk.cairo_set_source_pixbuf(cr, self.backdrop_pixbuf, 0, 0)
            cr.get_source().set_filter(cairo.FILTER_BILINEAR)
            cr.paint()
        else:
            # Fallback when no screenshot tool is available
            g = cairo.LinearGradient(0, 0, w, h)
            g.add_color_stop_rgb(0.0, 0.10, 0.12, 0.20)
            g.add_color_stop_rgb(0.5, 0.20, 0.16, 0.24)
            g.add_color_stop_rgb(1.0, 0.07, 0.14, 0.20)
            cr.set_source(g)
            cr.paint()
        return surf

    def invalidate_backdrop(self):
        self._backdrop_surface = None
        self.queue_draw()

    def on_window_draw(self, widget, cr):
        w = widget.get_allocated_width()
        h = widget.get_allocated_height()
        if w < 1 or h < 1:
            return False
        if self._backdrop_surface is None or self._backdrop_size != (w, h):
            self._backdrop_surface = self._make_backdrop_surface(w, h)
            self._backdrop_size = (w, h)
        cr.save()
        cr.set_operator(cairo.OPERATOR_DEST_OVER if self.rgba_ok else cairo.OPERATOR_OVER)
        cr.set_source_surface(self._backdrop_surface, 0, 0)
        cr.paint()
        cr.restore()
        return False

    def on_panel_draw_before(self, widget, cr):
        # Clip children (VTE) to the rounded panel shape
        rounded_rect(cr, 0, 0, widget.get_allocated_width(),
                     widget.get_allocated_height(), PANEL_RADIUS * self.scale)
        cr.clip()
        return False

    def on_panel_draw_after(self, widget, cr):
        rounded_rect(cr, 0.5, 0.5, widget.get_allocated_width() - 1,
                     widget.get_allocated_height() - 1, PANEL_RADIUS * self.scale)
        cr.set_source_rgba(1, 1, 1, 0.08)
        cr.set_line_width(1.0)
        cr.stroke()
        return False

    def refresh_backdrop(self):
        """Hide the window for a moment, re-shoot the desktop, blur once, cache."""
        self.show_toast("Refreshing background…")
        self.set_opacity(0.0)

        def _do():
            pb = prepare_backdrop(reuse_cache=False)
            if pb is not None:
                self.backdrop_pixbuf = pb
                self.invalidate_backdrop()
            self.set_opacity(1.0)
            self.show_toast("Background updated" if pb is not None else "No screenshot tool found")
            return False

        GLib.timeout_add(450, _do)

    # ------------------------------------------------------------------
    # Toast
    # ------------------------------------------------------------------
    def show_toast(self, msg, ms=1800):
        if self._toast_timeout:
            GLib.source_remove(self._toast_timeout)
            self._toast_timeout = None
        if not msg:
            self.toast.hide()
            return
        self.toast.set_text(msg)
        self.toast.show()
        self._toast_timeout = GLib.timeout_add(ms, self._hide_toast)

    def _hide_toast(self):
        self._toast_timeout = None
        self.toast.hide()
        return False

    def update_status(self, msg):
        self.show_toast(msg)

    # ------------------------------------------------------------------
    # Font / zoom
    # ------------------------------------------------------------------
    def apply_font(self):
        self.terminal.set_font(Pango.FontDescription(f"Monospace {self.font_size}"))

    def zoom_in(self):
        if self.font_size < FONT_MAX:
            self.font_size = min(FONT_MAX, self.font_size + FONT_STEP)
            self.apply_font()
        self.show_toast(f"Font size: {self.font_size}")

    def zoom_out(self):
        if self.font_size > FONT_MIN:
            self.font_size = max(FONT_MIN, self.font_size - FONT_STEP)
            self.apply_font()
        self.show_toast(f"Font size: {self.font_size}")

    # ------------------------------------------------------------------
    # Side panels
    # ------------------------------------------------------------------
    def build_dpad(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        outer.set_valign(Gtk.Align.CENTER)
        outer.get_style_context().add_class("side-panel")

        side = int(44 * self.scale)
        enter_w = int(side * 1.5)

        def make_btn(label, name, extra_class=None):
            btn = Gtk.Button(label=label)
            ctx = btn.get_style_context()
            ctx.add_class("side-key")
            ctx.add_class("dpad")
            if extra_class:
                ctx.add_class(extra_class)
            btn.set_size_request(side if name != "enter" else enter_w, side)
            btn.set_can_focus(True)
            btn.connect("clicked", self.on_dpad_clicked, name)
            self.dpad_buttons[name] = btn
            return btn

        row0 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3)
        row0.set_halign(Gtk.Align.CENTER)
        row0.pack_start(make_btn("↑", "up"), False, False, 0)
        outer.pack_start(row0, False, False, 0)

        row1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3)
        row1.set_halign(Gtk.Align.CENTER)
        row1.pack_start(make_btn("←", "left"), False, False, 0)
        row1.pack_start(make_btn("Enter", "enter", "enter-key"), False, False, 0)
        row1.pack_start(make_btn("→", "right"), False, False, 0)
        outer.pack_start(row1, False, False, 0)

        row2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3)
        row2.set_halign(Gtk.Align.CENTER)
        row2.pack_start(make_btn("↓", "down"), False, False, 0)
        outer.pack_start(row2, False, False, 0)
        return outer

    def build_zoom(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        outer.set_valign(Gtk.Align.CENTER)
        outer.get_style_context().add_class("side-panel")

        side = int(48 * self.scale)
        self.zoom_buttons = []
        # order matters: index 0 = in, 1 = out, 2 = binds menu
        for label, action in (("+", "in"), ("−", "out"), ("⚙", "binds")):
            btn = Gtk.Button(label=label)
            btn.get_style_context().add_class("side-key")
            btn.get_style_context().add_class("zoom-key")
            btn.set_size_request(side, side)
            btn.set_can_focus(True)
            btn.connect("clicked", self.on_zoom_clicked, action)
            outer.pack_start(btn, False, False, 0)
            self.zoom_buttons.append(btn)
        return outer

    def on_dpad_clicked(self, widget, name):
        seq = {"up": "\x1b[A", "down": "\x1b[B", "right": "\x1b[C",
               "left": "\x1b[D", "enter": "\r"}
        if name in seq:
            self.feed(seq[name])

    def on_zoom_clicked(self, widget, action):
        if action == "in":
            self.zoom_in()
        elif action == "out":
            self.zoom_out()
        elif action == "binds":
            self.open_binds_menu()

    # ------------------------------------------------------------------
    # Keyboard build
    # ------------------------------------------------------------------
    def get_layout(self):
        if self.current_layer == "numbers":
            return LAYER_NUMBERS
        if self.current_layer == "symbols":
            return LAYER_SYMBOLS
        return LAYER_LETTERS

    def build_keyboard(self):
        for child in self.kb_box.get_children():
            self.kb_box.remove(child)
        self.key_buttons = []

        layout = self.get_layout()
        base_w = int(46 * self.scale)
        wide_w = int(64 * self.scale)
        space_w = int(220 * self.scale)

        for r, row in enumerate(layout):
            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
            hbox.set_halign(Gtk.Align.CENTER)
            hbox.set_homogeneous(False)

            row_buttons = []
            for c, label in enumerate(row):
                btn = Gtk.Button(label=self.display_label(label))
                ctx = btn.get_style_context()
                ctx.add_class("key")

                if label in SPECIAL_KEYS:
                    ctx.add_class("special")
                if label in ("123", "ABC", "Sym"):
                    ctx.add_class("layer")
                if label == "Exit":
                    ctx.add_class("exit")
                if label == " ":
                    ctx.add_class("space")
                    btn.set_size_request(space_w, -1)
                elif label in WIDER_KEYS:
                    btn.set_size_request(wide_w, -1)
                else:
                    btn.set_size_request(base_w, -1)

                if label == "Shift" and self.shift_active:
                    ctx.add_class("modifier-active")
                if label == "Caps" and self.caps_active:
                    ctx.add_class("modifier-active")
                if label == "Ctrl" and self.ctrl_active:
                    ctx.add_class("modifier-active")
                if label == "Alt" and self.alt_active:
                    ctx.add_class("modifier-active")

                btn.connect("clicked", self.on_key_clicked, r, c)
                btn.set_can_focus(True)
                hbox.pack_start(btn, False, False, 0)
                row_buttons.append(btn)

            self.kb_box.pack_start(hbox, False, False, 0)
            self.key_buttons.append(row_buttons)

        self.kb_box.show_all()
        self.focus_row = min(self.focus_row, len(self.key_buttons) - 1)
        self.focus_col = min(self.focus_col, len(self.key_buttons[self.focus_row]) - 1)

    def display_label(self, label):
        if label in SPECIAL_KEYS:
            return "Space" if label == " " else label
        if self.current_layer == "letters":
            if self.shift_active or self.caps_active:
                return SHIFT_MAP.get(label, label.upper())
        return label

    # ------------------------------------------------------------------
    # OSK modes (lock / hide)
    # ------------------------------------------------------------------
    @property
    def osk_active(self):
        return self.osk_visible and not self.osk_locked

    def set_osk_locked(self, locked):
        self.osk_locked = locked
        ctx = self.kb_outer.get_style_context()
        if locked:
            ctx.add_class("osk-locked")
        else:
            ctx.remove_class("osk-locked")
        # Visible but inert: no clicks, no remote focus
        self.kb_box.set_sensitive(not locked)
        self.dpad_box.set_sensitive(not locked)
        self.update_focus_visual()
        self.terminal.grab_focus()
        self.show_toast("Keyboard input disabled — external keyboard mode" if locked
                        else "Keyboard input enabled")

    def set_osk_visible(self, visible):
        self.osk_visible = visible
        if visible:
            self.kb_outer.show()
        else:
            self.kb_outer.hide()
        self.update_focus_visual()
        self.terminal.grab_focus()
        self.show_toast("Keyboard shown" if visible else "Keyboard hidden")

    # ------------------------------------------------------------------
    # Focus handling (remote navigation)
    # ------------------------------------------------------------------
    def clear_all_focus_styles(self):
        for row in self.key_buttons:
            for btn in row:
                btn.get_style_context().remove_class("focused")
        for btn in self.dpad_buttons.values():
            btn.get_style_context().remove_class("focused")
        for btn in self.zoom_buttons:
            btn.get_style_context().remove_class("focused")

    def update_focus_visual(self):
        self.clear_all_focus_styles()
        if not self.osk_active:
            return
        if self.focus_zone == "kb":
            if self.key_buttons:
                r = min(self.focus_row, len(self.key_buttons) - 1)
                c = min(self.focus_col, len(self.key_buttons[r]) - 1)
                self.key_buttons[r][c].get_style_context().add_class("focused")
        elif self.focus_zone == "dpad":
            btn = self.dpad_buttons.get(self.dpad_focus)
            if btn:
                btn.get_style_context().add_class("focused")
        elif self.focus_zone == "zoom":
            if self.zoom_buttons:
                idx = min(self.zoom_focus, len(self.zoom_buttons) - 1)
                self.zoom_buttons[idx].get_style_context().add_class("focused")

    def move_focus(self, d_row, d_col):
        if self.focus_zone == "kb":
            rows = len(self.key_buttons)
            if rows == 0:
                return
            if d_col < 0 and self.focus_col == 0:
                self.focus_zone = "dpad"
                self.dpad_focus = "enter"
                self.update_focus_visual()
                return
            cols = len(self.key_buttons[self.focus_row])
            if d_col > 0 and self.focus_col >= cols - 1:
                self.focus_zone = "zoom"
                self.zoom_focus = 0
                self.update_focus_visual()
                return
            new_r = (self.focus_row + d_row) % rows
            if d_col != 0:
                new_c = (self.focus_col + d_col) % len(self.key_buttons[new_r])
            else:
                new_c = min(self.focus_col, len(self.key_buttons[new_r]) - 1)
            self.focus_row, self.focus_col = new_r, new_c
            self.update_focus_visual()

        elif self.focus_zone == "dpad":
            nav = {
                "up":    {"up": "up", "down": "enter", "left": "up", "right": "up"},
                "left":  {"up": "up", "down": "down", "left": "left", "right": "enter"},
                "enter": {"up": "up", "down": "down", "left": "left", "right": "right"},
                "right": {"up": "up", "down": "down", "left": "enter", "right": "kb"},
                "down":  {"up": "enter", "down": "down", "left": "down", "right": "down"},
            }
            direction = None
            if d_row < 0:
                direction = "up"
            elif d_row > 0:
                direction = "down"
            elif d_col < 0:
                direction = "left"
            elif d_col > 0:
                direction = "right"
            if direction:
                nxt = nav[self.dpad_focus][direction]
                if nxt == "kb":
                    self.focus_zone = "kb"
                    self.focus_col = 0
                else:
                    self.dpad_focus = nxt
            self.update_focus_visual()

        elif self.focus_zone == "zoom":
            if d_row != 0:
                self.zoom_focus = (self.zoom_focus + d_row) % len(self.zoom_buttons)
            if d_col < 0:
                self.focus_zone = "kb"
                if self.key_buttons:
                    self.focus_col = len(self.key_buttons[self.focus_row]) - 1
            self.update_focus_visual()

    def activate_focused(self):
        if self.focus_zone == "kb":
            if self.key_buttons:
                self.on_key_clicked(None, self.focus_row, self.focus_col)
        elif self.focus_zone == "dpad":
            self.on_dpad_clicked(None, self.dpad_focus)
        elif self.focus_zone == "zoom":
            action = ("in", "out", "binds")[min(self.zoom_focus, 2)]
            self.on_zoom_clicked(None, action)

    # ------------------------------------------------------------------
    # Key handling (on-screen)
    # ------------------------------------------------------------------
    def on_key_clicked(self, widget, row, col):
        layout = self.get_layout()
        self.handle_key(layout[row][col])

    def _switch_layer(self, layer):
        self.current_layer = layer
        self.shift_active = False
        self.build_keyboard()
        self.update_focus_visual()

    def handle_key(self, label):
        if label == "Exit":
            Gtk.main_quit()
            return
        if label == "123":
            return self._switch_layer("numbers")
        if label == "ABC":
            return self._switch_layer("letters")
        if label == "Sym":
            return self._switch_layer("symbols")

        if label in ("Shift", "Caps", "Ctrl", "Alt"):
            attr = {"Shift": "shift_active", "Caps": "caps_active",
                    "Ctrl": "ctrl_active", "Alt": "alt_active"}[label]
            setattr(self, attr, not getattr(self, attr))
            self.build_keyboard()
            self.update_focus_visual()
            return

        if label in KEY_SEQUENCES:
            self.feed(KEY_SEQUENCES[label])
            return

        if label in DEAD_KEYS and self.current_layer == "letters":
            self.pending_dead = DEAD_KEYS[label]
            self.update_status(f"Accent pending: {label}")
            return

        char = label
        if self.current_layer == "letters":
            if self.shift_active or self.caps_active:
                char = SHIFT_MAP.get(label, label.upper())
            if self.pending_dead:
                combined = ACCENT_MAP.get((self.pending_dead, char))
                if combined:
                    char = combined
                self.pending_dead = None
                self.update_status("")

        if self.ctrl_active and len(char) == 1:
            code = ord(char.upper()) - 64
            self.feed(chr(code) if 1 <= code <= 26 else char)
            self.ctrl_active = False
            self.build_keyboard()
            self.update_focus_visual()
            return

        self.feed(char)

        if self.shift_active and self.current_layer == "letters":
            self.shift_active = False
            self.build_keyboard()
            self.update_focus_visual()

    def feed(self, text):
        self.terminal.feed_child(text.encode("utf-8"))

    # ------------------------------------------------------------------
    # Remote keybind actions
    # ------------------------------------------------------------------
    def _rebuild_lookup(self):
        self.binds_lookup = {}
        for action, keys in self.binds.items():
            for k in keys:
                self.binds_lookup[k] = action

    def run_action(self, action):
        if action == "nav_up":
            self.move_focus(-1, 0)
        elif action == "nav_down":
            self.move_focus(1, 0)
        elif action == "nav_left":
            self.move_focus(0, -1)
        elif action == "nav_right":
            self.move_focus(0, 1)
        elif action == "select":
            self.activate_focused()
        elif action == "layer_cycle":
            order = ["letters", "numbers", "symbols"]
            self._switch_layer(order[(order.index(self.current_layer) + 1) % 3])
        elif action == "osk_lock":
            self.set_osk_locked(not self.osk_locked)
        elif action == "osk_toggle":
            self.set_osk_visible(not self.osk_visible)
        elif action == "zoom_in":
            self.zoom_in()
        elif action == "zoom_out":
            self.zoom_out()
        elif action == "open_binds":
            self.open_binds_menu()
        elif action == "refresh_backdrop":
            self.refresh_backdrop()
        elif action == "exit":
            Gtk.main_quit()
        elif action in SEND_SEQUENCES:
            self.feed(SEND_SEQUENCES[action])

    def on_window_key(self, widget, event):
        if self.capture_action:
            return self.on_capture_key(event)
        if self.binds_open:
            return self.on_binds_menu_key(event)

        ctrl_shift = (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK)
        if (event.state & ctrl_shift) == ctrl_shift and \
                Gdk.keyval_to_lower(event.keyval) == Gdk.KEY_k:
            self.open_binds_menu()   # emergency way in, independent of the binds
            return True

        name = key_name_from_event(event)
        action = None if (event.state & MOD_BLOCK_MASK) else self.binds_lookup.get(name)

        if action:
            if action in OSK_ONLY_ACTIONS and not self.osk_active:
                return False          # let it reach the terminal (external keyboard)
            self.run_action(action)
            return True

        if self.osk_active:
            key = event.keyval
            if key == Gdk.KEY_Escape and self.pending_dead:
                self.pending_dead = None
                self.update_status("")
                return True
            if name in LEGACY_ZOOM_IN:
                self.zoom_in()
                return True
            if name in LEGACY_ZOOM_OUT:
                self.zoom_out()
                return True
        return False

    # ------------------------------------------------------------------
    # Keybinds menu
    # ------------------------------------------------------------------
    def build_binds_panel(self):
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        panel.get_style_context().add_class("binds-panel")
        panel.set_halign(Gtk.Align.CENTER)
        panel.set_valign(Gtk.Align.CENTER)
        panel.set_size_request(int(760 * self.scale), -1)

        title = Gtk.Label(label="Remote key binds")
        title.get_style_context().add_class("binds-title")
        title.set_xalign(0)
        panel.pack_start(title, False, False, 0)

        hint = Gtk.Label(
            label="↑↓ choose  •  OK: press the remote key to assign  •  Del: clear  •  Esc: close"
        )
        hint.get_style_context().add_class("binds-hint")
        hint.set_xalign(0)
        panel.pack_start(hint, False, False, 0)

        self.binds_scroll = Gtk.ScrolledWindow()
        self.binds_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.binds_scroll.set_min_content_height(int(430 * self.scale))
        self.binds_scroll.set_max_content_height(int(430 * self.scale))
        self.binds_scroll.set_propagate_natural_height(False)
        panel.pack_start(self.binds_scroll, True, True, 0)

        listbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        self.binds_scroll.add(listbox)

        self.binds_rows = []

        def add_row(kind, action, text):
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            box.get_style_context().add_class("bind-row")
            left = Gtk.Label(label=text)
            left.set_xalign(0)
            left.set_hexpand(True)
            right = Gtk.Label(label="")
            right.set_xalign(1)
            right.get_style_context().add_class("bind-key")
            box.pack_start(left, True, True, 0)
            box.pack_end(right, False, False, 0)
            listbox.pack_start(box, False, False, 0)
            self.binds_rows.append({"kind": kind, "action": action,
                                    "box": box, "keys": right})

        for group_title, items in ACTION_GROUPS:
            g = Gtk.Label(label=group_title.upper())
            g.get_style_context().add_class("binds-group")
            g.set_xalign(0)
            listbox.pack_start(g, False, False, 0)
            for action, label in items:
                add_row("action", action, label)

        sep = Gtk.Label(label="")
        listbox.pack_start(sep, False, False, 0)
        add_row("reset", None, "Reset all binds to defaults")
        add_row("close", None, "Close")

        self.refresh_bind_labels()
        return panel

    def refresh_bind_labels(self):
        for row in self.binds_rows:
            if row["kind"] != "action":
                continue
            keys = self.binds.get(row["action"], [])
            row["keys"].set_text(", ".join(pretty_key(k) for k in keys) if keys else "—")
            row["box"].get_style_context().remove_class("capturing")

    def update_binds_focus(self):
        for i, row in enumerate(self.binds_rows):
            ctx = row["box"].get_style_context()
            if i == self.binds_index:
                ctx.add_class("focused")
            else:
                ctx.remove_class("focused")
        GLib.idle_add(self._scroll_to_focused_bind)

    def _scroll_to_focused_bind(self):
        if not self.binds_rows:
            return False
        box = self.binds_rows[self.binds_index]["box"]
        adj = self.binds_scroll.get_vadjustment()
        a = box.get_allocation()
        top, bottom = a.y - 6, a.y + a.height + 6
        page = adj.get_page_size()
        v = adj.get_value()
        if self.binds_index == 0:
            adj.set_value(0)
        elif top < v:
            adj.set_value(top)
        elif bottom > v + page:
            adj.set_value(bottom - page)
        return False

    def open_binds_menu(self):
        if self.binds_open:
            return
        self.binds_index = 0
        self.refresh_bind_labels()
        self.binds_panel.show_all()
        self.binds_open = True
        self.update_binds_focus()

    def close_binds_menu(self):
        self.cancel_capture()
        self.binds_open = False
        self.binds_panel.hide()
        self.terminal.grab_focus()

    def on_binds_menu_key(self, event):
        key = event.keyval
        name = key_name_from_event(event)
        bound = self.binds_lookup.get(name)
        n = len(self.binds_rows)

        if key == Gdk.KEY_Escape:
            self.close_binds_menu()
        elif key in (Gdk.KEY_Up, Gdk.KEY_KP_Up) or bound == "nav_up":
            self.binds_index = (self.binds_index - 1) % n
            self.update_binds_focus()
        elif key in (Gdk.KEY_Down, Gdk.KEY_KP_Down) or bound == "nav_down":
            self.binds_index = (self.binds_index + 1) % n
            self.update_binds_focus()
        elif key in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_Select,
                     Gdk.KEY_space) or bound == "select":
            self.activate_bind_row()
        elif key in (Gdk.KEY_Delete, Gdk.KEY_BackSpace):
            row = self.binds_rows[self.binds_index]
            if row["kind"] == "action":
                self.binds[row["action"]] = []
                self._rebuild_lookup()
                save_binds(self.binds)
                self.refresh_bind_labels()
        return True   # menu swallows everything

    def activate_bind_row(self):
        row = self.binds_rows[self.binds_index]
        if row["kind"] == "close":
            self.close_binds_menu()
        elif row["kind"] == "reset":
            self.binds = {a: list(DEFAULT_BINDS.get(a, [])) for a in ACTION_LABELS}
            self._rebuild_lookup()
            save_binds(self.binds)
            self.refresh_bind_labels()
            self.show_toast("Binds reset to defaults")
        else:
            self.start_capture(row["action"])

    def start_capture(self, action):
        self.capture_action = action
        row = self.binds_rows[self.binds_index]
        row["keys"].set_text("Press a key…")
        row["box"].get_style_context().add_class("capturing")
        # auto-cancel so a mis-click can never lock the menu
        self._capture_timeout = GLib.timeout_add_seconds(6, self._capture_timed_out)

    def _capture_timed_out(self):
        self._capture_timeout = None
        self.cancel_capture()
        return False

    def cancel_capture(self):
        if self._capture_timeout:
            GLib.source_remove(self._capture_timeout)
            self._capture_timeout = None
        if self.capture_action:
            self.capture_action = None
            self.refresh_bind_labels()

    def on_capture_key(self, event):
        name = Gdk.keyval_name(Gdk.keyval_to_lower(event.keyval)) or ""
        if name in PURE_MODIFIERS:
            return True            # wait for a real key
        name = key_name_from_event(event)
        action = self.capture_action
        if self._capture_timeout:
            GLib.source_remove(self._capture_timeout)
            self._capture_timeout = None
        self.capture_action = None

        stolen = None
        for a, keys in self.binds.items():
            if a != action and name in keys:
                keys.remove(name)
                stolen = a
        self.binds[action] = [name]
        self._rebuild_lookup()
        save_binds(self.binds)
        self.refresh_bind_labels()
        if stolen:
            self.show_toast(f"{pretty_key(name)} moved from “{ACTION_LABELS[stolen]}”", 2600)
        else:
            self.show_toast(f"{ACTION_LABELS[action]}: {pretty_key(name)}")
        return True


def main():
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    reuse = "--reuse-backdrop" in sys.argv
    Gtk.init([])
    # Must happen BEFORE the window exists, so the screenshot shows the real desktop.
    backdrop = prepare_backdrop(reuse_cache=reuse)
    TVTerminal(backdrop_pixbuf=backdrop)
    Gtk.main()


if __name__ == "__main__":
    main()
