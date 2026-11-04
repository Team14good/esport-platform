import { zodResolver } from "@hookform/resolvers/zod"
import { PlusIcon } from "lucide-react"
import { useEffect, useId, useState } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"

import type { PublicSchool } from "@/client"
import { DataTable, type DataTableColumn } from "@/components/common/DataTable"
import { EmptyState } from "@/components/common/EmptyState"
import { FormErrorAlert } from "@/components/common/FormErrorAlert"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { LoadingButton } from "@/components/ui/loading-button"
import {
  type ApiError,
  applyFieldErrors,
  getErrorMessage,
  parseApiError,
} from "@/lib/api-error"
import {
  SCHOOL_NAME_MAX_LENGTH,
  useCreateSchool,
  useRenameSchool,
} from "./admin-schools"
import { codePointLength } from "./SignupForm"
import { useSchools } from "./schools"

export const SCHOOLS_EMPTY_TEXT = "還沒有學校。"
export const SCHOOLS_FILTERED_EMPTY_TEXT = "沒有符合條件的學校。"
export const SCHOOLS_PAGE_SIZE = 20
const SCHOOL_NAME_TAKEN = "SCHOOL_NAME_TAKEN"

const schoolSchema = z.object({
  name: z
    .string()
    .trim()
    .min(1, "請輸入學校名稱")
    .refine((value) => codePointLength(value) <= SCHOOL_NAME_MAX_LENGTH, {
      message: `學校名稱最多 ${SCHOOL_NAME_MAX_LENGTH} 個字`,
    }),
})

type SchoolValues = z.infer<typeof schoolSchema>

type SchoolDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 修正名稱時是原本的學校（預填原名）；新增時不給 */
  school?: PublicSchool
}

/** 新增學校或修正學校名稱的 Dialog；名稱重複（409）顯示在欄位下方。 */
function SchoolDialog({ open, onOpenChange, school }: SchoolDialogProps) {
  const create = useCreateSchool()
  const rename = useRenameSchool()
  const [formError, setFormError] = useState<ApiError | null>(null)
  const form = useForm<SchoolValues>({
    resolver: zodResolver(schoolSchema),
    defaultValues: { name: school?.name ?? "" },
  })
  // 驗證中也算送出中，避免連點送出兩次
  const pending =
    create.isPending || rename.isPending || form.formState.isSubmitting
  const title = school ? "修正學校名稱" : "新增學校"

  const submit = form.handleSubmit(async (values) => {
    setFormError(null)
    try {
      if (school) {
        await rename.mutateAsync({ schoolId: school.id, name: values.name })
      } else {
        await create.mutateAsync(values.name)
      }
      onOpenChange(false)
    } catch (error) {
      const parsed = parseApiError(error)
      if (parsed.kind === "business" && parsed.code === SCHOOL_NAME_TAKEN) {
        form.setError(
          "name",
          { type: "server", message: parsed.message },
          { shouldFocus: true },
        )
        return
      }
      setFormError(applyFieldErrors(form, error))
    }
  })

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        // 送出中不能關閉
        if (!pending) onOpenChange(next)
      }}
    >
      <DialogContent showCloseButton={false}>
        <Form {...form}>
          <form noValidate onSubmit={submit} className="flex flex-col gap-5">
            <DialogHeader>
              <DialogTitle className="text-heading-md">{title}</DialogTitle>
              <DialogDescription className="text-body">
                {school
                  ? "已選這所學校的帳號與申請會一起顯示新名稱。"
                  : "新增後，註冊與申請主辦方時就能選到這所學校。"}
              </DialogDescription>
            </DialogHeader>
            <FormErrorAlert error={formError} />
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>學校名稱</FormLabel>
                  <FormControl>
                    <Input autoComplete="off" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                disabled={pending}
                onClick={() => onOpenChange(false)}
              >
                取消
              </Button>
              <LoadingButton type="submit" loading={pending}>
                {school ? "修正名稱" : "新增學校"}
              </LoadingButton>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}

