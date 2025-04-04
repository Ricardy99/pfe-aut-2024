
import sys
import subprocess
import re
from PyQt5.QtCore import QObject, QRunnable, QThreadPool, Qt, pyqtSignal, pyqtSlot, QProcess, QTimer
from PyQt5.QtGui import QColor, QBrush
from PyQt5.QtWidgets import ( 
    QApplication, QLabel, QMainWindow, QPlainTextEdit, QPushButton, QVBoxLayout, QHBoxLayout, QGroupBox, QWidget, QSlider, QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QSizePolicy, QStackedWidget, QSpacerItem
)
from bluepy import btle
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.patches as patches
import time
import datetime
import mariadb

from workout_log import NewWindow, calculateBPM, update_workout_data, calculate_speed_statistics

#Declaration variables globables
TROUBLESHOOTING = 0
THRESHOLD = 1200    #Variable THRESHOLD, pour determiner sensibilité des capteurs FSR
sample_rate = 30    #sample of steps per X seconds
freq = 60 / sample_rate    #to get in BPM, X * (60/freq)

## Necessaire pour la connection au serveur mariadb
# Connect to MariaDB Platform
try:
    conn = mariadb.connect(
        user="webuser",
        password="password",
        host="127.0.0.1",
        port=3306,
        database="pfedb"
    )
except mariadb.Error as e:
    print(f"Error connecting to MariaDB Platform: {e}")
    sys.exit(1)

# Get Cursor
cur = conn.cursor()


#"""
class SensorData:
    def __init__(self, timestamp=None, anp35=None, anp39=None, anp37=None, anp36=None, anp34=None, anp38=None):
        self.timestamp = timestamp
        self.anp35 = anp35
        self.anp39 = anp39
        self.anp37 = anp37
        self.anp36 = anp36
        self.anp34 = anp34
        self.anp38 = anp38

    def update(self, timestamp, sensor, value):
        self.timestamp = timestamp  # Update timestamp with each message
        if sensor == "AnP35":
            self.anp35 = value
        elif sensor == "AnP39":
            self.anp39 = value
        elif sensor == "AnP37":
            self.anp37 = value
        elif sensor == "AnP36":
            self.anp36 = value
        elif sensor == "AnP34":
            self.anp34 = value
        elif sensor == "AnP38":
            self.anp38 = value

    def is_complete(self):
        return all(sensor is not None for sensor in [self.anp35, self.anp39, self.anp37, self.anp36, self.anp34, self.anp38])

# Class for foot graph
class MatplotlibCanvas(FigureCanvas):
    def __init__(self):
        self.figure = Figure()
        super().__init__(self.figure)
        self.ax = self.figure.add_subplot(111)
        self.create_plot()

    def create_plot(self):
        # Initial plot setup
        self.ax.clear()
        outer_width = 20
        outer_height = 10

        # Outer rectangle
        outer_rectangle = patches.Rectangle((0, 0), outer_width, outer_height, linewidth=2, edgecolor='black', facecolor='white')
        self.ax.add_patch(outer_rectangle)

        self.ax.set_aspect('equal')
        self.ax.set_xlim(-1, outer_width + 1)
        self.ax.set_ylim(-1, outer_height + 1)
        self.ax.axis('off')

    def update_plot(self, sensor_data):
        # Clear previous rectangles
        self.ax.clear()
        self.create_plot()

        # Extract sensor values
        anp_values = {
            "anp35": sensor_data.anp35,
            "anp34": sensor_data.anp34,
            "anp39": sensor_data.anp39,
            "anp38": sensor_data.anp38,
            "anp37": sensor_data.anp37,
            "anp36": sensor_data.anp36
        }

        # Determine active/inactive states
        pied = [1 if value and value > THRESHOLD else 0 for value in anp_values.values()]

        # Add rectangles dynamically based on sensor data
        def add_rectangle(init_x, init_y, width, height, color):
            rectangle = patches.Rectangle((init_x, init_y), width, height, facecolor=color)
            self.ax.add_patch(rectangle)

        def create_6_rectangles(init_x, init_y, values):
            init_heights = [
                init_y,
                init_y + 1.5 / 2,
                init_y + 1.5 / 2 + 1.5,
                init_y + 1.5 / 2 + 2 * 1.5,
                init_y + 1.5 / 2 + 3 * 1.5,
                init_y + 1.5 / 2 + 4 * 1.5,
            ]
            color = 'g' if sum(values) > 3 else 'r'
            for i, value in enumerate(values):
                if value == 1:
                    height = 1.5 / 2 if i in [0, 5] else 1.5
                    add_rectangle(init_x, init_heights[i], 3, height, color)

        # Update the foot visualization
        create_6_rectangles(3, 1.5, pied)
        create_6_rectangles(14.5, 1.5, pied)

        # Refresh the canvas
        self.draw()
        
class WorkerSignals(QObject):
    signalMsg = pyqtSignal(str)
    signalRes = pyqtSignal(str)
    signalConnecting = pyqtSignal(bool)
    signalConnected = pyqtSignal(bool)
    signalDataParsed = pyqtSignal(SensorData)

class MyDelegate(btle.DefaultDelegate):
    def __init__(self, sgn, sensor_data):
        btle.DefaultDelegate.__init__(self)
        self.sgn = sgn
        self.sensor_data = sensor_data

    def handleNotification(self, cHandle, data):
        try:
            dataDecoded = data.decode()
            self.sgn.signalRes.emit(dataDecoded)
            print("Data: ", dataDecoded)

            # Parse the data values
            match = re.search(r'(\d+:\d+\.\d+),AnP(\d+):(\d+)', dataDecoded)
            if match:
                timestamp = match.group(1)
                sensor = f"AnP{match.group(2)}"
                value = int(match.group(3))

                self.sensor_data.update(timestamp, sensor, value)

                # Emit the sensor data only if all fields are populated
                if self.sensor_data.is_complete():
                    self.sgn.signalDataParsed.emit(self.sensor_data)
                    # Reset the sensor data after emitting so it can be re-populated with new values
                    self.sensor_data = SensorData()

        except UnicodeError:
            print("UnicodeError: ", data)

