import assert from 'node:assert/strict'
import { readdirSync, readFileSync } from 'node:fs'

import { calculate } from '#frontend/lib/calculator.ts'
import { priceTariff } from '#frontend/lib/pricing.ts'

const baseline = {
	'moskva--sankt-peterburg': 130000,
	'sankt-peterburg--moskva': 80000,
	'moskva--samara': 180000,
	'samara--moskva': 120000,
	'moskva--kazan': 170000,
	'moskva--ekaterinburg': 220000,
	'moskva--vladivostok': 750000,
	'samara--kazan': 53200,
	'moskva--anapa': 200000,
}

function observations(directory) {
	const root = new URL(`../data/${directory}/`, import.meta.url)

	return readdirSync(root)
		.filter((file) => file.endsWith('.json'))
		.map((file) => ({
			file,
			source: JSON.parse(readFileSync(new URL(file, root), 'utf8')),
		}))
}

let training = 0

for (const { file, source } of observations('training')) {
	const key = `${source.route.from_slug}--${source.route.to_slug}`
	const base = baseline[key]

	assert.ok(base, `No independently established baseline: ${key}`)
	const auto = [44, 53, 66, 75, 88, 100].map((coefficient) => Math.ceil((base * coefficient) / 10000) * 100)
	const result = priceTariff({ auto }, source.cargo.weight_kg)

	assert.equal(result.status, source.status, file)

	assert.deepEqual(
		result.options.map((option) => [option.type, option.priceVat, option.priceNoVat]),
		source.options
			.filter((option) => option.type !== 'container')
			.map((option) => [option.type, option.price_vat, option.price_novat]),
		file,
	)

	training++
}

let control = 0

for (const { file, source } of observations('control')) {
	const result = calculate(source.route.from_slug, source.route.to_slug, source.cargo.weight_kg)

	assert.equal(result.status, source.status, file)

	assert.deepEqual(
		result.options.map((option) => [option.type, option.priceVat, option.priceNoVat]),
		source.options.map((option) => [option.type, option.price_vat, option.price_novat]),
		file,
	)

	control++
}

console.log(`Training: ${training} quotes matched. Control: ${control} quotes matched. Mismatches: 0.`)
