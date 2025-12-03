"""
HARD SNIPER v2 - Détection d'anomalies temps réel
=================================================
- Prix de référence: FUTBIN (stable, fiable) -> fodder_targets.json
- Scan temps réel: EA Market pour trouver les anomalies
- Achat si: prix EA < SEUIL% du prix Futbin
- Notifications Discord via webhook
"""

import json
import time
import random
import requests
from datetime import datetime

# ==================== CONFIG ====================
BASE_URL = "https://utas.mob.v5.prd.futc-ext.gcp.ea.com/ut/game/fc26"

# Discord Webhook (mettre ton URL ici)
DISCORD_WEBHOOK_URL = ""  # Ex: "https://discord.com/api/webhooks/123456/abcdef..."
DISCORD_ENABLED = False    # Passer à True une fois le webhook configuré

# Notes à surveiller - toutes les notes fodder
TARGET_RATINGS = [83, 84, 85, 86, 87, 88, 89, 90]

# Prix minimum EA par note (impossible de vendre en dessous)
EA_MIN_PRICE = {
    83: 700,
    84: 700,
    85: 700,
    86: 750,
    87: 800,
    88: 850,
    89: 900,
    90: 950,
    91: 1000,
    92: 1100
}

# Seuil d'anomalie: acheter si prix < X% du prix Futbin
ANOMALY_THRESHOLD = 0.85  # 85% = -15% sous le marché Futbin

# Timing (anti-ban)
SCAN_DELAY_MIN = 2.0      # Délai min entre scans par note
SCAN_DELAY_MAX = 4.0      # Délai max entre scans par note
CYCLE_PAUSE = 8           # Pause entre cycles complets

# Budget
MAX_BUDGET_PER_CARD = 30000  # Budget max par carte
MAX_PURCHASE_PER_CYCLE = 3   # Max achats par cycle (anti-flood)

# ==================== DISCORD ====================
def send_discord_notification(title, description, color=0x00ff00, fields=None):
    """Envoie une notification Discord via webhook"""
    if not DISCORD_ENABLED or not DISCORD_WEBHOOK_URL:
        return
    
    embed = {
        "title": title,
        "description": description,
        "color": color,
        "timestamp": datetime.utcnow().isoformat(),
        "footer": {"text": "FC Bot Sniper"}
    }
    
    if fields:
        embed["fields"] = fields
    
    payload = {"embeds": [embed]}
    
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=5)
    except:
        pass  # Silencieux si Discord échoue

def notify_snipe(player, rating, price, futbin_price, profit):
    """Notification de snipe réussi"""
    send_discord_notification(
        title="🎯 SNIPE RÉUSSI!",
        description=f"**{player}** (Note {rating})",
        color=0x00ff00,  # Vert
        fields=[
            {"name": "💰 Prix d'achat", "value": f"{price:,} CR", "inline": True},
            {"name": "📊 Prix Futbin", "value": f"{futbin_price:,} CR", "inline": True},
            {"name": "📈 Profit estimé", "value": f"+{profit:,} CR", "inline": True},
            {"name": "⏰ Heure", "value": datetime.now().strftime("%H:%M:%S"), "inline": True}
        ]
    )

def notify_session_expired():
    """Notification de session expirée"""
    send_discord_notification(
        title="❌ SESSION EXPIRÉE",
        description="Le token EA a expiré. Relance le bot après extraction d'un nouveau token.",
        color=0xff0000  # Rouge
    )

def notify_bot_started():
    """Notification de démarrage du bot"""
    send_discord_notification(
        title="🚀 BOT DÉMARRÉ",
        description=f"Hard Sniper actif - Notes surveillées: {TARGET_RATINGS}",
        color=0x3498db,  # Bleu
        fields=[
            {"name": "Seuil anomalie", "value": f"{int(ANOMALY_THRESHOLD*100)}%", "inline": True},
            {"name": "Max achats/cycle", "value": str(MAX_PURCHASE_PER_CYCLE), "inline": True}
        ]
    )

# ==================== LOAD CONFIG ====================
def load_session():
    """Charge le token de session EA"""
    try:
        with open("active_session.json", "r") as f:
            return json.load(f)
    except:
        print("❌ Erreur: active_session.json introuvable")
        return None

def load_futbin_prices():
    """Charge les prix Futbin comme référence depuis fodder_targets.json"""
    try:
        with open("fodder_targets.json", "r") as f:
            data = json.load(f)
        
        prices = {}
        for target in data.get("targets", []):
            rating = target["rating"]
            # sell_price = prix Futbin marché
            # max_buy = prix achat safe calculé par futbin_pricer
            prices[rating] = {
                "futbin_price": target["sell_price"],
                "max_buy": target["max_buy"]
            }
        
        return prices
    except Exception as e:
        print(f"❌ Erreur chargement fodder_targets.json: {e}")
        return {}

