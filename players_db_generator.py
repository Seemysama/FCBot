import requests
import json
import os
import re
import time

# --- CONFIGURATION FC 26 (Saison 2025/2026) ---

# URL standard du CDN pour FC 26.
# SI 404/403: Ouvre la Web App -> F12 -> Network -> Cherche le gros JSON (souvent ~60MB)
EA_DB_URL = "https://drop-api.ea.com/rating/fc-25"  # API publique EA FC
BACKUP_URL = "https://www.ea.com/ea-sports-fc/ultimate-team/web-app/content/24B23FDE-7835-41C2-87A2-F453DFDB2E82/2025/fut/items/web/players.json"

OUTPUT_FILE = "players_index_fc26.json"

# Mapping Raretés (Heuristique FC 26)
RARITY_MAP = {
    0: "Gold Common",
    1: "Gold Rare",
    2: "TOTW (Team of the Week)",
    3: "Icon",
    4: "Hero",
    5: "Evolution Base",
    12: "Rush Special",
}

def normalize(text):
    """Normalisation stricte pour recherche rapide"""
    if not text: return ""
    text = text.lower()
    # Suppression accents
    text = re.sub(r'[àáâãäå]', 'a', text)
    text = re.sub(r'[èéêë]', 'e', text)
    text = re.sub(r'[ìíîï]', 'i', text)
    text = re.sub(r'[òóôõö]', 'o', text)
    text = re.sub(r'[ùúûü]', 'u', text)
    text = re.sub(r'[ñ]', 'n', text)
    text = re.sub(r'[ç]', 'c', text)
    # Alphanumérique uniquement
    text = re.sub(r'[^a-z0-9\s]', '', text)
    return text.strip()

def get_rarity_string(type_id):
    if type_id in RARITY_MAP:
        return RARITY_MAP[type_id]
    if type_id > 1:
        return f"Special/Promo (Type {type_id})"
    return "Standard"

def try_ea_drop_api():
    """Essaie l'API publique EA Drop (ratings)"""
    print("[FC 26] Tentative via EA Drop API...")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json"
    }
    
    all_players = []
    offset = 0
    limit = 100
    
    while True:
        url = f"https://drop-api.ea.com/rating/fc-25?locale=fr&limit={limit}&offset={offset}"
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            if resp.status_code != 200:
                print(f"  [!] Status {resp.status_code} à offset {offset}")
                break
            
            data = resp.json()
            items = data.get("items", [])
            
            if not items:
                break
                
            all_players.extend(items)
            print(f"  [+] Récupéré {len(items)} joueurs (total: {len(all_players)})")
            
            offset += limit
            time.sleep(0.3)  # Rate limiting
            
            # Limite sécurité (l'API a environ 20k+ joueurs)
            if offset > 25000:
                break
                
        except Exception as e:
            print(f"  [ERREUR] {e}")
            break
    
    return all_players

def try_webapp_json():
    """Essaie le JSON de la Web App"""
    print("[FC 26] Tentative via Web App JSON...")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    try:
        resp = requests.get(BACKUP_URL, headers=headers, timeout=90, stream=True)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"  [!] Web App JSON échoué: {e}")
    
    return None

