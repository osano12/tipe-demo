# Smart Waste Sorter — TIPE

[![CI](https://github.com/osano12/tipe-demo/actions/workflows/ci.yml/badge.svg)](https://github.com/osano12/tipe-demo/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12-3776AB)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

Prototype de poubelle intelligente capable de capturer un déchet, de le classer et de transmettre une décision de tri à une Arduino R4 WiFi. L'inférence fonctionne au choix avec Ollama en local ou Google Gemini.

## Points techniques

- API FastAPI et tableau de bord responsive en temps réel
- capture par webcam USB ou ESP32-CAM
- fournisseurs IA interchangeables : Ollama/LLaVA et Gemini Vision
- cache perceptuel dHash pour réduire la latence et le coût des appels IA
- historique SQLite, statistiques et constitution automatique d'un dataset local
- verrouillage des analyses concurrentes et cycle de vie propre des ressources
- firmwares Arduino R4 WiFi et ESP32-CAM inclus
- lancement natif Ubuntu et Windows, sans Docker
- tests automatisés sur Python 3.11 et 3.12 avec GitHub Actions

## Architecture

```text
Capteur PIR
    |
Arduino R4 WiFi -- HTTP --> FastAPI <-- MJPEG/JPEG -- Webcam ou ESP32-CAM
                              |
                              +--> cache perceptuel dHash
                              |
                              +--> Ollama local ou Gemini API
                              |
                              +--> SQLite + dataset local
                              |
                              +--> dashboard + décision moteur
```

Une explication détaillée est disponible dans [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Installation Ubuntu

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/init_db.py
chmod +x run_ubuntu.sh
```

## Installation Windows

Dans PowerShell avec Python 3.11 ou 3.12 installé :

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe scripts\init_db.py
```

## Configuration

Copiez `.env.example` vers `.env`, puis adaptez uniquement les valeurs nécessaires. `.env` n'est jamais versionné.

```bash
cp .env.example .env
```

| Variable | Valeur par défaut | Rôle |
|---|---|---|
| `AI_PROVIDER` | `ollama` | `ollama` ou `gemini` |
| `AI_MODEL` | `llava` | modèle utilisé par le fournisseur |
| `GEMINI_API_KEY` | vide | clé requise pour Gemini |
| `CAMERA_MODE` | `webcam` | `webcam` ou `esp32` |
| `CAMERA_INDEX` | `0` | index OpenCV de la webcam |
| `ESP32_CAPTURE_URL` | URL mDNS | endpoint JPEG de l'ESP32-CAM |
| `LOG_LEVEL` | `INFO` | niveau de journalisation |

## Lancement

Ubuntu avec Ollama :

```bash
ollama serve
ollama pull llava
./run_ubuntu.sh --ai ollama --camera webcam
```

Windows avec Ollama :

```powershell
ollama pull llava
.\run_windows.ps1 --ai ollama --camera webcam
```

Ubuntu avec Gemini :

```bash
export GEMINI_API_KEY="votre-cle"
./run_ubuntu.sh --ai gemini --model gemini-2.5-flash --camera webcam
```

Windows avec Gemini :

```powershell
$env:GEMINI_API_KEY="votre-cle"
.\run_windows.ps1 --ai gemini --model gemini-2.5-flash --camera webcam
```

Pour une ESP32-CAM, remplacez `--camera webcam` par :

```text
--camera esp32 --esp32-url http://esp32-cam.local/capture
```

Ouvrez ensuite [http://127.0.0.1:8000](http://127.0.0.1:8000). Toutes les options sont visibles avec `python run.py --help`.

## API

| Méthode | Route | Description |
|---|---|---|
| `GET` | `/api/health` | état de la caméra, de l'IA et du traitement |
| `GET` | `/api/events` | événements récents |
| `GET` | `/api/rank` | statistiques par catégorie |
| `POST` | `/api/arduino/event` | déclenche une analyse matérielle |
| `POST` | `/api/debug/simulate-pir` | déclenche une analyse manuelle |
| `GET` | `/api/arduino/get_action` | retourne la décision à l'Arduino |
| `GET` | `/camera/stream` | diffuse ou relaie le flux MJPEG |

La documentation interactive est disponible sur `/docs` pendant l'exécution.

## Tests

```bash
.venv/bin/python -m compileall -q run.py server ia scripts tests
.venv/bin/python -m unittest discover -s tests -v
```

## Matériel

- Arduino UNO R4 WiFi
- ESP32-CAM AI Thinker ou webcam USB
- capteur PIR
- servomoteurs et moteur pas-à-pas selon le montage

Les identifiants réseau des firmwares sont volontairement remplacés par des valeurs d'exemple. Configurez-les localement avant le téléversement.

Pour vérifier une ESP32-CAM avant de lancer le serveur :

```bash
.venv/bin/python scripts/check_esp32.py http://esp32-cam.local/capture --output /tmp/capture.jpg
```

## Limites

Ce dépôt est un prototype de démonstration. Avant un déploiement public, ajoutez une authentification, HTTPS et une politique de conservation des images. La qualité du tri dépend du cadrage, de l'éclairage et du modèle vision choisi.

## Licence

Distribué sous licence [MIT](LICENSE).
