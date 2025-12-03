"""
SMART VOLUME TRADER - Trading cyclique jour/nuit
=================================================
Stratégie: Acheter en heures creuses, vendre en heures de pointe

Cycle optimal FC25:
- ACHAT: 00h-10h (nuit/matin = prix bas, peu de demande)
- VENTE: 18h-23h (soirée = prix hauts, forte demande)
"""

import json
import time
import random
import requests
from datetime import datetime

# ==================== CONFIG ====================
BASE_URL = "https://utas.mob.v5.prd.futc-ext.gcp.ea.com/ut/game/fc26"

# Notes à cibler (chargées depuis fodder_targets.json)
TARGET_RATINGS = [83, 84]  # Notes basses = accessibles avec peu de crédits

# Heures optimales (format 24h)
BUY_HOURS = range(0, 12)    # Acheter de minuit à midi
SELL_HOURS = range(17, 24)  # Vendre de 17h à minuit

# Limites
MAX_CARDS_TO_BUY = 50       # Max cartes à acheter par session
BUY_DELAY = 3               # Secondes entre achats
SCAN_DELAY = 2              # Secondes entre scans

# Discord (optionnel)
DISCORD_WEBHOOK = ""
DISCORD_ENABLED = False

# ==================== HELPERS ====================
def load_session():
    with open("active_session.json", "r") as f:
        return json.load(f)

def load_targets():
    """Charge les prix depuis fodder_targets.json (généré par futbin_pricer.py)"""
    try:
        with open("fodder_targets.json", "r") as f:
            data = json.load(f)
        
        targets = {}
        for t in data.get("targets", []):
            rating = t["rating"]
            if rating in TARGET_RATINGS:
                targets[rating] = {
                    "buy_max": t["max_buy"],
                    "sell_price": t["sell_price"],
                    "profit": t["estimated_profit"]
                }
        return targets
    except Exception as e:
        print(f"❌ Erreur chargement fodder_targets.json: {e}")
        return {}

