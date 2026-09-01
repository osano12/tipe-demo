# Fournisseurs IA

## Ollama

Ollama conserve les images et l'inférence sur la machine locale. Le modèle par défaut est `llava`. Le serveur Ollama doit fonctionner avant la première analyse.

```bash
ollama serve
ollama pull llava
./run_ubuntu.sh --ai ollama
```

## Google Gemini

Gemini évite l'installation d'un modèle local mais transmet l'image à l'API Google et peut générer des coûts. La clé reste dans `GEMINI_API_KEY`.

```bash
export GEMINI_API_KEY="votre-cle"
./run_ubuntu.sh --ai gemini --model gemini-2.5-flash
```

## Format commun

Les deux fournisseurs produisent un objet, une matière, une catégorie, une confiance et un indicateur d'incertitude. Le pipeline force la catégorie `inconnu` sous le seuil de confiance afin d'éviter un mouvement hasardeux.

Les réponses incorrectes ou les erreurs réseau sont ramenées à un résultat sûr avec une confiance nulle.
