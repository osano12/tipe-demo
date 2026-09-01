#include "esp_camera.h"
#include <WiFi.h>
#include "esp_http_server.h"
#include "esp_log.h"
#include "ESPmDNS.h"

// AJOUT IMPORTANT : Include pour LEDC
#include <driver/ledc.h>

#define FLASH_LED_PIN 4
#define FLASH_CHANNEL 7

// =========================
// Configuration utilisateur
// =========================
const char* WIFI_SSID = "VOTRE_WIFI";
const char* WIFI_PASSWORD = "VOTRE_MOT_DE_PASSE";

// =========================
// AI Thinker ESP32-CAM pins
// =========================
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27

#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

static httpd_handle_t camera_httpd = NULL;
static uint8_t flashLevel = 0;

void setFlashLevel(uint8_t level) {
  flashLevel = level;
  ledcWrite(FLASH_CHANNEL, flashLevel);
}

bool initCamera() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  if (psramFound()) {
    config.frame_size = FRAMESIZE_SVGA;
    config.jpeg_quality = 12;
    config.fb_count = 2;
    config.grab_mode = CAMERA_GRAB_LATEST;
  } else {
    config.frame_size = FRAMESIZE_VGA;
    config.jpeg_quality = 14;
    config.fb_count = 1;
    config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("[CAM] init failed: 0x%x\n", err);
    return false;
  }

  sensor_t* sensor = esp_camera_sensor_get();
  if (sensor != nullptr) {
    sensor->set_framesize(sensor, FRAMESIZE_SVGA);
    sensor->set_quality(sensor, 12);
  }

  Serial.println("[CAM] OK!");
  return true;
}

void initFlash() {
  ledc_timer_config_t ledc_timer = {
    .duty_resolution = LEDC_TIMER_8_BIT,
    .freq_hz = 5000,
    .speed_mode = LEDC_LOW_SPEED_MODE,
    .timer_num = static_cast<ledc_timer_t>(FLASH_CHANNEL),
    .clk_cfg = LEDC_AUTO_CLK
  };
  ledc_timer_config(&ledc_timer);

  ledc_channel_config_t ledc_channel = {
    .channel    = static_cast<ledc_channel_t>(FLASH_CHANNEL),
    .duty       = 0,
    .gpio_num   = FLASH_LED_PIN,
    .speed_mode = LEDC_LOW_SPEED_MODE,
    .hpoint     = 0,
    .timer_sel  = static_cast<ledc_timer_t>(FLASH_CHANNEL)
  };
  ledc_channel_config(&ledc_channel);

  Serial.println("[FLASH] ready");
}

esp_err_t status_handler(httpd_req_t* req) {
  String payload = "{\"status\":\"ready\",\"ip\":\"" + WiFi.localIP().toString() +
                   "\",\"flash_level\":" + String(flashLevel) + "}";
  httpd_resp_set_type(req, "application/json");
  return httpd_resp_send(req, payload.c_str(), payload.length());
}

esp_err_t root_handler(httpd_req_t* req) {
  const char* msg = "ESP32-CAM ready. Endpoints: /status /capture /stream /flash/on /flash/off /flash?level=0..255";
  httpd_resp_set_type(req, "text/plain");
  return httpd_resp_send(req, msg, HTTPD_RESP_USE_STRLEN);
}

void connectWifiBlocking() {
  WiFi.mode(WIFI_STA);
  WiFi.setHostname("esp32-cam");
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.println("[WIFI] connecting...");
  unsigned long started = millis();
  while (WiFi.status() != WL_CONNECTED && (millis() - started) < 15000) {
    delay(300);
    Serial.print(".");
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("[WIFI] connected, IP=%s\n", WiFi.localIP().toString().c_str());
    if (MDNS.begin("esp32-cam")) {
      MDNS.addService("http", "tcp", 80);
      Serial.println("[MDNS] esp32-cam.local ready");
    } else {
      Serial.println("[MDNS] init failed");
    }
  } else {
    Serial.println("[WIFI] initial connect timeout");
  }
}

esp_err_t flash_off_handler(httpd_req_t* req) {
  setFlashLevel(0);
  httpd_resp_set_type(req, "application/json");
  return httpd_resp_send(req, "{\"ok\":true,\"flash\":\"off\",\"level\":0}", HTTPD_RESP_USE_STRLEN);
}

