import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

import { calculate, cities, routeCount } from '#frontend/lib/calculator.ts'

const rows = JSON.parse(readFileSync(new URL('../data/catalog/published-rates.json', import.meta.url), 'utf8'))
const knownCities = new Set(cities.map((city) => city.id))
const unavailable = JSON.parse(readFileSync(new URL('../data/catalog/availability.json', import.meta.url), 'utf8'))
const routes = new Set()
let checked = 0

for (const row of rows) {
	const key = `${row.from}--${row.to}`

	assert.ok(knownCities.has(row.from) && knownCities.has(row.to), `Unknown city: ${key}`)
	assert.notEqual(row.from, row.to, key)
	assert.ok(row.source.startsWith('https://'), `Missing source: ${key}`)
	routes.add(key)

	for (const [index, weight] of [1500, 5000, 10000, 20000].entries()) {
		const quote = calculate(row.from, row.to, weight)

		if (unavailable[key]) {
			assert.equal(quote.status, 'unavailable', key)
			assert.equal(quote.options.length, 0, key)
			continue
		}

		assert.equal(quote.status, 'ok', key)
		const auto = quote.options.find((option) => option.type === 'auto')

		assert.equal(auto?.priceVat, (row.prices4 ?? row.prices)[index], `${key}: ${weight} kg`)
		checked++
	}
}

assert.ok(routeCount + Object.keys(unavailable).length >= routes.size)
assert.equal(knownCities.size, cities.length, 'Duplicate city IDs')
assert.ok(cities.every((city) => city.name.trim().length > 0))

console.log(
	`Published catalog: ${routes.size} directed routes, ${checked} prices matched; runtime: ${routeCount} routes.`,
)
