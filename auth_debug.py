"""
Capture X-UT-SID token - Version DEBUG qui affiche tout
"""

import json
import os
import time
import re
from seleniumwire import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

SESSION_FILE = "active_session.json"
WEB_APP_URL = "https://www.ea.com/ea-sports-fc/ultimate-team/web-app/"


def create_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1280,900")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
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


def is_valid_sid(value):
    """Check if value looks like a valid X-UT-SID (UUID format)"""
    if not value or not isinstance(value, str):
        return False
    # UUID format: 8-4-4-4-12 hex chars
    return bool(re.match(r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$', value.lower()))


def main():
    print("=" * 60)
    print("  EA FC26 Token Capture - DEBUG MODE")
    print("=" * 60)
    print()
    print("Instructions:")
    print("1. Connecte-toi à la Web App EA")
    print("2. Va sur le Transfer Market")
    print("3. Fais une recherche de joueur")
    print("4. Le script capture le token automatiquement")
    print()
    print("Le navigateur restera ouvert jusqu'à ce que tu fasses Ctrl+C")
    print()
    
    driver, user_agent = create_driver()
    
    try:
        driver.get(WEB_APP_URL)
        print(f"[OK] Page ouverte: {WEB_APP_URL}\n")
        
        token = None
        seen_requests = set()
        
        while True:
            time.sleep(1)
            
            for req in driver.requests:
                req_id = id(req)
                if req_id in seen_requests:
                    continue
                seen_requests.add(req_id)
                
                url = req.url
                
                # Only process EA/FUT related requests
                if not any(x in url.lower() for x in ['ea.com', 'fut', 'utas', 'fc26']):
                    continue
                
                # Check for transfermarket or ut/game requests
                if any(x in url.lower() for x in ['transfermarket', 'ut/game', '/trade', '/user']):
                    print(f"\n[REQUEST] {url[:100]}")
                    
                    # Check ALL request headers
                    print("  Request Headers:")
                    for k, v in req.headers.items():
                        k_lower = k.lower()
                        if any(x in k_lower for x in ['sid', 'token', 'auth', 'session', 'ut-']):
                            print(f"    {k}: {v}")
                            if is_valid_sid(v):
                                token = v
                                print(f"\n*** FOUND VALID TOKEN: {token} ***\n")
                    
                    # Check response headers
                    if req.response:
                        print("  Response Headers:")
                        for k, v in req.response.headers.items():
                            k_lower = k.lower()
                            if any(x in k_lower for x in ['sid', 'token', 'auth', 'session', 'ut-']):
                                print(f"    {k}: {v}")
                                if is_valid_sid(v):
                                    token = v
                                    print(f"\n*** FOUND VALID TOKEN: {token} ***\n")
                
                if token:
                    break
            
            if token:
                print("\n" + "=" * 60)
                print("TOKEN CAPTURED SUCCESSFULLY!")
                print("=" * 60)
                print(f"X-UT-SID: {token}")
                
                session_data = {
                    "x-ut-sid": token,
                    "nucleus_id": None,
                    "user_agent": user_agent,
                    "timestamp": time.time()
                }
                
                with open(SESSION_FILE, "w") as f:
                    json.dump(session_data, f, indent=2)
                
                print(f"\nSauvegardé dans {SESSION_FILE}")
                print("\nTu peux maintenant lancer: python smart_worker.py")
                break
    
    except KeyboardInterrupt:
        print("\n\n[INFO] Arrêté par l'utilisateur")
        
        # Show all headers found even if no valid token
        print("\n[DEBUG] Dump de toutes les requêtes EA avec headers intéressants:")
        for req in driver.requests:
            if 'ea.com' in req.url or 'fut' in req.url.lower():
                interesting = False
                for k in req.headers.keys():
                    if any(x in k.lower() for x in ['sid', 'token', 'ut']):
                        interesting = True
                        break
                if interesting:
                    print(f"\n  URL: {req.url[:80]}")
                    for k, v in req.headers.items():
                        if any(x in k.lower() for x in ['sid', 'token', 'ut', 'auth']):
                            print(f"    {k}: {v}")
    
    finally:
        input("\nAppuie sur Entrée pour fermer le navigateur...")
        driver.quit()


if __name__ == "__main__":
    main()
