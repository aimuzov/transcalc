import argparse
from collections import defaultdict
from datetime import datetime, timezone
import fcntl
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request

from collect_route_quotes import parse_regional_prices
from collect_tariffs import plain


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def page_identity(source):
    result = {}
    for tag, key in [('title', 'pageTitle'), ('h1', 'heading')]:
        match = re.search(rf'<{tag}\b[^>]*>(.*?)</{tag}>', source, re.S | re.I)
        result[key] = plain(match[1]) if match else None
    result['canonicalUrl'] = None
    for tag in re.findall(r'<link\b[^>]*>', source, re.I):
        if not re.search(r'rel=["\']canonical["\']', tag, re.I):
            continue
        href = re.search(r'href=["\']([^"\']+)', tag, re.I)
        if href:
            result['canonicalUrl'] = plain(href[1])
    return result


def validate_page(requested, final, source, origin_name=None):
    expected_host = urllib.parse.urlsplit(requested).hostname
    if urllib.parse.urlsplit(final).hostname != expected_host:
        return 'foreign_redirect'
    identity = page_identity(source)
    canonical = identity['canonicalUrl']
    if canonical and urllib.parse.urlsplit(urllib.parse.urljoin(requested, canonical)).hostname != expected_host:
        return 'foreign_canonical'
    heading = identity['heading']
    if not heading or 'Грузоперевозки по России из ' not in heading:
        return 'unexpected_origin_heading'
    if origin_name:
        text = heading.removeprefix('Грузоперевозки по России из ').lower().replace('ё', 'е')
        words = re.findall(r'[а-я]+', origin_name.lower().replace('ё', 'е'))
        stems = [word[:max(2, len(word) - 2)] for word in words]
        if any(stem not in text for stem in stems):
            return 'origin_name_mismatch'
    return None


def linked_hosts(source):
    return set(re.findall(r'https?://([a-z][a-z0-9-]*)\.datrans\.ru(?:/|["\'\s<])', source))


