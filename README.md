# FC Ultimate Team Trading Bot

Bot de trading automatisé pour EA FC Ultimate Team.

## Fonctionnalités

- **Night Trader** : Bot de trading nocturne qui scanne les cartes Gold Rare par note (83-86) et achète/revend automatiquement
- **Scanner** : Analyse du marché en temps réel
- **Session Manager** : Gestion des tokens d'authentification EA

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install requests
```

## Configuration

1. Créer `active_session.json` avec votre token EA :
```json
{
  "x-ut-sid": "votre-token-ici",
  "user_agent": "Mozilla/5.0..."
}
```

2. Configurer les prix dans `fodder_targets.json`

## Usage

```bash
# Lancer le bot de nuit (8 heures)
python night_trader.py 8
```

## ⚠️ Disclaimer

Ce projet est à but éducatif uniquement. L'utilisation de bots peut entraîner un ban de votre compte EA.
