import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

import { priceTariff } from '#frontend/lib/pricing.ts'

const cases = [
	['dzerzhinsk--kazan--1000', 184],
	['rostov-na-donu--sochi--3000', 158],
	['vladivostok--komsomolsk-na-amure--1501', 225],
	['novosibirsk--nizhniy-tagil--11000', 59],
	['samara--krymsk--20000', 105],
	['krymsk--samara--20000', 105],
]

for (const [name, rate] of cases) {
	const source = JSON.parse(
		readFileSync(new URL(`../data/route-formula/quotes/${name}.json`, import.meta.url), 'utf8'),
	)

	assert.equal(source._meta.legacy.price_per_km, rate, name)
	const base = Math.max(35000, rate * Math.ceil(source.route.km / 100) * 100)
	const auto = [44, 53, 66, 75, 88, 100].map((coefficient) => Math.ceil((base * coefficient) / 10000) * 100)
	const quote = priceTariff({ auto }, source.cargo.weight_kg)

	assert.equal(quote.status, source.status, name)

	assert.deepEqual(
		quote.options.map((option) => [option.type, option.priceVat, option.priceNoVat]),
		source.options
			.filter((option) => option.type !== 'container')
			.map((option) => [option.type, option.price_vat, option.price_novat]),
		name,
	)
}

console.log(`Regional end-to-end controls: ${cases.length} matched. Mismatches: 0.`)
