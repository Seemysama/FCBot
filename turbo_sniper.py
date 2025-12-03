"""
TURBO SNIPER - Mode agressif avec monitoring complet
=====================================================
- Scan d'UNE seule note en boucle rapide
- Nom complet du joueur dans les notifications
- Solde du compte affiché périodiquement
- Alertes Discord en cas d'erreur
- Stats détaillées
"""

import json
import time
import requests
from datetime import datetime

# ==================== CONFIG ====================
BASE_URL = "https://utas.mob.v5.prd.futc-ext.gcp.ea.com/ut/game/fc26"

# Note ciblée (une seule pour max vitesse)
TARGET_RATING = 83  # Changer ici pour scanner une autre note

# Plages d'achat par note: (min_buy, max_buy, sell_price)
PRICE_RANGES = {
    83: {"min": 700, "max": 900, "sell": 1000},     # Profit: 50-250 CR
    84: {"min": 800, "max": 1100, "sell": 1200},    # Profit: 40-340 CR  
    85: {"min": 2200, "max": 2800, "sell": 3000},   # Profit: 50-650 CR
    86: {"min": 4500, "max": 5500, "sell": 6000},   # Profit: 200-1200 CR
    87: {"min": 7500, "max": 9000, "sell": 10000},  # Profit: 500-2000 CR
    88: {"min": 11000, "max": 13500, "sell": 15000},# Profit: 250-3250 CR
}

# Timing - safe pour éviter ban EA
SCAN_DELAY = 2.0      # 2s entre chaque scan
BALANCE_CHECK_INTERVAL = 50  # Vérifier le solde tous les X scans

# Discord
DISCORD_WEBHOOK_URL = "https://discordapp.com/api/webhooks/1445904312327995422/-5Ha4PIjw07NYN_kdCT7Tw0jOu_dTuoZyVcokVKYqGO5toS9ZZUsmGodG0elfM7no0RA"
DISCORD_ENABLED = True

# ==================== FUNCTIONS ====================
def load_session():
    with open("active_session.json", "r") as f:
        return json.load(f)

