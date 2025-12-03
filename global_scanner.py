"""
=============================================================================
                    GLOBAL MARKET SCANNER (BRAIN v2)
=============================================================================
Système intelligent de détection d'opportunités globales.

PHILOSOPHIE:
- Le "Spotting" vaut plus cher que l'exécution
- On ne se fixe PAS sur un joueur
- On scanne le marché et on détecte les anomalies de prix

MÉTHODE:
1. Scanner les dernières pages du marché (nouvelles annonces)
2. Comparer avec les prix moyens connus
3. Identifier les cartes sous-évaluées
4. Générer des cibles pour le worker

ANTI-BAN:
- Délais Pareto entre requêtes
- Rotation des types de recherche
- Pas de pattern répétitif
=============================================================================
"""

import requests
import json
import time
import random
import os
from datetime import datetime
from collections import defaultdict

# =============================================================================
# CONFIGURATION
# =============================================================================

# Fichiers
SESSION_FILE = "active_session.json"
PLAYERS_DB_FILE = "clean_players.json"
PRICE_CACHE_FILE = "price_cache.json"
TARGETS_FILE = "active_targets.json"
SCAN_LOG_FILE = "scan_log.json"

# EA API
EA_BASE_URL = "https://utas.mob.v5.prd.futc-ext.gcp.ea.com/ut/game/fc26"

# Paramètres de scan
SCAN_DELAY_MIN = 3.0      # Délai minimum entre requêtes
SCAN_DELAY_MAX = 7.0      # Délai maximum
PAGES_PER_SCAN = 3        # Pages à scanner par type
MAX_SCANS_PER_HOUR = 40   # Limite horaire

# Stratégie
TAX_RATE = 0.05           # 5% taxe EA
MIN_PROFIT_MARGIN = 0.05  # 5% profit minimum après taxe
MIN_PROFIT_ABSOLUTE = 200 # 200 CR profit minimum
MAX_BUY_PRICE = 15000     # Prix max d'achat (sécurité)

# Types de scan (rotation pour paraître humain)
SCAN_STRATEGIES = [
    # Fodder Gold Rare 82-84 (très liquide)
    {"name": "Fodder 82", "params": {"type": "player", "raretype": "1", "minb": 700, "maxb": 3000, "lev": "gold", "minr": 82, "maxr": 82}},
    {"name": "Fodder 83", "params": {"type": "player", "raretype": "1", "minb": 1500, "maxb": 5000, "lev": "gold", "minr": 83, "maxr": 83}},
    {"name": "Fodder 84", "params": {"type": "player", "raretype": "1", "minb": 3000, "maxb": 8000, "lev": "gold", "minr": 84, "maxr": 84}},
    
    # Meta Players (85-87)
    {"name": "Meta 85", "params": {"type": "player", "raretype": "1", "minb": 4000, "maxb": 12000, "lev": "gold", "minr": 85, "maxr": 85}},
    {"name": "Meta 86", "params": {"type": "player", "raretype": "1", "minb": 8000, "maxb": 20000, "lev": "gold", "minr": 86, "maxr": 86}},
    
    # Chemistry Styles (ultra-liquides)
    {"name": "Hunter", "params": {"type": "training", "cat": "playStyle", "minb": 3000, "maxb": 8000}},
    {"name": "Shadow", "params": {"type": "training", "cat": "playStyle", "minb": 3000, "maxb": 8000}},
    
    # Nouvelles annonces génériques (dernières 59 min)
    {"name": "Fresh Deals", "params": {"type": "player", "raretype": "1", "minb": 600, "maxb": 10000, "lev": "gold"}},
]

# =============================================================================
# CLASSES
# =============================================================================

