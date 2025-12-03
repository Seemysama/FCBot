"""
FUTBIN PRICER - Scrape les prix Futbin PC pour alimenter le sniper
Utilise Selenium headless + BeautifulSoup
"""

import json
import time
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

FILTERS_FILE = "futbin_prices.json"
FODDER_FILE = "fodder_targets.json"
TARGET_URL = "https://www.futbin.com/home-tab/cheapest-by-rating"

# Config
MARGIN = 200       # Marge de sécurité (crédits)
TAX = 0.95         # Taxe EA 5%
MIN_RATING = 83    # Note minimum fodder
MAX_RATING = 92    # Note maximum fodder

def parse_price(price_str):
    """Convertit '1.2K', '850', '1.5M' en entier."""
    if not price_str:
        return 0
    price_str = price_str.upper().strip()
    try:
        if 'M' in price_str:
            return int(float(price_str.replace('M', '').replace(',', '.')) * 1_000_000)
        elif 'K' in price_str:
            return int(float(price_str.replace('K', '').replace(',', '.')) * 1_000)
        else:
            return int(float(price_str.replace(',', '')))
    except ValueError:
        return 0

def create_driver():
    """Crée le driver Selenium"""
    print("[PRICER] Initialisation Chrome headless...")
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)

def run_pricer():
    print("\n" + "="*60)
    print("   FUTBIN PRICER - Prix PC uniquement")
    print("="*60)
    
    driver = create_driver()
    prices_by_rating = {}  # Pour dédupliquer et garder le min

    try:
        print(f"[PRICER] Chargement {TARGET_URL}...")
        driver.get(TARGET_URL)
        time.sleep(4)  # Attendre hydratation JS/Cloudflare

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # IMPORTANT: Cibler uniquement les colonnes PC (.hide-not-pc)
        columns = soup.select('.stc-player-column.hide-not-pc')
        
        print(f"[PRICER] {len(columns)} colonnes PC trouvées. Analyse...")

        if not columns:
            # Fallback si la classe a changé
            print("[WARN] Aucune colonne .hide-not-pc, tentative fallback...")
            columns = soup.select('.stc-player-column')

        for col in columns:
            # 1. Récupération de la note
            rating_div = col.select_one('.stc-rating')
            if not rating_div:
                continue
            
            try:
                rating_text = rating_div.get_text(strip=True)
                rating = int(''.join(filter(str.isdigit, rating_text)))
            except:
                continue
            
            # Filtrer les notes fodder (83-92)
            if not (MIN_RATING <= rating <= MAX_RATING):
                continue

            # 2. Récupération des prix PC
            prices = []
            price_elements = col.select('.platform-price-wrapper-small')
            
            for p_el in price_elements:
                p_text = p_el.get_text(strip=True)
                val = parse_price(p_text)
                if val > 0:
                    prices.append(val)
            
            if not prices:
                continue

            # Prix minimum pour cette note
            market_price = min(prices)
            
            # Garder le prix le plus bas par note (dédupliquer)
            if rating not in prices_by_rating or market_price < prices_by_rating[rating]:
                prices_by_rating[rating] = market_price

        # Générer les targets avec calculs de profit
        filters = []
        fodder_targets = []
        
        print("\n[PC] Prix récupérés:")
        for rating in sorted(prices_by_rating.keys()):
            market_price = prices_by_rating[rating]
            
            # Calcul du prix d'achat max rentable
            break_even = market_price * TAX
            max_buy = int((break_even - MARGIN) / 50) * 50  # Arrondi à 50
            sell_price = int(market_price / 50) * 50
            profit = int(sell_price * TAX - max_buy)
            
            if max_buy > 500 and profit > 0:
                print(f"  Note {rating}: Marché {market_price:,} | Achat max {max_buy:,} | Vente {sell_price:,} | Profit +{profit}")
                
                filters.append({
                    "name": f"Fodder {rating} (PC)",
                    "rating": rating,
                    "market_price": market_price,
                    "max_buy": max_buy,
                    "sell_price": sell_price,
                    "profit": profit,
                    "platform": "PC",
                    "updated_at": time.strftime("%Y-%m-%d %H:%M")
                })
                
                fodder_targets.append({
                    "rating": rating,
                    "max_buy": max_buy,
                    "sell_price": sell_price,
                    "estimated_profit": profit
                })

        # Sauvegarde
        if filters:
            # Fichier détaillé
            output = {
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "source": "futbin_pc",
                "platform": "PC",
                "margin": MARGIN,
                "targets": filters
            }
            
            with open(FILTERS_FILE, 'w') as f:
                json.dump(output, f, indent=2)
            
            # Fichier pour le bot (format simple)
            with open(FODDER_FILE, 'w') as f:
                json.dump({"platform": "PC", "targets": fodder_targets}, f, indent=2)
            
            print(f"\n[OK] {len(filters)} prix PC sauvegardés")
            print(f"  -> {FILTERS_FILE}")
            print(f"  -> {FODDER_FILE}")
        else:
            print("\n[WARN] Aucun prix PC trouvé!")

    except Exception as e:
        print(f"[ERR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        driver.quit()
        print("\n" + "="*60)

if __name__ == "__main__":
    run_pricer()
