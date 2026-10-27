import {
  type QueryClient,
  queryOptions,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query"
import {
  type AnyRouter,
  type ParsedLocation,
  redirect as routerRedirect,
  useRouter,
} from "@tanstack/react-router"
import { useCallback, useSyncExternalStore } from "react"
import { toast } from "sonner"

import { type Identity, IdentityService } from "@/client"
import { client } from "@/client/client.gen"
import { parseApiError } from "@/lib/api-error"
import { safeRedirect } from "./redirect"

// 登入狀態只存在瀏覽器：access token（無狀態 JWT，登出只在前端清除）與上次使用的身分。
export const ACCESS_TOKEN_STORAGE_KEY = "flow-access-token"
export const LAST_IDENTITY_STORAGE_KEY = "flow-last-identity"

export const SESSION_EXPIRED_TEXT = "登入已過期，請重新登入。"
export const INVALID_CREDENTIALS = "INVALID_CREDENTIALS"

/** 目前帳號相關 query 的共同前綴。 */
export const ME_QUERY_KEY = ["identity", "me"] as const

// ---------------------------------------------------------------- localStorage

// 無痕視窗或封鎖網站資料時 localStorage 可能丟例外：寫不進去的值改存在記憶體，
// 只在這個分頁有效（重新整理後要重新登入）。記憶體有值時優先於 localStorage。
const memoryFallback = new Map<string, string | null>()

function readStorage(key: string): string | null {
  if (memoryFallback.has(key)) return memoryFallback.get(key) ?? null
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

function writeStorage(key: string, value: string | null): void {
  try {
    if (value === null) window.localStorage.removeItem(key)
    else window.localStorage.setItem(key, value)
    memoryFallback.delete(key)
  } catch {
    memoryFallback.set(key, value)
  }
  notify()
}

const listeners = new Set<() => void>()

function notify(): void {
  for (const listener of listeners) listener()
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  // 其他分頁登入或登出時同步
  const onStorage = (event: StorageEvent) => {
    if (
      event.key === null ||
      event.key === ACCESS_TOKEN_STORAGE_KEY ||
      event.key === LAST_IDENTITY_STORAGE_KEY
    ) {
      listener()
    }
  }
  window.addEventListener("storage", onStorage)
  return () => {
    listeners.delete(listener)
    window.removeEventListener("storage", onStorage)
  }
}

export function getAccessToken(): string | null {
  return readStorage(ACCESS_TOKEN_STORAGE_KEY) || null
}

export function setAccessToken(token: string): void {
  writeStorage(ACCESS_TOKEN_STORAGE_KEY, token)
}

export function clearAccessToken(): void {
  writeStorage(ACCESS_TOKEN_STORAGE_KEY, null)
}

export function getLastIdentity(): string | null {
  return readStorage(LAST_IDENTITY_STORAGE_KEY)
}

export function setLastIdentity(key: string): void {
  writeStorage(LAST_IDENTITY_STORAGE_KEY, key)
}

/** 目前的 access token；登入、登出（包含其他分頁）時重新渲染。 */
export function useAccessToken(): string | null {
  return useSyncExternalStore(subscribe, getAccessToken, () => null)
}

export function useIsSignedIn(): boolean {
  return useAccessToken() !== null
}

function useLastIdentity(): string | null {
  return useSyncExternalStore(subscribe, getLastIdentity, () => null)
}

// ---------------------------------------------------------------- 目前帳號與身分清單

export const currentAccountQueryOptions = () =>
  queryOptions({
    queryKey: [...ME_QUERY_KEY, "account"],
    queryFn: async () => (await IdentityService.readCurrentAccount()).data,
  })

export const identitiesQueryOptions = () =>
  queryOptions({
    queryKey: [...ME_QUERY_KEY, "identities"],
    queryFn: async () => (await IdentityService.listCurrentIdentities()).data,
  })

/** 目前登入的帳號；未登入時不送請求。 */
export function useCurrentAccount() {
  const signedIn = useIsSignedIn()
  return useQuery({ ...currentAccountQueryOptions(), enabled: signedIn })
}

/** 目前帳號擁有的身分（只由後端產生）；未登入時不送請求。 */
export function useIdentities() {
  const signedIn = useIsSignedIn()
  return useQuery({ ...identitiesQueryOptions(), enabled: signedIn })
}

/** 目前身分：上次使用的身分；不在清單內（或還沒選過）時是清單第一項「瀏覽賽事」。 */
export function pickCurrentIdentity(
  identities: Identity[],
  lastIdentity: string | null,
): Identity | undefined {
  return (
    identities.find((identity) => identity.key === lastIdentity) ??
    identities[0]
  )
}

export function useCurrentIdentity(): Identity | undefined {
  const identities = useIdentities()
  const lastIdentity = useLastIdentity()
  return pickCurrentIdentity(identities.data ?? [], lastIdentity)
}

/**
 * 登入後要去的頁面：有合格的 redirect 時回原頁；只有 1 種身分到 S1；
 * 2 種以上時，記住的上次身分還在清單內就到它的首頁，否則（第一次）到 S11。
 */
export function postLoginDestination({
  redirect,
  identities,
  lastIdentity,
}: {
  redirect?: string
  identities: Identity[]
  lastIdentity: string | null
}): string {
  const target = safeRedirect(redirect)
  if (target) return target
  if (identities.length <= 1) return "/"
  const last = identities.find((identity) => identity.key === lastIdentity)
  return last ? last.home_path : "/me"
}

/** 切換身分：記住這個身分並前往它的首頁；只改變導覽與首頁，不改變權限。 */
export function useSwitchIdentity(): (identity: Identity) => void {
  const router = useRouter()
  return useCallback(
    (identity: Identity) => {
      setLastIdentity(identity.key)
      router.history.push(identity.home_path)
    },
    [router],
  )
}

/**
 * 換帳號（登入、登出、登入過期、其他分頁換了 token）時清掉所有 query 的快取：
 * 任何 query 都可能帶著前一個帳號的資料，不只 `ME_QUERY_KEY` 底下的。
 */
function clearCachedQueries(queryClient: QueryClient): void {
  queryClient.removeQueries()
}

/** 登入成功後：存 token、清掉舊帳號的快取，並關掉還開著的「登入已過期」。 */
export function signIn(queryClient: QueryClient, accessToken: string): void {
  clearCachedQueries(queryClient)
  setAccessToken(accessToken)
  toast.dismiss(SESSION_EXPIRED_TEXT)
}

function signOut(queryClient: QueryClient): void {
  clearAccessToken()
  clearCachedQueries(queryClient)
}

/** 登出：清除登入狀態並回到 S1，不需確認；上次使用的身分保留給下次登入。 */
export function useLogout(): () => void {
  const queryClient = useQueryClient()
  const router = useRouter()
  return useCallback(() => {
    signOut(queryClient)
    router.navigate({ to: "/" })
  }, [queryClient, router])
}

/**
 * 需要登入的頁面（S10、S11）的 `beforeLoad`：未登入時導向 S6，帶 `redirect` 回原頁
 * （包含查詢參數）。
 */
export function requireSignedIn({
  location,
}: {
  location: ParsedLocation
}): void {
  if (getAccessToken() === null) {
    throw routerRedirect({
      to: "/login",
      search: { redirect: safeRedirect(location.href) },
    })
  }
}

// ---------------------------------------------------------------- 401 處理

/**
 * 產生的 client（axios）的回應攔截器：API 回 401 時清除 token，導向 S6 並帶
 * `redirect` 回原頁。原本是登入狀態時另外顯示「登入已過期，請重新登入。」；
 * 正在填寫的表單內容不保留。登入 API 本身的 401（`INVALID_CREDENTIALS`）不處理。
 */
export function createUnauthorizedHandler(
  router: AnyRouter,
  queryClient: QueryClient,
): (error: unknown) => Promise<never> {
  return (error: unknown) => {
    const apiError = parseApiError(error)
    if (
      apiError.kind === "unauthorized" &&
      apiError.code !== INVALID_CREDENTIALS
    ) {
      if (getAccessToken() !== null) {
        signOut(queryClient)
        // 以訊息當 id：同時有好幾個請求回 401 時只顯示一則
        toast.error(SESSION_EXPIRED_TEXT, {
          id: SESSION_EXPIRED_TEXT,
          duration: Number.POSITIVE_INFINITY,
          closeButton: true,
        })
      }
      const { pathname, href } = router.state.location
      if (pathname !== "/login") {
        router.navigate({
          to: "/login",
          search: { redirect: safeRedirect(href) },
        })
      }
    }
    return Promise.reject(error)
  }
}

/**
 * 設定產生的 API client：需要登入的 API（OpenAPI 標了 bearer）自動帶
 * `Authorization: Bearer <token>`，任何 API 回 401 時交給 createUnauthorizedHandler。
 * 其他分頁登入、登出或換了帳號時清掉這個分頁的快取。
 * 回傳移除 401 攔截器與 storage 監聽的函式（測試用）。
 */
export function configureApiClient(
  router: AnyRouter,
  queryClient: QueryClient,
  baseURL = "",
): () => void {
  client.setConfig({
    baseURL,
    auth: () => getAccessToken() ?? undefined,
  })
  const interceptor = client.instance.interceptors.response.use(
    undefined,
    createUnauthorizedHandler(router, queryClient),
  )
  const onStorage = (event: StorageEvent) => {
    if (event.key === null || event.key === ACCESS_TOKEN_STORAGE_KEY) {
      clearCachedQueries(queryClient)
    }
  }
  window.addEventListener("storage", onStorage)
  return () => {
    client.instance.interceptors.response.eject(interceptor)
    window.removeEventListener("storage", onStorage)
  }
}
