#include <Arduino_RouterBridge.h>


String myai_ping() {
  return String("pong");
}


unsigned long myai_uptime_ms() {
  return millis();
}


String myai_mcu_status() {
  return String("ventuno-mcu-ready");
}


void setup() {
  Serial.begin(115200);

  if (!Bridge.begin()) {
    Serial.println("MyAI: RouterBridge kunde inte starta.");
  }

  Bridge.provide_safe("myai_ping", myai_ping);
  Bridge.provide_safe("myai_uptime_ms", myai_uptime_ms);
  Bridge.provide_safe("myai_mcu_status", myai_mcu_status);
}


void loop() {
  // Inga skrivande eller autonoma hårdvaruåtgärder i basfirmware.
}
