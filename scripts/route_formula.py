import argparse
from collections import defaultdict
import json
import math
from pathlib import Path


def effective_region(description):
    return description.partition(',')[2].strip() if ',' in description else description.strip()


def ordinary_base(distance, rate, override=None):
    if distance is None or rate is None or not math.isfinite(distance) or not math.isfinite(rate):
        raise ValueError('Distance and rate must be finite numbers')
    if distance <= 0 or rate <= 0:
        raise ValueError('Distance and rate must be positive')
    if override is not None:
        if not math.isfinite(override) or override <= 0:
            raise ValueError('Override must be a positive finite price')
        return override
    return max(35000, 100 * math.ceil(distance / 100) * rate)


def analyze(root):
    observations = {}
    for directory in ['training', 'control', 'route-formula/quotes']:
        for path in sorted((root / directory).glob('*.json')):
            source = json.loads(path.read_text())
            route = source['route']
            key = (route.get('from_slug'), route.get('to_slug'), source['cargo']['weight_kg'])
            observations[key] = (source, str(path))
    routes = []
    groups = defaultdict(list)
    unavailable = []
    for (origin, destination, weight), (source, path) in sorted(observations.items()):
        if weight != 20000:
            continue
        if source['status'] != 'ok':
            unavailable.append({'from': origin, 'to': destination, 'status': source['status'], 'km': source['route']['km'], 'source': path})
            continue
        route = source['route']
        legacy = source['_meta']['legacy']
        row = {
            'from': origin, 'to': destination,
            'fromRegion': effective_region(route['from_region']),
            'toRegion': effective_region(route['to_region']),
            'km': route['km'], 'roundedKm': legacy['km_rounded'],
            'rate': legacy['price_per_km'], 'actualBase': legacy['auto'],
            'ordinaryBase': ordinary_base(route['km'], legacy['price_per_km']),
            'source': path,
        }
        row['delta'] = row['actualBase'] - row['ordinaryBase']
        routes.append(row)
        groups[(row['fromRegion'], row['toRegion'])].append(row)
    registry = []
    for (origin, destination), members in sorted(groups.items()):
        rates = sorted({member['rate'] for member in members})
        registry.append({'fromRegion': origin, 'toRegion': destination, 'rates': rates,
                         'routes': len(members), 'evidence': [member['source'] for member in members]})
    public_rows = json.loads((root / 'route-formula/published-rates.json').read_text())
    price_vectors = defaultdict(set)
    factor_errors = []
    checked = 0
    for row in public_rows:
        price_vectors[(row['from'], row['to'])].add(tuple(row['prices']))
        base = row['prices'][-1]
        for index, coefficient in enumerate([44, 66, 88, 100]):
            expected = ((base * coefficient + 9999) // 10000) * 100
            checked += 1
            if row['prices'][index] != expected:
                factor_errors.append({'from': row['from'], 'to': row['to'], 'index': index,
                                      'actual': row['prices'][index], 'expected': expected})
    return {
        'quoteCases': len(observations), 'routes20t': len(routes),
        'regionalPairs': len(registry),
        'multiRouteRegionalPairs': sum(group['routes'] > 1 for group in registry),
        'rateConflicts': [group for group in registry if len(group['rates']) != 1],
        'ordinaryBaseMatches': sum(row['delta'] == 0 for row in routes),
        'exceptions': [row for row in routes if row['delta'] != 0],
        'unavailable': unavailable,
        'registry': registry, 'routes': routes,
        'publishedRows': len(public_rows), 'publishedUniqueRoutes': len(price_vectors),
        'publishedPriceConflicts': sum(len(values) > 1 for values in price_vectors.values()),
        'checkedWeightPrices': checked, 'weightFactorErrors': factor_errors,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=Path, default=Path('data'))
    parser.add_argument('--output', type=Path, default=Path('data/route-formula/analysis.json'))
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    result = analyze(args.data)
    if args.check:
        if json.loads(args.output.read_text()) != result:
            raise SystemExit('Saved analysis differs from current observations')
    else:
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: result[key] for key in [
        'quoteCases', 'routes20t', 'regionalPairs', 'multiRouteRegionalPairs',
        'ordinaryBaseMatches', 'publishedRows', 'publishedUniqueRoutes', 'checkedWeightPrices',
    ]}))
    print(f'Base exceptions: {len(result["exceptions"])}. Rate conflicts: {len(result["rateConflicts"])}. Weight errors: {len(result["weightFactorErrors"])}.')
    if result['rateConflicts'] or result['weightFactorErrors'] or result['publishedPriceConflicts']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