esp_err_t flash_level_handler(httpd_req_t* req) {
  char query[64];
  uint8_t level = flashLevel;

  if (httpd_req_get_url_query_str(req, query, sizeof(query)) == ESP_OK) {
    char param[8];
    if (httpd_query_key_value(query, "level", param, sizeof(param)) == ESP_OK) {
      int requested = atoi(param);
      if (requested < 0) requested = 0;
      if (requested > 255) requested = 255;
      level = static_cast<uint8_t>(requested);
      setFlashLevel(level);
    }
  }

  String payload = "{\"ok\":true,\"level\":" + String(level) + "}";
  httpd_resp_set_type(req, "application/json");
  return httpd_resp_send(req, payload.c_str(), payload.length());
}

esp_err_t capture_handler(httpd_req_t* req) {
  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) {
    httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "camera_error");
    return ESP_FAIL;
  }

  httpd_resp_set_type(req, "image/jpeg");
  httpd_resp_set_hdr(req, "Cache-Control", "no-store, no-cache, must-revalidate, max-age=0");
  esp_err_t res = httpd_resp_send(req, (const char*)fb->buf, fb->len);
  esp_camera_fb_return(fb);
  return res;
}

esp_err_t stream_handler(httpd_req_t* req) {
  static const char* STREAM_CONTENT_TYPE = "multipart/x-mixed-replace;boundary=frame";
  static const char* BOUNDARY = "\r\n--frame\r\n";
  static const char* PART = "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

  httpd_resp_set_type(req, STREAM_CONTENT_TYPE);
  httpd_resp_set_hdr(req, "Cache-Control", "no-store, no-cache, must-revalidate, max-age=0");
  httpd_resp_set_hdr(req, "Pragma", "no-cache");

  while (true) {
    camera_fb_t* fb = esp_camera_fb_get();
    if (!fb) {
      Serial.println("[STREAM] frame fail");
      return ESP_FAIL;
    }

    if (httpd_resp_send_chunk(req, BOUNDARY, strlen(BOUNDARY)) != ESP_OK) {
      esp_camera_fb_return(fb);
      break;
    }

    char header[64];
    size_t hlen = snprintf(header, sizeof(header), PART, fb->len);
    if (httpd_resp_send_chunk(req, header, hlen) != ESP_OK) {
      esp_camera_fb_return(fb);
      break;
    }

    if (httpd_resp_send_chunk(req, (const char*)fb->buf, fb->len) != ESP_OK) {
      esp_camera_fb_return(fb);
      break;
    }

    esp_camera_fb_return(fb);
    delay(35);
  }

  return ESP_OK;
}

void startCameraServer() {
  httpd_config_t config = HTTPD_DEFAULT_CONFIG();
  config.server_port = 80;

  httpd_uri_t root_uri = {
    .uri       = "/",
    .method    = HTTP_GET,
    .handler   = root_handler,
    .user_ctx  = NULL
  };
  
  httpd_uri_t status_uri = {
    .uri       = "/status",
    .method    = HTTP_GET,
    .handler   = status_handler,
    .user_ctx  = NULL
  };
  
  httpd_uri_t capture_uri = {
    .uri       = "/capture",
    .method    = HTTP_GET,
    .handler   = capture_handler,
    .user_ctx  = NULL
  };
  
  httpd_uri_t stream_uri = {
    .uri       = "/stream",
    .method    = HTTP_GET,
    .handler   = stream_handler,
    .user_ctx  = NULL
  };
  
  httpd_uri_t flash_off_uri = {
    .uri       = "/flash/off",
    .method    = HTTP_GET,
    .handler   = flash_off_handler,
    .user_ctx  = NULL
  };
  
  httpd_uri_t flash_uri = {
    .uri       = "/flash",
    .method    = HTTP_GET,
    .handler   = flash_level_handler,
    .user_ctx  = NULL
  };

  if (httpd_start(&camera_httpd, &config) == ESP_OK) {
    httpd_register_uri_handler(camera_httpd, &root_uri);
    httpd_register_uri_handler(camera_httpd, &status_uri);
    httpd_register_uri_handler(camera_httpd, &capture_uri);
    httpd_register_uri_handler(camera_httpd, &stream_uri);
    httpd_register_uri_handler(camera_httpd, &flash_off_uri);
    httpd_register_uri_handler(camera_httpd, &flash_uri);
    
    Serial.println("[HTTP] Server ready!");
  }
}

void setup() {
  Serial.begin(115200);
  Serial.println("[BOOT] Starting ESP32-CAM...");
  
  // Initialisation Flash AVANT la caméra
  initFlash();

  if (!initCamera()) {
    Serial.println("[BOOT] Camera init failed!");
    return;
  }

  connectWifiBlocking();
  startCameraServer();
  
  Serial.println("[BOOT] Setup complete!");
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[WIFI] Reconnecting...");
    delay(5000);
  }
  delay(2000);
}
