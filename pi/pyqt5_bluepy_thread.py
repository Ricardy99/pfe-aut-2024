
import sys
import re
from PyQt5.QtCore import QObject, QRunnable, QThreadPool, Qt, pyqtSignal, pyqtSlot, QProcess, QTimer
from PyQt5.QtGui import QColor, QBrush
from PyQt5.QtWidgets import ( 
    QApplication, QLabel, QMainWindow, QPlainTextEdit, QPushButton, QVBoxLayout, QHBoxLayout, QGroupBox, QWidget, QSlider, QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QSizePolicy, QStackedWidget
)
#from bluepy import btle
import time
import datetime

"""
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
        
"""    
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

        ##########################################################################################################
        #                                       Menu page layout                                                 #
        ##########################################################################################################
        menuPageLayout = QVBoxLayout()

        # Add page title
        menuPageTitle = QLabel("Menu")
        menuPageTitle.setAlignment(Qt.AlignCenter)
        menuPageTitle.setStyleSheet("font-size: 15px;")
        menuPageTitle.setFixedHeight(15)


        # Add button to the workout page
        workoutPageButton = QPushButton("Start a workout")
        #workoutPageButton.setAlignment(Qt.AlignCenter)
        #workoutPageButton.setMinimumWidth(100)
        #workoutPageButton.setMaximumWidth(200)
        #workoutPageButton.setFixedWidth(150)
        #workoutPageButton.setStyleSheet("width: 50px;")
        workoutPageButton.clicked.connect(lambda: self.stackedWidget.setCurrentWidget(self.workoutPageWidget))

        # Add button to settings page
        settingsPageButton = QPushButton("Settings")
        settingsPageButton.clicked.connect(lambda: self.stackedWidget.setCurrentWidget(self.settingsPageWidget1))
        
        # Add a button to close the app
        closeButton = QPushButton("Close App")
        closeButton.clicked.connect(self.close)

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
        menuPageLayout.addWidget(workoutPageButton)
        menuPageLayout.addWidget(self.connectingLabel) # Add connecting text label to the layout
        menuPageLayout.addWidget(self.buttonStartBLE)
        menuPageLayout.addWidget(settingsPageButton)
        menuPageLayout.addWidget(self.buttonResetApp)  # Add Reset Button to the top
        menuPageLayout.addWidget(closeButton)

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

        # Add button to the menu page
        menuPageButton = QPushButton("Menu")
        menuPageButton.clicked.connect(lambda: self.stackedWidget.setCurrentWidget(self.menuPageWidget))
    
        settingsPageButton2 = QPushButton("Next")
        settingsPageButton2.clicked.connect(lambda: self.stackedWidget.setCurrentWidget(self.settingsPageWidget2))
        
        # Group Box for Battery Percentage Display
        batteryGroupBox = QGroupBox("Battery")
        self.batteryLabel = QLabel("Battery: N/A")
        batteryLayout = QVBoxLayout()
        batteryLayout.addWidget(self.batteryLabel)
        batteryGroupBox.setLayout(batteryLayout)

        # Group Box for BPM Controls
        bpmGroupBox = QGroupBox("BPM Controls")

        self.bpmLabel = QLabel("BPM: 0")
        self.bpmSlider = QSlider(Qt.Horizontal)
        self.bpmSlider.setRange(0, 100)
        self.bpmSlider.setValue(30)

        self.lowerBoundOffsetLabel = QLabel("Lower bound offset: 0")
        self.lowerBoundOffsetSlider = QSlider(Qt.Horizontal)
        self.lowerBoundOffsetSlider.setRange(0, 20)
        self.lowerBoundOffsetSlider.setValue(0)

        self.upperBoundOffsetLabel = QLabel("Upper bound offset: 0")
        self.upperBoundOffsetSlider = QSlider(Qt.Horizontal)
        self.upperBoundOffsetSlider.setRange(0, 20)
        self.upperBoundOffsetSlider.setValue(0)

        self.tapButton = QPushButton("Tap")
        self.tapButton.pressed.connect(self.tapBPM)

        self.bpmSlider.valueChanged.connect(self.updateBPM)
        self.lowerBoundOffsetSlider.valueChanged.connect(self.updateLBO)
        self.upperBoundOffsetSlider.valueChanged.connect(self.updateUBO)

        bpmLayout = QVBoxLayout()
        bpmLayout.addWidget(self.bpmLabel)

        bpmControlsLayout = QHBoxLayout()
        bpmControlsLayout.addWidget(self.tapButton)
        bpmControlsLayout.addWidget(self.bpmSlider)

        lowerBoundOffsetLayout = QHBoxLayout()
        lowerBoundOffsetLayout.addWidget(self.lowerBoundOffsetLabel)
        lowerBoundOffsetLayout.addWidget(self.lowerBoundOffsetSlider)

        upperBoundOffsetLayout = QHBoxLayout()
        upperBoundOffsetLayout.addWidget(self.upperBoundOffsetLabel)
        upperBoundOffsetLayout.addWidget(self.upperBoundOffsetSlider)

        bpmLayout.addLayout(bpmControlsLayout)
        bpmLayout.addLayout(lowerBoundOffsetLayout)
        bpmLayout.addLayout(upperBoundOffsetLayout)
        bpmGroupBox.setLayout(bpmLayout)

        # New Group Box for Cadence Controls
        cadenceGroupBox = QGroupBox("Cadence")

        self.cadenceLabel = QLabel("Cadence: 0 BPM")

        cadenceLayout = QVBoxLayout()
        cadenceLayout.addWidget(self.cadenceLabel)
        cadenceGroupBox.setLayout(cadenceLayout)

        

        """
        # Création du bouton de démarrage du minuteur
        self.start_button = QPushButton("Start Timer")  # Bouton pour démarrer le minuteur
        self.start_button.clicked.connect(self.start_timer)  # Connecte le clic du bouton à la fonction de démarrage du minuteur

        # Création du label pour afficher le décompte du minuteur
        #self.timer_label = QLabel("2:00", self)  # Affiche initialement "2:00" pour représenter 2 minutes
        
        # Configuration du minuteur
        self.timer = QTimer(self)  # Initialisation de l'objet QTimer
        self.timer.timeout.connect(self.update_timer)  # Connecte chaque expiration du minuteur à la fonction `update_timer`
        self.timer_duration = 120  # Durée totale du minuteur (120 secondes, soit 2 minutes)
        self.time_remaining = self.timer_duration  # Variable pour le temps restant
        """
        

        # Adding widgets to the first settings layout
        settingsLayout1.addWidget(settingsPageTitle1)
        settingsLayout1.addWidget(menuPageButton)
        settingsLayout1.addWidget(batteryGroupBox)      # Add the Battery group box
        settingsLayout1.addWidget(bpmGroupBox)          # Add the BPM Controls group box
        settingsLayout1.addWidget(cadenceGroupBox)      # Add the Cadence group box near BPM controls
        settingsLayout1.addWidget(settingsPageButton2)

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

        # Add button to first settings page
        settingsPageButton1 = QPushButton("Back")
        settingsPageButton1.clicked.connect(lambda: self.stackedWidget.setCurrentWidget(self.settingsPageWidget1))

        # Group Box for Weight Display
        weightGroupBox = QGroupBox("Weight")
        self.weightLabel = QLabel("Weight: N/A")
        weightLayout = QVBoxLayout()
        weightLayout.addWidget(self.weightLabel)
        weightGroupBox.setLayout(weightLayout)

        # Group Box for Analog Values Table
        analogGroupBox = QGroupBox("Analog Values")

        self.timestampLabel = QLabel("Timestamp: N/A")
        self.analogTable = QTableWidget(6, 1)  # 6 rows, 1 column
        # Remove header labels
        self.analogTable.horizontalHeader().setVisible(False)
        self.analogTable.verticalHeader().setVisible(False)
        self.analogTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.analogTable.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