def get_headers(session):
    """Headers pour les requêtes EA"""
    return {
        "X-UT-SID": session["x-ut-sid"],
        "User-Agent": session.get("user_agent", "Mozilla/5.0"),
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

# ==================== EA API ====================
def search_market(session, rating, max_price=None):
    """
    Recherche sur le marché EA pour une note donnée
    Filtre: Gold, Rare, note exacte
    """
    headers = get_headers(session)
    
    params = {
        "type": "player",
        "rarityIds": "1",          # Gold Rare uniquement
        "lev": "gold",
        "ovr_min": rating,
        "ovr_max": rating,
        "num": 21,                 # Max résultats
        "start": 0
    }
    
    if max_price:
        params["maxb"] = max_price
    
    url = f"{BASE_URL}/transfermarket"
    
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        
        if resp.status_code == 401:
            print("❌ Token expiré! Relancer l'extraction.")
            return None
        
        if resp.status_code == 429:
            print("⚠️ Rate limit - pause 60s")
            time.sleep(60)
            return []
        
        if resp.status_code != 200:
            print(f"⚠️ Erreur API: {resp.status_code}")
            return []
        
        data = resp.json()
        return data.get("auctionInfo", [])
        
    except Exception as e:
        print(f"⚠️ Erreur requête: {e}")
        return []

def buy_card(session, trade_id, price):
    """Achète une carte sur le marché (BIN)"""
    headers = get_headers(session)
    url = f"{BASE_URL}/trade/{trade_id}/bid"
    
    payload = {"bid": price}
    
    try:
        resp = requests.put(url, headers=headers, json=payload, timeout=10)
        return resp.status_code == 200
    except:
        return False

def send_to_tradepile(session, item_id):
    """Envoie une carte dans la pile de transfert"""
    headers = get_headers(session)
    url = f"{BASE_URL}/item"
    
    payload = {"itemData": [{"id": item_id, "pile": "trade"}]}
    
    try:
        resp = requests.put(url, headers=headers, json=payload, timeout=10)
        return resp.status_code == 200
    except:
        return False

def list_card_for_sale(session, item_id, start_price, buy_now):
    """Met une carte en vente"""
    headers = get_headers(session)
    url = f"{BASE_URL}/auctionhouse"
    
    payload = {
        "itemData": {"id": item_id},
        "startingBid": start_price,
        "duration": 3600,  # 1 heure
        "buyNowPrice": buy_now
    }
    
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        return resp.status_code == 200
    except:
        return False

# ==================== SNIPER LOGIC ====================
def gaussian_delay(min_d, max_d):
    """Délai gaussien pour paraître humain"""
    mean = (min_d + max_d) / 2
    std = (max_d - min_d) / 4
    delay = random.gauss(mean, std)
    return max(min_d, min(max_d, delay))

def scan_for_anomalies(session, futbin_prices):
    """
    Scan le marché EA et compare aux prix Futbin
    Retourne les anomalies détectées (prix bien sous Futbin)
    """
    anomalies = []
    
    for rating in TARGET_RATINGS:
        if rating not in futbin_prices:
            continue
        
        ref = futbin_prices[rating]
        futbin_price = ref["futbin_price"]
        
        # Prix seuil = X% du prix Futbin
        threshold_price = int(futbin_price * ANOMALY_THRESHOLD)
        
        # Vérifier que le seuil est au-dessus du prix plancher EA
        min_ea_price = EA_MIN_PRICE.get(rating, 700)
        if threshold_price <= min_ea_price:
            print(f"  [Note {rating}] ⏭️ Skip - seuil {threshold_price} <= plancher EA {min_ea_price}")
            continue
        
        print(f"  [Note {rating}] Futbin: {futbin_price} CR | Cherche {min_ea_price}-{threshold_price} CR")
        
        # Recherche EA avec prix max = seuil anomalie
        auctions = search_market(session, rating, max_price=threshold_price)
        
        if auctions is None:  # Token expiré
            return None
        
        if auctions:
            for auction in auctions:
                buy_now = auction.get("buyNowPrice", 0)
                player_data = auction.get("itemData", {})
                actual_rating = player_data.get("rating", 0)
                
                # IMPORTANT: Vérifier que la note RÉELLE correspond
                if actual_rating != rating:
                    continue  # Skip si note différente
                
                if buy_now > 0 and buy_now <= threshold_price:
                    player_name = player_data.get("lastName", "Unknown")
                    
                    anomalies.append({
                        "trade_id": auction["tradeId"],
                        "item_id": player_data["id"],
                        "rating": actual_rating,
                        "price": buy_now,
                        "futbin_price": futbin_price,
                        "discount": round((1 - buy_now/futbin_price) * 100, 1),
                        "player": player_name
                    })
        
        # Délai anti-ban entre chaque note
        time.sleep(gaussian_delay(SCAN_DELAY_MIN, SCAN_DELAY_MAX))
    
    return anomalies

def process_anomalies(session, anomalies, futbin_prices):
    """Traite les anomalies: achat + mise en vente"""
    purchases = 0
    
    # Trier par meilleur discount (les meilleures affaires d'abord)
    anomalies.sort(key=lambda x: x["discount"], reverse=True)
    
    for anomaly in anomalies:
        if purchases >= MAX_PURCHASE_PER_CYCLE:
            print(f"  ⏸️ Max achats atteint ({MAX_PURCHASE_PER_CYCLE})")
            break
        
        trade_id = anomaly["trade_id"]
        item_id = anomaly["item_id"]
        price = anomaly["price"]
        rating = anomaly["rating"]
        discount = anomaly["discount"]
        player = anomaly["player"]
        futbin_price = anomaly["futbin_price"]
        
        print(f"\n  🎯 ANOMALIE: {player} (Note {rating})")
        print(f"     Prix: {price} CR | Futbin: {futbin_price} CR | -{discount}%")
        
        # Tentative d'achat
        if buy_card(session, trade_id, price):
            print(f"     ✅ ACHETÉ!")
            purchases += 1
            
            # Calculer profit pour la notification
            profit = int(futbin_price * 0.95 - price)
            
            # Notification Discord
            notify_snipe(player, rating, price, futbin_price, profit)
            
            # Attendre un peu
            time.sleep(1)
            
            # Envoyer dans pile de transfert
            if send_to_tradepile(session, item_id):
                # Mettre en vente au prix Futbin (ou légèrement en dessous)
                sell_price = futbin_price
                start_price = int(sell_price * 0.9)
                
                if list_card_for_sale(session, item_id, start_price, sell_price):
                    print(f"     📤 En vente: {sell_price} CR | Profit estimé: +{profit} CR")
                else:
                    print(f"     ⚠️ Échec mise en vente (pile pleine?)")
            else:
                print(f"     ⚠️ Échec envoi tradepile")
        else:
            print(f"     ❌ Raté (déjà vendu ou outbid)")
        
        # Petit délai entre achats
        time.sleep(gaussian_delay(1.0, 2.0))
    
    return purchases

# ==================== MAIN ====================
def main():
    print("\n" + "="*60)
    print("   🎯 HARD SNIPER v2 - Futbin + EA Temps Réel")
    print("="*60)
    
    # Charger session
    session = load_session()
    if not session:
        return
    
    # Charger prix Futbin comme référence
    futbin_prices = load_futbin_prices()
    if not futbin_prices:
        print("❌ Aucun prix Futbin chargé! Lance d'abord futbin_pricer.py")
        return
    
    print(f"\n📊 Référentiel Futbin PC:")
    for rating in TARGET_RATINGS:
        if rating in futbin_prices:
            p = futbin_prices[rating]
            threshold = int(p["futbin_price"] * ANOMALY_THRESHOLD)
            print(f"  Note {rating}: {p['futbin_price']} CR -> Anomalie si < {threshold} CR")
    
    print(f"\n⚙️ Config:")
    print(f"  - Seuil anomalie: {int(ANOMALY_THRESHOLD*100)}% du Futbin (-{int((1-ANOMALY_THRESHOLD)*100)}%)")
    print(f"  - Délai entre notes: {SCAN_DELAY_MIN}-{SCAN_DELAY_MAX}s")
    print(f"  - Pause entre cycles: {CYCLE_PAUSE}s")
    print(f"  - Max achats/cycle: {MAX_PURCHASE_PER_CYCLE}")
    print(f"  - Discord: {'✅ Activé' if DISCORD_ENABLED else '❌ Désactivé'}")
    
    total_purchases = 0
    cycle = 0
    
    print(f"\n🚀 Démarrage du sniper...")
    print("-"*60)
    
    # Notification Discord au démarrage
    notify_bot_started()
    
    try:
        while True:
            cycle += 1
            print(f"\n[Cycle {cycle}] {datetime.now().strftime('%H:%M:%S')} - Scan en cours...")
            
            # Scanner les anomalies
            anomalies = scan_for_anomalies(session, futbin_prices)
            
            if anomalies is None:  # Token expiré
                print("\n❌ Session expirée. Relancer le bot après extraction token.")
                notify_session_expired()
                break
            
            if anomalies:
                print(f"\n  🔥 {len(anomalies)} anomalie(s) détectée(s)!")
                purchases = process_anomalies(session, anomalies, futbin_prices)
                total_purchases += purchases
                print(f"\n  📈 Total achats session: {total_purchases}")
            else:
                print(f"  ✓ RAS - Aucune anomalie")
            
            # Pause entre cycles
            pause = gaussian_delay(CYCLE_PAUSE * 0.8, CYCLE_PAUSE * 1.2)
            print(f"\n  ⏳ Prochain scan dans {pause:.1f}s...")
            time.sleep(pause)
            
    except KeyboardInterrupt:
        print(f"\n\n🛑 Arrêt manuel")
        print(f"📊 Bilan: {total_purchases} cartes achetées")

if __name__ == "__main__":
    main()