def get_headers(session):
    return {
        "X-UT-SID": session["x-ut-sid"],
        "User-Agent": session.get("user_agent", "Mozilla/5.0"),
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

def get_coins(session):
    """Récupère le solde du compte"""
    headers = get_headers(session)
    url = f"{BASE_URL}/user/credits"
    
    try:
        resp = requests.get(url, headers=headers, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("credits", 0)
        return None
    except:
        return None

def get_tradepile_status(session):
    """Récupère le statut de la pile de transfert"""
    headers = get_headers(session)
    url = f"{BASE_URL}/tradepile"
    
    try:
        resp = requests.get(url, headers=headers, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("auctionInfo", [])
            selling = sum(1 for i in items if i.get("tradeState") == "active")
            sold = sum(1 for i in items if i.get("tradeState") == "closed")
            return {"total": len(items), "selling": selling, "sold": sold}
        return None
    except:
        return None

def search_market(session, rating, max_price):
    """Recherche sur le marché"""
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
    
    url = f"{BASE_URL}/transfermarket"
    
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=5)
        
        if resp.status_code == 401:
            return "TOKEN_EXPIRED"
        if resp.status_code == 429:
            return "RATE_LIMIT"
        if resp.status_code != 200:
            return "ERROR"
        
        return resp.json().get("auctionInfo", [])
    except Exception as e:
        return "NETWORK_ERROR"

def buy_now(session, trade_id, price):
    """Achat instantané"""
    headers = get_headers(session)
    url = f"{BASE_URL}/trade/{trade_id}/bid"
    
    try:
        resp = requests.put(url, headers=headers, json={"bid": price}, timeout=3)
        if resp.status_code == 200:
            return "SUCCESS"
        elif resp.status_code == 461:
            return "ALREADY_SOLD"
        elif resp.status_code == 401:
            return "TOKEN_EXPIRED"
        else:
            return f"ERROR_{resp.status_code}"
    except:
        return "NETWORK_ERROR"

def send_to_pile(session, item_id):
    """Envoie en pile de transfert"""
    headers = get_headers(session)
    url = f"{BASE_URL}/item"
    
    try:
        resp = requests.put(url, headers=headers, json={"itemData": [{"id": item_id, "pile": "trade"}]}, timeout=3)
        return resp.status_code == 200
    except:
        return False

def list_for_sale(session, item_id, sell_price):
    """Met en vente"""
    headers = get_headers(session)
    url = f"{BASE_URL}/auctionhouse"
    
    payload = {
        "itemData": {"id": item_id},
        "startingBid": int(sell_price * 0.9),
        "duration": 3600,
        "buyNowPrice": sell_price
    }
    
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=3)
        return resp.status_code == 200
    except:
        return False

def notify_discord(message, is_error=False):
    """Envoie une notification Discord"""
    if DISCORD_ENABLED and DISCORD_WEBHOOK_URL:
        try:
            # Ajouter timestamp
            timestamp = datetime.now().strftime("%H:%M:%S")
            full_message = f"[{timestamp}] {message}"
            
            requests.post(DISCORD_WEBHOOK_URL, json={"content": full_message}, timeout=3)
        except:
            pass

def format_coins(amount):
    """Formate les coins avec séparateurs"""
    return f"{amount:,}".replace(",", " ")

def get_player_name(player_data):
    """Récupère le nom complet du joueur"""
    first_name = player_data.get("firstName", "")
    last_name = player_data.get("lastName", "")
    
    if first_name and last_name:
        return f"{first_name} {last_name}"
    elif last_name:
        return last_name
    elif first_name:
        return first_name
    else:
        return "Joueur inconnu"

# ==================== MAIN ====================
def main():
    print("\n" + "="*60)
    print("   ⚡ TURBO SNIPER - Mode Monitoring Complet")
    print("="*60)
    
    session = load_session()
    rating = TARGET_RATING
    
    # Récupérer la plage pour cette note
    if rating not in PRICE_RANGES:
        print(f"❌ Note {rating} non configurée dans PRICE_RANGES")
        return
    
    price_config = PRICE_RANGES[rating]
    min_buy = price_config["min"]
    max_buy = price_config["max"]
    sell_price = price_config["sell"]
    
    # Vérifier le solde initial
    initial_coins = get_coins(session)
    if initial_coins is None:
        print("❌ Impossible de récupérer le solde - Token invalide?")
        notify_discord("❌ Erreur: Impossible de récupérer le solde initial")
        return
    
    print(f"\n💰 Solde initial: {format_coins(initial_coins)} CR")
    print(f"🎯 Cible: Note {rating}")
    print(f"💵 Plage achat: {min_buy} - {max_buy} CR")
    print(f"📤 Prix vente: {sell_price} CR")
    print(f"📊 Profit potentiel: +{int(sell_price * 0.95 - max_buy)} à +{int(sell_price * 0.95 - min_buy)} CR")
    print(f"⚡ Délai: {SCAN_DELAY}s entre scans")
    
    # Notifier Discord du démarrage
    notify_discord(f"🚀 **Bot démarré!**\n💰 Solde: {format_coins(initial_coins)} CR\n🎯 Cible: Note {rating} ({min_buy}-{max_buy} CR)")
    
    total_buys = 0
    total_profit = 0
    scans = 0
    errors = 0
    start_time = time.time()
    last_coins = initial_coins
    
    print(f"\n🚀 GO! Scan en cours...")
    print("-"*60)
    
    try:
        while True:
            scans += 1
            
            # Recherche avec le MAX de la plage
            auctions = search_market(session, rating, max_buy)
            
            # Gestion des erreurs
            if auctions == "TOKEN_EXPIRED":
                print("\n❌ Token expiré!")
                notify_discord("🚨 **ERREUR:** Token EA expiré - Relancer le bot!")
                break
            elif auctions == "RATE_LIMIT":
                errors += 1
                print("\n⚠️ Rate limit! Pause 60s...")
                notify_discord("⚠️ Rate limit EA - Pause 60s")
                time.sleep(60)
                continue
            elif auctions == "NETWORK_ERROR":
                errors += 1
                print("\n⚠️ Erreur réseau, retry...")
                time.sleep(5)
                continue
            elif auctions == "ERROR":
                errors += 1
                time.sleep(2)
                continue
            
            # Trier par prix croissant pour favoriser les moins chers
            auctions = sorted(auctions, key=lambda x: x.get("buyNowPrice", 999999))
            
            # Traiter les résultats
            for auction in auctions:
                buy_price = auction.get("buyNowPrice", 0)
                player_data = auction.get("itemData", {})
                actual_rating = player_data.get("rating", 0)
                
                # Vérifier la note
                if actual_rating != rating:
                    continue
                
                # Vérifier que le prix est dans la plage
                if buy_price > 0 and buy_price >= min_buy and buy_price <= max_buy:
                    trade_id = auction["tradeId"]
                    item_id = player_data["id"]
                    player_name = get_player_name(player_data)
                    
                    # ACHAT INSTANTANÉ
                    result = buy_now(session, trade_id, buy_price)
                    
                    if result == "SUCCESS":
                        profit = int(sell_price * 0.95 - buy_price)
                        total_buys += 1
                        total_profit += profit
                        
                        # Indicateur de qualité du snipe
                        quality = "🔥 MEGA" if buy_price <= min_buy + 50 else "✅"
                        
                        print(f"\n{quality} SNIPE! {player_name} ({rating}) | {buy_price} CR | +{profit} CR")
                        notify_discord(f"🎯 **SNIPE!** {player_name} ({rating})\n💰 Acheté: {buy_price} CR\n📈 Profit estimé: +{profit} CR\n📊 Total session: {total_buys} achats | +{total_profit} CR")
                        
                        # Mettre en vente
                        time.sleep(0.5)
                        if send_to_pile(session, item_id):
                            if list_for_sale(session, item_id, sell_price):
                                print(f"   📤 En vente: {sell_price} CR")
                        
                        # Petite pause après achat
                        time.sleep(2)
                        
                    elif result == "ALREADY_SOLD":
                        print(f"\r⚡ Raté: {player_name} déjà vendu", end="", flush=True)
                    elif result == "TOKEN_EXPIRED":
                        print("\n❌ Token expiré pendant l'achat!")
                        notify_discord("🚨 **ERREUR:** Token expiré pendant un achat!")
                        return
            
            # Vérification périodique du solde et stats
            if scans % BALANCE_CHECK_INTERVAL == 0:
                elapsed = time.time() - start_time
                rate = scans / elapsed * 60
                
                # Récupérer le solde actuel
                current_coins = get_coins(session)
                tradepile = get_tradepile_status(session)
                
                if current_coins:
                    coin_diff = current_coins - last_coins
                    last_coins = current_coins
                    
                    status = f"\n📊 [{scans} scans | {rate:.0f}/min | {total_buys} achats]"
                    status += f"\n💰 Solde: {format_coins(current_coins)} CR"
                    if coin_diff != 0:
                        sign = "+" if coin_diff > 0 else ""
                        status += f" ({sign}{format_coins(coin_diff)})"
                    
                    if tradepile:
                        status += f"\n📦 Pile: {tradepile['selling']} en vente | {tradepile['sold']} vendus"
                    
                    if errors > 0:
                        status += f"\n⚠️ Erreurs: {errors}"
                    
                    print(status)
                    
                    # Notif Discord toutes les 5 mins environ (150 scans à 2s)
                    if scans % 150 == 0:
                        notify_discord(f"📊 **Status**\n💰 Solde: {format_coins(current_coins)} CR\n🛒 Achats: {total_buys} | Profit: +{total_profit} CR\n📦 Pile: {tradepile['selling'] if tradepile else '?'} en vente")
            
            # Délai entre scans
            time.sleep(SCAN_DELAY)
            
    except KeyboardInterrupt:
        pass
    
    # Bilan final
    elapsed = time.time() - start_time
    final_coins = get_coins(session) or last_coins
    real_profit = final_coins - initial_coins
    
    print(f"\n\n{'='*60}")
    print(f"🛑 ARRÊT après {scans} scans en {elapsed/60:.1f} min")
    print(f"{'='*60}")
    print(f"📊 Achats: {total_buys}")
    print(f"💵 Profit estimé: +{total_profit} CR")
    print(f"💰 Solde final: {format_coins(final_coins)} CR")
    print(f"📈 Gain réel: {'+' if real_profit >= 0 else ''}{format_coins(real_profit)} CR")
    if errors > 0:
        print(f"⚠️ Erreurs rencontrées: {errors}")
    
    notify_discord(f"🛑 **Bot arrêté**\n⏱️ Durée: {elapsed/60:.1f} min\n🛒 Achats: {total_buys}\n💰 Solde: {format_coins(final_coins)} CR\n📈 Gain: {'+' if real_profit >= 0 else ''}{format_coins(real_profit)} CR")

if __name__ == "__main__":
    main()
