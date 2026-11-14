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
	const city = page.getByRole('combobox')

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
	const city = page.getByRole('combobox')

	await city.fill('')
	await page.getByRole('option').nth(5).dispatchEvent('pointerdown', { pointerType: 'touch' })
	await expect(city).toHaveAttribute('aria-expanded', 'true')
	await expect(city).toHaveValue('')
	await page.getByRole('option', { name: 'Самара', exact: true }).click()
	await expect(city).toHaveValue('Самара')
})
