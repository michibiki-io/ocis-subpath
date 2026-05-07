import {
  expect,
  request as playwrightRequest,
  test,
  type APIRequestContext,
  type Browser,
  type BrowserContext,
  type Page,
  type Request,
  type Response
} from '@playwright/test'
import crypto from 'node:crypto'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

function normalizeSubpath(raw = '/ocis'): string {
  if (!raw || raw === '/') {
    return ''
  }
  return `/${raw.replace(/^\/+/, '').replace(/\/+$/, '')}`
}

const subpath = normalizeSubpath(process.env.E2E_SUBPATH)
const origin = (process.env.E2E_BASE_ORIGIN || 'https://127.0.0.1:9200').replace(/\/+$/, '')
const baseUrl = process.env.E2E_BASE_URL || `${origin}${subpath}`
const basePath = new URL(baseUrl).pathname.replace(/\/+$/, '')
const allowRootRewrite = /^(1|true|yes|on)$/i.test(process.env.E2E_ALLOW_ROOT_REWRITE || '')
const loginUser = process.env.E2E_USERNAME
const loginPassword = process.env.E2E_PASSWORD
const scenarioPassword = process.env.E2E_SCENARIO_PASSWORD || 'E2e-User-Password-123!'
const videoFileName = 'Big_Buck_Bunny_alt.webm'
const zipFileName = 'Big_Buck_Bunny_alt.zip'
const markdownFileName = 'commonmark-smoke.md'
const samplePdfFileName = 'sample.pdf'
const videoSourceUrl = 'https://commons.wikimedia.org/wiki/Special:Redirect/file/Big_Buck_Bunny_alt.webm'
const resultsDir = path.resolve(__dirname, 'test-results')
const markdownFixturePath = path.resolve(__dirname, 'fixtures/commonmark-smoke.md')
const samplePdfFixturePath = path.resolve(__dirname, 'fixtures/sample.pdf')
const assetsDir = process.env.E2E_ASSET_CACHE_DIR
  ? path.resolve(process.env.E2E_ASSET_CACHE_DIR)
  : path.join(os.tmpdir(), 'ocis-subpath-e2e-assets')
const videoFixturePath = path.join(assetsDir, videoFileName)
const suspiciousPrefixes = [
  '/config.json',
  '/api/',
  '/dav/',
  '/data/',
  '/favicon.ico',
  '/graph/',
  '/js/',
  '/themes/',
  '/fonts/',
  '/icons/',
  '/oidc-callback.html',
  '/oidc-silent-redirect.html',
  '/ocs/',
  '/remote.php/',
  '/thumbnails/'
]

function url(pathname = ''): string {
  const suffix = pathname.startsWith('/') ? pathname : `/${pathname}`
  return pathname ? `${baseUrl}${suffix}` : `${baseUrl}/`
}

function originUrl(pathname = ''): string {
  const suffix = pathname.startsWith('/') ? pathname : `/${pathname}`
  return `${new URL(baseUrl).origin}${suffix}`
}