class WorkerBLE(QRunnable):
    def __init__(self):
        super().__init__()
        self.signals = WorkerSignals()
        self.rqsToSend = False
        self.bytestosend = b''
        self.sensor_data = SensorData()  # Maintain the sensor data state
        self._is_running = True  # Add a state attribute to control the loop
        self.max_retries = 5  # Maximum number of retries for connection
        self.retry_delay = 5  # Delay between retries (in seconds)

    def stop(self):
        self._is_running = False  # Method to stop the worker

    @pyqtSlot()
    def run(self):
        self.signals.signalMsg.emit("WorkerBLE start")

        retry_count = 0

        while self._is_running:
            try:
                # Attempt to connect to the Bluetooth device
                self.signals.signalConnecting.emit(True)
                p = btle.Peripheral("08:F9:E0:20:3E:0A")
                self.signals.signalConnected.emit(True)
                p.setDelegate(MyDelegate(self.signals, self.sensor_data))
                self.signals.signalConnecting.emit(False)

                svc = p.getServiceByUUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
                self.ch_Tx = svc.getCharacteristics("6E400002-B5A3-F393-E0A9-E50E24DCCA9E")[0]
                ch_Rx = svc.getCharacteristics("6E400003-B5A3-F393-E0A9-E50E24DCCA9E")[0]

                setup_data = b"\x01\x00"
                p.writeCharacteristic(ch_Rx.valHandle + 1, setup_data)

                retry_count = 0  # Reset retry count on successful connection

                # BLE loop --------
                while self._is_running:
                    p.waitForNotifications(1.0)

                    if self.rqsToSend:
                        self.rqsToSend = False
                        try:
                            self.ch_Tx.write(self.bytestosend, True)
                        except btle.BTLEException:
                            print("btle.BTLEException")
            except btle.BTLEException as e:
                self.signals.signalConnected.emit(False)
                self.signals.signalConnecting.emit(False)
                print(f"Failed to connect: {e}")
                time.sleep(self.retry_delay)
                retry_count += 1

                if retry_count >= self.max_retries:
                    print("Max retries reached, stopping worker...")
                    self.stop()

        self.signals.signalMsg.emit("WorkerBLE end")

    def toSendBLE(self, tosend):
        self.bytestosend = bytes(tosend, 'utf-8')
        self.rqsToSend = True
        
