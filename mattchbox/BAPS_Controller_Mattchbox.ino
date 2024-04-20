/*
  BAPS Serial (Over USB) Controller
  First deployed on an Arduino Nano in the MattchBox by Matthew Stratford, Winter 2018-19

  Adapted June 2021 for fader live detection.
*/

const int noOfChannels = 3;
// Pins D2 to D7 for BAPS 1 Play, Stop, BAPS 2 Play...
const int noOfPins = noOfChannels * 2;
int buttonPins[noOfPins] = {2,3,4,5,6,7};
int buttonDelay[noOfPins];
int buttonStates[noOfPins];
// Pins 8, 9, 10 for BAPS 1,2,3 Play, (stop can also be implemented if more pins are available.)
int ledPins[noOfPins]    = {8,0,9,0,10,0};
int ledTimeouts[noOfPins];
int studioPwrDetect   = A0;
int studioPwrDelay;
int faderLivePins[noOfChannels] = {A1,A3,A5};
int faderLiveState[noOfChannels];
int keepAlive = 100;

// the setup routine runs once when you press reset:
void setup() {
  // initialize serial communication at 2400 bits per second:
  Serial.begin(2400);
  while (!Serial) {
    ; // wait for serial port to connect. Needed for native USB port only
  }
  int j;
  for (j = 0; j < noOfPins; j++) {
  // make the pushbutton's pin an input:
    pinMode(buttonPins[j], INPUT_PULLUP);
    // make the led pins outputs
    // output pin must be high to turn off LEDs.
    pinMode(ledPins[j], OUTPUT);
    digitalWrite(ledPins[j], HIGH);
  }
  // BAPS Conn OK LED
  pinMode(13, OUTPUT);
  digitalWrite(13, HIGH);

  // Fader Live Monitoring Pins
  int i;
  for (i = 0; i < noOfChannels; i++) {
    pinMode(faderLivePins[i], INPUT_PULLUP);
  }
}

// the loop routine runs over and over again forever:
void loop() {
  int i;
  
  if (digitalRead(studioPwrDetect)) {
    if (studioPwrDelay <= 500) {
      studioPwrDelay++;
    }
  } else {
    studioPwrDelay = 0;
  }
  for (i = 0; i < noOfChannels; i++) {
    int faderLive = digitalRead(faderLivePins[i]);
    // Periodically send an update on keepalive, or send state change if we've changed.
    if (faderLive != faderLiveState[i] || keepAlive <= 1) {

      if (!faderLive) {
        Serial.write(51+i); // 50 for channel 0 off...
      } else {
        Serial.write(61+i); // 60 for channel 0 on...
      }
      // Update live state.
      faderLiveState[i] = faderLive;
    }
  }
  // read the input pin:

  for (i = 0; i < noOfPins; i++)
  {
    // Add some debouncing by counting up if the input changes.
    int readValue = digitalRead(buttonPins[i]);
    if (readValue != buttonStates[i]) {
      buttonDelay[i]++;
    } else {
      buttonDelay[i] = 0;
    }
    // If the input pin has changed for 5 loops, it's probably not noise.
    if (buttonDelay[i] > 5) {
      buttonStates[i] = readValue;
      // The input shorts to ground when a button is pressed.
      if (readValue == 0) {
          // Ignore inputs upto 5 seconds (500 x 10ms loop speed, ish)
          // after studio power is provided. (S2 desks trigger inputs on power up.)
          if (studioPwrDelay > 500) {
            // Set the LED of the channel triggered to turn on for 100 cycles
            ledTimeouts[i] = 100;
            // BAPS is expecting a raw byte of 1-6
            Serial.write(i+1);
          }
      }
    }
    // Light the LED if it currently has a countdown remaining.
    if (ledTimeouts[i] != 0 && ledPins[i] != 0) {
      ledTimeouts[i]--;
      digitalWrite(ledPins[i], LOW);
    } else {
      digitalWrite(ledPins[i], HIGH);
    }
  }
  delay(10);        // delay in between reads for stability
  // Implement keepalive, every second send 255 to the BAPS Server, if it replies, light CONN led.
  keepAlive--;
  if (keepAlive == 0) {
    keepAlive = 1000;
    Serial.write(255);
    byte data[1];
    data[0] = 0;
    Serial.readBytes(data, 1);
    if (data[0] == 255) {
      digitalWrite(13, LOW);
    } else {
      digitalWrite(13, HIGH);
    }
  }
}
