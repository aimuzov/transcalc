import json
from pathlib import Path


def main():
    containers = {}
    routes = {}
    for directory in ['training', 'control']:
        for path in sorted(Path('data', directory).glob('*.json')):
            source = json.loads(path.read_text())
            route = source['route']
            if 'moskva' not in [route['from_slug'], route['to_slug']]:
                continue
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
    Path('src/frontend/data/route-details.json').write_text(
        json.dumps({'containers': containers, 'routes': routes}, ensure_ascii=False, indent=2) + '\n'
    )


if __name__ == '__main__':
    main()
