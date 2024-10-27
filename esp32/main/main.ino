#include "Adafruit_HX711.h"
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include <esp_system.h>
#include <string>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include "esp_task_wdt.h"
#include <Wire.h> // Needed for I2C
#include <SparkFun_MAX1704x_Fuel_Gauge_Arduino_Library.h> // Click here to get the library: http://librarymanager/All#SparkFun_MAX1704x_Fuel_Gauge_Arduino_Library

// See the following for generating UUIDs:
// https://www.uuidgenerator.net/

#define DISABLE_LOADCELLS
#define SERVICE_UUID           "6E400001-B5A3-F393-E0A9-E50E24DCCA9E" // UART service UUID
#define CHARACTERISTIC_UUID_RX "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
#define CHARACTERISTIC_UUID_TX "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

#define NORMAL_OPERATION 0
#define NEED_TARING 1
#define NEED_SCALING 2
uint8_t weightOperation = 1;

// I2C
TwoWire myWire(0);
SFE_MAX1704X lipo; // Defaults to the MAX17043

double voltage = 0; // Variable to keep track of LiPo voltage
double soc = 0; // Variable to keep track of LiPo state-of-charge (SOC)
bool alert; // Variable to keep track of whether alert has been triggered

// Define the pins for the HX711 communication
const uint8_t DATA_PIN1 = 33;  // Can use any pins!
const uint8_t CLOCK_PIN1 = 25; // Can use any pins!
const uint8_t DATA_PIN2 = 26;  // Can use any pins!
const uint8_t CLOCK_PIN2 = 27; // Can use any pins!

// Taring operation variables
uint8_t needTaring = 1;
uint8_t taredValue;
bool    taredUnit = false; // Default to kg (false: kg, true: lbs)


// Scaling operation variables
uint8_t needScaling = 0;
float   scaleFactor = 1;
float   weight = 0;
int32_t weightA128_1;
int32_t weightB32_1;
int32_t weightA128_2;
int32_t weightB32_2;

// Lighting operation
bool needLight = false;
bool needFaster = false;
bool needSlower = false;


// BLE
BLEServer *pServer = NULL;
BLECharacteristic *pTxCharacteristic;
bool deviceConnected = false;
bool oldDeviceConnected = false;

Adafruit_HX711 hx711_1(DATA_PIN1, CLOCK_PIN1);
Adafruit_HX711 hx711_2(DATA_PIN2, CLOCK_PIN2);

void asyncLight(void * parameter) {
  while(true) {
    if (needLight) {
        digitalWrite(23, LOW);
        digitalWrite(18, HIGH);
        digitalWrite(10, LOW);
    } else if (needFaster) {
        digitalWrite(23, LOW);
        digitalWrite(18, LOW);
        digitalWrite(10, HIGH);
    } else if (needSlower) {
        digitalWrite(23, HIGH);
        digitalWrite(18, LOW);
        digitalWrite(10, LOW);
    } else {
        // Turn the LEDs OFF
        digitalWrite(23, LOW);
        digitalWrite(18, LOW);
        digitalWrite(10, LOW);
    }
    needLight = false;
    needSlower = false;
    needFaster = false;

    delay(3000);
  }
}