#        self.analogTable.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        
        analogLayout = QVBoxLayout()
        analogLayout.addWidget(self.timestampLabel)
        analogLayout.addWidget(self.analogTable)
        analogGroupBox.setLayout(analogLayout)

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
        settingsLayout2.addWidget(weightGroupBox)       # Add the weight group box here
        settingsLayout2.addWidget(tareGroupBox)
        settingsLayout2.addWidget(calGroupBox)
        settingsLayout2.addWidget(fsrGroupBox)          # Add the Calibrate FSR group box
        settingsLayout2.addWidget(analogGroupBox)       # Add the analog values table group box
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

        # Add button to the menu page
        menuPageButton_2 = QPushButton("Menu")
        menuPageButton_2.clicked.connect(lambda: self.stackedWidget.setCurrentWidget(self.menuPageWidget))

        # Add button to start the workout
        startWorkoutButton = QPushButton("Start")

        # Add widgets to layout
        workoutPageLayout.addWidget(workoutPageTitle)
        workoutPageLayout.addWidget(startWorkoutButton)
        workoutPageLayout.addWidget(menuPageButton_2)

        self.workoutPageWidget.setLayout(workoutPageLayout)
        ##########################################################################################################


        # Add widget to the stacked widget
        self.stackedWidget.addWidget(self.menuPageWidget)
        self.stackedWidget.addWidget(self.settingsPageWidget1)
        self.stackedWidget.addWidget(self.settingsPageWidget2)
        self.stackedWidget.addWidget(self.workoutPageWidget)

        # Show menu page by default
        self.stackedWidget.setCurrentWidget(self.menuPageWidget)

        #self.showFullScreen()
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

    def updateSliderLabel(self, value):
        self.sliderLabel.setText(f"Value: {value}")

    def updateBPM(self, value):
        self.bpmLabel.setText(f"BPM: {value}")
        self.current_bpm = value
        self.checkAndSendLightCommand()

    def updateLBO(self, value):
        self.lowerBoundOffsetLabel.setText(f"Lower bound offset: {value}")
        self.current_lbo = value
        self.checkAndSendLightCommand()

    def updateUBO(self, value):
        self.upperBoundOffsetLabel.setText(f"Upper bound offset: {value}")
        self.current_ubo = value
        self.checkAndSendLightCommand()

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

    def updateFSR(self, value):
        self.fsrLabel.setText(f"FSR Value: {value}")
        self.fsr_value = value

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
                lower_bound = 0
            else:
                lower_bound = self.current_bpm - self.current_lbo   #0.9
            upper_bound = self.current_bpm + self.current_ubo   #1.1
            if lower_bound <= self.current_cadence <= upper_bound:
                self.sendLightCommand()
            else:
                if self.current_cadence > self.current_bpm:
                    self.workerBLE.toSendBLE("Faster")
                    print("Sent 'Faster' command")
                elif self.current_cadence < self.current_bpm:
                    self.workerBLE.toSendBLE("Slower")
                    print("Sent 'Slower' command")

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
                
    
    def start_timer(self):
        # Réinitialisation et démarrage du minuteur
        self.time_remaining = self.timer_duration  # Réinitialise le temps restant
        self.update_timer_label()  # Met à jour l'affichage du label de minuteur
        self.timer.start(1000)  # Démarre le minuteur avec un intervalle de 1 seconde

    def update_timer(self):
        # Diminue le temps restant et met à jour le label
        if self.time_remaining > 0:
            self.time_remaining -= 1  # Diminue le temps restant d'une seconde
            self.update_timer_label()  # Met à jour le label du minuteur avec le nouveau temps restant
        else:
            self.timer.stop()  # Arrête le minuteur lorsque le temps est écoulé
            self.timer_label.setText("Time's up!")  # Affiche "Time's up!" lorsque le temps est écoulé

    def update_timer_label(self):
        # Met à jour le label pour afficher le temps restant au format MM:SS
        minutes, seconds = divmod(self.time_remaining, 60)
        self.timer_label.setText(f"{minutes}:{seconds:02}")

    def resetApp(self):
        # Method to reset the app
        print("Resetting the application...")
        QProcess.startDetached(sys.executable, sys.argv)  # Restart the app
        QApplication.exit()
        
        

app = QApplication(sys.argv)
window = MainWindow()
window.resize(1024, 600)
window.show()
#window.showFullScreen()
app.exec()
