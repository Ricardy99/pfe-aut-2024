"""
Version 4. Objectifs:
 1. Utilisation de MariaDB (open-source dabatase) pour log les entrées 
 des sensors analog et calculer la cadence.
 2. Utiliser ces données pour obtenir les infos suivantes: date de la 
 seance, durée, vitesse moyenne, maximale et minimale.
 3. Afficher tout ça à l'écran.
 4. (optionnel) option pour effacer données?
 
 Issue 1: Probleme affichage du pourcentage de la batterie
 
 Update 6 dec: présentement la cadence est calculée mais non montrée sur l'application.
 J'aimerais le montrer proche du graph de pieds.
"""

import sys
import subprocess
import re
import random   #pour test values graph
from PyQt5.QtCore import QObject, QRunnable, QThreadPool, Qt, pyqtSignal, pyqtSlot, QProcess
from PyQt5.QtGui import QColor, QBrush
from PyQt5.QtWidgets import (
    QApplication, QLabel, QMainWindow, QPlainTextEdit, QPushButton, QVBoxLayout, QHBoxLayout, QGroupBox, QWidget, QSlider, QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QSizePolicy
)
from bluepy import btle
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.patches as patches
import time
import datetime
import mariadb

from workout_log import NewWindow, updateBPM, update_workout_data, calculate_speed_statistics

#Declaration des variables globales
THRESHOLD = 1200    #Variable THRESHOLD, pour determiner sensibilité des capteurs FSR
calculated_BPM = 0
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

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        mainLayout = QVBoxLayout()

        # Add Reset Button at the top of the screen
        self.buttonResetApp = QPushButton("Reset App")
        self.buttonResetApp.pressed.connect(self.resetApp)
        
        # Add Close Button at the top of the screen
        self.buttonCloseApp = QPushButton("Close App")
        self.buttonCloseApp.pressed.connect(self.CloseApp)

        # Add Start BLE Button
        self.buttonStartBLE = QPushButton("Start BLE")
        self.buttonStartBLE.pressed.connect(self.startBLE)
        
        # Add test button for manual sensor input
        self.buttonTestSensors = QPushButton("Set Test Sensor Values")
        self.buttonTestSensors.pressed.connect(self.setTestSensorValues)
        
        # Add button to open a new page
        self.buttonNewPage = QPushButton("NP(workout log)")
        self.buttonNewPage.pressed.connect(self.openNewPage)


        # Connecting text label setup
        self.connectingLabel = QLabel("Trying to connect to Bluetooth...", self)
        self.connectingLabel.setAlignment(Qt.AlignCenter)
        self.connectingLabel.setVisible(False)

        # Group Box for Battery Percentage Display
        batteryGroupBox = QGroupBox("Battery")
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

        # # # Group Box for Analog Values Table
        # # analogGroupBox = QGroupBox("Analog Values")

        # # self.timestampLabel = QLabel("Timestamp: N/A")
        # # self.analogTable = QTableWidget(6, 1)  # 6 rows, 1 column
        # # # Remove header labels
        # # self.analogTable.horizontalHeader().setVisible(False)
        # # self.analogTable.verticalHeader().setVisible(False)
        # # self.analogTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        # # self.analogTable.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
# # #        self.analogTable.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        # Group Box for Analog Values Table
        analogGroupBox = QGroupBox("Analog Values")

        self.timestampLabel = QLabel("Timestamp: N/A")
        self.analogTable = QTableWidget(6, 1)  # 6 rows, 1 column
        # Remove header labels
        self.analogTable.horizontalHeader().setVisible(False)
        self.analogTable.verticalHeader().setVisible(False)
        self.analogTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.analogTable.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)

        analogLayout = QVBoxLayout()
        analogLayout.addWidget(self.timestampLabel)
        analogLayout.addWidget(self.analogTable)
        analogGroupBox.setLayout(analogLayout)

        # Group Box for Foot Plot
        plotGroupBox = QGroupBox("Foot Visualization")
        plotLayout = QHBoxLayout()  #Horizontal layout pour avoir BPM a coté
        self.footPlot = MatplotlibCanvas()

        # Set a minimum size for the canvas
        self.footPlot.setMinimumSize(200, 100)
        
        # Add a label to display the number (e.g., Cadence or Speed)
