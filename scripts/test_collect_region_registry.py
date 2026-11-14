import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).with_name('collect_region_registry.py')


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.exists(), 'Registry collector must exist')
        spec = importlib.util.spec_from_file_location('registry', SCRIPT)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def quote(self, origin='a', destination='b', rate=133, base=66500, status='ok'):
        return {'status': status, 'cargo': {'weight_kg':20000}, 'route': {'from_slug':origin,'to_slug':destination,'from':origin,'to':destination,'from_region':origin+', Region A','to_region':destination+', Region B','km':464}, '_meta':{'legacy':{'price_per_km':rate,'km_rounded':500,'auto':base}}}

    def test_data_metadata_overrides_autocomplete(self):
        metadata, conflicts = self.module.canonical_metadata({'a':{'region':'Wrong'}}, [{'data':self.quote(),'source':'quote.json'}])
        self.assertEqual(metadata['a']['region'], 'Region A')
        self.assertEqual(metadata['a']['metadataSource'], 'calc.DATA.route')
        self.assertEqual(conflicts[0]['id'], 'a')

    def test_conflicting_data_does_not_choose_region(self):
        quote = self.quote()
        other = self.quote()
        other['route']['from_region']='a, Different'
        metadata, conflicts = self.module.canonical_metadata({}, [{'data':quote,'source':'one'}, {'data':other,'source':'two'}])
        self.assertIsNone(metadata['a']['region'])
        self.assertTrue(metadata['a']['conflict'])
        self.assertEqual(metadata['a']['unknownReason'],'conflicting_DATA_regions')

    def test_registry_requires_actual_data_rate(self):
        rows=[{'from':'a','to':'b','prices4':[1,2,3,66500]}]
        metadata={'a':{'region':'Region A'},'b':{'region':'Region B'}}
        plan=self.module.make_plan(rows,metadata,[])
        self.assertEqual(len(plan['pendingRegionPairs']),1)
        self.assertEqual(plan['registry'],[])
        plan=self.module.make_plan(rows,metadata,[{'data':self.quote(),'source':'quote.json'}])
        self.assertEqual(plan['pendingRegionPairs'],[])
        self.assertEqual(plan['registry'][0]['rate'],133)
        self.assertEqual(plan['registry'][0]['evidence'][0]['source'],'quote.json')

    def test_not_served_does_not_confirm_zero_rate(self):
        rows=[{'from':'a','to':'b','prices4':[1,2,3,66500]}]
        metadata={'a':{'region':'Region A'},'b':{'region':'Region B'}}
        plan=self.module.make_plan(rows,metadata,[{'data':self.quote(rate=0,base=0,status='not_served'),'source':'quote.json'}])
        self.assertEqual(plan['registry'],[])
        self.assertEqual(len(plan['unavailableRegionPairs']),1)

    def test_not_served_retries_another_city_in_region(self):
        rows=[{'from':'a','to':'b','prices4':[1,2,3,66500]},{'from':'a','to':'c','prices4':[1,2,3,80000]}]
        metadata={'a':{'region':'Region A'},'b':{'region':'Region B'},'c':{'region':'Region B'}}
        plan=self.module.make_plan(rows,metadata,[{'data':self.quote(rate=0,base=0,status='not_served'),'source':'quote.json'}])
        self.assertEqual(plan['pendingRegionPairs'][0]['to'],'c')

    def test_override_keeps_observed_base(self):
        quote=self.quote(base=80000)
        plan=self.module.make_plan([],{},[{'data':quote,'source':'quote.json'}])
        self.assertEqual(plan['exceptions'][0]['base'],80000)
        self.assertEqual(plan['exceptions'][0]['formulaBase'],66500)

    def test_canonical_names_do_not_use_declined_catalog_labels(self):
        cities=self.module.canonical_cities({'a','b'},{'a':{'name':'Анапа','region':'Region'}},{})
        self.assertEqual(cities,[{'id':'a','name':'Анапа','region':'Region'},{'id':'b','name':None,'region':None}])

    def test_published_base_change_is_reported_with_both_sources(self):
        rows=[{'from':'a','to':'b','prices4':[1,2,3,70000],'source':'published.html'}]
        result=self.module.compare_published_quotes(rows,[{'data':self.quote(),'source':'quote.json'}])
        self.assertEqual(result['matchedPairs'],0)
        self.assertEqual(result['differences'][0]['quoteBase'],66500)
        self.assertEqual(result['differences'][0]['publishedBases'],[70000])
        self.assertEqual(result['differences'][0]['quoteSource'],'quote.json')

    def test_not_served_published_pair_is_not_a_price_change(self):
        rows=[{'from':'a','to':'b','prices4':[1,2,3,70000],'source':'published.html'}]
        result=self.module.compare_published_quotes(rows,[{'data':self.quote(status='not_served',rate=0,base=0),'source':'quote.json'}])
        self.assertEqual(result['differences'][0]['kind'],'quote_not_served_with_published_price')

    def test_controls_only_does_not_start_region_crawl(self):
        plan={'metadataQueue':[{'from':'a','to':'b'}],'pendingRegionPairs':[{'from':'c','to':'d'}]}
        self.assertEqual(self.module.select_case(plan,[],[],set(),cases_only=True),None)

    def test_control_deduplication_includes_weight(self):
        plan={'metadataQueue':[],'pendingRegionPairs':[]}
        cases=[{'from':'a','to':'b','weight':20000},{'from':'a','to':'b','weight':1000}]
        selected=self.module.select_case(plan,[{'data':self.quote(),'source':'quote.json'}],cases,set(),cases_only=True)
        self.assertEqual(selected['weight'],1000)

    def test_gcd_registry_keeps_candidate_separate_from_confirmed(self):
        rows=[{'from':'a','to':'b','prices4':[1,2,3,147000]},{'from':'a','to':'c','prices4':[1,2,3,161700]},{'from':'a','to':'d','prices4':[1,2,3,176400]}]
        metadata={city:{'region':'A' if city=='a' else 'B','metadataSource':'calc.DATA.route'} for city in 'abcd'}
        candidates=self.module.candidate_registry(rows,metadata,[])
        self.assertEqual(candidates['groups'][0]['gcdBaseUnits100'],147)
        self.assertIsNone(candidates['groups'][0]['confirmedRate'])
        self.assertEqual(candidates['groups'][0]['cityPairCount'],3)
        self.assertIn(147,candidates['groups'][0]['arithmeticCandidateRates'])

    def test_candidate_registry_does_not_group_unknown_metadata(self):
        rows=[{'from':'a','to':'b','prices4':[1,2,3,147000]}]
        candidates=self.module.candidate_registry(rows,{'a':{'region':'A'}},[])
        self.assertEqual(candidates['groups'],[])
        self.assertEqual(candidates['unmappedCityPairs'],[['a','b']])

    def test_weight_control_compares_actual_auto_to_published_tier(self):
        quote=self.quote(base=29300)
        quote['cargo']['weight_kg']=1000
        rows=[{'from':'a','to':'b','prices4':[29300,43900,58600,66500],'source':'published.html'}]
        result=self.module.compare_weight_controls(rows,[{'data':quote,'source':'quote.json'}],[{'from':'a','to':'b','weight':1000}])
        self.assertEqual(result['matched'],1)
        self.assertEqual(result['missing'],[])

    def test_missing_weight_controls_are_not_counted_as_passes(self):
        result=self.module.compare_weight_controls([],[],[{'from':'a','to':'b','weight':5000}])
        self.assertEqual(result['matched'],0)
        self.assertEqual(len(result['missing']),1)


if __name__=='__main__':
    unittest.main()
