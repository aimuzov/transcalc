import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

test('расчёт, НДС и смена направления', async ({ page }) => {
	await page.goto('/')
	await page.getByRole('button', { name: 'Рассчитать стоимость' }).click()
	await expect(page.getByRole('heading', { name: 'Москва → Санкт-Петербург' })).toBeVisible()
	await expect(page.getByText('Сборный груз', { exact: true })).toBeVisible()
	await expect(page.locator('.quote-primary .price')).toHaveText(/18\s200\s₽/)
	await page.screenshot({ path: '/tmp/transcalc-desktop.png', fullPage: true })
	expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
	await expect(page).toHaveURL(/weight=1000/)
	await page.getByRole('switch', { name: 'Включить НДС 22%' }).click()
	await expect(page.getByText('Без НДС', { exact: true }).first()).toBeVisible()
	await expect(page.locator('.quote-primary .price')).toHaveText(/14\s918\s₽/)
	await page.getByRole('button', { name: 'Поменять направление' }).click()
	await expect(page.getByRole('heading', { name: 'Москва → Санкт-Петербург' })).not.toBeVisible()
	await page.getByRole('button', { name: 'Рассчитать стоимость' }).click()
	await expect(page.getByRole('heading', { name: 'Санкт-Петербург → Москва' })).toBeVisible()
})

test('город выбирается клавиатурой, неверный вес не рассчитывается', async ({ page }) => {
	await page.goto('/')
	const city = page.getByRole('combobox', { name: 'Куда', exact: true })

	await city.fill('Казань')
	await city.press('ArrowDown')
	await city.press('Enter')
	await expect(city).toHaveValue('Казань')
	await page.getByRole('button', { name: 'Рассчитать стоимость' }).click()
	await expect(page.getByRole('heading', { name: 'Москва → Казань' })).toBeVisible()
	await page.reload()
	await expect(city).toHaveValue('Казань')
	await page.getByLabel('Вес груза, кг').fill('0')
	await page.getByRole('button', { name: 'Рассчитать стоимость' }).click()
	await expect(page.getByRole('alert')).toContainText('Укажите вес')
	await page.getByLabel('Вес груза, кг').fill('499')
	await page.getByRole('button', { name: 'Рассчитать стоимость' }).click()
	await expect(page.getByRole('alert')).toContainText('500')
})

test('ссылка восстанавливает расчёт, мобильная страница не выходит за экран', async ({ page }) => {
	await page.setViewportSize({ width: 320, height: 780 })
	await page.goto('/?from=moskva&to=sankt-peterburg&weight=500')
	await expect(page.getByRole('heading', { name: 'Москва → Санкт-Петербург' })).toBeVisible()
	expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
	await page.screenshot({ path: '/tmp/transcalc-mobile.png', fullPage: true })
	await page.getByLabel('Вес груза, кг').fill('20001')
	await expect(page.getByRole('heading', { name: 'Москва → Санкт-Петербург' })).not.toBeVisible()
	await page.getByRole('button', { name: 'Рассчитать стоимость' }).click()
	await expect(page.getByRole('alert')).toContainText('20 000')
})

test('неопубликованный тариф обозначается явно', async ({ page }) => {
	await page.goto('/?from=moskva&to=abay&weight=1000')
	await expect(page.getByRole('alert')).toContainText('нет опубликованного тарифа')
	await expect(page.locator('.price')).toHaveCount(0)
})

test('контейнер сравнивается по показанной цене при переключении НДС', async ({ page }) => {
	await page.goto('/?from=moskva&to=vladivostok&weight=20000')
	await page.getByRole('switch', { name: 'Включить НДС 22%' }).click()
	await expect(page.locator('.quote-primary h3')).toHaveText('Контейнер')
	await expect(page.locator('.quote-primary .price')).toHaveText(/194\s600\s₽/)
	await expect(page.locator('.quote-primary')).toContainText('Доступен только с НДС')
})

