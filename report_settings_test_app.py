import sys

from PyQt5.QtWidgets import QApplication

from View.options import Config

if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = Config(None, None)
    window.show()
    sys.exit(app.exec_())