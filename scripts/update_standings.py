#!/usr/bin/env python3
"""Build NFL regular-season W/L/T tables from nflverse's public game results.

No ESPN API dependency. A failed or incomplete download never replaces an existing snapshot.
"""
import csv
import io
import json
import os
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

SOURCE = 'https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv'
OUT = Path(__file__).resolve().parents[1] / 'data' / 'standings.json'
DIVISIONS = {
    'AFC': {'East': ['BUF', 'MIA', 'NE', 'NYJ'], 'North': ['BAL', 'CIN', 'CLE', 'PIT'],
            'South': ['HOU', 'IND', 'JAX', 'TEN'], 'West': ['DEN', 'KC', 'LAC', 'LV']},
    'NFC': {'East': ['DAL', 'NYG', 'PHI', 'WAS'], 'North': ['CHI', 'DET', 'GB', 'MIN'],
            'South': ['ATL', 'CAR', 'NO', 'TB'], 'West': ['ARI', 'LA', 'SF', 'SEA']},
}
ALIASES = {'WSH': 'WAS', 'JAC': 'JAX', 'LAR': 'LA', 'STL': 'LA', 'SD': 'LAC', 'OAK': 'LV'}
NAMES = {'ARI':'Arizona Cardinals','ATL':'Atlanta Falcons','BAL':'Baltimore Ravens','BUF':'Buffalo Bills',
'CAR':'Carolina Panthers','CHI':'Chicago Bears','CIN':'Cincinnati Bengals','CLE':'Cleveland Browns',
'DAL':'Dallas Cowboys','DEN':'Denver Broncos','DET':'Detroit Lions','GB':'Green Bay Packers',
'HOU':'Houston Texans','IND':'Indianapolis Colts','JAX':'Jacksonville Jaguars','KC':'Kansas City Chiefs',
'LA':'Los Angeles Rams','LAC':'Los Angeles Chargers','LV':'Las Vegas Raiders','MIA':'Miami Dolphins',
'MIN':'Minnesota Vikings','NE':'New England Patriots','NO':'New Orleans Saints','NYG':'New York Giants',
'NYJ':'New York Jets','PHI':'Philadelphia Eagles','PIT':'Pittsburgh Steelers','SEA':'Seattle Seahawks',
'SF':'San Francisco 49ers','TB':'Tampa Bay Buccaneers','TEN':'Tennessee Titans','WAS':'Washington Commanders'}

def build(csv_text, season, today=None):
    today = today or date.today()
    expected = {t for conf in DIVISIONS.values() for div in conf.values() for t in div}
    if expected != set(NAMES) or len(expected) != 32:
        raise ValueError('Invalid NFL team mapping')
    totals = {t: {'wins':0, 'losses':0, 'ties':0} for t in expected}
    played = set()
    latest = None
    for row in csv.DictReader(io.StringIO(csv_text)):
        if row.get('season') != str(season) or row.get('game_type') != 'REG':
            continue
        day = date.fromisoformat(row['gameday'])
        if day > today or not row.get('home_score') or not row.get('away_score'):
            continue
        home = ALIASES.get(row['home_team'], row['home_team'])
        away = ALIASES.get(row['away_team'], row['away_team'])
        if home not in expected or away not in expected or home == away:
            raise ValueError(f'Unknown teams: {home}, {away}')
        game_id = row['game_id']
        if game_id in played:
            raise ValueError(f'Duplicate game: {game_id}')
        played.add(game_id)
        h, a = int(row['home_score']), int(row['away_score'])
        if h < 0 or a < 0:
            raise ValueError('Negative score')
        if h == a:
            totals[home]['ties'] += 1
            totals[away]['ties'] += 1
        else:
            winner, loser = (home, away) if h > a else (away, home)
            totals[winner]['wins'] += 1
            totals[loser]['losses'] += 1
        latest = max(latest, day) if latest else day
    # Never replace a valid table with a blank or stale current-season feed.
    if len(played) < 16 or len([t for t, r in totals.items() if sum(r.values())]) < 28:
        raise ValueError(f'Incomplete {season} regular season feed: {len(played)} games')
    if (today - latest).days > 14 and today.month in (9, 10, 11, 12, 1):
        raise ValueError(f'Stale schedule: latest completed game {latest}')
    conferences = {}
    for conf, divs in DIVISIONS.items():
        conferences[conf] = []
        for name, codes in divs.items():
            teams = []
            for code in codes:
                record = totals[code]
                games = sum(record.values())
                pct = (record['wins'] + record['ties']/2) / games if games else 0
                teams.append({'name': NAMES[code], **record, 'pct': f'{pct:.3f}'})
            teams.sort(key=lambda t: (-float(t['pct']), -t['wins'], t['losses'], t['name']))
            conferences[conf].append({'name':f'{conf} {name}', 'teams':teams})
    return {'updated_at':datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M UTC'),
            'results_through':latest.isoformat(), 'source':SOURCE, 'conferences':conferences}

def main():
    today = date.today()
    season = today.year if today.month >= 8 else today.year - 1
    request = Request(SOURCE, headers={'User-Agent':'THE-HUDDLE-standings/1.0', 'Accept':'text/csv'})
    with urlopen(request, timeout=40) as response:
        content = response.read().decode('utf-8-sig')
    result = build(content, season, today)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    os.replace(tmp, OUT)
    print(f"NFL tables updated from nflverse: {season}, through {result['results_through']}")

if __name__ == '__main__':
    main()
