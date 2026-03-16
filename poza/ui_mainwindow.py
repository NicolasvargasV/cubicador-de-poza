# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'mainwindow.ui'
##
## Created by: Qt User Interface Compiler version 6.10.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFrame,
    QGridLayout, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMainWindow, QPushButton,
    QSizePolicy, QSpacerItem, QStatusBar, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget)

class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        if not MainWindow.objectName():
            MainWindow.setObjectName(u"MainWindow")
        MainWindow.resize(1200, 720)
        MainWindow.setStyleSheet(u"\n"
"QMainWindow { background-color: #EAECF4; }\n"
"   ")
        self.centralwidget = QWidget(MainWindow)
        self.centralwidget.setObjectName(u"centralwidget")
        self.centralwidget.setStyleSheet(u"background-color: #EAECF4;")
        self.verticalLayout_root = QVBoxLayout(self.centralwidget)
        self.verticalLayout_root.setSpacing(0)
        self.verticalLayout_root.setObjectName(u"verticalLayout_root")
        self.verticalLayout_root.setContentsMargins(0, 0, 0, 0)
        self.header = QWidget(self.centralwidget)
        self.header.setObjectName(u"header")
        self.header.setMinimumSize(QSize(0, 64))
        self.header.setMaximumSize(QSize(16777215, 64))
        self.header.setStyleSheet(u"\n"
"background: qlineargradient(x1:0, y1:0, x2:1, y2:0,\n"
"    stop:0 #1A2052, stop:0.5 #29306A, stop:1 #3D4A9A);\n"
"border-bottom: 2px solid #F75C03;\n"
"       ")
        self.horizontalLayout_header = QHBoxLayout(self.header)
        self.horizontalLayout_header.setSpacing(14)
        self.horizontalLayout_header.setObjectName(u"horizontalLayout_header")
        self.horizontalLayout_header.setContentsMargins(18, 10, 18, 10)
        self.headerAccent = QWidget(self.header)
        self.headerAccent.setObjectName(u"headerAccent")
        self.headerAccent.setMinimumSize(QSize(4, 36))
        self.headerAccent.setMaximumSize(QSize(4, 36))
        self.headerAccent.setStyleSheet(u"background-color: #F75C03; border-radius: 2px;")

        self.horizontalLayout_header.addWidget(self.headerAccent)

        self.lblTitle = QLabel(self.header)
        self.lblTitle.setObjectName(u"lblTitle")
        self.lblTitle.setStyleSheet(u"\n"
"color: #FFFFFF;\n"
"font: bold 15pt \"Segoe UI\";\n"
"background: transparent;\n"
"letter-spacing: 1px;\n"
"          ")

        self.horizontalLayout_header.addWidget(self.lblTitle)

        self.lblSubtitle = QLabel(self.header)
        self.lblSubtitle.setObjectName(u"lblSubtitle")
        self.lblSubtitle.setStyleSheet(u"\n"
"color: rgba(255,255,255,0.55);\n"
"font: 10pt \"Segoe UI\";\n"
"background: transparent;\n"
"          ")

        self.horizontalLayout_header.addWidget(self.lblSubtitle)

        self.headerSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_header.addItem(self.headerSpacer)

        self.lblReservLabel = QLabel(self.header)
        self.lblReservLabel.setObjectName(u"lblReservLabel")
        self.lblReservLabel.setStyleSheet(u"color: rgba(255,255,255,0.75); font: 9pt \"Segoe UI\"; background: transparent;")

        self.horizontalLayout_header.addWidget(self.lblReservLabel)

        self.cmbReservorio = QComboBox(self.header)
        self.cmbReservorio.setObjectName(u"cmbReservorio")
        self.cmbReservorio.setMinimumSize(QSize(155, 32))
        self.cmbReservorio.setStyleSheet(u"\n"
"QComboBox {\n"
"    background: rgba(255,255,255,0.15);\n"
"    color: #FFFFFF;\n"
"    border: 1px solid rgba(255,255,255,0.35);\n"
"    border-radius: 5px;\n"
"    padding: 4px 10px;\n"
"    font: 10pt \"Segoe UI\";\n"
"}\n"
"QComboBox:hover { background: rgba(255,255,255,0.25); }\n"
"QComboBox::drop-down { border: none; }\n"
"QComboBox QAbstractItemView {\n"
"    background: #29306A; color: white;\n"
"    selection-background-color: #F75C03;\n"
"}\n"
"          ")

        self.horizontalLayout_header.addWidget(self.cmbReservorio)


        self.verticalLayout_root.addWidget(self.header)

        self.body = QWidget(self.centralwidget)
        self.body.setObjectName(u"body")
        self.horizontalLayout_body = QHBoxLayout(self.body)
        self.horizontalLayout_body.setSpacing(14)
        self.horizontalLayout_body.setObjectName(u"horizontalLayout_body")
        self.horizontalLayout_body.setContentsMargins(16, 16, 16, 16)
        self.groupDem = QGroupBox(self.body)
        self.groupDem.setObjectName(u"groupDem")
        self.groupDem.setStyleSheet(u"\n"
"QGroupBox {\n"
"    background: #FFFFFF;\n"
"    border: 1px solid #D0D4E8;\n"
"    border-top: 3px solid #29306A;\n"
"    border-radius: 6px;\n"
"    margin-top: 12px;\n"
"    font: bold 11pt \"Segoe UI\";\n"
"    color: #29306A;\n"
"    padding-top: 6px;\n"
"}\n"
"QGroupBox::title {\n"
"    subcontrol-origin: margin;\n"
"    subcontrol-position: top left;\n"
"    left: 12px;\n"
"    padding: 0 6px;\n"
"    background: #FFFFFF;\n"
"}\n"
"          ")
        self.verticalLayout_dem = QVBoxLayout(self.groupDem)
        self.verticalLayout_dem.setSpacing(10)
        self.verticalLayout_dem.setObjectName(u"verticalLayout_dem")
        self.widgetDemActions = QWidget(self.groupDem)
        self.widgetDemActions.setObjectName(u"widgetDemActions")
        self.widgetDemActions.setStyleSheet(u"background: transparent;")
        self.gridLayout_demActions = QGridLayout(self.widgetDemActions)
        self.gridLayout_demActions.setSpacing(8)
        self.gridLayout_demActions.setObjectName(u"gridLayout_demActions")
        self.gridLayout_demActions.setContentsMargins(4, 4, 4, 4)
        self.btnPickDem = QPushButton(self.widgetDemActions)
        self.btnPickDem.setObjectName(u"btnPickDem")
        self.btnPickDem.setMinimumSize(QSize(0, 34))
        self.btnPickDem.setStyleSheet(u"\n"
"QPushButton {\n"
"    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,\n"
"        stop:0 #3D4A9A, stop:1 #29306A);\n"
"    color: white;\n"
"    font: bold 10pt \"Segoe UI\";\n"
"    padding: 6px 16px;\n"
"    border: none;\n"
"    border-radius: 5px;\n"
"}\n"
"QPushButton:hover {\n"
"    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,\n"
"        stop:0 #4A58B8, stop:1 #3D4A9A);\n"
"}\n"
"QPushButton:pressed { background: #1A2052; }\n"
"                ")

        self.gridLayout_demActions.addWidget(self.btnPickDem, 0, 0, 1, 1)

        self.btnPickMask = QPushButton(self.widgetDemActions)
        self.btnPickMask.setObjectName(u"btnPickMask")
        self.btnPickMask.setMinimumSize(QSize(0, 34))
        self.btnPickMask.setStyleSheet(u"\n"
"QPushButton {\n"
"    background: #F0F1F8;\n"
"    color: #29306A;\n"
"    font: 10pt \"Segoe UI\";\n"
"    padding: 6px 16px;\n"
"    border: 1px solid #C0C5E0;\n"
"    border-radius: 5px;\n"
"}\n"
"QPushButton:hover { background: #E0E3F4; border-color: #29306A; }\n"
"QPushButton:pressed { background: #D0D4E8; }\n"
"                ")

        self.gridLayout_demActions.addWidget(self.btnPickMask, 0, 1, 1, 1)

        self.chkUseMask = QCheckBox(self.widgetDemActions)
        self.chkUseMask.setObjectName(u"chkUseMask")
        self.chkUseMask.setChecked(True)
        self.chkUseMask.setStyleSheet(u"\n"
"QCheckBox {\n"
"    font: 10pt \"Segoe UI\";\n"
"    color: #29306A;\n"
"    spacing: 6px;\n"
"}\n"
"QCheckBox::indicator {\n"
"    width: 16px; height: 16px;\n"
"    border: 2px solid #29306A;\n"
"    border-radius: 3px;\n"
"    background: white;\n"
"}\n"
"QCheckBox::indicator:checked {\n"
"    background: #29306A;\n"
"    image: none;\n"
"}\n"
"                ")

        self.gridLayout_demActions.addWidget(self.chkUseMask, 0, 2, 1, 1)

        self.spacerDemActions = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.gridLayout_demActions.addItem(self.spacerDemActions, 0, 3, 1, 1)

        self.lblPaths = QLabel(self.widgetDemActions)
        self.lblPaths.setObjectName(u"lblPaths")
        self.lblPaths.setStyleSheet(u"\n"
"color: #808B96;\n"
"font: italic 9pt \"Segoe UI\";\n"
"background: #F7F8FC;\n"
"border: 1px solid #E0E3F0;\n"
"border-radius: 4px;\n"
"padding: 3px 8px;\n"
"                ")

        self.gridLayout_demActions.addWidget(self.lblPaths, 1, 0, 1, 4)


        self.verticalLayout_dem.addWidget(self.widgetDemActions)

        self.viewerContainer = QWidget(self.groupDem)
        self.viewerContainer.setObjectName(u"viewerContainer")
        self.viewerContainer.setStyleSheet(u"\n"
"background: #1A1A2E;\n"
"border: 1px solid #D0D4E8;\n"
"border-radius: 4px;\n"
"             ")
        self.verticalLayout_viewer = QVBoxLayout(self.viewerContainer)
        self.verticalLayout_viewer.setSpacing(0)
        self.verticalLayout_viewer.setObjectName(u"verticalLayout_viewer")
        self.verticalLayout_viewer.setContentsMargins(0, 0, 0, 0)

        self.verticalLayout_dem.addWidget(self.viewerContainer)


        self.horizontalLayout_body.addWidget(self.groupDem)

        self.rightPanel = QWidget(self.body)
        self.rightPanel.setObjectName(u"rightPanel")
        self.rightPanel.setStyleSheet(u"background: transparent;")
        self.verticalLayout_right = QVBoxLayout(self.rightPanel)
        self.verticalLayout_right.setSpacing(14)
        self.verticalLayout_right.setObjectName(u"verticalLayout_right")
        self.verticalLayout_right.setContentsMargins(0, 0, 0, 0)
        self.groupParams = QGroupBox(self.rightPanel)
        self.groupParams.setObjectName(u"groupParams")
        self.groupParams.setStyleSheet(u"\n"
"QGroupBox {\n"
"    background: #FFFFFF;\n"
"    border: 1px solid #D0D4E8;\n"
"    border-top: 3px solid #F75C03;\n"
"    border-radius: 6px;\n"
"    margin-top: 12px;\n"
"    font: bold 11pt \"Segoe UI\";\n"
"    color: #F75C03;\n"
"    padding-top: 6px;\n"
"}\n"
"QGroupBox::title {\n"
"    subcontrol-origin: margin;\n"
"    subcontrol-position: top left;\n"
"    left: 12px;\n"
"    padding: 0 6px;\n"
"    background: #FFFFFF;\n"
"}\n"
"             ")
        self.gridLayout_params = QGridLayout(self.groupParams)
        self.gridLayout_params.setSpacing(10)
        self.gridLayout_params.setObjectName(u"gridLayout_params")
        self.gridLayout_params.setContentsMargins(12, 10, 12, 12)
        self.lblSalt = QLabel(self.groupParams)
        self.lblSalt.setObjectName(u"lblSalt")
        self.lblSalt.setStyleSheet(u"font: 10pt \"Segoe UI\"; color: #333355;")

        self.gridLayout_params.addWidget(self.lblSalt, 0, 0, 1, 1)

        self.txtSalt = QLineEdit(self.groupParams)
        self.txtSalt.setObjectName(u"txtSalt")
        self.txtSalt.setStyleSheet(u"\n"
"QLineEdit {\n"
"    font: 10pt \"Segoe UI\";\n"
"    padding: 5px 8px;\n"
"    border: 1px solid #C5CAE9;\n"
"    border-radius: 4px;\n"
"    background: #F7F8FC;\n"
"    color: #1A2052;\n"
"}\n"
"QLineEdit:focus {\n"
"    border: 2px solid #29306A;\n"
"    background: #FFFFFF;\n"
"}\n"
"                ")

        self.gridLayout_params.addWidget(self.txtSalt, 0, 1, 1, 1)

        self.lblWater = QLabel(self.groupParams)
        self.lblWater.setObjectName(u"lblWater")
        self.lblWater.setStyleSheet(u"font: 10pt \"Segoe UI\"; color: #333355;")

        self.gridLayout_params.addWidget(self.lblWater, 1, 0, 1, 1)

        self.txtWater = QLineEdit(self.groupParams)
        self.txtWater.setObjectName(u"txtWater")
        self.txtWater.setStyleSheet(u"\n"
"QLineEdit {\n"
"    font: 10pt \"Segoe UI\";\n"
"    padding: 5px 8px;\n"
"    border: 1px solid #C5CAE9;\n"
"    border-radius: 4px;\n"
"    background: #F7F8FC;\n"
"    color: #1A2052;\n"
"}\n"
"QLineEdit:focus {\n"
"    border: 2px solid #29306A;\n"
"    background: #FFFFFF;\n"
"}\n"
"                ")

        self.gridLayout_params.addWidget(self.txtWater, 1, 1, 1, 1)

        self.lblOcc = QLabel(self.groupParams)
        self.lblOcc.setObjectName(u"lblOcc")
        self.lblOcc.setStyleSheet(u"font: 10pt \"Segoe UI\"; color: #333355;")

        self.gridLayout_params.addWidget(self.lblOcc, 2, 0, 1, 1)

        self.txtOcc = QLineEdit(self.groupParams)
        self.txtOcc.setObjectName(u"txtOcc")
        self.txtOcc.setStyleSheet(u"\n"
"QLineEdit {\n"
"    font: 10pt \"Segoe UI\";\n"
"    padding: 5px 8px;\n"
"    border: 1px solid #C5CAE9;\n"
"    border-radius: 4px;\n"
"    background: #F7F8FC;\n"
"    color: #1A2052;\n"
"}\n"
"QLineEdit:focus {\n"
"    border: 2px solid #29306A;\n"
"    background: #FFFFFF;\n"
"}\n"
"                ")

        self.gridLayout_params.addWidget(self.txtOcc, 2, 1, 1, 1)

        self.separator = QFrame(self.groupParams)
        self.separator.setObjectName(u"separator")
        self.separator.setFrameShape(QFrame.HLine)
        self.separator.setFrameShadow(QFrame.Sunken)
        self.separator.setStyleSheet(u"color: #E0E3F0;")

        self.gridLayout_params.addWidget(self.separator, 3, 0, 1, 2)

        self.widgetButtons = QWidget(self.groupParams)
        self.widgetButtons.setObjectName(u"widgetButtons")
        self.widgetButtons.setStyleSheet(u"background: transparent;")
        self.horizontalLayout_buttons = QHBoxLayout(self.widgetButtons)
        self.horizontalLayout_buttons.setSpacing(8)
        self.horizontalLayout_buttons.setObjectName(u"horizontalLayout_buttons")
        self.horizontalLayout_buttons.setContentsMargins(0, 0, 0, 0)
        self.btnCalculate = QPushButton(self.widgetButtons)
        self.btnCalculate.setObjectName(u"btnCalculate")
        self.btnCalculate.setMinimumSize(QSize(0, 36))
        self.btnCalculate.setStyleSheet(u"\n"
"QPushButton {\n"
"    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,\n"
"        stop:0 #FF7A30, stop:1 #F75C03);\n"
"    color: white;\n"
"    font: bold 10pt \"Segoe UI\";\n"
"    padding: 6px 18px;\n"
"    border: none;\n"
"    border-radius: 5px;\n"
"}\n"
"QPushButton:hover {\n"
"    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,\n"
"        stop:0 #FF8C4A, stop:1 #FF6A1A);\n"
"}\n"
"QPushButton:pressed { background: #D44C00; }\n"
"                   ")

        self.horizontalLayout_buttons.addWidget(self.btnCalculate)

        self.btnExportCsv = QPushButton(self.widgetButtons)
        self.btnExportCsv.setObjectName(u"btnExportCsv")
        self.btnExportCsv.setMinimumSize(QSize(0, 36))
        self.btnExportCsv.setStyleSheet(u"\n"
"QPushButton {\n"
"    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,\n"
"        stop:0 #3D4A9A, stop:1 #29306A);\n"
"    color: white;\n"
"    font: bold 10pt \"Segoe UI\";\n"
"    padding: 6px 14px;\n"
"    border: none;\n"
"    border-radius: 5px;\n"
"}\n"
"QPushButton:hover {\n"
"    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,\n"
"        stop:0 #4A58B8, stop:1 #3D4A9A);\n"
"}\n"
"QPushButton:pressed { background: #1A2052; }\n"
"                   ")

        self.horizontalLayout_buttons.addWidget(self.btnExportCsv)

        self.btnClear = QPushButton(self.widgetButtons)
        self.btnClear.setObjectName(u"btnClear")
        self.btnClear.setMinimumSize(QSize(0, 36))
        self.btnClear.setStyleSheet(u"\n"
"QPushButton {\n"
"    background: #EAECF4;\n"
"    color: #555577;\n"
"    font: 10pt \"Segoe UI\";\n"
"    padding: 6px 14px;\n"
"    border: 1px solid #C0C5E0;\n"
"    border-radius: 5px;\n"
"}\n"
"QPushButton:hover { background: #D8DBF0; color: #29306A; }\n"
"QPushButton:pressed { background: #C8CCE8; }\n"
"                   ")

        self.horizontalLayout_buttons.addWidget(self.btnClear)

        self.spacerBtns = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_buttons.addItem(self.spacerBtns)


        self.gridLayout_params.addWidget(self.widgetButtons, 4, 0, 1, 2)


        self.verticalLayout_right.addWidget(self.groupParams)

        self.groupResults = QGroupBox(self.rightPanel)
        self.groupResults.setObjectName(u"groupResults")
        self.groupResults.setStyleSheet(u"\n"
"QGroupBox {\n"
"    background: #FFFFFF;\n"
"    border: 1px solid #D0D4E8;\n"
"    border-top: 3px solid #29B6A8;\n"
"    border-radius: 6px;\n"
"    margin-top: 12px;\n"
"    font: bold 11pt \"Segoe UI\";\n"
"    color: #29B6A8;\n"
"    padding-top: 6px;\n"
"}\n"
"QGroupBox::title {\n"
"    subcontrol-origin: margin;\n"
"    subcontrol-position: top left;\n"
"    left: 12px;\n"
"    padding: 0 6px;\n"
"    background: #FFFFFF;\n"
"}\n"
"             ")
        self.verticalLayout_results = QVBoxLayout(self.groupResults)
        self.verticalLayout_results.setObjectName(u"verticalLayout_results")
        self.verticalLayout_results.setContentsMargins(8, 8, 8, 8)
        self.treeResults = QTreeWidget(self.groupResults)
        self.treeResults.setObjectName(u"treeResults")
        self.treeResults.setStyleSheet(u"\n"
"QTreeWidget {\n"
"    font: 10pt \"Segoe UI\";\n"
"    border: 1px solid #D8DBF0;\n"
"    border-radius: 4px;\n"
"    background: #FAFBFF;\n"
"    alternate-background-color: #F0F2FA;\n"
"    color: #222244;\n"
"    gridline-color: #E8EAF6;\n"
"    outline: none;\n"
"}\n"
"QTreeWidget::item { padding: 4px 6px; }\n"
"QTreeWidget::item:selected {\n"
"    background: #29306A;\n"
"    color: white;\n"
"    border-radius: 3px;\n"
"}\n"
"QTreeWidget::item:hover:!selected { background: #E8EBF8; }\n"
"QHeaderView::section {\n"
"    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,\n"
"        stop:0 #3D4A9A, stop:1 #29306A);\n"
"    color: white;\n"
"    font: bold 10pt \"Segoe UI\";\n"
"    padding: 6px 8px;\n"
"    border: none;\n"
"    border-right: 1px solid #4A58B8;\n"
"}\n"
"QScrollBar:vertical {\n"
"    background: #F0F2FA;\n"
"    width: 8px;\n"
"    border-radius: 4px;\n"
"}\n"
"QScrollBar::handle:vertical {\n"
"    background: #C0C5E0;\n"
"    border-radius: 4px;\n"
"    min-height: 30px;\n"
"}\n"
"QScro"
                        "llBar::handle:vertical:hover { background: #29306A; }\n"
"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }\n"
"                ")
        self.treeResults.setAlternatingRowColors(True)

        self.verticalLayout_results.addWidget(self.treeResults)


        self.verticalLayout_right.addWidget(self.groupResults)


        self.horizontalLayout_body.addWidget(self.rightPanel)


        self.verticalLayout_root.addWidget(self.body)

        MainWindow.setCentralWidget(self.centralwidget)
        self.statusbar = QStatusBar(MainWindow)
        self.statusbar.setObjectName(u"statusbar")
        self.statusbar.setStyleSheet(u"\n"
"QStatusBar {\n"
"    background: #29306A;\n"
"    color: rgba(255,255,255,0.7);\n"
"    font: 9pt \"Segoe UI\";\n"
"    border-top: 1px solid #1A2052;\n"
"}\n"
"    ")
        MainWindow.setStatusBar(self.statusbar)

        self.retranslateUi(MainWindow)

        QMetaObject.connectSlotsByName(MainWindow)
    # setupUi

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle(QCoreApplication.translate("MainWindow", u"Cubicador de Pozas", None))
        self.lblTitle.setText(QCoreApplication.translate("MainWindow", u"Cubicador de Pozas", None))
        self.lblSubtitle.setText(QCoreApplication.translate("MainWindow", u"\u2014 C\u00e1lculo de vol\u00famenes", None))
        self.lblReservLabel.setText(QCoreApplication.translate("MainWindow", u"Reservorio:", None))
        self.groupDem.setTitle(QCoreApplication.translate("MainWindow", u"  Vista DEM", None))
        self.btnPickDem.setText(QCoreApplication.translate("MainWindow", u"\U0001f4c2  Elegir DEM\U00002026", None))
        self.btnPickMask.setText(QCoreApplication.translate("MainWindow", u"\U0001f5fa  Subir contorno\U00002026", None))
        self.chkUseMask.setText(QCoreApplication.translate("MainWindow", u"Usar contorno", None))
        self.lblPaths.setText(QCoreApplication.translate("MainWindow", u"Sin DEM cargado", None))
        self.groupParams.setTitle(QCoreApplication.translate("MainWindow", u"  Par\u00e1metros de c\u00e1lculo", None))
        self.lblSalt.setText(QCoreApplication.translate("MainWindow", u"Cota de sal (m):", None))
        self.lblWater.setText(QCoreApplication.translate("MainWindow", u"Cota pelo de agua (m):", None))
        self.lblOcc.setText(QCoreApplication.translate("MainWindow", u"Fracci\u00f3n ocluida (0\u20131):", None))
        self.txtOcc.setText(QCoreApplication.translate("MainWindow", u"0.20", None))
        self.btnCalculate.setText(QCoreApplication.translate("MainWindow", u"\u25b6  Calcular", None))
        self.btnExportCsv.setText(QCoreApplication.translate("MainWindow", u"\u2193  Exportar CSV", None))
        self.btnClear.setText(QCoreApplication.translate("MainWindow", u"\u2715  Limpiar", None))
        self.groupResults.setTitle(QCoreApplication.translate("MainWindow", u"  Resultados", None))
        ___qtreewidgetitem = self.treeResults.headerItem()
        ___qtreewidgetitem.setText(2, QCoreApplication.translate("MainWindow", u"Unidad", None));
        ___qtreewidgetitem.setText(1, QCoreApplication.translate("MainWindow", u"Valor", None));
        ___qtreewidgetitem.setText(0, QCoreApplication.translate("MainWindow", u"Item", None));
    # retranslateUi

