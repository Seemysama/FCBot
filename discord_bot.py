"""
FC SNIPER - Bot Discord Interactif
===================================
Contrôle total du sniper via Discord
"""

import discord
from discord.ext import commands, tasks
import json
import asyncio
import aiohttp
import time
import re
from datetime import datetime
import os

# ==================== CONFIG ====================
DISCORD_BOT_TOKEN = ""  # À remplir avec ton token bot Discord
DISCORD_CHANNEL_ID = None  # Canal où envoyer les notifs (auto-détecté)

BASE_URL = "https://utas.mob.v5.prd.futc-ext.gcp.ea.com/ut/game/fc26"

# Config par défaut
config = {
    "running": False,
    "target_rating": 83,
    "scan_delay": 2.0,
    "price_ranges": {
        83: {"min": 700, "max": 900, "sell": 1000},
        84: {"min": 800, "max": 1100, "sell": 1200},
        85: {"min": 2200, "max": 2800, "sell": 3000},
        86: {"min": 4500, "max": 5500, "sell": 6000},
        87: {"min": 7500, "max": 9000, "sell": 10000},
        88: {"min": 11000, "max": 13500, "sell": 15000},
    }
}

# Stats session
stats = {
    "total_buys": 0,
    "total_profit": 0,
    "scans": 0,
    "errors": 0,
    "start_time": None,
    "initial_coins": 0
}

# Session EA
ea_session = None

# ==================== DISCORD BOT ====================
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ==================== EA API FUNCTIONS ====================
def load_session():
    global ea_session
    try:
        with open("active_session.json", "r") as f:
            ea_session = json.load(f)
        return True
    except:
        return False

