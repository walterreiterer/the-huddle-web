import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('standings',Path(__file__).resolve().parents[1]/'scripts'/'update_standings.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)

class StandingsTests(unittest.TestCase):
    def test_complete_standings(self):
        entries=[]
        for conf in mod.DIVISIONS.values():
            for teams in conf.values():
                for code in teams:
                    entries.append({'team':{'abbreviation':code,'displayName':code},'stats':[
                        {'name':'wins','value':6},{'name':'losses','value':3},
                        {'name':'ties','value':0},{'name':'winPercent','value':.667}]})
        data=mod.convert({'children':[{'children':[{'standings':{'entries':entries}}]}]})
        self.assertEqual(len(data['conferences']['AFC']),4)
        self.assertEqual(sum(len(d['teams']) for c in data['conferences'].values() for d in c),32)
    def test_incomplete_feed_rejected(self):
        with self.assertRaises(ValueError):mod.convert({'children':[{'entries':[]}]})

if __name__=='__main__':unittest.main()
