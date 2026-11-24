import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { useState } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"

import { RegistrationService } from "@/client"
import { FormErrorAlert } from "@/components/common/FormErrorAlert"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import { LoadingButton } from "@/components/ui/loading-button"
import { codePointLength } from "@/features/identity/SignupForm"
import { VerificationRequired } from "@/features/identity/VerificationRequired"
import { type ApiError, applyFieldErrors } from "@/lib/api-error"
import { notifySuccess } from "@/lib/feedback"
import { myTeamsQueryOptions, teamQueryOptions } from "./queries"

export const TEAM_NAME_MAX_LENGTH = 30
export const TEAM_CREATED_TEXT = "隊伍已建立。"

// 與後端相同的規則（去頭尾空白後 1～30 字）；伺服器的 422／409 仍以伺服器為準
const teamSchema = z.object({
  name: z
    .string()
    .trim()
    .min(1, "請輸入隊名")
    .refine((value) => codePointLength(value) <= TEAM_NAME_MAX_LENGTH, {
      message: `隊名最多 ${TEAM_NAME_MAX_LENGTH} 個字`,
    }),
})

type TeamInput = z.input<typeof teamSchema>
type TeamValues = z.output<typeof teamSchema>

type CreateTeamProps = {
  tournamentId: string
  /** 自訂賽事的賽事報名連結 token（S2 網址的 `invite`，Story 3.10）；校園賽不帶 */
  inviteToken?: string
}

function CreateTeamForm({ tournamentId, inviteToken }: CreateTeamProps) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [formError, setFormError] = useState<ApiError | null>(null)
  const form = useForm<TeamInput, unknown, TeamValues>({
    resolver: zodResolver(teamSchema),
    defaultValues: { name: "" },
  })

  const create = useMutation({
    mutationFn: async (values: TeamValues) =>
      (
        await RegistrationService.createTeam({
          path: { tournament_id: tournamentId },
          body:
            inviteToken === undefined
              ? values
              : { ...values, invite_token: inviteToken },
        })
      ).data,
    onSuccess: (team) => {
      queryClient.setQueryData(teamQueryOptions(team.id).queryKey, team)
      queryClient.invalidateQueries({
        queryKey: myTeamsQueryOptions().queryKey,
      })
      notifySuccess(TEAM_CREATED_TEXT)
      navigate({ to: "/teams/$teamId", params: { teamId: team.id } })
    },
    onError: (error) => setFormError(applyFieldErrors(form, error)),
  })

  return (
    <Form {...form}>
      <form
        noValidate
        onSubmit={form.handleSubmit((values) => {
          setFormError(null)
          create.mutate(values)
        })}
        className="flex flex-col gap-5"
      >
        <FormErrorAlert error={formError} />
        <FormField
          control={form.control}
          name="name"
          render={({ field }) => (
            <FormItem>
              <FormLabel>隊名</FormLabel>
              <FormControl>
                <Input autoComplete="off" {...field} />
              </FormControl>
              <FormDescription>
                最多 {TEAM_NAME_MAX_LENGTH}{" "}
                個字；同一個賽事內不能與其他隊伍同名。
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
        <DialogFooter>
          <LoadingButton type="submit" loading={create.isPending}>
            建立隊伍
          </LoadingButton>
        </DialogFooter>
      </form>
    </Form>
  )
}

/**
 * S16 建立隊伍：「建立隊伍」按鈕＋`Dialog`。送出成功後導向該隊 S17。
 * Email 未驗證時按鈕停用並說明原因。自訂賽事帶賽事報名連結 token；連結在對話框開著時
 * 被重設，伺服器的 403（報名連結已失效）照樣顯示在對話框內。S2 的入口是 `CreateTeamEntry`（開放報名時，
 * 依登入、主辦方身分與是否已有隊伍決定是否顯示）。
 */
export function CreateTeamDialog({
  tournamentId,
  inviteToken,
}: CreateTeamProps) {
  const [open, setOpen] = useState(false)

  return (
    <VerificationRequired action="建立隊伍">
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogTrigger asChild>
          <Button>建立隊伍</Button>
        </DialogTrigger>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>建立隊伍</DialogTitle>
            <DialogDescription>
              建立後你會成為隊長，可以把邀請連結分享給隊友。
            </DialogDescription>
          </DialogHeader>
          {/* 每次開啟都是新的表單 */}
          {open && (
            <CreateTeamForm
              tournamentId={tournamentId}
              inviteToken={inviteToken}
            />
          )}
        </DialogContent>
      </Dialog>
    </VerificationRequired>
  )
}
