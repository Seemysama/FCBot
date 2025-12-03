"""
=============================================================================
                    FUTBIN PRICE SCRAPER v2
=============================================================================
Récupère les prix "Cheapest by Rating" de Futbin pour calibrer le bot.

Méthode: requête directe sur l'API/page Futbin + parsing BeautifulSoup
Génère fodder_targets.json consommé par le sniper.
=============================================================================
"""

import requests
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime

# Configuration
FUTBIN_URL = "https://www.futbin.com/stc/cheapest"
FUTBIN_API_URL = "https://www.futbin.com/home-tab/cheapest-by-rating"
OUTPUT_FILE = "fodder_targets.json"

# Marge de sécurité : acheter X% sous le prix marché
DISCOUNT_PERCENT = 0.15  # 15% sous le marché

# Headers pour éviter le blocage
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Referer': 'https://www.futbin.com/',
}


def parse_price(price_str):
    """Convertit un prix Futbin (ex: '2.5K', '1.2M', '850') en entier"""
    price_str = price_str.strip().upper()
    
    if 'M' in price_str:
        return int(float(price_str.replace('M', '').replace(',', '.')) * 1000000)
    elif 'K' in price_str:
        return int(float(price_str.replace('K', '').replace(',', '.')) * 1000)
    else:
        return int(float(price_str.replace(',', '')))


def scrape_futbin_prices():
    """Scrape les prix depuis Futbin"""
    print("\n" + "=" * 60)
    print("   FUTBIN PRICE SCRAPER v2")
    print("=" * 60)
    
    mapping = {}
    
    # Essayer l'API d'abord
    try:
        print(f"[FUTBIN] Tentative API: {FUTBIN_API_URL}")
        resp = requests.get(FUTBIN_API_URL, headers=HEADERS, timeout=15)
        
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # Chercher les prix par rating
            for rating in range(81, 97):
                # Pattern: "XX Rated Players"
                rated_header = soup.find(string=re.compile(f"^{rating}\\s*Rated", re.IGNORECASE))
                
                if not rated_header:
                    continue
                
                # Chercher les prix dans la section
                parent = rated_header.find_parent()
                if parent:
                    # Chercher tous les prix (format psxboxXXX ou pcXXX)
                    text = parent.get_text()
                    prices = re.findall(r'(?:psxbox|pc)([0-9.,]+[KMkm]?)', text)
                    
                    if prices:
                        int_prices = []
                        for p in prices:
                            try:
                                int_prices.append(parse_price(p))
                            except:
                                pass
                        
                        if int_prices:
                            mapping[rating] = min(int_prices)
                            print(f"  Note {rating}: {mapping[rating]:,} CR")
            
            if mapping:
                print(f"\n[✓] {len(mapping)} notes extraites depuis Futbin")
                return mapping
    
    except Exception as e:
        print(f"[!] Erreur API Futbin: {e}")
    
    # Fallback sur la page principale
    try:
        print(f"\n[FUTBIN] Tentative page principale: {FUTBIN_URL}")
        resp = requests.get(FUTBIN_URL, headers=HEADERS, timeout=15)
        
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # Chercher les prix dans le HTML
            for rating in range(81, 97):
                pattern = re.compile(f'{rating}.*?([0-9.,]+[KMkm]?)', re.DOTALL)
                matches = pattern.findall(soup.get_text())
                
                if matches:
                    int_prices = []
                    for p in matches[:10]:  # Limiter aux 10 premiers
                        try:
                            price = parse_price(p)
                            if 100 < price < 10000000:  # Filtre sanity
                                int_prices.append(price)
                        except:
                            pass
                    
                    if int_prices:
                        mapping[rating] = min(int_prices)
            
            if mapping:
                print(f"[✓] {len(mapping)} notes extraites")
                return mapping
    
    except Exception as e:
        print(f"[!] Erreur page Futbin: {e}")
    
    return None


def use_fallback_prices():
    """Prix de référence si Futbin inaccessible - basés sur données utilisateur"""
    print("[FALLBACK] Utilisation des derniers prix connus...")
    
    # Prix Futbin fournis par l'utilisateur (3 décembre 2025)
    return {
        81: 400,
        82: 450,
        83: 750,
        84: 850,
        85: 2500,
        86: 4900,
        87: 8800,
        88: 13500,
        89: 22750,
        90: 33500,
        91: 105000,
    }


def generate_targets(prices):
    """Génère les cibles de snipe à partir des prix"""
    targets = []
    
    for rating, market_price in prices.items():
        if rating < 83 or rating > 91:  # Fodder tradable uniquement
            continue
        
        # Prix d'achat max = 85% du prix marché (arrondi aux 50)
        max_buy = int((market_price * (1 - DISCOUNT_PERCENT)) / 50) * 50
        
        # Profit estimé après taxe 5%
        estimated_profit = int(market_price * 0.95 - max_buy)
        
        # Ignorer si profit trop faible
        if estimated_profit < 100:
            continue
        
        targets.append({
            'rating': rating,
            'market_price': market_price,
            'max_buy': max_buy,
            'estimated_profit': estimated_profit,
            'type': 'fodder_rating',
            'source': 'futbin',
            'updated_at': datetime.now().isoformat()
        })
    
    return sorted(targets, key=lambda x: x['rating'])


def save_targets(targets, source='futbin'):
    """Sauvegarde les cibles dans le fichier JSON"""
    output = {
        'generated_at': datetime.now().isoformat(),
        'source': source,
        'discount_percent': DISCOUNT_PERCENT * 100,
        'targets': targets
    }
    
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\n[✓] Sauvegardé dans {OUTPUT_FILE}")


def main():
    # Essayer de scraper Futbin
    prices = scrape_futbin_prices()
    
    # Fallback si échec
    if not prices:
        print("\n[!] Scraping échoué - utilisation des prix de référence")
        prices = use_fallback_prices()
        source = 'fallback'
    else:
        source = 'futbin_live'
    
    # Générer les cibles
    targets = generate_targets(prices)
    
    if not targets:
        print("[!] Aucune cible générée")
        return
    
    # Afficher
    print("\n" + "-" * 50)
    print(f"{'Note':<6} {'Marché':<12} {'Snipe Max':<12} {'Profit'}")
    print("-" * 50)
    for t in targets:
        print(f"{t['rating']:<6} {t['market_price']:>8,} CR  {t['max_buy']:>8,} CR   +{t['estimated_profit']:>5,} CR")
    
    # Sauvegarder
    save_targets(targets, source)


if __name__ == "__main__":
    main()