#"""    
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # Create QStackedWidget that contain the pages
        self.stackedWidget = QStackedWidget()
        self.setCentralWidget(self.stackedWidget)

        # Create pages
        self.menuPageWidget = QWidget()
        self.settingsPageWidget1 = QWidget()
        self.settingsPageWidget2 = QWidget()
        self.workoutPageWidget = QWidget()
        self.feedbackPageWidget = QWidget()

        ##########################################################################################################
        #                                       Menu page layout                                                 #
        ##########################################################################################################
        menuPageLayout = QVBoxLayout()

        # Add a title to the menu page
        menuPageTitle = QLabel("Menu")
        menuPageTitle.setAlignment(Qt.AlignCenter)
        menuPageTitle.setStyleSheet("font-size: 15px;")
        menuPageTitle.setFixedHeight(20)

        # Add button to the workout page
        workoutPageButton = QPushButton("Start a workout")
        workoutPageButton.clicked.connect(lambda: self.stackedWidget.setCurrentWidget(self.settingsPageWidget1))
        
        # Add button to open a new page (for workout log)
        self.buttonNewPage = QPushButton("Workout history")
        self.buttonNewPage.clicked.connect(self.openNewPage)

        # Add button to settings page
        settingsPageButton = QPushButton("Calibration")
        settingsPageButton.clicked.connect(lambda: self.stackedWidget.setCurrentWidget(self.settingsPageWidget2))
        
        # Add a button to close the app
        self.closeButton = QPushButton("Close App")
        self.closeButton.clicked.connect(self.closeApp)

        # Add Reset Button at the top of the screen
        self.buttonResetApp = QPushButton("Reset App")
        self.buttonResetApp.pressed.connect(self.resetApp)

        # Add Start BLE Button
        self.buttonStartBLE = QPushButton("Start BLE")
        self.buttonStartBLE.pressed.connect(self.startBLE)

        # Connecting text label setup
        self.connectingLabel = QLabel("Trying to connect to Bluetooth...", self)
        self.connectingLabel.setAlignment(Qt.AlignCenter)
        self.connectingLabel.setVisible(False)

        # Add widget to the menu layout
        menuPageLayout.addWidget(menuPageTitle)
        # menuPageLayout.addWidget(workoutPageButton)
        buttonLayout = QHBoxLayout()            #le "start workout" et "workout history" seront a coté
        buttonLayout.addWidget(workoutPageButton)
        buttonLayout.addWidget(self.buttonNewPage)
        # Add the layout to the main layout
        menuPageLayout.addLayout(buttonLayout)
        menuPageLayout.addWidget(self.connectingLabel)
        menuPageLayout.addWidget(self.buttonStartBLE)
        menuPageLayout.addWidget(settingsPageButton)
        menuPageLayout.addWidget(self.buttonResetApp)
        menuPageLayout.addWidget(self.closeButton)
        
        # Horizontal layout pour 2 boutons: start workout + new page pour workout log


        self.menuPageWidget.setLayout(menuPageLayout)
        ##########################################################################################################



        ##########################################################################################################
        #                                       Settings page layout 1                                           #
        ##########################################################################################################
        settingsLayout1 = QVBoxLayout()

        # Add page title
        settingsPageTitle1 = QLabel("Settings")
        settingsPageTitle1.setAlignment(Qt.AlignCenter)
        settingsPageTitle1.setStyleSheet("font-size: 15px;")
        settingsPageTitle1.setFixedHeight(19)

        # Add button to the calibration page
        settingsPageButton2 = QPushButton("Next")
        settingsPageButton2.clicked.connect(lambda: self.stackedWidget.setCurrentWidget(self.settingsPageWidget2))
        
        # Add button to start the workout
        startWorkoutButton = QPushButton("Start")
        startWorkoutButton.clicked.connect(lambda: self.stackedWidget.setCurrentWidget(self.workoutPageWidget))
        startWorkoutButton.clicked.connect(self.startTimer)

        # Group Box for BPM Controls
        bpmGroupBox = QGroupBox("BPM Controls")

        self.bpmLabel = QLabel("BPM: 0")
        self.bpmSlider = QSlider(Qt.Horizontal)
        self.bpmSlider.setRange(0, 100)
        self.bpmSlider.setValue(0)

        self.lowerBoundLabel = QLabel("Lower limit: 0")
        self.upperBoundLabel = QLabel("Upper limit: 0")

        self.lowerBoundOffsetLabel = QLabel("Lower limit offset: 0")
        self.lowerBoundOffsetSlider = QSlider(Qt.Horizontal)
        self.lowerBoundOffsetSlider.setRange(0, 20)
        self.lowerBoundOffsetSlider.setValue(0)

        self.upperBoundOffsetLabel = QLabel("Upper limit offset: 0")
        self.upperBoundOffsetSlider = QSlider(Qt.Horizontal)
        self.upperBoundOffsetSlider.setRange(0, 20)
        self.upperBoundOffsetSlider.setValue(0)

        self.offBeatStepsLabel = QLabel("Number of off beat steps allowed: 0")
        self.offBeatStepsSlider = QSlider(Qt.Horizontal)
        self.offBeatStepsSlider.setRange(0, 50)
        self.offBeatStepsSlider.setValue(0)

        self.tapButton = QPushButton("Tap")
        self.tapButton.pressed.connect(self.tapBPM)

        self.bpmSlider.valueChanged.connect(self.updateBPM)
        self.lowerBoundOffsetSlider.valueChanged.connect(self.updateLBO)
        self.upperBoundOffsetSlider.valueChanged.connect(self.updateUBO)
        self.offBeatStepsSlider.valueChanged.connect(self.updateOffBeatSteps)

        bpmLayout = QVBoxLayout()

        bpmDisplayLayout = QHBoxLayout()
        bpmDisplayLayout.addWidget(self.lowerBoundLabel)
        bpmDisplayLayout.addWidget(self.bpmLabel)
        bpmDisplayLayout.addWidget(self.upperBoundLabel)

        bpmControlsLayout = QHBoxLayout()
        bpmControlsLayout.addWidget(self.tapButton)
        bpmControlsLayout.addWidget(self.bpmSlider)

        lowerBoundOffsetLayout = QHBoxLayout()
        lowerBoundOffsetLayout.addWidget(self.lowerBoundOffsetLabel)
        lowerBoundOffsetLayout.addWidget(self.lowerBoundOffsetSlider)

        upperBoundOffsetLayout = QHBoxLayout()
        upperBoundOffsetLayout.addWidget(self.upperBoundOffsetLabel)
        upperBoundOffsetLayout.addWidget(self.upperBoundOffsetSlider)

        OffbeatStepsLayout = QHBoxLayout()
        OffbeatStepsLayout.addWidget(self.offBeatStepsLabel)
        OffbeatStepsLayout.addWidget(self.offBeatStepsSlider)

        bpmLayout.addLayout(bpmDisplayLayout)
        bpmLayout.addLayout(bpmControlsLayout)
        bpmLayout.addLayout(lowerBoundOffsetLayout)
        bpmLayout.addLayout(upperBoundOffsetLayout)
        bpmLayout.addLayout(OffbeatStepsLayout)
        bpmGroupBox.setLayout(bpmLayout)

        # Add button to the menu page
        menuPageButton = QPushButton("Back")
        menuPageButton.clicked.connect(lambda: self.stackedWidget.setCurrentWidget(self.menuPageWidget))
        
        # Group box for timer control
        timerControlGroupBox = QGroupBox("Timer Controls")

        self.timerControlLabel = QLabel("120 s", self)
       
        self.timer = QTimer(self)
        self.timerDuration = 120

        self.timerSlider = QSlider(Qt.Horizontal)
        self.timerSlider.setRange(0, 600)
        self.timerSlider.setSingleStep(10)
        self.timerSlider.setValue(120)
        self.timerSlider.valueChanged.connect(self.updateControlTimer)
        
        timerControlLayout = QVBoxLayout()
        timerControlLayout.addWidget(self.timerControlLabel)
        timerControlLayout.addWidget(self.timerSlider)
        timerControlGroupBox.setLayout(timerControlLayout)

        # Adding widgets to the first settings layout
        settingsLayout1.addWidget(settingsPageTitle1)
        settingsLayout1.addWidget(startWorkoutButton)
        settingsLayout1.addWidget(timerControlGroupBox)
        settingsLayout1.addWidget(bpmGroupBox)
        settingsLayout1.addWidget(menuPageButton)

        self.settingsPageWidget1.setLayout(settingsLayout1)
        ##########################################################################################################

        ##########################################################################################################
        #                                       Settings page layout 2                                           #
        ##########################################################################################################
        settingsLayout2 = QVBoxLayout()

        # Add page title
        settingsPageTitle2 = QLabel("Calibration")
        settingsPageTitle2.setAlignment(Qt.AlignCenter)
        settingsPageTitle2.setStyleSheet("font-size: 15px;")
        settingsPageTitle2.setFixedHeight(15)

        # Add button to menu page
        settingsPageButton1 = QPushButton("Back")
        settingsPageButton1.clicked.connect(lambda: self.stackedWidget.setCurrentWidget(self.menuPageWidget))

        # Group Box for Battery Percentage Display
        batteryGroupBox = QGroupBox("Battery")
        batteryGroupBox.setMaximumHeight(50)
        self.batteryLabel = QLabel("Battery: N/A")
        batteryLayout = QVBoxLayout()
        batteryLayout.addWidget(self.batteryLabel)
        batteryGroupBox.setLayout(batteryLayout)

        # Group Box for Weight Display
        weightGroupBox = QGroupBox("Weight")
        self.weightLabel = QLabel("Weight: N/A")
        weightLayout = QVBoxLayout()
        weightLayout.addWidget(self.weightLabel)
        weightGroupBox.setLayout(weightLayout)

        # Group Box for Tare Controls
        tareGroupBox = QGroupBox("Tare")
        tareLayout = QVBoxLayout()

        buttonTare = QPushButton("Tare")
        buttonTare.pressed.connect(self.sendTare)

        tareLayout.addWidget(buttonTare)
        tareGroupBox.setLayout(tareLayout)

        # Group Box for Calibrate FSR
        fsrGroupBox = QGroupBox("Calibrate FSR")

        self.fsrSlider = QSlider(Qt.Horizontal)
        self.fsrSlider.setRange(0, 4095)
        self.fsrSlider.setValue(0)
        self.fsrSlider.valueChanged.connect(self.updateFSR)

        self.fsrLabel = QLabel("FSR Value: 0")

        fsrLayout = QVBoxLayout()
        fsrLayout.addWidget(self.fsrSlider)
        fsrLayout.addWidget(self.fsrLabel)
        fsrGroupBox.setLayout(fsrLayout)

        # Group Box for Calibrate Controls
        calGroupBox = QGroupBox("Calibrate Load Cells")
        calLayout = QVBoxLayout()

        sliderLayout = QHBoxLayout()
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 300)
        self.slider.setTickInterval(10)
        self.slider.setTickPosition(QSlider.TicksBelow)
        self.slider.setValue(0)
        self.sliderLabel = QLabel("Value: 0")

        self.slider.valueChanged.connect(self.updateSliderLabel)

        self.unitToggle = QComboBox()
        self.unitToggle.addItems(["kg", "lbs"])

        sliderLayout.addWidget(self.slider)
        sliderLayout.addWidget(self.sliderLabel)
        sliderLayout.addWidget(self.unitToggle)

        buttonCalibrateBLE = QPushButton("Calibrate")
        buttonCalibrateBLE.pressed.connect(self.sendCalibrateBLE)

        calLayout.addLayout(sliderLayout)
        calLayout.addWidget(buttonCalibrateBLE)
        calGroupBox.setLayout(calLayout)

        # Adding widgets to the second settings layout
        settingsLayout2.addWidget(settingsPageTitle2)
        settingsLayout2.addWidget(batteryGroupBox)
        settingsLayout2.addWidget(weightGroupBox)
        settingsLayout2.addWidget(tareGroupBox)
        settingsLayout2.addWidget(calGroupBox)
        settingsLayout2.addWidget(fsrGroupBox)
        settingsLayout2.addWidget(settingsPageButton1)

        self.settingsPageWidget2.setLayout(settingsLayout2)
        ##########################################################################################################

        ##########################################################################################################
        #                                       Workout page layout                                              #
        ##########################################################################################################
        workoutPageLayout = QVBoxLayout()

        # Add page title
        workoutPageTitle = QLabel("Workout")
        workoutPageTitle.setAlignment(Qt.AlignCenter)
        workoutPageTitle.setStyleSheet("font-size: 15px;")
        workoutPageTitle.setFixedHeight(15)

        # Add timer
        timerGroupBox = QGroupBox("Timer")
        self.timer.timeout.connect(self.updateTimer)
        self.timeRemaining = self.timerDuration

        self.timerLabel = QLabel(f"timer: {self.timeRemaining} s")

        timerLayout = QVBoxLayout()
        timerLayout.addWidget(self.timerLabel)
        timerGroupBox.setLayout(timerLayout)

        # New Group Box for Cadence Controls
        cadenceGroupBox = QGroupBox("Cadence")
        #cadenceGroupBox.setStyleSheet("QGroupBox {background-color: #1abf08;}")

        self.cadenceLabel = QLabel("Cadence: 0 BPM")

        self.cadenceFeedbackLabel = QLabel("On pace")
        self.cadenceFeedbackLabel.setAlignment(Qt.AlignCenter)
        self.cadenceFeedbackLabel.setStyleSheet("QLabel {background-color: #1abf08;}")

        self.onPaceCountLabel = QLabel("On pace count: 0")
        self.fasterCountLabel = QLabel("Faster count: 0")
        self.slowerCountLabel = QLabel("Slower count: 0")

        self.consecutiveOnPaceCountLabel = QLabel("Consecutive on pace count: 0")
        self.consecutiveFasterCountLabel = QLabel("Consecutive faster count: 0")
        self.consecutiveSlowerCountLabel = QLabel("Consecutive slower count: 0")

        consecutiveCountLayout = QHBoxLayout()
        consecutiveCountLayout.addWidget(self.consecutiveSlowerCountLabel)
        consecutiveCountLayout.addWidget(self.consecutiveOnPaceCountLabel)
        consecutiveCountLayout.addWidget(self.consecutiveFasterCountLabel)

        cadenceLayout = QVBoxLayout()
        cadenceDisplayLayout = QHBoxLayout()
        cadenceDisplayLayout.addWidget(self.cadenceLabel)
        cadenceDisplayLayout.addWidget(self.slowerCountLabel)
        cadenceDisplayLayout.addWidget(self.onPaceCountLabel)
        cadenceDisplayLayout.addWidget(self.fasterCountLabel)
        cadenceLayout.addLayout(cadenceDisplayLayout)
        cadenceLayout.addLayout(consecutiveCountLayout)
        cadenceLayout.addWidget(self.cadenceFeedbackLabel)
        cadenceGroupBox.setLayout(cadenceLayout)
        
        #Pour avoir valeurs capteurs analog + graph a coté
        sideBySideLayout = QHBoxLayout()
        
        # Group Box for Analog Values Table
        analogGroupBox = QGroupBox("Analog Values")
        analogLayout = QVBoxLayout()
        self.timestampLabel = QLabel("Timestamp: N/A")
        self.analogTable = QTableWidget(6, 1)  # 6 rows, 1 column
        # Remove header labels
        self.analogTable.horizontalHeader().setVisible(False)
        self.analogTable.verticalHeader().setVisible(False)
        self.analogTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.analogTable.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
