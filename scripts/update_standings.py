#!/usr/bin/env python3
"""Refresh NFL division standings from ESPN's public structured standings feed.

Do not overwrite a good snapshot if upstream is unavailable or malformed.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

URL = 'https://site.api.espn.com/apis/site/v2/sports/football/nfl/standings'
OUT = Path(__file__).resolve().parents[1] / 'data' / 'standings.json'
DIVISIONS = {
    'AFC': {'East': ['BUF','MIA','NE','NYJ'], 'North': ['BAL','CIN','CLE','PIT'],
            'South': ['HOU','IND','JAX','TEN'], 'West': ['DEN','KC','LAC','LV']},
    'NFC': {'East': ['DAL','NYG','PHI','WSH'], 'North': ['CHI','DET','GB','MIN'],
            'South': ['ATL','CAR','NO','TB'], 'West': ['ARI','LA','SF','SEA']},
}
ALIASES = {'WSH':'WSH','WAS':'WSH','LAR':'LA','LA':'LA','JAC':'JAX','JAX':'JAX',
           'WS':'WSH','ARZ':'ARI','ARI':'ARI'}

def metric(stats, *names):
    for s in stats:
        if s.get('name') in names or s.get('abbreviation') in names:
            return s.get('value', s.get('displayValue'))
    raise ValueError('Missing metric '+str(names))

def convert(payload, now=None):
    records = {}
    def walk(node):
        if isinstance(node, list):
            for child in node: walk(child)
        elif isinstance(node, dict):
            if isinstance(node.get('entries'), list):
                for entry in node['entries']:
                    team = entry.get('team') or {}
                    code = ALIASES.get(team.get('abbreviation',''),team.get('abbreviation',''))
                    if code in records: raise ValueError('Duplicate team '+code)
                    if code:
                        stats = entry.get('stats') or []
                        wins = int(float(metric(stats,'wins','W')))
                        losses = int(float(metric(stats,'losses','L')))
                        ties = int(float(metric(stats,'ties','T')))
                        pct = float(metric(stats,'winPercent','PCT'))
                        if min(wins,losses,ties) < 0 or not 0 <= pct <= 1: raise ValueError('Invalid record')
                        records[code] = {'name':team.get('displayName') or team.get('name') or code,
                                         'wins':wins,'losses':losses,'ties':ties,'pct':f'{pct:.3f}'}
            for key in ('children','groups','standings'):
                if key in node: walk(node[key])
    walk(payload)
    expected={code for conf in DIVISIONS.values() for division in conf.values() for code in division}
    if set(records)!=expected: raise ValueError(f'Expected 32 NFL teams, got {len(records)}; missing {sorted(expected-set(records))}; extra {sorted(set(records)-expected)}')
    conferences={}
    for conf,divs in DIVISIONS.items():
        conferences[conf]=[]
        for name,codes in divs.items():
            teams=[records[c] for c in codes]
            teams.sort(key=lambda t:(-float(t['pct']),-t['wins'],t['losses'],t['name']))
            conferences[conf].append({'name':f'{conf} {name}','teams':teams})
    timestamp=now or datetime.now(timezone.utc)
    return {'updated_at':timestamp.strftime('%d.%m.%Y %H:%M UTC'), 'source':URL,
            'conferences':conferences}

def main():
    request=Request(URL,headers={'User-Agent':'THE HUDDLE NFL Standings (https://thehuddle.at)','Accept':'application/json'})
    with urlopen(request,timeout=30) as response: payload=json.load(response)
    result=convert(payload)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    tmp=OUT.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    os.replace(tmp,OUT)
    print('NFL standings updated: 32 teams, 8 divisions')

if __name__=='__main__':main()
