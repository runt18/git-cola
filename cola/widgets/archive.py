from __future__ import division, absolute_import, unicode_literals

import os

from PyQt4 import QtCore
from PyQt4 import QtGui
from PyQt4.QtCore import Qt
from PyQt4.QtCore import SIGNAL

from cola import cmds
from cola import core
from cola import icons
from cola import qtutils
from cola.git import git
from cola.git import STDOUT
from cola.i18n import N_
from cola.widgets import defs


class ExpandableGroupBox(QtGui.QGroupBox):

    def __init__(self, parent=None):
        QtGui.QGroupBox.__init__(self, parent)
        self.setFlat(True)
        self.expanded = True
        self.click_pos = None
        self.arrow_icon_size = defs.small_icon

    def set_expanded(self, expanded):
        if expanded == self.expanded:
            self.emit(SIGNAL('expanded(bool)'), expanded)
            return
        self.expanded = expanded
        for widget in self.findChildren(QtGui.QWidget):
            widget.setHidden(not expanded)
        self.emit(SIGNAL('expanded(bool)'), expanded)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            option = QtGui.QStyleOptionGroupBox()
            self.initStyleOption(option)
            icon_size = defs.small_icon
            button_area = QtCore.QRect(0, 0, icon_size, icon_size)
            offset = icon_size + defs.spacing
            adjusted = option.rect.adjusted(0, 0, -offset, 0)
            top_left = adjusted.topLeft()
            button_area.moveTopLeft(QtCore.QPoint(top_left))
            self.click_pos = event.pos()
        QtGui.QGroupBox.mousePressEvent(self, event)

    def mouseReleaseEvent(self, event):
        if (event.button() == Qt.LeftButton and
            self.click_pos == event.pos()):
            self.set_expanded(not self.expanded)
        QtGui.QGroupBox.mouseReleaseEvent(self, event)

    def paintEvent(self, event):
        painter = QtGui.QStylePainter(self)
        option = QtGui.QStyleOptionGroupBox()
        self.initStyleOption(option)
        painter.save()
        painter.translate(self.arrow_icon_size + defs.spacing, 0)
        painter.drawText(option.rect, Qt.AlignLeft, self.title())
        painter.restore()

        style = QtGui.QStyle
        point = option.rect.adjusted(0, -4, 0, 0).topLeft()
        icon_size = self.arrow_icon_size
        option.rect = QtCore.QRect(point.x(), point.y(), icon_size, icon_size)
        if self.expanded:
            painter.drawPrimitive(style.PE_IndicatorArrowDown, option)
        else:
            painter.drawPrimitive(style.PE_IndicatorArrowRight, option)


def show_save_dialog(oid, parent=None):
    shortoid = oid[:7]
    dlg = GitArchiveDialog(oid, shortoid, parent=parent)
    dlg.show()
    dlg.raise_()
    if dlg.exec_() != dlg.Accepted:
        return None
    return dlg