#        self.plotNumberLabel = QLabel("BPM: 0")
        self.plotNumberLabel = QLabel(f"BPM: {calculated_BPM}")
        self.plotNumberLabel.setAlignment(Qt.AlignCenter)
        self.plotNumberLabel.setStyleSheet("font-size: 18px; font-weight: bold;")

        plotLayout.addWidget(self.footPlot, stretch=3)
        plotLayout.addWidget(self.plotNumberLabel, stretch=1)  # Less space for the number
        plotGroupBox.setLayout(plotLayout)

        # Combine both sections in a horizontal layout
        sideBySideLayout = QHBoxLayout()
        sideBySideLayout.addWidget(analogGroupBox)  # Add Analog Values Group Box
        sideBySideLayout.addWidget(plotGroupBox)    # Add Foot Visualization Group Box

        # Add the horizontal layout to the main layout
        mainLayout.addLayout(sideBySideLayout)
        
       

        
        # # analogLayout = QVBoxLayout()
        # # analogLayout.addWidget(self.timestampLabel)
        # # analogLayout.addWidget(self.analogTable)
        # # analogGroupBox.setLayout(analogLayout)
        
        # # # Add Group Box for Foot Plot
        # # plotGroupBox = QGroupBox("Foot Visualization")
        # # plotLayout = QVBoxLayout()
        # # self.footPlot = MatplotlibCanvas()
        
        # # # Set a minimum size for the canvas
        # # self.footPlot.setMinimumSize(200, 100)

        # # plotLayout.addWidget(self.footPlot)
        # # plotGroupBox.setLayout(plotLayout)
        
        # Optional, remove if problematic
        #plotGroupBox.setMinimumHeight(250)

        # Group Box for Tare Controls
        tareGroupBox = QGroupBox("Tare")
        tareLayout = QVBoxLayout()

        buttonTare = QPushButton("Tare")
        buttonTare.pressed.connect(self.sendTare)

        tareLayout.addWidget(buttonTare)
        tareGroupBox.setLayout(tareLayout)

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

        # Group Box for BPM Controls
        bpmGroupBox = QGroupBox("BPM Controls")

        self.bpmLabel = QLabel("BPM: 0")
        self.bpmSlider = QSlider(Qt.Horizontal)
        self.bpmSlider.setRange(0, 100)
        self.bpmSlider.setValue(30)

        self.tapButton = QPushButton("Tap")
        self.tapButton.pressed.connect(self.tapBPM)

        self.bpmSlider.valueChanged.connect(self.updateBPM)

        bpmLayout = QVBoxLayout()
        bpmLayout.addWidget(self.bpmLabel)

        bpmControlsLayout = QHBoxLayout()
        bpmControlsLayout.addWidget(self.tapButton)
        bpmControlsLayout.addWidget(self.bpmSlider)

        bpmLayout.addLayout(bpmControlsLayout)
        bpmGroupBox.setLayout(bpmLayout)

        # New Group Box for Cadence Controls
        cadenceGroupBox = QGroupBox("Cadence")

        self.cadenceLabel = QLabel("Cadence: 0 BPM")

        cadenceLayout = QVBoxLayout()
        cadenceLayout.addWidget(self.cadenceLabel)
        cadenceGroupBox.setLayout(cadenceLayout)

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

        # Adding widgets to the main layout
        # # mainLayout.addWidget(self.buttonResetApp)  # Add Reset Button to the top
        # # mainLayout.addWidget(self.buttonCloseApp)  # Add Close Button to the top
        buttonLayout = QHBoxLayout()            #Create horizontal layout, Reset will be next to Close button
        buttonLayout.addWidget(self.buttonResetApp)  # Add Reset Button first
        buttonLayout.addWidget(self.buttonCloseApp)  # Add Close Button
        mainLayout.addLayout(buttonLayout)  # Add the horizontal layout to the main layout

        
        mainLayout.addWidget(self.buttonStartBLE)
        
        
        
        
        # Horizontal layout pour 2 boutons: set sensor values + new page pour workout log
        buttonLayout = QHBoxLayout()
        buttonLayout.addWidget(self.buttonTestSensors)
        buttonLayout.addWidget(self.buttonNewPage)
        # Add the layout to the main layout
        mainLayout.addLayout(buttonLayout)

        
        mainLayout.addWidget(batteryGroupBox)      # Add the Battery group box
        mainLayout.addWidget(bpmGroupBox)          # Add the BPM Controls group box
        #mainLayout.addWidget(cadenceGroupBox)      # Add the Cadence group box near BPM controls
        #mainLayout.addWidget(self.connectingLabel) # Add connecting text label to the layout
        mainLayout.addWidget(weightGroupBox)       # Add the weight group box here
        # # mainLayout.addWidget(analogGroupBox)       # Add the analog values table group box
        # # mainLayout.addWidget(plotGroupBox)         # Foot Visualization
        # # mainLayout.addWidget(tareGroupBox)
        mainLayout.addWidget(calGroupBox)
        mainLayout.addWidget(fsrGroupBox)          # Add the Calibrate FSR group box
        

        widget = QWidget()
        widget.setLayout(mainLayout)

        self.setCentralWidget(widget)

        #self.showFullScreen()
        self.showNormal()
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
        
    def setTestSensorValues(self):
        # Create a SensorData object with test values
        test_data = SensorData(
            timestamp="00:00.000",
            anp35=random.randint(0, 3000),
            anp39=random.randint(0, 3000),
            anp37=random.randint(0, 3000),
            anp36=random.randint(0, 3000),
            anp34=random.randint(0, 3000),
            anp38=random.randint(0, 3000)
        )
        # Update the analog values table
        self.updateAnalogValues(test_data)
        # Update the plot with the test values
        self.footPlot.update_plot(test_data)
        
    def openNewPage(self):
        self.newWindow = NewWindow(cur, conn)  # Create an instance of the new page
        self.newWindow.show()         # Show the new page
    
    # 29 nov 2024
