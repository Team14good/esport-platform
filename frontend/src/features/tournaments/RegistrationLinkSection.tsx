import { useQuery } from "@tanstack/react-query"

import type { TournamentRead } from "@/client"
import { ConfirmDialog } from "@/components/common/ConfirmDialog"
import { Button } from "@/components/ui/button"
import { InviteLinkField } from "@/features/registration/InviteLinkField"
import { notifySuccess } from "@/lib/feedback"
import {
  REGISTRATION_LINK_DESCRIPTION,
  REGISTRATION_LINK_LABEL,
  REGISTRATION_LINK_RESET_TEXT,
  RESET_REGISTRATION_LINK_CONFIRM_TEXT,
  RESET_REGISTRATION_LINK_TEXT,
  registrationLinkQueryOptions,
  registrationLinkUrl,
  useResetRegistrationLink,
} from "./registration-link"

function RegistrationLinkContent({ tournamentId }: { tournamentId: string }) {
  const link = useQuery(registrationLinkQueryOptions(tournamentId))
  const reset = useResetRegistrationLink(tournamentId)
  if (!link.data) return null

  return (
    <section
      aria-label={REGISTRATION_LINK_LABEL}
      className="mt-6 flex flex-col gap-3 rounded-lg border bg-card p-4"
    >
      <InviteLinkField
        label={REGISTRATION_LINK_LABEL}
        url={registrationLinkUrl(tournamentId, link.data.invite_token)}
        note={REGISTRATION_LINK_DESCRIPTION}
      />
      <div className="flex">
        <ConfirmDialog
          title={RESET_REGISTRATION_LINK_TEXT}
          description={RESET_REGISTRATION_LINK_CONFIRM_TEXT}
          confirmLabel={RESET_REGISTRATION_LINK_TEXT}
          destructive
          // 失敗時 reject：對話框留著並顯示伺服器的訊息
          onConfirm={async () => {
            await reset.mutateAsync()
            notifySuccess(REGISTRATION_LINK_RESET_TEXT)
          }}
          trigger={
            <Button variant="outline" className="h-10 w-full sm:w-auto">
              {RESET_REGISTRATION_LINK_TEXT}
            </Button>
          }
        />
      </div>
    </section>
  )
}

/**
 * S27 的賽事報名連結（Story 3.10）：自訂賽事才顯示連結（可複製）、說明與「重設報名連結」。
 * 校園賽，以及已取消、已結束的賽事不顯示，也不查詢。
 */
export function RegistrationLinkSection({
  tournament,
}: {
  tournament: TournamentRead
}) {
  if (tournament.mode !== "custom") return null
  if (tournament.status === "cancelled" || tournament.status === "finished") {
    return null
  }
  return <RegistrationLinkContent tournamentId={tournament.id} />
}
