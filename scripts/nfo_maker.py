#!/usr/bin/env python3
"""
NFO Maker - TUI tool for creating Kodi/Emby-style NFO files and artwork
for Movies and TV Shows.

Supports mouse + keyboard navigation.
"""

from __future__ import annotations

import os
import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
    DirectoryTree,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    RadioButton,
    RadioSet,
    Static,
    TextArea,
)
from textual.events import Click
from textual.message import Message

# Optional image support
try:
    from textual_image.widget import Image as TerminalImage
    HAS_IMAGE = True
except ImportError:
    HAS_IMAGE = False
    TerminalImage = None  # type: ignore


# ---------------------------------------------------------------------------
# Configuration – change the default save path here if desired
# ---------------------------------------------------------------------------
DEFAULT_SAVE_PATH = os.path.expanduser("~/Videos")

VIDEO_EXTENSIONS = {
    ".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".webm",
    ".m4v", ".mpg", ".mpeg", ".ts", ".m2ts", ".vob", ".ogv",
}

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}


def sanitize_filename(name: str) -> str:
    """Make a string safe for use as a filename.

    Colons become " - " so "Pokémon: Generations" → "Pokémon - Generations".
    Other Windows/path-forbidden characters become a single dash.
    """
    # Preserve meaning of ":" as a readable separator
    name = name.replace(":", " - ")
    # Path separators and remaining Windows-forbidden characters
    name = re.sub(r'[\\/*?"<>|]', "-", name)
    # Collapse runs of whitespace
    name = re.sub(r"\s+", " ", name)
    # Collapse runs of dashes / " - - "
    name = re.sub(r"(?:\s*-\s*)+", " - ", name)
    return name.strip(" -") or "Untitled"