class GitArchiveDialog(QtGui.QDialog):

    def __init__(self, ref, shortref=None, parent=None):
        QtGui.QDialog.__init__(self, parent)
        if parent is not None:
            self.setWindowModality(Qt.WindowModal)

        # input
        self.ref = ref
        if shortref is None:
            shortref = ref

        # outputs
        self.fmt = None

        filename = '{0!s}-{1!s}'.format(os.path.basename(core.getcwd()), shortref)
        self.prefix = filename + '/'
        self.filename = filename

        # widgets
        self.setWindowTitle(N_('Save Archive'))

        self.filetext = QtGui.QLineEdit()
        self.filetext.setText(self.filename)

        self.browse = qtutils.create_toolbutton(icon=icons.file_zip())

        self.format_strings = (
                git.archive('--list')[STDOUT].rstrip().splitlines())
        self.format_combo = QtGui.QComboBox()
        self.format_combo.setEditable(False)
        self.format_combo.addItems(self.format_strings)

        self.close_button = qtutils.close_button()
        self.save_button = qtutils.create_button(text=N_('Save'),
                                                 icon=icons.save(),
                                                 default=True)
        self.prefix_label = QtGui.QLabel()
        self.prefix_label.setText(N_('Prefix'))
        self.prefix_text = QtGui.QLineEdit()
        self.prefix_text.setText(self.prefix)

        self.prefix_group = ExpandableGroupBox()
        self.prefix_group.setTitle(N_('Advanced'))

        # layouts
        self.filelayt = qtutils.hbox(defs.no_margin, defs.spacing,
                                     self.browse, self.filetext,
                                     self.format_combo)

        self.prefixlayt = qtutils.hbox(defs.margin, defs.spacing,
                                       self.prefix_label, self.prefix_text)
        self.prefix_group.setLayout(self.prefixlayt)
        self.prefix_group.set_expanded(False)

        self.btnlayt = qtutils.hbox(defs.no_margin, defs.spacing,
                                    qtutils.STRETCH, self.close_button,
                                    self.save_button)

        self.mainlayt = qtutils.vbox(defs.margin, defs.no_spacing,
                                     self.filelayt, self.prefix_group,
                                     qtutils.STRETCH, self.btnlayt)
        self.setLayout(self.mainlayt)
        self.resize(defs.scale(520), defs.scale(10))

        # initial setup; done before connecting to avoid
        # signal/slot side-effects
        if 'tar.gz' in self.format_strings:
            idx = self.format_strings.index('tar.gz')
        elif 'zip' in self.format_strings:
            idx = self.format_strings.index('zip')
        else:
            idx = 0
        self.format_combo.setCurrentIndex(idx)
        self.update_filetext_for_format(idx)

        # connections
        self.connect(self.filetext, SIGNAL('textChanged(QString)'),
                     self.filetext_changed)

        self.connect(self.prefix_text, SIGNAL('textChanged(QString)'),
                     self.prefix_text_changed)

        self.connect(self.format_combo, SIGNAL('currentIndexChanged(int)'),
                     self.update_filetext_for_format)

        self.connect(self.prefix_group, SIGNAL('expanded(bool)'),
                     self.prefix_group_expanded)

        self.connect(self, SIGNAL('accepted()'), self.archive_saved)

        qtutils.connect_button(self.browse, self.choose_filename)
        qtutils.connect_button(self.close_button, self.reject)
        qtutils.connect_button(self.save_button, self.save_archive)

    def archive_saved(self):
        cmds.do(cmds.Archive, self.ref, self.fmt, self.prefix, self.filename)
        qtutils.information(N_('File Saved'),
                            N_('File saved to "%s"') % self.filename)

    def save_archive(self):
        filename = self.filename
        if not filename:
            return
        if core.exists(filename):
            title = N_('Overwrite File?')
            msg = N_('The file "%s" exists and will be overwritten.') % filename
            info_txt = N_('Overwrite "%s"?') % filename
            ok_txt = N_('Overwrite')
            if not qtutils.confirm(title, msg, info_txt, ok_txt,
                                   default=False, icon=icons.save()):
                return
        self.accept()

    def choose_filename(self):
        filename = qtutils.save_as(self.filename)
        if not filename:
            return
        self.filetext.setText(filename)
        self.update_filetext_for_format(self.format_combo.currentIndex())

    def filetext_changed(self, filename):
        self.filename = filename
        self.save.setEnabled(bool(self.filename))
        prefix = self.strip_exts(os.path.basename(self.filename)) + '/'
        self.prefix_text.setText(prefix)

    def prefix_text_changed(self, prefix):
        self.prefix = prefix

    def strip_exts(self, text):
        for format_string in self.format_strings:
            ext = '.'+format_string
            if text.endswith(ext):
                return text[:-len(ext)]
        return text

    def update_filetext_for_format(self, idx):
        self.fmt = self.format_strings[idx]
        text = self.strip_exts(self.filetext.text())
        self.filename = '{0!s}.{1!s}'.format(text, self.fmt)
        self.filetext.setText(self.filename)
        self.filetext.setFocus()
        if '/' in text:
            start = text.rindex('/') + 1
        else:
            start = 0
        self.filetext.setSelection(start, len(text) - start)

    def prefix_group_expanded(self, expanded):
        if expanded:
            self.prefix_text.setFocus()
        else:
            self.filetext.setFocus()
