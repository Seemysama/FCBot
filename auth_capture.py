"""
Capture X-UT-SID token from EA Web App using selenium-wire.
This intercepts ALL network requests without needing DevTools.
Uses your existing Chrome profile so you don't have to log in again!
"""

import json
import os
import time
import getpass
from seleniumwire import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

SESSION_FILE = "active_session.json"
WEB_APP_URL = "https://www.ea.com/ea-sports-fc/ultimate-team/web-app/"

# Token patterns to look for in headers
TOKEN_PATTERNS = ["x-ut-sid", "X-UT-SID", "X-Ut-Sid"]

# Wait up to 10 minutes
MAX_WAIT_SECONDS = 600

# Chemin vers le profil Chrome de l'utilisateur (macOS)
USER = getpass.getuser()
CHROME_PROFILE_PATH = f"/Users/{USER}/Library/Application Support/Google/Chrome"


def create_driver():
    """Create a selenium-wire Chrome driver with fresh profile."""
    options = webdriver.ChromeOptions()
    
    # Utiliser un profil temporaire pour éviter les conflits
    # Tu devras te connecter manuellement à EA
    import tempfile
    temp_profile = tempfile.mkdtemp(prefix="chrome_ea_")
    options.add_argument(f"--user-data-dir={temp_profile}")
    
    # Anti-detection
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1280,900")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    
    # User agent
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    
    # Selenium-wire options to intercept HTTPS
    seleniumwire_options = {
        'verify_ssl': False,
        'suppress_connection_errors': True,
    }
    
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options,
        seleniumwire_options=seleniumwire_options
    )
    
    # Remove webdriver flag
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    return driver, ua


def find_token_in_requests(driver):
    """Scan all intercepted requests for X-UT-SID token."""
    token = None
    nucleus_id = None
    
    for request in driver.requests:
        # PRIORITÉ: requêtes vers l'API UT (transfermarket, etc.)
        is_ut_api = "utas.mob" in request.url or "futc-ext" in request.url
        is_ea = "ea.com" in request.url
        
        if not is_ut_api and not is_ea:
            continue
        
        # Log les requêtes UT pour debug
        if is_ut_api:
            print(f"[DEBUG] UT API request: {request.url[:80]}...")
            
        # Check request headers
        for pattern in TOKEN_PATTERNS:
            if pattern in request.headers:
                candidate = request.headers[pattern]
                # Accepter UUID (36 chars) OU JWT (commence par eyJ)
                if candidate:
                    is_uuid = len(candidate) == 36 and candidate.count('-') == 4
                    is_jwt = candidate.startswith('eyJ')
                    if is_uuid or (is_ut_api and len(candidate) > 20):
                        token = candidate
                        print(f"[FOUND] Token in request headers: {token[:50]}...")
                        break
        
        # Check response headers if we have a response
        if request.response:
            for pattern in TOKEN_PATTERNS:
                if pattern in request.response.headers:
                    candidate = request.response.headers[pattern]
                    if candidate:
                        is_uuid = len(candidate) == 36 and candidate.count('-') == 4
                        if is_uuid or (is_ut_api and len(candidate) > 20):
                            token = candidate
                            print(f"[FOUND] Token in response headers: {token[:50]}...")
                            break
            
            # Check for nucleus ID
            if "easw-session-data-nucleus-id" in request.response.headers:
                nucleus_id = request.response.headers["easw-session-data-nucleus-id"]
        
        # Si on a trouvé un UUID, c'est le bon, on arrête
        if token and len(token) == 36:
            break
    
    return token, nucleus_id


def find_token_in_url(driver):
    """Some EA requests include the SID in URL params."""
    for request in driver.requests:
        url = request.url
        if "sid=" in url.lower():
            # Extract sid from URL
            import urllib.parse
            parsed = urllib.parse.urlparse(url)
            params = urllib.parse.parse_qs(parsed.query)
            if 'sid' in params:
                return params['sid'][0], None
    return None, None


