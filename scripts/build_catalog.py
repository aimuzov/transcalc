"""Compile published directed prices without estimating missing routes."""

import argparse
import json
from pathlib import Path
import re


def ceil100(base, percent):
    return ((base * percent + 9999) // 10000) * 100


def source_checked_at(previous, manifest):
    return min([previous['checkedAt']] + [page['fetchedAt'][:10] for page in manifest['pages'] if page.get('valid')])


def compact_tariff(tariff):
    base = tariff['auto'][-1]
    expected = [ceil100(base, factor) for factor in (44, 53, 66, 75, 88, 100)]
    return base if tariff['auto'] == expected else tariff


def compile_catalog(rows):
    routes = {}
    sources = {}
    for row in rows:
        origin, destination = row['from'], row['to']
        if origin == destination or not all(re.fullmatch(r'[a-z][a-z0-9-]*', city) for city in (origin, destination)):
            raise ValueError(f'Invalid route: {origin}--{destination}')
        prices = row.get('prices4', row.get('prices', []))
        if len(prices) != 4 or any(type(price) is not int or price <= 0 for price in prices):
            raise ValueError(f'Invalid prices: {origin}--{destination}')
        base = prices[-1]
        if prices != [ceil100(base, factor) for factor in (44, 66, 88, 100)]:
            raise ValueError(f'Unexpected weight factors: {origin}--{destination}')
        key = f'{origin}--{destination}'
        auto = [prices[0], ceil100(base, 53), prices[1], ceil100(base, 75), prices[2], base]
        if key in routes and routes[key]['auto'] != auto:
            raise ValueError(f'Conflicting prices: {key}')
        routes[key] = {'auto': auto}
        sources.setdefault(key, set()).add(row['source'])
    return {'routes': dict(sorted(routes.items())),
            'sources': {key: sorted(values) for key, values in sorted(sources.items())}}


def merge_quotes(compiled, quotes):
    for quote in quotes:
        key = f'{quote["route"]["from_slug"]}--{quote["route"]["to_slug"]}'
        if quote['status'] == 'not_served' and quote['cargo']['weight_kg'] == 20000:
            compiled.setdefault('unavailable', {})[key] = {
                'status': 'not_served', 'publishedTariff': compiled['routes'].pop(key, None),
                'publishedSources': compiled['sources'].pop(key, []),
                'source': f'https://datrans.ru/calc/?from={quote["route"]["from_slug"]}&to={quote["route"]["to_slug"]}&weight=20000',
            }
            continue
        if quote['status'] != 'ok' or quote['cargo']['weight_kg'] != 20000:
            continue
        base = next((option['price_vat'] for option in quote['options'] if option['type'] == 'auto'), None)
        if base is None:
            continue
        origin, destination = quote['route']['from_slug'], quote['route']['to_slug']
        source = f'https://datrans.ru/calc/?from={origin}&to={destination}&weight=20000'
        row = {'from': origin, 'to': destination, 'prices': [ceil100(base, factor) for factor in (44, 66, 88, 100)], 'source': source}
        added = compile_catalog([row])
        key = f'{origin}--{destination}'
        if key in compiled['routes'] and compiled['routes'][key] != added['routes'][key]:
            raise ValueError(f'Conflicting quote: {key}')
        compiled['routes'][key] = added['routes'][key]
        compiled['sources'][key] = sorted(set(compiled['sources'].get(key, []) + [source]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('rows', type=Path)
    parser.add_argument('--cities', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, default=Path('data/moscow-tariffs.json'))
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--quotes', type=Path, nargs='*', default=[Path('data/route-formula/quotes'), Path('data/catalog/quotes')])
    parser.add_argument('--output', type=Path, default=Path('src/frontend/data/tariffs.json'))
    parser.add_argument('--provenance', type=Path, default=Path('data/catalog-provenance.json'))
    parser.add_argument('--availability', type=Path, default=Path('data/catalog/availability.json'))
    args = parser.parse_args()
    compiled = compile_catalog(json.loads(args.rows.read_text()))
    previous = json.loads(args.baseline.read_text())
    # The old individual tariff pages contain two routes absent from regional tables.
    for key, value in previous['routes'].items():
        if key in compiled['routes'] and compiled['routes'][key]['auto'] != value['auto']:
            raise ValueError(f'Existing snapshot conflicts: {key}')
        if key not in compiled['routes']:
            compiled['routes'][key] = value
            other = key.split('--')[1] if key.startswith('moskva--') else key.split('--')[0]
            compiled['sources'][key] = [f'https://datrans.ru/tariffs/{other}/']
    merge_quotes(compiled, (json.loads(path.read_text()) for directory in args.quotes for path in sorted(directory.glob('*.json'))
                            if re.search(r'--\d+(?:\.\d+)?\.json$', path.name)))
    city_names = {city['id']: city['name'] for city in previous['cities']}
    incoming = json.loads(args.cities.read_text())
    if isinstance(incoming, list):
        incoming = {city['id']: city['name'] for city in incoming}
    if any(not isinstance(name, str) or not name.strip() for name in incoming.values()):
        raise ValueError('All city names must be canonical nonempty strings')
    city_names.update(incoming)
    used = {city for key in compiled['routes'] for city in key.split('--')}
    missing = used - city_names.keys()
    if missing:
        raise ValueError(f'Missing city names: {sorted(missing)}')
    manifest = json.loads(args.manifest.read_text())
    snapshot = {'source': previous['source'], 'checkedAt': source_checked_at(previous, manifest),
                'cities': [{'id': slug, 'name': name} for slug, name in sorted(city_names.items())],
                'routes': {key: compact_tariff(value) for key, value in sorted(compiled['routes'].items())}}
    args.output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + '\n')
    args.provenance.write_text(json.dumps(compiled['sources'], ensure_ascii=False, indent=2) + '\n')
    args.availability.write_text(json.dumps(compiled.get('unavailable', {}), ensure_ascii=False, indent=2) + '\n')
    print(f'{len(snapshot["cities"])} cities, {len(snapshot["routes"])} directed routes')


if __name__ == '__main__':
    main()
