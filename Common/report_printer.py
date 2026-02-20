from PyQt5.QtCore import QThread

from Presenter.presenter import Presenter

class ReportPrinter(QThread):
    def __init__(self, presenter: Presenter):
        super().__init__()
        self.presenter = presenter

    def run(self):
        config = self.presenter.print_reports_config()
        print("Config: ", config)
        self.presenter.run(config["grades"], config["rooms"], config["cycles"], config["formats"])