test('срок контейнера указан в его карточке', async ({ page }) => {
	await page.goto('/?from=moskva&to=irkutsk&weight=20000')
	await expect(page.locator('.quote-primary')).toContainText('18 дн.')
	await expect(page.locator('.result-meta')).not.toContainText('дн.')
})

test('начало касания списка не выбирает город', async ({ page }) => {
	await page.goto('/')
	const city = page.getByRole('combobox', { name: 'Куда', exact: true })

	await city.fill('')
	await page.getByRole('option').nth(5).dispatchEvent('pointerdown', { pointerType: 'touch' })
	await expect(city).toHaveAttribute('aria-expanded', 'true')
	await expect(city).toHaveValue('')
	await page.getByRole('option', { name: 'Самара', exact: true }).click()
	await expect(city).toHaveValue('Самара')
})

test('оба города доступны для выбора, совпадающие города не рассчитываются', async ({ page }) => {
	await page.goto('/')
	await expect(page.getByRole('combobox')).toHaveCount(2)
	const from = page.getByRole('combobox', { name: 'Откуда' })
	const to = page.getByRole('combobox', { name: 'Куда', exact: true })

	await from.fill('Казань')
	await from.press('ArrowDown')
	await from.press('Enter')
	await to.fill('Казань')
	await to.press('ArrowDown')
	await to.press('Enter')
	await page.getByRole('button', { name: 'Рассчитать стоимость' }).click()
	await expect(page.getByRole('alert')).toContainText('должны отличаться')
	await expect(page.locator('.price')).toHaveCount(0)
})

test('пара без Москвы восстанавливается по ссылке и учитывает направление тарифа', async ({ page }) => {
	await page.setViewportSize({ width: 320, height: 780 })
	await page.goto('/?from=samara&to=kazan&weight=20000')
	await expect(page.getByRole('combobox', { name: 'Откуда', exact: true })).toHaveValue('Самара')
	await expect(page.getByRole('combobox', { name: 'Куда', exact: true })).toHaveValue('Казань')
	await expect(page.getByRole('heading', { name: 'Самара → Казань' })).toBeVisible()

	await expect(
		page
			.locator('.quote-option')
			.filter({ has: page.getByRole('heading', { name: 'Отдельная машина' }) })
			.locator('.price'),
	).toHaveText(/53\s200\s₽/)

	expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
	expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
	await page.screenshot({ path: '/tmp/transcalc-non-moscow-mobile.png', fullPage: true })
	await page.getByRole('button', { name: 'Поменять направление' }).click()
	await expect(page.getByRole('combobox', { name: 'Откуда', exact: true })).toHaveValue('Казань')
	await expect(page.getByRole('combobox', { name: 'Куда', exact: true })).toHaveValue('Самара')
	await expect(page.locator('.price')).toHaveCount(0)
	await page.getByRole('button', { name: 'Рассчитать стоимость' }).click()
	await expect(page.getByRole('heading', { name: 'Казань → Самара' })).toBeVisible()

	await expect(
		page
			.locator('.quote-option')
			.filter({ has: page.getByRole('heading', { name: 'Отдельная машина' }) })
			.locator('.price'),
	).toHaveText(/35\s000\s₽/)

	await expect(page).toHaveURL(/from=kazan&to=samara&weight=20000/)
	await page.reload()
	await expect(page.getByRole('heading', { name: 'Казань → Самара' })).toBeVisible()
})

test('обмен направления очищает недовыбранный город без старой подписи', async ({ page }) => {
	await page.goto('/')
	const from = page.getByRole('combobox', { name: 'Откуда', exact: true })
	const to = page.getByRole('combobox', { name: 'Куда', exact: true })

	await to.fill('Каз')
	await expect(to).toHaveValue('Каз')
	await page.getByRole('button', { name: 'Поменять направление' }).click()
	await expect(from).toHaveValue('')
	await expect(to).toHaveValue('Москва')
	await from.fill('Сам')
	await expect(from).toHaveValue('Сам')
	await from.fill('Самара')
	await from.press('ArrowDown')
	await from.press('Enter')
	await expect(from).toHaveValue('Самара')
})
