// 直接存取 compose 的 PostgreSQL（e2e 容器內建 psql）。
// 申訴期至少 30 分鐘、每輪間隔更長，演練等不了真實時間：這裡只把期限改到需要的時間，之後仍由真的 worker 處理。
// 期中版也由這裡直接查 AuditLog（2.8 查閱頁面擱置）。
import { execFile } from "node:child_process"
import { promisify } from "node:util"

const run = promisify(execFile)

const UUID_PATTERN = /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i

function databaseUrl(): string {
  const url = process.env.E2E_DATABASE_URL
  if (!url) {
    throw new Error(
      "缺少 E2E_DATABASE_URL；請用 docker compose --profile e2e run --rm e2e 執行",
    )
  }
  return url
}

async function sql(statement: string): Promise<string> {
  const { stdout } = await run(
    "psql",
    [databaseUrl(), "-AtqX", "-v", "ON_ERROR_STOP=1", "-c", statement],
    { maxBuffer: 32 * 1024 * 1024 },
  )
  return stdout.trim()
}

function uuid(value: string): string {
  if (!UUID_PATTERN.test(value)) throw new Error(`不是 UUID：${value}`)
  return `'${value}'`
}

function uuidArray(values: string[]): string {
  return `ARRAY[${values.map(uuid).join(",")}]::uuid[]`
}

function text(value: string): string {
  return `'${value.split("'").join("''")}'`
}

/** 大量準備的帳號不逐一收信，直接標成已驗證（角色帳號仍從 Mailpit 取信）。 */
export async function markEmailsVerified(emails: string[]) {
  await sql(
    `UPDATE account SET email_verified = true WHERE email IN (${emails.map(text).join(",")})`,
  )
}

/**
 * 讓優先期現在結束，由 worker 分配正取與候補。
 * 要用 `now()`：結算只收 `submitted_at <= priority_end` 的報名，往前推會漏掉剛送出的隊伍。
 */
export async function endPriorityWindow(tournamentId: string) {
  await sql(
    `UPDATE tournament SET priority_end = now() WHERE id = ${uuid(tournamentId)}`,
  )
}

/** 把場次改到 5 分鐘後開始，進入報到開放時間（開始前 30 分鐘內）。 */
export async function openCheckIn(matchIds: string[]) {
  await sql(
    `UPDATE "match" SET scheduled_at = now() + interval '5 minutes' WHERE id = ANY(${uuidArray(matchIds)})`,
  )
}

/** 讓場次的申訴期已過，由 worker 自動確認並晉級。 */
export async function expireAppealWindows(matchIds: string[]) {
  await sql(
    `UPDATE "match" SET appeal_deadline = now() - interval '1 second' WHERE id = ANY(${uuidArray(matchIds)}) AND status = 'appeal_window'`,
  )
}

export type AuditRow = {
  action: string
  actor_id: string | null
  before: Record<string, unknown> | null
  after: Record<string, unknown> | null
}

/** 這場賽事某些操作的 AuditLog，依寫入順序排列。 */
export async function auditRows(
  tournamentId: string,
  actions: string[],
): Promise<AuditRow[]> {
  const output = await sql(
    `SELECT coalesce(json_agg(row_to_json(t)), '[]') FROM (
       SELECT action, actor_id, before, after FROM audit_log
       WHERE tournament_id = ${uuid(tournamentId)}
         AND action IN (${actions.map(text).join(",")})
       ORDER BY seq
     ) t`,
  )
  return JSON.parse(output) as AuditRow[]
}
