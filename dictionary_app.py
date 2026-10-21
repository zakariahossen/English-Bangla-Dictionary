import ctypes
import ctypes.util
import json
import random
import sys
from bisect import bisect_left
from pathlib import Path
from string import Template

BASE_DIR = Path(__file__).resolve().parent
DICT_FILE = BASE_DIR / "dictionary.json"
FAV_FILE = BASE_DIR / "favorites.json"
FONT_DIR = BASE_DIR / "fonts"


def load_bundled_fonts():
    """Register every .ttf/.otf in ./fonts for this program only (via fontconfig).

    Runs BEFORE GTK is imported, so Pango sees the fonts from the very start.
    If anything fails, Pango simply falls back to a system Bengali font.
    """
    if not sys.platform.startswith("linux") or not FONT_DIR.is_dir():
        return
    try:
        lib_name = ctypes.util.find_library("fontconfig")
        if not lib_name:
            return
        fc = ctypes.CDLL(lib_name)
        fc.FcConfigAppFontAddFile.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        fc.FcConfigAppFontAddFile.restype = ctypes.c_int
        for font_file in sorted(FONT_DIR.glob("*.[to]tf")):
            fc.FcConfigAppFontAddFile(None, str(font_file).encode("utf-8"))
    except Exception:
        pass


load_bundled_fonts()

try:
    import gi

    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    from gi.repository import Gdk, GLib, Gtk, Pango
except (ImportError, ValueError):
    sys.exit(
        "GTK 3 bindings not found.\n"
        "Install them with:  sudo apt install python3-gi gir1.2-gtk-3.0"
    )

THEMES = {
    "light": {
        "bg": "#F3F5FA",
        "surface": "#FFFFFF",
        "card": "#F4F6FB",
        "text": "#1E2433",
        "muted": "#7A8296",
        "accent": "#4F46E5",
        "accent_fg": "#FFFFFF",
        "border": "#E1E5EF",
        "select": "#EEF0FF",
        "star": "#D97706",
    },
    "dark": {
        "bg": "#0E1320",
        "surface": "#171E2E",
        "card": "#1F2739",
        "text": "#E6EAF5",
        "muted": "#8D96AD",
        "accent": "#8B93FF",
        "accent_fg": "#0E1320",
        "border": "#2B3550",
        "select": "#27305A",
        "star": "#FBBF24",
    },
}

CSS = Template("""
window.dict-window { background-color: $bg; color: $text; }
.panel { background-color: $surface; border: 1px solid $border; border-radius: 14px; }
.muted { color: $muted; }
.app-title { font-size: 22px; font-weight: bold; }
.word { font-size: 32px; font-weight: bold; }
.bn {
    font-family: "Kalpurush", "Noto Sans Bengali", "Noto Serif Bengali", "Lohit Bengali",
                 "SolaimanLipi", "Siyam Rupali", "Nirmala UI", "Vrinda", sans-serif;
    font-size: 20px;
}
.bn-small { font-size: 15px; }

entry.dict-search {
    background-image: none; background-color: $card; color: $text;
    border: 2px solid $border; border-radius: 10px; box-shadow: none;
    padding: 8px 10px; min-height: 22px; font-size: 15px;
}
entry.dict-search:focus { border-color: $accent; }

button.dict-btn, button.dict-tab {
    background-image: none; box-shadow: none; text-shadow: none;
    border: none; border-radius: 8px; padding: 7px 16px;
    background-color: $card; color: $text;
}
button.dict-btn:hover, button.dict-tab:hover { background-color: $border; }
button.dict-btn.saved { color: $star; font-weight: bold; }
button.dict-tab { color: $muted; font-weight: bold; padding: 5px 14px; }
button.dict-tab:checked { background-color: $accent; color: $accent_fg; }
button.dict-theme { background-color: $surface; border: 1px solid $border; }

treeview.dict-list { background-color: transparent; color: $text; font-size: 15px; }
treeview.dict-list:selected { background-color: $select; color: $accent; }

scrolledwindow, viewport, .meanings { background-color: transparent; }
scrollbar { background-color: transparent; border: none; }
scrollbar slider { background-color: $border; border-radius: 4px; min-width: 6px; min-height: 30px; }
scrollbar slider:hover { background-color: $muted; }

.card { background-color: $card; border-radius: 12px; }
.badge {
    background-color: $accent; color: $accent_fg; font-weight: bold;
    border-radius: 15px; min-width: 30px; min-height: 30px;
}
.bar { background-color: $accent; border-radius: 1px; min-width: 48px; min-height: 3px; }
.line { background-color: $border; min-height: 1px; }
""")


