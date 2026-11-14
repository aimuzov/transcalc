import assert from 'node:assert/strict'
import { test } from 'node:test'

import { priceTariff } from './pricing.ts'

const petersburg = { auto: [57200, 68900, 85800, 97500, 114400, 130000] }
const samara = { auto: [79200, 95400, 118800, 135000, 158400, 180000] }

test('reproduces observed Moscow to Petersburg quotes across vehicle boundaries', () => {
	for (const [weight, auto, modular] of [
		[500, 57200, 12000],
		[1000, 57200, 18200],
		[1500, 57200, 27300],
		[1501, 68900, 27400],
		[3000, 68900, 46500],
		[3001, 85800, 46500],
		[5000, 85800, 68300],
		[7000, 97500, 82800],
		[10000, 114400, 97200],
		[11000, 130000, 100100],
	]) {
		const result = priceTariff(petersburg, weight)

		assert.equal(result.status, 'ok')
		assert.equal(result.options.find((option) => option.type === 'auto')?.priceVat, auto)
		assert.equal(result.options.find((option) => option.type === 'modular')?.priceVat, modular)
	}
})

test('groupage discounts depend on the route price rather than weight alone', () => {
	for (const [weight, price] of [
		[1500, 32200],
		[3000, 60500],
		[5000, 94500],
		[10000, 126000],
	]) {
		assert.equal(priceTariff(samara, weight).options.find((option) => option.type === 'modular')?.priceVat, price)
	}
})

test('groupage ends at 11000 kg while full truck remains available to 20000 kg', () => {
	assert.equal(priceTariff(petersburg, 11001).options.length, 1)
	assert.equal(priceTariff(petersburg, 20000).options[0]?.priceVat, 130000)
	assert.equal(priceTariff(petersburg, 20001).status, 'heavy')
	assert.deepEqual(priceTariff(petersburg, 20001).options, [])
	assert.equal(priceTariff(petersburg, 499).status, 'light')
})

test('rejects invalid input and uses whole kilograms as the source calculator does', () => {
	for (const weight of [NaN, Infinity, -1, 0]) {
		assert.equal(priceTariff(petersburg, weight).status, 'invalid')
	}

	assert.equal(priceTariff(petersburg, 499.5).status, 'light')
	assert.equal(priceTariff(petersburg, 1500.5).options[0]?.priceVat, 57200)
})

test('VAT conversion matches the source quote', () => {
	const result = priceTariff(petersburg, 1000)

	assert.equal(result.options[0]?.priceNoVat, 46885)
	assert.equal(result.options[1]?.priceNoVat, 14918)
})
