import argparse
from datetime import datetime, timezone
import gzip
import html
import hashlib
import json
import math
from pathlib import Path
import re
import time
import urllib.request


def plain(value):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', value))).strip()


def parse_cities(source):
    cities = {}
    for slug, label in re.findall(r'<a[^>]+href=["\']/tariffs/([a-z0-9-]+)/["\'][^>]*>(.*?)</a>', source, re.S):
        name = plain(label)
        if name and slug != 'moskva':
            cities.setdefault(slug, {"id": slug, "name": name})
    for slug, label in re.findall(r'<a[^>]+href=["\']https?://([a-z0-9-]+)\.datrans\.ru/?["\'][^>]*>(.*?)</a>', source, re.S):
        name = plain(label)
        if slug in cities and name:
            cities[slug]['name'] = name
    return sorted(cities.values(), key=lambda city: city['id'])


def parse_tariff_page(source):
    tables = re.findall(r'<table\b[^>]*>(.*?)</table>', source, re.S)
    rows = []
    for table in tables:
        match = re.search(r'<tr[^>]+class=["\'][^"\']*price_from_table[^"\']*["\'][^>]*>(.*?)</tr>', table, re.S)
        if not match:
            continue
        cells = [plain(cell) for cell in re.findall(r'<td\b[^>]*>(.*?)</td>', match[1], re.S)]
        prices = [int(re.sub(r'\D', '', cell)) if re.search(r'\d', cell) else None for cell in cells]
        duration = re.search(r'<tr[^>]+class=["\']dostavka["\'][^>]*>(.*?)</tr>', table, re.S)
        days = plain(duration[1]).removeprefix('Срок доставки').strip() if duration else ''
        rows.append({"auto": prices, "days": days})
    if len(rows) < 2 or len(rows[0]['auto']) != 6 or len(rows[1]['auto']) != 6:
        return None
    metadata = re.search(r'<script[^>]+id=["\']dt-route-meta["\'][^>]*>(.*?)</script>', source, re.S)
    return {"outbound": rows[0], "inbound": rows[1], "publishedModular": rows[2:4],
            "route": json.loads(metadata[1]) if metadata else None}


def parse_price_index(source):
    routes = {}
    tables = re.findall(r'<table\b[^>]*class=["\'][^"\']*table-fixed-head[^"\']*["\'][^>]*>(.*?)</table>', source, re.S)
    for table in tables:
        heading = plain(table.split('</thead>')[0])
        inbound = heading.startswith('из')
        if not inbound and not heading.startswith('в'):
            continue
        for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>', table, re.S):
            link = re.search(r'href=["\']/tariffs/([a-z0-9-]+)/["\']', row)
            cells = re.findall(r'<td\b[^>]*>(.*?)</td>', row, re.S)
            if not link or len(cells) != 5:
                continue
            prices = [int(re.sub(r'\D', '', plain(cell))) for cell in cells[1:]]
            base = prices[-1]
            auto = [prices[0], math.ceil(base * 53 / 10000) * 100, prices[1],
                    math.ceil(base * 75 / 10000) * 100, prices[2], base]
            slug = link[1]
            key = f'{slug}--moskva' if inbound else f'moskva--{slug}'
            routes[key] = {"auto": auto, "published": prices}
    return routes


def checked_at(paths):
    dates = []
    for path in paths:
        metadata = path.with_suffix('.meta.json')
        if metadata.exists():
            dates.append(json.loads(metadata.read_text())['fetchedAt'][:10])
        else:
            dates.append(datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).date().isoformat())
    return min(dates)


def fetch(url, path, delay, refresh=False):
    if path.exists() and not refresh:
        return path.read_text()
    request = urllib.request.Request(url, headers={
        'User-Agent': 'Transcalc tariff research (private prototype)',
        'Accept-Encoding': 'gzip',
    })
    with urllib.request.urlopen(request, timeout=45) as response:
        raw = response.read()
        if response.headers.get('Content-Encoding') == 'gzip':
            raw = gzip.decompress(raw)
        source = raw.decode('utf-8')
    path.write_text(source)
    path.with_suffix('.meta.json').write_text(json.dumps({
        'url': url, 'fetchedAt': datetime.now(timezone.utc).isoformat(),
    }) + '\n')
    time.sleep(delay)
    return source


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cache', type=Path, default=Path('/tmp/transcalc-pages'))
    parser.add_argument('--output', type=Path, default=Path('data/published-tariffs.json'))
    parser.add_argument('--delay', type=float, default=1)
    parser.add_argument('--limit', type=int)
    parser.add_argument('--index-only', action='store_true')
    parser.add_argument('--refresh', action='store_true')
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    source = fetch('https://datrans.ru/', args.cache / 'index.html', args.delay, args.refresh)
    cities = parse_cities(source)
    if args.index_only:
        source = fetch('https://datrans.ru/gruzoperevozki-po-rossii/', args.cache / 'price-index.html', args.delay, args.refresh)
        routes = parse_price_index(source)
        loaded = [args.cache / 'index.html', args.cache / 'price-index.html']
        if len(routes) < 300:
            raise ValueError(f'Неполный прайс: {len(routes)} направлений')
        for city in cities:
            page = args.cache / f'{city["id"]}.html'
            tariff = parse_tariff_page(page.read_text()) if page.exists() else None
            if tariff:
                loaded.append(page)
                metadata = tariff['route']
                if metadata and metadata.get('toSlug') == city['id']:
                    city['name'] = metadata['to']
                for direction, key in [('outbound', f'moskva--{city["id"]}'), ('inbound', f'{city["id"]}--moskva')]:
                    routes[key] = {"auto": tariff[direction]['auto'], "days": tariff[direction]['days']}
        result = {"source": 'https://datrans.ru/gruzoperevozki-po-rossii/',
                  "checkedAt": checked_at(loaded), "sourceSha256": hashlib.sha256(source.encode()).hexdigest(),
                  "cities": [{"id": "moskva", "name": "Москва"}] + cities, "routes": routes}
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        print(f'Cities: {len(result["cities"])}, routes: {len(routes)}', flush=True)
        return
    loaded = [args.cache / 'index.html']
    result = {"source": 'https://datrans.ru/', "checkedAt": checked_at(loaded), "cities": cities, "tariffs": {}, "errors": {}}
    if args.output.exists():
        previous = json.loads(args.output.read_text())
        result['tariffs'] = previous.get('tariffs', {})
    for index, city in enumerate(cities[:args.limit]):
        slug = city['id']
        try:
            path = args.cache / f'{slug}.html'
            page = fetch(f'https://datrans.ru/tariffs/{slug}/', path, args.delay, args.refresh)
            tariff = parse_tariff_page(page)
            if tariff is None:
                raise ValueError('Не найдены две таблицы отдельных машин')
            result['tariffs'][slug] = tariff
            loaded.append(path)
            result['checkedAt'] = checked_at(loaded)
            print(f'{index + 1}/{len(cities)} {slug}: ok', flush=True)
        except Exception as error:
            result['errors'][slug] = str(error)
            print(f'{slug}: {error}', flush=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(f'Tariffs: {len(result["tariffs"])}, errors: {len(result["errors"])}', flush=True)


if __name__ == '__main__':
    main()
