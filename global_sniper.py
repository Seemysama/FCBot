"""
=============================================================================
                    GLOBAL OPPORTUNITY SNIPER (WORKER v2)
=============================================================================
Exécute les achats sur les opportunités détectées par le Scanner Global.

FONCTIONNEMENT:
1. Lit les cibles depuis active_targets.json
2. Recherche les cartes correspondantes sur le marché
3. Achète si le prix est dans la fourchette
4. Log les achats et met à jour les stats

ANTI-BAN:
- Délais Pareto entre actions
- Limite d'achats par heure
- Pause post-achat
- Rotation des recherches
=============================================================================
"""

import requests
import json
import time
import random
import os
from datetime import datetime

# =============================================================================
# CONFIGURATION
# =============================================================================

SESSION_FILE = "active_session.json"
TARGETS_FILE = "active_targets.json"
PURCHASES_LOG = "purchases_log.json"

EA_BASE_URL = "https://utas.mob.v5.prd.futc-ext.gcp.ea.com/ut/game/fc26"

# Anti-ban
REQUEST_DELAY_MIN = 2.5
REQUEST_DELAY_MAX = 5.0
MAX_BUYS_PER_HOUR = 8
POST_BUY_PAUSE_MIN = 20
POST_BUY_PAUSE_MAX = 45

# Mode
DRY_RUN = os.environ.get('DRY_RUN', '0') == '1'

# =============================================================================
# CLASSES
# =============================================================================

