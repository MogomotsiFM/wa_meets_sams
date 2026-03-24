from copy import deepcopy

from PyQt5.QtCore import Qt

from PyQt5.QtWidgets import QTableWidget, QComboBox, QLineEdit, QFrame
from PyQt5.QtWidgets import QPushButton, QFileDialog

import qtawesome as qta

class CoverPagesTable(QTableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setColumnCount(5)
        self.horizontalHeader().setVisible(False)
        self.verticalHeader().setVisible(False)
        self.setFrameShape(QFrame.NoFrame)
        self.setShowGrid(False)

        self.options = set(["FET", "Senior", "Foundation", "Intermediate"])

        # Add initial row
        self.add_row()


    def add_row(self):
        row = self.rowCount()
        self.insertRow(row)

        # ComboBox
        combo = QComboBox()
        combo.addItems(self.options)
        self.setCellWidget(row, 0, combo)

        # LineEdit
        line_edit = QLineEdit()
        self.setCellWidget(row, 1, line_edit)

        # Browse Button
        browse_btn = QPushButton()
        folder_icon = qta.icon('fa6.folder-open', color='black')
        browse_btn.setIcon(folder_icon)
        browse_btn.setToolTip("Browse for file")
        browse_btn.adjustSize()
        browse_btn.clicked.connect(lambda: self.browse_file(line_edit))
        self.setCellWidget(row, 2, browse_btn)

        # Remove Button
        remove_btn = QPushButton()
        minus_icon = qta.icon('fa5s.minus', color='black')
        remove_btn.setIcon(minus_icon)
        remove_btn.setToolTip("Remove this row")
        remove_btn.adjustSize()
        remove_btn.clicked.connect(self.remove_row)
        self.setCellWidget(row, 3, remove_btn)

        # Add Button
        add_btn = QPushButton()
        plus_icon = qta.icon('fa5s.plus', color='black')
        add_btn.setIcon(plus_icon)
        add_btn.setToolTip("Add new row")
        add_btn.adjustSize()
        add_btn.clicked.connect(self.on_add_cover_page)
        self.setCellWidget(row, 4, add_btn)


    def browse_file(self, line_edit):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select File")
        if file_path:
            line_edit.setText(file_path)


    def remove_row(self):
        button = self.sender()
        if button:
            # Find the row of the button that was clicked
            for row in range(self.rowCount()):
                if self.cellWidget(row, 3) == button:
                    self.removeRow(row)
                    if self.rowCount() == 0:
                        self.add_row()
                    break


    def on_add_cover_page(self):
        options = deepcopy(self.options)
        for row in range(self.rowCount()):
            txt = self.cellWidget(row, 0).currentText()
            options.discard(txt)
        if len(options) > 0:
            self.add_row()


    def get_cover_pages(self):
        cps = {}
        for row in range(self.rowCount()):
            pg = self.cellWidget(row, 1).text()
            if len(pg) > 0:
                key = self.cellWidget(row, 0).currentText()
                cps[key] = pg
        return cps

