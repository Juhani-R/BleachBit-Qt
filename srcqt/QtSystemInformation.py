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


# standard library
import logging
import locale
import os
import platform
import sys

from PySide6 import QtCore, QtGui, QtWidgets

# local
import bleachbit
from bleachbit.General import get_executable

logger = logging.getLogger(__name__)


def get_version(four_parts=False):
    """Return version information as a string.

    CI builds will have an integer build number.

    If four_parts is True, always return a four-part version string.
    If False, return three or four parts, depending on available information.
    """
    build_number_env = os.getenv('APPVEYOR_BUILD_NUMBER')
    build_number_src = None
    try:
        from bleachbit.Revision import build_number as build_number_import
        build_number_src = build_number_import
    except ImportError:
        pass

    build_number = build_number_src or build_number_env
    if not build_number:
        if not four_parts:
            return bleachbit.APP_VERSION
        return f'{bleachbit.APP_VERSION}.0'
    assert build_number.isdigit()
    return f'{bleachbit.APP_VERSION}.{build_number}'


def get_qt_info():
    """Get dictionary of information about Qt / PySide6."""
    info = {}
    try:
        from PySide6 import __version__ as pyside6_version
        from PySide6 import QtCore, QtWidgets
    except Exception:
        logger.debug('PySide6 not available', exc_info=True)
        return info

    info['PySide6 version'] = pyside6_version
    try:
        info['Qt version'] = QtCore.qVersion()
    except Exception:
        pass

    # Style may depend on QApplication existing; handle both cases safely
    try:
        app = QtWidgets.QApplication.instance()
        if app is not None:
            info['Qt style'] = app.style().objectName()
        else:
            # This will work even without an existing QApplication in most cases
            info['Qt style'] = QtWidgets.QStyleFactory.keys()
    except Exception:
        pass

    return info


def get_system_information(include_qt=True):
    """Return system information as a string."""
    from collections import OrderedDict
    info = OrderedDict()

    # Application and library versions
    info['BleachBit version'] = get_version()

    try:
        # CI builds and Linux tarball will have a revision.
        from bleachbit.Revision import revision
        info['Git revision'] = revision
    except ImportError:
        pass

    if include_qt:
        info.update(get_qt_info())

    import sqlite3
    info['SQLite version'] = sqlite3.sqlite_version

    # Variables defined in __init__.py
    info['local_cleaners_dir'] = bleachbit.local_cleaners_dir
    info['locale_dir'] = bleachbit.locale_dir
    info['options_dir'] = bleachbit.options_dir
    info['personal_cleaners_dir'] = bleachbit.personal_cleaners_dir
    info['system_cleaners_dir'] = bleachbit.system_cleaners_dir

    # System environment information
    info['locale.getlocale'] = str(locale.getlocale())

    # Environment variables
    if 'posix' == os.name:
        envs = ('DESKTOP_SESSION', 'LOGNAME', 'USER', 'SUDO_UID')
    elif 'nt' == os.name:
        envs = ('APPDATA', 'cd', 'LocalAppData', 'LocalAppDataLow', 'Music',
                'USERPROFILE', 'ProgramFiles', 'ProgramW6432', 'TMP')
    else:
        envs = ()

    for env in envs:
        info[f'os.getenv({env})'] = os.getenv(env)

    info['os.path.expanduser(~")'] = os.path.expanduser('~')

    # Mac Version Name - Dictionary
    macosx_dict = {
        '5': 'Leopard',
        '6': 'Snow Leopard',
        '7': 'Lion',
        '8': 'Mountain Lion',
        '9': 'Mavericks',
        '10': 'Yosemite',
        '11': 'El Capitan',
        '12': 'Sierra',
    }

    if sys.platform == 'linux':
        from bleachbit.Unix import get_distribution_name_version
        info['get_distribution_name_version()'] = get_distribution_name_version()
    elif sys.platform.startswith('darwin'):
        if hasattr(platform, 'mac_ver'):
            mac_version = platform.mac_ver()[0]
            parts = mac_version.split('.')
            if len(parts) >= 2:
                version_minor = parts[1]
                if version_minor in macosx_dict:
                    info['platform.mac_ver()'] = f'{mac_version} ({macosx_dict[version_minor]})'
                else:
                    info['platform.mac_ver()'] = mac_version
    else:
        info['platform.uname().version'] = platform.uname().version

    # System information
    info['sys.argv'] = sys.argv
    info['sys.executable'] = get_executable()
    info['sys.version'] = sys.version
    if 'nt' == os.name:
        try:
            from win32com.shell import shell
            info['IsUserAnAdmin()'] = shell.IsUserAnAdmin()
        except Exception:
            logger.debug("Failed to query IsUserAnAdmin()", exc_info=True)
    info['__file__'] = __file__

    # Render the information as a string
    return '\n'.join(f'{key} = {value}' for key, value in info.items())


# ---------------------------------------------------------------------------
# Qt dialog
# ---------------------------------------------------------------------------

class QtSystemInformationDialog(QtWidgets.QDialog):
    """
    Qt implementation (Qt/PySide6) of of the BleachBit Show system information dialog
    """
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("System Information")

        layout = QtWidgets.QVBoxLayout(self)

        label = QtWidgets.QLabel(
            "This information is useful for troubleshooting and bug reports"
        )
        self.resize(600, 550)
        label.setWordWrap(True)
        layout.addWidget(label)

        self.text = QtWidgets.QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap)
        font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)
        self.text.setFont(font)
        self.text.setPlainText(get_system_information(include_qt=True))
        layout.addWidget(self.text, 1)

        btn_row = QtWidgets.QHBoxLayout()
        layout.addLayout(btn_row)

        self.btn_copy = QtWidgets.QPushButton("Copy")
        self.btn_copy.clicked.connect(self._copy)
        btn_row.addWidget(self.btn_copy)

        self.btn_save = QtWidgets.QPushButton("Save…")
        self.btn_save.clicked.connect(self._save)
        btn_row.addWidget(self.btn_save)

        btn_row.addStretch(1)

        self.btn_close = QtWidgets.QPushButton("Close")
        self.btn_close.clicked.connect(self.accept)   # <-- self.accept
        btn_row.addWidget(self.btn_close)


    def _copy(self):
        QtWidgets.QApplication.clipboard().setText(self.text.toPlainText())

    def _save(self):
        suggested = "bleachbit-system-information.txt"
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save system information",
            suggested,
            "Text files (*.txt);;All files (*)",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.text.toPlainText())
        except OSError as exc:
            QtWidgets.QMessageBox.critical(
                self,
                "Error",
                f"Failed to save file:\n{exc}",
                QtWidgets.QMessageBox.Ok,
            )
