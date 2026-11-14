<script lang="ts">
	import { onMount } from 'svelte'
	import Button from '@aimuzov/infra-site-kit/ui/button.svelte'
	import Input from '@aimuzov/infra-site-kit/ui/input.svelte'
	import Field from '@aimuzov/infra-site-kit/ui/field.svelte'
	import CityPicker from './city-picker.svelte'
	import { calculate, cities, checkedAt, routeInfo, sourceUrl } from '#frontend/lib/calculator.ts'
	import type { Quote } from '#frontend/lib/pricing.ts'
	let city = $state('sankt-peterburg')
	let reverse = $state(false)
	let weight = $state('1000')
	let vat = $state(true)
	let quote = $state<Quote | null>(null)
	let error = $state('')
	const from = $derived(reverse ? city : 'moskva')
	const to = $derived(reverse ? 'moskva' : city)
	const name = (id: string) => cities.find((city) => city.id === id)?.name ?? ''
	const money = (price: number) => new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 }).format(price)
	const duration = (days: string) => (/^\d[\d\s-]*$/.test(days) ? `${days} дн.` : days)
	const info = $derived(quote?.status === 'ok' ? routeInfo(from, to) : undefined)
	const options = $derived(
		quote?.options.toSorted(
			(a, b) =>
				(vat ? a.priceVat : (a.priceNoVat ?? a.priceVat)) - (vat ? b.priceVat : (b.priceNoVat ?? b.priceVat)),
		) ?? [],
	)
	const messages = {
		invalid: 'Укажите вес груза в целых килограммах.',
		light: 'Для груза легче 500 кг нужен индивидуальный расчёт.',
		heavy: 'Для груза тяжелее 20 000 кг нужен индивидуальный расчёт.',
		unavailable:
			'Для этого направления нет опубликованного тарифа. Выберите другой город или поменяйте направление.',
	}

	function clear() {
		quote = null
		error = ''

		if (typeof window !== 'undefined') history.replaceState(null, '', location.pathname)
	}
	function submit() {
		error = ''

		if (!city) {
			error = 'Выберите город из списка.'

			return
		}

		const number = Number(weight)

		if (!weight.trim() || !Number.isInteger(number) || number <= 0) {
			error = messages.invalid

			return
		}

		const result = calculate(from, to, number)

		if (result.status !== 'ok') {
			quote = null
			error = messages[result.status]

			return
		}

		quote = result
		const query = new URLSearchParams({ from, to, weight: String(number) })

		history.replaceState(null, '', `${location.pathname}?${query}`)
	}

	onMount(() => {
		const query = new URLSearchParams(location.search)
		const source = query.get('from')
		const target = query.get('to')
		const amount = query.get('weight')

		if (!source || !target || !amount || source === target || (source !== 'moskva' && target !== 'moskva')) return

		const other = source === 'moskva' ? target : source

		if (!cities.some((city) => city.id === other)) return

		city = other
		reverse = target === 'moskva'
		weight = amount
		submit()
	})
</script>

