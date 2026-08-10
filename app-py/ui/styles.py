def get_stylesheet():
    return """
    QWidget {
        background-color: #0b0f19;
        color: #e2e8f0;
        font-family: 'Segoe UI', Inter, sans-serif;
        font-size: 14px;
    }
    
    QLabel#title {
        font-size: 24px;
        font-weight: bold;
        color: #ffffff;
    }
    
    QLabel#subtitle {
        font-size: 14px;
        color: #94a3b8;
    }

    QPushButton {
        background-color: #1e293b;
        color: #ffffff;
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 10px 16px;
        font-weight: bold;
    }

    QPushButton:hover {
        background-color: #3b82f6;
        border-color: #60a5fa;
    }
    
    QPushButton:pressed {
        background-color: #2563eb;
    }
    
    QPushButton:disabled {
        background-color: #0f172a;
        color: #475569;
        border-color: #1e293b;
    }

    QPushButton#actionButton {
        background-color: #2563eb;
        border-color: #3b82f6;
    }
    
    QPushButton#actionButton:hover {
        background-color: #3b82f6;
        border-color: #60a5fa;
    }
    
    QPushButton#dangerButton {
        background-color: #b91c1c;
        border-color: #ef4444;
    }
    
    QPushButton#dangerButton:hover {
        background-color: #dc2626;
    }

    QComboBox {
        background-color: #1e293b;
        border: 1px solid #334155;
        border-radius: 6px;
        padding: 8px 12px;
        color: #e2e8f0;
    }
    
    QComboBox:drop-down {
        border-left: 1px solid #334155;
        width: 30px;
    }
    
    QComboBox QAbstractItemView {
        background-color: #1e293b;
        border: 1px solid #334155;
        selection-background-color: #3b82f6;
    }

    QFrame#previewFrame {
        background-color: #000000;
        border: 2px solid #334155;
        border-radius: 12px;
    }
    """
