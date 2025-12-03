"""
AUTO WORKER - Le Sniper Autonome
=================================
Consomme les cibles générées par market_analyzer.py
et exécute les achats automatiquement.

Usage:
  1. Lance d'abord: python market_analyzer.py (dans un terminal)
  2. Puis: python auto_worker.py (dans un autre terminal)

Le worker lit active_targets.json et snipe les opportunités.
"""

import requests
import json
import time
import random
import os

SESSION_FILE = "active_session.json"
TARGETS_FILE = "active_targets.json"
PURCHASES_LOG = "purchases_log.json"

# =============================================================================
# PARAMÈTRES ANTI-BAN
# =============================================================================
REQUEST_DELAY_MIN = 3.0       # Délai minimum entre requêtes
REQUEST_DELAY_MAX = 6.0       # Délai maximum entre requêtes
POST_BUY_PAUSE_MIN = 15.0     # Pause minimum après achat
POST_BUY_PAUSE_MAX = 45.0     # Pause maximum après achat
MAX_BUYS_PER_HOUR = 8         # Maximum d'achats par heure
TARGETS_REFRESH_INTERVAL = 10 # Recharger targets toutes les X secondes


class AutoWorker:
    """Worker autonome qui snipe les cibles du Brain."""
    
    def __init__(self):
        self.session = requests.Session()
        self.api_url = None
        self.targets = []
        self.last_targets_load = 0
        self.purchases_this_hour = 0
        self.hour_start = time.time()
        self.total_spent = 0
        self.total_purchases = 0
        
        self.load_session()
        
    def load_session(self):
        """Charge la session EA."""
        if not os.path.exists(SESSION_FILE):
            raise SystemExit("[ERREUR] Pas de session. Lance: python auth_capture.py")
            
        with open(SESSION_FILE, 'r') as f:
            data = json.load(f)
        
        self.api_url = "https://utas.mob.v5.prd.futc-ext.gcp.ea.com"
        
        self.session.headers.update({
            "User-Agent": data.get("user_agent", "Mozilla/5.0"),
            "X-UT-SID": data.get("x-ut-sid"),
            "Accept": "application/json",
            "Content-Type": "application/json",
        })
        
        print(f"[SESSION] Token: {data.get('x-ut-sid', '')[:20]}...")
        
    def refresh_targets(self):
        """Recharge les cibles depuis le fichier généré par Brain."""
        # Ne pas recharger trop souvent
        if time.time() - self.last_targets_load < TARGETS_REFRESH_INTERVAL:
            return
            
        if not os.path.exists(TARGETS_FILE):
            return
        
        try:
            with open(TARGETS_FILE, 'r') as f:
                data = json.load(f)
            
            self.targets = data.get("targets", [])
            self.last_targets_load = time.time()
            
            updated_at = data.get("updated_at", "?")
            print(f"[REFRESH] {len(self.targets)} cibles chargées (màj: {updated_at})")
            
        except (json.JSONDecodeError, IOError):
            # Fichier en cours d'écriture par Brain
            pass
    
    def check_hour_limit(self):
        """Vérifie et reset le compteur horaire."""
        if time.time() - self.hour_start > 3600:
            print(f"[RESET] Nouvelle heure - Achats: {self.purchases_this_hour} -> 0")
            self.purchases_this_hour = 0
            self.hour_start = time.time()
            
        return self.purchases_this_hour < MAX_BUYS_PER_HOUR
    
    def search_market(self, target: dict) -> list:
        """
        Recherche les items sur le marché pour une cible.
        Retourne la liste des auctions trouvées.
        """
        url = f"{self.api_url}/ut/game/fc26/transfermarket"
        
        params = {
            "num": 21,
            "type": target["type"],
            "maxb": target["max_buy"],
            "_": int(time.time() * 1000)  # Cache buster
        }
        
        if target["type"] == "player":
            params["maskedDefId"] = target["id"]
        elif target["type"] == "training":
            params["cat"] = target.get("cat", "playStyle")
            params["definitionId"] = target["id"]
        
        try:
            resp = self.session.get(url, params=params, timeout=10)
            
            if resp.status_code == 200:
                return resp.json().get("auctionInfo", [])
            elif resp.status_code == 429:
                print("[429] Rate Limit - Pause 20s")
                time.sleep(20)
            elif resp.status_code == 401:
                print("[401] Token expiré - Relance auth_capture.py")
                exit(1)
            else:
                print(f"[WARN] Status {resp.status_code}")
                
        except requests.exceptions.RequestException as e:
            print(f"[ERREUR] {e}")
        
        return []
    
    def execute_buy(self, item: dict, target: dict) -> bool:
        """
        Exécute l'achat d'un item.
        Retourne True si succès.
        """
        trade_id = item["tradeId"]
        price = item["buyNowPrice"]
        
        url = f"{self.api_url}/ut/game/fc26/trade/{trade_id}/bid"
        payload = {"bid": price}
        
        try:
            start = time.time()
            resp = self.session.put(url, json=payload, timeout=10)
            latency = int((time.time() - start) * 1000)
            
            if resp.status_code == 200:
                self.purchases_this_hour += 1
                self.total_purchases += 1
                self.total_spent += price
                
                print(f"\033[92m[$$$] ACHAT OK!\033[0m {target['name']} @ {price} CR (latency: {latency}ms)")
                print(f"     Profit attendu: +{target.get('expected_profit', '?')} CR")
                print(f"     Total session: {self.total_purchases} achats, {self.total_spent} CR dépensés")
                
                # Log l'achat
                self.log_purchase(target, item, price)
                
                # Notification sonore
                print('\a')
                
                return True
            else:
                print(f"[FAIL] Achat échoué: {resp.status_code} - {resp.text[:100]}")
                
        except requests.exceptions.RequestException as e:
            print(f"[ERREUR] Buy failed: {e}")
        
        return False
    
    def log_purchase(self, target: dict, item: dict, price: int):
        """Enregistre l'achat dans un fichier log."""
        log_entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "name": target["name"],
            "trade_id": item["tradeId"],
            "price": price,
            "market_price": target.get("market_price"),
            "expected_profit": target.get("expected_profit")
        }
        
        # Charger log existant
        logs = []
        if os.path.exists(PURCHASES_LOG):
            try:
                with open(PURCHASES_LOG, 'r') as f:
                    logs = json.load(f)
            except:
                pass
        
        logs.append(log_entry)
        
        with open(PURCHASES_LOG, 'w') as f:
            json.dump(logs, f, indent=2)
    
    def snipe_target(self, target: dict):
        """
        Cherche et achète la meilleure opportunité pour une cible.
        """
        items = self.search_market(target)
        
        if not items:
            print(f"[SCAN] {target['name']} < {target['max_buy']} : Rien trouvé")
            return
        
        # Trier par prix croissant
        items.sort(key=lambda x: x.get('buyNowPrice', 999999))
        
        # Filtrer les BIN disponibles
        buyable = [i for i in items if i.get('buyNowPrice', 0) > 0]
        
        if not buyable:
            print(f"[SCAN] {target['name']} : {len(items)} items mais pas de BIN")
            return
        
        # Prendre le moins cher
        best = buyable[0]
        price = best['buyNowPrice']
        
        print(f"[!!!] TROUVÉ: {target['name']} @ {price} CR (max: {target['max_buy']})")
        
        # Exécuter l'achat
        if self.execute_buy(best, target):
            # Pause post-achat anti-ban
            pause = random.uniform(POST_BUY_PAUSE_MIN, POST_BUY_PAUSE_MAX)
            print(f"[ANTI-BAN] Pause post-achat: {pause:.1f}s ({self.purchases_this_hour}/{MAX_BUYS_PER_HOUR} cette heure)")
            time.sleep(pause)
    
    def get_random_delay(self) -> float:
        """
        Génère un délai aléatoire avec distribution de Pareto.
        Simule un comportement humain (souvent rapide, parfois lent).
        """
        # Pareto: la plupart des valeurs proches du min, quelques valeurs élevées
        delay = random.paretovariate(1.5) + REQUEST_DELAY_MIN
        return min(delay, REQUEST_DELAY_MAX * 2)  # Cap à 2x max
    
    def run(self):
        """Boucle principale du worker."""
        print()
        print("="*60)
        print("[WORKER] Démarrage mode autonome")
        print("="*60)
        print(f"  Délai entre scans: {REQUEST_DELAY_MIN}-{REQUEST_DELAY_MAX}s")
        print(f"  Max achats/heure:  {MAX_BUYS_PER_HOUR}")
        print(f"  Pause post-achat:  {POST_BUY_PAUSE_MIN}-{POST_BUY_PAUSE_MAX}s")
        print()
        print("[INFO] En attente des cibles du Brain...")
        print("[INFO] Lance 'python market_analyzer.py' dans un autre terminal")
        print()
        
        while True:
            try:
                # Recharger les cibles
                self.refresh_targets()
                
                if not self.targets:
                    print("[WAIT] Aucune cible. En attente du Brain...")
                    time.sleep(5)
                    continue
                
                # Vérifier limite horaire
                if not self.check_hour_limit():
                    wait = 3600 - (time.time() - self.hour_start)
                    print(f"[LIMIT] Max achats atteint. Pause {int(wait)}s...")
                    time.sleep(min(wait, 300))  # Check toutes les 5 min
                    continue
                
                # Choisir une cible au hasard (comportement humain)
                target = random.choice(self.targets)
                
                # Scanner et sniper
                self.snipe_target(target)
                
                # Délai anti-bot
                delay = self.get_random_delay()
                time.sleep(delay)
                
            except KeyboardInterrupt:
                print("\n[STOP] Arrêt demandé.")
                print(f"[STATS] Total: {self.total_purchases} achats, {self.total_spent} CR")
                break
            except Exception as e:
                print(f"[ERREUR] {e}")
                time.sleep(10)


def main():
    worker = AutoWorker()
    worker.run()


if __name__ == "__main__":
    main()
