import details from '#frontend/data/route-details.json' with { type: 'json' }
import snapshot from '#frontend/data/tariffs.json' with { type: 'json' }

import { priceTariff, type Quote, type Tariff } from './pricing.ts'

export const cities = snapshot.cities.toSorted((a, b) => a.name.localeCompare(b.name, 'ru'))
export const checkedAt = snapshot.checkedAt
export const sourceUrl = snapshot.source
export const routeCount = Object.keys(snapshot.routes).length
const tariffs: Record<string, number | Tariff> = snapshot.routes
const routeDetails: Record<string, { km: number | null; days: string; optionDays?: Record<string, string> }> =
	details.routes
const containers: Record<string, { priceVat: number; priceNoVat: number | null; days: string }> = details.containers

export function calculate(from: string, to: string, weightKg: number): Quote {
	const key = `${from}--${to}`
	const tariff = tariffs[key]

	if (!tariff) return { status: 'unavailable', weightKg, options: [] }

	const auto =
		typeof tariff === 'number'
			? { auto: [44, 53, 66, 75, 88, 100].map((factor) => Math.ceil((tariff * factor) / 10000) * 100) }
			: tariff
	const result = priceTariff(auto, weightKg)

	for (const option of result.options) {
		option.days = routeDetails[key]?.optionDays?.[option.type]
	}

	if (result.status === 'ok' && containers[key]) {
		result.options.push({ type: 'container', ...containers[key] })
	}

	return result
}

export function routeInfo(from: string, to: string) {
	return routeDetails[`${from}--${to}`]
}

export function hasTariff(from: string, to: string) {
	return Boolean(tariffs[`${from}--${to}`])
}