class PriceTracker:
    """Suit les prix pour détecter les anomalies"""
    
    def __init__(self):
        self.prices = defaultdict(list)  # {item_id: [(price, timestamp), ...]}
        self.load_cache()
    
    def load_cache(self):
        if os.path.exists(PRICE_CACHE_FILE):
            try:
                with open(PRICE_CACHE_FILE, 'r') as f:
                    data = json.load(f)
                    for k, v in data.items():
                        self.prices[int(k)] = v
            except:
                pass
    
    def save_cache(self):
        # Ne garder que les 24h dernières heures
        now = time.time()
        cutoff = now - 86400
        
        cleaned = {}
        for item_id, entries in self.prices.items():
            recent = [(p, t) for p, t in entries if t > cutoff]
            if recent:
                cleaned[item_id] = recent[-50:]  # Max 50 entrées par item
        
        with open(PRICE_CACHE_FILE, 'w') as f:
            json.dump(cleaned, f)
    
    def make_key(self, asset_id, rareflag):
        """Crée une clé unique par version de carte (Gold vs IF vs TOTW etc.)
        
        rareflag values:
        - 1 = Gold Rare
        - 0 = Gold Non-Rare  
        - 3 = Team of the Week (TOTW/IF)
        - 12 = TOTS, etc.
        
        IMPORTANT: On doit séparer les versions pour ne pas mélanger les prix!
        """
        return f"{asset_id}_{rareflag}"
    
    def record_price(self, asset_id, price, rareflag=1):
        key = self.make_key(asset_id, rareflag)
        self.prices[key].append((price, time.time()))
    
    def get_average(self, asset_id, rareflag=1):
        """Prix moyen des dernières heures pour cette VERSION spécifique"""
        key = self.make_key(asset_id, rareflag)
        entries = self.prices.get(key, [])
        if not entries:
            return None
        
        # Pondérer les prix récents
        now = time.time()
        weighted_sum = 0
        weight_total = 0
        
        for price, ts in entries[-20:]:  # 20 derniers
            age_hours = (now - ts) / 3600
            weight = max(0.1, 1 - (age_hours / 24))  # Plus récent = plus de poids
            weighted_sum += price * weight
            weight_total += weight
        
        return int(weighted_sum / weight_total) if weight_total > 0 else None
    
    def get_lowest_seen(self, asset_id, rareflag=1):
        """Plus bas prix vu récemment pour cette VERSION spécifique"""
        key = self.make_key(asset_id, rareflag)
        entries = self.prices.get(key, [])
        if not entries:
            return None
        
        # Dernières 6 heures
        now = time.time()
        recent = [p for p, t in entries if now - t < 21600]
        return min(recent) if recent else None
    
    def get_sample_count(self, asset_id, rareflag=1):
        """Nombre d'échantillons de prix (pour mesurer la fiabilité)"""
        key = self.make_key(asset_id, rareflag)
        return len(self.prices.get(key, []))