function escapedUrlPath(pathname: string): string {
  return pathname.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function currentPathIsInsideSubpath(currentUrl: string): boolean {
  const current = new URL(currentUrl)
  const base = new URL(`${baseUrl}/`)
  return current.origin === base.origin && current.pathname.startsWith(base.pathname)
}

function frameIsLoginProvider(request: Request): boolean {
  try {
    const frameUrl = request.frame().url()
    if (!frameUrl) {
      return false
    }
    const pathname = new URL(frameUrl).pathname
    return pathname.startsWith('/signin') || pathname.startsWith('/konnect')
  } catch {
    return false
  }
}

function isCriticalResponse(response: Response): boolean {
  const status = response.status()
  if (status < 400) {
    return false
  }
  if (status === 404 && (response.url().includes('processor=thumbnail') || response.url().includes('/thumbnails'))) {
    return false
  }
  return ['document', 'script', 'stylesheet', 'fetch', 'xhr'].includes(response.request().resourceType())
}

function suspiciousRootAbsolute(request: Request): boolean {
  const requestUrl = new URL(request.url())
  const base = new URL(`${baseUrl}/`)
  if (requestUrl.origin !== base.origin) {
    return false
  }
  if (requestUrl.pathname.startsWith(base.pathname)) {
    return false
  }
  if (frameIsLoginProvider(request)) {
    return false
  }
  return suspiciousPrefixes.some((prefix) => requestUrl.pathname === prefix || requestUrl.pathname.startsWith(prefix))
}

async function collectPageSignals(page: Page) {
  const pageErrors: string[] = []
  const consoleErrors: string[] = []
  const failedRequests: string[] = []
  const criticalResponses: string[] = []
  const suspiciousRequests: string[] = []

  page.on('pageerror', (error) => {
    pageErrors.push(error.message)
  })
  page.on('console', (message) => {
    if (message.type() === 'error') {
      consoleErrors.push(message.text())
    }
  })
  page.on('requestfailed', (request) => {
    failedRequests.push(`${request.method()} ${request.url()} :: ${request.failure()?.errorText || 'unknown'}`)
  })
  page.on('request', (request) => {
    if (suspiciousRootAbsolute(request)) {
      suspiciousRequests.push(`${request.method()} ${request.url()}`)
    }
  })
  page.on('response', (response) => {
    if (isCriticalResponse(response)) {
      criticalResponses.push(`${response.status()} ${response.request().resourceType()} ${response.url()}`)
    }
  })

  return { pageErrors, consoleErrors, failedRequests, criticalResponses, suspiciousRequests }
}

async function waitForStableLoad(page: Page) {
  await page.waitForLoadState('domcontentloaded')
  try {
    await page.waitForLoadState('networkidle', { timeout: 15_000 })
  } catch {
    // Best-effort only.
  }
}

async function login(page: Page, username = loginUser!, password = loginPassword!) {
  await page.goto(url(), { waitUntil: 'domcontentloaded' })
  await waitForStableLoad(page)

  const userField = page
    .locator('input[autocomplete="username"], input[name="username"], input[type="email"], input[type="text"]')
    .first()
  const passwordField = page
    .locator('input[autocomplete="current-password"], input[name="password"], input[type="password"]')
    .first()
  await userField.fill(username)
  await passwordField.fill(password)

  const submitButton = page.getByRole('button', { name: /log in|login|sign in|ログイン/i }).first()
  await submitButton.click()
  await expect(page.locator('#_userMenuButton')).toBeVisible({ timeout: 60_000 })
  await waitForStableLoad(page)
}

function encodePath(...segments: string[]): string {
  return segments.map((segment) => segment.split('/').map(encodeURIComponent).join('/')).join('/')
}

function encodeMetadata(metadata: Record<string, string>): string {
  return Object.entries(metadata)
    .map(([key, value]) => `${key} ${Buffer.from(value).toString('base64')}`)
    .join(',')
}

function sha256(buffer: Buffer): string {
  return crypto.createHash('sha256').update(buffer).digest('hex')
}

function ensureStatus(response: { status(): number }, allowedStatuses: number[], description: string) {
  expect(allowedStatuses, `${description} returned ${response.status()}`).toContain(response.status())
}

async function ensureVideoFixture() {
  fs.mkdirSync(assetsDir, { recursive: true })
  if (fs.existsSync(videoFixturePath) && fs.statSync(videoFixturePath).size > 0) {
    return
  }

  const response = await fetch(videoSourceUrl)
  if (!response.ok) {
    throw new Error(`Failed to download fixture: ${response.status} ${response.statusText}`)
  }
  fs.writeFileSync(videoFixturePath, Buffer.from(await response.arrayBuffer()))
}

async function createFolderFromUi(page: Page, folderName: string) {
  await page.locator('#new-file-menu-btn').click()
  await page.locator('.oc-drop, .oc-dropdown').getByText('Folder', { exact: true }).click()
  const dialog = page.getByRole('dialog')
  await dialog.locator('input[type="text"]').fill(folderName)
  await dialog.getByRole('button', { name: /create/i }).click()
  await expect(page.getByText(folderName, { exact: true }).first()).toBeVisible({ timeout: 30_000 })
}

async function enterFolderFromUi(page: Page, folderName: string) {
  await page.getByText(folderName, { exact: true }).first().dblclick()
  await expect(page.locator('body')).toContainText(/new|upload|files/i, { timeout: 30_000 })
}

async function waitForUploadedDriveFile(
  api: APIRequestContext,
  driveId: string,
  pathSegments: string[],
  expectedBuffer: Buffer
) {
  const fileUrl = url(`/dav/spaces/${encodePath(driveId, ...pathSegments)}`)

  await expect.poll(async () => {
    const response = await api.get(fileUrl, { failOnStatusCode: false })
    if (response.status() !== 200) {
      return `status:${response.status()}`
    }
    return sha256(Buffer.from(await response.body()))
  }, { timeout: 120_000 }).toBe(sha256(expectedBuffer))
}

async function uploadFileFromUi(
  page: Page,
  fileName: string,
  mimeType: string,
  buffer: Buffer,
  verification?: { api: APIRequestContext; driveId: string; pathSegments: string[] }
) {
  const base = new URL(`${baseUrl}/`)
  const baseApiPath = `${base.pathname.replace(/\/$/, '')}/dav/`
  const uploadCreated = page.waitForResponse((response) => {
    const responseUrl = new URL(response.url())
    return (
      responseUrl.origin === base.origin &&
      responseUrl.pathname.startsWith(baseApiPath) &&
      ['POST', 'PUT', 'PATCH'].includes(response.request().method()) &&
      [200, 201, 204].includes(response.status())
    )
  }, { timeout: 120_000 })
    .catch(() => undefined)

  await page.locator('#upload-menu-btn').click()
  await page.locator('#files-file-upload-input').setInputFiles({ name: fileName, mimeType, buffer })
  if (verification) {
    await waitForUploadedDriveFile(verification.api, verification.driveId, verification.pathSegments, buffer)
  } else {
    expect(await uploadCreated, `upload response for ${fileName}`).toBeTruthy()
  }
  await expect(page.getByText(/Unknown error/i)).toHaveCount(0, { timeout: 30_000 })
  await page.reload({ waitUntil: 'domcontentloaded' })
  await waitForStableLoad(page)
  await expect(page.getByText(fileName, { exact: true }).first()).toBeVisible({ timeout: 60_000 })
}

async function getAccessToken(page: Page): Promise<string> {
  const state = await page.context().storageState()
  const origin = state.origins.find((item) => item.origin === new URL(baseUrl).origin)
  const oauthEntry = origin?.localStorage.find((item) => item.name.startsWith('oc_oAuth.user:') && item.name.endsWith(':web'))
  if (!oauthEntry) {
    throw new Error('OAuth storage entry was not found after login')
  }
  const payload = JSON.parse(oauthEntry.value)
  const token = payload.access_token || payload.accessToken
  if (!token) {
    throw new Error('OAuth access token was not found after login')
  }
  return token
}

async function authenticatedApi(page: Page): Promise<APIRequestContext> {
  const accessToken = await getAccessToken(page)
  return playwrightRequest.newContext({
    ignoreHTTPSErrors: true,
    extraHTTPHeaders: {
      Authorization: `Bearer ${accessToken}`
    }
  })
}

async function recordedPage(browser: Browser, label: string): Promise<{ context: BrowserContext; page: Page; label: string }> {
  const context = await browser.newContext({
    acceptDownloads: true,
    ignoreHTTPSErrors: true,
    recordVideo: {
      dir: resultsDir,
      size: { width: 1280, height: 720 }
    }
  })
  const page = await context.newPage()
  return { context, page, label }
}

async function closeRecordedPage(recording: { context: BrowserContext; page: Page; label: string }) {
  const video = recording.page.video()
  await recording.context.close()
  if (!video) {
    return
  }
  const recordedPath = await video.path()
  const finalVideoPath = path.join(resultsDir, `ocis-subpath-${recording.label}.webm`)
  fs.rmSync(finalVideoPath, { force: true })
  fs.renameSync(recordedPath, finalVideoPath)
}

async function personalDriveId(api: APIRequestContext): Promise<string> {
  const response = await api.get(url('/graph/v1.0/me/drives?$filter=driveType%20eq%20personal'))
  expect(response.status()).toBe(200)
  const body = await response.json()
  const driveId = body.value?.[0]?.id
  expect(driveId).toBeTruthy()
  return driveId
}

async function uploadFileViaTus(
  api: APIRequestContext,
  driveId: string,
  parentPath: string[],
  fileName: string,
  contentType: string,
  fileBuffer: Buffer
) {
  const uploadPath = url(`/dav/spaces/${encodePath(driveId, ...parentPath)}`)
  const response = await api.post(uploadPath, {
    headers: {
      'Content-Type': 'application/offset+octet-stream',
      'Tus-Resumable': '1.0.0',
      'Upload-Length': String(fileBuffer.length),
      'Upload-Metadata': encodeMetadata({
        name: fileName,
        filename: fileName,
        type: contentType,
        filetype: contentType,
        mtime: String(Math.floor(Date.now() / 1000))
      })
    },
    data: fileBuffer
  })
  expect(response.status()).toBe(201)
  expect(response.headers()['upload-offset']).toBe(String(fileBuffer.length))
}

async function uploadVideoViaTus(api: APIRequestContext, driveId: string, folderName: string, fileBuffer: Buffer) {
  await uploadFileViaTus(api, driveId, [folderName], videoFileName, 'video/webm', fileBuffer)
}

async function deleteSpaceFile(api: APIRequestContext, driveId: string, fileName: string) {
  const response = await api.delete(url(`/dav/spaces/${encodePath(driveId, fileName)}`), {
    failOnStatusCode: false
  })
  ensureStatus(response, [200, 204, 404], `delete ${fileName}`)
}

async function putSpaceFile(
  api: APIRequestContext,
  driveId: string,
  fileName: string,
  contentType: string,
  contents: string | Buffer
) {
  const response = await api.put(url(`/dav/spaces/${encodePath(driveId, fileName)}`), {
    headers: {
      'Content-Type': contentType
    },
    data: contents
  })
  ensureStatus(response, [200, 201, 204], `put ${fileName}`)
}

async function downloadSpaceFile(api: APIRequestContext, driveId: string, fileName: string): Promise<Buffer> {
  const fileUrl = url(`/dav/spaces/${encodePath(driveId, fileName)}`)
  for (let attempt = 0; attempt < 30; attempt += 1) {
    const response = await api.get(fileUrl, { failOnStatusCode: false })
    if (response.status() === 200) {
      return Buffer.from(await response.body())
    }
    if (response.status() !== 425) {
      expect(response.status()).toBe(200)
    }
    await new Promise((resolve) => setTimeout(resolve, 1_000))
  }
  const response = await api.get(fileUrl, { failOnStatusCode: false })
  expect(response.status()).toBe(200)
  return Buffer.from(await response.body())
}

async function downloadAuthenticatedFile(api: APIRequestContext, driveId: string, folderName: string): Promise<Buffer> {
  const response = await api.get(url(`/dav/spaces/${encodePath(driveId, folderName, videoFileName)}`))
  expect(response.status()).toBe(200)
  return Buffer.from(await response.body())
}

async function createPublicShareForSpace(api: APIRequestContext, driveId: string, fileName: string, password: string): Promise<string> {
  const response = await api.post(url('/ocs/v2.php/apps/files_sharing/api/v1/shares?format=json'), {
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      'OCS-APIRequest': 'true'
    },
    form: {
      space_ref: `${driveId}/${fileName}`,
      shareType: '3',
      permissions: '1',
      password
    }
  })
  expect(response.status()).toBe(200)
  const body = await response.json()
  const token = body.ocs?.data?.token
  expect(token).toBeTruthy()
  expect(body.ocs.data.url).toContain(`${baseUrl}/s/`)
  return token
}