def get_headers(session):
    return {
        "X-UT-SID": session["x-ut-sid"],
        "User-Agent": session.get("user_agent", "Mozilla/5.0"),
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

def notify(msg):
    print(msg)
    if DISCORD_ENABLED and DISCORD_WEBHOOK:
        try:
            requests.post(DISCORD_WEBHOOK, json={"content": msg}, timeout=3)
        except:
            pass

def is_buy_time():
    """Retourne True si c'est l'heure d'acheter"""
    return datetime.now().hour in BUY_HOURS

def is_sell_time():
    """Retourne True si c'est l'heure de vendre"""
    return datetime.now().hour in SELL_HOURS

# ==================== EA API ====================
def search_market(session, rating, max_price):
    """Recherche des cartes sur le marché"""
    headers = get_headers(session)
    
    params = {
        "type": "player",
        "rarityIds": "1",
        "lev": "gold",
        "ovr_min": rating,
        "ovr_max": rating,
        "maxb": max_price,
        "num": 21,
        "start": 0
    }
    
    try:
        resp = requests.get(f"{BASE_URL}/transfermarket", headers=headers, params=params, timeout=10)
        if resp.status_code == 401:
            return None
        if resp.status_code == 429:
            print("⚠️ Rate limit - pause 60s")
            time.sleep(60)
            return []
        if resp.status_code == 200:
            return resp.json().get("auctionInfo", [])
        return []
    except:
        return []

def buy_card(session, trade_id, price):
    """Achète une carte"""
    headers = get_headers(session)
    try:
        resp = requests.put(f"{BASE_URL}/trade/{trade_id}/bid", headers=headers, json={"bid": price}, timeout=5)
        return resp.status_code == 200
    except:
        return False

def get_tradepile(session):
    """Récupère le contenu de la pile de transfert"""
    headers = get_headers(session)
    try:
        resp = requests.get(f"{BASE_URL}/tradepile", headers=headers, timeout=10)
        if resp.status_code == 200:
            return resp.json().get("auctionInfo", [])
        return []
    except:
        return []

def get_unassigned(session):
    """Récupère les cartes non assignées (achetées)"""
    headers = get_headers(session)
    try:
        resp = requests.get(f"{BASE_URL}/purchased/items", headers=headers, timeout=10)
        if resp.status_code == 200:
            return resp.json().get("itemData", [])
        return []
    except:
        return []

def send_to_tradepile(session, item_id):
    """Envoie une carte dans la pile de transfert"""
    headers = get_headers(session)
    try:
        resp = requests.put(f"{BASE_URL}/item", headers=headers, 
                           json={"itemData": [{"id": item_id, "pile": "trade"}]}, timeout=5)
        return resp.status_code == 200
    except:
        return False

def list_card(session, item_id, start_price, buy_now):
    """Met une carte en vente"""
    headers = get_headers(session)
    payload = {
        "itemData": {"id": item_id},
        "startingBid": start_price,
        "duration": 3600,
        "buyNowPrice": buy_now
    }
    try:
        resp = requests.post(f"{BASE_URL}/auctionhouse", headers=headers, json=payload, timeout=5)
        return resp.status_code == 200
    except:
        return False

def relist_all(session):
    """Reliste toutes les cartes expirées"""
    headers = get_headers(session)
    try:
        resp = requests.put(f"{BASE_URL}/auctionhouse/relist", headers=headers, timeout=10)
        return resp.status_code == 200
    except:
        return False

# ==================== TRADING LOGIC ====================
def buy_phase(session, targets):
    """Phase d'achat - achète des fodder au prix cible"""
    print(f"\n🛒 PHASE ACHAT - {datetime.now().strftime('%H:%M')}")
    
    total_bought = 0
    
    for rating, config in targets.items():
        max_price = config["buy_max"]
        
        print(f"  Recherche Note {rating} <= {max_price} CR...")
        
        auctions = search_market(session, rating, max_price)
        
        if auctions is None:
            notify("❌ Token expiré!")
            return None
        
        for auction in auctions:
            if total_bought >= MAX_CARDS_TO_BUY:
                print(f"  ⏸️ Limite atteinte ({MAX_CARDS_TO_BUY} cartes)")
                return total_bought
            
            buy_now = auction.get("buyNowPrice", 0)
            player_data = auction.get("itemData", {})
            actual_rating = player_data.get("rating", 0)
            
            if actual_rating != rating:
                continue
            
            if buy_now > 0 and buy_now <= max_price:
                trade_id = auction["tradeId"]
                player_name = player_data.get("lastName", "?")
                
                if buy_card(session, trade_id, buy_now):
                    total_bought += 1
                    profit_est = int(config["sell_price"] * 0.95 - buy_now)
                    print(f"  ✅ {player_name} ({rating}) @ {buy_now} CR | Profit potentiel: +{profit_est}")
                    time.sleep(BUY_DELAY)
        
        time.sleep(SCAN_DELAY)
    
    return total_bought

def sell_phase(session, targets):
    """Phase de vente - liste les cartes non vendues"""
    print(f"\n💰 PHASE VENTE - {datetime.now().strftime('%H:%M')}")
    
    # 1. Relister les cartes expirées
    print("  Relisting des cartes expirées...")
    relist_all(session)
    time.sleep(1)
    
    # 2. Envoyer les cartes non assignées vers tradepile
    unassigned = get_unassigned(session)
    if unassigned:
        print(f"  {len(unassigned)} cartes non assignées à traiter...")
        for item in unassigned:
            item_id = item.get("id")
            rating = item.get("rating", 0)
            
            if send_to_tradepile(session, item_id):
                # Lister au prix de vente
                if rating in targets:
                    sell_price = targets[rating]["sell_price"]
                    start_price = int(sell_price * 0.9)
                    
                    if list_card(session, item_id, start_price, sell_price):
                        print(f"    📤 Note {rating} en vente @ {sell_price} CR")
                    
            time.sleep(0.5)
    
    # 3. Vérifier la tradepile
    tradepile = get_tradepile(session)
    active = sum(1 for a in tradepile if a.get("tradeState") == "active")
    sold = sum(1 for a in tradepile if a.get("tradeState") == "closed")
    
    print(f"  📊 Tradepile: {active} en vente | {sold} vendues")
    
    return active

# ==================== MAIN ====================
def main():
    print("\n" + "="*55)
    print("   💹 SMART VOLUME TRADER - Cycle Jour/Nuit")
    print("="*55)
    
    session = load_session()
    
    # Charger les prix Futbin
    targets = load_targets()
    if not targets:
        print("❌ Aucune cible chargée! Lance d'abord: python futbin_pricer.py")
        return
    
    print(f"\n📋 Cibles (depuis Futbin):")
    for rating, config in targets.items():
        print(f"  Note {rating}: Achat <= {config['buy_max']} | Vente {config['sell_price']} | +{config['profit']} CR")
    
    print(f"\n⏰ Horaires:")
    print(f"  Achat: {min(BUY_HOURS)}h - {max(BUY_HOURS)}h")
    print(f"  Vente: {min(SELL_HOURS)}h - {max(SELL_HOURS)}h")
    
    total_bought = 0
    cycle = 0
    
    print(f"\n🚀 Démarrage...")
    print("-"*55)
    
    try:
        while True:
            cycle += 1
            now = datetime.now()
            
            print(f"\n[Cycle {cycle}] {now.strftime('%H:%M:%S')}")
            
            if is_buy_time():
                result = buy_phase(session, targets)
                if result is None:
                    notify("❌ Session expirée - Relancer après nouveau token")
                    break
                total_bought += result
                print(f"  📈 Total acheté: {total_bought} cartes")
                
            elif is_sell_time():
                result = sell_phase(session, targets)
                if result is None:
                    notify("❌ Session expirée - Relancer après nouveau token")
                    break
                    
            else:
                # Heures intermédiaires: relister et attendre
                print(f"  ⏳ Heures creuses - Relisting uniquement")
                relist_all(session)
            
            # Pause entre cycles
            pause = random.randint(45, 90)
            print(f"  💤 Prochain cycle dans {pause}s...")
            time.sleep(pause)
            
    except KeyboardInterrupt:
        print(f"\n\n🛑 Arrêt manuel")
        print(f"📊 Total acheté cette session: {total_bought} cartes")

if __name__ == "__main__":
    main()