import os,io,json,zipfile,requests
from datetime import datetime,timezone
from openai import OpenAI
repo=os.environ['GITHUB_REPOSITORY'];token=os.environ['GITHUB_TOKEN']
headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json'}
s=requests.Session()
def api(path,params=None):
 r=s.get('https://api.github.com'+path,headers=headers,params=params,timeout=25);r.raise_for_status();return r.json()
rid=os.environ.get('SOURCE_RUN_ID','').strip()
if not rid:
 runs=api(f'/repos/{repo}/actions/workflows/the-huddle-55.yml/runs',{'status':'success','per_page':25}).get('workflow_runs',[])
 if not runs:raise RuntimeError('Schritt 55 nicht gefunden')
 rid=str(runs[0]['id'])
arts=api(f'/repos/{repo}/actions/runs/{rid}/artifacts').get('artifacts',[])
a=next((x for x in arts if x['name']=='the-huddle-nachrichten-55' and not x['expired']),None)
if not a:raise RuntimeError('Schritt-55-Artefakt fehlt')
r=s.get(a['archive_download_url'],headers=headers,timeout=40);r.raise_for_status()
with zipfile.ZipFile(io.BytesIO(r.content)) as z:data=json.loads(z.read('the-huddle-55.json'))
# Only 55 source evidence is passed to the model; no unsupported facts.
stories=data.get('top_stories',[])[:8]
aw=data.get('austrian_watch',[])[:8]
games=[g for g in data.get('games',[]) if g.get('completed')][:16]
if not stories and not games:raise RuntimeError('Keine ausreichenden Daten aus 55')
source={'timestamp_utc':datetime.now(timezone.utc).isoformat(),'top_stories':stories,'austrian_watch':aw,'games':games}
# Cap input and output to keep a single manual API request inexpensive.
serialized=json.dumps(source,ensure_ascii=False)[:19000]
instructions="""Du bist Redakteur von THE HUDDLE, einem seriösen deutschsprachigen NFL-Morgenjournal für Österreich.
Schreibe einen vollständigen, gut lesbaren MARKDOWN-ENTWURF, nicht bloß eine Quellensammlung.
Abschnitte: Titel und Datum, NFL in 60 Sekunden (90-130 Wörter), Top Stories (bis zu 4, je 70-110 Wörter), Austrian Watch (2-3 Absätze), Game Center (alle gelieferten Final-Ergebnisse kompakt), Quellen- und Redaktionshinweise.
Arbeite ausschließlich mit dem beigefügten JSON. Jede berichtete Nachricht braucht einen direkt danebenstehenden Originalquellenlink. Behandle RSS-Kurzbeschreibungen als begrenzte Quellen und formuliere keine Details hinzu. Spekulationen und Meinungen nicht als bestätigte Fakten darstellen. Doppelte Themen zusammenführen; wenn zu wenige harte Nachrichten vorhanden sind, lieber weniger Stories als erfundene Meldungen. Datumsangaben der Quellen beachten, ältere Austrian-Watch-Beiträge als Rückblick kennzeichnen. Colts-Entwicklungen können ohne direkte Namensnennung für Bernhard Raimann relevant sein, aber keine persönlichen Folgen ohne Beleg behaupten. Valentin Senn nur bei konkretem Beleg. Spielstände nur aus abgeschlossenen Spielen übernehmen. Auf Deutsch formulieren; NFL-Eigennamen beibehalten. Keine Werbesprache, keine erfundenen Zitate. Am Ende deutlich: ENTWURF – Faktenprüfung und Freigabe ausständig. Keine automatische Publikation."""
client=OpenAI(api_key=os.environ['OPENAI_API_KEY'],timeout=90,max_retries=0)
resp=client.responses.create(model='gpt-6.1-terra',instructions=instructions,input=serialized,max_output_tokens=2600,store=False)
text=(resp.output_text or '').strip()
if len(text)<700:raise RuntimeError('KI-Ausgabe unvollständig; keine Veröffentlichung. Status: '+str(resp.status))
os.makedirs('drafts',exist_ok=True)
with open('drafts/the-huddle-erstausgabe.md','w',encoding='utf-8') as f:f.write(text+'\n')
usage=resp.usage
with open('drafts/the-huddle-erstausgabe-meta.json','w',encoding='utf-8') as f:
 json.dump({'source_55_run':rid,'model':'gpt-6.1-terra','response_status':resp.status,
 'input_tokens':getattr(usage,'input_tokens',None),'output_tokens':getattr(usage,'output_tokens',None),
 'approved':False,'published':False,'api_calls':1},f,ensure_ascii=False,indent=2)
print('Redaktionsentwurf erzeugt. Tokenverbrauch:',getattr(usage,'input_tokens',None),getattr(usage,'output_tokens',None))
