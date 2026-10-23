import { useQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"

import { UtilsService } from "@/client"

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

  let backendStatus = "無法連線"
  if (healthCheck.isPending) {
    backendStatus = "檢查中"
  } else if (healthCheck.data === true) {
    backendStatus = "正常"
  }

  return (
    <main className="flex min-h-svh flex-col items-center justify-center gap-4 p-6">
      <h1 className="text-4xl font-bold tracking-widest">FLOW</h1>
      <p className="text-muted-foreground" role="status">
        後端狀態：{backendStatus}
      </p>
    </main>
  )
}
