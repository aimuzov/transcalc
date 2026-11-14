import argparse
from collections import defaultdict
from datetime import datetime, timezone
import fcntl
import glob
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import time
import urllib.parse
import urllib.request


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def source_path(path):
    path = path.resolve()
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def route_region(route, side):
    title = route.get(side + '_region', '')
    return title.split(', ', 1)[1] if ', ' in title else None


def canonical_cities(city_ids, metadata, existing_names):
    result = []
    for city in sorted(city_ids):
        item = metadata.get(city, {})
        name = item.get('name') if item.get('metadataSource') == 'calc.DATA.route' else existing_names.get(city, item.get('name'))
        result.append({'id': city, 'name': name, 'region': item.get('region')})
    return result


def compare_published_quotes(rows, records):
    published = defaultdict(list)
    for row in rows:
        published[(row['from'], row['to'])].append(row)
    checked = 0
    matched = 0
    differences = []
    for record in records:
        data = record['data']
        route = data.get('route', {})
        pair = (route.get('from_slug'), route.get('to_slug'))
        if data.get('cargo', {}).get('weight_kg') != 20000 or pair not in published:
            continue
        variants = published[pair]
        bases = sorted({(r.get('prices4') or r.get('prices') or [r.get('B')])[-1] for r in variants})
        actual = data.get('_meta', {}).get('legacy', {}).get('auto')
        checked += 1
        if data.get('status') == 'ok' and bases == [actual]:
            matched += 1
            continue
        kind = 'published_price_mismatch' if data.get('status') == 'ok' else 'quote_not_served_with_published_price'
        differences.append({'from': pair[0], 'to': pair[1], 'kind': kind, 'quoteStatus': data.get('status'), 'quoteBase': actual, 'publishedBases': bases, 'quoteSource': record['source'], 'publishedSources': sorted({row.get('source', '') for row in variants})})
    return {'checkedPairs': checked, 'matchedPairs': matched, 'differences': differences}