def main():
    print("=" * 50)
    print("  EA FC26 Token Capture (selenium-wire)")
    print("=" * 50)
    print()
    print("[INFO] Lancement du navigateur...")
    print("[INFO] Connecte-toi à la Web App et va sur le Transfer Market")
    print("[INFO] Le script capture automatiquement le token X-UT-SID")
    print()
    
    driver, user_agent = create_driver()
    
    try:
        # Navigate to Web App
        driver.get(WEB_APP_URL)
        print(f"[INFO] Page ouverte: {WEB_APP_URL}")
        print("[INFO] En attente de connexion et navigation vers Transfer Market...")
        print()
        
        token = None
        nucleus_id = None
        start_time = time.time()
        max_wait = 600  # 10 minutes au lieu de 5
        
        print("[INFO] Prends ton temps pour te connecter...")
        print("[INFO] Navigue vers le Transfer Market et fais une recherche...")
        print("[INFO] Le token sera capturé automatiquement\n")
        
        while not token and (time.time() - start_time) < max_wait:
            time.sleep(3)
            
            # Clear old requests to avoid memory buildup
            requests_count = len(driver.requests)
            elapsed = int(time.time() - start_time)
            print(f"[SCAN] {requests_count} requêtes interceptées... ({elapsed}s)", end="\r")
            
            # Look for token in requests
            token, nucleus_id = find_token_in_requests(driver)
            
            if not token:
                # Try URL params
                token, nucleus_id = find_token_in_url(driver)
            
            # Also check localStorage for UUID-formatted tokens
            if not token:
                try:
                    stored = driver.execute_script("""
                        var result = {};
                        for (var i = 0; i < localStorage.length; i++) {
                            var key = localStorage.key(i);
                            result[key] = localStorage.getItem(key);
                        }
                        // Also check sessionStorage
                        for (var i = 0; i < sessionStorage.length; i++) {
                            var key = sessionStorage.key(i);
                            result['session_' + key] = sessionStorage.getItem(key);
                        }
                        return result;
                    """)
                    if stored:
                        for key, value in stored.items():
                            # Look for UUID pattern (typical X-UT-SID format: 8-4-4-4-12)
                            if value and isinstance(value, str) and len(value) == 36 and value.count('-') == 4:
                                # Verify it's a valid UUID format
                                import re
                                if re.match(r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$', value.lower()):
                                    token = value
                                    print(f"\n[FOUND] Token from storage ({key}): {token}")
                                    break
                except Exception as e:
                    pass
            
            # Also look for the token in any JSON response bodies
            if not token:
                for request in driver.requests[-50:]:  # Check recent requests
                    if request.response and request.response.body:
                        try:
                            body = request.response.body.decode('utf-8', errors='ignore')
                            # Look for sid pattern in JSON
                            import re
                            matches = re.findall(r'"sid"\s*:\s*"([a-f0-9-]{36})"', body, re.IGNORECASE)
                            if matches:
                                token = matches[0]
                                print(f"\n[FOUND] Token in response body: {token}")
                                break
                        except:
                            pass
        
        if token and len(token) == 36 and token.count('-') == 4:
            print(f"\n\n{'='*50}")
            print("[SUCCESS] TOKEN CAPTURED!")
            print(f"{'='*50}")
            print(f"X-UT-SID: {token}")
            
            # Save to file
            session_data = {
                "x-ut-sid": token,
                "nucleus_id": nucleus_id,
                "user_agent": user_agent,
                "timestamp": time.time()
            }
            
            with open(SESSION_FILE, "w") as f:
                json.dump(session_data, f, indent=2)
            
            print(f"\n[SAVED] Token sauvegardé dans {SESSION_FILE}")
            print("\nTu peux maintenant lancer le bot avec:")
            print("  python smart_worker.py")
            
        else:
            print("\n[TIMEOUT] Token non trouvé après 5 minutes")
            print("Assure-toi d'être connecté et d'avoir navigué vers le Transfer Market")
            
            # Show debug info - all headers from EA requests
            print("\n[DEBUG] Headers des requêtes EA:")
            for req in driver.requests:
                if "ea.com" in req.url or "futc" in req.url:
                    print(f"\n  URL: {req.url[:100]}")
                    print(f"  Request Headers:")
                    for k, v in req.headers.items():
                        if "sid" in k.lower() or "token" in k.lower() or "auth" in k.lower() or "ut" in k.lower():
                            print(f"    {k}: {v[:50] if len(str(v)) > 50 else v}")
                    if req.response:
                        print(f"  Response Headers:")
                        for k, v in req.response.headers.items():
                            if "sid" in k.lower() or "token" in k.lower() or "auth" in k.lower() or "ut" in k.lower():
                                print(f"    {k}: {v[:50] if len(str(v)) > 50 else v}")
    
    except KeyboardInterrupt:
        print("\n[INFO] Annulé par l'utilisateur")
    
    finally:
        print("\n[INFO] Appuie sur Entrée pour fermer le navigateur...")
        try:
            input()
        except:
            pass
        driver.quit()


if __name__ == "__main__":
    main()
