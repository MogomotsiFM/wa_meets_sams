from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget, QCheckBox, QListWidget
from PyQt5.QtWidgets import QLineEdit, QPushButton, QGroupBox, QRadioButton

class DbSelection(QWidget):
    def __init__(self, parent):
        super().__init__(parent)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(main_layout)

        # Select database location
        layout = QHBoxLayout()
        db_location_group = QGroupBox(title="Select database location")
        db_location_group.setLayout(layout)
        self.local_db_radio = QRadioButton(text="On this computer")
        self.network_db_radio = QRadioButton(text="On the network")
        layout.addWidget(self.local_db_radio)
        layout.addWidget(self.network_db_radio)
        self.local_db_radio.setChecked(True)
        
        # Select specific database
        self.local_db_widget = QWidget()
        self.network_db_widget = QWidget()

        self.stacked_widget = QStackedWidget()

        layout = QVBoxLayout()
        self.db_group = QGroupBox(title="Option A: Databases on this computer")
        self.db_group.setLayout(layout)
        self.stacked_widget.addWidget(self.local_db_widget)
        self.stacked_widget.addWidget(self.network_db_widget)
        layout.addWidget(self.stacked_widget)

        # Local DB controls
        layout = QVBoxLayout()
        self.local_db_widget.setLayout(layout)

        self.copy_local_db_checkbox = QCheckBox(text="Copy database before opening")
        self.local_db_list = QListWidget()
        self.local_continue_login_btn = QPushButton(text="Continue")
        self.local_continue_login_btn.setEnabled(False)
        layout.addWidget(self.copy_local_db_checkbox)
        layout.addWidget(self.local_db_list)
        layout.addWidget(self.local_continue_login_btn)

        # Networked DB controls
        layout = QVBoxLayout()
        self.network_db_widget.setLayout(layout)

        self.network_db_path = QLineEdit()
        self.network_db_path.setReadOnly(True)
        
        self.browse_btn = QPushButton(text="Browse...")
        self.network_continue_btn = QPushButton(text="Continue")
        self.network_continue_btn.setEnabled(False)

        hlayout = QHBoxLayout()
        hlayout.addWidget(self.network_db_path)
        hlayout.addWidget(self.browse_btn)
        
        layout.addLayout(hlayout)
        layout.addWidget(self.network_continue_btn)
        layout.addStretch(2)


        main_layout.addWidget(db_location_group)
        main_layout.addSpacing(2)
        main_layout.addWidget(self.db_group)