<div class="calculator">
	<form
		class="calculator-form"
		onsubmit={(event) => {
			event.preventDefault()
			submit()
		}}
		novalidate
	>
		<div class="form-heading">
			<h2>Рассчитать перевозку</h2>
			<span>От 500 кг до 20 т</span>
		</div>
		<div class="route-fields">
			<Field label="Откуда" for="from-city">
				{#if reverse}<CityPicker id="from-city" bind:value={city} onchange={clear} />{:else}<Input
						id="from-city"
						value="Москва"
						readonly
					/>{/if}
			</Field>
			<div class="swap">
				<Button
					variant="outline"
					aria-label="Поменять направление"
					onclick={() => {
						reverse = !reverse
						clear()
					}}
					><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"
						><path d="M4 7h16m-4-4 4 4-4 4M20 17H4m4-4-4 4 4 4" /></svg
					></Button
				>
			</div>
			<Field label="Куда" for="to-city">
				{#if reverse}<Input id="to-city" value="Москва" readonly />{:else}<CityPicker
						id="to-city"
						bind:value={city}
						onchange={clear}
					/>{/if}
			</Field>
		</div>
		<p class="field-note">Маршруты из Москвы и обратно. Начните вводить название города.</p>
		<div class="weight-section">
			<Field label="Вес груза, кг" for="weight"
				><Input
					id="weight"
					inputmode="numeric"
					bind:value={weight}
					oninput={clear}
					aria-describedby="weight-hint"
					aria-invalid={error ? 'true' : undefined}
				/></Field
			>
			<p id="weight-hint" class="field-note">Общий вес всей отправки в килограммах.</p>
			<div class="presets" aria-label="Быстрый выбор веса">
				{#each [500, 1000, 3000, 5000, 10000, 20000] as amount}<Button
						size="sm"
						variant="ghost"
						aria-pressed={weight === String(amount)}
						onclick={() => {
							weight = String(amount)
							clear()
						}}>{money(amount)}</Button
					>{/each}
			</div>
		</div>
		{#if error}<p class="form-error" role="alert">{error}</p>{/if}
		<div class="submit-row">
			<Button type="submit" size="xl">Рассчитать стоимость <span aria-hidden="true">→</span></Button><span
				>Без заявки и звонка</span
			>
		</div>
	</form>
	<section class="results" aria-label="Результат расчёта" aria-live="polite" aria-atomic="true">
		{#if quote?.status === 'ok'}
			<div class="result-heading">
				<div>
					<p class="eyebrow">Стоимость перевозки</p>
					<h2>{name(from)} → {name(to)}</h2>
					<p class="result-meta">
						{money(quote.weightKg)} кг{#if info?.km}
							· {money(info.km)} км{/if}
					</p>
				</div>
				<button
					type="button"
					class="vat-switch"
					role="switch"
					aria-checked={vat}
					aria-label="Включить НДС 22%"
					onclick={() => (vat = !vat)}
					><span class="switch-track"><span></span></span>{vat ? 'С НДС 22%' : 'Без НДС'}</button
				>
			</div>
			<div class="quote-options">
				{#each options as option, index (option.type)}
					<article class:quote-primary={index === 0} class="quote-option">
						<div class="quote-label">
							<h3>
								{option.type === 'modular'
									? 'Сборный груз'
									: option.type === 'auto'
										? 'Отдельная машина'
										: 'Контейнер'}
							</h3>
							{#if index === 0 && options.length > 1}<span class="price-badge">Выгоднее по цене</span
								>{/if}
						</div>
						<p class="price">
							{money(vat || option.priceNoVat === null ? option.priceVat : option.priceNoVat)}
							<span>₽</span>
						</p>
						<p class="quote-caption">
							{!vat && option.priceNoVat === null
								? 'Доступен только с НДС'
								: vat
									? 'С НДС 22%'
									: 'Без НДС'}{#if option.vehicle}
								· {option.vehicle}{/if}
							{#if option.days}
								· {duration(option.days)}{/if}
						</p>
					</article>
				{/each}
			</div>
			<p class="estimate-note">
				Предварительная стоимость. Итог зависит от объёма, свойств груза, адресов и условий погрузки. Уточните
				цену у перевозчика.
			</p>
		{:else}
			<div class="empty-result">
				<span class="empty-symbol" aria-hidden="true">₽</span>
				<div>
					<h2>Сравните варианты перевозки</h2>
					<p>
						Укажите маршрут и вес. Покажем стоимость отдельной машины и сборного груза, если он доступен.
						Контейнер появится при наличии тарифа.
					</p>
				</div>
			</div>
		{/if}
	</section>
	<p class="source-note">
		Тарифы: <a href={sourceUrl} target="_blank" rel="noreferrer">datrans.ru</a>. Проверены {new Intl.DateTimeFormat(
			'ru-RU',
			{ day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' },
		).format(new Date(checkedAt))}.
	</p>
</div>