class GlobalScanner:
    """Scanner de marché global"""
    
    def __init__(self):
        self.session = self.load_session()
        self.players_db = self.load_players_db()
        self.price_tracker = PriceTracker()
        self.scan_count = 0
        self.hourly_count = 0
        self.hour_start = time.time()
        self.opportunities = []
    
    def load_session(self):
        if not os.path.exists(SESSION_FILE):
            raise Exception(f"Session non trouvée: {SESSION_FILE}")
        with open(SESSION_FILE, 'r') as f:
            return json.load(f)
    
    def load_players_db(self):
        """Charge la base de données des joueurs"""
        if not os.path.exists(PLAYERS_DB_FILE):
            print(f"[!] Base joueurs non trouvée: {PLAYERS_DB_FILE}")
            return {}
        
        with open(PLAYERS_DB_FILE, 'r') as f:
            data = json.load(f)
        
        # Index par ID pour recherche rapide
        by_id = {}
        for name, cards in data.items():
            for card in cards:
                by_id[card.get('resourceId', card.get('baseId'))] = {
                    'name': card.get('name', name),
                    'rating': card.get('rating', 0),
                    'position': card.get('position', '')
                }
        
        print(f"[DB] {len(by_id)} joueurs chargés")
        return by_id
    
    def get_player_info(self, asset_id):
        """Récupère les infos d'un joueur"""
        return self.players_db.get(asset_id, {'name': f'ID:{asset_id}', 'rating': 0})
    
    def pareto_delay(self):
        """Délai aléatoire avec distribution Pareto (plus réaliste)"""
        base = random.uniform(SCAN_DELAY_MIN, SCAN_DELAY_MAX)
        # Parfois plus long (simule distraction humaine)
        if random.random() < 0.1:
            base *= random.uniform(1.5, 3.0)
        return base
    
    def check_hourly_limit(self):
        """Vérifie la limite horaire"""
        now = time.time()
        if now - self.hour_start > 3600:
            self.hour_start = now
            self.hourly_count = 0
        
        return self.hourly_count < MAX_SCANS_PER_HOUR
    
    def search_market(self, params, page=0):
        """Effectue une recherche sur le marché"""
        if not self.check_hourly_limit():
            print("[!] Limite horaire atteinte")
            return None
        
        url = f"{EA_BASE_URL}/transfermarket"
        
        search_params = {
            "num": 21,
            "start": page * 21,
            **params
        }
        
        headers = {
            "X-UT-SID": self.session['x-ut-sid'],
            "User-Agent": self.session.get('user_agent', 'Mozilla/5.0'),
            "Accept": "application/json",
        }
        
        try:
            resp = requests.get(url, params=search_params, headers=headers, timeout=15)
            self.hourly_count += 1
            self.scan_count += 1
            
            if resp.status_code == 401:
                print("[!] Token expiré - relance auth_capture.py")
                return None
            elif resp.status_code == 429:
                print("[!] Rate limit - pause longue")
                time.sleep(random.uniform(60, 120))
                return None
            elif resp.status_code != 200:
                print(f"[!] Erreur API: {resp.status_code}")
                return None
            
            return resp.json()
            
        except Exception as e:
            print(f"[!] Erreur requête: {e}")
            return None
    
    def calculate_profit(self, buy_price, sell_price):
        """Calcule le profit net après taxe"""
        net_sell = sell_price * (1 - TAX_RATE)
        return net_sell - buy_price
    
    def is_good_deal(self, buy_now_price, estimated_sell_price):
        """Vérifie si c'est une bonne affaire"""
        if buy_now_price > MAX_BUY_PRICE:
            return False, 0
        
        profit = self.calculate_profit(buy_now_price, estimated_sell_price)
        margin = profit / buy_now_price if buy_now_price > 0 else 0
        
        if profit >= MIN_PROFIT_ABSOLUTE and margin >= MIN_PROFIT_MARGIN:
            return True, profit
        
        return False, profit
    
    def analyze_listing(self, item):
        """Analyse une annonce pour détecter une opportunité"""
        try:
            # Extraction données
            trade_id = item.get('tradeId')
            buy_now = item.get('buyNowPrice', 0)
            current_bid = item.get('currentBid', 0)
            starting_bid = item.get('startingBid', 0)
            expires = item.get('expires', 0)
            
            item_data = item.get('itemData', {})
            asset_id = item_data.get('assetId', item_data.get('resourceId'))
            rating = item_data.get('rating', 0)
            rareflag = item_data.get('rareflag', 1)  # 1=Gold Rare par défaut
            
            if not asset_id or not buy_now:
                return None
            
            # IMPORTANT: Filtrer uniquement les Gold Rare (rareflag=1)
            # On ne veut PAS comparer les prix IF/TOTW avec les Gold!
            if rareflag != 1:
                # Enregistrer quand même pour les stats, mais ne pas trader
                self.price_tracker.record_price(asset_id, buy_now, rareflag)
                return None  # On skip les versions spéciales pour l'instant
            
            # Enregistrer le prix avec le rareflag
            self.price_tracker.record_price(asset_id, buy_now, rareflag)
            
            # Récupérer prix moyen pour CETTE VERSION (Gold Rare uniquement)
            avg_price = self.price_tracker.get_average(asset_id, rareflag)
            lowest_seen = self.price_tracker.get_lowest_seen(asset_id, rareflag)
            sample_count = self.price_tracker.get_sample_count(asset_id, rareflag)
            
            # SÉCURITÉ: Besoin d'au moins 5 échantillons pour être fiable
            if sample_count < 5:
                return None  # Pas assez de données pour ce joueur
            
            if avg_price:
                # Comparer avec moyenne
                estimated_sell = int(avg_price * 0.95)  # Vente légèrement sous moyenne
                is_deal, profit = self.is_good_deal(buy_now, estimated_sell)
                
                if is_deal:
                    player_info = self.get_player_info(asset_id)
                    return {
                        'trade_id': trade_id,
                        'asset_id': asset_id,
                        'name': player_info['name'],
                        'rating': rating or player_info['rating'],
                        'rareflag': rareflag,
                        'buy_now': buy_now,
                        'avg_price': avg_price,
                        'estimated_sell': estimated_sell,
                        'profit': int(profit),
                        'margin_pct': round((profit / buy_now) * 100, 1),
                        'expires': expires,
                        'sample_count': sample_count,
                        'timestamp': time.time(),
                        'confidence': 'HIGH' if (profit > 500 and sample_count >= 10) else 'MEDIUM'
                    }
            
            return None
            
        except Exception as e:
            return None
    
    def scan_strategy(self, strategy):
        """Scanne avec une stratégie donnée"""
        name = strategy['name']
        params = strategy['params']
        
        print(f"\n[SCAN] {name}")
        
        opportunities = []
        
        for page in range(PAGES_PER_SCAN):
            result = self.search_market(params, page)
            
            if not result:
                break
            
            auctions = result.get('auctionInfo', [])
            print(f"  Page {page + 1}: {len(auctions)} annonces")
            
            for item in auctions:
                opp = self.analyze_listing(item)
                if opp:
                    opportunities.append(opp)
                    print(f"  [💰] {opp['name']} ({opp['rating']}) - "
                          f"Achat: {opp['buy_now']} | Profit: +{opp['profit']} CR ({opp['margin_pct']}%)")
            
            # Délai avant page suivante
            if page < PAGES_PER_SCAN - 1:
                time.sleep(self.pareto_delay())
        
        return opportunities
    
    def run_full_scan(self):
        """Lance un scan complet de toutes les stratégies"""
        print("\n" + "=" * 60)
        print(f"   SCAN GLOBAL - {datetime.now().strftime('%H:%M:%S')}")
        print("=" * 60)
        
        all_opportunities = []
        
        # Mélanger les stratégies (anti-pattern)
        strategies = SCAN_STRATEGIES.copy()
        random.shuffle(strategies)
        
        for strategy in strategies[:5]:  # Max 5 stratégies par scan
            opps = self.scan_strategy(strategy)
            all_opportunities.extend(opps)
            
            # Délai entre stratégies
            delay = self.pareto_delay() * 1.5
            print(f"  [⏳] Pause {delay:.1f}s...")
            time.sleep(delay)
        
        # Trier par profit
        all_opportunities.sort(key=lambda x: x['profit'], reverse=True)
        
        # Sauvegarder
        self.save_opportunities(all_opportunities[:10])  # Top 10
        self.price_tracker.save_cache()
        
        print(f"\n[RÉSUMÉ] {len(all_opportunities)} opportunités détectées")
        print(f"[STATS] Requêtes cette session: {self.scan_count}")
        print(f"[STATS] Requêtes cette heure: {self.hourly_count}/{MAX_SCANS_PER_HOUR}")
        
        return all_opportunities
    
    def save_opportunities(self, opportunities):
        """Sauvegarde les opportunités pour le worker"""
        targets = []
        
        for opp in opportunities:
            targets.append({
                "player_id": opp['asset_id'],
                "player_name": opp['name'],
                "max_buy_price": opp['buy_now'],
                "target_sell_price": opp['estimated_sell'],
                "expected_profit": opp['profit'],
                "confidence": opp['confidence'],
                "expires_at": time.time() + 300,  # Valide 5 min
                "source": "global_scan"
            })
        
        output = {
            "generated_at": datetime.now().isoformat(),
            "scan_count": self.scan_count,
            "targets": targets
        }
        
        with open(TARGETS_FILE, 'w') as f:
            json.dump(output, f, indent=2)
        
        print(f"[✓] {len(targets)} cibles sauvegardées → {TARGETS_FILE}")
    
    def run_continuous(self, interval_minutes=5):
        """Mode continu avec scans réguliers"""
        print("\n" + "=" * 60)
        print("   GLOBAL MARKET SCANNER - MODE CONTINU")
        print("=" * 60)
        print(f"Intervalle: {interval_minutes} minutes")
        print(f"Limite horaire: {MAX_SCANS_PER_HOUR} requêtes")
        print("Ctrl+C pour arrêter\n")
        
        try:
            while True:
                self.run_full_scan()
                
                # Attendre avant prochain scan
                wait = interval_minutes * 60 + random.uniform(-30, 30)
                print(f"\n[💤] Prochain scan dans {wait/60:.1f} minutes...")
                time.sleep(wait)
                
        except KeyboardInterrupt:
            print("\n[STOP] Scanner arrêté")
            self.price_tracker.save_cache()


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import sys
    
    scanner = GlobalScanner()
    
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        # Scan unique
        scanner.run_full_scan()
    else:
        # Mode continu
        interval = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        scanner.run_continuous(interval_minutes=interval)