def generate_fc26_db():
    print("=" * 60)
    print("   GÉNÉRATEUR BASE DE DONNÉES FC 26")
    print("=" * 60)
    
    raw_data = None
    source = None
    
    # Méthode 1: EA Drop API (plus fiable)
    drop_players = try_ea_drop_api()
    if drop_players and len(drop_players) > 1000:
        raw_data = drop_players
        source = "EA Drop API"
    else:
        # Méthode 2: Web App JSON
        raw_data = try_webapp_json()
        source = "Web App JSON"
    
    if not raw_data:
        print("\n[ERREUR] Impossible de récupérer les données joueurs.")
        print("ACTION REQUISE:")
        print("  1. Ouvre https://www.ea.com/ea-sports-fc/ultimate-team/web-app")
        print("  2. F12 -> Onglet Network -> Filtre 'players'")
        print("  3. Copie l'URL du gros JSON (~60MB)")
        print("  4. Remplace BACKUP_URL dans ce script")
        return
    
    print(f"\n[TRAITEMENT] Source: {source}")
    print(f"[TRAITEMENT] Analyse de {len(raw_data)} assets...")
    
    index = {}
    by_id = {}  # Index par ID pour recherche rapide
    stats = {"Gold": 0, "Special": 0, "Icons": 0, "Total": 0}

    # 1. Injection des Styles de Chimie (IDs fixes)
    styles_list = [
        {"id": 250, "name": "CHASSEUR", "altNames": ["Hunter"], "type": "chemstyle"},
        {"id": 251, "name": "OMBRE", "altNames": ["Shadow"], "type": "chemstyle"},
        {"id": 252, "name": "CATALYSEUR", "altNames": ["Catalyst"], "type": "chemstyle"},
        {"id": 253, "name": "ANCRE", "altNames": ["Anchor"], "type": "chemstyle"},
        {"id": 254, "name": "MOTEUR", "altNames": ["Engine"], "type": "chemstyle"},
        {"id": 255, "name": "OEIL DE LYNX", "altNames": ["Hawk"], "type": "chemstyle"},
        {"id": 256, "name": "ARCHITECTE", "altNames": ["Architect"], "type": "chemstyle"},
        {"id": 257, "name": "ARTISTE", "altNames": ["Artist"], "type": "chemstyle"},
        {"id": 258, "name": "SENTINELLE", "altNames": ["Sentinel"], "type": "chemstyle"},
        {"id": 259, "name": "GARDIEN", "altNames": ["Guardian"], "type": "chemstyle"},
        {"id": 260, "name": "MAESTRO", "altNames": ["Maestro"], "type": "chemstyle"},
        {"id": 261, "name": "FINISSEUR", "altNames": ["Finisher"], "type": "chemstyle"},
        {"id": 262, "name": "TIREUR", "altNames": ["Deadeye"], "type": "chemstyle"},
        {"id": 263, "name": "SNIPER", "altNames": ["Sniper"], "type": "chemstyle"},
        {"id": 264, "name": "POWERHOUSE", "altNames": ["Powerhouse"], "type": "chemstyle"},
        # Gardiens
        {"id": 265, "name": "MUR", "altNames": ["Wall"], "type": "chemstyle_gk"},
        {"id": 266, "name": "BOUCLIER", "altNames": ["Shield"], "type": "chemstyle_gk"},
        {"id": 267, "name": "CHAT", "altNames": ["Cat"], "type": "chemstyle_gk"},
        {"id": 268, "name": "GANT", "altNames": ["Glove"], "type": "chemstyle_gk"},
    ]
    
    for s in styles_list:
        key = normalize(s["name"])
        index[key] = [{
            "id": s["id"],
            "name": s["name"],
            "altNames": s.get("altNames", []),
            "type": s["type"],
            "rating": 0,
            "rarity": "Consumable"
        }]
        by_id[s["id"]] = index[key][0]

    # 2. Traitement Joueurs
    for p in raw_data:
        try:
            # EA Drop API format
            if "id" in p and "overallRating" in p:
                def_id = p.get("id")
                base_id = p.get("baseId", def_id)
                rating = p.get("overallRating", 0)
                
                # Nom
                first = p.get("firstName", "")
                last = p.get("lastName", "")
                common = p.get("commonName", "")
                full_name = common if common else f"{first} {last}".strip()
                
                # Rareté
                rarity_info = p.get("rarity", {})
                rare_type = rarity_info.get("id", 0) if isinstance(rarity_info, dict) else 0
                
                # Position, Nation, Club
                position = p.get("position", {}).get("shortLabel", "") if isinstance(p.get("position"), dict) else ""
                nation = p.get("nationality", {}).get("label", "") if isinstance(p.get("nationality"), dict) else ""
                league = p.get("league", {}).get("label", "") if isinstance(p.get("league"), dict) else ""
                club = p.get("team", {}).get("label", "") if isinstance(p.get("team"), dict) else ""
                
            # Web App JSON format (fallback)
            else:
                def_id = p.get("id")
                base_id = p.get("baseId", def_id)
                rating = p.get("r", p.get("rating", 0))
                
                first = p.get("f", "")
                last = p.get("l", "")
                common = p.get("c", "")
                full_name = common if common else f"{first} {last}".strip()
                
                rare_type = p.get("rare", 0)
                position = ""
                nation = p.get("n", "")
                league = p.get("lg", "")
                club = p.get("team", "")

            # FILTRE: Ignorer cartes < 75 (sauf spéciales)
            if rating < 75 and rare_type <= 1:
                continue
            
            if not full_name or not def_id:
                continue

            search_key = normalize(full_name)
            if not search_key:
                continue

            rarity_label = get_rarity_string(rare_type)
            
            # Structure optimisée
            card_obj = {
                "id": def_id,
                "baseId": base_id,
                "name": full_name,
                "rating": rating,
                "rarity": rarity_label,
                "position": position,
                "type": "player",
                "nation": nation,
                "league": league,
                "club": club
            }

            if search_key not in index:
                index[search_key] = []
            
            index[search_key].append(card_obj)
            by_id[def_id] = card_obj

            # Stats
            if rare_type in [3, 4]:
                stats["Icons"] += 1
            elif rare_type > 1:
                stats["Special"] += 1
            else:
                stats["Gold"] += 1
            stats["Total"] += 1
            
        except Exception as e:
            continue

    # 3. Tri (Meilleure note en premier)
    for k in index:
        index[k].sort(key=lambda x: x.get('rating', 0), reverse=True)

    # 4. Création structure finale
    final_db = {
        "metadata": {
            "version": "FC26",
            "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
            "source": source,
            "total_cards": stats["Total"],
            "total_search_keys": len(index)
        },
        "by_name": index,
        "by_id": by_id
    }

    # 5. Sauvegarde
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(final_db, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 60}")
    print(f"[SUCCES] Base FC 26 générée : {OUTPUT_FILE}")
    print(f"{'=' * 60}")
    print(f" -> {stats['Gold']:,} Or (Common + Rare)")
    print(f" -> {stats['Special']:,} Spéciales (TOTW, Promo)")
    print(f" -> {stats['Icons']:,} Icônes/Héros")
    print(f" -> {len(styles_list)} Styles de chimie")
    print(f" -> {len(index):,} clés de recherche uniques")
    print(f"\nFichier: {os.path.abspath(OUTPUT_FILE)}")
    print(f"Taille: {os.path.getsize(OUTPUT_FILE) / 1024 / 1024:.2f} MB")

