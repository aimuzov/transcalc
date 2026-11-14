import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

test('на широком экране история занимает полную ширину, ссылка в шапке показана иконкой', async ({ page }) => {
	await page.setViewportSize({ width: 1440, height: 1000 })
	await page.goto('/changelog/')
	const body = page.locator('.changelog__body')

	expect((await body.boundingBox())!.width).toBeGreaterThan(500)
	const link = page.getByRole('link', { name: 'Что нового', exact: true })

	await expect(link.locator('svg')).toHaveCount(1)
	await expect(link).toHaveText('')
})

test('история изменений и тема доступны на обеих страницах', async ({ page }) => {
	await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' })
	await page.goto('/')
	const theme = page.getByRole('button', { name: /^Тема:/ })

	await theme.click()
	await expect(page.locator('html')).toHaveCSS('color-scheme', 'dark')
	await page.reload()
	await expect(page.locator('html')).toHaveCSS('color-scheme', 'dark')
	await page.getByRole('link', { name: 'Что нового', exact: true }).click()
	await expect(page.getByRole('heading', { name: 'Что нового', exact: true })).toBeVisible()
	await expect(page.getByRole('heading', { name: 'Перевозки между регионами', exact: true })).toBeVisible()
	await expect(page.locator('html')).toHaveCSS('color-scheme', 'dark')
	expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
	await page.setViewportSize({ width: 320, height: 780 })
	expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
	await page.screenshot({ path: '/tmp/transcalc-changelog-dark.png', fullPage: true })
	await page.getByRole('button', { name: /^Тема:/ }).click()
	expect(await page.evaluate(() => getComputedStyle(document.documentElement).colorScheme)).toMatch(/light/)
	await page.screenshot({ path: '/tmp/transcalc-changelog-light.png', fullPage: true })
})