// Function that you want to run asynchronously
void asyncFunction(void * parameter) {
    // Cast the parameter to the appropriate type
    uint8_t* weightOperationPtr = (uint8_t*) parameter;

    while (true) {
                Serial.print("Weight operation: ");
                Serial.println(*weightOperationPtr);

        switch (*weightOperationPtr) {

            case NEED_TARING:
                // tare
                tareSensors();

                weightOperation = NORMAL_OPERATION;
                break;

            case NEED_SCALING:
                Serial.println("Calibrating....");
                //scale
                //const int numSamples = 10; // Define the number of samples

                for (uint8_t t = 0; t < 10; t++) {
                    int32_t weightA128_1 = hx711_1.readChannelBlocking(CHAN_A_GAIN_64);
                    int32_t weightB32_1 = hx711_1.readChannelBlocking(CHAN_B_GAIN_32);
                    int32_t weightA128_2 = hx711_2.readChannelBlocking(CHAN_A_GAIN_64);
                    int32_t weightB32_2 = hx711_2.readChannelBlocking(CHAN_B_GAIN_32);

                    float weightSum = abs(weightA128_1) + abs(weightB32_1) + abs(weightA128_2) + abs(weightB32_2);

                    if (t == 0) {
                        scaleFactor = weightSum / taredValue;
                    } else {
                        scaleFactor = (scaleFactor + weightSum / taredValue) / 2.0;
                    }
                    // Yield control back to the FreeRTOS scheduler
                    vTaskDelay(1); // Yield to prevent watchdog timer from triggering
                }

                Serial.print("Scale Factor: ");
                Serial.println(scaleFactor);

                weightOperation = NORMAL_OPERATION;

                break;
                
            case NORMAL_OPERATION:
                Serial.println("Normal operation loop");
                weightA128_1 = hx711_1.readChannelBlocking(CHAN_A_GAIN_64);
                weightB32_1 = hx711_1.readChannelBlocking(CHAN_B_GAIN_32);
                weightA128_2 = hx711_2.readChannelBlocking(CHAN_A_GAIN_64);
                weightB32_2 = hx711_2.readChannelBlocking(CHAN_B_GAIN_32);
                char string[200];
                snprintf(string, sizeof(string), "WA1:%d,WB1:%d,WA2:%d,WB2:%d", 
                  weightA128_1, 
                  weightB32_1, 
                  weightA128_2,
                  weightB32_2);
                Serial.println(string);

                weight = ( abs((float)weightA128_1) + abs((float)weightB32_1) + abs((float)weightA128_2) + abs((float)weightB32_2) ) / scaleFactor;

                break;
            default:
                break;
        }
        
        delay(1000); // 1-second delay
    }
}


void tareSensors() {
  Serial.println("Tareing....");
  for (uint8_t t = 0; t < 3; t++) {
    hx711_1.tareA(hx711_1.readChannelRaw(CHAN_A_GAIN_64));
    hx711_1.tareA(hx711_1.readChannelRaw(CHAN_A_GAIN_64));
    hx711_1.tareB(hx711_1.readChannelRaw(CHAN_B_GAIN_32));
    hx711_1.tareB(hx711_1.readChannelRaw(CHAN_B_GAIN_32));
    hx711_2.tareA(hx711_2.readChannelRaw(CHAN_A_GAIN_64));
    hx711_2.tareA(hx711_2.readChannelRaw(CHAN_A_GAIN_64));
    hx711_2.tareB(hx711_2.readChannelRaw(CHAN_B_GAIN_32));
    hx711_2.tareB(hx711_2.readChannelRaw(CHAN_B_GAIN_32));
    // Yield control back to the FreeRTOS scheduler
    vTaskDelay(1); // Yield to prevent watchdog timer from triggering
  }
}


class MyServerCallbacks: public BLEServerCallbacks {
    void onConnect(BLEServer* pServer) {
      deviceConnected = true;
    };

    void onDisconnect(BLEServer* pServer) {
      deviceConnected = false;
    }
};

class MyCallbacks : public BLECharacteristicCallbacks {
public:
    void onWrite(BLECharacteristic *pCharacteristic) {
        // Convert the String object returned by pCharacteristic->getValue() into a const char*
        String value = pCharacteristic->getValue();
        const char* valueCStr = value.c_str();
        
        // Use const char* to initialize std::string
        std::string rxValue(valueCStr);

        if (rxValue.length() > 0) {
            Serial.println("*********");
            Serial.print("Received Value: ");
            for (int i = 0; i < rxValue.length(); i++)
                Serial.print(rxValue[i]);

            Serial.println();
            Serial.println("*********");

            // Split the incoming string to extract the first word
            size_t firstSpaceIndex = rxValue.find(' ');
            std::string rxValue_command = rxValue.substr(0, firstSpaceIndex);

            if (rxValue_command == "Calibrate") {
                Serial.println("Executing Calibrate command...");
                
                // Assign scale operation variables
                weightOperation = NEED_SCALING;
                size_t secondSpaceIndex = rxValue.find(' ', firstSpaceIndex + 1);
                size_t thirdSpaceIndex = rxValue.find(' ', secondSpaceIndex + 1);
                std::string tempTaredValue = rxValue.substr(firstSpaceIndex + 1, secondSpaceIndex - firstSpaceIndex - 1);
                Serial.println(tempTaredValue.c_str());
                // taredValue
                taredValue = std::stoi(tempTaredValue);
                // taredUnit
                std::string tempTaredUnit = rxValue.substr(secondSpaceIndex + 1, thirdSpaceIndex - secondSpaceIndex - 1);
                if (tempTaredUnit == "lbs") {
                  taredUnit = true;
                } else {
                  taredUnit = false;
                }


            } else if (rxValue_command == "Tare") {
                // Assign tare operation variables
                weightOperation = NEED_TARING;

            } else if (rxValue_command == "Light") {
                needLight = true;
            } else if (rxValue_command == "Faster") {
                needFaster = true;
            } else if (rxValue_command == "Slower") {
                needSlower = true;
            } else {
                Serial.print("Unknown command received: ");
                Serial.println(rxValue.c_str());
            }
        }
    }
};