async function createPublicShare(api: APIRequestContext, folderName: string, password: string): Promise<string> {
  const response = await api.post(url('/ocs/v2.php/apps/files_sharing/api/v1/shares?format=json'), {
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      'OCS-APIRequest': 'true'
    },
    form: {
      path: `/${folderName}/${videoFileName}`,
      shareType: '3',
      permissions: '1',
      password
    }
  })
  expect(response.status()).toBe(200)
  const body = await response.json()
  const token = body.ocs?.data?.token
  expect(token).toBeTruthy()
  expect(body.ocs.data.url).toContain(`${baseUrl}/s/`)
  return token
}

async function downloadPublicShare(token: string, password: string): Promise<Buffer> {
  const publicApi = await playwrightRequest.newContext({
    ignoreHTTPSErrors: true,
    extraHTTPHeaders: {
      Authorization: `Basic ${Buffer.from(`${token}:${password}`).toString('base64')}`
    }
  })
  try {
    const response = await publicApi.get(url(`/remote.php/dav/public-files/${encodePath(token, videoFileName)}`))
    expect(response.status()).toBe(200)
    return Buffer.from(await response.body())
  } finally {
    await publicApi.dispose()
  }
}

async function downloadPublicShareFile(token: string, password: string, fileName: string): Promise<Buffer> {
  const publicApi = await playwrightRequest.newContext({
    ignoreHTTPSErrors: true,
    extraHTTPHeaders: {
      Authorization: `Basic ${Buffer.from(`${token}:${password}`).toString('base64')}`
    }
  })
  try {
    const response = await publicApi.get(url(`/remote.php/dav/public-files/${encodePath(token, fileName)}`))
    expect(response.status()).toBe(200)
    return Buffer.from(await response.body())
  } finally {
    await publicApi.dispose()
  }
}