def escape_xml(text: str) -> str:
    """Basic XML escaping."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def generate_nfo(title: str, year: str, plot: str, media_type: str) -> str:
    """Generate a minimal NFO XML string."""
    root_tag = "movie" if media_type == "movie" else "tvshow"
    root = ET.Element(root_tag)
    ET.SubElement(root, "title").text = title
    ET.SubElement(root, "year").text = year
    ET.SubElement(root, "plot").text = plot

    def indent(elem: ET.Element, level: int = 0) -> None:
        i = "\n" + level * "  "
        if len(elem):
            if not elem.text or not elem.text.strip():
                elem.text = i + "  "
            for child in elem:
                indent(child, level + 1)
            if not child.tail or not child.tail.strip():  # type: ignore[name-defined]
                child.tail = i
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i

    indent(root)
    xml_decl = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    return xml_decl + ET.tostring(root, encoding="unicode") + "\n"


def list_videos(directory: Path) -> list[Path]:
    """Return sorted list of video files in the given directory."""
    files = []
    try:
        for p in directory.iterdir():
            if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS:
                files.append(p)
    except PermissionError:
        pass
    return sorted(files, key=lambda p: p.name.lower())


# ---------------------------------------------------------------------------
# Screens
# ---------------------------------------------------------------------------

class VideoListScreen(Screen):
    """Initial screen: list video files in the current working directory."""

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.videos: list[Path] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Label("Select a video file (Enter / click)  |  q = Quit  |  r = Refresh", id="hint")
        yield ListView(id="video-list")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_list()

    def refresh_list(self) -> None:
        self.videos = list_videos(Path.cwd())
        lv = self.query_one("#video-list", ListView)
        lv.clear()
        if not self.videos:
            lv.append(ListItem(Label("[dim]No video files found in current directory[/]")))
        else:
            for v in self.videos:
                lv.append(ListItem(Label(v.name), name=str(v)))

    def action_refresh(self) -> None:
        self.refresh_list()
        self.notify("List refreshed")

    @on(ListView.Selected)
    def on_video_selected(self, event: ListView.Selected) -> None:
        item = event.item
        if item and item.name:
            path = Path(item.name)
            self.app.push_screen(EditScreen(path))


class FileBrowserScreen(ModalScreen[Optional[Path]]):
    """Pseudo file manager starting at the user's home directory for selecting an image."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("q", "cancel", "Cancel"),
    ]

    def __init__(self, start_path: Optional[Path] = None) -> None:
        super().__init__()
        self.start_path = start_path or Path.home()
        self.selected: Optional[Path] = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("Browse and select an image  |  Esc / q = Cancel", id="browser-hint")
        yield DirectoryTree(str(self.start_path), id="dir-tree")
        with Horizontal(id="browser-buttons"):
            yield Button("Select", variant="primary", id="btn-select")
            yield Button("Cancel", variant="error", id="btn-cancel")
        yield Footer()

    @on(DirectoryTree.FileSelected)
    def on_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        path = event.path
        if path.suffix.lower() in IMAGE_EXTENSIONS:
            self.selected = path
            self.query_one("#btn-select", Button).disabled = False
            self.notify(f"Selected: {path.name}")
        else:
            self.selected = None
            self.query_one("#btn-select", Button).disabled = True
            self.notify("Not an image file", severity="warning")

    @on(Button.Pressed, "#btn-select")
    def on_select(self) -> None:
        if self.selected:
            self.dismiss(self.selected)
        else:
            self.notify("No image selected", severity="error")

    @on(Button.Pressed, "#btn-cancel")
    def on_cancel_btn(self) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class EditScreen(Screen):
    """Main editing form for title, year, plot, type, artwork and save path."""

    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("ctrl+s", "save", "Save"),
    ]

    # (storage attr, image widget id, placeholder id, button id, suffix label)
    ARTWORK_SLOTS = (
        ("poster_path", "poster-image", "poster-placeholder", "btn-poster", "Poster"),
        ("banner_path", "banner-image", "banner-placeholder", "btn-banner", "Banner"),
        ("bg_path", "bg-image", "bg-placeholder", "btn-bg", "BG"),
    )

    def __init__(self, video_path: Path) -> None:
        super().__init__()
        self.video_path = video_path
        self.poster_path: Optional[Path] = None
        self.banner_path: Optional[Path] = None
        self.bg_path: Optional[Path] = None
        self.initial_title = video_path.stem

    def _artwork_row(self, image_id: str, placeholder_id: str, button_id: str, label: str) -> ComposeResult:
        yield Label(f"{label}  (click image or button to change)")
        with Horizontal(classes="art-row"):
            if HAS_IMAGE:
                img = TerminalImage(id=image_id, classes="art-preview")
                img.can_focus = True
                yield img
            else:
                yield Static(
                    f"[dim]No preview\nClick or use button[/]",
                    id=placeholder_id,
                    classes="art-preview",
                )
            yield Button(f"Select {label}…", id=button_id, variant="default")

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with VerticalScroll(id="form"):
            yield Label(f"Video: [bold]{self.video_path.name}[/]", id="video-label")

            yield Label("Media Type")
            with RadioSet(id="media-type"):
                yield RadioButton("Movie", value=True, id="type-movie")
                yield RadioButton("TV Show", id="type-tvshow")

            yield Label("Title")
            yield Input(value=self.initial_title, placeholder="Title of the movie/show", id="title")

            yield Label("Year")
            yield Input(placeholder="e.g. 1994", id="year", type="integer")

            yield Label("Plot / Description")
            yield TextArea(id="plot", language=None)

            yield from self._artwork_row("poster-image", "poster-placeholder", "btn-poster", "Poster")
            yield from self._artwork_row("banner-image", "banner-placeholder", "btn-banner", "Banner")
            yield from self._artwork_row("bg-image", "bg-placeholder", "btn-bg", "Background")

            yield Label("Save Path  (files will be MOVED here)")
            yield Input(value=DEFAULT_SAVE_PATH, placeholder="~/Videos or /mnt/sdb2/…", id="save-path")

            with Horizontal(id="action-row"):
                yield Button("Save & Move", variant="success", id="btn-save")
                yield Button("Back", variant="default", id="btn-back")

        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#title", Input).focus()

    def action_back(self) -> None:
        self.app.pop_screen()

    @on(Button.Pressed, "#btn-back")
    def on_back(self) -> None:
        self.action_back()

    # ----- artwork pickers -----

    def _open_browser_for(self, attr: str, image_id: str, placeholder_id: str, label: str) -> None:
        def callback(path: Optional[Path]) -> None:
            if path is None:
                return
            setattr(self, attr, path)
            if HAS_IMAGE:
                img = self.query_one(f"#{image_id}", TerminalImage)
                img.image = str(path)
            else:
                ph = self.query_one(f"#{placeholder_id}", Static)
                ph.update(f"[green]Selected:[/] {path.name}")
            self.notify(f"{label} set: {path.name}")

        self.app.push_screen(FileBrowserScreen(), callback)

    @on(Button.Pressed, "#btn-poster")
    def on_btn_poster(self) -> None:
        self._open_browser_for("poster_path", "poster-image", "poster-placeholder", "Poster")

    @on(Button.Pressed, "#btn-banner")
    def on_btn_banner(self) -> None:
        self._open_browser_for("banner_path", "banner-image", "banner-placeholder", "Banner")

    @on(Button.Pressed, "#btn-bg")
    def on_btn_bg(self) -> None:
        self._open_browser_for("bg_path", "bg-image", "bg-placeholder", "Background")

    @on(Click, "#poster-image")
    @on(Click, "#poster-placeholder")
    def on_poster_click(self) -> None:
        self._open_browser_for("poster_path", "poster-image", "poster-placeholder", "Poster")

    @on(Click, "#banner-image")
    @on(Click, "#banner-placeholder")
    def on_banner_click(self) -> None:
        self._open_browser_for("banner_path", "banner-image", "banner-placeholder", "Banner")

    @on(Click, "#bg-image")
    @on(Click, "#bg-placeholder")
    def on_bg_click(self) -> None:
        self._open_browser_for("bg_path", "bg-image", "bg-placeholder", "Background")

    # ----- save -----

    @on(Button.Pressed, "#btn-save")
    def on_save_btn(self) -> None:
        self.action_save()

    def _move_artwork(self, src: Optional[Path], dest_dir: Path, safe_title: str, suffix: str) -> Optional[str]:
        """Move an artwork file to dest_dir as '{safe_title}_{suffix}{ext}'. Returns dest name or None."""
        if not src or not src.is_file():
            return None
        ext = src.suffix.lower() or ".jpg"
        dest = dest_dir / f"{safe_title}_{suffix}{ext}"
        if src.resolve() != dest.resolve():
            shutil.move(str(src), str(dest))
        return dest.name

    def action_save(self) -> None:
        title = self.query_one("#title", Input).value.strip()
        year = self.query_one("#year", Input).value.strip()
        plot = self.query_one("#plot", TextArea).text.strip()
        save_path_str = self.query_one("#save-path", Input).value.strip()
        media_type_widget = self.query_one("#media-type", RadioSet)
        media_type = (
            "movie"
            if media_type_widget.pressed_button and media_type_widget.pressed_button.id == "type-movie"
            else "tvshow"
        )

        if not title:
            self.notify("Title is required", severity="error")
            return
        if not save_path_str:
            self.notify("Save path is required", severity="error")
            return

        safe_title = sanitize_filename(title)
        dest_dir = Path(os.path.expanduser(save_path_str)).resolve()

        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self.notify(f"Cannot create directory: {e}", severity="error")
            return

        video_ext = self.video_path.suffix
        dest_video = dest_dir / f"{safe_title}{video_ext}"
        dest_nfo = dest_dir / f"{safe_title}.nfo"

        if dest_video.exists() and dest_video.resolve() != self.video_path.resolve():
            self.notify(f"Target video already exists: {dest_video.name}", severity="error")
            return

        try:
            # 1. Write NFO (title in NFO keeps the original ":", only filenames are sanitized)
            nfo_content = generate_nfo(title, year, plot, media_type)
            dest_nfo.write_text(nfo_content, encoding="utf-8")

            # 2. Move video
            if self.video_path.resolve() != dest_video.resolve():
                shutil.move(str(self.video_path), str(dest_video))

            # 3. Move artwork with suffixes
            moved = [dest_video.name, dest_nfo.name]
            for attr, suffix in (
                ("poster_path", "Poster"),
                ("banner_path", "Banner"),
                ("bg_path", "BG"),
            ):
                name = self._move_artwork(getattr(self, attr), dest_dir, safe_title, suffix)
                if name:
                    moved.append(name)

            self.notify("Saved!\n" + "\n".join(moved), severity="information", timeout=8)
            self.app.pop_screen()
            if isinstance(self.app.screen, VideoListScreen):
                self.app.screen.refresh_list()

        except Exception as e:
            self.notify(f"Error while saving: {e}", severity="error")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

