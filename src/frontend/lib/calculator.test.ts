import assert from 'node:assert/strict'
import { readdirSync, readFileSync } from 'node:fs'
import { test } from 'node:test'

import { calculate, cities } from './calculator.ts'

test('keeps the two directions independent', () => {
	assert.equal(calculate('moskva', 'sankt-peterburg', 1000).options[0]?.priceVat, 57200)
	assert.equal(calculate('sankt-peterburg', 'moskva', 1000).options[0]?.priceVat, 35200)
})

test('does not invent a tariff for an unpublished route', () => {
	assert.equal(calculate('samara', 'kazan', 1000).status, 'unavailable')
	assert.equal(calculate('moskva', 'moskva', 1000).status, 'unavailable')
	assert.equal(calculate('moskva', 'unknown', 1000).status, 'unavailable')
	assert.equal(cities.find((city) => city.id === 'samara')?.name, 'Самара')
})

test('reproduces independent source quotes including known container tariffs', () => {
	const directory = new URL('../../../data/control/', import.meta.url)

	for (const file of readdirSync(directory).filter((name) => name.endsWith('.json'))) {
		const source = JSON.parse(readFileSync(new URL(file, directory), 'utf8'))
		const result = calculate(source.route.from_slug, source.route.to_slug, source.cargo.weight_kg)

		assert.equal(result.status, source.status, file)

		assert.deepEqual(
			result.options.map((option) => [option.type, option.priceVat, option.priceNoVat]),
			source.options.map((option: { type: string; price_vat: number; price_novat: number | null }) => [
				option.type,
				option.price_vat,
				option.price_novat,
			]),
			file,
		)
	}
})