def search_player(query, limit=10):
    """Fonction utilitaire pour chercher un joueur"""
    if not os.path.exists(OUTPUT_FILE):
        print("[ERREUR] Base de données non générée. Lance d'abord generate_fc26_db()")
        return []
    
    with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
        db = json.load(f)
    
    query_norm = normalize(query)
    results = []
    
    # Recherche exacte
    if query_norm in db["by_name"]:
        results.extend(db["by_name"][query_norm])
    
    # Recherche partielle
    for key, cards in db["by_name"].items():
        if query_norm in key and key != query_norm:
            results.extend(cards)
    
    # Dédoublonner par ID
    seen = set()
    unique = []
    for r in results:
        if r["id"] not in seen:
            seen.add(r["id"])
            unique.append(r)
    
    # Trier par rating
    unique.sort(key=lambda x: x.get("rating", 0), reverse=True)
    
    return unique[:limit]

def get_fodder_targets(min_rating=82, max_rating=84, min_count=50):
    """Récupère les joueurs 'Fodder' méta pour le trading"""
    if not os.path.exists(OUTPUT_FILE):
        print("[ERREUR] Base de données non générée.")
        return []
    
    with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
        db = json.load(f)
    
    fodder = []
    for card in db["by_id"].values():
        if card.get("type") != "player":
            continue
        rating = card.get("rating", 0)
        rarity = card.get("rarity", "")
        
        # Gold Rare entre 82-84
        if min_rating <= rating <= max_rating and "Gold Rare" in rarity:
            fodder.append(card)
    
    fodder.sort(key=lambda x: x["rating"], reverse=True)
    return fodder[:min_count]

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "search" and len(sys.argv) > 2:
            query = " ".join(sys.argv[2:])
            results = search_player(query)
            print(f"\nRésultats pour '{query}':")
            for r in results:
                print(f"  [{r['id']}] {r['name']} ({r['rating']}) - {r['rarity']}")
        elif sys.argv[1] == "fodder":
            targets = get_fodder_targets()
            print(f"\nFodder Méta (82-84):")
            for t in targets[:20]:
                print(f"  [{t['id']}] {t['name']} ({t['rating']}) - {t['club']}")
    else:
        generate_fc26_db()
