# Architecture technique

## Composants

Le système sépare quatre responsabilités : le matériel de détection, la capture, la décision IA et la restitution web.

L'Arduino R4 détecte un objet et appelle `POST /api/arduino/event`. FastAPI réserve une analyse afin d'empêcher deux mouvements concurrents. Une image est récupérée depuis la dernière trame webcam ou depuis `/capture` sur l'ESP32-CAM.

Le pipeline calcule un dHash. Une image proche d'une classification fiable retourne immédiatement le résultat en cache. Sinon, elle est envoyée au fournisseur configuré : Ollama pour une exécution locale ou Gemini pour une exécution distante. Le résultat normalisé appartient à `bio`, `recyclable`, `waste` ou `inconnu`.

La décision et ses métadonnées sont enregistrées dans SQLite. Les exemples fiables enrichissent en parallèle la mémoire et le dataset local. L'Arduino récupère ensuite une fois la décision avec `GET /api/arduino/get_action`.

## Concurrence

- un thread unique conserve la dernière trame webcam ;
- des verrous protègent la trame, l'action et la classification ;
- une seconde demande d'analyse reçoit HTTP 409 pendant un traitement ;
- chaque lecture ou écriture applicative utilise une connexion SQLite courte ;
- le cycle de vie FastAPI libère la caméra et le cache à l'arrêt.

## Données

`db/app.db` contient l'historique public de l'application et est créé depuis `db/schema.sql`. `db/waste_cache.sqlite3` contient le cache perceptuel. `data/captures`, `data/dataset`, les deux bases et la mémoire apprise restent locaux et sont ignorés par Git.

## Choix multiplateforme

`server/main.py` reste la seule implémentation du serveur. `run.py` applique une configuration identique sur Linux et Windows. Les scripts `run_ubuntu.sh` et `run_windows.ps1` ne font qu'utiliser l'interpréteur du virtualenv propre à chaque système.

Cette organisation évite de maintenir deux backends qui pourraient diverger.