function crc32(buffer: Buffer): number {
  let crc = 0xffffffff
  for (const byte of buffer) {
    crc ^= byte
    for (let i = 0; i < 8; i += 1) {
      crc = (crc >>> 1) ^ (crc & 1 ? 0xedb88320 : 0)
    }
  }
  return (crc ^ 0xffffffff) >>> 0
}

function dosDateTime(date = new Date()): { date: number; time: number } {
  const year = Math.max(1980, date.getFullYear())
  return {
    time: (date.getHours() << 11) | (date.getMinutes() << 5) | Math.floor(date.getSeconds() / 2),
    date: ((year - 1980) << 9) | ((date.getMonth() + 1) << 5) | date.getDate()
  }
}

function createStoredZip(fileName: string, contents: Buffer): Buffer {
  const name = Buffer.from(fileName)
  const checksum = crc32(contents)
  const modified = dosDateTime()
  const localHeader = Buffer.alloc(30)
  localHeader.writeUInt32LE(0x04034b50, 0)
  localHeader.writeUInt16LE(20, 4)
  localHeader.writeUInt16LE(0, 6)
  localHeader.writeUInt16LE(0, 8)
  localHeader.writeUInt16LE(modified.time, 10)
  localHeader.writeUInt16LE(modified.date, 12)
  localHeader.writeUInt32LE(checksum, 14)
  localHeader.writeUInt32LE(contents.length, 18)
  localHeader.writeUInt32LE(contents.length, 22)
  localHeader.writeUInt16LE(name.length, 26)
  localHeader.writeUInt16LE(0, 28)

  const centralDirectory = Buffer.alloc(46)
  centralDirectory.writeUInt32LE(0x02014b50, 0)
  centralDirectory.writeUInt16LE(20, 4)
  centralDirectory.writeUInt16LE(20, 6)
  centralDirectory.writeUInt16LE(0, 8)
  centralDirectory.writeUInt16LE(0, 10)
  centralDirectory.writeUInt16LE(modified.time, 12)
  centralDirectory.writeUInt16LE(modified.date, 14)
  centralDirectory.writeUInt32LE(checksum, 16)
  centralDirectory.writeUInt32LE(contents.length, 20)
  centralDirectory.writeUInt32LE(contents.length, 24)
  centralDirectory.writeUInt16LE(name.length, 28)
  centralDirectory.writeUInt16LE(0, 30)
  centralDirectory.writeUInt16LE(0, 32)
  centralDirectory.writeUInt16LE(0, 34)
  centralDirectory.writeUInt16LE(0, 36)
  centralDirectory.writeUInt32LE(0, 38)
  centralDirectory.writeUInt32LE(0, 42)

  const centralDirectoryOffset = localHeader.length + name.length + contents.length
  const centralDirectorySize = centralDirectory.length + name.length
  const end = Buffer.alloc(22)
  end.writeUInt32LE(0x06054b50, 0)
  end.writeUInt16LE(0, 4)
  end.writeUInt16LE(0, 6)
  end.writeUInt16LE(1, 8)
  end.writeUInt16LE(1, 10)
  end.writeUInt32LE(centralDirectorySize, 12)
  end.writeUInt32LE(centralDirectoryOffset, 16)
  end.writeUInt16LE(0, 20)

  return Buffer.concat([localHeader, name, contents, centralDirectory, name, end])
}

async function playPreviewForTenSeconds(page: Page, folderName: string) {
  await page.getByText(videoFileName, { exact: true }).first().dblclick()
  const previewPrefix = `${basePath}/preview`
  await expect(page).toHaveURL(new RegExp(`${escapedUrlPath(previewPrefix)}/.+/${escapedUrlPath(folderName)}/${escapedUrlPath(videoFileName)}`), { timeout: 30_000 })
  const video = page.locator('video').first()
  await expect(video).toBeVisible({ timeout: 30_000 })

  const playback = await video.evaluate(async (node) => {
    const element = node as HTMLVideoElement
    element.muted = true
    element.volume = 0

    await Promise.race([
      element.play(),
      new Promise((_, reject) => window.setTimeout(() => reject(new Error('video play timed out')), 20_000))
    ])

    const start = element.currentTime
    await new Promise<void>((resolve, reject) => {
      const deadline = window.setTimeout(() => reject(new Error('video did not advance for 10 seconds')), 25_000)
      const tick = () => {
        if (element.currentTime - start >= 10) {
          window.clearTimeout(deadline)
          resolve()
          return
        }
        window.requestAnimationFrame(tick)
      }
      tick()
    })

    return {
      advanced: element.currentTime - start,
      currentTime: element.currentTime,
      networkState: element.networkState,
      readyState: element.readyState
    }
  })

  expect(playback.readyState).toBeGreaterThanOrEqual(2)
  expect(playback.advanced).toBeGreaterThanOrEqual(10)
  await page.keyboard.press('Escape')
  try {
    await expect(page.getByText(videoFileName, { exact: true }).first()).toBeVisible({ timeout: 5_000 })
  } catch {
    await page.goBack({ waitUntil: 'domcontentloaded' })
    await waitForStableLoad(page)
    await expect(page.getByText(videoFileName, { exact: true }).first()).toBeVisible({ timeout: 30_000 })
  }
}

async function logoutToLoginPage(page: Page) {
  await page.locator('#_userMenuButton').click()
  await page.getByText(/log out|logout|sign out|ログアウト/i).first().click()
  await expect(page.locator('input[type="password"]').first()).toBeVisible({ timeout: 30_000 })
  await expect(page.locator('body')).toContainText(/log in|login|sign in|username|password|ログイン/i)
}

