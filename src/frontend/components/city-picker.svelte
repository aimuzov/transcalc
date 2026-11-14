<script lang="ts">
	import Input from '@aimuzov/infra-site-kit/ui/input.svelte'
	import { cities } from '#frontend/lib/calculator.ts'
	let {
		value = $bindable('sankt-peterburg'),
		id,
		onchange,
	}: { value?: string; id: string; onchange: () => void } = $props()
	let query = $state('')
	let syncedValue: string | undefined

	$effect(() => {
		if (value !== syncedValue) {
			query = cities.find((city) => city.id === value)?.name ?? ''
			syncedValue = value
		}
	})

	let open = $state(false)
	let active = $state(-1)
	const choices = $derived(
		cities.filter((city) => city.name.toLocaleLowerCase('ru').includes(query.trim().toLocaleLowerCase('ru'))),
	)

	function choose(index: number) {
		const city = choices[index]

		if (!city) return

		syncedValue = city.id
		value = city.id
		query = city.name
		open = false
		active = -1
		onchange()
	}
	function keydown(event: KeyboardEvent) {
		if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
			event.preventDefault()
			open = true

			if (event.key === 'Home') active = 0
			else if (event.key === 'End') active = choices.length - 1
			else active = Math.max(0, Math.min(choices.length - 1, active + (event.key === 'ArrowDown' ? 1 : -1)))

			requestAnimationFrame(() =>
				document.getElementById(`${id}-option-${active}`)?.scrollIntoView({ block: 'nearest' }),
			)
		} else if (event.key === 'Enter' && open) {
			event.preventDefault()
			choose(active < 0 ? 0 : active)
		} else if (event.key === 'Escape') {
			open = false
			active = -1
		} else if (event.key === 'Tab') open = false
	}
</script>

<div
	class="city-picker"
	onfocusout={(event) => {
		if (!event.currentTarget.contains(event.relatedTarget as Node)) open = false
	}}
>
	<Input
		{id}
		bind:value={query}
		role="combobox"
		aria-autocomplete="list"
		aria-expanded={open}
		aria-controls={`${id}-list`}
		aria-activedescendant={open && active >= 0 ? `${id}-option-${active}` : undefined}
		autocomplete="off"
		placeholder="Найти город"
		onkeydown={keydown}
		onfocus={() => {
			open = true
			active = -1
		}}
		oninput={() => {
			syncedValue = ''
			value = ''
			open = true
			active = -1
			onchange()
		}}
	/>
	{#if open}
		<div class="city-menu">
			<ul id={`${id}-list`} role="listbox" aria-label="Города">
				{#each choices as city, index (city.id)}
					<li
						id={`${id}-option-${index}`}
						role="option"
						aria-selected={active === index}
						class:highlighted={active === index}
						onmousedown={(event) => {
							event.preventDefault()
						}}
						onclick={() => choose(index)}
						onkeydown={keydown}
					>
						{city.name}
					</li>
				{/each}
			</ul>
			{#if choices.length === 0}<p class="city-empty" role="status">Город не найден. Проверьте название.</p>{/if}
		</div>
	{/if}
</div>
