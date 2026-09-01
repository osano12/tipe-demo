#include <WiFiS3.h>
#include <ArduinoHttpClient.h>
#include <Servo.h>

// WiFi & Serveur
char ssid[] = "VOTRE_WIFI";
char pass[] = "VOTRE_MOT_DE_PASSE";
char serverAddress[] = "192.168.1.100";
int port = 8000;

WiFiClient wifi;
HttpClient client = HttpClient(wifi, serverAddress, port);

// STEPPER 28BYJ-48 (votre séquence qui marche)
const int IN1 = 8, IN2 = 10, IN3 = 9, IN4 = 11;
Servo s1, s2;

// Positions (ajustez)
int POS_BIO = 25;      // ~120°
int POS_RECYC = 150;    // ~240°

void setup() {
  Serial.begin(115200);
  pinMode(2, INPUT); pinMode(4, INPUT_PULLUP);
  
  // Stepper
  pinMode(IN1, OUTPUT); pinMode(IN2, OUTPUT);
  pinMode(IN3, OUTPUT); pinMode(IN4, OUTPUT);
  
  // Servos
  s1.attach(6); s2.attach(7);
  s1.write(0); s2.write(180);
  
  // WiFi
  WiFi.begin(ssid, pass);
  while (WiFi.status() != WL_CONNECTED) { 
    delay(500); Serial.print("."); 
  }
  Serial.println("\n🚀 [SYSTEM] WiFi OK ! Prêt IA...");
}

// Extrait la valeur du champ "action" dans le JSON renvoyé par le serveur.
// Cherche le motif exact "action":"<valeur>" pour éviter les faux positifs.
String parseAction(String json) {
  // Cherche la clé "action" dans le JSON
  int idx = json.indexOf("\"action\":");
  if (idx == -1) return "";
  idx += 9; // avance après "action":
  // Saute les espaces ou guillemets
  while (idx < (int)json.length() && (json[idx] == ' ' || json[idx] == '"')) idx++;
  // Lit jusqu'au prochain '"' ou '}'
  String val = "";
  while (idx < (int)json.length() && json[idx] != '"' && json[idx] != '}') {
    val += json[idx++];
  }
  val.trim();
  return val;
}

void loop() {
  // Anti-rebond : on lit le PIR une seule fois par cycle
  bool pirHigh    = (digitalRead(2) == HIGH);
  bool boutonPush = (digitalRead(4) == LOW);

  if (pirHigh || boutonPush) {
    Serial.println("\n🎯 DÉCLENCHEMENT – Cycle IA");

    // 1. NOTIFIER LE SERVEUR (lancement de l'inférence IA)
    int httpCode = client.post("/api/arduino/event", "application/json", "{}");
    client.responseBody(); // Vide le buffer
    Serial.print("[POST /api/arduino/event] code HTTP : ");
    Serial.println(httpCode);

    // 2. POLLING : on attend le résultat en boucle
    String res = "processing";
    int tentatives = 0;
    const int MAX_TENTATIVES = 30;   // 30 x 1s = 30s max

    while (res == "processing" || res == "waiting" || res == "") {
      delay(1000);

      int getCode = client.get("/api/arduino/get_action");
      String body = client.responseBody();

      Serial.print(".");
      if (tentatives % 5 == 0) {
        // Log complet toutes les 5 tentatives pour ne pas spammer
        Serial.print(" [body=" + body + "] ");
      }

      // Parsing strict : cherche "action":"bio" etc.
      String action = parseAction(body);
      if (action == "bio" || action == "recyclable" || action == "waste") {
        res = action;
      }

      tentatives++;
      if (tentatives >= MAX_TENTATIVES) {
        Serial.println("\n⚠️  Timeout IA (" + String(MAX_TENTATIVES) + "s) – Fallback 'waste'");
        res = "waste";
        break;
      }
    }

    Serial.println("\n🤖 Résultat IA : " + res);

    // 3. MOUVEMENT MÉCANIQUE
    int steps = 0;
    if (res == "bio") {
      steps = POS_BIO;
      Serial.println("🟢 BIO");
      rotateOneWay(steps * 8);
    } else if (res == "recyclable") {
      steps = POS_RECYC;
      Serial.println("🔵 RECYCLABLE");
      rotateOneWay(steps * 8);
    } else {
      Serial.println("🔴 WASTE (tout-venant, pas de rotation)");
    }

    // ÉJECTION via servos
    s1.write(90); s2.write(90);
    delay(1500);
    s1.write(0); s2.write(180);
    delay(500);

    // RETOUR à zéro
    if (steps != 0) {
      rotateOtherWay(steps * 8);
    }

    Serial.println("✅ CYCLE TERMINÉ – Attente 5s anti-rebond...");
    delay(5000); // Anti-rebond : évite de relancer un cycle pendant la phase mécanique
  }
}

// VOS FONCTIONS (qui marchent !)
void rotateOneWay(int totalSteps) {
  for(int i = 0; i < totalSteps; i++) {
    stepA(); stepB(); stepC(); stepD(); stepE(); stepF(); stepG(); stepH();
  }
}

void rotateOtherWay(int totalSteps) {
  for(int i = 0; i < totalSteps; i++) {
    stepH(); stepG(); stepF(); stepE(); stepD(); stepC(); stepB(); stepA();
  }
}

void stepA() { digitalWrite(IN1,HIGH); digitalWrite(IN2,LOW); digitalWrite(IN3,LOW); digitalWrite(IN4,LOW); delayMicroseconds(1200); }
void stepB() { digitalWrite(IN1,HIGH); digitalWrite(IN2,HIGH);digitalWrite(IN3,LOW); digitalWrite(IN4,LOW); delayMicroseconds(1200); }
void stepC() { digitalWrite(IN1,LOW); digitalWrite(IN2,HIGH);digitalWrite(IN3,LOW); digitalWrite(IN4,LOW); delayMicroseconds(1200); }
void stepD() { digitalWrite(IN1,LOW); digitalWrite(IN2,HIGH);digitalWrite(IN3,HIGH);digitalWrite(IN4,LOW); delayMicroseconds(1200); }
void stepE() { digitalWrite(IN1,LOW); digitalWrite(IN2,LOW); digitalWrite(IN3,HIGH);digitalWrite(IN4,LOW); delayMicroseconds(1200); }
void stepF() { digitalWrite(IN1,LOW); digitalWrite(IN2,LOW); digitalWrite(IN3,HIGH);digitalWrite(IN4,HIGH);delayMicroseconds(1200); }
void stepG() { digitalWrite(IN1,LOW); digitalWrite(IN2,LOW); digitalWrite(IN3,LOW); digitalWrite(IN4,HIGH);delayMicroseconds(1200); }
void stepH() { digitalWrite(IN1,HIGH);digitalWrite(IN2,LOW); digitalWrite(IN3,LOW); digitalWrite(IN4,HIGH);delayMicroseconds(1200); }
