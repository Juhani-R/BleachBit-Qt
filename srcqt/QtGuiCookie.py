# vim: ts=4:sw=4:expandtab

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
)

from bleachbit.Options import options

logger = logging.getLogger(__name__)

# Location types for preferences tabs
LOCATIONS_WHITELIST = 1
LOCATIONS_CUSTOM = 2

COOKIE_ALLOWLIST_FILENAME = "cookie_allowlist.json"
COOKIE_DISCOVERY_WARN_THRESHOLD = 2.0  # seconds

class QtCookieManagerDialog(QtWidgets.QDialog):
    """Manage cookies to keep (Qt port of GuiCookie.CookieManagerDialog)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("Manage cookies to keep"))
        self.resize(600, 500)
        self.setModal(True)

        self.allowlist_path = os.path.join(
            bleachbit.options_dir, COOKIE_ALLOWLIST_FILENAME
        )
        self.saved_domains = self._load_saved_domains()
        self.show_selected_only = False

        self._build_ui()
        self._populate_cookie_list()

    # ---------- UI ----------

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        # Instructions
        instructions = QtWidgets.QLabel(
            _(
                "Select the cookies to keep when cleaning cookies across browsers."
            )
        )
        instructions.setWordWrap(True)
        font = instructions.font()
        font.setBold(True)
        instructions.setFont(font)
        layout.addWidget(instructions)

        # Search + "show only allowed"
        top_row = QtWidgets.QHBoxLayout()
        lbl_search = QtWidgets.QLabel(_("Filter:"))
        self.search_entry = QtWidgets.QLineEdit()
        self.search_entry.setPlaceholderText(_("Type to filter by host…"))
        self.search_entry.textChanged.connect(self._update_filter)

        self.cb_show_selected = QtWidgets.QCheckBox(_("Show only allowed cookies"))
        self.cb_show_selected.toggled.connect(self._on_show_selected_toggled)

        top_row.addWidget(lbl_search)
        top_row.addWidget(self.search_entry, 1)
        top_row.addWidget(self.cb_show_selected)
        layout.addLayout(top_row)

        # Tree of cookies: [Allow] [Host]
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels([_("Allow"), _("Host")])
        header = self.tree.header()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        self.tree.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.tree, 1)

        # Stats label
        self.stat_label = QtWidgets.QLabel("")
        layout.addWidget(self.stat_label)

        # Buttons: Select all / none + Cancel / Keep
        btn_row = QtWidgets.QHBoxLayout()

        self.btn_select_all = QtWidgets.QPushButton(_("Select all"))
        self.btn_select_all.clicked.connect(self._select_all_visible)
        self.btn_select_none = QtWidgets.QPushButton(_("Select none"))
        self.btn_select_none.clicked.connect(self._select_none_visible)

        btn_row.addWidget(self.btn_select_all)
        btn_row.addWidget(self.btn_select_none)
        btn_row.addStretch(1)

        self.btn_cancel = QtWidgets.QPushButton(_("Cancel"))
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_keep = QtWidgets.QPushButton(_("Keep selected cookies"))
        self.btn_keep.clicked.connect(self.accept)

        btn_row.addWidget(self.btn_cancel)
        btn_row.addWidget(self.btn_keep)
        layout.addLayout(btn_row)

    # ---------- Data loading / saving ----------

    def _load_saved_domains(self):
        """Load saved cookie hostnames from cookie_allowlist.json."""
        domains = set()
        try:
            with open(self.allowlist_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return domains

        if isinstance(data, list):
            for item in data:
                if isinstance(item, str):
                    candidate = item
                elif isinstance(item, dict):
                    candidate = item.get("domain")
                else:
                    candidate = None
                if isinstance(candidate, str) and candidate:
                    domains.add(candidate.strip())
        return domains

    def _populate_cookie_list(self):
        """Discover cookies, merge with saved domains, and fill the tree."""
        start = time.monotonic()
        discovered = []
        try:
            discovered = list_unique_cookies()
        except (OSError, RuntimeError, ValueError) as exc:
            logger.error("Failed to enumerate cookies: %s", exc)
        duration = time.monotonic() - start
        if duration >= COOKIE_DISCOVERY_WARN_THRESHOLD:
            logger.warning("Enumerating cookie hosts took %.2fs", duration)

        all_hosts = {h.strip() for h in discovered if h}
        all_hosts.update(self.saved_domains)
        sorted_hosts = sorted(all_hosts, key=lambda host: host.lower())

        self.tree.blockSignals(True)
        self.tree.clear()
        for host in sorted_hosts:
            if not host:
                continue
            item = QtWidgets.QTreeWidgetItem()
            item.setFlags(
                item.flags() | QtCore.Qt.ItemIsUserCheckable
            )
            item.setText(1, host)
            if host in self.saved_domains:
                item.setCheckState(0, QtCore.Qt.Checked)
            else:
                item.setCheckState(0, QtCore.Qt.Unchecked)
            self.tree.addTopLevelItem(item)
        self.tree.blockSignals(False)

        self._update_stats()
        self._update_filter()

    def _iter_selected_domains(self):
        """Yield domains currently marked as allowed."""
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item.checkState(0) == QtCore.Qt.Checked:
                host = (item.text(1) or "").strip()
                if host:
                    # Normalize a little (strip leading dot)
                    yield host.lstrip(".")

    def accept(self):
        """Save whitelist and close dialog."""
        whitelist = sorted(set(self._iter_selected_domains()))
        try:
            # Write as list of strings. BleachBit core also supports
            # legacy list-of-dicts, but strings are enough.
            with open(self.allowlist_path, "w", encoding="utf-8") as f:
                json.dump(whitelist, f, ensure_ascii=False, indent=2)
        except OSError as exc:
            logger.error("Failed to save cookie allowlist: %s", exc)
            QtWidgets.QMessageBox.critical(
                self,
                _("Error"),
                _("Failed to save cookie allowlist:\n{error}").format(error=str(exc)),
            )
            return  # Do not close dialog on failure

        self.saved_domains = set(whitelist)
        super().accept()

    # ---------- Filter and stats ----------

    def _update_filter(self):
        """Apply text filter and 'show only allowed' filter."""
        search_text = self.search_entry.text().strip().lower()
        show_selected_only = self.show_selected_only

        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            domain = (item.text(1) or "").lower()
            matches_search = not search_text or (search_text in domain)
            matches_selected = True
            if show_selected_only:
                matches_selected = item.checkState(0) == QtCore.Qt.Checked

            item.setHidden(not (matches_search and matches_selected))

        self._update_stats()

    def _update_stats(self):
        """Update the 'X of Y cookies allowed' label."""
        total = self.tree.topLevelItemCount()
        selected = 0
        for i in range(total):
            item = self.tree.topLevelItem(i)
            if item.checkState(0) == QtCore.Qt.Checked:
                selected += 1

        self.stat_label.setText(
            _n(
                "%(selected)d of %(total)d cookie allowed",
                "%(selected)d of %(total)d cookies allowed",
                selected,
            )
            % {"selected": selected, "total": total}
        )

    # ---------- Callbacks ----------

    def _on_item_changed(self, _item, _column):
        # Any checkbox change updates stats and filter when needed
        self._update_stats()
        if self.show_selected_only:
            self._update_filter()

    def _on_show_selected_toggled(self, checked):
        self.show_selected_only = bool(checked)
        self._update_filter()

    def _select_all_visible(self):
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if not item.isHidden():
                item.setCheckState(0, QtCore.Qt.Checked)
        self._update_stats()

    def _select_none_visible(self):
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if not item.isHidden():
                item.setCheckState(0, QtCore.Qt.Unchecked)
        self._update_stats()

