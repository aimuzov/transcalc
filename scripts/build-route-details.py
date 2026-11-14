import json
from pathlib import Path


def build_details(quotes):
    containers = {}
    routes = {}
    for source in quotes:
        route = source['route']
        key = route['from_slug'] + '--' + route['to_slug']
        record = routes.setdefault(key, {
            'km': route['km'], 'days': route['days'], 'optionDays': {},
        })
        for option in source['options']:
            if option.get('days'):
                record['optionDays'][option['type']] = str(option['days'])
            if option['type'] == 'container':
                containers[key] = {
                    'priceVat': option['price_vat'],
                    'priceNoVat': option['price_novat'],
                    'days': str(option['days']),
                }
    return {'containers': containers, 'routes': routes}


def main():
    paths = [path for directory in ['training', 'control', 'route-formula/quotes', 'catalog/quotes']
             for path in sorted(Path('data', directory).glob('*.json'))
             if not path.name.endswith(('.meta.json', '.error.json', '.rejected.json'))]
    result = build_details(json.loads(path.read_text()) for path in paths)
    Path('src/frontend/data/route-details.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