async function ensureUser(api: APIRequestContext, username: string): Promise<{ id: string; displayName: string }> {
  const existing = await api.get(url(`/graph/v1.0/users/${encodeURIComponent(username)}`), { failOnStatusCode: false })
  if (existing.status() === 200) {
    return existing.json()
  }
  ensureStatus(existing, [404], `lookup user ${username}`)

  const response = await api.post(url('/graph/v1.0/users'), {
    headers: {
      'Content-Type': 'application/json'
    },
    data: {
      displayName: username[0].toUpperCase() + username.slice(1),
      mail: `${username}@example.test`,
      onPremisesSamAccountName: username,
      passwordProfile: {
        password: scenarioPassword
      }
    }
  })
  ensureStatus(response, [200, 201], `create user ${username}`)
  return response.json()
}

async function ensureGroup(api: APIRequestContext, displayName: string): Promise<{ id: string; displayName: string }> {
  const list = await api.get(url('/graph/v1.0/groups?$top=999'))
  expect(list.status()).toBe(200)
  const groups = await list.json()
  const existing = groups.value?.find((group: { displayName?: string }) => group.displayName === displayName)
  if (existing?.id) {
    return existing
  }

  const response = await api.post(url('/graph/v1.0/groups'), {
    headers: {
      'Content-Type': 'application/json'
    },
    data: {
      displayName
    }
  })
  ensureStatus(response, [200, 201], `create group ${displayName}`)
  return response.json()
}

async function addUserToGroup(api: APIRequestContext, groupId: string, userId: string) {
  const response = await api.post(url(`/graph/v1.0/groups/${encodeURIComponent(groupId)}/members/$ref`), {
    failOnStatusCode: false,
    headers: {
      'Content-Type': 'application/json'
    },
    data: {
      '@odata.id': `${baseUrl}/graph/v1.0/users/${userId}`
    }
  })
  if ([200, 204, 409].includes(response.status())) {
    return
  }
  if (response.status() === 400 && /already|exist|member/i.test(await response.text())) {
    return
  }
  ensureStatus(response, [200, 204, 409], `add user ${userId} to group ${groupId}`)
}

async function ensureProjectSpace(api: APIRequestContext, name: string): Promise<{ id: string; name: string }> {
  const list = await api.get(url("/graph/v1.0/drives?$filter=driveType%20eq%20'project'"))
  expect(list.status()).toBe(200)
  const drives = await list.json()
  const existing = drives.value?.find((drive: { name?: string; id?: string }) => drive.name === name)
  if (existing?.id) {
    return existing
  }

  const response = await api.post(url('/graph/v1.0/drives'), {
    headers: {
      'Content-Type': 'application/json'
    },
    data: {
      name,
      driveType: 'project',
      description: `${name} E2E project space`
    }
  })
  ensureStatus(response, [200, 201], `create project space ${name}`)
  return response.json()
}

async function shareSpaceMembership(
  api: APIRequestContext,
  driveId: string,
  shareWith: string,
  memberType: 'user' | 'group',
  role: 'viewer' | 'editor' | 'manager'
) {
  const response = await api.post(url('/ocs/v2.php/apps/files_sharing/api/v1/shares?format=json'), {
    failOnStatusCode: false,
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      'OCS-APIRequest': 'true'
    },
    form: {
      space_ref: driveId,
      shareType: memberType === 'group' ? '8' : '7',
      shareWith,
      role
    }
  })
  const body = await response.text()
  if (response.status() === 200 && /"statuscode"\s*:\s*(100|200)/.test(body)) {
    return
  }
  if (/already|exist|member/i.test(body)) {
    return
  }
  throw new Error(`share ${driveId} with ${memberType} ${shareWith} as ${role} returned ${response.status()}: ${body.slice(0, 1000)}`)
}

async function projectDriveIdForUser(api: APIRequestContext, name: string): Promise<string> {
  const response = await api.get(url("/graph/v1.0/me/drives?$filter=driveType%20eq%20'project'"))
  expect(response.status()).toBe(200)
  const body = await response.json()
  const drive = body.value?.find((item: { name?: string; id?: string }) => item.name === name)
  expect(drive?.id, `project space ${name} should be visible`).toBeTruthy()
  return drive.id
}

async function openProjectSpaceFromUi(page: Page, spaceName: string) {
  await page.goto(url('/files/spaces/projects'), { waitUntil: 'domcontentloaded' })
  await waitForStableLoad(page)
  const spaceEntry = page.getByText(spaceName, { exact: true }).first()
  await expect(spaceEntry).toBeVisible({ timeout: 30_000 })
  await spaceEntry.dblclick()
  await waitForStableLoad(page)
}

async function previewMarkdownFromUi(page: Page, fileName: string, expectedText: string) {
  const fileEntry = page.getByText(fileName, { exact: true }).first()
  await expect(fileEntry).toBeVisible({ timeout: 30_000 })
  await fileEntry.dblclick()
  await expect(page).toHaveURL(new RegExp(`${escapedUrlPath(basePath)}/(preview|text-editor)/`), { timeout: 30_000 })
  await expect(page.locator('body')).toContainText('CommonMark Smoke Test', { timeout: 30_000 })
  await page.keyboard.press('Control+End')
  await expect(page.locator('body')).toContainText(expectedText, { timeout: 30_000 })
}

async function previewPdfFromUi(page: Page, fileName: string) {
  const fileEntry = page.getByText(fileName, { exact: true }).first()
  await expect(fileEntry).toBeVisible({ timeout: 30_000 })
  await fileEntry.dblclick()
  await expect(page).toHaveURL(new RegExp(`${escapedUrlPath(basePath)}/(preview|pdf-viewer)/`), { timeout: 30_000 })
  await expect(page.locator('body')).toContainText(fileName, { timeout: 30_000 })
}

