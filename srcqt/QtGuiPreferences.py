# vim: ts=4:sw=4:expandtab
# -*- coding: UTF-8 -*-

# BleachBit
# Copyright (C) 2008-2025 Andrew Ziem
# https://www.bleachbit.org
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import logging
import os
import sys
import time
import json   # NEW

from PySide6 import QtCore, QtGui, QtWidgets

import bleachbit
from bleachbit import APP_NAME, appicon_path, online_update_notification_enabled
from bleachbit.Cleaner import backends, register_cleaners
from bleachbit.Cookie import list_unique_cookies  # NEW
from bleachbit.Language import (
    get_text as _,
    pget_text as _p,
    nget_text as _n,              # NEW
    get_active_language_code,
    get_supported_language_code_name_dict,
    setup_translation,
)

from bleachbit.Options import options
from bleachbit.FileUtilities import bytes_to_human
from bleachbit.Log import GtkLoggerHandler, set_root_log_level

from bleachbit.QtGuiCookie import QtCookieManagerDialog

logger = logging.getLogger(__name__)

# location types for preferences tabs
LOCATIONS_WHITELIST = 1
LOCATIONS_CUSTOM = 2

COOKIE_ALLOWLIST_FILENAME = "cookie_allowlist.json"
COOKIE_DISCOVERY_WARN_THRESHOLD = 2.0  # seconds

# ---------------------------------------------------------------------------
# Qt Preferences dialog
# ---------------------------------------------------------------------------

