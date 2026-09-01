# API HTTP

## Santé et consultation

### `GET /api/health`

Retourne l'état du serveur, de la caméra, du fournisseur IA, la dernière action et l'occupation du pipeline.

### `GET /api/events?limit=20`

Retourne entre 1 et 100 événements, du plus récent au plus ancien.

### `GET /api/rank`

Agrège le nombre d'événements par catégorie.

## Déclenchement

### `POST /api/arduino/event`

Réserve le pipeline et planifie la capture. Retourne HTTP 202 lorsque la demande est acceptée ou HTTP 409 lorsqu'une analyse est déjà active.

### `POST /api/debug/simulate-pir`

Utilise le même traitement depuis le tableau de bord pour une démonstration sans capteur PIR.

### `GET /api/arduino/get_action`

Retourne `waiting`, `processing`, `bio`, `recyclable`, `waste` ou `inconnu`. Une décision finale est consommée à la première lecture.

## Caméra et données

### `GET /camera/stream`

Produit un flux MJPEG depuis la webcam ou relaie celui de l'ESP32-CAM.

### `GET /api/db/download`

Télécharge la base SQLite locale. Cette route doit être protégée avant toute exposition publique.