def city_labels(source):
    result = defaultdict(set)
    for href, label in re.findall(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', source, re.S):
        match = re.fullmatch(r'/tariffs/([a-z0-9-]+)/', href)
        external = re.fullmatch(r'https?://([a-z0-9-]+)\.datrans\.ru/?', href)
        if match or external:
            name = plain(label)
            if name:
                result[(match or external)[1]].add(name)
    return result


def load_page(host, cache, delay, refresh, timeout=15, retry_failed=False):
    url = ('https://datrans.ru' if host == 'moskva' else f'https://{host}.datrans.ru') + '/gruzoperevozki-po-rossii/'
    path = cache / f'{host}.html'
    meta_path = cache / f'{host}.meta.json'
    if meta_path.exists() and not refresh:
        meta = json.loads(meta_path.read_text())
        if not retry_failed or meta.get('status') == 200:
            return {**meta, 'cached': True}, path.read_text() if path.exists() else ''
    meta = {'host': host, 'requestedUrl': url, 'fetchedAt': datetime.now(timezone.utc).isoformat()}
    body = ''
    request = urllib.request.Request(url, headers={'User-Agent': 'Transcalc public tariff collector', 'Accept-Encoding': 'gzip'})
    opener = urllib.request.build_opener(NoRedirect())
    lock = Path('/tmp/transcalc-datrans-http.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX)
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read()
            if response.headers.get('Content-Encoding') == 'gzip':
                raw = gzip.decompress(raw)
            body = raw.decode('utf-8')
            meta.update(status=response.status, finalUrl=response.url, cacheControl=response.headers.get('Cache-Control'))
    except urllib.error.HTTPError as error:
        meta.update(status=error.code, finalUrl=error.url, location=error.headers.get('Location'), error=str(error))
    except Exception as error:
        meta.update(status=None, error=str(error))
    finally:
        time.sleep(delay)
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()
    if body:
        path.write_text(body)
        meta['sha256'] = hashlib.sha256(body.encode()).hexdigest()
    write_json(meta_path, meta)
    return meta, body


def build_outputs(output, pages, names, queued_hosts=None):
    rows = [row for page in pages.values() for row in page.get('rows', [])]
    pairs = defaultdict(list)
    for row in rows:
        pairs[(row['from'], row['to'])].append(row)
    cities = set(names) | {city for pair in pairs for city in pair}
    conflicts = []
    for (origin, target), variants in pairs.items():
        prices = {tuple(row['prices4']) for row in variants}
        if len(prices) > 1:
            conflicts.append({'from': origin, 'to': target, 'variants': variants})
    coverage = []
    for city in sorted(cities):
        outgoing = sorted(target for origin, target in pairs if origin == city)
        incoming = sorted(origin for origin, target in pairs if target == city)
        coverage.append({'id': city, 'outgoing': len(outgoing), 'incoming': len(incoming), 'missingOutgoing': sorted(cities - {city} - set(outgoing)), 'missingIncoming': sorted(cities - {city} - set(incoming))})
    manifest = {'checkedAt': datetime.now(timezone.utc).isoformat(), 'hostCount': len(pages), 'validHosts': sum(page.get('valid', False) for page in pages.values()), 'rowCount': len(rows), 'uniqueDirectedPairs': len(pairs), 'cityCount': len(cities), 'possibleDirectedPairs': len(cities) * (len(cities) - 1), 'queuedHosts': sorted(queued_hosts or []), 'collectionComplete': queued_hosts is not None and not queued_hosts, 'missingPairMeaning': 'unknown', 'conflicts': conflicts, 'errors': [{key: value for key, value in page.items() if key != 'rows'} for page in pages.values() if not page.get('valid')], 'pages': [{key: value for key, value in page.items() if key != 'rows'} for page in pages.values()], 'coverage': coverage}
    write_json(output / 'rows.json', rows)
    write_json(output / 'cities.json', [{'id': city, 'names': sorted(names.get(city, set()))} for city in sorted(cities)])
    write_json(output / 'manifest.json', manifest)
    return manifest


def seed_cache(cache, previous):
    for path in previous.glob('*-russia.html'):
        host = path.name.removesuffix('-russia.html')
        target = cache / f'{host}.html'
        if target.exists() or host == 'almaty':
            continue
        url = f'https://{host}.datrans.ru/gruzoperevozki-po-rossii/'
        source = path.read_text()
        if validate_page(url, url, source):
            continue
        shutil.copyfile(path, target)
        write_json(cache / f'{host}.meta.json', {'host': host, 'requestedUrl': url, 'finalUrl': url, 'status': 200, 'fetchedAt': datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(), 'seedFile': str(path), 'sha256': hashlib.sha256(source.encode()).hexdigest()})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('/tmp/transcalc-full-catalog'))
    parser.add_argument('--hosts', type=Path, default=Path('data/catalog/hosts.json'))
    parser.add_argument('--previous', type=Path, help='Optionally seed existing *-russia.html snapshots and city metadata.')
    parser.add_argument('--delay', type=float, default=1)
    parser.add_argument('--timeout', type=float, default=15)
    parser.add_argument('--refresh', action='store_true')
    parser.add_argument('--resume', action='store_true', help='Reuse every cached response, including failures (default).')
    parser.add_argument('--retry-failed', action='store_true', help='Fetch cached non-200 responses again.')
    parser.add_argument('--probe-target-hosts', action='store_true')
    parser.add_argument('--cities', type=Path, default=Path('src/frontend/data/tariffs.json'))
    args = parser.parse_args()
    if args.delay < 1:
        parser.error('Delay must be at least one second')
    args.output.mkdir(parents=True, exist_ok=True)
    cache = args.output / 'pages'
    cache.mkdir(exist_ok=True)
    if args.previous:
        seed_cache(cache, args.previous)
    known_hosts = {urllib.parse.urlsplit(url).hostname.split('.')[0] for url in json.loads(args.hosts.read_text())}
    pending = {'moskva'} | known_hosts
    pages = {}
    names = defaultdict(set)
    catalog = json.loads(args.cities.read_text())['cities']
    canonical_names = {city['id']: city['name'] for city in catalog}
    for city in catalog:
        names[city['id']].add(city['name'])
    if args.probe_target_hosts:
        pending.update(canonical_names)
    metadata_path = args.previous / 'city-regions.json' if args.previous else None
    russian_hosts = set()
    if metadata_path and metadata_path.exists():
        for slug, row in json.loads(metadata_path.read_text()).items():
            canonical_names.setdefault(slug, row.get('name', slug))
            region = row.get('region', '')
            if not any(word in region for word in ['Казахстан', 'Актюбин', 'Абай', 'Атырау', 'Павлодар', 'Туркестан', 'Улытау']):
                russian_hosts.add(slug)
    while pending:
        host = min(pending, key=lambda item: (0 if (cache / f'{item}.meta.json').exists() else 1 if item in known_hosts or item == 'moskva' else 2 if item in russian_hosts else 3, item))
        pending.remove(host)
        if host in pages:
            continue
        meta, source = load_page(host, cache, args.delay, args.refresh, args.timeout, args.retry_failed)
        if (meta.get('status') is None or meta.get('status', 0) >= 500) and not meta.get('cached') and not meta.get('retried'):
            meta, source = load_page(host, cache, args.delay, True, args.timeout)
            meta['retried'] = True
            write_json(cache / f'{host}.meta.json', meta)
        validation = validate_page(meta['requestedUrl'], meta.get('finalUrl', ''), source, canonical_names.get(host)) if meta.get('status') == 200 else f'http_{meta.get("status")}'
        rows = [] if validation else parse_regional_prices(source, host, meta['requestedUrl'])
        if not validation and not rows:
            validation = 'no_tables'
        page = {**meta, **page_identity(source), 'valid': not validation, 'validation': validation, 'rowCount': len(rows), 'rows': []}
        if not validation:
            for row in rows:
                row['prices4'] = row.pop('prices')
                page['rows'].append(row)
            for slug, labels in city_labels(source).items():
                names[slug].update(labels)
                if slug in canonical_names:
                    names[slug].add(canonical_names[slug])
            discovered = linked_hosts(source)
            if args.probe_target_hosts:
                discovered.update(row[end] for row in rows for end in ('from', 'to'))
            pending.update(discovered - pages.keys() - {host})
        pages[host] = page
        manifest = build_outputs(args.output, pages, names, pending)
        print(f'{len(pages)} hosts, {manifest["validHosts"]} valid, {manifest["uniqueDirectedPairs"]} pairs; {host}: {validation or str(len(rows)) + " rows"}; {len(pending)} pending', flush=True)


if __name__ == '__main__':
    main()