async function fileIdFromPropfind(api: APIRequestContext, driveId: string, fileName: string): Promise<string> {
  const response = await api.fetch(url(`/dav/spaces/${encodePath(driveId, fileName)}`), {
    method: 'PROPFIND',
    headers: {
      Depth: '0',
      'Content-Type': 'application/xml'
    },
    data: '<?xml version="1.0"?><d:propfind xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns"><d:prop><oc:fileid /></d:prop></d:propfind>'
  })
  expect(response.status()).toBe(207)
  const xml = await response.text()
  const match = xml.match(/<oc:fileid>([^<]+)<\/oc:fileid>/)
  expect(match?.[1], `fileid should be present for ${fileName}`).toBeTruthy()
  return match![1]
}

async function fileVersionKeys(api: APIRequestContext, fileId: string): Promise<string[]> {
  const response = await api.fetch(url(`/remote.php/dav/meta/${encodePath(fileId)}/v`), {
    method: 'PROPFIND',
    headers: {
      Depth: '1',
      'Content-Type': 'application/xml'
    },
    data: '<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:allprop /></d:propfind>'
  })
  expect(response.status()).toBe(207)
  const xml = await response.text()
  return [...xml.matchAll(/\/v\/([^/<]+)<\/d:href>/g)].map((match) => decodeURIComponent(match[1]))
}

test('config.json is served from the subpath', async ({ request }) => {
  const response = await request.get(url('/config.json'))
  expect(response.status()).toBe(200)
  const body = await response.json()
  expect(body.server).toBe(baseUrl)
  expect(body.theme.startsWith(`${baseUrl}/themes/`)).toBeTruthy()
  expect(body.openIdConnect.metadata_url).toBe(`${baseUrl}/.well-known/openid-configuration`)
  expect(body.openIdConnect.authority).toBe(baseUrl)
  expect(body.openIdConnect.client_id).toBeTruthy()
  expect(Array.isArray(body.apps)).toBeTruthy()
  expect(body.apps.length).toBeGreaterThan(0)
})

test('OIDC discovery is reachable through the subpath', async ({ request }) => {
  const response = await request.get(url('/.well-known/openid-configuration'))
  expect(response.status()).toBe(200)
  const body = await response.json()
  expect(body.issuer).toBe(baseUrl)
  expect(body.authorization_endpoint).toBeTruthy()
  expect(body.token_endpoint).toBeTruthy()
  expect(body.jwks_uri).toBeTruthy()
})

test('Web UI does not white-screen at the subpath root', async ({ page }) => {
  const signals = await collectPageSignals(page)
  await page.goto(url(), { waitUntil: 'domcontentloaded' })
  await waitForStableLoad(page)

  const bodyText = await page.locator('body').innerText()
  const title = await page.title()

  expect(bodyText.trim().length).toBeGreaterThan(0)
  expect(title.trim().length).toBeGreaterThan(0)
  await expect(page.locator('body')).toContainText(/owncloud|log in|login|username|password|files/i)
  expect(signals.pageErrors).toEqual([])
  expect(signals.criticalResponses).toEqual([])
  if (!allowRootRewrite) {
    expect(signals.suspiciousRequests).toEqual([])
  }
})

test('Deep link keeps subpath asset requests intact', async ({ page }) => {
  const signals = await collectPageSignals(page)
  await page.goto(url('/files/spaces/personal'), { waitUntil: 'domcontentloaded' })
  await waitForStableLoad(page)

  const bodyText = await page.locator('body').innerText()
  expect(bodyText.trim().length).toBeGreaterThan(0)
  expect(signals.pageErrors).toEqual([])
  expect(signals.criticalResponses).toEqual([])
  if (!allowRootRewrite) {
    expect(signals.suspiciousRequests).toEqual([])
  }
})

test('Root paths are not externally served', async ({ request }) => {
  const rootPaths = [
    '/',
    '/config.json',
    '/oidc-callback.html',
    '/oidc-silent-redirect.html',
    '/manifest.json',
    '/favicon.ico',
    '/robots.txt',
    '/js/',
    '/themes/owncloud/theme.json',
    '/graph/v1.0/me',
    '/api/v0/settings/values',
    '/dav/spaces',
    '/data',
    '/remote.php/dav',
    '/ocs/v2.php/cloud/capabilities',
    '/thumbnails',
    '/.well-known/openid-configuration',
    '/signin',
    '/konnect'
  ]

  for (const pathname of rootPaths) {
    const response = await request.get(originUrl(pathname), {
      failOnStatusCode: false,
      maxRedirects: 0
    })
    expect(response.status(), `${pathname} should not be served from origin root`).toBeGreaterThanOrEqual(400)
  }
})

test('Optional login works when credentials are provided', async ({ page }) => {
  test.skip(!loginUser || !loginPassword, 'Set E2E_USERNAME and E2E_PASSWORD to enable login coverage.')

  const signals = await collectPageSignals(page)
  await login(page)

  await expect(page.locator('body')).toContainText(/files|spaces|personal|new/i)
  expect(currentPathIsInsideSubpath(page.url())).toBeTruthy()
  await expect(
    page.locator('input[autocomplete="username"], input[name="username"], input[type="email"], input[type="text"]')
  ).toHaveCount(0)

  await page.goto(url('/files/spaces/personal'), { waitUntil: 'domcontentloaded' })
  await waitForStableLoad(page)
  await expect(page.locator('body')).toContainText(/files|spaces|personal|new/i)
  expect(currentPathIsInsideSubpath(page.url())).toBeTruthy()

  await page.reload({ waitUntil: 'domcontentloaded' })
  await waitForStableLoad(page)
  await expect(page.locator('body')).toContainText(/files|spaces|personal|new/i)
  expect(currentPathIsInsideSubpath(page.url())).toBeTruthy()
  expect(signals.pageErrors).toEqual([])
  expect(signals.criticalResponses).toEqual([])
  if (!allowRootRewrite) {
    expect(signals.suspiciousRequests).toEqual([])
  }
})