class OpportunitySniper:
    """Sniper d'opportunités globales"""
    
    def __init__(self):
        self.session = self.load_session()
        self.buys_this_hour = 0
        self.hour_start = time.time()
        self.total_profit = 0
        self.purchases = []
    
    def load_session(self):
        if not os.path.exists(SESSION_FILE):
            raise Exception(f"Session non trouvée: {SESSION_FILE}")
        with open(SESSION_FILE, 'r') as f:
            return json.load(f)
    
    def load_targets(self):
        """Charge les cibles actives"""
        if not os.path.exists(TARGETS_FILE):
            return []
        
        try:
            with open(TARGETS_FILE, 'r') as f:
                data = json.load(f)
            
            targets = data.get('targets', [])
            now = time.time()
            
            # Filtrer les cibles expirées
            valid = [t for t in targets if t.get('expires_at', 0) > now]
            
            return valid
        except:
            return []
    
    def pareto_delay(self, min_d=None, max_d=None):
        """Délai aléatoire Pareto"""
        min_d = min_d or REQUEST_DELAY_MIN
        max_d = max_d or REQUEST_DELAY_MAX
        
        base = random.uniform(min_d, max_d)
        if random.random() < 0.15:
            base *= random.uniform(1.5, 2.5)
        return base
    
    def check_buy_limit(self):
        """Vérifie la limite d'achats"""
        now = time.time()
        if now - self.hour_start > 3600:
            self.hour_start = now
            self.buys_this_hour = 0
        return self.buys_this_hour < MAX_BUYS_PER_HOUR
    
    def search_player(self, player_id, max_price):
        """Recherche un joueur sur le marché"""
        url = f"{EA_BASE_URL}/transfermarket"
        
        params = {
            "type": "player",
            "maskedDefId": player_id,
            "maxb": max_price,
            "num": 21,
            "start": 0
        }
        
        headers = {
            "X-UT-SID": self.session['x-ut-sid'],
            "User-Agent": self.session.get('user_agent', 'Mozilla/5.0'),
            "Accept": "application/json",
        }
        
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=15)
            
            if resp.status_code == 401:
                print("[!] Token expiré")
                return None
            elif resp.status_code == 429:
                print("[!] Rate limit")
                return None
            elif resp.status_code != 200:
                return None
            
            return resp.json()
            
        except Exception as e:
            print(f"[!] Erreur recherche: {e}")
            return None
    
    def buy_card(self, trade_id, price):
        """Achète une carte"""
        if DRY_RUN:
            print(f"  [DRY-RUN] Achat simulé: {trade_id} @ {price}")
            return True
        
        url = f"{EA_BASE_URL}/trade/{trade_id}/bid"
        
        headers = {
            "X-UT-SID": self.session['x-ut-sid'],
            "User-Agent": self.session.get('user_agent', 'Mozilla/5.0'),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        
        payload = {"bid": price}
        
        try:
            resp = requests.put(url, json=payload, headers=headers, timeout=15)
            
            if resp.status_code == 200:
                return True
            else:
                print(f"  [!] Échec achat: {resp.status_code}")
                return False
                
        except Exception as e:
            print(f"  [!] Erreur achat: {e}")
            return False
    
    def log_purchase(self, target, trade_id, price):
        """Log un achat"""
        purchase = {
            "timestamp": datetime.now().isoformat(),
            "player_id": target['player_id'],
            "player_name": target['player_name'],
            "trade_id": trade_id,
            "buy_price": price,
            "expected_sell": target.get('target_sell_price', 0),
            "expected_profit": target.get('expected_profit', 0),
            "source": target.get('source', 'global')
        }
        
        self.purchases.append(purchase)
        self.total_profit += target.get('expected_profit', 0)
        
        # Sauvegarder
        all_purchases = []
        if os.path.exists(PURCHASES_LOG):
            try:
                with open(PURCHASES_LOG, 'r') as f:
                    all_purchases = json.load(f)
            except:
                pass
        
        all_purchases.append(purchase)
        
        with open(PURCHASES_LOG, 'w') as f:
            json.dump(all_purchases, f, indent=2)
    
    def hunt_target(self, target):
        """Chasse une cible spécifique"""
        player_id = target['player_id']
        player_name = target['player_name']
        max_price = target['max_buy_price']
        expected_profit = target.get('expected_profit', 0)
        
        print(f"\n[🎯] Chasse: {player_name} (max {max_price} CR)")
        
        # Rechercher
        result = self.search_player(player_id, max_price)
        
        if not result:
            print("  [✗] Recherche échouée")
            return False
        
        auctions = result.get('auctionInfo', [])
        print(f"  [i] {len(auctions)} annonces trouvées")
        
        if not auctions:
            return False
        
        # Chercher la meilleure offre
        best = None
        for auction in auctions:
            buy_now = auction.get('buyNowPrice', 0)
            if buy_now and buy_now <= max_price:
                if not best or buy_now < best['buyNowPrice']:
                    best = auction
        
        if not best:
            print("  [✗] Aucune offre dans le budget")
            return False
        
        trade_id = best['tradeId']
        buy_now = best['buyNowPrice']
        
        print(f"  [→] Meilleure offre: {buy_now} CR")
        
        # Acheter
        if self.buy_card(trade_id, buy_now):
            self.buys_this_hour += 1
            self.log_purchase(target, trade_id, buy_now)
            
            print(f"  [✓] ACHETÉ! Profit attendu: +{expected_profit} CR")
            
            # Pause post-achat
            pause = random.uniform(POST_BUY_PAUSE_MIN, POST_BUY_PAUSE_MAX)
            print(f"  [⏳] Pause sécurité {pause:.1f}s...")
            time.sleep(pause)
            
            return True
        
        return False
    
    def run_cycle(self):
        """Exécute un cycle de chasse"""
        targets = self.load_targets()
        
        if not targets:
            return 0
        
        print(f"\n[📋] {len(targets)} cibles actives")
        
        bought = 0
        
        for target in targets:
            if not self.check_buy_limit():
                print("[!] Limite d'achats atteinte")
                break
            
            if self.hunt_target(target):
                bought += 1
            
            # Délai entre cibles
            time.sleep(self.pareto_delay())
        
        return bought
    
    def run_continuous(self, check_interval=15):
        """Mode continu"""
        print("\n" + "=" * 60)
        print("   OPPORTUNITY SNIPER - MODE CONTINU")
        print("=" * 60)
        print(f"Intervalle de vérification: {check_interval}s")
        print(f"Limite achats/heure: {MAX_BUYS_PER_HOUR}")
        print(f"Mode: {'DRY-RUN (simulation)' if DRY_RUN else 'RÉEL'}")
        print("Ctrl+C pour arrêter\n")
        
        try:
            while True:
                bought = self.run_cycle()
                
                if bought > 0:
                    print(f"\n[📊] Session: {len(self.purchases)} achats | "
                          f"Profit estimé: +{self.total_profit} CR")
                
                # Attendre
                wait = check_interval + random.uniform(-3, 3)
                time.sleep(max(5, wait))
                
        except KeyboardInterrupt:
            print("\n[STOP] Sniper arrêté")
            print(f"[📊] Total achats: {len(self.purchases)}")
            print(f"[📊] Profit estimé: +{self.total_profit} CR")


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import sys
    
    sniper = OpportunitySniper()
    
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        sniper.run_cycle()
    else:
        interval = int(sys.argv[2]) if len(sys.argv) > 2 else 15
        sniper.run_continuous(check_interval=interval)
