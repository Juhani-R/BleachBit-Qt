# vim: ts=4:sw=4:expandtab
# -*- coding: UTF-8 -*-

# BleachBit Qt UI (PySide6) initial implementation by Juhani-R
# Alternative frontend to the existing GTK GUI.
#
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

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtGui import QPalette, QColor

import bleachbit
from bleachbit import APP_NAME, appicon_path
from bleachbit.Cleaner import backends, register_cleaners
from bleachbit.Cookie import list_unique_cookies
from bleachbit.Language import get_text as _

from bleachbit.Options import options
from bleachbit.FileUtilities import bytes_to_human
from bleachbit.Log import GtkLoggerHandler, set_root_log_level

from bleachbit.QtGuiPreferences import QtPreferencesDialog
from bleachbit.QtSystemInformation import QtSystemInformationDialog

logger = logging.getLogger('bleachbit')

def get_current_locale_qt(info = False) -> str:
    """
    Returns the current locale given by QtCore.QLocale().name()
    Not in use at the moment, but here if ever needed
    """
    current_locale = QtCore.QLocale()
    name = current_locale.name()
    info_str = f"QtCore.QLocale(): \n-country:{current_locale.nativeCountryName()} \n-locale:{name} \n-native language:{current_locale.nativeLanguageName()}"
    if info:
        print(info_str)
    return name

# ---------------------------------------------------------------------------
# Bleachbit Qt main window
# ---------------------------------------------------------------------------

