"""
Point d'entree du client batcheck empaquete.

C'est ce fichier que PyInstaller transforme en executable double-cliquable.
Il demarre le serveur local et ouvre le navigateur automatiquement.
"""

import server

if __name__ == "__main__":
    # open_browser=True : l'utilisateur double-clique, sa console s'ouvre toute seule.
    server.main(open_browser=True)