def candidate_registry(rows, metadata, confirmed):
    groups = defaultdict(list)
    unmapped = set()
    known = {(r['fromRegion'], r['toRegion']): r['rate'] for r in confirmed}
    for row in rows:
        regions = tuple(metadata.get(city, {}).get('region') for city in [row['from'], row['to']])
        if not all(regions):
            unmapped.add((row['from'], row['to']))
        else:
            groups[regions].append(row)
    result = []
    for regions, members in sorted(groups.items()):
        pairs = defaultdict(set)
        prices = set()
        metadata_confirmed = True
        for row in members:
            base = (row.get('prices4') or row.get('prices') or [row.get('B')])[-1]
            if isinstance(base, int) and base > 0:
                prices.add(base)
                pairs[(row['from'], row['to'])].add(base)
            metadata_confirmed &= all(metadata.get(city, {}).get('metadataSource', '').startswith('calc.DATA') for city in [row['from'], row['to']])
        gcd_base = math.gcd(*prices)
        units = gcd_base // 100 if gcd_base and gcd_base % 100 == 0 else None
        divisors = set()
        if units:
            for number in range(1, math.isqrt(units) + 1):
                if units % number == 0:
                    divisors.update([number, units // number])
        ambiguity = []
        if not metadata_confirmed:
            ambiguity.append('unconfirmed_city_regions')
        if len(pairs) < 2:
            ambiguity.append('single_city_pair')
        if len(divisors) > 1:
            ambiguity.append('multiple_arithmetic_divisors')
        if any(len(variants) > 1 for variants in pairs.values()):
            ambiguity.append('published_price_conflict')
        rate = known.get(regions)
        if rate is not None and units is not None and units % rate != 0:
            ambiguity.append('confirmed_rate_not_gcd_divisor')
        result.append({'fromRegion': regions[0], 'toRegion': regions[1], 'cityPairCount': len(pairs), 'rowCount': len(members), 'metadataConfirmed': metadata_confirmed, 'gcdBase': gcd_base, 'gcdBaseUnits100': units, 'arithmeticCandidateRates': sorted(divisors), 'confirmedRate': rate, 'status': 'confirmed' if rate is not None else 'candidate', 'ambiguity': ambiguity})
    return {'groups': result, 'unmappedCityPairs': [list(pair) for pair in sorted(unmapped)]}


def compare_weight_controls(rows, records, cases):
    published = defaultdict(list)
    for row in rows:
        published[(row['from'], row['to'])].append(row)
    quotes = {(r['data'].get('route', {}).get('from_slug'), r['data'].get('route', {}).get('to_slug'), r['data'].get('cargo', {}).get('weight_kg')): r for r in records}
    checked = []
    missing = []
    columns = {1000: 0, 1500: 0, 5000: 1, 10000: 2, 20000: 3}
    for case in cases:
        key = (case['from'], case['to'], case.get('weight', 20000))
        if key not in quotes:
            missing.append(case)
            continue
        record = quotes[key]
        data = record['data']
        column = columns.get(key[2])
        expected = sorted({(row.get('prices4') or row.get('prices'))[column] for row in published[key[:2]]}) if column is not None else []
        auto = next((option for option in data.get('options', []) if option.get('type') == 'auto'), {})
        actual = auto.get('price_vat', data.get('_meta', {}).get('legacy', {}).get('auto'))
        checked.append(dict(case, status=data.get('status'), actual=actual, publishedPrices=expected, matches=data.get('status') == 'ok' and expected == [actual], source=record['source']))
    return {'requested': len(cases), 'checked': len(checked), 'matched': sum(r['matches'] for r in checked), 'missing': missing, 'results': checked}


def canonical_metadata(seed, records):
    result = {key: dict(value) for key, value in seed.items()}
    claims = defaultdict(list)
    for record in records:
        route = record['data'].get('route', {})
        for side in ['from', 'to']:
            slug = route.get(side + '_slug')
            region = route_region(route, side)
            if slug and region:
                claims[slug].append({'region': region, 'name': route.get(side), 'title': route.get(side + '_region'), 'source': record['source']})
    conflicts = []
    for slug, observations in claims.items():
        regions = sorted({item['region'] for item in observations})
        previous = result.get(slug, {}).get('region')
        if len(regions) > 1 or previous and previous not in regions:
            conflicts.append({'id': slug, 'seedRegion': previous, 'dataRegions': regions, 'evidence': observations})
        chosen = observations[0]
        result[slug] = {'id': slug, 'name': chosen['name'], 'title': chosen['title'], 'region': regions[0] if len(regions) == 1 else None, 'metadataSource': 'calc.DATA.route', 'sourceFile': chosen['source'], 'conflict': len(regions) != 1}
        if len(regions) > 1:
            result[slug]['unknownReason'] = 'conflicting_DATA_regions'
    return result, conflicts


def make_plan(rows, metadata, records):
    evidence = defaultdict(list)
    attempted = set()
    exceptions = []
    for record in records:
        data = record['data']
        route = data.get('route', {})
        if data.get('cargo', {}).get('weight_kg') != 20000:
            continue
        pair = (route.get('from_slug'), route.get('to_slug'))
        attempted.add(pair)
        legacy = data.get('_meta', {}).get('legacy', {})
        rate = legacy.get('price_per_km')
        regions = (route_region(route, 'from'), route_region(route, 'to'))
        if data.get('status') != 'ok' or not isinstance(rate, (int, float)) or rate <= 0 or not all(regions):
            continue
        quote = {'from': pair[0], 'to': pair[1], 'km': route.get('km'), 'kmRounded': legacy.get('km_rounded'), 'rate': rate, 'base': legacy.get('auto'), 'status': data.get('status'), 'source': record['source']}
        evidence[regions].append(quote)
        if isinstance(quote['km'], (int, float)) and isinstance(quote['base'], (int, float)):
            expected = max(35000, rate * ((quote['km'] + 99) // 100) * 100)
            if quote['base'] != expected:
                exceptions.append(dict(quote, fromRegion=regions[0], toRegion=regions[1], formulaBase=expected, delta=quote['base'] - expected))
    registry = []
    rate_conflicts = []
    for regions, quotes in sorted(evidence.items()):
        rates = sorted({q['rate'] for q in quotes})
        item = {'fromRegion': regions[0], 'toRegion': regions[1], 'rate': rates[0] if len(rates) == 1 else None, 'evidence': quotes}
        (registry if len(rates) == 1 else rate_conflicts).append(item)
    confirmed = {(r['fromRegion'], r['toRegion']) for r in registry}
    candidates = defaultdict(list)
    unknown = set()
    for row in rows:
        origin, destination = row['from'], row['to']
        regions = tuple(metadata.get(city, {}).get('region') for city in [origin, destination])
        unknown.update(city for city in [origin, destination] if not metadata.get(city, {}).get('region'))
        if all(regions):
            candidates[regions].append(row)
    pending = []
    unavailable = []
    for regions, group in sorted(candidates.items()):
        if regions in confirmed:
            continue
        remaining = [r for r in group if (r['from'], r['to']) not in attempted]
        def score(row):
            return (row.get('prices4') or row.get('prices') or [row.get('B', 0)])[-1]
        remaining.sort(key=score, reverse=True)
        item = {'fromRegion': regions[0], 'toRegion': regions[1], 'candidates': len(group), 'remaining': len(remaining)}
        if remaining:
            row = remaining[0]
            pending.append(dict(item, **{'from': row['from'], 'to': row['to']}))
        else:
            unavailable.append(item)
    metadata_queue = []
    queued = set()
    for city in sorted(unknown):
        available = [r for r in rows if city in [r['from'], r['to']] and (r['from'], r['to']) not in attempted]
        available.sort(key=lambda r: (int('moskva' in [r['from'], r['to']]), (r.get('prices4') or r.get('prices') or [r.get('B', 0)])[-1]), reverse=True)
        if available:
            row = available[0]
            pair = (row['from'], row['to'])
            if pair not in queued:
                metadata_queue.append({'city': city, 'from': pair[0], 'to': pair[1]})
                queued.add(pair)
    return {'registry': registry, 'rateConflicts': rate_conflicts, 'pendingRegionPairs': pending, 'unavailableRegionPairs': unavailable, 'unknownCities': sorted(unknown), 'metadataQueue': metadata_queue, 'exceptions': exceptions, 'observedRegionPairs': len(candidates)}


def load_records(paths):
    records = {}
    for pattern in paths:
        for name in sorted(glob.glob(pattern)):
            try:
                data = json.loads(Path(name).read_text())
                route = data['route']
                key = (route['from_slug'], route['to_slug'], data['cargo']['weight_kg'])
                records[key] = {'data': data, 'source': source_path(Path(name))}
            except (ValueError, TypeError, KeyError, OSError):
                continue
    return list(records.values())


def quote_manifest(records):
    result = []
    for record in records:
        data = record['data']
        route = data.get('route', {})
        path = Path(record['source'])
        meta_path = path.with_name(path.stem + '.meta.json')
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        raw_path = path.with_name(path.stem + '.html.gz')
        raw_hash = hashlib.sha256(gzip.decompress(raw_path.read_bytes())).hexdigest() if raw_path.exists() else None
        url = 'https://datrans.ru/calc/?' + urllib.parse.urlencode({'from': route.get('from_slug'), 'to': route.get('to_slug'), 'weight': data.get('cargo', {}).get('weight_kg')})
        result.append({'sourceFile': record['source'], 'requestUrl': meta.get('url', url), 'fetchedAt': meta.get('fetchedAt'), 'dataSha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'responseSha256': meta.get('responseSha256', raw_hash), 'rawResponseFile': str(raw_path) if raw_path.exists() else None})
    return result


def select_case(plan, records, cases, failed, metadata_only=False, cases_only=False):
    attempted = {(r['data'].get('route', {}).get('from_slug'), r['data'].get('route', {}).get('to_slug'), r['data'].get('cargo', {}).get('weight_kg')) for r in records}
    queue = list(cases)
    if not cases_only:
        queue += plan['metadataQueue'] + ([] if metadata_only else plan['pendingRegionPairs'])
    return next((case for case in queue if (case['from'], case['to'], case.get('weight', 20000)) not in attempted | failed), None)


def fetch_quote(origin, destination, cache, delay, timeout, retries, weight=20000):
    if not all(re.fullmatch(r'[a-z][a-z0-9-]*', slug) for slug in [origin, destination]):
        raise ValueError('Invalid city slug')
    if not isinstance(weight, (int, float)) or not math.isfinite(weight) or weight <= 0:
        raise ValueError('Invalid weight')
    path = cache / f'{origin}--{destination}--{weight:g}.json'
    if path.exists():
        return {'data': json.loads(path.read_text()), 'source': source_path(path)}
    url = 'https://datrans.ru/calc/?' + urllib.parse.urlencode({'from': origin, 'to': destination, 'weight': weight})
    for attempt in range(retries + 1):
        try:
            with Path('/tmp/transcalc-datrans-http.lock').open('a+') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                request = urllib.request.Request(url, headers={'Accept-Encoding': 'gzip', 'User-Agent': 'Transcalc public tariff registry collector'})
                try:
                    with urllib.request.urlopen(request, timeout=timeout) as response:
                        raw = response.read()
                        if response.headers.get('Content-Encoding') == 'gzip':
                            raw = gzip.decompress(raw)
                    html = raw.decode('utf-8')
                finally:
                    time.sleep(max(1, delay))
            (cache / path.name.replace('.json', '.html.gz')).write_bytes(gzip.compress(raw))
            match = re.search(r'let\s+DATA\s*=\s*(\{.*?\});\s*const\s+TEST_SITE', html, re.S)
            if not match:
                raise ValueError('No DATA in response')
            data = json.loads(match[1])
            route = data.get('route', {})
            if (route.get('from_slug'), route.get('to_slug')) != (origin, destination):
                write_json(cache / path.name.replace('.json', '.rejected.json'), {'requestedFrom': origin, 'requestedTo': destination, 'DATA': data})
                raise ValueError('Response route does not match request')
            if data.get('cargo', {}).get('weight_kg') != weight:
                raise ValueError('Response weight does not match request')
            write_json(path, data)
            write_json(cache / path.name.replace('.json', '.meta.json'), {'url': url, 'fetchedAt': datetime.now(timezone.utc).isoformat(), 'attempts': attempt + 1, 'responseSha256': hashlib.sha256(raw).hexdigest(), 'dataSha256': hashlib.sha256(path.read_bytes()).hexdigest()})
            return {'data': data, 'source': source_path(path)}
        except Exception as error:
            if attempt == retries or isinstance(error, ValueError):
                write_json(cache / path.name.replace('.json', '.error.json'), {'url': url, 'from': origin, 'to': destination, 'weight': weight, 'error': str(error), 'attempts': attempt + 1, 'nonRetryable': isinstance(error, ValueError), 'at': datetime.now(timezone.utc).isoformat()})
                raise
            time.sleep(min(30, 5 * (attempt + 1)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--catalog', type=Path, default=Path('data/catalog/published-rates.json'))
    parser.add_argument('--seed', type=Path, default=Path('data/catalog/city-regions.json'))
    parser.add_argument('--output', type=Path, default=Path('data/catalog'))
    parser.add_argument('--quote-glob', action='append')
    parser.add_argument('--research-caches', action='store_true')
    parser.add_argument('--fetch', action='store_true')
    parser.add_argument('--metadata-only', action='store_true')
    parser.add_argument('--require-data-metadata', action='store_true')
    parser.add_argument('--cases', type=Path)
    parser.add_argument('--cases-only', action='store_true')
    parser.add_argument('--watch-catalog', action='store_true')
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--delay', type=float, default=1.1)
    parser.add_argument('--timeout', type=float, default=40)
    parser.add_argument('--retries', type=int, default=2)
    parser.add_argument('--max-consecutive-failures', type=int, default=1)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    cache = args.output / 'quotes'
    cache.mkdir(exist_ok=True)
    rows = json.loads(args.catalog.read_text())
    cities_file = args.catalog.parent / 'cities.json'
    catalog_cities = json.loads(cities_file.read_text()) if cities_file.exists() else []
    existing_file = Path('src/frontend/data/tariffs.json')
    existing = json.loads(existing_file.read_text()) if existing_file.exists() else {}
    existing_names = {city['id']: city['name'] for city in existing.get('cities', [])}
    names_file = args.output / 'name-normalizations.json'
    normalized_names = json.loads(names_file.read_text()) if names_file.exists() else {}
    existing_names.update(normalized_names)
    seed = json.loads(args.seed.read_text())
    if isinstance(seed, list):
        seed = {city['id']: city for city in seed}
    conflicts_file = args.seed.parent / 'metadata-conflicts.json'
    if conflicts_file.exists():
        seed_conflicts = json.loads(conflicts_file.read_text())
        conflict_ids = list(seed_conflicts) if isinstance(seed_conflicts, dict) else [item['id'] for item in seed_conflicts]
        for city in conflict_ids:
            if city in seed and not seed[city].get('metadataSource', '').startswith('calc.DATA'):
                seed[city] = dict(seed[city], region=None, conflict=True)
    quote_paths = args.quote_glob or ['data/training/*.json', 'data/control/*.json', 'data/route-formula/quotes/*.json', 'data/catalog/quotes/*.json']
    if args.research_caches:
        quote_paths += ['/tmp/transcalc-geography/*.json', '/tmp/transcalc-research/*.json', '/tmp/transcalc-route-probes/*.json', '/tmp/transcalc-route-matrix/*.json']
    records = load_records(quote_paths + [str(cache / '*.json')])
    cases = json.loads(args.cases.read_text()) if args.cases else []
    requests = 0
    failed = set()
    for path in cache.glob('*.error.json'):
        error = json.loads(path.read_text())
        if error.get('nonRetryable'):
            failed.add((error.get('from'), error.get('to'), error.get('weight', 20000)))
    consecutive_failures = 0
    catalog_stamp = args.catalog.stat().st_mtime_ns
    while True:
        if args.watch_catalog and args.catalog.stat().st_mtime_ns != catalog_stamp:
            rows = json.loads(args.catalog.read_text())
            catalog_cities = json.loads(cities_file.read_text()) if cities_file.exists() else []
            catalog_stamp = args.catalog.stat().st_mtime_ns
        metadata, conflicts = canonical_metadata(seed, records)
        for city, name in normalized_names.items():
            if city not in metadata:
                metadata[city] = {'id': city, 'region': None}
            if metadata[city].get('metadataSource') != 'calc.DATA.route':
                metadata[city].update(name=name, nameSource='manualnormalization')
        if args.require_data_metadata:
            for item in metadata.values():
                if not item.get('metadataSource', '').startswith('calc.DATA'):
                    item.update(autocompleteRegion=item.get('region'), region=None, unknownReason='no_owning_DATA_region')
        for error_file in cache.glob('*.error.json'):
            error = json.loads(error_file.read_text())
            for city in [error.get('from'), error.get('to')]:
                if city in metadata and not metadata[city].get('region'):
                    metadata[city].update(unknownReason=error.get('error'), errorSource=str(error_file.resolve()))
        plan = make_plan(rows, metadata, records)
        city_ids = {city for row in rows for city in [row['from'], row['to']]} | {city['id'] for city in catalog_cities}
        canonical = canonical_cities(city_ids, metadata, existing_names)
        missing_metadata = {city for city in city_ids if not metadata.get(city, {}).get('region')}
        missing_names = {city['id'] for city in canonical if not city['name']}
        attempted = {(record['data'].get('route', {}).get('from_slug'), record['data'].get('route', {}).get('to_slug')) for record in records if record['data'].get('cargo', {}).get('weight_kg') == 20000}
        queued_cities = {case['city'] for case in plan['metadataQueue']}
        for city in sorted((missing_metadata | missing_names) - queued_cities - {'moskva'}):
            if ('moskva', city) not in attempted:
                plan['metadataQueue'].append({'city': city, 'from': 'moskva', 'to': city})
        summary = {'updatedAt': datetime.now(timezone.utc).isoformat(), 'catalogRows': len(rows), 'catalogCities': len(city_ids), 'mappedCities': len(city_ids - set(plan['unknownCities'])), 'unknownCities': len(plan['unknownCities']), 'observedRegionPairs': plan['observedRegionPairs'], 'confirmedRegionPairs': len(plan['registry']), 'pendingRegionPairs': len(plan['pendingRegionPairs']), 'unavailableRegionPairs': len(plan['unavailableRegionPairs']), 'rateConflicts': len(plan['rateConflicts']), 'exceptions': len(plan['exceptions']), 'newRequestsThisRun': requests}
        summary['missingNames'] = [city['id'] for city in canonical if not city['name']]
        summary['missingMetadataCities'] = sorted(missing_metadata)
        summary['mappedCities'] = len(city_ids - missing_metadata)
        summary['unknownCities'] = len(missing_metadata)
        summary['metadataRequests'] = len(plan['metadataQueue'])
        case = select_case(plan, records, cases, failed, args.metadata_only, args.cases_only)
        stop = not args.fetch or case is None or args.limit and requests >= args.limit
        if requests % 10 == 0 or stop:
            write_json(args.output / 'canonical-city-regions.json', {city: metadata.get(city, {'id': city, 'region': None}) for city in sorted(city_ids)})
            write_json(args.output / 'canonical-cities.json', canonical)
            write_json(args.output / 'metadata-conflicts.json', conflicts)
            write_json(args.output / 'plan.json', plan)
            write_json(args.output / 'registry.json', plan['registry'])
            write_json(args.output / 'exceptions.json', plan['exceptions'])
            write_json(args.output / 'published-quote-comparison.json', compare_published_quotes(rows, records))
            if cases:
                write_json(args.output / 'weight-controls.json', compare_weight_controls(rows, records, cases))
            write_json(args.output / 'summary.json', summary)
            print(json.dumps(summary, ensure_ascii=False), flush=True)
        if requests % 100 == 0 or stop:
            write_json(args.output / 'candidate-registry.json', candidate_registry(rows, metadata, plan['registry']))
            write_json(args.output / 'quote-manifest.json', quote_manifest(records))
        if stop:
            break
        requests += 1
        try:
            record = fetch_quote(case['from'], case['to'], cache, args.delay, args.timeout, args.retries, case.get('weight', 20000))
            records.append(record)
            consecutive_failures = 0
            data = record['data']
            print(json.dumps({'request': requests, 'from': case['from'], 'to': case['to'], 'weight': case.get('weight', 20000), 'status': data.get('status'), 'rate': data.get('_meta', {}).get('legacy', {}).get('price_per_km')}, ensure_ascii=False), flush=True)
        except Exception as error:
            failed.add((case['from'], case['to'], case.get('weight', 20000)))
            consecutive_failures = 0 if isinstance(error, ValueError) else consecutive_failures + 1
            print(json.dumps({'request': requests, 'from': case['from'], 'to': case['to'], 'error': str(error)}, ensure_ascii=False), flush=True)
            if consecutive_failures >= args.max_consecutive_failures:
                print('Stopped after repeated failed HTTP attempts; cached progress is preserved.', flush=True)
                break


if __name__ == '__main__':
    main()