class BleachBitQtMainWindow(QtWidgets.QMainWindow):
    """
    Qt main window that provides:
    - cleaners tree with options (left)
    - Preview, Clean and Abort buttons
    - progress bar
    - log output
    - total size cleaned in the status bar
    """

    def __init__(self, auto_exit=False, parent=None):
        super().__init__(parent)
        self._auto_exit = auto_exit
        self.worker = None
        self._worker_gen = None
        self.start_time = None

        self.setWindowTitle(APP_NAME)
        self.resize(1000, 800)
        self._set_window_icon()

        self._build_ui()
        self._setup_logging()
        self._populate_cleaners_tree()

    # ---------- window & logging setup ----------

    def _set_window_icon(self):
        try:
            if appicon_path and os.path.exists(appicon_path):
                self.setWindowIcon(QtGui.QIcon(appicon_path))
        except Exception:
            logger.debug("Failed to set application icon", exc_info=True)

    def _setup_logging(self):
        """
        Attach a handler that writes BleachBit log messages into
        the GUI log widget using append_text().
        """
        set_root_log_level()
        bb_logger = logging.getLogger('bleachbit')
        gui_handler = GtkLoggerHandler(self.append_text)
        bb_logger.addHandler(gui_handler)
        gui_handler.update_log_level()

    # ---------- UI construction ----------

    def _build_ui(self):
        # Main window central area: left tree, right vertical (buttons, progress, log)
        central = QtWidgets.QWidget(self)
        self.setCentralWidget(central)
        hbox = QtWidgets.QHBoxLayout(central)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        hbox.addWidget(splitter)

        # Left: tree of cleaners/options
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels([_("Name"), _("Size")])
        self.tree.header().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents) # Stretch
        self.tree.header().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch) # ResizeToContents)
        self.tree
        self.tree.itemChanged.connect(self._on_tree_item_changed)
        splitter.addWidget(self.tree) #hbox.addWidget(self.tree, 2)

        # Right side
        right = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right)
        splitter.addWidget(right) #hbox.addWidget(right, 3)

        # Toolbar (Preview / Clean / Stop)
        toolbar_layout = QtWidgets.QHBoxLayout()
        right_layout.addLayout(toolbar_layout)

        self.preview_button = QtWidgets.QPushButton(_("Preview"))
        self.preview_button.setIcon(QtGui.QIcon("icons/preview.png"))
        self.preview_button.setIconSize(QtCore.QSize(18, 18))
        self.preview_button.clicked.connect(self._on_preview_clicked)
        toolbar_layout.addWidget(self.preview_button)

        self.clean_button = QtWidgets.QPushButton(_("Clean"))
        self.clean_button.setIcon(QtGui.QIcon("icons/clean.png"))
        self.clean_button.setIconSize(QtCore.QSize(18, 18))
        self.clean_button.clicked.connect(self._on_clean_clicked)
        toolbar_layout.addWidget(self.clean_button)

        self.stop_button = QtWidgets.QPushButton(_("Abort"))
        self.stop_button.setIcon(QtGui.QIcon("icons/abort.png"))
        self.stop_button.setIconSize(QtCore.QSize(18, 18))
        self.stop_button.clicked.connect(self.cb_stop_operations)
        self.stop_button.setEnabled(False)
        toolbar_layout.addWidget(self.stop_button)

        toolbar_layout.addStretch(1)

        # Progress bar
        self.progressbar = QtWidgets.QProgressBar()
        self.progressbar.setMinimum(0)
        self.progressbar.setMaximum(100)
        self.progressbar.setTextVisible(True)
        self.progressbar.setValue(0)
        right_layout.addWidget(self.progressbar)

        # Log output
        self.log_edit = QtWidgets.QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap)
        font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)
        self.log_edit.setFont(font)
        right_layout.addWidget(self.log_edit, 1)

        # Status bar: total cleaned size
        self.total_label = QtWidgets.QLabel(bytes_to_human(0))
        self.statusBar().addPermanentWidget(QtWidgets.QLabel(_("Total cleaned:")))
        self.statusBar().addPermanentWidget(self.total_label)

        self._build_menu_bar()

        # Set initial splitter proportions last to take effect
        splitter.setStretchFactor(0, 4) # Left side w tree gets 40%
        splitter.setStretchFactor(1, 6) # Right side w log gets 60%

    def _build_menu_bar(self):
        menu_bar = self.menuBar()

        # File menu
        file_menu = menu_bar.addMenu(_("&File"))

        """self.act_shred_files = QtGui.QAction(_("Shred Files"), self)
        self.act_shred_files.triggered.connect(self._shred_files)
        file_menu.addAction(self.act_shred_files)
        self.act_shred_files.setDisabled(True)

        self.act_shred_folders = QtGui.QAction(_("Shred Folders"), self)
        self.act_shred_folders.triggered.connect(self._shred_folders)
        file_menu.addAction(self.act_shred_folders)
        self.act_shred_folders.setDisabled(True)

        self.act_shred_paths = QtGui.QAction(_("Shred Paths From Clipboard"), self)
        self.act_shred_paths.triggered.connect(self._shred_paths)
        file_menu.addAction(self.act_shred_paths)
        self.act_shred_paths.setDisabled(True)

        act_wipe_free_space = QtGui.QAction(_("Wipe Free Space"), self)
        act_wipe_free_space.triggered.connect(self._wipe_free_space)
        file_menu.addAction(act_wipe_free_space)
        act_wipe_free_space.setDisabled(True)

        act_make_chaff = QtGui.QAction(_("Make Chaff"), self)
        act_make_chaff.triggered.connect(self._make_chaff)
        file_menu.addAction(act_make_chaff)
        act_make_chaff.setDisabled(True)

        file_menu.addSeparator()"""

        self.act_systeminfo = QtGui.QAction(_("System information"), self)
        self.act_systeminfo.triggered.connect(self._show_sysinfo_dialog)
        file_menu.addAction(self.act_systeminfo)

        file_menu.addSeparator()

        self.act_quit = QtGui.QAction(_("Quit"), self) #self.act_quit.setShortcut(QtGui.QKeySequence(""))
        self.act_quit.triggered.connect(self.close)
        file_menu.addAction(self.act_quit)

        # Edit menu with Preferences
        edit_menu = menu_bar.addMenu(_("&Edit"))
        self.act_preferences = QtGui.QAction(_("Preferences"), self) #self.act_preferences.setShortcut(QtGui.QKeySequence(""))
        self.act_preferences.triggered.connect(self._show_preferences_dialog)
        edit_menu.addAction(self.act_preferences)

        # Help menu
        help_menu = menu_bar.addMenu(_("&Help"))
        self.act_about = QtGui.QAction(_("About"), self)
        self.act_about.triggered.connect(self._show_about_dialog)
        help_menu.addAction(self.act_about)
 
    def _shred_files(self):
        dummy = True

    def _shred_folders(self):
        dummy = True

    def _shred_paths(self):
        dummy = True

    def _wipe_free_space(self):
        dummy = True

    def _make_chaff(self):
        dummy = True

        #"This text is <b>bold</b> and <font color='red'>red</font>!"
    def _show_about_dialog(self):
        copyright=bleachbit.APP_COPYRIGHT
        program_name=APP_NAME
        version=bleachbit.APP_VERSION
        website=bleachbit.APP_URL
        about =  f"<br><b>{program_name} {version} Qt</b><br>"
        about += f"Program to clean unnecessary files<br>"
        about += f"<a href='{website}'>Website</a><br>"
        about += f"{copyright}"
        QtWidgets.QMessageBox.about(
            self,
            _("About BleachBit"),
            about # "{}\n\n{}".format(APP_NAME, _("Qt user interface (experimental).")
        )

    def _show_preferences_dialog(self):
        dlg = QtPreferencesDialog(self, cb_refresh_operations=self.cb_refresh_operations)
        dlg.exec()

    def _show_sysinfo_dialog(self):
        dlg = QtSystemInformationDialog(self)
        dlg.exec()

        # TODO: this
    def shred_paths(self, paths, shred_settings=False):
        """Shred file or folders
        When shredding_settings=True:
        If user confirms to delete, then returns True.  If user aborts, returns
        False.
        """
        from bleachbit import Cleaner
        from bleachbit.Cleaner import backends
        # create a temporary cleaner object
        backends['_gui'] = Cleaner.create_simple_cleaner(paths)

        # preview and confirm
        operations = {'_gui': ['files']}
        self.preview_or_run_operations(False, operations)

        if self._confirm_delete(False, shred_settings):
            # delete
            self.preview_or_run_operations(True, operations)
            if shred_settings:
                return True
            
        # TODO: Figure how to implement auto exit here properly
        """
        if self._auto_exit:
            GLib.idle_add(self.close,
                          priority=GLib.PRIORITY_LOW)
        """
        # user aborted
        return False


    # ---------- cleaners tree ----------

    def _populate_cleaners_tree(self):
        """
        Register cleaners and populate the tree widget with
        backends and options. This is synchronous for now.
        """
        self.update_progress_bar("Loading cleaners…")
        try:
            gen = register_cleaners(self.update_progress_bar, lambda: None)
            for _ in gen:
                QtWidgets.QApplication.processEvents()
        except Exception:
            logger.exception("Error registering cleaners")
        finally:
            self.update_progress_bar(0.0)

        self.tree.clear()

        hidden_cleaners = []
        # Build tree: top-level = cleaners, children = options
        for key in sorted(backends):
            backend = backends[key]
            options_list = list(backend.get_options())
            if not options_list:
                # localizations has no options, so it should be hidden
                # https://github.com/az0/bleachbit/issues/110
                continue

            cleaner_name = backend.get_name()
            cleaner_id = backend.get_id()
            cleaner_checked = bool(options.get_tree(cleaner_id, None))

            if not cleaner_checked and options.get('auto_hide') and backend.auto_hide():
                hidden_cleaners.append(cleaner_id)
                continue

            cleaner_item = QtWidgets.QTreeWidgetItem(self.tree)
            cleaner_item.setText(0, cleaner_name)
            cleaner_item.setText(1, "")
            cleaner_item.setFlags(
                cleaner_item.flags() | QtCore.Qt.ItemIsUserCheckable
            )
            cleaner_item.setCheckState(
                0, QtCore.Qt.Checked if cleaner_checked else QtCore.Qt.Unchecked
            )
            cleaner_item.setData(
                0, QtCore.Qt.UserRole,
                {"type": "cleaner", "id": cleaner_id}
            )

            # Options
            for opt_id, opt_name in options_list:
                opt_checked = bool(options.get_tree(cleaner_id, opt_id))

                opt_item = QtWidgets.QTreeWidgetItem(cleaner_item)
                blocked = opt_item.treeWidget().blockSignals(True) # block signals to prevent recursive emits
                opt_item.setText(0, opt_name)
                opt_item.setText(1, "")
                opt_item.setFlags(
                    opt_item.flags() | QtCore.Qt.ItemIsUserCheckable
                )
                opt_item.setCheckState(
                    0, QtCore.Qt.Checked if opt_checked else QtCore.Qt.Unchecked
                )
                opt_item.setData(
                    0, QtCore.Qt.UserRole,
                    {"type": "option", "cleaner_id": cleaner_id, "id": opt_id}
                )
                opt_item.treeWidget().blockSignals(blocked) # remove block 

        if hidden_cleaners:
            logger.debug("automatically hid %d cleaners: %s", len(
                hidden_cleaners), ', '.join(hidden_cleaners))

        self.tree.expandAll()

    # ---------- Tree helpers / selection ----------

    def _on_tree_item_changed(self, item, column):
        """
        Handle toggling of cleaners and options.
        """
        if column != 0:
            return

        data = item.data(0, QtCore.Qt.UserRole)
        if not isinstance(data, dict):
            return

        checked = (item.checkState(0) == QtCore.Qt.Checked)

        if data.get("type") == "cleaner":
            cleaner_id = data.get("id")
            # Toggle all child options to same state
            for i in range(item.childCount()):
                child = item.child(i)
                child.setCheckState(0, QtCore.Qt.Checked if checked else QtCore.Qt.Unchecked)
            # Save parent state
            options.set_tree(cleaner_id, None, checked)

        elif data.get("type") == "option":
            cleaner_id = data.get("cleaner_id")
            opt_id = data.get("id")

            # When enabling an option, show warning if backend defines one
            if checked:
                backend = backends.get(cleaner_id)
                if backend:
                    warning = backend.get_warning(opt_id)
                    description = backend.get_option_description(opt_id)
                    if warning:
                        msg = _("Warning regarding %(cleaner)s - %(description)s:\n\n%(warning)s") % \
                            {'cleaner': backend.get_name(),
                            'description': description[0],
                            'warning': warning}
                        reply = QtWidgets.QMessageBox.question(
                            self,
                            APP_NAME,
                            msg,
                            QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel,
                            QtWidgets.QMessageBox.Cancel,
                        )
                        if reply != QtWidgets.QMessageBox.Ok:
                            # revert change
                            item.setCheckState(0, QtCore.Qt.Unchecked)
                            return

            # Save option state
            options.set_tree(cleaner_id, opt_id, checked)

            # Update parent cleaner checkbox:
            parent = item.parent()
            if parent is not None:
                any_child_checked = any(
                    parent.child(i).checkState(0) == QtCore.Qt.Checked
                    for i in range(parent.childCount())
                )
                blocked = parent.treeWidget().blockSignals(True) # block signals to prevent recursive emits
                parent.setCheckState(
                    0, QtCore.Qt.Checked if any_child_checked else QtCore.Qt.Unchecked
                )
                parent.treeWidget().blockSignals(blocked) # remove block
                options.set_tree(cleaner_id, None, any_child_checked)

    def get_selected_operations(self):
        """Return a list of cleaner IDs that are enabled in the tree."""
        ret = []
        top_count = self.tree.topLevelItemCount()
        for i in range(top_count):
            item = self.tree.topLevelItem(i)
            if item.checkState(0) == QtCore.Qt.Checked:
                data = item.data(0, QtCore.Qt.UserRole)
                if isinstance(data, dict) and data.get("type") == "cleaner":
                    ret.append(data.get("id"))
        return ret

    def get_operation_options(self, operation):
        """For the given cleaner ID, return a list of selected option IDs."""
        ret = []
        top_count = self.tree.topLevelItemCount()
        for i in range(top_count):
            item = self.tree.topLevelItem(i)
            data = item.data(0, QtCore.Qt.UserRole)
            if not isinstance(data, dict):
                continue
            if data.get("type") != "cleaner":
                continue
            if data.get("id") != operation:
                continue

            if item.childCount() == 0:
                return None

            for j in range(item.childCount()):
                child = item.child(j)
                if child.checkState(0) == QtCore.Qt.Checked:
                    cdata = child.data(0, QtCore.Qt.UserRole)
                    if isinstance(cdata, dict):
                        ret.append(cdata.get("id"))
        return ret

    # ---------- Worker interface / actions ----------

    def _on_preview_clicked(self):
        self.preview_or_run_operations(False)

    def _on_clean_clicked(self):
        if self._confirm_delete(mention_preview=True):
            self.preview_or_run_operations(True)

    def _confirm_delete(self, mention_preview, shred_settings=False):
        """
        Qt version of the confirmation dialog before cleaning.
        """
        if not options.get("delete_confirmation"):
            return True

        if mention_preview:
            text = _(
                "Are you sure you want to permanently delete the selected items?\n"
                "You may want to run a preview first."
            )
        else:
            text = _("Are you sure you want to permanently delete the selected items?")

        reply = QtWidgets.QMessageBox.question(
            self,
            APP_NAME,
            text,
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        return reply == QtWidgets.QMessageBox.Yes

    def preview_or_run_operations(self, really_delete, operations=None):
        """
        Equivalent to GUI.preview_or_run_operations(), but driven by Qt's
        event loop instead of GLib.idle_add.
        """
        assert isinstance(really_delete, bool)

        from bleachbit import Worker

        self.start_time = None

        if not operations:
            operations = {
                operation: self.get_operation_options(operation)
                for operation in self.get_selected_operations()
            }
        if not operations:
            QtWidgets.QMessageBox.warning(
                self,
                APP_NAME,
                _("You must select an operation"),
            )
            return

        # UI prep
        self.set_sensitive(False)
        self.log_edit.clear()
        self.progressbar.setValue(0)
        self.stop_button.setEnabled(True)

        try:
            self.worker = Worker.Worker(self, really_delete, operations)
        except Exception:
            logger.exception("Error in Worker()")
            self.set_sensitive(True)
            self.stop_button.setEnabled(False)
            return

        self.start_time = time.time()
        self._worker_gen = self.worker.run()
        self._continue_worker()

    def _continue_worker(self):
        """
        Step through the Worker generator, scheduling the next step
        via a 0ms singleShot to keep the UI responsive.
        """
        if self._worker_gen is None:
            return
        try:
            next(self._worker_gen)
        except StopIteration:
            really_delete = getattr(self.worker, "really_delete", False)
            self.worker_done(self.worker, really_delete)
            self.worker = None
            self._worker_gen = None
        else:
            QtCore.QTimer.singleShot(0, self._continue_worker)

    def cb_stop_operations(self):
        """Callback to stop the preview/cleaning process"""
        if self.worker is not None:
            try:
                self.worker.abort()
            except Exception:
                logger.exception("Error aborting worker")
        self.stop_button.setEnabled(False)

    # ---------- Worker callbacks ----------

    def append_text(self, text, tag=None, __iter=None, scroll=True):
        """
        Add some text to the log. tag may be 'error', etc.
        """
        if tag == 'error':
            text = "ERROR: " + text
        self.log_edit.moveCursor(QtGui.QTextCursor.End)
        self.log_edit.insertPlainText(text)
        if scroll:
            self.log_edit.moveCursor(QtGui.QTextCursor.End)

    def update_progress_bar(self, status):
        """
        Callback to update the progress bar with number or text.
        - float -> percentage
        - str   -> message text
        """
        if isinstance(status, float):
            self.progressbar.setRange(0, 100)
            self.progressbar.setValue(int(max(0.0, min(1.0, status)) * 100))
            self.progressbar.setFormat("%p%")
        elif isinstance(status, str):
            self.progressbar.setFormat(status)
        else:
            raise RuntimeError('unexpected type: ' + str(type(status)))

    def update_total_size(self, bytes_removed):
        """Update the total size cleaned (status bar)."""
        self.total_label.setText(bytes_to_human(bytes_removed))

    def update_item_size(self, operation, option_id, bytes_removed):
        """
        Update size in tree control, similar to GUI.update_item_size().
        operation   -> cleaner ID
        option_id   -> option ID or -1 for total per cleaner
        """
        size_text = bytes_to_human(bytes_removed)
        if bytes_removed == 0:
            size_text = ""

        top_count = self.tree.topLevelItemCount()
        for i in range(top_count):
            cleaner_item = self.tree.topLevelItem(i)
            data = cleaner_item.data(0, QtCore.Qt.UserRole)
            if not isinstance(data, dict):
                continue
            if data.get("type") != "cleaner":
                continue
            if data.get("id") != operation:
                continue

            if option_id == -1:
                cleaner_item.setText(1, size_text)
            else:
                for j in range(cleaner_item.childCount()):
                    child = cleaner_item.child(j)
                    cdata = child.data(0, QtCore.Qt.UserRole)
                    if isinstance(cdata, dict) and cdata.get("id") == option_id:
                        child.setText(1, size_text)
                        break
            break

    def worker_done(self, worker, really_delete):
        """
        Called when the Worker is finished.
        """
        self.progressbar.setValue(100)
        self.progressbar.setFormat(_("Done."))
        self.set_sensitive(True)
        self.stop_button.setEnabled(False)

        if really_delete and options.get("exit_done") and self._auto_exit:
            QtWidgets.QApplication.quit()

        self.log_edit.moveCursor(QtGui.QTextCursor.End)

        elapsed = (time.time() - self.start_time)
        logger.debug('elapsed time: %d seconds', elapsed)

    def set_sensitive(self, enabled: bool):
        """Enable/disable main interactive widgets."""
        self.preview_button.setEnabled(enabled)
        self.clean_button.setEnabled(enabled)
        self.tree.setEnabled(enabled)
        # stop_button handled separately

    # ---------- Preferences-related ----------

    def cb_refresh_operations(self):
        """Refresh cleaners list after preference changes (e.g. auto_hide, language)."""
        self._populate_cleaners_tree()

    # ---------- misc ----------

    def closeEvent(self, event: QtGui.QCloseEvent):
        """
        Make sure we don't keep running a worker after the window closes.
        """
        if self.worker is not None and not getattr(self.worker, "is_aborted", False):
            reply = QtWidgets.QMessageBox.question(
                self,
                APP_NAME,
                _("A cleaning operation is still running. Abort and exit?"),
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No,
            )
            if reply != QtWidgets.QMessageBox.Yes:
                event.ignore()
                return
            try:
                self.worker.abort()
            except Exception:
                logger.exception("Error aborting worker on exit")
        event.accept()

def get_style_palette(app=None, style: str = "default") -> QPalette:
    """
    Return a QPalette for the given style. Example implementation for styles.

    style:
        'default'  -> use application's default palette
        'dark'     -> neutral dark theme
        'blue'     -> dark theme with blue accent
        'green'    -> dark theme with green accent
        'orange'   -> dark theme with orange accent
        'yellow'   -> dark theme with yellow accent
        'brown'    -> dark theme with brown accent
    """

    def make_dark_palette(accent: QColor) -> QPalette:
        p = QPalette(base_palette)

        # ---- Neutral dark base ----
        p.setColor(QPalette.Window, QColor(37, 37, 38))
        p.setColor(QPalette.WindowText, QColor(220, 220, 220))

        # Item views (tree/list/table)
        p.setColor(QPalette.Base, QColor(25, 25, 26))           # background for rows
        p.setColor(QPalette.AlternateBase, QColor(40, 40, 42))  # alternating row color

        # Tooltips
        p.setColor(QPalette.ToolTipBase, QColor(50, 50, 50))
        p.setColor(QPalette.ToolTipText, QColor(230, 230, 230))

        # Generic text / buttons
        p.setColor(QPalette.Text, QColor(220, 220, 220))
        p.setColor(QPalette.Button, QColor(60, 60, 60))         # used for checkbox indicator bg
        p.setColor(QPalette.ButtonText, QColor(220, 220, 220))

        # These roles + Button are used heavily by Fusion for checkbox drawing
        # Still, some issues w QTreeWidget checkboxes
        p.setColor(QPalette.Dark, QColor(20, 20, 20))
        p.setColor(QPalette.Mid, QColor(90, 90, 90))            # border color
        p.setColor(QPalette.Light, QColor(130, 130, 130))       # top/left highlight
        p.setColor(QPalette.Shadow, QColor(0, 0, 0))

        p.setColor(QPalette.BrightText, QColor(255, 80, 80))

        # Accent colors
        p.setColor(QPalette.Link, accent.lighter(110))
        p.setColor(QPalette.LinkVisited, accent.darker(115))
        p.setColor(QPalette.Highlight, accent)
        p.setColor(QPalette.HighlightedText, QColor(0, 0, 0))

        # Disabled state
        disabled = QPalette.Disabled
        gray = QColor(127, 127, 127)
        p.setColor(disabled, QPalette.WindowText, gray)
        p.setColor(disabled, QPalette.Text, gray)
        p.setColor(disabled, QPalette.ButtonText, gray)
        p.setColor(disabled, QPalette.Highlight, QColor(70, 70, 70))
        p.setColor(disabled, QPalette.HighlightedText, gray)

        return p


    base_palette = QPalette() if app is None else app.palette()
    s = (style or "default").lower()

    if s == "default":
        return base_palette
    
    app.setStyleSheet("""
        QTreeView::indicator:unchecked,
        QTreeWidget::indicator:unchecked {
            border: 1px solid rgb(64,64,64);
            background: rgb(0,0,0);
        }
    """)

    # Theme accents
    if s == "dark":
        accent = QColor(128, 128, 128)
    elif s == "blue":
        accent = QColor(66, 133, 244)
    elif s == "green":
        accent = QColor(52, 168, 83)
    elif s == "orange":
        accent = QColor(244, 160, 0)
    elif s == "yellow":
        accent = QColor(251, 188, 5)
    elif s == "brown":
        accent = QColor(160, 112, 72)
    else:
        return base_palette

    return make_dark_palette(accent)


def main_qt(auto_exit = False):
    """
    Convenience entry point to run the Qt UI from Python code.
    """

    app = QtWidgets.QApplication(sys.argv)
    app.setStyle('Fusion')
    # An example how to set the optional theme: app.setPalette(get_a_style_palette(app, 'orange'))
    app.setPalette(get_style_palette(app))
    app.setApplicationName(APP_NAME)
    if appicon_path and os.path.exists(appicon_path):
        app.setWindowIcon(QtGui.QIcon(appicon_path))
    window = BleachBitQtMainWindow(auto_exit=auto_exit)
    
    window.show()
    return app.exec()