#    def setGraphValues(self, data):
#        self.footPlot.update_plot(data)

#must be a mistake cause why defined a second time? 29 nov 24
#   def updateAnalogValues(self, data):
#        # Update sensor values in the table
#        # Update the foot visualization dynamically
#        self.footPlot.update_plot(data)

    def updateSliderLabel(self, value):
        self.sliderLabel.setText(f"Value: {value}")


    def updateBPM(self, sensor_data):
        updateBPM(sensor_data, self.plotNumberLabel, conn, cur, sample_rate, freq, THRESHOLD)

       #Commented out because im moving it to another file
    # # #sensor_data was previously value, fonction team ete24
    # # def updateBPM(self, sensor_data):
        # # # Extract sensor values
        # # anp_values = {
            # # "anp35": sensor_data.anp35,
            # # "anp34": sensor_data.anp34,
            # # "anp39": sensor_data.anp39,
            # # "anp38": sensor_data.anp38,
            # # "anp37": sensor_data.anp37,
            # # "anp36": sensor_data.anp36
        # # }
        # # # Decomposer et mettre dans un format pour envoyer au database
        # # result = ",".join(str(value) for value in anp_values.values())
         
        # # valid_sensor_cnt = sum(1 for value in anp_values.values() if value > THRESHOLD)
                
        # # try:
            # # cur.execute("SELECT Valid FROM SensorEntries ORDER BY Timestamp DESC LIMIT 1")
            # # last_valid_variable = cur.fetchone()  # Fetch the most recent entry
            # # last_valid_variable = last_valid_variable[0] if last_valid_variable else 0  # Default to 0 if no entry
        # # except mariadb.Error as e:
            # # print(f"Error fetching last entry: {e}")
            # # last_valid_variable = None
            
        # # print("Last valid variable is", last_valid_variable)
        
        # # valid_entry = 0;
        
        # # # Ne comptabilisera pas si l'entree est très legere (a moins que la derniere ait ete 0)
        # # if valid_sensor_cnt > 0 and valid_sensor_cnt <= 3:  #si seulement 3 bandes ou moins sont activees, invalid
                # # valid_entry = 0
        # # elif valid_sensor_cnt > 3: #plus de la motie des capteurs, pour que l'utilisateur ne "triche" pas
                # # valid_entry = 1
        # # else:
                # # valid_entry = 2;    #for 0,0,0,0,0
                
        # # if valid_entry != 9 and last_valid_variable !=12:
            # # try:        #insert information in db
                # # cur.execute("INSERT INTO SensorEntries (Timestamp, SensorArray, Valid) VALUES (NOW(), %s, %s)", (result, valid_entry))
                   # # #cur.execute("INSERT INTO TrainingSessions (Name, TimeStarted, TimeEnded, HighestSpeed, LowestSpeed, AverageSpeed) VALUES (?, ?, ?, ?, ?, ?)",
                   # # #("Test_v4", time_started, time_ended, random.randint(50,57), random.randint(38,45), random.randint(45,50)))
                    
            # # except mariadb.Error as e: 
                    # # print(f"Error: {e}")

            # # conn.commit() 
            # # print(f"Last Inserted ID: {cur.lastrowid}")

        
        # # # Calculate cadence/speed
        # # try:
            # # # Fetch all Valid entries from the last 10 seconds
            # # cur.execute("SELECT Valid FROM SensorEntries WHERE Timestamp >= NOW() - INTERVAL %s SECOND", (sample_rate,))
            # # valid_entries = [row[0] for row in cur.fetchall()]  # List of Valid values
            # # #print(f"Valid entries in the last 10 seconds: {valid_entries}")

            # # # Count only non-consecutive 1s
            # # speed = 0
            # # previous = None
            # # for entry in valid_entries:
                # # if entry == 1 and previous != 1:
                    # # speed += 1
                # # previous = entry

            # # print(f"Speed (non-consecutive valid entries per 10 seconds): {speed}")
            
            # # # Update the label directly
            # # self.plotNumberLabel.setText(f"BPM: {speed * freq}")
        # # except mariadb.Error as e:
            # # print(f"Error calculating speed: {e}")    
    
    
    
    
        # # # # # self.bpmLabel.setText(f"BPM: {value}")
        # # # # # self.current_bpm = value
        # # # # # self.checkAndSendLightCommand()

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
        self.workerBLE.signals.signalDataParsed.connect(self.footPlot.update_plot)
     #   self.workerBLE.signals.signalDataParsed.connect(self.footPlot.updateDB)     #useless todelete
        self.workerBLE.signals.signalDataParsed.connect(self.updateBPM)
       # self.workerBLE.signals.signalDataParsed.connect(MatplotlibCanvas.update_plot)       #29 nov 2024
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
            lower_bound = self.current_bpm * 0.9
            upper_bound = self.current_bpm * 1.1
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
        print(f"Debug: Received message for battery - {message}")       #For troubleshooting, new battery
        match = re.search(r'B:(\d+)', message)
        if match:
            battery = match.group(1)
            self.batteryLabel.setText(f"Battery: {battery}%")
        else:
            print("Battery percentage not found in the message.")
            

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
        self.sensor_exceed_timestamps[sensor_key] = timestamps[-50:]

        if len(timestamps) >= 2:
            intervals = [(timestamps[i] - timestamps[i-1]).total_seconds() for i in range(1, len(timestamps))]
            avg_interval = sum(intervals) / len(intervals)
            bpm = int(60 / avg_interval)
            print(f"Rhythm for {sensor_key}: {bpm} BPM")

            # Update cadence label with the calculated BPM
            self.updateCadence(bpm)

    def updateCadence(self, bpm):
  #      self.cadenceLabel.setText(f"Cadence: {bpm} BPM")
  #      self.current_cadence = bpm
    #replaced 2 lines above with line below to stop error messages
        self.current_cadence = 4
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

    def resetApp(self):
        # Method to reset the app
        print("Resetting the application...")
        # Close mariadb Connection
        conn.close()
        QProcess.startDetached(sys.executable, sys.argv)  # Restart the app
        QApplication.exit()
    def CloseApp(self):
        # Method to close the app
        print("Closing the application.")
        # Delete sensorEntries table, updating workout and then closing mariadb connection
        try:
            # Delete all entries from SensorEntries
            cur.execute("DELETE FROM SensorEntries")
            
            # Truncate the table to reset the AUTO_INCREMENT value
            cur.execute("TRUNCATE TABLE SensorEntries")
            
            # Commit the transaction
            conn.commit()
        except mariadb.Error as e:
            print(f"Error deleting or truncating SensorEntries: {e}")
            
        update_workout_data(cur,conn)
        
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
app.exec()

