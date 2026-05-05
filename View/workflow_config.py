import os
import logging

from PyQt5.QtCore import QDate, QTime, QSize
from PyQt5.QtWidgets import QTimeEdit, QDateEdit, QMessageBox
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget, QGridLayout
from PyQt5.QtWidgets import QLineEdit, QPushButton, QLabel, QGroupBox, QRadioButton, QFileDialog

import qtawesome as qta

from Common.directories import AppDirectories

class WorkflowConfig(QWidget):
    def __init__(self, parent, app_dirs: AppDirectories):
        super().__init__(parent)

        self.app_dirs = app_dirs

        self.setStyleSheet("font: 75 12pt Arial;")

        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        glayout = QGridLayout()
        main_layout.addSpacing(2)

        grp = QGroupBox()
        grp.setLayout(glayout)
        main_layout.addWidget(grp)

        # School emblem
        text = QLabel(text="School emblem")
        self.emblem_edit = QLineEdit()
        self.emblem_btn = QPushButton()
        folder_icon = qta.icon("fa6.folder-open", color="black")
        self.emblem_btn.setIcon(folder_icon)
        self.emblem_btn.setToolTip("Browse for file")
        glayout.addWidget(text, 0, 0)
        glayout.addWidget(self.emblem_edit, 0, 1)
        glayout.addWidget(self.emblem_btn, 0, 2)


        # Deadline: At some point in time we need to start printing physical reports.
        self.text = QLabel(text="Deadline")
        self.text.setToolTip("The deadline for receipt of responses to opt-in messages. After this point, all opt-in messages are auto-declined. This needs to happen so we can prepare for in-person collection of report. For example, printing of reports.")
        self.dead_date = QDateEdit(QDate.currentDate())
        self.dead_date.setCalendarPopup(True)
        self.dead_time = QTimeEdit(QTime.currentTime())
        self.dead_time.setCalendarPopup(True)
        glayout.addWidget(self.text, 1, 0)
        dt_layout = QHBoxLayout()
        dt_layout.setContentsMargins(0, 0, 0, 0)
        dt_layout.addWidget(self.dead_date)
        dt_layout.addWidget(self.dead_time)
        self.deadline_info_btn = QPushButton()
        self.deadline_info_btn.setIcon(qta.icon("fa6s.question", color="black"))
        dt_layout.addWidget(self.deadline_info_btn)
        dt_layout.addStretch(0)
        glayout.addLayout(dt_layout, 1, 1)

        main_layout.addSpacing(5)

        # Report collection date and time
        text = QLabel(text="Report collection date")
        self.collection_date = QDateEdit(QDate.currentDate())
        self.collection_date.setCalendarPopup(True)
        self.collection_time = QTimeEdit(QTime.currentTime())
        self.collection_time.setCalendarPopup(True)
        glayout.addWidget(text, 2, 0)
        dt_layout = QHBoxLayout()
        dt_layout.addWidget(self.collection_date)
        dt_layout.addWidget(self.collection_time)
        dt_layout.addStretch(0)
        glayout.addLayout(dt_layout, 2, 1)

        main_layout.addSpacing(5)

        layout = QHBoxLayout()
        report_group = QGroupBox(title="Source of reports PDF")
        report_group.setLayout(layout)
        self.upload = QRadioButton(text="Upload")
        self.generate = QRadioButton(text="Generate")
        layout.addWidget(self.upload)
        layout.addWidget(self.generate)
        main_layout.addWidget(report_group)
        
        main_layout.addSpacing(5)

        wa_group = QGroupBox(title="WhatsApp Settings")
        main_layout.addWidget(wa_group)
        walayout = QGridLayout()
        wa_group.setLayout(walayout)

        # WhatsApp Cloud API token
        text = QLabel(text="Token")
        self.token_edit = QLineEdit()
        walayout.addWidget(text, 0, 0)
        walayout.addWidget(self.token_edit, 0, 1)

        # WhatsApp phone number ID
        text = QLabel(text="Phone Id")
        self.id_edit = QLineEdit()
        walayout.addWidget(text, 1, 0)
        walayout.addWidget(self.id_edit, 1, 1)


        # ngrok OR localtunnel
        vlayout = QVBoxLayout()
        layout = QHBoxLayout()
        webhook_group = QGroupBox(title="Webhook")
        webhook_group.setLayout(vlayout)
        vlayout.addLayout(layout)
        self.local_tunnel_radio = QRadioButton(text="LocalTunnel (Free)")
        self.ngrok_radio = QRadioButton(text="NGrok (Paid)")
        layout.addWidget(self.local_tunnel_radio)
        layout.addWidget(self.ngrok_radio)
        self.local_tunnel_radio.setChecked(True)

        main_layout.addSpacing(5)
        main_layout.addWidget(webhook_group)

        self.local_tunnel_widget = QWidget()
        self.ngrok_widget = QWidget()

        self.stacked_widget = QStackedWidget()

        layout = QVBoxLayout()
        self.domain_group = QGroupBox(title="Option A: LocalTunnel tunnel")
        self.domain_group.setLayout(layout)
        self.stacked_widget.addWidget(self.local_tunnel_widget)
        self.stacked_widget.addWidget(self.ngrok_widget)
        self.stacked_widget.setCurrentIndex(0)
        layout.addWidget(self.stacked_widget)

        vlayout.addWidget(self.domain_group)

        # LocalTunnel settings
        vlayout = QVBoxLayout()
        vlayout.setContentsMargins(0, 0, 0, 0)
        layout = QHBoxLayout()
        vlayout.addLayout(layout)
        self.local_tunnel_widget.setLayout(vlayout)
        label = QLabel(text="Domain:")
        self.lt_domain = QLineEdit()
        layout.addWidget(label)
        layout.addWidget(self.lt_domain)
        vlayout.addStretch(0)

        # ngrok settings
        vlayout = QVBoxLayout()
        vlayout.setContentsMargins(0, 0, 0, 0)
        layout = QHBoxLayout()
        vlayout.addLayout(layout)
        self.ngrok_widget.setLayout(vlayout)
        label = QLabel(text="Domain:")
        self.ngrok_domain = QLineEdit()
        layout.addWidget(label)
        layout.addWidget(self.ngrok_domain)
        vlayout.addStretch(0)

        self.init()

    
    def init(self):
        self.emblem_btn.clicked.connect(self.on_emblem_btn_clicked)
        self.local_tunnel_radio.clicked.connect(self.on_lt_radio_clicked)
        self.ngrok_radio.clicked.connect(self.on_ngrok_radio_clicked)
        self.deadline_info_btn.clicked.connect(self.on_dealine_info_btn_clicked)

        WA_SAMS_TOKEN = os.getenv("WA_SAMS_TOKEN")
        if WA_SAMS_TOKEN is not None:
            self.token_edit.setText(WA_SAMS_TOKEN)
        WA_SAMS_PHONE_ID = os.getenv("WA_SAMS_PHONE_ID")
        if WA_SAMS_PHONE_ID is not None:
            self.id_edit.setText(WA_SAMS_PHONE_ID)


    def on_dealine_info_btn_clicked(self):
        info_icon = qta.icon("mdi6.information", color="black")
        
        x = QMessageBox(QMessageBox.Icon.Information, "Deadline Date Info", self.text.toolTip())
        x.setIconPixmap(info_icon.pixmap(self.deadline_info_btn.size()))
        x.exec_()


    def on_lt_radio_clicked(self):
        logging.getLogger().info("LocalTunnel widget")
        self.stacked_widget.setCurrentWidget(self.local_tunnel_widget)
        self.domain_group.setTitle("Option A: LocalTunnel tunnel")


    def on_ngrok_radio_clicked(self):
        logging.getLogger().info("ngrok widget")
        self.stacked_widget.setCurrentWidget(self.ngrok_widget)
        self.domain_group.setTitle("Option B: NGrok tunnel")

    
    def on_emblem_btn_clicked(self):
        # The getOpenFileName returns a tuple, we only need the file name (the first element)
        file_name, _ = QFileDialog.getOpenFileName(self, 'Open File', '/', "All Files (*.*);;Python Files (*.py)")
        
        if file_name:
            if self.sender() == self.emblem_btn:
                self.emblem_edit.setText(file_name)

                self.app_dirs.school_emblem_path = file_name

