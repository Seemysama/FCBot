"""
SNIPE WORKER - Hard Sniping Mode
Blind Buy sur filtres pré-définis - Vitesse pure
"""

import requests
import json
import time
import random
from datetime import datetime
from collections import deque

# === CONFIG ===
SESSION_FILE = "active_session.json"
FILTERS_FILE = "snipe_filters.json"
STATS_FILE = "snipe_stats.json"

EA_URL = "https://utas.mob.v5.prd.futc-ext.gcp.ea.com/ut/game/fc26"

# VITESSE - Agressif mais pas suicidaire
SPEED_MIN = 1.5  # Minimum entre requêtes
SPEED_MAX = 2.5  # Maximum entre requêtes
SOFTBAN_PAUSE = 120  # 2 min pause si softban détecté
SOFTBAN_THRESHOLD = 3  # Nombre d'erreurs avant pause

# Anti-détection : Distribution gaussienne
def smart_delay():
    """Délai humain-like (distribution gaussienne)"""
    delay = abs(random.gauss(2.0, 0.5))
    return max(SPEED_MIN, min(SPEED_MAX, delay))

class AggressiveSniper:
    def __init__(self):
        with open(SESSION_FILE) as f:
            self.session = json.load(f)
        
        self.load_filters()
        self.stats = {
            'scans': 0,
            'hits': 0,
            'buys': 0,
            'fails': 0,
            'profit_estimate': 0,
            'errors_streak': 0,
            'start_time': time.time()
        }
        self.recent_buys = deque(maxlen=50)  # Historique des 50 derniers achats
        
    def load_filters(self):
        """Charge les filtres actifs"""
        with open(FILTERS_FILE) as f:
            data = json.load(f)
        self.filters = [f for f in data['filters'] if f.get('active', True)]
        print(f"[INIT] {len(self.filters)} filtres actifs chargés")
        
    def api(self, method, endpoint, params=None, data=None):
        """Requête API optimisée pour la vitesse"""
        url = f"{EA_URL}/{endpoint}"
        headers = {
            "X-UT-SID": self.session['x-ut-sid'],
            "User-Agent": self.session.get('user_agent', 'Mozilla/5.0'),
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        try:
            if method == "GET":
                resp = requests.get(url, params=params, headers=headers, timeout=10)
            elif method == "PUT":
                resp = requests.put(url, json=data, headers=headers, timeout=10)
            elif method == "POST":
                resp = requests.post(url, json=data, headers=headers, timeout=10)
            return resp
        except requests.exceptions.Timeout:
            return None
        except Exception as e:
            print(f"[ERR] {e}")
            return None
    
    def scan_filter(self, filter_config):
        """Scan un filtre et retourne les résultats"""
        params = filter_config['params'].copy()
        params['num'] = 21  # Max résultats
        
        resp = self.api("GET", "transfermarket", params=params)
        self.stats['scans'] += 1
        
        if not resp:
            return None, "TIMEOUT"
        
        if resp.status_code == 401:
            return None, "TOKEN_EXPIRED"
        
        if resp.status_code == 429:
            return None, "SOFTBAN"
        
        if resp.status_code != 200:
            return None, f"HTTP_{resp.status_code}"
        
        try:
            auctions = resp.json().get('auctionInfo', [])
            return auctions, "OK"
        except:
            return None, "JSON_ERROR"
    
    def blind_buy(self, auction):
        """Achat instantané - pas de vérification"""
        trade_id = auction['tradeId']
        price = auction['buyNowPrice']
        
        # PUT instantané
        resp = self.api("PUT", f"trade/{trade_id}/bid", data={"bid": price})
        
        if resp and resp.status_code == 200:
            return True
        return False
    
    def move_to_tradepile(self, item_id):
        """Déplace vers pile de transfert"""
        self.api("PUT", "item", data={"itemData": [{"id": item_id, "pile": "trade"}]})
    
    def list_for_sale(self, item_id, buy_price, expected_value):
        """Met en vente avec markup"""
        # Prix de vente = max(expected_value, buy_price * 1.3)
        sell_price = max(expected_value, int(buy_price * 1.3))
        sell_price = (sell_price // 50) * 50  # Arrondi à 50
        
        start_price = int(sell_price * 0.9 // 50) * 50
        
        self.api("POST", "auctionhouse", data={
            "itemData": {"id": item_id},
            "startingBid": start_price,
            "duration": 43200,  # 12h
            "buyNowPrice": sell_price
        })
        
        return sell_price
    
    def process_hit(self, auction, filter_config):
        """Traite un hit - Achat + Vente"""
        item = auction.get('itemData', {})
        price = auction['buyNowPrice']
        name = item.get('lastName', item.get('name', '?'))
        rating = item.get('rating', '?')
        expected = filter_config.get('expected_min_value', price * 1.5)
        
        now = datetime.now().strftime("%H:%M:%S")
        print(f"\n[{now}] 🎯 HIT! {filter_config['name']}")
        print(f"  -> {name} ({rating}) @ {price} CR")
        
        # BLIND BUY
        if self.blind_buy(auction):
            self.stats['buys'] += 1
            self.stats['hits'] += 1
            profit = int(expected * 0.95 - price)
            self.stats['profit_estimate'] += profit
            
            print(f"  ✅ ACHETÉ! Profit estimé: +{profit} CR")
            
            # Log l'achat
            self.recent_buys.append({
                'time': now,
                'name': name,
                'rating': rating,
                'price': price,
                'filter': filter_config['name']
            })
            
            # Pause courte puis mise en vente
            time.sleep(random.uniform(2, 4))
            
            # Récupérer l'item acheté
            resp = self.api("GET", "purchased/items")
            if resp and resp.status_code == 200:
                items = resp.json().get('itemData', [])
                for bought_item in items:
                    item_id = bought_item.get('id')
                    if item_id:
                        self.move_to_tradepile(item_id)
                        time.sleep(1)
                        sell_price = self.list_for_sale(item_id, price, expected)
                        print(f"  📤 En vente @ {sell_price} CR")
                        time.sleep(random.uniform(1, 2))
            
            return True
        else:
            self.stats['fails'] += 1
            print(f"  ❌ Raté (déjà vendu)")
            return False
    
    def check_softban(self, status):
        """Gère la détection de softban"""
        if status in ["SOFTBAN", "HTTP_429"]:
            self.stats['errors_streak'] += 1
            print(f"\n⚠️  [429] Erreur #{self.stats['errors_streak']}")
            
            if self.stats['errors_streak'] >= SOFTBAN_THRESHOLD:
                print(f"🛑 SOFTBAN DÉTECTÉ - Pause {SOFTBAN_PAUSE}s...")
                time.sleep(SOFTBAN_PAUSE)
                self.stats['errors_streak'] = 0
                return True
        else:
            self.stats['errors_streak'] = 0
        
        return False
    
    def print_stats(self):
        """Affiche les stats"""
        elapsed = time.time() - self.stats['start_time']
        rpm = (self.stats['scans'] / elapsed) * 60 if elapsed > 0 else 0
        
        print(f"\n{'='*50}")
        print(f"📊 STATS | Scans: {self.stats['scans']} | RPM: {rpm:.1f}")
        print(f"   Hits: {self.stats['hits']} | Buys: {self.stats['buys']} | Fails: {self.stats['fails']}")
        print(f"   Profit estimé: {self.stats['profit_estimate']:,} CR")
        print(f"{'='*50}\n")
    
    def run(self):
        """Boucle principale - Rotation des filtres"""
        print("\n" + "="*60)
        print("   🎯 AGGRESSIVE SNIPER - Hard Mode")
        print("="*60)
        print(f"Filtres: {[f['name'] for f in self.filters]}")
        print(f"Vitesse: {SPEED_MIN}-{SPEED_MAX}s")
        print("="*60 + "\n")
        
        filter_index = 0
        last_stats = time.time()
        
        try:
            while True:
                # Rotation des filtres
                current_filter = self.filters[filter_index]
                filter_index = (filter_index + 1) % len(self.filters)
                
                # Scan
                auctions, status = self.scan_filter(current_filter)
                
                # Gestion erreurs
                if status == "TOKEN_EXPIRED":
                    print("\n❌ TOKEN EXPIRÉ - Arrêt")
                    break
                
                if self.check_softban(status):
                    continue
                
                # Traitement des résultats
                if auctions:
                    # BLIND BUY sur le premier résultat
                    self.process_hit(auctions[0], current_filter)
                    # Pause plus longue après achat
                    time.sleep(random.uniform(5, 10))
                
                # Stats toutes les 60 secondes
                if time.time() - last_stats > 60:
                    self.print_stats()
                    last_stats = time.time()
                    # Hot reload des filtres
                    self.load_filters()
                
                # Délai intelligent
                time.sleep(smart_delay())
                
        except KeyboardInterrupt:
            print("\n\n🛑 Arrêt manuel")
            self.print_stats()
            
            # Sauvegarde stats
            with open(STATS_FILE, 'w') as f:
                json.dump(self.stats, f, indent=2)

if __name__ == "__main__":
    sniper = AggressiveSniper()
    sniper.run()