/** 篩選學校名稱：去除前後空白、不分大小寫的部分比對。 */
export function filterSchools(
  schools: PublicSchool[],
  keyword: string,
): PublicSchool[] {
  const needle = keyword.trim().toLowerCase()
  if (!needle) return schools
  return schools.filter((school) => school.name.toLowerCase().includes(needle))
}

/** S36 學校清單：依名稱列出（前端每頁 20 筆）、關鍵字篩選、新增學校與修正名稱。 */
export function AdminSchoolsPage() {
  const searchId = useId()
  const schools = useSchools()
  const [keyword, setKeyword] = useState("")
  const [page, setPage] = useState(1)
  const [creating, setCreating] = useState(false)
  const [renaming, setRenaming] = useState<PublicSchool | null>(null)

  const filtered = schools.data
    ? filterSchools(schools.data, keyword)
    : undefined
  const totalPages = Math.max(
    1,
    Math.ceil((filtered?.length ?? 0) / SCHOOLS_PAGE_SIZE),
  )

  // 篩選或資料變少時頁碼不超出最後一頁
  useEffect(() => {
    if (page > totalPages) setPage(totalPages)
  }, [page, totalPages])

  const columns: DataTableColumn<PublicSchool>[] = [
    {
      key: "name",
      header: "學校名稱",
      cell: (row) => <span className="break-words">{row.name}</span>,
    },
    {
      key: "actions",
      header: "操作",
      cell: (row) => (
        // 每一列的無障礙名稱帶上學校名稱，讀螢幕軟體才分得出是哪一筆
        <Button
          variant="outline"
          size="sm"
          aria-label={`修正「${row.name}」的名稱`}
          onClick={() => setRenaming(row)}
        >
          修正名稱
        </Button>
      ),
    },
  ]

  const toolbar = (
    <div className="flex flex-col gap-2 sm:max-w-sm">
      <Label htmlFor={searchId}>搜尋學校</Label>
      <Input
        id={searchId}
        type="search"
        value={keyword}
        placeholder="輸入學校名稱的關鍵字"
        onChange={(event) => {
          setKeyword(event.target.value)
          setPage(1)
        }}
      />
    </div>
  )

  return (
    <section className="flex min-w-0 flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-heading-lg">學校清單</h1>
        <Button onClick={() => setCreating(true)}>
          <PlusIcon aria-hidden="true" />
          新增學校
        </Button>
      </div>
      {schools.isError && !schools.data ? (
        <div className="flex flex-col items-start gap-3">
          <p className="text-body text-destructive">
            {getErrorMessage(parseApiError(schools.error))}
          </p>
          <Button variant="outline" onClick={() => schools.refetch()}>
            重新載入
          </Button>
        </div>
      ) : (
        <DataTable
          label="學校"
          columns={columns}
          rows={filtered?.slice(
            (page - 1) * SCHOOLS_PAGE_SIZE,
            page * SCHOOLS_PAGE_SIZE,
          )}
          getRowId={(row) => row.id}
          page={page}
          pageSize={SCHOOLS_PAGE_SIZE}
          total={filtered?.length ?? 0}
          onPageChange={setPage}
          toolbar={toolbar}
          empty={
            <EmptyState
              title={
                keyword.trim()
                  ? SCHOOLS_FILTERED_EMPTY_TEXT
                  : SCHOOLS_EMPTY_TEXT
              }
            />
          }
        />
      )}
      {/* 每次開啟都重新掛載：表單從預填值開始，不留上次的錯誤 */}
      {creating && <SchoolDialog open onOpenChange={setCreating} />}
      {renaming && (
        <SchoolDialog
          key={renaming.id}
          open
          school={renaming}
          onOpenChange={(open) => {
            if (!open) setRenaming(null)
          }}
        />
      )}
    </section>
  )
}
