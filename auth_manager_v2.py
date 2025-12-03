"""Robust auth capture for EA Web App.

Captures X-UT-SID and nucleus id from Chrome DevTools performance logs,
falls back to Selenium cookies, validates the token with a lightweight
API call, and only persists a session file when validation succeeds.
"""

import json
import os
import time
from typing import Dict, Optional

import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from webdriver_manager.chrome import ChromeDriverManager

SESSION_FILE = "active_session.json"
# Default to the latest EA FC Web App URL; overridable via EA_WEB_APP_URL.
WEB_APP_URL = os.environ.get(
    "EA_WEB_APP_URL",
    "https://www.ea.com/ea-sports-fc/ultimate-team/web-app/",
)

# Validation endpoints: env override supports comma-separated list. Default to FC26 hosts.
_env_urls = os.environ.get("EA_VALIDATION_URL") or os.environ.get("EA_VALIDATION_URLS")
if _env_urls:
    VALIDATION_URLS = [u.strip() for u in _env_urls.split(",") if u.strip()]
else:
    VALIDATION_URLS = [
        "https://utas.mob.v5.prd.futc-ext.gcp.ea.com/ut/auth",  # FC26 primary
        "https://fcas.mob.v5.prd.futc-ext.gcp.ea.com/fc/auth",  # FC26 alternate
    ]

# Tuning knobs
VALIDATION_TIMEOUT = float(os.environ.get("EA_VALIDATION_TIMEOUT", 8))
VALIDATION_SKIP = os.environ.get("EA_VALIDATION_SKIP", "0") == "1"

MAX_CAPTURE_SECONDS = 300