void setup() {
  Serial.begin(115200);

  /*  FSR  */
  pinMode(36, INPUT);
  pinMode(37, INPUT);
  pinMode(38, INPUT);
  pinMode(39, INPUT);
  pinMode(34, INPUT);
  pinMode(35, INPUT);
  /*  LED  */
  pinMode(23, OUTPUT);
  pinMode(18, OUTPUT);
  pinMode(10, OUTPUT);
  // Turn the LEDs OFF
  digitalWrite(23, LOW);
  digitalWrite(18, LOW);
  digitalWrite(10, LOW);

  /* I2C */
  myWire.begin();
  lipo.enableDebugging(Serial); // Uncomment this line to enable helpful debug messages on non-standard serial
  // Set up the MAX17043 LiPo fuel gauge:
  if (lipo.begin(myWire) == false) // Connect to the MAX17043 using non-standard wire port
  {
    Serial.println(F("MAX17043 not detected. Please check wiring. Freezing."));
    while (1)
      ;
  }
  // Quick start restarts the MAX17043 in hopes of getting a more accurate
	// guess for the SOC.
	lipo.quickStart();

	// We can set an interrupt to alert when the battery SoC gets too low.
	// We can alert at anywhere between 1% - 32%:
	lipo.setThreshold(20); // Set alert threshold to 20%.


  // Create the BLE Device
  BLEDevice::init("esp32");  // Set the device name to "esp32"

  // Create the BLE Server
  pServer = BLEDevice::createServer();
  pServer->setCallbacks(new MyServerCallbacks());

  // Create the BLE Service
  BLEService *pService = pServer->createService(SERVICE_UUID);

  // Create a BLE Characteristic
  pTxCharacteristic = pService->createCharacteristic(
     CHARACTERISTIC_UUID_TX,
     BLECharacteristic::PROPERTY_NOTIFY
  );
                  
  pTxCharacteristic->addDescriptor(new BLE2902());

  BLECharacteristic * pRxCharacteristic = pService->createCharacteristic(
    CHARACTERISTIC_UUID_RX,
    BLECharacteristic::PROPERTY_WRITE
  );

  pRxCharacteristic->setCallbacks(new MyCallbacks());

  // Start the service
  pService->start();

  // Start advertising
  pServer->getAdvertising()->start();
  Serial.println("Waiting a client connection to notify...");

  // wait for serial port to connect. Needed for native USB port only
  while (!Serial) {
    delay(10);
  }

  Serial.println("Adafruit HX711 Test!");

        // Create a FreeRTOS task
    xTaskCreate(
        asyncFunction,  // Function to be executed
        "Async Task",   // Name of the task
        10000,          // Stack size (in words)
        &weightOperation,           // Parameter to pass
        1,              // Task priority
        NULL            // Task handle
    );
            // Create another FreeRTOS task
    xTaskCreate(
        asyncLight,  // Function to be executed
        "Async Light Task",   // Name of the task
        10000,          // Stack size (in words)
        NULL,           // Parameter to pass
        2,              // Task priority
        NULL            // Task handle
    );


  // Initialize the HX711
  Serial.print("Initialising HX711_1 on pins ");
  Serial.print(DATA_PIN1);
  Serial.print(", ");
  Serial.println(CLOCK_PIN1);
  hx711_1.begin();
  Serial.print("Initialising HX711_2 on pins ");
  Serial.print(DATA_PIN2);
  Serial.print(", ");
  Serial.println(CLOCK_PIN2);
  hx711_2.begin();

}

