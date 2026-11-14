import unittest

from build_catalog import compact_tariff, compile_catalog, merge_quotes, source_checked_at


class CatalogTests(unittest.TestCase):
    def test_explicit_not_served_overrides_published_price(self):
        result = compile_catalog([{'from': 'a', 'to': 'b', 'prices': [15400, 23100, 30800, 35000], 'source': 'table'}])
        merge_quotes(result, [{'status': 'not_served', 'route': {'from_slug': 'a', 'to_slug': 'b'}, 'cargo': {'weight_kg': 20000}}])
        self.assertNotIn('a--b', result['routes'])
        self.assertEqual(result['unavailable']['a--b']['publishedTariff']['auto'][-1], 35000)

    def test_compact_storage_preserves_individual_weight_exceptions(self):
        self.assertEqual(compact_tariff({'auto': [15400, 18600, 23100, 26300, 30800, 35000]}), 35000)
        special = {'auto': [15000, 18600, 23100, 26300, 30800, 35000]}
        self.assertEqual(compact_tariff(special), special)

    def test_build_date_does_not_replace_actual_check_date(self):
        manifest = {'checkedAt': '2030-01-01', 'pages': [
            {'valid': True, 'fetchedAt': '2026-11-15T00:00:00Z'},
            {'valid': False, 'fetchedAt': '2020-01-01T00:00:00Z'},
        ]}
        self.assertEqual(source_checked_at({'checkedAt': '2026-11-14'}, manifest), '2026-11-14')

    def test_quote_backfills_unpublished_base_and_detects_conflicts(self):
        quote = {'status': 'ok', 'route': {'from_slug': 'samara', 'to_slug': 'kazan'},
                 'cargo': {'weight_kg': 20000}, 'options': [{'type': 'auto', 'price_vat': 53200}]}
        result = compile_catalog([])
        merge_quotes(result, [quote])
        self.assertEqual(result['routes']['samara--kazan']['auto'][-1], 53200)
        with self.assertRaisesRegex(ValueError, 'Conflicting'):
            merge_quotes(result, [{**quote, 'options': [{'type': 'auto', 'price_vat': 50000}]}])

    def test_preserves_directed_special_prices_and_sources(self):
        rows = [
            {'from': 'samara', 'to': 'kazan', 'prices': [23500, 35200, 46900, 53200], 'source': 'https://samara.datrans.ru/'},
            {'from': 'kazan', 'to': 'samara', 'prices': [15400, 23100, 30800, 35000], 'source': 'https://kazan.datrans.ru/'},
        ]
        result = compile_catalog(rows)
        self.assertEqual(result['routes']['samara--kazan']['auto'], [23500, 28200, 35200, 39900, 46900, 53200])
        self.assertEqual(result['routes']['kazan--samara']['auto'][-1], 35000)
        self.assertEqual(result['sources']['samara--kazan'], ['https://samara.datrans.ru/'])

    def test_duplicates_merge_sources_but_conflicts_fail(self):
        row = {'from': 'a', 'to': 'b', 'prices': [15400, 23100, 30800, 35000], 'source': 'first'}
        result = compile_catalog([row, {**row, 'source': 'second'}])
        self.assertEqual(result['sources']['a--b'], ['first', 'second'])
        with self.assertRaisesRegex(ValueError, 'Conflicting'):
            compile_catalog([row, {**row, 'prices': [17600, 26400, 35200, 40000]}])

    def test_rejects_invalid_prices_and_same_city(self):
        for prices in [[1, 2, 3, 4], [15400, 23100, 30800, 0], [15400, 23100, 30800]]:
            with self.assertRaises(ValueError):
                compile_catalog([{'from': 'a', 'to': 'b', 'prices': prices, 'source': 'source'}])
        with self.assertRaises(ValueError):
            compile_catalog([{'from': 'a', 'to': 'a', 'prices': [15400, 23100, 30800, 35000], 'source': 'source'}])


if __name__ == '__main__':
    unittest.main()
