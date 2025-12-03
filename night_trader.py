"""
NIGHT TRADER - Bot Achat/Vente Multi-Notes
Scanne les notes 83-86, achète <= Futbin, revend au prix Futbin
"""

import requests
import json
import time
import random
from datetime import datetime

# Config
SESSION_FILE = "active_session.json"
TARGETS_FILE = "fodder_targets.json"
LOG_FILE = "night_trader_log.json"
EA_URL = "https://utas.mob.v5.prd.futc-ext.gcp.ea.com/ut/game/fc26"

# Timing anti-ban (plus agressif)
SCAN_DELAY_MIN = 4.0
SCAN_DELAY_MAX = 8.0
POST_BUY_PAUSE_MIN = 8.0
POST_BUY_PAUSE_MAX = 15.0
JITTER_CHANCE = 0.15  # 15% chance pause longue

# Limites
MAX_BUYS_PER_HOUR = 25

class NightTrader:
    def __init__(self):
        with open(SESSION_FILE) as f:
            self.session = json.load(f)
        with open(TARGETS_FILE) as f:
            self.config = json.load(f)
        
        self.targets = {t['rating']: t for t in self.config['targets']}
        self.buys = 0
        self.listed = 0
        self.hour_start = time.time()
        self.buys_this_hour = 0
        self.log = []
    
    def api(self, method, endpoint, params=None, data=None):
        url = f"{EA_URL}/{endpoint}"
        headers = {
            "X-UT-SID": self.session['x-ut-sid'],
            "User-Agent": self.session.get('user_agent', 'Mozilla/5.0'),
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        try:
            if method == "GET":
                return requests.get(url, params=params, headers=headers, timeout=15)
            elif method == "PUT":
                return requests.put(url, json=data, headers=headers, timeout=15)
            elif method == "POST":
                return requests.post(url, json=data, headers=headers, timeout=15)
        except Exception as e:
            print(f"[!] Erreur: {e}")
            return None
    
    def check_limits(self):
        now = time.time()
        if now - self.hour_start > 3600:
            self.hour_start = now
            self.buys_this_hour = 0
        return self.buys_this_hour < MAX_BUYS_PER_HOUR
    
    def scan_rating(self, rating):
        """Scanne une note et retourne les opportunités"""
        target = self.targets.get(rating)
        if not target:
            return []
        
        max_buy = target['max_buy']
        
        params = {
            'type': 'player',
            'raretype': '1',
            'lev': 'gold', 
            'minr': rating,
            'maxr': rating,
            'maxb': max_buy,
            'num': 21
        }
        
        resp = self.api("GET", "transfermarket", params=params)
        if not resp or resp.status_code != 200:
            if resp and resp.status_code == 401:
                return None  # Token expiré
            return []
        
        auctions = resp.json().get('auctionInfo', [])
        
        # Filtrer Gold Rare + bonne note
        opps = []
        for a in auctions:
            item = a.get('itemData', {})
            if item.get('rareflag') == 1 and item.get('rating') == rating:
                opps.append({
                    'trade_id': a['tradeId'],
                    'item_id': item.get('id'),
                    'name': item.get('lastName', '?'),
                    'rating': rating,
                    'price': a['buyNowPrice'],
                    'sell_price': target['sell_price']
                })
        
        return opps
    
    def buy(self, opp):
        """Achète une carte"""
        resp = self.api("PUT", f"trade/{opp['trade_id']}/bid", data={"bid": opp['price']})
        if resp and resp.status_code == 200:
            return True
        return False
    
    def sell_unassigned(self, sell_price):
        """Liste les cartes non assignées"""
        resp = self.api("GET", "purchased/items")
        if not resp or resp.status_code != 200:
            return 0
        
        items = resp.json().get('itemData', [])
        count = 0
        
        for item in items:
            item_id = item.get('id')
            if not item_id:
                continue
            
            # Move to tradepile
            self.api("PUT", "item", data={"itemData": [{"id": item_id, "pile": "trade"}]})
            time.sleep(1)
            
            # List for sale - 12h = 43200 secondes
            start = int(sell_price * 0.9 / 50) * 50
            resp = self.api("POST", "auctionhouse", data={
                "itemData": {"id": item_id},
                "startingBid": start,
                "duration": 43200,
                "buyNowPrice": sell_price
            })
            
            if resp and resp.status_code == 200:
                count += 1
            
            time.sleep(random.uniform(2, 4))
        
        return count
    
    def run(self, hours=8):
        print("\n" + "="*60)
        print("   NIGHT TRADER - Achat/Vente Auto")
        print("="*60)
        print(f"Notes ciblées: {list(self.targets.keys())}")
        print(f"Durée: {hours}h | Max {MAX_BUYS_PER_HOUR} achats/h")
        print("="*60)
        
        end_time = time.time() + (hours * 3600)
        ratings = list(self.targets.keys())
        
        while time.time() < end_time:
            if not self.check_limits():
                print(f"[LIMIT] {MAX_BUYS_PER_HOUR} achats/h atteint, pause 5min...")
                time.sleep(300)
                continue
            
            # Rotation des notes
            rating = random.choice(ratings)
            target = self.targets[rating]
            
            now = datetime.now().strftime("%H:%M:%S")
            
            opps = self.scan_rating(rating)
            
            if opps is None:
                print(f"\n[{now}] [!] TOKEN EXPIRE - Arret")
                break
            
            if opps:
                print(f"\n[{now}] Note {rating}: {len(opps)} trouvé(s)!")
                
                # Acheter le moins cher
                opp = min(opps, key=lambda x: x['price'])
                print(f"  -> {opp['name']} @ {opp['price']} CR")
                
                if self.buy(opp):
                    print(f"  [OK] ACHETE!")
                    self.buys += 1
                    self.buys_this_hour += 1
                    
                    # Pause puis revente
                    pause = random.uniform(POST_BUY_PAUSE_MIN, POST_BUY_PAUSE_MAX)
                    print(f"  Pause {pause:.0f}s puis revente...")
                    time.sleep(pause)
                    
                    listed = self.sell_unassigned(opp['sell_price'])
                    if listed:
                        print(f"  [OK] {listed} carte(s) en vente @ {opp['sell_price']} CR")
                        self.listed += listed
                else:
                    print(f"  [X] Echec (deja vendue?)")
            
            # Délai aléatoire
            delay = random.uniform(SCAN_DELAY_MIN, SCAN_DELAY_MAX)
            if random.random() < JITTER_CHANCE:
                delay += random.uniform(10, 30)
                print(f"  [Jitter] +pause longue")
            time.sleep(delay)
        
        # Résumé
        print("\n" + "="*60)
        print("   RESUME SESSION")
        print("="*60)
        print(f"Achats: {self.buys}")
        print(f"Listés: {self.listed}")
        print("="*60)

if __name__ == "__main__":
    import sys
    hours = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    trader = NightTrader()
    trader.run(hours=hours)
