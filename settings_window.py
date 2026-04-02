"""Settings window for managing launcher applications."""

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

from gi.repository import Gtk, Gdk
from logger import log


class SettingsWindow:
    """GTK window for configuring launcher apps."""

    def __init__(self, db, on_close_callback=None):
        self._db = db
        self._on_close_callback = on_close_callback
        self._apps = []
        self._setup_ui()
        self._load_apps()

    def _setup_ui(self):
        self._window = Gtk.Window()
        self._window.set_title("Configuración de mados-launcher")
        self._window.set_size_request(600, 500)
        self._window.set_position(Gtk.WindowPosition.CENTER)
        self._window.set_modal(True)

        self._window.connect("destroy", self._on_destroy)
        self._window.connect("key-press-event", self._on_key_press)

        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(b"""
            window {
                background: #2E3440;
            }
            headerbar {
                background: #3B4252;
            }
            listbox {
                background: #2E3440;
            }
            row {
                background: #3B4252;
                border-radius: 6px;
                margin: 2px 8px;
            }
            row:hover {
                background: #434C5E;
            }
            button {
                background: #4C566A;
                color: #D8DEE9;
                border-radius: 4px;
                padding: 6px 12px;
            }
            button:hover {
                background: #5E81AC;
            }
        """)
        self._window.get_style_context().add_provider(
            css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._window.add(main_box)

        header = Gtk.HeaderBar()
        header.set_title("Configuración de mados-launcher")
        header.set_show_close_button(True)
        main_box.pack_start(header, False, False, 0)

        toolbar = Gtk.Toolbar()
        toolbar.set_style(Gtk.ToolbarStyle.ICONS)
        header.pack_start(toolbar)

        sync_btn = Gtk.ToolButton()
        sync_btn.set_icon_name("view-refresh")
        sync_btn.set_tooltip_text("Sincronizar con sistema")
        sync_btn.connect("clicked", self._on_sync_clicked)
        toolbar.insert(sync_btn, 0)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        main_box.pack_start(scrolled, True, True, 0)

        self._listbox = Gtk.ListBox()
        self._listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self._listbox.set_activate_on_single_click(False)
        scrolled.add(self._listbox)

        target = Gtk.TargetEntry.new("text/plain", 0, 0)
        self._listbox.drag_source_set(
            Gdk.ModifierType.BUTTON1_MASK,
            [target],
            Gdk.DragAction.MOVE
        )
        self._listbox.drag_dest_set(
            Gtk.DestDefaults.ALL,
            [target],
            Gdk.DragAction.MOVE
        )
        self._listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._listbox.connect("drag-data-get", self._on_drag_data_get)
        self._listbox.connect("drag-data-received", self._on_drag_data_received)

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        footer.set_margin_top(12)
        footer.set_margin_bottom(12)
        footer.set_margin_start(12)
        footer.set_margin_end(12)
        main_box.pack_start(footer, False, False, 0)

        legend = Gtk.Label()
        legend.set_text("✓ Visible  |  👤 Sudo  |  ⌨ Terminal  |  Grupo")
        legend.set_xalign(0)
        footer.pack_start(legend, True, True, 0)

        close_btn = Gtk.Button.new_with_label("Cerrar")
        close_btn.connect("clicked", self._on_close_clicked)
        footer.pack_end(close_btn, False, False, 0)

        self._window.show_all()

    def _load_apps(self):
        for child in self._listbox.get_children():
            self._listbox.remove(child)

        self._apps = self._db.get_all_apps()
        for app in self._apps:
            row = self._create_app_row(app)
            self._listbox.add(row)

    def _create_app_row(self, app):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.set_margin_start(8)
        box.set_margin_end(8)
        box.set_margin_top(6)
        box.set_margin_bottom(6)

        grip = Gtk.Image()
        grip.set_from_icon_name("list-drag", Gtk.IconSize.BUTTON)
        grip.set_opacity(0.5)
        box.pack_start(grip, False, False, 0)

        icon = Gtk.Image()
        icon.set_size_request(32, 32)
        try:
            theme = Gtk.IconTheme.get_default()
            pixbuf = theme.load_icon(app.get("icon_name", "application-x-executable"), 32, 0)
            icon.set_from_pixbuf(pixbuf)
        except Exception:
            icon.set_from_icon_name("application-x-executable", Gtk.IconSize.DIALOG)
        box.pack_start(icon, False, False, 0)

        name_label = Gtk.Label(app.get("name", ""))
        name_label.set_xalign(0)
        name_label.set_hexpand(True)
        box.pack_start(name_label, True, True, 0)

        enabled_btn = Gtk.CheckButton()
        enabled_btn.set_active(bool(app.get("enabled", 1)))
        enabled_btn.set_tooltip_text("Habilitada")
        enabled_btn.connect("toggled", self._on_enabled_toggled, app["id"])
        box.pack_start(enabled_btn, False, False, 0)

        sudo_btn = Gtk.Button()
        sudo_btn.set_image(Gtk.Image.new_from_icon_name("dialog-password", Gtk.IconSize.BUTTON))
        sudo_btn.set_tooltip_text("Lanzar con sudo")
        sudo_btn.set_relief(Gtk.ReliefStyle.NONE)
        if app.get("launch_sudo"):
            sudo_btn.set_label("👤")
        sudo_btn.connect("clicked", self._on_sudo_clicked, app["id"])
        box.pack_start(sudo_btn, False, False, 0)

        terminal_btn = Gtk.Button()
        terminal_btn.set_image(Gtk.Image.new_from_icon_name("utilities-terminal", Gtk.IconSize.BUTTON))
        terminal_btn.set_tooltip_text("Lanzar en terminal")
        terminal_btn.set_relief(Gtk.ReliefStyle.NONE)
        if app.get("terminal"):
            terminal_btn.set_label("⌨")
        terminal_btn.connect("clicked", self._on_terminal_clicked, app["id"])
        box.pack_start(terminal_btn, False, False, 0)

        group_combo = Gtk.ComboBoxText()
        group_combo.append_text("auto")
        group_combo.append_text("manual")
        group_combo.append_text("none")
        current_mode = app.get("group_mode", "auto")
        modes = ["auto", "manual", "none"]
        if current_mode not in modes:
            current_mode = "auto"
        group_combo.set_active(modes.index(current_mode))
        group_combo.connect("changed", self._on_group_mode_changed, app["id"])
        box.pack_start(group_combo, False, False, 0)

        group_entry = Gtk.Entry()
        group_entry.set_width_chars(10)
        group_entry.set_placeholder_text("group key")
        group_entry.set_text(app.get("group_key", ""))
        group_entry.set_sensitive(current_mode == "manual")
        group_entry.connect("changed", self._on_group_key_changed, app["id"], group_combo)
        box.pack_start(group_entry, False, False, 0)

        box.show_all()
        return box

    def _on_enabled_toggled(self, btn, app_id):
        enabled = 1 if btn.get_active() else 0
        self._db.update_app(app_id, enabled=enabled)
        log.info(f"App {app_id} enabled={enabled}")

    def _on_sudo_clicked(self, btn, app_id):
        app = self._db.get_app_by_id(app_id)
        if app:
            current = app.get("launch_sudo", 0)
            self._db.update_app(app_id, launch_sudo=1 - current)
            btn.set_label("👤" if not current else "")
        self._load_apps()

    def _on_terminal_clicked(self, btn, app_id):
        app = self._db.get_app_by_id(app_id)
        if app:
            current = app.get("terminal", 0)
            self._db.update_app(app_id, terminal=1 - current)
            btn.set_label("⌨" if not current else "")
        self._load_apps()

    def _on_sync_clicked(self, btn):
        from desktop_entries import scan_and_sync
        added, updated, removed = scan_and_sync(self._db)
        log.info(f"Sync complete: added={added}, updated={updated}, removed={removed}")
        self._load_apps()

    def _on_group_mode_changed(self, combo, app_id):
        mode = combo.get_active_text()
        if not mode:
            return
        self._db.update_app(app_id, group_mode=mode)
        self._load_apps()

    def _on_group_key_changed(self, entry, app_id, group_combo):
        if group_combo.get_active_text() != "manual":
            return
        self._db.update_app(app_id, group_key=entry.get_text().strip())

    def _on_drag_data_get(self, widget, context, data, info, time):
        selection = widget.get_selected_rows()
        if selection:
            row = selection[0]
            row_index = widget.get_children().index(row)
            data.set_text(str(row_index), -1)

    def _on_drag_data_received(self, widget, context, x, y, data, info, time):
        if not data.get_text():
            return
        source_index = int(data.get_text())
        target = widget.get_row_at_y(y)
        if target:
            target_index = widget.get_children().index(target)
            if source_index != target_index:
                app_ids = [app["id"] for app in self._apps]
                app_ids.insert(target_index, app_ids.pop(source_index))
                self._db.reorder_apps(app_ids)
                self._load_apps()
        context.finish(True, True, time)

    def _on_close_clicked(self, btn):
        self._close()

    def _on_destroy(self, widget):
        self._close()

    def _on_key_press(self, widget, event):
        if event.keyval == Gdk.KEY_Escape:
            self._close()
        return False

    def _close(self):
        if self._on_close_callback:
            self._on_close_callback()
        self._window.destroy()

    def present(self):
        self._window.present()

    def destroy(self):
        self._window.destroy()
