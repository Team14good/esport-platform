import { CircleAlertIcon } from "lucide-react"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { type ApiError, getErrorMessage } from "@/lib/api-error"
import { cn } from "@/lib/utils"

type FormErrorAlertProps = {
  /** applyFieldErrors 的回傳值：寫不進欄位的錯誤或業務錯誤；null 時不顯示 */
  error: ApiError | null
  className?: string
}

/** 表單頂部的錯誤 Alert：照實顯示伺服器的 detail.message。 */
export function FormErrorAlert({ error, className }: FormErrorAlertProps) {
  if (!error) return null

  const messages =
    error.kind === "validation"
      ? Object.values(error.fields)
      : [getErrorMessage(error)]

  return (
    <Alert variant="destructive" className={cn("rounded-md", className)}>
      <CircleAlertIcon />
      <AlertDescription className="text-destructive">
        {messages.map((message, index) => (
          <p key={index}>{message}</p>
        ))}
      </AlertDescription>
    </Alert>
  )
}
