"""
Simple EA Token Capture - Wait for user to login and capture X-UT-SID
"""

import json
import time
import re
from seleniumwire import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

SESSION_FILE = "active_session.json"
WEB_APP_URL = "https://www.ea.com/ea-sports-fc/ultimate-team/web-app/"


def main():
    print("=" * 60)
    print("  EA FC26 - Capture de Token")
    print("=" * 60)
    print()
    
    # Setup Chrome
    options = webdriver.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1400,900")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    options.add_argument(f"user-agent={ua}")
    
    seleniumwire_options = {'verify_ssl': False}
    
    print("[1] Lancement du navigateur...")
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options,
        seleniumwire_options=seleniumwire_options
    )
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    print("[2] Ouverture de la Web App EA...")
    driver.get(WEB_APP_URL)
    
    print()
    print("=" * 60)
    print("  INSTRUCTIONS:")
    print("  1. Connecte-toi avec ton compte EA")
    print("  2. Va sur le Transfer Market")
    print("  3. Fais une recherche de joueur")
    print("  4. Le token sera capturé automatiquement")
    print("=" * 60)
    print()
    
    token = None
    nucleus_id = None
    
    # Loop until we find the token or user quits
    try:
        while True:
            time.sleep(2)
            
            # Count requests
            total = len(driver.requests)
            ea_requests = [r for r in driver.requests if 'utas' in r.url or 'futc' in r.url or 'ut/game' in r.url]
            
            print(f"\r[SCAN] {total} requêtes total, {len(ea_requests)} vers EA API...", end="", flush=True)
            
            # Check headers in EA API requests
            for req in ea_requests:
                # Check request headers
                for key, value in req.headers.items():
                    if key.lower() == 'x-ut-sid':
                        if len(value) == 36 and value.count('-') == 4:
                            token = value
                            print(f"\n\n[FOUND] X-UT-SID dans request header: {token}")
                            break
                
                # Check response headers
                if req.response:
                    for key, value in req.response.headers.items():
                        if key.lower() == 'x-ut-sid':
                            if len(value) == 36 and value.count('-') == 4:
                                token = value
                                print(f"\n\n[FOUND] X-UT-SID dans response header: {token}")
                                break
                    
                    # Check nucleus_id
                    nuc = req.response.headers.get('Easw-Session-Data-Nucleus-Id')
                    if nuc:
                        nucleus_id = nuc
                
                if token:
                    break
            
            if token:
                break
                
    except KeyboardInterrupt:
        print("\n\n[INFO] Arrêté par l'utilisateur (Ctrl+C)")
    
    # Save if we found a token
    if token:
        print()
        print("=" * 60)
        print("  SUCCESS! Token capturé!")
        print("=" * 60)
        print(f"  X-UT-SID: {token}")
        print()
        
        session = {
            "x-ut-sid": token,
            "nucleus_id": nucleus_id,
            "user_agent": ua,
            "timestamp": time.time()
        }
        
        with open(SESSION_FILE, 'w') as f:
            json.dump(session, f, indent=2)
        
        print(f"[SAVED] Sauvegardé dans {SESSION_FILE}")
        print()
        print("Tu peux maintenant lancer le bot:")
        print("  python smart_worker.py")
    else:
        print("\n\n[INFO] Aucun token trouvé")
    
    print()
    input("[INFO] Appuie sur Entrée pour fermer le navigateur...")
    driver.quit()


if __name__ == "__main__":
    main()
