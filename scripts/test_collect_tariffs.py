import unittest
import os
import tempfile
from pathlib import Path

from collect_tariffs import parse_cities, parse_tariff_page, parse_price_index, checked_at


class TariffParserTests(unittest.TestCase):
    def test_snapshot_date_comes_from_oldest_loaded_source(self):
        with tempfile.TemporaryDirectory() as directory:
            old = Path(directory) / 'old.html'
            new = Path(directory) / 'new.html'
            old.write_text('cached')
            new.write_text('fresh')
            os.utime(old, (1577836800, 1577836800))
            os.utime(new, (1735689600, 1735689600))
            self.assertEqual(checked_at([old, new]), '2020-01-01')

    def test_cities_are_unique_and_keep_russian_names(self):
        source = '<a href="/tariffs/samara/">Самару</a><a href="/tariffs/samara/">Самары</a><a href="/tariffs/kazan/">Казань</a><a href="https://samara.datrans.ru/">Самара</a>'
        self.assertEqual(parse_cities(source), [
            {"id": "kazan", "name": "Казань"},
            {"id": "samara", "name": "Самара"},
        ])

    def test_direction_prices_are_kept_separately(self):
        def table(prices):
            return '<table><tr class="price_from_table"><th>Цена</th>' + ''.join(
                f'<td>{price} ₽</td>' for price in prices
            ) + '</tr></table>'
        source = table(['79 200', '95 400', '118 800', '135 000', '158 400', '180 000'])
        source += table(['52 800', '63 600', '79 200', '90 000', '105 600', '120 000'])
        result = parse_tariff_page(source)
        self.assertEqual(result['outbound']['auto'], [79200, 95400, 118800, 135000, 158400, 180000])
        self.assertEqual(result['inbound']['auto'][-1], 120000)

    def test_missing_tables_are_not_zero_prices(self):
        self.assertIsNone(parse_tariff_page('<html>Нет тарифа</html>'))

    def test_price_index_has_independent_directions_and_rounds_missing_weight_classes(self):
        source = '''<table class="table-fixed-head"><thead><tr><th>в...</th></tr></thead><tbody><tr>
        <td><a href="/tariffs/samara/">Самару</a></td><td>79 200 ₽</td><td>118 800 ₽</td><td>158 400 ₽</td><td>180 000 ₽</td>
        </tr></tbody></table><table class="table-fixed-head"><thead><tr><th>из...</th></tr></thead><tbody><tr>
        <td><a href="/tariffs/samara/">Самары</a></td><td>52 800 ₽</td><td>79 200 ₽</td><td>105 600 ₽</td><td>120 000 ₽</td>
        </tr></tbody></table>'''
        result = parse_price_index(source)
        self.assertEqual(result['moskva--samara']['auto'], [79200, 95400, 118800, 135000, 158400, 180000])
        self.assertEqual(result['samara--moskva']['auto'][-1], 120000)


if __name__ == '__main__':
    unittest.main()