class QtPreferencesDialog(QtWidgets.QDialog):
    """ 
    Qt implementation (Qt/PySide6) of the BleachBit Preferences dialog 
    """

    def __init__(self, parent=None, cb_refresh_operations=None):
        super().__init__(parent)
        self.cb_refresh_operations = cb_refresh_operations
        self.refresh_operations = False
        self._languages_table_populating = False

        self.setWindowTitle(_("Preferences"))
        self.resize(650, 500)
        self.setModal(True)

        self._build_ui()

    # ---------- UI construction ----------

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        self.tabs = QtWidgets.QTabWidget()
        layout.addWidget(self.tabs)

        # Order mirrors GTK:
        # General, Custom, Drives, (Languages on POSIX), Allowlist
        self.tabs.addTab(self._build_general_page(), _("General"))
        self.tabs.addTab(self._build_locations_page(LOCATIONS_CUSTOM), _("Custom"))
        self.tabs.addTab(self._build_drives_page(), _("Drives"))
        if os.name == 'posix':
            self.tabs.addTab(self._build_languages_page(), _("Languages"))
        self.tabs.addTab(self._build_locations_page(LOCATIONS_WHITELIST), _("Allowlist"))

        # Button box
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    # ---------- General page ----------

    def _build_general_page(self):
        widget = QtWidgets.QWidget()
        vbox = QtWidgets.QVBoxLayout(widget)

        self._create_update_widgets(vbox)
        self._create_general_checkboxes(vbox)

        # Remember window geometry
        self.cb_geom = QtWidgets.QCheckBox(_("Remember window geometry"))
        self.cb_geom.setChecked(options.get("remember_geometry"))
        self.cb_geom.toggled.connect(
            lambda checked: self._set_option("remember_geometry", checked)
        )
        vbox.addWidget(self.cb_geom)

        # Language selection widgets (UI language)
        self._create_language_widgets(vbox)

        vbox.addStretch(1)
        return widget

    def _create_update_widgets(self, vbox):
        """Create and configure update-related checkboxes."""
        if not online_update_notification_enabled:
            return

        self.cb_updates = QtWidgets.QCheckBox(
            _("Check periodically for software updates via the Internet")
        )
        self.cb_updates.setChecked(options.get('check_online_updates'))
        self.cb_updates.setToolTip(
            _(
                "If an update is found, you will be given the option to "
                "download and install it. Then, you may manually download "
                "and install the update."
            )
        )
        self.cb_updates.toggled.connect(self._on_updates_toggled)
        vbox.addWidget(self.cb_updates)

        updates_group = QtWidgets.QGroupBox(_("Software updates"))
        gbox = QtWidgets.QVBoxLayout(updates_group)

        self.cb_beta = QtWidgets.QCheckBox(_("Check for new beta releases"))
        self.cb_beta.setChecked(options.get('check_beta'))
        self.cb_beta.setEnabled(options.get('check_online_updates'))
        self.cb_beta.toggled.connect(
            lambda checked: self._set_option('check_beta', checked)
        )
        gbox.addWidget(self.cb_beta)

        if os.name == 'nt':
            self.cb_winapp2 = QtWidgets.QCheckBox(
                _("Download and update cleaners from community (winapp2.ini)")
            )
            self.cb_winapp2.setChecked(options.get('update_winapp2'))
            self.cb_winapp2.setEnabled(options.get('check_online_updates'))
            self.cb_winapp2.toggled.connect(
                lambda checked: self._set_option('update_winapp2', checked)
            )
            gbox.addWidget(self.cb_winapp2)
        else:
            self.cb_winapp2 = None

        vbox.addWidget(updates_group)

    def _create_general_checkboxes(self, vbox):
        """Create and configure general checkboxes."""

        # Hide irrelevant cleaners
        cb_auto_hide = QtWidgets.QCheckBox(_("Hide irrelevant cleaners"))
        cb_auto_hide.setChecked(options.get('auto_hide'))
        cb_auto_hide.setToolTip(
            _(
                "Hide cleaners which would do nothing on this system "
                "(for example, Firefox if it is not installed)."
            )
        )
        cb_auto_hide.toggled.connect(
            lambda checked: self._on_auto_hide_toggled(checked)
        )
        vbox.addWidget(cb_auto_hide)

        # Overwrite contents (shred)
        cb_shred = QtWidgets.QCheckBox(
            _("Overwrite contents of files to prevent recovery")
        )
        cb_shred.setChecked(options.get('shred'))
        cb_shred.setToolTip(
            _(
                "Overwriting is ineffective on some file systems and some "
                "BleachBit operations. Overwriting is significantly slower."
            )
        )
        cb_shred.toggled.connect(
            lambda checked: self._set_option('shred', checked)
        )
        vbox.addWidget(cb_shred)

        # Exit after cleaning
        cb_exit = QtWidgets.QCheckBox(_("Exit after cleaning"))
        cb_exit.setChecked(options.get('exit_done'))
        cb_exit.toggled.connect(
            lambda checked: self._set_option('exit_done', checked)
        )
        vbox.addWidget(cb_exit)

        # Confirm before delete
        cb_popup = QtWidgets.QCheckBox(_("Confirm before delete"))
        cb_popup.setChecked(options.get('delete_confirmation'))
        cb_popup.toggled.connect(
            lambda checked: self._set_option('delete_confirmation', checked)
        )
        vbox.addWidget(cb_popup)

        # IEC sizes
        cb_units_iec = QtWidgets.QCheckBox(
            _("Use IEC sizes (1 KiB = 1024 bytes) instead of SI (1 kB = 1000 bytes)")
        )
        cb_units_iec.setChecked(options.get("units_iec"))
        cb_units_iec.toggled.connect(
            lambda checked: self._set_option("units_iec", checked)
        )
        vbox.addWidget(cb_units_iec)

    def _create_language_widgets(self, vbox):
        """Language auto-detection + UI language combo."""
        lang_box = QtWidgets.QVBoxLayout()

        self.cb_auto_lang = QtWidgets.QCheckBox(_("Auto-detect language"))
        is_auto_detect = options.get("auto_detect_lang")
        self.cb_auto_lang.setChecked(is_auto_detect)
        self.cb_auto_lang.setToolTip(
            _("Automatically detect the system language")
        )
        self.cb_auto_lang.toggled.connect(self._on_auto_detect_toggled)
        lang_box.addWidget(self.cb_auto_lang)

        self.lang_select_box = QtWidgets.QHBoxLayout()
        lang_label = QtWidgets.QLabel(_("Language:"))
        self.lang_select_box.addWidget(lang_label)

        self.lang_combo = QtWidgets.QComboBox()
        self.lang_select_box.addWidget(self.lang_combo, 1)

        # Populate combobox
        current_lang_code = get_active_language_code()
        lang_idx = 0
        active_language_idx = None
        try:
            supported_langs = get_supported_language_code_name_dict().items()
        except Exception:
            logger.error("Failed to get supported languages", exc_info=True)
            supported_langs = []

        for lang_code, native in sorted(
            supported_langs, key=lambda x: x[1] or x[0]
        ):
            if native:
                text = f"{native} ({lang_code})"
            else:
                text = lang_code
            self.lang_combo.addItem(text, userData=lang_code)
            if lang_code == current_lang_code:
                active_language_idx = lang_idx
            lang_idx += 1

        if active_language_idx is not None:
            self.lang_combo.setCurrentIndex(active_language_idx)

        self.lang_combo.currentIndexChanged.connect(
            self._on_language_combo_changed
        )

        # Disable selection when auto-detect is on
        self._set_language_widgets_enabled(not is_auto_detect)

        lang_box.addLayout(self.lang_select_box)
        vbox.addLayout(lang_box)

    # ---------- Drives page ----------

    def _build_drives_page(self):
        widget = QtWidgets.QWidget()
        vbox = QtWidgets.QVBoxLayout(widget)

        desc = QtWidgets.QLabel(
            _(
                "These paths will be used when wiping free disk space. "
                "Be careful: wiping large volumes can be slow."
            )
        )
        font = QtGui.QFont()
        font.setBold(True)
        desc.setFont(font)
        desc.setWordWrap(True)
        vbox.addWidget(desc)

        self.drives_list = QtWidgets.QListWidget()
        self._shred_drives_paths = options.get_list('shred_drives') or []
        self._shred_drives_paths = sorted(self._shred_drives_paths)
        self._reload_drives_list()
        vbox.addWidget(self.drives_list, 1)

        buttons_layout = QtWidgets.QHBoxLayout()
        btn_add = QtWidgets.QPushButton(_p('button', 'Add'))
        btn_remove = QtWidgets.QPushButton(_p('button', 'Remove'))
        btn_add.clicked.connect(self._add_drive)
        btn_remove.clicked.connect(self._remove_drive)
        buttons_layout.addWidget(btn_add)
        buttons_layout.addWidget(btn_remove)
        buttons_layout.addStretch(1)
        vbox.addLayout(buttons_layout)

        return widget

    def _reload_drives_list(self):
        self.drives_list.clear()
        for path in self._shred_drives_paths:
            self.drives_list.addItem(path)

    def _add_drive(self):
        """Add a directory to the shred_drives list."""
        caption = _("Choose a folder")
        start_dir = os.path.expanduser("~")
        dirname = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            caption,
            start_dir,
            QtWidgets.QFileDialog.ShowDirsOnly
        )
        if dirname:
            dirname = os.path.abspath(dirname)
            if dirname not in self._shred_drives_paths:
                self._shred_drives_paths.append(dirname)
                self._shred_drives_paths.sort()
                self._reload_drives_list()
                options.set_list('shred_drives', self._shred_drives_paths)

    def _remove_drive(self):
        """Remove selected paths from shred_drives list."""
        selected = self.drives_list.selectedItems()
        if not selected:
            return
        for item in selected:
            path = item.text()
            if path in self._shred_drives_paths:
                self._shred_drives_paths.remove(path)
        self._shred_drives_paths.sort()
        self._reload_drives_list()
        options.set_list('shred_drives', self._shred_drives_paths)

    # ---------- Languages page (preserve languages) ----------

    def _build_languages_page(self):
        widget = QtWidgets.QWidget()
        vbox = QtWidgets.QVBoxLayout(widget)

        notice = QtWidgets.QLabel(
            _("All languages will be deleted except those checked.")
        )
        notice.setWordWrap(True)
        vbox.addWidget(notice)

        self.languages_table = QtWidgets.QTableWidget()
        self.languages_table.setColumnCount(3)
        self.languages_table.setHorizontalHeaderLabels(
            [_("Preserve"), _("Code"), _("Name")]
        )
        header = self.languages_table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)

        # Populate rows
        try:
            supported = get_supported_language_code_name_dict().items()
        except Exception:
            logger.error("Failed to get languages for preserve list", exc_info=True)
            supported = []

        rows = []
        for lang_code, native in supported:
            preserve = options.get_language(lang_code)
            rows.append((native or "", lang_code, preserve))
        rows.sort(key=lambda x: x[0] or x[1])

        self._languages_table_populating = True
        self.languages_table.setRowCount(len(rows))
        for row_idx, (native, lang_code, preserve) in enumerate(rows):
            chk_item = QtWidgets.QTableWidgetItem()
            chk_item.setFlags(
                QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEnabled
            )
            chk_item.setCheckState(
                QtCore.Qt.Checked if preserve else QtCore.Qt.Unchecked
            )
            self.languages_table.setItem(row_idx, 0, chk_item)

            code_item = QtWidgets.QTableWidgetItem(lang_code)
            code_item.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
            self.languages_table.setItem(row_idx, 1, code_item)

            name_item = QtWidgets.QTableWidgetItem(native)
            name_item.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
            self.languages_table.setItem(row_idx, 2, name_item)

        self._languages_table_populating = False
        self.languages_table.itemChanged.connect(
            self._on_languages_table_item_changed
        )

        vbox.addWidget(self.languages_table)
        return widget

    def _on_languages_table_item_changed(self, item):
        if self._languages_table_populating:
            return
        if item.column() != 0:
            return
        row = item.row()
        code_item = self.languages_table.item(row, 1)
        if not code_item:
            return
        langid = code_item.text()
        preserve = (item.checkState() == QtCore.Qt.Checked)
        options.set_language(langid, preserve)

    # ---------- Custom / Allowlist pages ----------

    def _build_locations_page(self, page_type):
        """
        Return a widget containing a list of files and folders
        for either the custom paths or the allowlist.
        """
        widget = QtWidgets.QWidget()
        vbox = QtWidgets.QVBoxLayout(widget)

        # load data
        if page_type == LOCATIONS_WHITELIST:
            pathnames = options.get_whitelist_paths() or []
        else:
            pathnames = options.get_custom_paths() or []

        # Notice label
        if page_type == LOCATIONS_WHITELIST:
            notice_text = _("These paths will not be deleted or modified.")
        else:
            notice_text = _("These locations can be selected for deletion.")
        notice = QtWidgets.QLabel(notice_text)
        font = QtGui.QFont()
        font.setBold(True)
        notice.setFont(font)
        notice.setWordWrap(True)
        vbox.addWidget(notice)

        # Optional cookie manager button for allowlist
        btn_cookie_mgr = None
        if page_type == LOCATIONS_WHITELIST:
            btn_cookie_mgr = QtWidgets.QPushButton(_("Manage cookies to keep..."))
            btn_cookie_mgr.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Maximum,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )
            btn_cookie_mgr.clicked.connect(self._open_cookie_manager)

        # Tree widget: 2 columns (Type, Path)
        tree = QtWidgets.QTreeWidget()
        tree.setColumnCount(2)
        tree.setHeaderLabels([_("Type"), _("Path")])
        tree.header().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        tree.header().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)

        for type_code, path in pathnames:
            if type_code == 'file':
                type_str = _('File')
            elif type_code == 'folder':
                type_str = _('Folder')
            else:
                # Shouldn't happen, but don't crash UI
                logger.error("Invalid type code in locations list: %r", type_code)
                continue
            item = QtWidgets.QTreeWidgetItem([type_str, path])
            tree.addTopLevelItem(item)

        vbox.addWidget(tree, 1)

        # Buttons: Add file, Add folder, Remove
        btn_layout = QtWidgets.QHBoxLayout()
        btn_add_file = QtWidgets.QPushButton(_p('button', 'Add file'))
        btn_add_folder = QtWidgets.QPushButton(_p('button', 'Add folder'))
        btn_remove = QtWidgets.QPushButton(_p('button', 'Remove'))

        btn_layout.addWidget(btn_add_file)
        btn_layout.addWidget(btn_add_folder)
        btn_layout.addWidget(btn_remove)
        btn_layout.addStretch() #1
        if btn_cookie_mgr:
            btn_layout.addWidget(btn_cookie_mgr)
        vbox.addLayout(btn_layout)

        # Wire up callbacks, capturing page_type and tree
        def add_file_cb():
            caption = _("Choose a file")
            start_dir = os.path.expanduser("~")
            pathname, selectedFilter = QtWidgets.QFileDialog.getOpenFileName(
                self, 
                caption, 
                start_dir
            )
            if pathname:
                pathname = os.path.abspath(pathname)
                self._add_path_qt(pathname, 'file', page_type, tree)

        def add_folder_cb():
            caption = _("Choose a folder")
            start_dir = os.path.expanduser("~")
            dirname = QtWidgets.QFileDialog.getExistingDirectory(
                self,
                caption,
                start_dir,
                QtWidgets.QFileDialog.ShowDirsOnly
            )
            if dirname:
                dirname = os.path.abspath(dirname)
                self._add_path_qt(dirname, 'folder', page_type, tree)

        def remove_cb():
            self._remove_path_qt(tree, page_type)

        btn_add_file.clicked.connect(add_file_cb)
        btn_add_folder.clicked.connect(add_folder_cb)
        btn_remove.clicked.connect(remove_cb)

        return widget

    def _check_path_exists_qt(self, pathname, page_type):
        """
        Check if a path exists in either whitelist or custom lists.
        Returns True if path exists, False otherwise.
        """
        whitelist_paths = options.get_whitelist_paths() or []
        custom_paths = options.get_custom_paths() or []

        # Check in whitelist
        for path_type, path in whitelist_paths:
            if pathname == path:
                msg = _("This path already exists in the allowlist.")
                QtWidgets.QMessageBox.critical(
                    self,
                    _("Error"),
                    msg,
                    QtWidgets.QMessageBox.Ok,
                )
                return True

        # Check in custom
        for path_type, path in custom_paths:
            if pathname == path:
                msg = _("This path already exists in the custom list.")
                QtWidgets.QMessageBox.critical(
                    self,
                    _("Error"),
                    msg,
                    QtWidgets.QMessageBox.Ok,
                )
                return True

        return False

    def _add_path_qt(self, pathname, path_type, page_type, tree):
        """
        Common function to add a path to either whitelist or custom list.
        path_type is 'file' or 'folder'.
        """
        if self._check_path_exists_qt(pathname, page_type):
            return

        type_str = _('File') if path_type == 'file' else _('Folder')

        # Add to tree
        item = QtWidgets.QTreeWidgetItem([type_str, pathname])
        tree.addTopLevelItem(item)

        # Update options
        if page_type == LOCATIONS_WHITELIST:
            pathnames = options.get_whitelist_paths() or []
            pathnames.append([path_type, pathname])
            options.set_whitelist_paths(pathnames)
        else:
            pathnames = options.get_custom_paths() or []
            pathnames.append([path_type, pathname])
            options.set_custom_paths(pathnames)

    def _remove_path_qt(self, tree, page_type):
        """
        Common function to remove a path from either whitelist or custom list.
        """
        item = tree.currentItem()
        if item is None:
            return

        pathname = item.text(1)

        # Remove from tree
        idx = tree.indexOfTopLevelItem(item)
        if idx >= 0:
            tree.takeTopLevelItem(idx)

        # Remove from options
        if page_type == LOCATIONS_WHITELIST:
            pathnames = options.get_whitelist_paths() or []
            pathnames = [p for p in pathnames if p[1] != pathname]
            options.set_whitelist_paths(pathnames)
        else:
            pathnames = options.get_custom_paths() or []
            pathnames = [p for p in pathnames if p[1] != pathname]
            options.set_custom_paths(pathnames)

    # ---------- helpers / callbacks ----------

    def _set_option(self, key, value):
        """Set simple boolean option and do any side effects."""
        options.set(key, bool(value))
        if key == 'auto_hide':
            self.refresh_operations = True
        if key in ('check_online_updates', 'check_beta', 'update_winapp2'):
            # Keep update-related widgets in sync
            if key == 'check_online_updates':
                enabled = bool(value)
                if hasattr(self, 'cb_beta') and self.cb_beta is not None:
                    self.cb_beta.setEnabled(enabled)
                if hasattr(self, 'cb_winapp2') and self.cb_winapp2 is not None:
                    self.cb_winapp2.setEnabled(enabled)

    def _on_updates_toggled(self, checked):
        self._set_option('check_online_updates', checked)

    def _on_auto_hide_toggled(self, checked):
        self._set_option('auto_hide', checked)

    def _set_language_widgets_enabled(self, enabled: bool):
        # Enable/disable the language selection row
        for i in range(self.lang_select_box.count()):
            item = self.lang_select_box.itemAt(i)
            w = item.widget()
            if w is not None:
                w.setEnabled(enabled)

    def _on_auto_detect_toggled(self, checked):
        self._set_option('auto_detect_lang', checked)
        self._set_language_widgets_enabled(not checked)
        if checked:
            # Clear forced language
            options.set("forced_language", "", section="bleachbit")
        setup_translation()
        self.refresh_operations = True

    def _on_language_combo_changed(self, index):
        if index < 0:
            return
        text = self.lang_combo.itemText(index)
        # text may be "Native (code)" or just "code"
        lang_code = None
        if "(" in text and text.endswith(")"):
            lang_code = text.split("(")[-1].rstrip(")")
        else:
            lang_code = self.lang_combo.currentData() or text
        if lang_code:
            options.set("forced_language", lang_code, section="bleachbit")
            setup_translation()
            self.refresh_operations = True

    def _on_accept(self):
        """Handle OK button: commit and maybe refresh operations."""
        self.accept()
        if self.refresh_operations and self.cb_refresh_operations is not None:
            try:
                self.cb_refresh_operations()
            except Exception:
                logger.exception("Error in cb_refresh_operations from preferences")

    def _open_cookie_manager(self):
        """Open the cookie manager dialog."""
        dlg = QtCookieManagerDialog(self)
        dlg.exec()


