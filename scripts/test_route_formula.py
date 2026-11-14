import unittest

from route_formula import ordinary_base, effective_region
from collect_route_quotes import parse_regional_prices


class RegionalFormulaTests(unittest.TestCase):
    def test_regional_price_table_respects_its_header_direction(self):
        source = '''<table class="table-fixed-head"><thead><tr><th>из...</th></tr></thead>
        <tr><td><a href="/tariffs/kazan/">Казани</a></td><td>15 400 ₽</td><td>23 100 ₽</td><td>30 800 ₽</td><td>35 000 ₽</td></tr></table>'''
        result = parse_regional_prices(source, 'samara', 'https://samara.datrans.ru/')
        self.assertEqual(result, [{'from': 'kazan', 'to': 'samara', 'prices': [15400, 23100, 30800, 35000],
                                   'href': '/tariffs/kazan/', 'source': 'https://samara.datrans.ru/'}])

    def test_rounding_distance_before_multiplication(self):
        self.assertEqual(ordinary_base(993, 147), 147000)
        self.assertEqual(ordinary_base(1033, 147), 161700)
        self.assertEqual(ordinary_base(1137, 147), 176400)

    def test_minimum_is_applied_to_the_base(self):
        self.assertEqual(ordinary_base(374, 79), 35000)

    def test_city_tariff_overrides_the_ordinary_formula(self):
        self.assertEqual(ordinary_base(3906, 106), 424000)
        self.assertEqual(ordinary_base(3906, 106, override=480000), 480000)
        self.assertEqual(ordinary_base(3939, 106), 424000)

    def test_invalid_distance_or_missing_rate_is_not_a_quote(self):
        for distance, rate in [(0, 147), (993, 0), (None, 147), (993, None)]:
            with self.assertRaises(ValueError):
                ordinary_base(distance, rate)

    def test_region_uses_the_calculator_field(self):
        self.assertEqual(effective_region('Самара, Самарская область'), 'Самарская область')
        self.assertEqual(effective_region('Республика Татарстан'), 'Республика Татарстан')


if __name__ == '__main__':
    unittest.main()
