"""
Script simple pour mettre à jour le token manuellement.
Usage: python update_token.py <TOKEN>
"""

import json
import sys
import time

SESSION_FILE = "active_session.json"

def update_token(token):
    session = {
        "x-ut-sid": token,
        "nucleus_id": None,
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "timestamp": time.time()
    }
    
    with open(SESSION_FILE, 'w') as f:
        json.dump(session, f, indent=2)
    
    print(f"[✓] Token mis à jour: {token[:20]}...")
    print(f"[✓] Fichier: {SESSION_FILE}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python update_token.py <X-UT-SID>")
        print("\nPour récupérer le token:")
        print("1. Ouvre la Web App FC dans Chrome")
        print("2. F12 → Network")
        print("3. Va sur Transfer Market")
        print("4. Clique sur une requête 'transfermarket'")
        print("5. Copie la valeur de X-UT-SID dans les Headers")
        sys.exit(1)
    
    token = sys.argv[1]
    update_token(token)
