#!/usr/bin/env python3
"""
Script pour capturer le token EA manuellement.

INSTRUCTIONS:
1. Va sur https://www.ea.com/ea-sports-fc/ultimate-team/web-app/
2. Connecte-toi normalement
3. Ouvre les DevTools (F12) → Onglet "Network"
4. Filtre par "transfermarket" ou "ut/game"
5. Clique sur une requête et cherche dans les Headers:
   - X-UT-SID: c'est ton token
6. Copie-le et colle-le ici
"""

import json
import time
import os

SESSION_FILE = "active_session.json"

def main():
    print("=" * 60)
    print("   CAPTURE MANUELLE DU TOKEN EA FC")
    print("=" * 60)
    print()
    print("INSTRUCTIONS:")
    print("1. Va sur https://www.ea.com/ea-sports-fc/ultimate-team/web-app/")
    print("2. Connecte-toi et accède au Transfer Market")
    print("3. Ouvre DevTools (F12) → Network")
    print("4. Fais une recherche sur le marché")
    print("5. Clique sur une requête 'transfermarket' ou 'ut/game'")
    print("6. Dans 'Request Headers', trouve 'X-UT-SID'")
    print()
    
    token = input("Colle ton X-UT-SID ici: ").strip()
    
    if not token:
        print("[ERREUR] Token vide!")
        return
    
    if len(token) < 20:
        print("[ERREUR] Token trop court, vérifie que tu as bien copié tout le token")
        return
    
    # Optionnel: nucleus ID
    nucleus_id = input("Nucleus ID (optionnel, appuie Entrée pour ignorer): ").strip() or None
    
    session_data = {
        "x-ut-sid": token,
        "nucleus_id": nucleus_id,
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "timestamp": time.time(),
        "manual_entry": True
    }
    
    with open(SESSION_FILE, "w") as f:
        json.dump(session_data, f, indent=2)
    
    print()
    print(f"[SUCCESS] Token sauvegardé dans {SESSION_FILE}")
    print(f"Token: {token[:15]}...{token[-10:]}")
    print()
    print("Tu peux maintenant lancer le bot avec:")
    print("  DRY_RUN=0 python smart_worker.py")

if __name__ == "__main__":
    main()