# --------------------------------------------------------------------------- #
#  Data layer
# --------------------------------------------------------------------------- #
class Dictionary:
    def __init__(self, path):
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)

        self.data = {}
        for word, meanings in raw.items():
            if not isinstance(meanings, list):
                meanings = [meanings]
            cleaned = [m.strip() for m in meanings if isinstance(m, str) and m.strip()]
            if cleaned:
                self.data[word.strip()] = cleaned

        self.keys = sorted(self.data, key=str.lower)
        self._lower = [k.lower() for k in self.keys]

    def __len__(self):
        return len(self.keys)

    def search(self, query):
        """Prefix matches first (alphabetical), then words that merely contain the query."""
        q = query.strip().lower()
        if not q:
            return list(self.keys)

        i = bisect_left(self._lower, q)
        prefix = []
        while i < len(self._lower) and self._lower[i].startswith(q):
            prefix.append(self.keys[i])
            i += 1

        contains = [
            self.keys[j]
            for j, w in enumerate(self._lower)
            if q in w and not w.startswith(q)
        ]
        return prefix + contains


def load_favorites(db):
    try:
        with open(FAV_FILE, encoding="utf-8") as f:
            return {w for w in json.load(f) if w in db.data}
    except Exception:
        return set()


def save_favorites(favs):
    try:
        with open(FAV_FILE, "w", encoding="utf-8") as f:
            json.dump(sorted(favs), f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def add_class(widget, *names):
    ctx = widget.get_style_context()
    for name in names:
        ctx.add_class(name)
    return widget


# --------------------------------------------------------------------------- #
#  Main window
# --------------------------------------------------------------------------- #
class DictionaryApp(Gtk.Window):
    def __init__(self, db):
        super().__init__(title="English → Bangla Dictionary")
        self.db = db
        self.favs = load_favorites(db)
        self.theme_name = "light"
        self.mode = "all"          # "all" | "saved"
        self.current = None
        self._tab_lock = False

        self.set_default_size(1000, 660)
        self.set_size_request(780, 500)
        add_class(self, "dict-window")

        self.css = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), self.css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        self._build_ui()
        self.apply_theme()
        self.refresh_list(auto=False)
        self.show_word(random.choice(db.keys))   # word of the day

        self.connect("key-press-event", self._on_window_key)
        self.connect("destroy", Gtk.main_quit)

    # ------------------------------------------------------------------ #
    #  UI construction
    # ------------------------------------------------------------------ #
    def _build_ui(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        outer.set_margin_top(18)
        outer.set_margin_bottom(22)
        outer.set_margin_start(22)
        outer.set_margin_end(22)
        self.add(outer)

        # ---- header ----
        header = Gtk.Box(spacing=10)
        title = add_class(Gtk.Label(label="Dictionary"), "app-title")
        subtitle = add_class(Gtk.Label(label="English → বাংলা"), "muted", "bn", "bn-small")
        subtitle.set_valign(Gtk.Align.END)

        self.theme_btn = add_class(Gtk.Button(label="🌙 Dark"), "dict-btn", "dict-theme")
        self.theme_btn.set_relief(Gtk.ReliefStyle.NONE)
        self.theme_btn.connect("clicked", lambda _b: self.toggle_theme())

        header.pack_start(title, False, False, 0)
        header.pack_start(subtitle, False, False, 0)
        header.pack_end(self.theme_btn, False, False, 0)
        outer.pack_start(header, False, False, 0)

        # ---- body ----
        body = Gtk.Box(spacing=16)
        body.pack_start(self._build_sidebar(), False, False, 0)
        body.pack_start(self._build_detail(), True, True, 0)
        outer.pack_start(body, True, True, 0)

    def _build_sidebar(self):
        side = add_class(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10), "panel")
        side.set_size_request(320, -1)
        for setter in (side.set_margin_top, side.set_margin_bottom,
                       side.set_margin_start, side.set_margin_end):
            setter(0)

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        inner.set_margin_top(14)
        inner.set_margin_bottom(12)
        inner.set_margin_start(14)
        inner.set_margin_end(10)
        side.pack_start(inner, True, True, 0)

        self.search = add_class(Gtk.SearchEntry(), "dict-search")
        self.search.set_placeholder_text("Search an English word…")
        self.search.connect("search-changed", lambda _e: self.refresh_list(auto=True))
        self.search.connect("key-press-event", self._on_search_key)
        inner.pack_start(self.search, False, False, 0)

        tabs = Gtk.Box(spacing=6)
        self.tab_all = add_class(Gtk.ToggleButton(label="All words"), "dict-tab")
        self.tab_saved = add_class(Gtk.ToggleButton(), "dict-tab")
        for btn in (self.tab_all, self.tab_saved):
            btn.set_relief(Gtk.ReliefStyle.NONE)
        self.tab_all.set_active(True)
        self.tab_all.connect("toggled", self._on_tab_toggled, "all")
        self.tab_saved.connect("toggled", self._on_tab_toggled, "saved")

        self.count_lbl = add_class(Gtk.Label(label=""), "muted")
        tabs.pack_start(self.tab_all, False, False, 0)
        tabs.pack_start(self.tab_saved, False, False, 0)
        tabs.pack_end(self.count_lbl, False, False, 0)
        inner.pack_start(tabs, False, False, 0)

        self.store = Gtk.ListStore(str)
        self.tree = add_class(Gtk.TreeView(model=self.store), "dict-list")
        self.tree.set_headers_visible(False)
        self.tree.set_enable_search(False)
        renderer = Gtk.CellRendererText(xpad=12, ypad=7)
        column = Gtk.TreeViewColumn("Word", renderer, text=0)
        column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        column.set_fixed_width(200)
        column.set_expand(True)
        self.tree.append_column(column)
        self.tree.set_fixed_height_mode(True)
        self.selection = self.tree.get_selection()
        self.selection.set_mode(Gtk.SelectionMode.SINGLE)
        self.selection.connect("changed", self._on_selection_changed)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.add(self.tree)
        inner.pack_start(scroller, True, True, 0)

        self._update_tabs()
        return side

    def _build_detail(self):
        panel = add_class(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "panel")
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        inner.set_margin_top(28)
        inner.set_margin_bottom(24)
        inner.set_margin_start(34)
        inner.set_margin_end(34)
        panel.pack_start(inner, True, True, 0)

        top = Gtk.Box(spacing=8)
        self.word_lbl = add_class(Gtk.Label(label=""), "word")
        self.word_lbl.set_xalign(0)
        self.word_lbl.set_selectable(True)
        self.word_lbl.set_ellipsize(Pango.EllipsizeMode.END)

        self.fav_btn = add_class(Gtk.Button(label="☆ Save"), "dict-btn")
        self.copy_btn = add_class(Gtk.Button(label="Copy"), "dict-btn")
        for btn in (self.fav_btn, self.copy_btn):
            btn.set_relief(Gtk.ReliefStyle.NONE)
            btn.set_valign(Gtk.Align.CENTER)
        self.fav_btn.connect("clicked", lambda _b: self.toggle_favorite())
        self.copy_btn.connect("clicked", lambda _b: self.copy_current())

        top.pack_start(self.word_lbl, True, True, 0)
        top.pack_end(self.copy_btn, False, False, 0)
        top.pack_end(self.fav_btn, False, False, 0)
        inner.pack_start(top, False, False, 0)

        self.sub_lbl = add_class(Gtk.Label(label=""), "muted")
        self.sub_lbl.set_xalign(0)
        self.sub_lbl.set_margin_top(2)
        self.sub_lbl.set_margin_bottom(14)
        inner.pack_start(self.sub_lbl, False, False, 0)

        bar = add_class(Gtk.Box(), "bar")
        bar.set_halign(Gtk.Align.START)
        inner.pack_start(bar, False, False, 0)
        inner.pack_start(add_class(Gtk.Box(), "line"), False, False, 0)

        self.meanings_box = add_class(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10),
                                      "meanings")
        self.meanings_box.set_margin_top(18)
        self.meanings_box.set_margin_end(8)

        self.scroll = Gtk.ScrolledWindow()
        self.scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scroll.add(self.meanings_box)
        inner.pack_start(self.scroll, True, True, 0)
        return panel

    # ------------------------------------------------------------------ #
    #  Theme
    # ------------------------------------------------------------------ #
    def apply_theme(self):
        t = THEMES[self.theme_name]
        self.css.load_from_data(CSS.substitute(t).encode("utf-8"))
        settings = Gtk.Settings.get_default()
        if settings is not None:
            settings.set_property("gtk-application-prefer-dark-theme", self.theme_name == "dark")
        self.theme_btn.set_label("🌙 Dark" if self.theme_name == "light" else "☀ Light")

    def toggle_theme(self):
        self.theme_name = "dark" if self.theme_name == "light" else "light"
        self.apply_theme()

    # ------------------------------------------------------------------ #
    #  Keyboard
    # ------------------------------------------------------------------ #
    def _on_window_key(self, _widget, event):
        ctrl = event.state & Gdk.ModifierType.CONTROL_MASK
        if ctrl and event.keyval in (Gdk.KEY_f, Gdk.KEY_F, Gdk.KEY_l, Gdk.KEY_L):
            self.search.grab_focus()
            self.search.select_region(0, -1)
            return True
        return False

    def _on_search_key(self, _entry, event):
        key = event.keyval
        if key == Gdk.KEY_Down:
            self._move(1)
            return True
        if key == Gdk.KEY_Up:
            self._move(-1)
            return True
        if key in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if len(self.store) and self._current_row() < 0:
                self._select_row(0)
            return True
        if key == Gdk.KEY_Escape:
            self.search.set_text("")
            return True
        return False

    # ------------------------------------------------------------------ #
    #  Search / list behaviour
    # ------------------------------------------------------------------ #
    def _on_tab_toggled(self, button, mode):
        if self._tab_lock:
            return
        self._tab_lock = True
        other = self.tab_saved if mode == "all" else self.tab_all
        button.set_active(True)        # a tab can't be switched off by clicking itself
        other.set_active(False)
        self._tab_lock = False
        if self.mode != mode:
            self.mode = mode
            self.refresh_list(auto=bool(self.search.get_text().strip()))

    def _update_tabs(self):
        self.tab_saved.set_label(f"★ Saved ({len(self.favs)})")

    def refresh_list(self, auto=False):
        query = self.search.get_text().strip()
        results = self.db.search(query)
        if self.mode == "saved":
            results = [w for w in results if w in self.favs]

        # detach the model while filling it: much faster for thousands of rows
        self.tree.set_model(None)
        self.store.clear()
        for word in results:
            self.store.append([word])
        self.tree.set_model(self.store)

        n = len(results)
        self.count_lbl.set_text(f"{n:,} word{'s' if n != 1 else ''}")

        if auto and query:
            if results:
                self._select_row(0)
            else:
                self.show_message("No match", f"“{query}” was not found in the dictionary.")
        elif auto and not query and self.mode == "saved" and not results:
            self.show_message("No saved words", "Press ☆ Save on any word to keep it here.")
        elif self.current in results:
            self._select_row(results.index(self.current))

    def _current_row(self):
        model, it = self.selection.get_selected()
        if it is None:
            return -1
        return model.get_path(it).get_indices()[0]

    def _select_row(self, row):
        path = Gtk.TreePath.new_from_indices([row])
        self.selection.select_path(path)
        self.tree.scroll_to_cell(path, None, False, 0.0, 0.0)

    def _move(self, step):
        count = len(self.store)
        if not count:
            return
        row = self._current_row()
        row = max(0, min(count - 1, (row if row >= 0 else -1) + step))
        self._select_row(row)

    def _on_selection_changed(self, selection):
        model, it = selection.get_selected()
        if it is not None:
            self.show_word(model[it][0])

    # ------------------------------------------------------------------ #
    #  Detail panel
    # ------------------------------------------------------------------ #
    def _clear_meanings(self):
        for child in self.meanings_box.get_children():
            self.meanings_box.remove(child)

    def show_message(self, title, subtitle):
        self.current = None
        self._clear_meanings()
        self.word_lbl.set_text(title)
        self.sub_lbl.set_text(subtitle)
        self._update_fav_button()

    def show_word(self, word):
        meanings = self.db.data.get(word)
        if meanings is None:
            return

        self.current = word
        self.word_lbl.set_text(word)
        n = len(meanings)
        self.sub_lbl.set_text(f"{n} meaning{'s' if n != 1 else ''}")
        self._update_fav_button()
        self._clear_meanings()

        for i, meaning in enumerate(meanings, 1):
            card = add_class(Gtk.Box(spacing=14), "card")

            badge = add_class(Gtk.Label(label=str(i)), "badge")
            badge.set_valign(Gtk.Align.START)
            badge.set_halign(Gtk.Align.CENTER)
            badge.set_margin_top(12)
            badge.set_margin_bottom(12)
            badge.set_margin_start(14)

            label = add_class(Gtk.Label(label=meaning), "bn")
            label.set_xalign(0)
            label.set_line_wrap(True)
            label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
            label.set_max_width_chars(60)
            label.set_selectable(True)
            label.set_margin_top(10)
            label.set_margin_bottom(10)
            label.set_margin_end(16)

            card.pack_start(badge, False, False, 0)
            card.pack_start(label, True, True, 0)
            self.meanings_box.pack_start(card, False, False, 0)

        self.meanings_box.show_all()
        adj = self.scroll.get_vadjustment()
        adj.set_value(0)

    # ------------------------------------------------------------------ #
    #  Favourites / clipboard
    # ------------------------------------------------------------------ #
    def _update_fav_button(self):
        saved = bool(self.current and self.current in self.favs)
        self.fav_btn.set_label("★ Saved" if saved else "☆ Save")
        ctx = self.fav_btn.get_style_context()
        if saved:
            ctx.add_class("saved")
        else:
            ctx.remove_class("saved")

    def toggle_favorite(self):
        if not self.current:
            return
        if self.current in self.favs:
            self.favs.remove(self.current)
        else:
            self.favs.add(self.current)
        save_favorites(self.favs)
        self._update_fav_button()
        self._update_tabs()
        if self.mode == "saved":
            self.refresh_list(auto=False)

    def copy_current(self):
        if not self.current:
            return
        text = f"{self.current}: " + "; ".join(self.db.data[self.current])
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(text, -1)
        self.copy_btn.set_label("Copied ✓")
        GLib.timeout_add(1200, self._reset_copy_label)

    def _reset_copy_label(self):
        self.copy_btn.set_label("Copy")
        return False


# --------------------------------------------------------------------------- #
def show_error(title, text):
    dialog = Gtk.MessageDialog(
        transient_for=None, flags=0, message_type=Gtk.MessageType.ERROR,
        buttons=Gtk.ButtonsType.CLOSE, text=title,
    )
    dialog.format_secondary_text(text)
    dialog.run()
    dialog.destroy()


def main():
    try:
        db = Dictionary(DICT_FILE)
    except FileNotFoundError:
        show_error("File not found",
                   f"Could not find:\n{DICT_FILE}\n\nPlace dictionary.json next to this script.")
        return 1
    except (json.JSONDecodeError, OSError) as exc:
        show_error("Cannot load dictionary", str(exc))
        return 1

    window = DictionaryApp(db)
    window.show_all()
    Gtk.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
