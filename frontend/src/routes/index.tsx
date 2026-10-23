import { useQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"

import { UtilsService } from "@/client"
import { Skeleton } from "@/components/ui/skeleton"

export const Route = createFileRoute("/")({
  component: Home,
})

function Home() {
  const healthCheck = useQuery({
    queryKey: ["utils", "health-check"],
    queryFn: async () => (await UtilsService.healthCheck()).data,
    // 後端沒回應時立刻顯示「無法連線」，不要重試好幾秒
    retry: false,
  })

  return (
    <section className="flex flex-1 flex-col items-center justify-center gap-4 py-12">
      <h1 className="text-display">FLOW</h1>
      {healthCheck.isPending ? (
        // 首次載入：形狀與下方狀態文字相符
        <div role="status" aria-busy="true">
          <Skeleton
            data-testid="health-check-skeleton"
            className="h-[22px] w-32"
          />
          <span className="sr-only">載入中</span>
        </div>
      ) : (
        <p className="text-muted-foreground" role="status">
          後端狀態：{healthCheck.data === true ? "正常" : "無法連線"}
        </p>
      )}
    </section>
  )
}