#        self.analogTable.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        analogLayout.addWidget(self.timestampLabel)
        analogLayout.addWidget(self.analogTable)
        analogGroupBox.setLayout(analogLayout)

        # Add the Analog Group Box to the layout
        sideBySideLayout.addWidget(analogGroupBox)
        
        # Group Box for Foot Plot
        plotGroupBox = QGroupBox("Foot Visualization")
        plotLayout = QHBoxLayout()  #Horizontal layout pour avoir BPM a coté
        self.footPlot = MatplotlibCanvas()
        
        # Set a minimum size for the canvas
        self.footPlot.setMinimumSize(200, 250)
        plotLayout.addWidget(self.footPlot)
        plotGroupBox.setLayout(plotLayout)
        
        # Add the Foot Plot Group Box to the layout
        sideBySideLayout.addWidget(plotGroupBox)
        
        # Add button to the menu page
        menuPageButton_2 = QPushButton("End workout")
        menuPageButton_2.clicked.connect(lambda: self.stackedWidget.setCurrentWidget(self.feedbackPageWidget))
        menuPageButton_2.clicked.connect(self.stopTimer)
        menuPageButton_2.clicked.connect(self.endWorkout)

        # Add widgets to layout
        workoutPageLayout.addWidget(workoutPageTitle)
        workoutPageLayout.addWidget(timerGroupBox)
        workoutPageLayout.addWidget(cadenceGroupBox)
      #  workoutPageLayout.addWidget(analogGroupBox)
      #  workoutPageLayout.addWidget(analogGroupBox)
        if TROUBLESHOOTING == 1:
            workoutPageLayout.addLayout(sideBySideLayout)
        else:
            workoutPageLayout.addWidget(plotGroupBox)
        workoutPageLayout.addWidget(menuPageButton_2)

        self.workoutPageWidget.setLayout(workoutPageLayout)
        ##########################################################################################################

        ##########################################################################################################
        #                                     Feedback page layout                                               #
        ##########################################################################################################
        feedbackPageLayout = QVBoxLayout()

        # Add page title
        feedbackPageTitle = QLabel("Feedback")
        feedbackPageTitle.setAlignment(Qt.AlignCenter)
        feedbackPageTitle.setStyleSheet("font-size: 15px;")
        feedbackPageTitle.setFixedHeight(15)

        # Add button to menu page
        feedback_to_MenuPageButton = QPushButton("Menu")
        feedback_to_MenuPageButton.clicked.connect(lambda: self.stackedWidget.setCurrentWidget(self.menuPageWidget))

        # Add a steps feedback group
        stepsFeedbackGroupBox = QGroupBox("Steps feedback")

        self.onPaceCountLabel_2 = QLabel("You took 0 steps on pace")
        self.fasterCountLabel_2 = QLabel("You took 0 steps too slow")
        self.slowerCountLabel_2 = QLabel("You took 0 steps too fast")

        stepsFeedbackLayout = QVBoxLayout()
        stepsFeedbackLayout.addWidget(self.fasterCountLabel_2)
        stepsFeedbackLayout.addWidget(self.onPaceCountLabel_2)
        stepsFeedbackLayout.addWidget(self.slowerCountLabel_2)
        stepsFeedbackGroupBox.setLayout(stepsFeedbackLayout)
        

        # Add widgets to layout
        feedbackPageLayout.addWidget(feedbackPageTitle)
        feedbackPageLayout.addWidget(stepsFeedbackGroupBox)
        feedbackPageLayout.addWidget(feedback_to_MenuPageButton)

        self.feedbackPageWidget.setLayout(feedbackPageLayout)
        ##########################################################################################################

        # Add widget to the stacked widget
        self.stackedWidget.addWidget(self.menuPageWidget)
        self.stackedWidget.addWidget(self.settingsPageWidget1)
        self.stackedWidget.addWidget(self.settingsPageWidget2)
        self.stackedWidget.addWidget(self.workoutPageWidget)
        self.stackedWidget.addWidget(self.feedbackPageWidget)

        # Show menu page by default
        self.stackedWidget.setCurrentWidget(self.menuPageWidget)

        self.threadpool = QThreadPool()
        print("Multithreading with Maximum %d threads" % self.threadpool.maxThreadCount())

        self.tap_times = []
        self.fsr_value = 0

        # Dictionary to keep track of the last exceed timestamps for each sensor
        self.sensor_exceed_timestamps = { "AnP35": [], "AnP39": [], "AnP37": [], "AnP36": [], "AnP34": [], "AnP38": [] }
        self.sensor_last_values = { "AnP35": 0, "AnP39": 0, "AnP37": 0, "AnP36": 0, "AnP34": 0, "AnP38": 0 }

        # Worker instance tracking
        self.workerBLE = None
        self.current_bpm = 0
        self.current_cadence = 0
        self.current_lbo = 0
        self.current_ubo = 0
        self.lower_bound = 0
        self.upper_bound = 0
        self.onPace_count = 0
        self.faster_count = 0
        self.slower_count = 0
        self.consecutiveFaster_count = 0
        self.consecutiveSlower_count = 0
        self.consecutiveOnPace_count = 0
        self.consecutiveSloweOrFaster_count = 0
        self.consecutiveOffBeatCount_allowed = 0
        #Last minute test
        self.calculated_speeds = []
        self.average_speed = 0
        self.max_speed = 0
        self.start_time =  0
        
    def resetCounters(self):
        self.onPace_count = 0
        self.faster_count = 0
        self.slower_count = 0
        self.consecutiveOnPace_count = 0
        self.consecutiveFaster_count = 0
        self.consecutiveSlower_count = 0
        self.consecutiveSloweOrFaster_count = 0
        self.onPaceCountLabel.setText(f"On pace count: {self.onPace_count}")
        self.slowerCountLabel.setText(f"Slower count: {self.slower_count}")
        self.fasterCountLabel.setText(f"Faster count: {self.faster_count}")
        self.consecutiveOnPaceCountLabel.setText(f"Consecutive on pace count: {self.consecutiveOnPace_count}")
        self.consecutiveSlowerCountLabel.setText(f"Consecutive slower count: {self.consecutiveSlower_count}")
        self.consecutiveFasterCountLabel.setText(f"Consecutive faster count: {self.consecutiveFaster_count}")
        #Last minute test
        self.calculated_speeds = []

    def updateCounters(self, sensor_key):
        now = datetime.datetime.now()
        #create a list of the last timestamps for each sensor
        timestamps = [
        self.sensor_exceed_timestamps[f"AnP3{i}"][-1]
        for i in range(4, 10)
        if f"AnP3{i}" != sensor_key and self.sensor_exceed_timestamps[f"AnP3{i}"]]
        # if all timestamps element happened at least 0.3 seconds ago
        if all(i + datetime.timedelta(milliseconds=300) < now for i in timestamps):
            self.consecutiveOnPaceCountLabel.setText(f"Consecutive on pace count: {self.consecutiveOnPace_count}")
            self.consecutiveSlowerCountLabel.setText(f"Consecutive slower count: {self.consecutiveSlower_count}")
            self.consecutiveFasterCountLabel.setText(f"Consecutive faster count: {self.consecutiveFaster_count}")
            #Last minute
            if not self.calculated_speeds:  # Checks if the list is empty
                self.start_time = now  # Get the current time in seconds
            if self.calculated_speeds is None:
                self.calculated_speeds = []
            
            self.calculated_speeds.append(self.current_cadence)
            
            if self.lower_bound <= self.current_cadence <= self.upper_bound:
                    self.consecutiveFaster_count = 0
                    self.consecutiveOnPace_count += 1
                    self.consecutiveSlower_count = 0
                    self.consecutiveSloweOrFaster_count = 0
                    self.onPace_count += 1
                    self.onPaceCountLabel.setText(f"On pace count: {self.onPace_count}")
                    self.cadenceFeedbackLabel.setText(f"On pace")
                    self.cadenceFeedbackLabel.setStyleSheet("QLabel {background-color: #1abf08;}")
            else:
                if self.current_cadence < self.current_bpm:
                    self.consecutiveFaster_count += 1
                    self.consecutiveOnPace_count = 0
                    self.consecutiveSlower_count = 0
                    self.consecutiveSloweOrFaster_count += 1
                    self.faster_count += 1
                    self.fasterCountLabel.setText(f"Faster count: {self.faster_count}")
                    self.cadenceFeedbackLabel.setText(f"Faster")
                    self.cadenceFeedbackLabel.setStyleSheet("QLabel {background-color: #d0d615;}")
                elif self.current_cadence > self.current_bpm:
                    self.consecutiveFaster_count = 0
                    self.consecutiveOnPace_count = 0
                    self.consecutiveSlower_count += 1
                    self.consecutiveSloweOrFaster_count += 1
                    self.slower_count += 1
                    self.slowerCountLabel.setText(f"Slower count: {self.slower_count}")
                    self.cadenceFeedbackLabel.setText(f"Slower")
                    self.cadenceFeedbackLabel.setStyleSheet("QLabel {background-color: #d0d615;}")
        if self.consecutiveSloweOrFaster_count == self.consecutiveOffBeatCount_allowed and self.consecutiveOffBeatCount_allowed:
            self.endWorkout()
                    

    def updateSliderLabel(self, value):
        self.sliderLabel.setText(f"Value: {value}")

    def updateOffBeatSteps(self, value):
        self.offBeatStepsLabel.setText(f"Number of off beat steps allowed: {value}")
        self.consecutiveOffBeatCount_allowed = value

    def updateBPM(self, value):
        self.bpmLabel.setText(f"BPM: {value}")
        self.current_bpm = value
        self.updateLB()
        self.updateUB()
        self.checkAndSendLightCommand()

    def updateLBO(self, value):
        self.lowerBoundOffsetLabel.setText(f"Lower limit offset: {value}")
        self.current_lbo = value
        self.updateLB()
        self.updateUB()
        self.checkAndSendLightCommand()

    def updateUBO(self, value):
        self.upperBoundOffsetLabel.setText(f"Upper limit offset: {value}")
        self.current_ubo = value
        self.updateLB()
        self.updateUB()
        self.checkAndSendLightCommand()

    def updateLB(self):
        if self.current_lbo > self.current_bpm:
            self.lower_bound = 0
        else:
            self.lower_bound = self.current_bpm - self.current_lbo
        self.lowerBoundLabel.setText(f"Lower limit: {self.lower_bound}")
        

    def updateUB(self):
        self.upper_bound = self.current_bpm + self.current_ubo
        self.upperBoundLabel.setText(f"Upper limit: {self.upper_bound}")

    def tapBPM(self):
        now = datetime.datetime.now()
        self.tap_times.append(now)

        # Keep only the last 5 tap times to calculate the BPM:
        self.tap_times = self.tap_times[-5:]

        if len(self.tap_times) >= 2:
            intervals = [(self.tap_times[i] - self.tap_times[i-1]).total_seconds() for i in range(1, len(self.tap_times))]
            avg_interval = sum(intervals) / len(intervals)
            bpm = int(60 / avg_interval)
            self.bpmSlider.setValue(bpm)
            self.updateBPM(bpm)
            
    # def tapBPM(self, sensor_data):
        # bpm = calculateBPM(sensor_data, conn, cur, sample_rate, freq, THRESHOLD)
        # self.bpmSlider.setValue(bpm)
        # self.updateBPM(bpm)

    def updateFSR(self, value):
        self.fsrLabel.setText(f"FSR Value: {value}")
        self.fsr_value = value
    
    #Fonction pour ouvrir page workout    
    def openNewPage(self):
        self.newWindow = NewWindow(cur, conn)  # Create an instance of the new page
        self.newWindow.show()         # Show the new page

    def startBLE(self):
        # Disable the button after it's clicked
        self.buttonStartBLE.setEnabled(False)
        
        # Stop any existing worker if running
        if self.workerBLE is not None:
            self.workerBLE.stop()
            self.threadpool.waitForDone()

        self.workerBLE = WorkerBLE()
        self.workerBLE.signals.signalMsg.connect(self.slotMsg)
        self.workerBLE.signals.signalRes.connect(self.slotRes)
        self.workerBLE.signals.signalConnecting.connect(self.setConnectingLabelVisible)
        self.workerBLE.signals.signalConnected.connect(self.updateBLEButton)
        self.workerBLE.signals.signalDataParsed.connect(self.updateAnalogValues)
        self.workerBLE.signals.signalDataParsed.connect(self.footPlot.update_plot)  #For foot graph
        #self.workerBLE.signals.signalDataParsed.connect(self.updateBPM2)  ###update and calculate BPM
        self.threadpool.start(self.workerBLE)

    def sendTare(self):
        tareCommand = "Tare"
        self.workerBLE.toSendBLE(tareCommand)

    def sendCalibrateBLE(self):
        calibrateCommand = "Calibrate"
        sliderValue = self.slider.value()
        unit = self.unitToggle.currentText()
        fullCommand = f"{calibrateCommand} {sliderValue} {unit}"
        self.workerBLE.toSendBLE(fullCommand)

    def sendLightCommand(self):
        lightCommand = "Light"
        self.workerBLE.toSendBLE(lightCommand)
        print("Light command sent")

    def checkAndSendLightCommand(self):
        if self.current_bpm > 0 and self.current_cadence > 0:
            if self.current_lbo > self.current_bpm:
                self.lower_bound = 0
            else:
                self.lower_bound = self.current_bpm - self.current_lbo
            self.upper_bound = self.current_bpm + self.current_ubo
            if self.lower_bound <= self.current_cadence <= self.upper_bound:
                self.sendLightCommand()
            else:
                if self.current_cadence < self.current_bpm:
                    self.workerBLE.toSendBLE("Faster")
                    print("Sent 'Faster' command")
                elif self.current_cadence > self.current_bpm:
                    self.workerBLE.toSendBLE("Slower")
                    print("Sent 'Slower' command")

    def updateStepsFeedbackLabel(self):
        self.slowerCountLabel_2.setText(f"You took {self.slower_count} steps too fast")
        self.onPaceCountLabel_2.setText(f"You took {self.onPace_count} steps on pace")
        self.fasterCountLabel_2.setText(f"You took {self.faster_count} steps too slow")

    def slotMsg(self, msg):
        print(msg)

    def slotRes(self, res):
        self.updateWeightDisplay(res)
        self.updateBatteryDisplay(res)

    def updateWeightDisplay(self, message):
        # Extract weight from the message
        match = re.search(r'W:(\d+)', message)
        if match:
            weight = match.group(1)
            unit = self.unitToggle.currentText()  # Get current unit from the combo box
            self.weightLabel.setText(f"Weight: {weight} {unit}")

    def updateBatteryDisplay(self, message):
        # Extract battery percentage from the message
        match = re.search(r'B:(\d+)', message)
        if match:
            battery = match.group(1)
            self.batteryLabel.setText(f"Battery: {battery}%")

    def updateAnalogValues(self, data):
        # Update the timestamp label
        self.timestampLabel.setText(f"Timestamp: {data.timestamp}")

        # Dictionary to map sensor indexes to their keys and table cell coordinates
        sensor_map = {0: ("AnP35", 0), 1: ("AnP34", 1), 2: ("AnP39", 2), 3: ("AnP38", 3), 4: ("AnP37", 4), 5: ("AnP36", 5)}

        # Loop over the sensor values and update the table
        for i, (sensor_key, row) in enumerate(sensor_map.values()):
            sensor_value = getattr(data, sensor_key.lower())
            item = QTableWidgetItem(f"{sensor_key}: {sensor_value}")

            # Check if the sensor value exceeds the fsr_value and if it transitioned from 0
            if sensor_value > self.fsr_value and self.sensor_last_values[sensor_key] == 0:
                item.setBackground(QBrush(QColor(0, 255, 0)))  # Set background to green
                self.registerExceed(sensor_key)
            elif sensor_value > self.fsr_value:
                # Check background color to ensure it stays green if the value still exceeds fsr_value
                current_color = QColor(item.background().color())
                if current_color != QColor(0, 255, 0):
                    item.setBackground(QBrush(QColor(0, 255, 0)))  # Maintain background green
            else:
                # Clear the background if the condition is not met anymore
                item.setBackground(QBrush(QColor(Qt.transparent)))

            self.analogTable.setItem(row, 0, item)
            self.sensor_last_values[sensor_key] = sensor_value

    def registerExceed(self, sensor_key):
        now = datetime.datetime.now()
        timestamps = self.sensor_exceed_timestamps[sensor_key]
        timestamps.append(now)

        # Keep only the last 5 timestamps to calculate the rhythm
        self.sensor_exceed_timestamps[sensor_key] = timestamps[-5:]

        if len(timestamps) >= 2:
            intervals = [(timestamps[i] - timestamps[i-1]).total_seconds() for i in range(1, len(timestamps))]
            avg_interval = sum(intervals) / len(intervals)
            bpm = int(60 / avg_interval)
            print(f"Rhythm for {sensor_key}: {bpm} BPM")
            # Update cadence label with the calculated BPM
            self.updateCadence(bpm)
            self.updateCounters(sensor_key)
            
    
     # def registerExceed(self, sensor_key, sensor_data):
         # bpm = calculateBPM(sensor_data, conn, cur, sample_rate, freq, THRESHOLD)
         # # Update cadence label with the calculated BPM
         # self.updateCadence(bpm)
         # self.updateCounters(sensor_key)
    

    def updateCadence(self, bpm):
        self.cadenceLabel.setText(f"Cadence: {bpm} BPM")
        self.current_cadence = bpm
        self.checkAndSendLightCommand()

    def setConnectingLabelVisible(self, isVisible):
        self.connectingLabel.setVisible(isVisible)

    def updateBLEButton(self, connected):
        if connected:
            self.buttonStartBLE.setText("BLE Connected")
            self.buttonStartBLE.setEnabled(False)
        else:
            self.buttonStartBLE.setText("Start BLE")
            self.buttonStartBLE.setEnabled(True)

            # Stop the current worker if there's a disconnection
            if self.workerBLE is not None:
                self.workerBLE.stop()
                self.threadpool.waitForDone()
                self.workerBLE = None  # Clean up the reference
                
    def updateControlTimer(self, value):
        self.timerDuration = value
        self.timerControlLabel.setText(f"{self.timerDuration} s")

    def startTimer(self):
        self.resetCounters()
        self.timeRemaining = self.timerDuration
        self.updateTimerLabel()
        self.timer.start(1000)

    def stopTimer(self):
        self.timer.stop()

    def updateTimer(self):
        if self.timeRemaining > 0:
            self.timeRemaining -= 1
            self.updateTimerLabel()
        else:
            self.endWorkout()
            

    def updateTimerLabel(self):
        #minutes, seconds = divmod(self.time_remaining, 60)
        self.timerLabel.setText(f"timer: {self.timeRemaining} s")

    def endWorkout(self):
        self.stopTimer()
        self.updateStepsFeedbackLabel()
        self.stackedWidget.setCurrentWidget(self.feedbackPageWidget)
        
        #Last minute, a tester
        if len(self.calculated_speeds) > 0:
            average_speed = sum(self.calculated_speeds) / len(self.calculated_speeds)
            highest_speed = max(self.calculated_speeds)
        else:
            print("No speed data available to calculate statistics.")
            average_speed = highest_speed = None
        
        workout_end_time = datetime.datetime.now()
    
        if self.start_time!= workout_end_time and average_speed != None and average_speed != 0:
            try:
                cur.execute("INSERT INTO TrainingSessions (Name, TimeStarted, TimeEnded, AverageSpeed, HighestSpeed) VALUES (%s, %s, %s, %s, %s)",
                            ("Default", self.start_time, workout_end_time, average_speed, highest_speed))
                conn.commit()
                print(f"Last Inserted ID: {cur.lastrowid}")
            except mariadb.Error as e:
                print(f"Error inserting into TrainingSessions: {e}")
        else:
            print("Table was not updated")

    def resetApp(self):
        # Method to reset the app
        print("Resetting the application...")
        QProcess.startDetached(sys.executable, sys.argv)  # Restart the app
        QApplication.exit()
        
    def closeApp(self):
        #Closing app. 
        print("Closing the application.")
        # Delete sensorEntries table, updating workout and then closing mariadb connection
        try:
            # Delete SensorEntries table
            cur.execute("DELETE FROM SensorEntries")
            cur.execute("TRUNCATE TABLE SensorEntries")
            
            # Commit the transaction
            conn.commit()
        except mariadb.Error as e:
            print(f"Error deleting or truncating SensorEntries: {e}")
            
        #update_workout_data(cur,conn)
        
        cur.close()
        conn.close()
        
        # Stop BLE worker if running
        if self.workerBLE is not None:
            self.workerBLE.stop()
            self.threadpool.waitForDone()  # Ensure the threadpool completes all tasks
        
        QApplication.exit(0)
        subprocess.call(['sh','kill_python.sh'])
        
        

app = QApplication(sys.argv)
window = MainWindow()
window.resize(1024, 600)
window.show()
#window.showFullScreen()
app.exec()
