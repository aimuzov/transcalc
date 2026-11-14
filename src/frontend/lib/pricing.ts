export type Tariff = { auto: number[] }
export type QuoteOption = {
	type: 'auto' | 'modular' | 'container'
	priceVat: number
	priceNoVat: number | null
	vehicle?: string
	days?: string
}
export type Quote = {
	status: 'ok' | 'light' | 'heavy' | 'invalid' | 'unavailable'
	weightKg: number
	options: QuoteOption[]
}

const vehicles = [
	{ max: 1500, name: 'Газель, до 1,5 т' },
	{ max: 3000, name: 'Машина до 3 т' },
	{ max: 5000, name: 'Машина до 5 т' },
	{ max: 7000, name: 'Машина до 7 т' },
	{ max: 10000, name: 'Машина до 10 т' },
	{ max: 20000, name: 'Фура, до 20 т' },
]

const groupageBands = [
	{ below: 20000, coefficient: 140 },
	{ below: 40000, coefficient: 119 },
	{ below: 60000, coefficient: 112 },
	{ below: 100000, coefficient: 105 },
	{ below: 140000, coefficient: 98 },
	{ below: Infinity, coefficient: 70 },
]

export function priceTariff(tariff: Tariff, inputWeight: number): Quote {
	const weightKg = Math.trunc(inputWeight)
	const empty = (status: Quote['status']): Quote => ({ status, weightKg, options: [] })

	if (!Number.isFinite(inputWeight) || weightKg <= 0) return empty('invalid')

	if (weightKg < 500) return empty('light')

	if (weightKg > 20000) return empty('heavy')

	if (tariff.auto.length !== 6 || tariff.auto.some((price) => !Number.isFinite(price) || price <= 0)) {
		return empty('unavailable')
	}

	const index = vehicles.findIndex((vehicle) => weightKg <= vehicle.max)
	const auto = tariff.auto[index]!
	const option = (type: QuoteOption['type'], priceVat: number): QuoteOption => ({
		type,
		priceVat,
		priceNoVat: Math.round(priceVat / 1.22),
	})
	const options: QuoteOption[] = [{ ...option('auto', auto), vehicle: vehicles[index]!.name }]

	if (weightKg <= 11000) {
		const proportional = (tariff.auto[5]! * weightKg) / 10000
		const coefficient = groupageBands.find((band) => proportional < band.below)!.coefficient
		const raw = Math.ceil((tariff.auto[5]! * weightKg * coefficient) / 100000000) * 100
		const modular = Math.min(Math.max(raw, 12000), Math.floor((auto * 85) / 10000) * 100)

		options.push(option('modular', modular))
	}

	return { status: 'ok', weightKg, options }
}
