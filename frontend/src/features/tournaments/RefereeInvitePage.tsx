import { useQuery } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { CircleAlertIcon, CircleCheckIcon } from "lucide-react"

import type { PublicRefereeInvitation } from "@/client"
import { HrefLink } from "@/components/common/HrefLink"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { LoadingButton } from "@/components/ui/loading-button"
import { Skeleton } from "@/components/ui/skeleton"
import { formatMatchDateTime } from "@/features/competition/match-time"
import { useIsSignedIn } from "@/features/identity/auth"
import { VerificationRequired } from "@/features/identity/VerificationRequired"
import { getErrorMessage, parseApiError } from "@/lib/api-error"
import {
  businessErrorCode,
  NOT_ACCEPTING_TEXT,
  ORGANIZER_CANNOT_BE_REFEREE,
  REFEREE_INVITATION_EXPIRED,
  REFEREE_INVITATION_NOT_FOUND,
  refereeInvitePath,
  refereeInvitePreviewQueryOptions,
  TOURNAMENT_NOT_ACCEPTING_REFEREES,
  useAcceptRefereeInvitation,
} from "./referee-queries"

export const INVITE_EXPIRED_TEXT = "此裁判邀請已過期，請向主辦方索取新連結。"
export const INVITE_NOT_FOUND_TEXT = "找不到這個裁判邀請。"
export const ORGANIZER_CANNOT_BE_REFEREE_TEXT = "主辦方不能擔任自己賽事的裁判。"
/** D 的 S13 我執法的場次（PR #51）；合併前路由還不存在，所以不用型別化的 Link。 */
export const MY_REFEREE_MATCHES_PATH = "/me/referee"

/** 邀請不存在：說明＋回首頁。 */
function NotFound() {
  return (
    <div className="flex flex-col items-start gap-3">
      <p className="text-body">{INVITE_NOT_FOUND_TEXT}</p>
      <Button asChild variant="outline">
        <Link to="/">回到首頁</Link>
      </Button>
    </div>
  )
}

/** 不能接受（過期、賽事已結束或已取消、主辦方本人）：說明原因，不提供「接受邀請」。 */
function Rejected({ reason }: { reason: string }) {
  return (
    <Alert variant="destructive" className="rounded-md">
      <CircleAlertIcon />
      <AlertDescription className="text-destructive">{reason}</AlertDescription>
    </Alert>
  )
}

/** 接受失敗的業務錯誤代碼對應到的說明；null 表示不是已知的拒絕原因。 */
function rejectedReason(code: string | null): string | null {
  switch (code) {
    case REFEREE_INVITATION_EXPIRED:
      return INVITE_EXPIRED_TEXT
    case TOURNAMENT_NOT_ACCEPTING_REFEREES:
      return NOT_ACCEPTING_TEXT
    case ORGANIZER_CANNOT_BE_REFEREE:
      return ORGANIZER_CANNOT_BE_REFEREE_TEXT
    default:
      return null
  }
}

function AcceptAction({
  token,
  invite,
}: {
  token: string
  invite: PublicRefereeInvitation
}) {
  const signedIn = useIsSignedIn()
  const accept = useAcceptRefereeInvitation(token)

  if (accept.isSuccess) {
    return (
      <div className="flex flex-col items-start gap-3">
        <p
          role="status"
          className="flex items-start gap-2 break-words text-body"
        >
          <CircleCheckIcon
            aria-hidden="true"
            className="mt-0.5 size-4 shrink-0 text-primary"
          />
          <span className="min-w-0">
            你已成為「{invite.tournament_name}」的裁判
          </span>
        </p>
        <Button asChild className="w-full sm:w-auto">
          <HrefLink href={MY_REFEREE_MATCHES_PATH}>查看我執法的場次</HrefLink>
        </Button>
      </div>
    )
  }

  // 與後端接受時的檢查順序一致：先看到期，再看賽事狀態
  if (invite.expired) return <Rejected reason={INVITE_EXPIRED_TEXT} />
  if (!invite.accepting) return <Rejected reason={NOT_ACCEPTING_TEXT} />

  if (!signedIn) {
    const redirect = refereeInvitePath(token)
    return (
      <div className="flex flex-col gap-3">
        <p className="text-body text-muted-foreground">
          註冊或登入後即可接受這個裁判邀請；新註冊的帳號完成 Email
          驗證後會回到這個頁面。
        </p>
        <div className="flex flex-col gap-2 sm:flex-row">
          <Button asChild>
            <Link to="/signup" search={{ redirect }}>
              註冊帳號
            </Link>
          </Button>
          <Button asChild variant="outline">
            <Link to="/login" search={{ redirect }}>
              登入
            </Link>
          </Button>
        </div>
      </div>
    )
  }

  if (accept.isError) {
    const code = businessErrorCode(accept.error)
    if (code === REFEREE_INVITATION_NOT_FOUND) return <NotFound />
    const reason = rejectedReason(code)
    if (reason !== null) return <Rejected reason={reason} />
  }

  return (
    <div className="flex flex-col gap-3">
      {accept.isError && (
        <Rejected reason={getErrorMessage(parseApiError(accept.error))} />
      )}
      <VerificationRequired action="接受裁判邀請">
        <LoadingButton
          type="button"
          loading={accept.isPending}
          onClick={() => accept.mutate()}
          className="w-full sm:w-auto sm:self-start"
        >
          接受邀請
        </LoadingButton>
      </VerificationRequired>
    </div>
  )
}

/** S23 接受裁判邀請：不需登入即可預覽賽事名稱與到期時間，依登入與驗證狀態提供「接受邀請」。 */
export function RefereeInvitePage({ token }: { token: string }) {
  const invite = useQuery(refereeInvitePreviewQueryOptions(token))

  return (
    <section className="mx-auto flex w-full max-w-md flex-col gap-6 py-8 sm:py-12">
      <h1 className="text-heading-lg">裁判邀請</h1>
      {/* 已有資料時一律顯示卡片：背景重抓失敗不能蓋掉內容（例如接受成功的狀態） */}
      {invite.data ? (
        <>
          <Card className="gap-2 px-6">
            <p className="text-caption text-muted-foreground">
              邀請你擔任這場賽事的裁判
            </p>
            <p className="break-words font-semibold text-heading-md">
              {invite.data.tournament_name}
            </p>
            <p className="text-caption text-muted-foreground">
              {invite.data.expired
                ? "連結已過期"
                : `${formatMatchDateTime(invite.data.expires_at)} 到期`}
            </p>
          </Card>
          <AcceptAction token={token} invite={invite.data} />
        </>
      ) : invite.isPending ? (
        <div role="status" aria-busy="true" className="flex flex-col gap-3">
          <Skeleton className="h-24 w-full rounded-lg" />
          <span className="sr-only">載入中</span>
        </div>
      ) : businessErrorCode(invite.error) === REFEREE_INVITATION_NOT_FOUND ? (
        <NotFound />
      ) : (
        <div className="flex flex-col items-start gap-3">
          <p className="text-body text-destructive">
            {getErrorMessage(parseApiError(invite.error))}
          </p>
          <Button variant="outline" onClick={() => invite.refetch()}>
            重新載入
          </Button>
        </div>
      )}
    </section>
  )
}