test('Provisioned users, groups, spaces, markdown, and zip sharing work from a subpath', async ({ browser }) => {
  test.skip(!loginUser || !loginPassword, 'Set E2E_USERNAME and E2E_PASSWORD to enable provisioned workflow coverage.')
  test.setTimeout(600_000)

  fs.mkdirSync(resultsDir, { recursive: true })
  await ensureVideoFixture()
  const originalVideo = fs.readFileSync(videoFixturePath)
  const samplePdf = fs.readFileSync(samplePdfFixturePath)
  const markdown = fs.readFileSync(markdownFixturePath, 'utf8')
  const randomLine = `E2E random line ${crypto.randomUUID()}`
  const updatedMarkdown = `${markdown}\n\n${randomLine}\n`
  const sharePassword = `E2e-${Date.now()}!`
  let adminApi: APIRequestContext | undefined
  let aliceApi: APIRequestContext | undefined
  let bobApi: APIRequestContext | undefined
  let charlieApi: APIRequestContext | undefined
  let adminRecording: Awaited<ReturnType<typeof recordedPage>> | undefined
  let aliceRecording: Awaited<ReturnType<typeof recordedPage>> | undefined
  let bobRecording: Awaited<ReturnType<typeof recordedPage>> | undefined
  let charlieRecording: Awaited<ReturnType<typeof recordedPage>> | undefined

  try {
    adminRecording = await recordedPage(browser, 'provisioned-workflow-admin')
    await login(adminRecording.page)
    adminApi = await authenticatedApi(adminRecording.page)

    const alice = await ensureUser(adminApi, 'alice')
    const bob = await ensureUser(adminApi, 'bob')
    const charlie = await ensureUser(adminApi, 'charlie')
    const david = await ensureUser(adminApi, 'david')

    const salesGroup = await ensureGroup(adminApi, 'sales')
    const developGroup = await ensureGroup(adminApi, 'develop')
    const marketingGroup = await ensureGroup(adminApi, 'marketing')

    await addUserToGroup(adminApi, salesGroup.id, alice.id)
    await addUserToGroup(adminApi, developGroup.id, bob.id)
    await addUserToGroup(adminApi, developGroup.id, charlie.id)
    await addUserToGroup(adminApi, marketingGroup.id, alice.id)
    await addUserToGroup(adminApi, marketingGroup.id, bob.id)

    const salesSpace = await ensureProjectSpace(adminApi, 'sales')
    const developSpace = await ensureProjectSpace(adminApi, 'develop')
    const marketngSpace = await ensureProjectSpace(adminApi, 'marketng')

    await shareSpaceMembership(adminApi, salesSpace.id, salesGroup.displayName, 'group', 'manager')
    await shareSpaceMembership(adminApi, salesSpace.id, marketingGroup.displayName, 'group', 'viewer')
    await shareSpaceMembership(adminApi, salesSpace.id, 'david', 'user', 'editor')
    await shareSpaceMembership(adminApi, developSpace.id, developGroup.displayName, 'group', 'manager')
    await shareSpaceMembership(adminApi, developSpace.id, salesGroup.displayName, 'group', 'viewer')
    await shareSpaceMembership(adminApi, marketngSpace.id, marketingGroup.displayName, 'group', 'manager')
    await shareSpaceMembership(adminApi, marketngSpace.id, 'david', 'user', 'editor')

    await deleteSpaceFile(adminApi, developSpace.id, videoFileName)
    await uploadFileViaTus(adminApi, developSpace.id, [], videoFileName, 'video/webm', originalVideo)
    await logoutToLoginPage(adminRecording.page)
    await adminApi.dispose()
    adminApi = undefined
    await closeRecordedPage(adminRecording)
    adminRecording = undefined

    aliceRecording = await recordedPage(browser, 'provisioned-workflow-alice')
    await login(aliceRecording.page, 'alice', scenarioPassword)
    aliceApi = await authenticatedApi(aliceRecording.page)
    const aliceSalesDriveId = await projectDriveIdForUser(aliceApi, 'sales')
    await openProjectSpaceFromUi(aliceRecording.page, 'sales')

    await deleteSpaceFile(aliceApi, aliceSalesDriveId, markdownFileName)
    await putSpaceFile(aliceApi, aliceSalesDriveId, markdownFileName, 'text/markdown; charset=utf-8', markdown)
    await aliceRecording.page.reload({ waitUntil: 'domcontentloaded' })
    await waitForStableLoad(aliceRecording.page)
    await expect(aliceRecording.page.getByText(markdownFileName, { exact: true }).first()).toBeVisible({ timeout: 30_000 })

    await aliceRecording.page.waitForTimeout(1_000)
    await putSpaceFile(aliceApi, aliceSalesDriveId, markdownFileName, 'text/markdown; charset=utf-8', updatedMarkdown)
    const markdownFileId = await fileIdFromPropfind(aliceApi, aliceSalesDriveId, markdownFileName)
    const versions = await fileVersionKeys(aliceApi, markdownFileId)
    expect(versions.length).toBeGreaterThanOrEqual(1)
    const versionPreview = await aliceApi.get(url(`/remote.php/dav/meta/${encodePath(markdownFileId)}/v/${encodePath(versions[0])}`))
    expect(versionPreview.status()).toBe(200)
    expect(await versionPreview.text()).toContain('CommonMark Smoke Test')
    await expect.poll(async () => (await downloadSpaceFile(aliceApi!, aliceSalesDriveId, markdownFileName)).toString('utf8')).toContain(randomLine)
    await aliceRecording.page.reload({ waitUntil: 'domcontentloaded' })
    await waitForStableLoad(aliceRecording.page)
    await previewMarkdownFromUi(aliceRecording.page, markdownFileName, randomLine)
    await logoutToLoginPage(aliceRecording.page)
    await aliceApi.dispose()
    aliceApi = undefined
    await closeRecordedPage(aliceRecording)
    aliceRecording = undefined

    bobRecording = await recordedPage(browser, 'provisioned-workflow-bob')
    await login(bobRecording.page, 'bob', scenarioPassword)
    bobApi = await authenticatedApi(bobRecording.page)
    const bobDevelopDriveId = await projectDriveIdForUser(bobApi, 'develop')
    await openProjectSpaceFromUi(bobRecording.page, 'develop')

    const downloadedVideo = await downloadSpaceFile(bobApi, bobDevelopDriveId, videoFileName)
    expect(sha256(downloadedVideo)).toBe(sha256(originalVideo))
    const zipContents = createStoredZip(videoFileName, downloadedVideo)
    await deleteSpaceFile(bobApi, bobDevelopDriveId, zipFileName)
    await uploadFileViaTus(bobApi, bobDevelopDriveId, [], zipFileName, 'application/zip', zipContents)
    const downloadedZip = await downloadSpaceFile(bobApi, bobDevelopDriveId, zipFileName)
    expect(sha256(downloadedZip)).toBe(sha256(zipContents))

    const zipShareToken = await createPublicShareForSpace(bobApi, bobDevelopDriveId, zipFileName, sharePassword)
    const publicZip = await downloadPublicShareFile(zipShareToken, sharePassword, zipFileName)
    expect(sha256(publicZip)).toBe(sha256(zipContents))

    await deleteSpaceFile(bobApi, bobDevelopDriveId, samplePdfFileName)
    await uploadFileViaTus(bobApi, bobDevelopDriveId, [], samplePdfFileName, 'application/pdf', samplePdf)
    const downloadedPdfByBob = await downloadSpaceFile(bobApi, bobDevelopDriveId, samplePdfFileName)
    expect(sha256(downloadedPdfByBob)).toBe(sha256(samplePdf))
    await logoutToLoginPage(bobRecording.page)
    await bobApi.dispose()
    bobApi = undefined
    await closeRecordedPage(bobRecording)
    bobRecording = undefined

    charlieRecording = await recordedPage(browser, 'provisioned-workflow-charlie')
    await login(charlieRecording.page, 'charlie', scenarioPassword)
    charlieApi = await authenticatedApi(charlieRecording.page)
    const charlieDevelopDriveId = await projectDriveIdForUser(charlieApi, 'develop')
    await openProjectSpaceFromUi(charlieRecording.page, 'develop')
    await previewPdfFromUi(charlieRecording.page, samplePdfFileName)
    const downloadedPdfByCharlie = await downloadSpaceFile(charlieApi, charlieDevelopDriveId, samplePdfFileName)
    expect(sha256(downloadedPdfByCharlie)).toBe(sha256(samplePdf))
    await logoutToLoginPage(charlieRecording.page)
    await charlieApi.dispose()
    charlieApi = undefined
    await closeRecordedPage(charlieRecording)
    charlieRecording = undefined
  } finally {
    await adminApi?.dispose()
    await aliceApi?.dispose()
    await bobApi?.dispose()
    await charlieApi?.dispose()
    if (adminRecording) {
      await closeRecordedPage(adminRecording)
    }
    if (aliceRecording) {
      await closeRecordedPage(aliceRecording)
    }
    if (bobRecording) {
      await closeRecordedPage(bobRecording)
    }
    if (charlieRecording) {
      await closeRecordedPage(charlieRecording)
    }
  }
})

