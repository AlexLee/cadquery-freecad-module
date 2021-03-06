# -*- coding: utf-8 -*-
"""
Contains the mode that control the external changes of file.
"""
import os
from pyqode.core.api.mode import Mode
from pyqode.qt import QtCore, QtWidgets


class FileWatcherMode(Mode, QtCore.QObject):
    """ Watches the current file for external modifications.

    FileWatcher mode, check if the opened file has changed externally.

    """
    #: Signal emitted when the file has been deleted. The Signal is emitted
    #: with the current editor instance so that user have a chance to close
    #: the editor.
    file_deleted = QtCore.Signal(object)

    #: Signal emitted when the file has been reloaded in the editor.
    file_reloaded = QtCore.Signal()

    @property
    def auto_reload(self):
        """
        Automatically reloads changed files
        """
        return self._auto_reload

    @auto_reload.setter
    def auto_reload(self, value):
        self._auto_reload = value
        if self.editor:
            # propagate changes to every clone
            for clone in self.editor.clones:
                try:
                    clone.modes.get(FileWatcherMode).auto_reload = value
                except KeyError:
                    # this should never happen since we're working with clones
                    pass

    def __init__(self):
        QtCore.QObject.__init__(self)
        Mode.__init__(self)
        self._auto_reload = False
        self._flg_notify = False
        self._data = (None, None)
        self._timer = QtCore.QTimer()
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._check_mtime)
        self._mtime = 0
        self._notification_pending = False
        self._processing = False

    def on_state_changed(self, state):
        if state:
            self.editor.new_text_set.connect(self._update_mtime)
            self.editor.new_text_set.connect(self._timer.start)
            # self.editor.text_saved.connect(self._update_mtime)
            # self.editor.text_saved.connect(self._timer.start)
            # self.editor.text_saving.connect(self._timer.stop)
            self.editor.text_saving.connect(self._cancel_next_change)
            self.editor.text_saved.connect(self._restart_monitoring)
            self.editor.focused_in.connect(self._check_for_pending)
        else:
            self._timer.stop()
            self.editor.new_text_set.connect(self._update_mtime)
            self.editor.new_text_set.connect(self._timer.start)
            # self.editor.text_saved.disconnect(self._update_mtime)
            # self.editor.text_saved.disconnect(self._timer.start)
            # self.editor.text_saving.disconnect(self._timer.stop)
            self.editor.text_saving.disconnect(self._cancel_next_change)
            self.editor.text_saved.disconnect(self._restart_monitoring)
            self.editor.focused_in.disconnect(self._check_for_pending)
            self._timer.stop()

    def _cancel_next_change(self):
        self._timer.stop()
        for e in self.editor.clones:
            try:
                w = e.modes.get(self.__class__)
            except KeyError:
                pass
            else:
                w._cancel_next_change()

    def _restart_monitoring(self):
        self._update_mtime()
        for e in self.editor.clones:
            try:
                w = e.modes.get(self.__class__)
            except KeyError:
                pass
            else:
                w._restart_monitoring()
        self._timer.start()

    def _update_mtime(self):
        """ Updates modif time """
        try:
            self._mtime = os.path.getmtime(self.editor.file.path)
        except OSError:
            # file_path does not exists.
            self._mtime = 0
            self._timer.stop()
        except (TypeError, AttributeError):
            # file path is none, this happen if you use setPlainText instead of
            # openFile. This is perfectly fine, we just do not have anything to
            # watch
            self._timer.stop()

    def _check_mtime(self):
        """
        Checks watched file moficiation time.
        """
        if self.editor and self.editor.file.path:
            if not os.path.exists(self.editor.file.path) and self._mtime:
                self._notify_deleted_file()
            else:
                mtime = os.path.getmtime(self.editor.file.path)
                if mtime > self._mtime:
                    self._mtime = mtime
                    self._notify_change()

    def _notify(self, title, message, expected_action=None):
        """
        Notify user from external event
        """
        inital_value = self.editor.save_on_focus_out
        self.editor.save_on_focus_out = False
        self._flg_notify = True
        dlg_type = (QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        expected_action = (
            lambda *x: None) if not expected_action else expected_action
        if (self._auto_reload or QtWidgets.QMessageBox.question(
                self.editor, title, message, dlg_type,
                QtWidgets.QMessageBox.Yes) == QtWidgets.QMessageBox.Yes):
            expected_action(self.editor.file.path)
        self._update_mtime()
        self.editor.save_on_focus_out = inital_value

    def _notify_change(self):
        """
        Notify user from external change if autoReloadChangedFiles is False
        then reload the changed file in the editor
        """
        def inner_action(*args):
            """ Inner action: open file """
            self.editor.file.open(self.editor.file.path)
            self.file_reloaded.emit()

        args = ("File changed",
                "The file <i>%s</i> has changed externally.\nDo you want to "
                "reload it?" % os.path.basename(self.editor.file.path))
        kwargs = {"expected_action": inner_action}
        if self.editor.hasFocus():
            self._notify(*args, **kwargs)
        else:
            self._notification_pending = True
            self._data = (args, kwargs)

    def _check_for_pending(self, *args, **kwargs):
        """
        Checks if a notification is pending.
        """
        if self._notification_pending and not self._processing:
            self._processing = True
            args, kwargs = self._data
            self._notify(*args, **kwargs)
            self._notification_pending = False
            self._processing = False

    def _notify_deleted_file(self):
        """
        Notify user from external file deletion.
        """
        self.file_deleted.emit(self.editor)

    def clone_settings(self, original):
        self.auto_reload = original.auto_reload