class NFOMakerApp(App):
    """Main application."""

    CSS = """
    Screen {
        background: $surface;
    }

    #hint, #browser-hint, #video-label {
        margin: 1 2;
        color: $text-muted;
    }

    #form {
        padding: 1 2;
        height: 1fr;
    }

    #form Label {
        margin-top: 1;
        text-style: bold;
    }

    #title, #year, #save-path {
        width: 100%;
        margin-bottom: 0;
    }

    #plot {
        height: 8;
        margin-bottom: 1;
    }

    .art-row {
        height: 12;
        margin: 1 0;
        align: left middle;
    }

    .art-preview {
        width: 28;
        height: 10;
        margin-right: 2;
        border: solid $accent;
        content-align: center middle;
    }

    .art-preview:hover {
        border: solid $success;
    }

    #action-row, #browser-buttons {
        margin-top: 1;
        height: auto;
        align: left middle;
    }

    #action-row Button, #browser-buttons Button {
        margin-right: 2;
    }

    #video-list {
        height: 1fr;
        margin: 0 1;
        border: solid $primary;
    }

    DirectoryTree {
        height: 1fr;
        margin: 0 1;
        border: solid $primary;
    }

    RadioSet {
        margin-bottom: 1;
    }
    """

    TITLE = "NFO Maker"
    SUB_TITLE = "Create NFO + artwork for Movies & TV Shows"

    def on_mount(self) -> None:
        self.push_screen(VideoListScreen())


def main() -> None:
    app = NFOMakerApp()
    app.run()


if __name__ == "__main__":
    main()
