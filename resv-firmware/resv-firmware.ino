#include <Wire.h>
#include <Adafruit_DS1841.h>

// Pin definitions for Feather RP2040
#define LED_PIN LED_BUILTIN    // Built-in LED
#define I2C_SDA_PIN 2          // I2C Data pin
#define I2C_SCL_PIN 3          // I2C Clock pin
#define RELAY_PIN 10           // Relay control pin

Adafruit_DS1841 ds;
bool relay_on = false;  // Track relay state

void testRelay() {
    // Test relay with visible delay
    digitalWrite(RELAY_PIN, HIGH);  // Turn ON
    delay(1000);                    // Wait 1 second
    digitalWrite(RELAY_PIN, LOW);   // Turn OFF
    delay(500);                     // Wait 0.5 second
}

void setup() {
    // Configure pins
    pinMode(LED_PIN, OUTPUT);
    pinMode(RELAY_PIN, OUTPUT);
    digitalWrite(LED_PIN, LOW);
    digitalWrite(RELAY_PIN, LOW);   // Start with relay OFF
    
    // Test relay at startup
    testRelay();
    
    // Start serial with wait
    Serial.begin(9600);
    
    // Initialize I2C
    Wire.setSDA(I2C_SDA_PIN);
    Wire.setSCL(I2C_SCL_PIN);
    Wire.begin();
    
    // Initialize DS1841
    if (!ds.begin()) {
        // If DS1841 not found, blink rapidly
        while (1) {
            digitalWrite(LED_PIN, !digitalRead(LED_PIN));
            delay(100);
        }
    }
    
    // Set initial wiper position to minimum speed
    ds.setWiper(20);  // Start at minimum speed
    
    // Show we're ready
    digitalWrite(LED_PIN, HIGH);
    Serial.println("Feather RP2040 Wavemaker Ready");
}

void loop() {
    if (Serial.available() > 0) {
        String input = Serial.readStringUntil('\n');
        input.trim();
        
        if (input == "on") {
            digitalWrite(RELAY_PIN, HIGH);
            digitalWrite(LED_PIN, HIGH);
            relay_on = true;
            Serial.println("ON_OK");
        }
        else if (input == "off") {
            digitalWrite(RELAY_PIN, LOW);
            digitalWrite(LED_PIN, LOW);
            relay_on = false;
            Serial.println("OFF_OK");
        }
        else {
            // Handle speed values only if relay is ON
            if (relay_on) {
                int value = input.toInt();
                if (value >= 20 && value <= 127) {  // Enforce minimum speed of 20
                    ds.setWiper(value);
                    Serial.print("SET_");
                    Serial.println(value);
                    
                    // Blink LED briefly to show activity
                    digitalWrite(LED_PIN, LOW);
                    delay(50);
                    digitalWrite(LED_PIN, HIGH);
                }
                else {
                    Serial.println("ERROR_VALUE");  // Error: value out of range
                }
            }
            else {
                Serial.println("ERROR_OFF");  // Error: relay must be on first
            }
        }
    }
} 