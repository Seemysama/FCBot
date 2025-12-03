"""
Capture X-UT-SID token from EA Web App.
ATTEND une vraie requête vers /transfermarket avant de capturer le token.
"""

import json
import os
import time
import getpass
import re
from seleniumwire import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

SESSION_FILE = "active_session.json"
WEB_APP_URL = "https://www.ea.com/ea-sports-fc/ultimate-team/web-app/"

# Chemin vers le profil Chrome
USER = getpass.getuser()
CHROME_PROFILE_PATH = f"/Users/{USER}/Library/Application Support/Google/Chrome"


def create_driver():
    """Create Chrome driver - profil vierge pour éviter les conflits."""
    options = webdriver.ChromeOptions()
    
    # Anti-detection
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1400,900")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    
    ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    options.add_argument(f"user-agent={ua}")
    
    seleniumwire_options = {
        'verify_ssl': False,
        'suppress_connection_errors': True,
    }
    
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options,
        seleniumwire_options=seleniumwire_options
    )
    
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    return driver, ua


def find_market_request_with_token(driver):
    """
    Cherche UNIQUEMENT les requêtes vers /transfermarket ou /ut/game/fc26
    et extrait le X-UT-SID de leurs headers.
    """
    for request in driver.requests:
        url = request.url.lower()
        
        # On cherche spécifiquement les requêtes vers l'API du marché
        if 'transfermarket' in url or '/ut/game/fc' in url or 'utas.' in url:
            # Cherche X-UT-SID dans les headers de la requête
            for header_name in ['X-UT-SID', 'x-ut-sid', 'X-Ut-Sid']:
                if header_name in request.headers:
                    token = request.headers[header_name]
                    # Vérifie que c'est un UUID valide
                    if token and len(token) == 36 and token.count('-') == 4:
                        if re.match(r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$', token.lower()):
                            return token, url
    return None, None


def main():
    print("=" * 60)
    print("  EA FC26 Token Capture v2")
    print("  (Attend une vraie requête vers le Transfer Market)")
    print("=" * 60)
    print()
    print("[INFO] Chrome va s'ouvrir - connecte-toi à EA")
    print("[INFO] Puis va sur Transfer Market et FAIS UNE RECHERCHE")
    print("[INFO] Le script ne fermera PAS tant que tu n'as pas fait ça")
    print()
    
    driver, user_agent = create_driver()
    
    try:
        driver.get(WEB_APP_URL)
        print(f"[OK] Page ouverte: {WEB_APP_URL}")
        print()
        print("━" * 60)
        print("  INSTRUCTIONS:")
        print("  1. Connecte-toi à ton compte EA")
        print("  2. Va sur 'Transfer Market' (Marché des Transferts)")
        print("  3. Fais une RECHERCHE de joueur (n'importe lequel)")
        print("  4. Le token sera capturé automatiquement")
        print("━" * 60)
        print()
        
        token = None
        start_time = time.time()
        max_wait = 600  # 10 minutes
        last_count = 0
        
        while not token and (time.time() - start_time) < max_wait:
            time.sleep(2)
            
            current_count = len(driver.requests)
            elapsed = int(time.time() - start_time)
            
            # Affiche le statut
            if current_count != last_count:
                print(f"[SCAN] {current_count} requêtes... (attend requête transfermarket)", end="\r")
                last_count = current_count
            
            # Cherche le token UNIQUEMENT dans les requêtes vers le marché
            token, found_url = find_market_request_with_token(driver)
            
            if token:
                print(f"\n\n{'='*60}")
                print("[SUCCESS] TOKEN TROUVÉ!")
                print(f"{'='*60}")
                print(f"X-UT-SID: {token}")
                print(f"Trouvé dans: {found_url[:60]}...")
                
                # Sauvegarde
                session_data = {
                    "x-ut-sid": token,
                    "nucleus_id": None,
                    "user_agent": user_agent,
                    "timestamp": time.time()
                }
                
                with open(SESSION_FILE, "w") as f:
                    json.dump(session_data, f, indent=2)
                
                print(f"\n[SAVED] Token sauvegardé dans {SESSION_FILE}")
                print("\n" + "="*60)
                print("Tu peux maintenant lancer le bot avec:")
                print("  DRY_RUN=0 EA_VALIDATION_SKIP=1 python smart_worker.py")
                print("="*60)
                break
        
        if not token:
            print("\n[TIMEOUT] Pas de token trouvé après 10 minutes")
            print("As-tu bien fait une recherche sur le Transfer Market?")
            
            # Debug: montre les URLs des requêtes EA
            print("\n[DEBUG] Requêtes EA interceptées:")
            ea_requests = [r for r in driver.requests if 'ea.com' in r.url or 'futc' in r.url]
            for req in ea_requests[-10:]:
                print(f"  {req.url[:80]}")
    
    except KeyboardInterrupt:
        print("\n[INFO] Annulé par l'utilisateur (Ctrl+C)")
    
    except Exception as e:
        print(f"\n[ERROR] {e}")
    
    finally:
        print("\n[INFO] Fermeture dans 3 secondes...")
        time.sleep(3)
        driver.quit()
        print("[INFO] Chrome fermé.")


if __name__ == "__main__":
    main()
