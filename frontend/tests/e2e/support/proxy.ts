// Playwright 的 globalSetup：
// 1. 有 E2E_PROXY（例如 "5173=frontend:5173,8000=backend:8000"）時，在容器內的 localhost 開 TCP 轉發，
//    讓瀏覽器照常使用 localhost:5173／localhost:8000，前端的 API 網址與後端的 CORS 都不必改。
// 2. 等前端與 API 回應後才開始測試（compose 只保證容器已啟動，Vite 可能還在準備）。
import net from "node:net"
import type { FullConfig } from "@playwright/test"

import { API_URL } from "./env"

type ProxyRoute = { listenPort: number; targetHost: string; targetPort: number }

const READY_TIMEOUT_MS = 120_000

/** 解析 E2E_PROXY：以逗號分隔的「本機埠=主機:埠」。 */
export function parseProxyRoutes(spec: string): ProxyRoute[] {
  return spec
    .split(",")
    .map((entry) => entry.trim())
    .filter((entry) => entry !== "")
    .map((entry) => {
      const match = /^(\d+)=([^:]+):(\d+)$/.exec(entry)
      if (match === null) {
        throw new Error(
          `E2E_PROXY 格式錯誤：「${entry}」，應為「5173=frontend:5173」`,
        )
      }
      return {
        listenPort: Number(match[1]),
        targetHost: match[2],
        targetPort: Number(match[3]),
      }
    })
}

function listen(server: net.Server, port: number, host: string) {
  return new Promise<boolean>((resolve) => {
    server.once("error", () => resolve(false))
    server.listen(port, host, () => resolve(true))
  })
}

/** 開始轉發一個埠，回傳關閉函式。IPv4 一定要成功；容器沒有 IPv6 時略過 ::1。 */
async function startForwarder(route: ProxyRoute): Promise<() => Promise<void>> {
  const sockets = new Set<net.Socket>()
  const createServer = () =>
    net.createServer((client) => {
      const upstream = net.connect(route.targetPort, route.targetHost)
      sockets.add(client)
      sockets.add(upstream)
      const closeBoth = () => {
        client.destroy()
        upstream.destroy()
        sockets.delete(client)
        sockets.delete(upstream)
      }
      client.on("error", closeBoth)
      upstream.on("error", closeBoth)
      client.on("close", closeBoth)
      upstream.on("close", closeBoth)
      client.pipe(upstream)
      upstream.pipe(client)
    })

  const servers: net.Server[] = []
  const ipv4 = createServer()
  if (!(await listen(ipv4, route.listenPort, "127.0.0.1"))) {
    throw new Error(`無法在 127.0.0.1:${route.listenPort} 開啟轉發`)
  }
  servers.push(ipv4)
  const ipv6 = createServer()
  if (await listen(ipv6, route.listenPort, "::1")) servers.push(ipv6)

  return async () => {
    for (const socket of sockets) socket.destroy()
    await Promise.all(
      servers.map(
        (server) =>
          new Promise<void>((resolve) => server.close(() => resolve())),
      ),
    )
  }
}

async function waitForHttp(url: string): Promise<void> {
  const deadline = Date.now() + READY_TIMEOUT_MS
  let lastError = ""
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url)
      if (response.ok) return
      lastError = `HTTP ${response.status}`
    } catch (error) {
      lastError = String(error)
    }
    await new Promise((resolve) => setTimeout(resolve, 1000))
  }
  throw new Error(
    `${READY_TIMEOUT_MS / 1000} 秒內 ${url} 沒有回應（${lastError}）`,
  )
}

export default async function globalSetup(config: FullConfig) {
  const spec = process.env.E2E_PROXY
  const stops = spec
    ? await Promise.all(parseProxyRoutes(spec).map(startForwarder))
    : []
  const baseURL =
    config.projects[0]?.use.baseURL ??
    process.env.PLAYWRIGHT_BASE_URL ??
    "http://localhost:5173"
  await waitForHttp(baseURL)
  await waitForHttp(`${API_URL}/api/v1/utils/health-check`)
  return async () => {
    await Promise.all(stops.map((stop) => stop()))
  }
}