void loop() {
    // lipo.getVoltage() returns a voltage value (e.g. 3.93)
  voltage = lipo.getVoltage();
  // lipo.getSOC() returns the estimated state of charge (e.g. 79%)
  soc = lipo.getSOC();
  // lipo.getAlert() returns a 0 or 1 (0=alert not triggered)
  alert = lipo.getAlert();

  // Read analog values
  int analogValP35 = analogRead(35);
  int analogValP39 = analogRead(39);
  int analogValP37 = analogRead(37);
  int analogValP36 = analogRead(36);
  int analogValP34 = analogRead(34);
  int analogValP38 = analogRead(38);

  // Get the current time in milliseconds
  unsigned long currentMillis = millis();
  unsigned long currentSeconds = currentMillis / 1000;
  unsigned long currentMilliseconds = currentMillis % 1000;

  // Format the time as MM:SS.mmm
  char timeStr[20];
  snprintf(timeStr, sizeof(timeStr), "%02lu:%02lu.%03lu", 
           (currentSeconds / 60) % 60, 
           currentSeconds % 60, 
           currentMilliseconds);

  // Format the fsr data into strings
  char dataStr0[32];
  snprintf(dataStr0, sizeof(dataStr0), "%s,AnP35:%d",
           timeStr, analogValP35);
  char dataStr1[32];
  snprintf(dataStr1, sizeof(dataStr1), "%s,AnP39:%d",
           timeStr, analogValP39);
  char dataStr2[32];
  snprintf(dataStr2, sizeof(dataStr2), "%s,AnP37:%d",
           timeStr, analogValP37);
  char dataStr3[32];
  snprintf(dataStr3, sizeof(dataStr3), "%s,AnP36:%d",
           timeStr, analogValP36);
  char dataStr4[32];
  snprintf(dataStr4, sizeof(dataStr4), "%s,AnP34:%d",
           timeStr, analogValP34);
  char dataStr5[32];
  snprintf(dataStr5, sizeof(dataStr5), "%s,AnP38:%d",
           timeStr, analogValP38);
      
  // Format the weight into strings
  char weightStr[32];
  snprintf(weightStr, sizeof(weightStr), "%s,W:%ld",
           timeStr, (int)weight);
  //Serial.println(weightStr);

    // Format the soc into strings
  char socStr[32];
  snprintf(socStr, sizeof(socStr), "%s,B:%ld",
           timeStr, (int)soc);
  //Serial.println(socStr);



  if (deviceConnected) {
    // Send the weight via Bluetooth
    pTxCharacteristic->setValue(weightStr);
    pTxCharacteristic->notify();
    // Send the weight via Bluetooth
    pTxCharacteristic->setValue(socStr);
    pTxCharacteristic->notify();
    // Send the data via Bluetooth
    pTxCharacteristic->setValue(dataStr0);
    pTxCharacteristic->notify();
    pTxCharacteristic->setValue(dataStr1);
    pTxCharacteristic->notify();
    pTxCharacteristic->setValue(dataStr2);
    pTxCharacteristic->notify();
    pTxCharacteristic->setValue(dataStr3);
    pTxCharacteristic->notify();
    pTxCharacteristic->setValue(dataStr4);
    pTxCharacteristic->notify();
    pTxCharacteristic->setValue(dataStr5);
    pTxCharacteristic->notify();
    

    delay(200); // Delay to avoid congestion
  }

  // disconnecting
  if (!deviceConnected && oldDeviceConnected) {
    delay(500); // give the bluetooth stack the chance to get things ready
    pServer->startAdvertising(); // restart advertising
    Serial.println("start advertising");
    oldDeviceConnected = deviceConnected;
  }
  // connecting
  if (deviceConnected && !oldDeviceConnected) {
    // do stuff here on connecting
    oldDeviceConnected = deviceConnected;
  }
}