test('Logged-in file workflow works from a subpath', async ({ browser }) => {
  test.skip(!loginUser || !loginPassword, 'Set E2E_USERNAME and E2E_PASSWORD to enable login workflow coverage.')
  test.setTimeout(300_000)

  fs.mkdirSync(resultsDir, { recursive: true })
  await ensureVideoFixture()
  const original = fs.readFileSync(videoFixturePath)
  const samplePdf = fs.readFileSync(samplePdfFixturePath)
  const folderName = `e2e-subpath-${Date.now()}`
  const uiUploadPdfName = `ui-upload-${Date.now()}.pdf`
  const sharePassword = `E2e-${Date.now()}!`
  const context = await browser.newContext({
    acceptDownloads: true,
    ignoreHTTPSErrors: true,
    recordVideo: {
      dir: resultsDir,
      size: { width: 1280, height: 720 }
    }
  })
  const page = await context.newPage()
  const signals = await collectPageSignals(page)
  let api: APIRequestContext | undefined

  try {
    await login(page)
    await createFolderFromUi(page, folderName)
    await enterFolderFromUi(page, folderName)
    api = await authenticatedApi(page)
    const driveId = await personalDriveId(api)
    await uploadFileFromUi(page, uiUploadPdfName, 'application/pdf', samplePdf, {
      api,
      driveId,
      pathSegments: [folderName, uiUploadPdfName]
    })

    await uploadVideoViaTus(api, driveId, folderName, original)
    await page.reload({ waitUntil: 'domcontentloaded' })
    await waitForStableLoad(page)
    await expect(page.getByText(videoFileName, { exact: true }).first()).toBeVisible({ timeout: 30_000 })

    await playPreviewForTenSeconds(page, folderName)

    const authenticatedDownload = await downloadAuthenticatedFile(api, driveId, folderName)
    expect(sha256(authenticatedDownload)).toBe(sha256(original))

    const shareToken = await createPublicShare(api, folderName, sharePassword)
    const publicDownload = await downloadPublicShare(shareToken, sharePassword)
    expect(sha256(publicDownload)).toBe(sha256(original))

    await logoutToLoginPage(page)
    expect(signals.pageErrors).toEqual([])
    expect(signals.criticalResponses).toEqual([])
    if (!allowRootRewrite) {
      expect(signals.suspiciousRequests).toEqual([])
    }
  } finally {
    await api?.dispose()
    const video = page.video()
    await context.close()
    if (video) {
      const recordedPath = await video.path()
      const finalVideoPath = path.join(resultsDir, 'ocis-subpath-login-workflow.webm')
      fs.rmSync(finalVideoPath, { force: true })
      fs.renameSync(recordedPath, finalVideoPath)
    }
  }
})
