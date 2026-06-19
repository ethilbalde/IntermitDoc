"""
Point d'entrée du PDF Classifier.
"""
import sys
from pathlib import Path

# Assurer que le dossier du script est dans le path Python
sys.path.insert(0, str(Path(__file__).parent))


def main():
    try:
        from ui import FenetrePrincipale
        from config import logger, LOG_FILE
    except ImportError as e:
        print(f"Erreur d'importation : {e}")
        print("Vérifiez que toutes les dépendances sont installées :")
        print("  pip install -r requirements.txt")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info(f"[Démarrage] IntermitDoc  —  log : {LOG_FILE}")

    app = FenetrePrincipale()
    app.mainloop()

    logger.info("[Arrêt] IntermitDoc fermé")


if __name__ == "__main__":
    main()