def get_headers():
    if not ea_session:
        return None
    return {
        "X-UT-SID": ea_session["x-ut-sid"],
        "User-Agent": ea_session.get("user_agent", "Mozilla/5.0"),
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

async def api_request(method, endpoint, json_data=None, params=None):
    """Requête async vers l'API EA"""
    headers = get_headers()
    if not headers:
        return {"error": "NO_SESSION"}
    
    url = f"{BASE_URL}/{endpoint}"
    
    try:
        async with aiohttp.ClientSession() as session:
            if method == "GET":
                async with session.get(url, headers=headers, params=params, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 401:
                        return {"error": "TOKEN_EXPIRED"}
                    if resp.status == 429:
                        return {"error": "RATE_LIMIT"}
                    if resp.status == 200:
                        return await resp.json()
                    return {"error": f"HTTP_{resp.status}"}
            elif method == "PUT":
                async with session.put(url, headers=headers, json=json_data, timeout=aiohttp.ClientTimeout(total=3)) as resp:
                    if resp.status == 200:
                        return {"success": True}
                    elif resp.status == 461:
                        return {"error": "ALREADY_SOLD"}
                    return {"error": f"HTTP_{resp.status}"}
            elif method == "POST":
                async with session.post(url, headers=headers, json=json_data, timeout=aiohttp.ClientTimeout(total=3)) as resp:
                    if resp.status == 200:
                        return {"success": True}
                    return {"error": f"HTTP_{resp.status}"}
    except asyncio.TimeoutError:
        return {"error": "TIMEOUT"}
    except Exception as e:
        return {"error": str(e)}

async def get_coins():
    data = await api_request("GET", "user/credits")
    if "error" in data:
        return None
    return data.get("credits", 0)

async def get_tradepile():
    data = await api_request("GET", "tradepile")
    if "error" in data:
        return None
    return data.get("auctionInfo", [])

async def search_market(rating, max_price):
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
    data = await api_request("GET", "transfermarket", params=params)
    if "error" in data:
        return data
    return data.get("auctionInfo", [])

async def buy_player(trade_id, price):
    return await api_request("PUT", f"trade/{trade_id}/bid", json_data={"bid": price})

async def send_to_tradepile(item_id):
    return await api_request("PUT", "item", json_data={"itemData": [{"id": item_id, "pile": "trade"}]})

async def list_for_sale(item_id, sell_price):
    payload = {
        "itemData": {"id": item_id},
        "startingBid": int(sell_price * 0.9),
        "duration": 3600,
        "buyNowPrice": sell_price
    }
    return await api_request("POST", "auctionhouse", json_data=payload)

def get_player_name(player_data):
    first = player_data.get("firstName", "")
    last = player_data.get("lastName", "")
    if first and last:
        return f"{first} {last}"
    return last or first or "?"

def format_coins(amount):
    return f"{amount:,}".replace(",", " ")

def format_time(seconds):
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        return f"{int(seconds/60)}m {int(seconds%60)}s"
    else:
        return f"{int(seconds/3600)}h {int((seconds%3600)/60)}m"

# ==================== SNIPER TASK ====================
@tasks.loop(seconds=2.0)
async def sniper_loop():
    if not config["running"]:
        return
    
    rating = config["target_rating"]
    price_config = config["price_ranges"].get(rating)
    
    if not price_config:
        return
    
    min_buy = price_config["min"]
    max_buy = price_config["max"]
    sell_price = price_config["sell"]
    
    stats["scans"] += 1
    
    # Log périodique
    if stats["scans"] % 30 == 0:
        print(f"📊 [{stats['scans']} scans | {stats['total_buys']} achats | +{stats['total_profit']} CR]")
    
    # Recherche
    auctions = await search_market(rating, max_buy)
    
    if isinstance(auctions, dict) and "error" in auctions:
        error = auctions["error"]
        print(f"⚠️ Erreur: {error}")
        if error == "TOKEN_EXPIRED":
            print("❌ TOKEN EXPIRÉ!")
            config["running"] = False
            channel = bot.get_channel(DISCORD_CHANNEL_ID)
            if channel:
                await channel.send("🚨 **Token expiré!** Utilise `!token` pour en uploader un nouveau.")
            return
        elif error == "RATE_LIMIT":
            print("⚠️ Rate limit - Pause 60s...")
            stats["errors"] += 1
            channel = bot.get_channel(DISCORD_CHANNEL_ID)
            if channel:
                await channel.send("⚠️ Rate limit - Pause 60s...")
            await asyncio.sleep(60)
            return
        else:
            stats["errors"] += 1
            return
    
    # Log des résultats
    if len(auctions) > 0:
        print(f"🔍 Scan #{stats['scans']}: {len(auctions)} joueurs trouvés (max {max_buy} CR)")
    
    # Trier par prix
    auctions = sorted(auctions, key=lambda x: x.get("buyNowPrice", 999999))
    
    for auction in auctions:
        buy_price = auction.get("buyNowPrice", 0)
        player_data = auction.get("itemData", {})
        actual_rating = player_data.get("rating", 0)
        
        if actual_rating != rating:
            continue
        
        if buy_price > 0 and min_buy <= buy_price <= max_buy:
            trade_id = auction["tradeId"]
            item_id = player_data["id"]
            player_name = get_player_name(player_data)
            
            print(f"💰 Tentative achat: {player_name} ({rating}) à {buy_price} CR...")
            
            result = await buy_player(trade_id, buy_price)
            
            if result.get("success"):
                profit = int(sell_price * 0.95 - buy_price)
                stats["total_buys"] += 1
                stats["total_profit"] += profit
                
                quality = "🔥" if buy_price <= min_buy + 50 else "✅"
                
                print(f"{quality} SNIPE RÉUSSI! {player_name} | {buy_price} CR | +{profit} CR")
                
                channel = bot.get_channel(DISCORD_CHANNEL_ID)
                if channel:
                    await channel.send(
                        f"{quality} **SNIPE!** {player_name} ({rating})\n"
                        f"💰 Acheté: {buy_price} CR\n"
                        f"📈 Profit: +{profit} CR\n"
                        f"📊 Session: {stats['total_buys']} achats | +{stats['total_profit']} CR"
                    )
                
                # Mettre en vente
                await asyncio.sleep(0.5)
                await send_to_tradepile(item_id)
                await list_for_sale(item_id, sell_price)
                print(f"📤 {player_name} mis en vente à {sell_price} CR")
                await asyncio.sleep(2)

@sniper_loop.before_loop
async def before_sniper():
    await bot.wait_until_ready()

# ==================== DISCORD COMMANDS ====================
@bot.event
async def on_ready():
    print(f"✅ Bot connecté: {bot.user}")
    load_session()

@bot.command(name="start")
async def start_sniper(ctx, rating: int = 83):
    """Démarre le sniper sur une note"""
    global DISCORD_CHANNEL_ID
    DISCORD_CHANNEL_ID = ctx.channel.id
    
    if not ea_session:
        await ctx.send("❌ Aucun token EA! Utilise `!token` pour en uploader un.")
        return
    
    if rating not in config["price_ranges"]:
        await ctx.send(f"❌ Note {rating} non configurée. Notes dispo: {list(config['price_ranges'].keys())}")
        return
    
    config["target_rating"] = rating
    config["running"] = True
    
    # Reset stats
    stats["total_buys"] = 0
    stats["total_profit"] = 0
    stats["scans"] = 0
    stats["errors"] = 0
    stats["start_time"] = time.time()
    stats["initial_coins"] = await get_coins() or 0
    
    price = config["price_ranges"][rating]
    
    if not sniper_loop.is_running():
        sniper_loop.change_interval(seconds=config["scan_delay"])
        sniper_loop.start()
    
    await ctx.send(
        f"🚀 **Sniper démarré!**\n"
        f"🎯 Note: {rating}\n"
        f"💵 Plage: {price['min']} - {price['max']} CR\n"
        f"📤 Vente: {price['sell']} CR\n"
        f"💰 Solde: {format_coins(stats['initial_coins'])} CR\n"
        f"⚡ Délai: {config['scan_delay']}s"
    )

@bot.command(name="stop")
async def stop_sniper(ctx):
    """Arrête le sniper"""
    config["running"] = False
    
    elapsed = time.time() - stats["start_time"] if stats["start_time"] else 0
    final_coins = await get_coins() or stats["initial_coins"]
    real_profit = final_coins - stats["initial_coins"]
    
    await ctx.send(
        f"🛑 **Sniper arrêté**\n"
        f"⏱️ Durée: {format_time(elapsed)}\n"
        f"📊 Scans: {stats['scans']}\n"
        f"🛒 Achats: {stats['total_buys']}\n"
        f"💰 Solde: {format_coins(final_coins)} CR\n"
        f"📈 Gain réel: {'+' if real_profit >= 0 else ''}{format_coins(real_profit)} CR"
    )

@bot.command(name="status")
async def status(ctx):
    """Affiche le status actuel"""
    coins = await get_coins()
    tradepile = await get_tradepile()
    
    status_text = "🟢 En cours" if config["running"] else "🔴 Arrêté"
    
    msg = f"**Status: {status_text}**\n"
    
    if coins is not None:
        msg += f"💰 Solde: {format_coins(coins)} CR\n"
    else:
        msg += f"💰 Solde: ❌ Erreur (token expiré?)\n"
    
    if config["running"]:
        elapsed = time.time() - stats["start_time"] if stats["start_time"] else 0
        msg += f"🎯 Cible: Note {config['target_rating']}\n"
        msg += f"📊 Scans: {stats['scans']} | Achats: {stats['total_buys']}\n"
        msg += f"💵 Profit session: +{stats['total_profit']} CR\n"
        msg += f"⏱️ Durée: {format_time(elapsed)}\n"
    
    if tradepile:
        selling = sum(1 for i in tradepile if i.get("tradeState") == "active")
        sold = sum(1 for i in tradepile if i.get("tradeState") == "closed")
        msg += f"📦 Pile: {selling} en vente | {sold} vendus | {len(tradepile)} total"
    
    await ctx.send(msg)

@bot.command(name="pile")
async def show_pile(ctx):
    """Affiche les détails de la pile de transfert"""
    tradepile = await get_tradepile()
    
    if not tradepile:
        await ctx.send("📦 Pile de transfert vide ou erreur")
        return
    
    msg = "📦 **Pile de transfert:**\n```"
    
    for item in tradepile[:15]:  # Max 15 pour pas spam
        player = item.get("itemData", {})
        name = get_player_name(player)[:15]
        rating = player.get("rating", "?")
        state = item.get("tradeState", "?")
        buy_now = item.get("buyNowPrice", 0)
        current_bid = item.get("currentBid", 0)
        expires = item.get("expires", 0)
        
        if state == "active":
            time_left = format_time(expires) if expires > 0 else "?"
            msg += f"{name} ({rating}) | {buy_now} CR | ⏱️{time_left}\n"
        elif state == "closed":
            msg += f"{name} ({rating}) | ✅ Vendu {current_bid} CR\n"
        else:
            msg += f"{name} ({rating}) | {state}\n"
    
    if len(tradepile) > 15:
        msg += f"... et {len(tradepile) - 15} autres"
    
    msg += "```"
    await ctx.send(msg)

@bot.command(name="prix")
async def set_price(ctx, rating: int, min_buy: int, max_buy: int, sell: int):
    """Modifie les prix pour une note: !prix 83 700 900 1000"""
    config["price_ranges"][rating] = {"min": min_buy, "max": max_buy, "sell": sell}
    profit_min = int(sell * 0.95 - max_buy)
    profit_max = int(sell * 0.95 - min_buy)
    await ctx.send(f"✅ Note {rating}: {min_buy}-{max_buy} CR → Vente {sell} CR (Profit: +{profit_min} à +{profit_max})")

@bot.command(name="delay")
async def set_delay(ctx, delay: float):
    """Change le délai entre scans: !delay 2.5"""
    if delay < 1.0:
        await ctx.send("⚠️ Délai minimum: 1.0s (éviter ban EA)")
        return
    config["scan_delay"] = delay
    if sniper_loop.is_running():
        sniper_loop.change_interval(seconds=delay)
    await ctx.send(f"✅ Délai: {delay}s entre les scans")

@bot.command(name="token")
async def upload_token(ctx):
    """Upload un fichier token JSON"""
    if not ctx.message.attachments:
        await ctx.send(
            "📎 **Comment uploader un token:**\n"
            "1. Fais l'export Chrome (net-export)\n"
            "2. Glisse le fichier JSON ici avec la commande `!token`\n"
            "3. Le bot extraira le token automatiquement"
        )
        return
    
    attachment = ctx.message.attachments[0]
    
    if not attachment.filename.endswith('.json'):
        await ctx.send("❌ Le fichier doit être un .json")
        return
    
    await ctx.send("⏳ Analyse du fichier...")
    
    try:
        content = await attachment.read()
        content = content.decode('utf-8')
        
        # Chercher le token
        sid_pattern = r'X-UT-SID["\s:]+([a-f0-9-]{36})'
        matches = re.findall(sid_pattern, content, re.IGNORECASE)
        
        if matches:
            token = matches[-1]
            
            global ea_session
            ea_session = {
                "x-ut-sid": token,
                "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            }
            
            with open('active_session.json', 'w') as f:
                json.dump(ea_session, f, indent=2)
            
            # Tester le token
            coins = await get_coins()
            if coins is not None:
                await ctx.send(f"✅ **Token valide!**\n💰 Solde: {format_coins(coins)} CR\n\nUtilise `!start 83` pour lancer le sniper!")
            else:
                await ctx.send("⚠️ Token extrait mais semble invalide. Refais l'export Chrome.")
        else:
            await ctx.send("❌ Aucun token trouvé dans le fichier. Assure-toi d'avoir fait des actions sur la Web App EA.")
    except Exception as e:
        await ctx.send(f"❌ Erreur: {e}")

@bot.command(name="collect")
async def collect_sales(ctx):
    """Récupère l'argent des ventes"""
    tradepile = await get_tradepile()
    
    if not tradepile:
        await ctx.send("📦 Rien à récupérer")
        return
    
    sold = [i for i in tradepile if i.get("tradeState") == "closed"]
    
    if not sold:
        await ctx.send("📦 Aucune vente à récupérer")
        return
    
    # L'API récupère automatiquement quand on accède à tradepile
    total = sum(i.get("currentBid", 0) for i in sold)
    await ctx.send(f"💰 **{len(sold)} ventes récupérées!**\nTotal: {format_coins(int(total * 0.95))} CR (après taxe)")

@bot.command(name="aide")
async def help_cmd(ctx):
    """Affiche l'aide"""
    help_text = """
**🤖 FC Sniper Bot - Commandes:**

**Contrôle:**
`!start 83` - Démarrer sur note 83 (ou autre)
`!stop` - Arrêter le sniper
`!status` - Voir le status actuel

**Configuration:**
`!prix 83 700 900 1000` - Modifier plage (note min max vente)
`!delay 2.5` - Changer le délai entre scans

**Infos:**
`!pile` - Détails de la pile de transfert
`!collect` - Récupérer les ventes

**Token:**
`!token` + fichier JSON - Uploader un nouveau token
"""
    await ctx.send(help_text)

# ==================== MAIN ====================
if __name__ == "__main__":
    print("="*50)
    print("  FC SNIPER - Bot Discord")
    print("="*50)
    
    # Charger le token Discord depuis l'env ou le fichier
    token_file = "discord_token.txt"
    
    if os.path.exists(token_file):
        with open(token_file, 'r') as f:
            DISCORD_BOT_TOKEN = f.read().strip()
    
    if not DISCORD_BOT_TOKEN:
        print("\n❌ Token Discord manquant!")
        print("1. Va sur https://discord.com/developers/applications")
        print("2. Crée une application > Bot > Copie le token")
        print("3. Colle-le dans discord_token.txt")
        print("\nOu lance avec: DISCORD_TOKEN=xxx python discord_bot.py")
        
        DISCORD_BOT_TOKEN = os.environ.get("DISCORD_TOKEN", "")
    
    if DISCORD_BOT_TOKEN:
        print("\n🚀 Démarrage du bot...")
        bot.run(DISCORD_BOT_TOKEN)
    else:
        print("\n❌ Impossible de démarrer sans token Discord")
