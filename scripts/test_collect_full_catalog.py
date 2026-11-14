import json
from pathlib import Path
import tempfile
import unittest

import collect_full_catalog as collector
from collect_route_quotes import parse_regional_prices


REGIONAL_PAGE = '''
<link rel="canonical" href="https://samara.datrans.ru/gruzoperevozki-po-rossii/">
<h1>Грузоперевозки по России из Самары</h1>
<table class="table-fixed-head"><thead><tr>
<th>в...</th><th>до 1.5 тонн</th><th>до 5 тонн</th><th>до 10 тонн</th><th>до 20 тонн</th>
</tr></thead><tbody><tr>
<td><a href="/tariffs/kazan/">Казань</a></td>
<td>23 500 ₽</td><td>35 200 ₽</td><td>46 900 ₽</td><td>53 200 ₽</td>
</tr></tbody></table>
<table class="table-fixed-head"><thead><tr>
<th>из...</th><th>до 1.5 тонн</th><th>до 5 тонн</th><th>до 10 тонн</th><th>до 20 тонн</th>
</tr></thead><tbody><tr>
<td><a href="/tariffs/kazan/">Казани</a></td>
<td>15 400 ₽</td><td>23 100 ₽</td><td>30 800 ₽</td><td>35 000 ₽</td>
</tr></tbody></table>
'''
URL = 'https://samara.datrans.ru/gruzoperevozki-po-rossii/'


class CollectorTests(unittest.TestCase):
    def test_foreign_redirect_is_rejected(self):
        self.assertEqual(collector.validate_page(URL, 'https://datrans.ru/', REGIONAL_PAGE), 'foreign_redirect')

    def test_published_prices_keep_both_directions(self):
        rows = parse_regional_prices(REGIONAL_PAGE, 'samara', URL)
        self.assertEqual(len(rows), 2)
        self.assertEqual((rows[0]['from'], rows[0]['to'], rows[0]['prices']), ('samara', 'kazan', [23500, 35200, 46900, 53200]))
        self.assertEqual((rows[1]['from'], rows[1]['to'], rows[1]['prices']), ('kazan', 'samara', [15400, 23100, 30800, 35000]))

    def test_valid_page_preserves_city(self):
        self.assertIsNone(collector.validate_page(URL, URL, REGIONAL_PAGE, 'Самара'))

    def test_wrong_canonical_is_rejected(self):
        source = '<link rel="canonical" href="https://datrans.ru/"><h1>Грузоперевозки по России из Самары</h1>'
        self.assertEqual(collector.validate_page(URL, URL, source, 'Самара'), 'foreign_canonical')

    def test_canonical_attribute_order_does_not_change_identity(self):
        source = '<link href="https://datrans.ru/" rel="canonical"><h1>Грузоперевозки по России из Самары</h1>'
        self.assertEqual(collector.validate_page(URL, URL, source, 'Самара'), 'foreign_canonical')

    def test_wrong_city_heading_is_rejected(self):
        source = '<h1>Грузоперевозки по России из Москвы</h1>'
        self.assertEqual(collector.validate_page(URL, URL, source, 'Самара'), 'origin_name_mismatch')

    def test_city_name_does_not_match_generic_heading_prefix(self):
        source = '<h1>Грузоперевозки по России из Москвы</h1>'
        self.assertEqual(collector.validate_page(URL, URL, source, 'Перевоз'), 'origin_name_mismatch')

    def test_unrelated_heading_is_rejected(self):
        self.assertEqual(collector.validate_page(URL, URL, '<h1>Грузоперевозки по Казахстану</h1>'), 'unexpected_origin_heading')

    def test_resume_reuses_cached_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            collector.write_json(cache / 'samara.meta.json', {'status': 410, 'requestedUrl': URL})
            meta, source = collector.load_page('samara', cache, 1, False)
            self.assertEqual(meta['status'], 410)
            self.assertTrue(meta['cached'])
            self.assertEqual(source, '')

    def test_conflicting_prices_are_kept_in_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            rows = [
                {'from': 'samara', 'to': 'kazan', 'prices4': [23500, 35200, 46900, 53200], 'source': URL},
                {'from': 'samara', 'to': 'kazan', 'prices4': [23500, 35200, 46900, 54000], 'source': 'https://kazan.datrans.ru/'},
            ]
            manifest = collector.build_outputs(output, {'samara': {'valid': True, 'rows': rows}}, {'samara': {'Самара'}, 'kazan': {'Казань'}})
            self.assertEqual(manifest['uniqueDirectedPairs'], 1)
            self.assertEqual(len(manifest['conflicts']), 1)
            self.assertEqual(len(json.loads((output / 'rows.json').read_text())), 2)
            samara = next(city for city in manifest['coverage'] if city['id'] == 'samara')
            self.assertEqual(samara['missingIncoming'], ['kazan'])

    def test_manifest_does_not_mark_unknown_queue_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = collector.build_outputs(Path(directory), {}, {})
            self.assertIn('queuedHosts', manifest)
            self.assertFalse(manifest['collectionComplete'])

    def test_manifest_records_remaining_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = collector.build_outputs(Path(directory), {}, {}, {'ufa', 'samara'})
            self.assertEqual(manifest['queuedHosts'], ['samara', 'ufa'])
            self.assertFalse(manifest['collectionComplete'])

    def test_manifest_records_exhausted_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = collector.build_outputs(Path(directory), {}, {}, set())
            self.assertEqual(manifest['queuedHosts'], [])
            self.assertTrue(manifest['collectionComplete'])


if __name__ == '__main__':
    unittest.main()
