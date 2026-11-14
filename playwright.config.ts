import preset from '@aimuzov/infra-site-kit/playwright'
import { defineConfig } from '@playwright/test'

const port = Number(process.env.E2E_PORT ?? 4399)
const baseURL = `http://127.0.0.1:${port}`

export default defineConfig({
	...preset,
	use: { ...preset.use, baseURL },
	webServer: {
		command: `astro build && astro preview --host 127.0.0.1 --port ${port} --ignore-lock`,
		url: baseURL,
		reuseExistingServer: false,
		timeout: 180_000,
	},
})
