import sys
import mariadb
import time
from datetime import datetime, timedelta
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QLabel, QTableWidget, QTableWidgetItem


calculated_speeds = []  # This will hold the speeds over time
# Initialize start time pour calculer duree entrainement
workout_start_time = None

# After collecting several speeds, you can calculate the average, max, and min
def calculate_speed_statistics():
    if len(calculated_speeds) > 0:
        avg_speed = sum(calculated_speeds) / len(calculated_speeds)
        max_speed = max(calculated_speeds)
    else:
        print("No speed data available to calculate statistics.")
        avg_speed = max_speed = None
    
    return avg_speed, max_speed

# Function to fetch workout data from the database
def fetch_workout_data(cur, conn):
    try:
        # conn = mariadb.connect(
            # user="webuser",
            # password="password",
            # host="127.0.0.1",
            # port=3306,
            # database="pfedb"
        # )
        # cur = conn.cursor()
        cur.execute(
            """
            SELECT Name, TimeStarted, TIMESTAMPDIFF(SECOND, TimeStarted, TimeEnded) AS Duration, 
                   AverageSpeed, HighestSpeed
            FROM TrainingSessions 
            ORDER BY TimeStarted DESC
            """
        )
        workouts = cur.fetchall()
        
        
        # Format the duration in minutes:seconds
        formatted_workouts = []
        for workout in workouts:
            name, time_started, duration_in_seconds, avg_speed, max_speed = workout
            minutes = duration_in_seconds // 60
            seconds = duration_in_seconds % 60
            formatted_duration = f"{minutes}:{seconds:02}"  # Format as MM:SS
            formatted_workouts.append((name, time_started, formatted_duration, avg_speed, max_speed))
            
        return formatted_workouts
        
    except mariadb.Error as e:
        print(f"Error fetching workout data: {e}")
        return []
        
def update_workout_data(cur, conn):
    # Generate random data for TrainingSessions
    name = "Default"
    
    global workout_start_time
    
    if workout_start_time is None:
        workout_start_time = datetime.now()
    
    workout_end_time = datetime.now()
    
    average_speed, highest_speed = calculate_speed_statistics()
    if workout_start_time!= workout_end_time and average_speed != None:
        try:
            cur.execute("INSERT INTO TrainingSessions (Name, TimeStarted, TimeEnded, AverageSpeed, HighestSpeed) VALUES (%s, %s, %s, %s, %s)",
                        (name, workout_start_time, workout_end_time, average_speed, highest_speed))
            conn.commit()
            print(f"Last Inserted ID: {cur.lastrowid}")
        except mariadb.Error as e:
            print(f"Error inserting into TrainingSessions: {e}")


