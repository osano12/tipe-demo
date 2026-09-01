# Contribuer

## Installation

Créez un environnement Python 3.11 ou 3.12, installez `requirements.txt`, puis initialisez la base :

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/init_db.py
```

## Validation

Avant une pull request :

```bash
python -m compileall -q run.py server ia scripts tests
python -m unittest discover -s tests -v
```

Ne versionnez jamais de clé API, d'identifiants Wi-Fi, de captures, de datasets, de logs ou de bases SQLite.

## Pull requests

Décrivez le problème traité, la solution, les tests effectués et l'impact matériel éventuel. Gardez les changements ciblés et mettez la documentation à jour lorsque l'API ou le lancement change.
