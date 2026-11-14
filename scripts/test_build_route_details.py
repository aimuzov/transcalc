import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('details', Path(__file__).with_name('build-route-details.py'))
details = importlib.util.module_from_spec(spec)
spec.loader.exec_module(details)


class DetailsTests(unittest.TestCase):
    def test_regional_routes_keep_per_option_days_and_container_vat(self):
        quote = {'route': {'from_slug': 'samara', 'to_slug': 'kazan', 'km': 349, 'days': '1-2'},
                 'options': [{'type': 'auto', 'price_vat': 50000, 'price_novat': 40984, 'days': '1-2'},
                             {'type': 'container', 'price_vat': 60000, 'price_novat': None, 'days': '5'}]}
        result = details.build_details([quote])
        self.assertEqual(result['routes']['samara--kazan']['optionDays']['auto'], '1-2')
        self.assertEqual(result['containers']['samara--kazan']['priceNoVat'], None)
        self.assertEqual(result['containers']['samara--kazan']['days'], '5')


if __name__ == '__main__':
    unittest.main()
