import argparse
import gzip
import json
from pathlib import Path
import re
import time
import urllib.request

from collect_tariffs import fetch, plain


def parse_regional_prices(source, origin, url):
    result = []
    for table in re.findall(r'<table\b[^>]*class=["\'][^"\']*table-fixed-head[^"\']*["\'][^>]*>(.*?)</table>', source, re.S):
        first = re.search(r'<th\b[^>]*>(.*?)</th>', table, re.S)
        if not first:
            continue
        heading = plain(first[1]).lower()
        if not heading.startswith(('в', 'из')):
            continue
        for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>', table, re.S):
            cells = re.findall(r'<td\b[^>]*>(.*?)</td>', row, re.S)
            link = re.search(r'href=["\'](/tariffs/([a-z0-9-]+)/)["\']', row)
            if not link or len(cells) != 5:
                continue
            prices = [int(re.sub(r'\D', '', plain(cell))) for cell in cells[1:]]
            target = link[2]
            result.append({'from': target if heading.startswith('из') else origin,
                           'to': origin if heading.startswith('из') else target,
                           'prices': prices, 'href': link[1], 'source': url})
    return result


def collect_quotes(cases, output, delay):
    output.mkdir(parents=True, exist_ok=True)
    for origin, destination, weight in json.loads(cases.read_text()):
        if not all(re.fullmatch(r'[a-z][a-z0-9-]*', slug) for slug in [origin, destination]):
            raise ValueError('Invalid city slug')
        if not isinstance(weight, (int, float)) or weight <= 0:
            raise ValueError('Invalid weight')
        path = output / f'{origin}--{destination}--{weight}.json'
        if path.exists():
            print(f'{path.name}: cached', flush=True)
            continue
        url = f'https://datrans.ru/calc/?from={origin}&to={destination}&weight={weight}'
        request = urllib.request.Request(url, headers={'Accept-Encoding': 'gzip'})
        with urllib.request.urlopen(request, timeout=45) as response:
            body = response.read()
            if response.headers.get('Content-Encoding') == 'gzip':
                body = gzip.decompress(body)
        match = re.search(r'let DATA=(.*?);\s*const TEST_SITE', body.decode(), re.S)
        if not match:
            raise ValueError(f'No DATA in {url}')
        result = json.loads(match[1])
        if (result['route'].get('from_slug'), result['route'].get('to_slug')) != (origin, destination):
            raise ValueError(f'Unexpected route in {url}')
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        print(f'{path.name}: {result["status"]}', flush=True)
        time.sleep(delay)


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest='command', required=True)
    quotes = commands.add_parser('quotes')
    quotes.add_argument('cases', type=Path)
    quotes.add_argument('--output', type=Path, default=Path('data/route-formula/quotes'))
    tariffs = commands.add_parser('tariffs')
    tariffs.add_argument('hosts', nargs='+')
    tariffs.add_argument('--cache', type=Path, default=Path('/tmp/transcalc-regional-pages'))
    tariffs.add_argument('--output', type=Path, default=Path('data/route-formula/published-rates.json'))
    parser.add_argument('--delay', type=float, default=1)
    args = parser.parse_args()
    if args.delay < 1:
        parser.error('Delay must be at least one second')
    if args.command == 'quotes':
        collect_quotes(args.cases, args.output, args.delay)
        return
    args.cache.mkdir(parents=True, exist_ok=True)
    result = []
    for host in args.hosts:
        if not re.fullmatch(r'[a-z][a-z0-9-]*', host):
            raise ValueError('Invalid regional host')
        url = f'https://{host}.datrans.ru/gruzoperevozki-po-rossii/'
        source = fetch(url, args.cache / f'{host}.html', args.delay)
        canonical = re.search(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)', source)
        if canonical and not canonical[1].startswith(f'https://{host}.datrans.ru/'):
            raise ValueError(f'Unexpected canonical for {host}: {canonical[1]}')
        rows = parse_regional_prices(source, host, url)
        if not rows:
            raise ValueError(f'No regional prices: {url}')
        result.extend(rows)
        print(f'{host}: {len(rows)} rows', flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
