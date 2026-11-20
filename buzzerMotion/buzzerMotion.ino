
#define PIR_PIN     8
#define BUZZER_PIN  9

const unsigned long HOLD_TIME = 250;
const unsigned long COOLDOWN_TIME = 2000;
const unsigned long MOTION_CONFIRM_TIME = 100;

unsigned long lastMotionTime = 0;
unsigned long alarmEndedTime = 0;
unsigned long motionStartTime = 0;

bool alarmActive = false;
bool inCooldown = false;
bool motionPending = false;

void setup() {
  Serial.begin(9600);

  pinMode(PIR_PIN, INPUT);
  pinMode(BUZZER_PIN, OUTPUT);

  digitalWrite(BUZZER_PIN, LOW);
}

void loop() {
  unsigned long now = millis();
  int pirState = digitalRead(PIR_PIN);

  inCooldown = !alarmActive &&
               (now - alarmEndedTime < COOLDOWN_TIME);

  if (!inCooldown && pirState == HIGH) {

    if (!motionPending) {
      motionStartTime = now;
      motionPending = true;
    }

    if (now - motionStartTime >= MOTION_CONFIRM_TIME) {
      lastMotionTime = now;

      if (!alarmActive) {
        alarmActive = true;
        Serial.println("1");
      }
    }

  } else {
    motionPending = false;
  }

  if (alarmActive) {

    if (now - lastMotionTime >= HOLD_TIME) {
      alarmActive = false;
      alarmEndedTime = now;
      Serial.println("0");
    }
  }

  digitalWrite(BUZZER_PIN, alarmActive ? HIGH : LOW);

  delay(20);
}