#sensor_data was previously value, fonction team ete24
def updateBPM(sensor_data, plotNumberLabel, conn, cur, sample_rate, freq, THRESHOLD):
    
    global workout_start_time
    
    # Extract sensor values
    anp_values = {
        "anp35": sensor_data.anp35,
        "anp34": sensor_data.anp34,
        "anp39": sensor_data.anp39,
        "anp38": sensor_data.anp38,
        "anp37": sensor_data.anp37,
        "anp36": sensor_data.anp36
    }
    # Decomposer et mettre dans un format pour envoyer au database
    result = ",".join(str(value) for value in anp_values.values())
     
    valid_sensor_cnt = sum(1 for value in anp_values.values() if value > THRESHOLD)
            
    try:
        cur.execute("SELECT Valid FROM SensorEntries ORDER BY Timestamp DESC LIMIT 1")
        last_valid_variable = cur.fetchone()  # Fetch the most recent entry
        last_valid_variable = last_valid_variable[0] if last_valid_variable else 0  # Default to 0 if no entry
    except mariadb.Error as e:
        print(f"Error fetching last entry: {e}")
        last_valid_variable = None
        
    print("Last valid variable is", last_valid_variable)
    
    valid_entry = 0;
    
    # Ne comptabilisera pas si l'entree est très legere (a moins que la derniere ait ete 0)
    if valid_sensor_cnt > 0 and valid_sensor_cnt <= 3:  #si seulement 3 bandes ou moins sont activees, invalid
            valid_entry = 0
    elif valid_sensor_cnt > 3: #plus de la motie des capteurs, pour que l'utilisateur ne "triche" pas
            valid_entry = 1
    else:
            valid_entry = 2;    #for 0,0,0,0,0
            
    if valid_entry != 9 and last_valid_variable !=12:
        try:        #insert information in db
            cur.execute("INSERT INTO SensorEntries (Timestamp, SensorArray, Valid) VALUES (NOW(), %s, %s)", (result, valid_entry))
               #cur.execute("INSERT INTO TrainingSessions (Name, TimeStarted, TimeEnded, HighestSpeed, LowestSpeed, AverageSpeed) VALUES (?, ?, ?, ?, ?, ?)",
               #("Test_v4", time_started, time_ended, random.randint(50,57), random.randint(38,45), random.randint(45,50)))
                
        except mariadb.Error as e: 
                print(f"Error: {e}")

        conn.commit() 
        print(f"Last Inserted ID: {cur.lastrowid}")

    
    # Calculate cadence/speed
    try:
        # Fetch all Valid entries from the last 10 seconds
        cur.execute("SELECT Valid FROM SensorEntries WHERE Timestamp >= NOW() - INTERVAL %s SECOND", (sample_rate,))
        valid_entries = [row[0] for row in cur.fetchall()]  # List of Valid values
        #print(f"Valid entries in the last 10 seconds: {valid_entries}")

        # Count only non-consecutive 1s
        speed = 0
        previous = None
        for entry in valid_entries:
            if entry == 1 and previous != 1:
                speed += 1
            previous = entry
            
        # Set start time of workout. (first measurement)
        if not calculated_speeds:  # Checks if the list is empty
            workout_start_time = datetime.now()  # Get the current time in seconds

        print(f"Speed (non-consecutive valid entries per 10 seconds): {speed}")
        # Add the calculated speed to the list
        calculated_speeds.append(speed * freq)  # Store the speed in the list
        
        # Update the label directly
        plotNumberLabel.setText(f"BPM: {speed * freq}")
    except mariadb.Error as e:
        print(f"Error calculating speed: {e}")
        
        
#sensor_data was previously value, fonction team ete24
def calculateBPM(sensor_data, conn, cur, sample_rate, freq, THRESHOLD):
    
    global workout_start_time
    
    # Extract sensor values
    anp_values = {
        "anp35": sensor_data.anp35,
        "anp34": sensor_data.anp34,
        "anp39": sensor_data.anp39,
        "anp38": sensor_data.anp38,
        "anp37": sensor_data.anp37,
        "anp36": sensor_data.anp36
    }
    # Decomposer et mettre dans un format pour envoyer au database
    result = ",".join(str(value) for value in anp_values.values())
     
    valid_sensor_cnt = sum(1 for value in anp_values.values() if value > THRESHOLD)
            
    try:
        cur.execute("SELECT Valid FROM SensorEntries ORDER BY Timestamp DESC LIMIT 1")
        last_valid_variable = cur.fetchone()  # Fetch the most recent entry
        last_valid_variable = last_valid_variable[0] if last_valid_variable else 0  # Default to 0 if no entry
    except mariadb.Error as e:
        print(f"Error fetching last entry: {e}")
        last_valid_variable = None
        
    print("Last valid variable is", last_valid_variable)
    
    valid_entry = 0;
    
    # Ne comptabilisera pas si l'entree est très legere (a moins que la derniere ait ete 0)
    if valid_sensor_cnt > 0 and valid_sensor_cnt <= 3:  #si seulement 3 bandes ou moins sont activees, invalid
            valid_entry = 0
    elif valid_sensor_cnt > 3: #plus de la motie des capteurs, pour que l'utilisateur ne "triche" pas
            valid_entry = 1
    else:
            valid_entry = 2;    #for 0,0,0,0,0
            
    try:        #insert information in db
        cur.execute("INSERT INTO SensorEntries (Timestamp, SensorArray, Valid) VALUES (NOW(), %s, %s)", (result, valid_entry))
           #cur.execute("INSERT INTO TrainingSessions (Name, TimeStarted, TimeEnded, HighestSpeed, LowestSpeed, AverageSpeed) VALUES (?, ?, ?, ?, ?, ?)",
           #("Test_v4", time_started, time_ended, random.randint(50,57), random.randint(38,45), random.randint(45,50)))
            
    except mariadb.Error as e: 
            print(f"Error: {e}")

    conn.commit() 
    print(f"Last Inserted ID: {cur.lastrowid}")

    
    # Calculate cadence/speed
    try:
        # Fetch all Valid entries from the last 10 seconds
        cur.execute("SELECT Valid FROM SensorEntries WHERE Timestamp >= NOW() - INTERVAL %s SECOND", (sample_rate,))
        valid_entries = [row[0] for row in cur.fetchall()]  # List of Valid values
        #print(f"Valid entries in the last 10 seconds: {valid_entries}")

        # Count only non-consecutive 1s
        speed = 0
        previous = None
        for entry in valid_entries:
            if entry == 1 and previous != 1:
                speed += 1
            previous = entry
            
        # Set start time of workout. (first measurement)
        if not calculated_speeds:  # Checks if the list is empty
            workout_start_time = datetime.now()  # Get the current time in seconds

        print(f"Speed (non-consecutive valid entries per 10 seconds): {speed}")
        # Add the calculated speed to the list
        calculated_speeds.append(speed * freq)  # Store the speed in the list
        
        # Update the label directly
        return (speed * freq)
    except mariadb.Error as e:
        print(f"Error calculating speed: {e}")



