from __future__ import annotations

import unittest

from ia.llm_ollama import extract_first_json, validate_ollama_json


class LlmValidationTests(unittest.TestCase):
    """Vérifie la normalisation commune des réponses des fournisseurs IA."""

    def test_extracts_json_from_wrapped_response(self) -> None:
        """Extrait le premier objet JSON même si le modèle ajoute du texte."""
        self.assertEqual(extract_first_json('Résultat: {"objet":"canette"} fin'), '{"objet":"canette"}')

    def test_normalizes_material_and_category(self) -> None:
        """Normalise une matière anglaise et conserve une décision fiable."""
        result = validate_ollama_json({"objet": "bouteille", "matiere": "plastic", "categorie_tri": "recyclable", "confiance": 0.91, "incertain": False})
        self.assertEqual(result["matiere"], "plastique")
        self.assertEqual(result["categorie"], "recyclable")
        self.assertFalse(result["incertain"])

    def test_rejects_low_confidence_decision(self) -> None:
        """Convertit une prédiction trop faible en catégorie inconnue."""
        result = validate_ollama_json({"objet": "objet", "matiere": "metal", "categorie_tri": "recyclable", "confiance": 0.4, "incertain": False})
        self.assertEqual(result["categorie"], "inconnu")
        self.assertTrue(result["incertain"])


if __name__ == "__main__":
    unittest.main()
