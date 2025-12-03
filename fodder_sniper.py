"""
=============================================================================
                    FODDER SNIPER - Volume Trading
=============================================================================
Snipe les cartes Gold Rare sous-évaluées pour revente rapide.

STRATÉGIE:
- Acheter sous le prix minimum du marché
- Revendre rapidement avec petite marge
- Volume > Marge unitaire

EXEMPLE 85 Gold Rare:
- Marché min: ~2800 CR
- Acheter: < 2500 CR
- Revendre: 3000-3200 CR  
- Profit: 350-500 CR/carte
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
SNIPE_LOG_FILE = "snipe_log.json"

EA_BASE_URL = "https://utas.mob.v5.prd.futc-ext.gcp.ea.com/ut/game/fc26"

# Timing anti-ban (MODE ÉQUILIBRÉ)
# Un joueur actif mais pas robot : ~4-6 recherches/minute
SCAN_DELAY_MIN = 8.0       # Délai min entre scans (8 sec)
SCAN_DELAY_MAX = 18.0      # Délai max entre scans (18 sec)
POST_BUY_PAUSE_MIN = 15.0  # Pause min après achat
POST_BUY_PAUSE_MAX = 40.0  # Pause max après achat

# Limites de sécurité (Nuit 1 - validées)
MAX_BUYS_PER_HOUR = 30     # 30 achats/heure max (assurance anti-ban)
MAX_SCANS_PER_HOUR = 300   # ~5 scans/min max
# PAS de limite CR/heure - on laisse le bot manger s'il y a des opportunités

# Comportement humain
JITTER_PROBABILITY = 0.20  # 20% de chance de pause longue aléatoire
JITTER_MIN = 5.0           # Pause jitter min
JITTER_MAX = 20.0          # Pause jitter max

# Stratégies de snipe par note - PRIX DE RÉFÉRENCE (sera écrasé par Futbin)
# Ces prix sont des fallbacks si fodder_targets.json n'existe pas
SNIPE_CONFIGS = {
    83: {"max_buy": 1100, "sell_target": 1500, "min_profit": 200},
    84: {"max_buy": 1900, "sell_target": 2500, "min_profit": 300},
    85: {"max_buy": 3400, "sell_target": 4200, "min_profit": 400},
    86: {"max_buy": 7800, "sell_target": 9000, "min_profit": 600},
    87: {"max_buy": 11500, "sell_target": 13500, "min_profit": 1000},
    88: {"max_buy": 16500, "sell_target": 19000, "min_profit": 1200},
    89: {"max_buy": 22000, "sell_target": 26000, "min_profit": 2000},
    90: {"max_buy": 29000, "sell_target": 34000, "min_profit": 2500},
}

FODDER_TARGETS_FILE = "fodder_targets.json"

TAX_RATE = 0.05


def load_futbin_prices():
    """Charge les prix Futbin si disponibles"""
    if not os.path.exists(FODDER_TARGETS_FILE):
        print(f"[!] {FODDER_TARGETS_FILE} non trouvé - utilisation prix par défaut")
        return None
    
    try:
        with open(FODDER_TARGETS_FILE, 'r') as f:
            data = json.load(f)
        
        targets = data.get('targets', [])
        if not targets:
            return None
        
        # Convertir en dictionnaire par rating
        prices = {}
        for t in targets:
            rating = t.get('rating')
            if rating:
                prices[rating] = {
                    'max_buy': t.get('max_buy'),
                    'sell_target': t.get('market_price'),
                    'min_profit': t.get('estimated_profit', 200),
                }
        
        source = data.get('source', 'unknown')
        generated = data.get('generated_at', 'unknown')
        print(f"[FUTBIN] Prix chargés: {len(prices)} notes (source: {source}, màj: {generated[:16]})")
        
        return prices
    except Exception as e:
        print(f"[!] Erreur chargement Futbin: {e}")
        return None


class FodderSniper:
    """Sniper de fodder Gold Rare"""
    
    def __init__(self, target_rating=85):
        self.session = self.load_session()
        self.target_rating = target_rating
        
        # Charger prix Futbin ou utiliser fallback
        futbin_prices = load_futbin_prices()
        if futbin_prices and target_rating in futbin_prices:
            self.config = futbin_prices[target_rating]
            print(f"[CONFIG] Note {target_rating}: Prix Futbin")
        else:
            self.config = SNIPE_CONFIGS.get(target_rating, SNIPE_CONFIGS[85])
            print(f"[CONFIG] Note {target_rating}: Prix fallback")
        
        # Stats
        self.buys_this_hour = 0
        self.spent_this_hour = 0
        self.scans_this_hour = 0
        self.hour_start = time.time()
        self.total_buys = 0
        self.total_listed = 0
        self.total_profit_potential = 0
        self.snipe_log = []
    
    def load_session(self):
        with open(SESSION_FILE, 'r') as f:
            return json.load(f)
    
    def check_limits(self):
        """Vérifie les limites horaires"""
        now = time.time()
        if now - self.hour_start > 3600:
            # Reset horaire
            self.hour_start = now
            self.buys_this_hour = 0
            self.spent_this_hour = 0
            self.scans_this_hour = 0
        
        if self.buys_this_hour >= MAX_BUYS_PER_HOUR:
            return False, "Limite achats/heure atteinte (30/h)"
        if self.scans_this_hour >= MAX_SCANS_PER_HOUR:
            return False, "Limite scans/heure atteinte - pause anti-ban"
        return True, "OK"
    
    def human_delay(self):
        """Délai aléatoire qui simule un comportement humain"""
        base = random.uniform(SCAN_DELAY_MIN, SCAN_DELAY_MAX)
        
        # 20% de chance de pause plus longue (jitter - casse la linéarité)
        if random.random() < JITTER_PROBABILITY:
            base += random.uniform(JITTER_MIN, JITTER_MAX)
            print(f"  💤 Pause humaine {base:.1f}s...")
        
        return base
    
    def api_request(self, method, endpoint, params=None, data=None):
        """Requête API EA"""
        url = f"{EA_BASE_URL}/{endpoint}"
        headers = {
            "X-UT-SID": self.session['x-ut-sid'],
            "User-Agent": self.session.get('user_agent', 'Mozilla/5.0'),
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        
        try:
            if method == "GET":
                resp = requests.get(url, params=params, headers=headers, timeout=15)
            elif method == "POST":
                resp = requests.post(url, params=params, json=data, headers=headers, timeout=15)
            elif method == "PUT":
                resp = requests.put(url, params=params, json=data, headers=headers, timeout=15)
            else:
                return None
            
            return resp
        except Exception as e:
            print(f"[!] Erreur requête: {e}")
            return None
    
    def search_snipes(self):
        """Cherche des opportunités de snipe"""
        params = {
            'type': 'player',
            'raretype': '1',
            'lev': 'gold',
            'minr': self.target_rating,
            'maxr': self.target_rating,
            'maxb': self.config['max_buy'],
            'num': 21,
        }
        
        resp = self.api_request("GET", "transfermarket", params=params)
        self.scans_this_hour += 1  # Compteur anti-ban
        
        if not resp:
            return []
        
        if resp.status_code == 401:
            print("[!] Token expiré - relance l'auth")
            return None
        elif resp.status_code == 429:
            print("[!] ⚠️ RATE LIMIT DÉTECTÉ - pause 2 minutes")
            time.sleep(120)  # 2 min au lieu de 1
            return []
        elif resp.status_code != 200:
            print(f"[!] Erreur API: {resp.status_code}")
            return []
        
        data = resp.json()
        auctions = data.get('auctionInfo', [])
        
        # Filtrer les bonnes affaires
        snipes = []
        for a in auctions:
            item = a.get('itemData', {})
            rareflag = item.get('rareflag', 0)
            rating = item.get('rating', 0)
            
            if rareflag != 1:  # Gold Rare only
                continue
            
            # IMPORTANT: Vérifier le rating car l'API EA ne respecte pas toujours les filtres
            if rating != self.target_rating:
                continue
            
            buy_now = a.get('buyNowPrice', 0)
            if buy_now <= 0 or buy_now > self.config['max_buy']:
                continue
            
            # Calculer profit potentiel
            sell_price = self.config['sell_target']
            profit = int(sell_price * (1 - TAX_RATE) - buy_now)
            
            if profit >= self.config['min_profit']:
                snipes.append({
                    'trade_id': a.get('tradeId'),
                    'asset_id': item.get('assetId'),
                    'name': item.get('lastName', 'Unknown'),
                    'rating': item.get('rating', 0),
                    'buy_now': buy_now,
                    'sell_target': sell_price,
                    'profit': profit,
                    'expires': a.get('expires', 0),
                })
        
        # Trier par profit décroissant
        return sorted(snipes, key=lambda x: x['profit'], reverse=True)
    
    def buy_card(self, trade_id, price):
        """Achète une carte"""
        data = {"bid": price}
        resp = self.api_request("PUT", f"trade/{trade_id}/bid", data=data)
        
        if not resp:
            return False, "Erreur réseau", None
        
        if resp.status_code == 200:
            # Récupérer l'ID de la carte achetée
            try:
                result = resp.json()
                # L'API retourne les infos de la carte achetée
                item_id = result.get('itemData', [{}])[0].get('id') if result.get('itemData') else None
            except:
                item_id = None
            return True, "Achat réussi", item_id
        elif resp.status_code == 461:
            return False, "Carte déjà vendue", None
        elif resp.status_code == 401:
            return False, "Token expiré", None
        else:
            return False, f"Erreur {resp.status_code}", None
    
    def get_trade_pile(self):
        """Récupère les cartes dans la pile de transfert (achetées, non listées)"""
        resp = self.api_request("GET", "tradepile")
        
        if not resp or resp.status_code != 200:
            return []
        
        try:
            data = resp.json()
            return data.get('auctionInfo', [])
        except:
            return []
    
    def get_unassigned_items(self):
        """Récupère les cartes non assignées (viennent d'être achetées)"""
        resp = self.api_request("GET", "purchased/items")
        
        if not resp or resp.status_code != 200:
            return []
        
        try:
            data = resp.json()
            return data.get('itemData', [])
        except:
            return []
    
    def move_to_tradepile(self, item_id):
        """Déplace une carte vers la pile de transfert"""
        data = {"itemData": [{"id": item_id, "pile": "trade"}]}
        resp = self.api_request("PUT", "item", data=data)
        
        if resp and resp.status_code == 200:
            return True
        return False
    
    def list_card_for_sale(self, item_id, start_price, buy_now_price, duration=3600):
        """Liste une carte en vente
        
        Args:
            item_id: ID de la carte
            start_price: Prix de départ enchère
            buy_now_price: Prix d'achat immédiat
            duration: Durée en secondes (3600=1h, 21600=6h, 43200=12h, 86400=24h)
        """
        data = {
            "itemData": {
                "id": item_id
            },
            "startingBid": start_price,
            "duration": duration,
            "buyNowPrice": buy_now_price
        }
        
        resp = self.api_request("POST", "auctionhouse", data=data)
        
        if not resp:
            return False, "Erreur réseau"
        
        if resp.status_code == 200:
            return True, "Carte listée en vente"
        elif resp.status_code == 461:
            return False, "Pile de vente pleine"
        elif resp.status_code == 401:
            return False, "Token expiré"
        else:
            return False, f"Erreur {resp.status_code}"
    
    def sell_card(self, item_id, sell_price):
        """Liste une carte avec prix calculé automatiquement"""
        # Prix de départ = 90% du buy now (pour les enchères)
        start_price = int(sell_price * 0.9)
        # Arrondir aux 50 CR
        start_price = (start_price // 50) * 50
        buy_now = (sell_price // 50) * 50
        
        success, message = self.list_card_for_sale(item_id, start_price, buy_now, duration=3600)
        return success, message
    
    def process_purchased_cards(self):
        """Traite les cartes achetées : les déplace et les liste en vente"""
        # 1. Récupérer les cartes non assignées
        unassigned = self.get_unassigned_items()
        
        if not unassigned:
            return 0
        
        listed_count = 0
        sell_price = self.config['sell_target']
        
        for item in unassigned:
            item_id = item.get('id')
            rating = item.get('rating', 0)
            name = item.get('lastName', 'Unknown')
            
            if not item_id:
                continue
            
            # Vérifier que c'est la bonne note
            if rating != self.target_rating:
                continue
            
            print(f"  [VENTE] {name} ({rating}) → Listage à {sell_price} CR...")
            
            # Déplacer vers trade pile
            if self.move_to_tradepile(item_id):
                time.sleep(1)  # Petit délai
                
                # Lister en vente
                success, msg = self.sell_card(item_id, sell_price)
                if success:
                    print(f"  [✓] {name} listé à {sell_price} CR")
                    listed_count += 1
                else:
                    print(f"  [!] Échec listage: {msg}")
            else:
                print(f"  [!] Échec déplacement vers pile de vente")
            
            time.sleep(random.uniform(2, 5))  # Délai anti-ban
        
        return listed_count
    
    def log_snipe(self, snipe, success, message):
        """Log un snipe"""
        entry = {
            'timestamp': datetime.now().isoformat(),
            'name': snipe['name'],
            'rating': snipe['rating'],
            'price': snipe['buy_now'],
            'profit_target': snipe['profit'],
            'success': success,
            'message': message,
        }
        self.snipe_log.append(entry)
        
        # Sauvegarder
        with open(SNIPE_LOG_FILE, 'w') as f:
            json.dump(self.snipe_log[-100:], f, indent=2)  # Garder 100 derniers
    
    def run_cycle(self):
        """Exécute un cycle de snipe"""
        can_buy, reason = self.check_limits()
        if not can_buy:
            print(f"[LIMIT] {reason}")
            return False
        
        snipes = self.search_snipes()
        
        if snipes is None:  # Token expiré
            return None
        
        if not snipes:
            return True  # Continuer mais rien trouvé
        
        print(f"[SCAN] {len(snipes)} opportunités trouvées")
        
        # Essayer d'acheter la meilleure
        for snipe in snipes[:3]:  # Max 3 tentatives
            print(f"  → {snipe['name']} ({snipe['rating']}) @ {snipe['buy_now']} CR "
                  f"(profit: +{snipe['profit']} CR)")
            
            success, message, item_id = self.buy_card(snipe['trade_id'], snipe['buy_now'])
            
            if success:
                print(f"  ✅ ACHETÉ: {snipe['name']} @ {snipe['buy_now']} CR")
                self.buys_this_hour += 1
                self.spent_this_hour += snipe['buy_now']
                self.total_buys += 1
                self.total_profit_potential += snipe['profit']
                self.log_snipe(snipe, True, message)
                
                # Pause après achat
                pause = random.uniform(POST_BUY_PAUSE_MIN, POST_BUY_PAUSE_MAX)
                print(f"  ⏸️  Pause {pause:.1f}s avant revente...")
                time.sleep(pause)
                
                # REVENTE AUTOMATIQUE
                print(f"  [REVENTE] Traitement des cartes achetées...")
                listed = self.process_purchased_cards()
                if listed > 0:
                    print(f"  ✅ {listed} carte(s) listée(s) en vente")
                    self.total_listed += listed
                
                return True
            else:
                print(f"  ❌ {message}")
                self.log_snipe(snipe, False, message)
                
                if "Token expiré" in message:
                    return None
        
        return True
    
    def run(self, max_cycles=100):
        """Lance le sniper"""
        print("\n" + "=" * 60)
        print(f"   FODDER SNIPER (SAFE MODE) - Note {self.target_rating}")
        print("=" * 60)
        print(f"Config: Acheter < {self.config['max_buy']} CR | "
              f"Revendre {self.config['sell_target']} CR | "
              f"Profit min {self.config['min_profit']} CR")
        print(f"Timing: {SCAN_DELAY_MIN}-{SCAN_DELAY_MAX}s entre scans | "
              f"Max {MAX_SCANS_PER_HOUR} scans/h")
        print("=" * 60)
        
        cycle = 0
        while cycle < max_cycles:
            cycle += 1
            
            # Stats avec scans/heure
            scans_per_min = self.scans_this_hour / max(1, (time.time() - self.hour_start) / 60)
            print(f"\n[Cycle {cycle}/{max_cycles}] "
                  f"Achats: {self.total_buys} | "
                  f"Scans: {self.scans_this_hour}/h ({scans_per_min:.1f}/min) | "
                  f"Profit: {self.total_profit_potential} CR")
            
            result = self.run_cycle()
            
            if result is None:  # Token expiré
                print("\n[!] Token expiré - arrêt")
                break
            
            # Délai humain aléatoire
            delay = self.human_delay()
            time.sleep(delay)
        
        # Résumé final
        print("\n" + "=" * 60)
        print("   RÉSUMÉ SESSION")
        print("=" * 60)
        print(f"Cycles effectués: {cycle}")
        print(f"Cartes achetées: {self.total_buys}")
        print(f"Cartes listées: {self.total_listed}")
        print(f"CR dépensés: {self.spent_this_hour:,}")
        print(f"Profit potentiel: {self.total_profit_potential:,} CR")
        print("=" * 60)


def main():
    import sys
    
    # Note cible (défaut: 84)
    rating = int(sys.argv[1]) if len(sys.argv) > 1 else 84
    
    # Nombre de cycles (défaut: 500 pour la nuit ~4h)
    max_cycles = int(sys.argv[2]) if len(sys.argv) > 2 else 500
    
    sniper = FodderSniper(target_rating=rating)
    sniper.run(max_cycles=max_cycles)


if __name__ == "__main__":
    main()
