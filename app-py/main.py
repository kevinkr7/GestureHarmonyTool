import sys
import os
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from ui.main_window import MainWindow
from ui.styles import get_stylesheet

def main():
    app = QApplication(sys.argv)
    
    # Set app icon for taskbar and title bar
    import ctypes
    myappid = 'mycompany.myproduct.subproduct.version' # arbitrary string
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except Exception:
        pass
        
    app.setStyleSheet(get_stylesheet())
    
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logo', 'GHT.png')
    app.setWindowIcon(QIcon(icon_path))
    
    window = MainWindow()
    window.showMaximized()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