class RobustAuth:
    def __init__(self):
        self.driver = None
        self.session_data: Dict[str, Optional[str]] = {
            "x-ut-sid": None,
            "nucleus_id": None,
            "user_agent": None,
        }

    def start_browser(self):
        caps = DesiredCapabilities.CHROME
        caps["goog:loggingPrefs"] = {"performance": "ALL"}

        opts = webdriver.ChromeOptions()
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_argument("--window-size=1280,800")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])

        ua = os.environ.get(
            "EA_BROWSER_UA",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        opts.add_argument(f"user-agent={ua}")
        self.session_data["user_agent"] = ua

        # Merge capabilities
        for k, v in caps.items():
            opts.set_capability(k, v)

        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()), options=opts
        )
        # Hide webdriver flag
        self.driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

    def _extract_from_headers(self, headers: Dict[str, str]):
        headers = {k.lower(): v for k, v in headers.items()}

        if "x-ut-sid" in headers:
            self.session_data["x-ut-sid"] = headers["x-ut-sid"]

        # Some endpoints expose nucleus id in custom header
        if "easw-session-data-nucleus-id" in headers:
            self.session_data["nucleus_id"] = headers["easw-session-data-nucleus-id"]

        # Parse Set-Cookie if present
        set_cookie = headers.get("set-cookie")
        if isinstance(set_cookie, str) and "x-ut-sid" in set_cookie.lower():
            parts = set_cookie.split(";")
            for p in parts:
                if "x-ut-sid" in p.lower():
                    _, value = p.split("=", 1)
                    self.session_data["x-ut-sid"] = value.strip()

    def extract_from_logs(self, logs):
        for entry in logs:
            try:
                msg = json.loads(entry["message"])["message"]
                params = msg.get("params", {})
                method = msg.get("method")

                if method == "Network.requestWillBeSent":
                    headers = params.get("request", {}).get("headers", {})
                    self._extract_from_headers(headers)
                elif method == "Network.responseReceived":
                    headers = params.get("response", {}).get("headers", {})
                    self._extract_from_headers(headers)
            except Exception:
                continue

    def fallback_cookie_scan(self):
        try:
            cookies = self.driver.get_cookies()
        except Exception:
            return

        for c in cookies:
            if c.get("name", "").lower() == "x-ut-sid":
                self.session_data["x-ut-sid"] = c.get("value")
            if c.get("name", "").lower() == "easw_session_data_nucleus_id":
                self.session_data["nucleus_id"] = c.get("value")

    def scan_local_storage(self):
        """Scan localStorage and sessionStorage for token."""
        try:
            # Check localStorage
            local_storage = self.driver.execute_script(
                "return JSON.stringify(localStorage);"
            )
            if local_storage:
                data = json.loads(local_storage)
                for key, value in data.items():
                    if "sid" in key.lower() or "token" in key.lower():
                        print(f"[SCAN] localStorage key: {key}")
                        if isinstance(value, str) and len(value) > 20:
                            # Could be a token
                            if not self.session_data.get("x-ut-sid"):
                                self.session_data["x-ut-sid"] = value
                                print(f"[FOUND] Potential token from localStorage: {value[:20]}...")

            # Check sessionStorage
            session_storage = self.driver.execute_script(
                "return JSON.stringify(sessionStorage);"
            )
            if session_storage:
                data = json.loads(session_storage)
                for key, value in data.items():
                    if "sid" in key.lower() or "token" in key.lower() or "ut" in key.lower():
                        print(f"[SCAN] sessionStorage key: {key}")

            # Try to find EASW session data in localStorage
            easw_data = self.driver.execute_script("""
                try {
                    var keys = Object.keys(localStorage);
                    for (var i = 0; i < keys.length; i++) {
                        var k = keys[i];
                        var v = localStorage.getItem(k);
                        if (v && (v.indexOf('sid') > -1 || v.indexOf('nucleus') > -1)) {
                            return {key: k, value: v};
                        }
                    }
                } catch(e) {}
                return null;
            """)
            if easw_data:
                print(f"[SCAN] Found EASW-related data: {easw_data}")

        except Exception as e:
            print(f"[WARN] localStorage scan failed: {e}")

    def scan_network_via_js(self):
        """Intercept fetch/XHR to capture tokens."""
        try:
            # Inject interceptor if not already done
            self.driver.execute_script("""
                if (!window.__tokenCapture) {
                    window.__tokenCapture = [];
                    var origFetch = window.fetch;
                    window.fetch = function() {
                        var args = arguments;
                        return origFetch.apply(this, args).then(function(response) {
                            var headers = {};
                            response.headers.forEach(function(v, k) { headers[k] = v; });
                            window.__tokenCapture.push({url: args[0], headers: headers});
                            return response;
                        });
                    };
                }
            """)
            
            # Retrieve captured data
            captured = self.driver.execute_script("return window.__tokenCapture || [];")
            for item in captured:
                headers = item.get("headers", {})
                self._extract_from_headers(headers)
                if self.session_data.get("x-ut-sid"):
                    print(f"[FOUND] Token captured from fetch: {item.get('url', 'unknown')[:50]}")
                    
        except Exception as e:
            pass

    def validate_and_save(self) -> bool:
        token = self.session_data.get("x-ut-sid")
        if not token:
            return False

        if VALIDATION_SKIP:
            print("[WARN] EA_VALIDATION_SKIP=1 -> skipping remote validation (use with caution)")
            self.session_data["timestamp"] = time.time()
            with open(SESSION_FILE, "w") as f:
                json.dump(self.session_data, f)
            return True

        headers = {
            "X-UT-SID": token,
            "User-Agent": self.session_data.get("user_agent"),
            "Content-Type": "application/json",
        }

        last_error = None
        for url in VALIDATION_URLS:
            try:
                resp = requests.get(url, headers=headers, timeout=VALIDATION_TIMEOUT)
            except Exception as e:
                last_error = e
                print(f"[ERR] Validation request failed {url}: {e}")
                continue

            if resp.status_code == 200:
                body = resp.json() if resp.content else {}
                if not self.session_data.get("nucleus_id"):
                    self.session_data["nucleus_id"] = body.get("nucleusId")

                self.session_data["timestamp"] = time.time()
                with open(SESSION_FILE, "w") as f:
                    json.dump(self.session_data, f)
                print(f"[SUCCESS] Session validated via {url} and saved.")
                return True

            print(f"[FAIL] Token invalid (code {resp.status_code}) on {url}.")

        if os.path.exists(SESSION_FILE):
            os.remove(SESSION_FILE)
        if last_error:
            print(f"[FAIL] No validation URL succeeded. Last error: {last_error}")
        return False

    def run(self):
        if os.path.exists(SESSION_FILE):
            os.remove(SESSION_FILE)

        self.start_browser()
        print(">>> Connectez-vous manuellement à la Web App dans la fenêtre ouverte <<<")
        self.driver.get(WEB_APP_URL)

        start = time.time()
        last_cookie_scan = 0
        validated = False

        try:
            while time.time() - start < MAX_CAPTURE_SECONDS:
                logs = self.driver.get_log("performance")
                self.extract_from_logs(logs)

                now = time.time()
                if now - last_cookie_scan > 3:
                    # Try all methods
                    if not self.session_data.get("x-ut-sid"):
                        self.fallback_cookie_scan()
                    if not self.session_data.get("x-ut-sid"):
                        self.scan_local_storage()
                    if not self.session_data.get("x-ut-sid"):
                        self.scan_network_via_js()
                    last_cookie_scan = now

                # Also check current URL for token in query params
                current_url = self.driver.current_url
                if "sid=" in current_url.lower():
                    import urllib.parse
                    parsed = urllib.parse.urlparse(current_url)
                    params = urllib.parse.parse_qs(parsed.query)
                    if "sid" in params:
                        self.session_data["x-ut-sid"] = params["sid"][0]
                        print(f"[FOUND] Token from URL: {params['sid'][0][:20]}...")

                if self.session_data.get("x-ut-sid"):
                    print(f"[INFO] Token found: {self.session_data['x-ut-sid'][:20]}... Validating...")
                    if self.validate_and_save():
                        validated = True
                        break
                    else:
                        # Reset and keep listening
                        print("[WARN] Token validation failed, continuing to search...")
                        self.session_data["x-ut-sid"] = None

                time.sleep(1)

        finally:
            self.driver.quit()

        if not validated:
            print("[TIMEOUT] Échec de capture/validation du token.")


if __name__ == "__main__":
    RobustAuth().run()