# New window to display workout log
class NewWindow(QWidget):
    def __init__(self, cur, con):
        super().__init__()
        self.setWindowTitle("Workout Log")  
        self.setGeometry(0, 0, 750, 450)    # (x,y,width,heigh)
        
        # Fetch data from the database
        self.workout_data = fetch_workout_data(cur,con)

        # Create the table
        self.table = QTableWidget(self)
        self.table.setRowCount(len(self.workout_data))  # Set the number of rows based on the data
        self.table.setColumnCount(5)  # 5 columns: Name, Date, Duration, HighestSpeed, AverageSpeed 
        
        # Set table headers
        # self.table.setHorizontalHeaderLabels(["Name", "Date", "Duration (mins)", "Max Speed", "Min Speed", "Avg Speed"])
        self.table.setHorizontalHeaderLabels(["Name", "Date", "Duration (mins)", "Avg Speed", "Max Speed"])

        # Populate the table with data
        for row, workout in enumerate(self.workout_data):
            self.table.setItem(row, 0, QTableWidgetItem(str(workout[0])))  # Name
            self.table.setItem(row, 1, QTableWidgetItem(str(workout[1])))  # TimeStarted (Date)
            self.table.setItem(row, 2, QTableWidgetItem(str(workout[2])))  # Duration (in minutes)
            self.table.setItem(row, 3, QTableWidgetItem(str(workout[3])))  # HighestSpeed
            self.table.setItem(row, 4, QTableWidgetItem(str(workout[4])))  # AverageSpeed
        #   self.table.setItem(row, 4, QTableWidgetItem(str(workout[4])))  # LowestSpeed

        
        # Apply style
        self.style_table()

        # Layout for the new window
        layout = QVBoxLayout()
        layout.addWidget(self.table)
        self.setLayout(layout)

    def style_table(self):
        # Apply simplified styles to the table widget
        self.table.setStyleSheet("""
            QTableWidget {
            border: 8px solid black;  /* Black border for the table */
            font-size: 15px;  /* Adjust font size */
            }
            
            QTableWidget::item {
            border: 1px solid black;  /* Continuous lines for cells */
            }
            
            QHeaderView::section {  /* Pour l'entete */
            font-weight: bold;
            }
        """)

        # Set a custom font
        #font = QFont("Arial", 12)  # Replace "Arial" with your preferred font
        #self.table.setFont(font)
    
        # Set column widths
        self.table.setColumnWidth(0, 100)  # Name column width
        self.table.setColumnWidth(1, 170)  # Date column width
        self.table.setColumnWidth(2, 120)  # Duration column width
        self.table.setColumnWidth(3, 100)  # Max Speed column width
        self.table.setColumnWidth(4, 100)  # Min Speed column width
        self.table.setColumnWidth(5, 100)  # Avg Speed column width

# Main Window
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Main Window")
        self.setGeometry(100, 100, 400, 300)

        # Layout for the main window
        layout = QVBoxLayout()

        # Create a button that opens the workout log window
        self.button = QPushButton("Workout Log", self)
        self.button.clicked.connect(self.open_new_window)  # Connect the button click to the method
        layout.addWidget(self.button)

        self.setLayout(layout)

    def open_new_window(self):
        # Create and show the new window
        self.new_window = NewWindow()
        self.new_window.show()

# Main Execution
if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    main_window = MainWindow()
    main_window.show()
    
    sys.exit(app.exec_())
