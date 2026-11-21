import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { useState } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import {
  CompetitionService,
  type PublicMatchDetail,
  type ResultScreenshotState,
} from "@/client"
import {
  MatchResultScreenshot,
  REPLACE_SCREENSHOT_TEXT,
  showsResultScreenshot,
  UPLOAD_SCREENSHOT_TEXT,
} from "@/features/competition/MatchResultScreenshot"
import { MatchSpectatorView } from "@/features/competition/MatchSpectatorView"
import { matchQueryKey } from "@/features/competition/match-source"
import {
  RESULT_SCREENSHOT_EMPTY_TEXT,
  RESULT_SCREENSHOT_FAILED_TEXT,
  RESULT_SCREENSHOT_TITLE,
  ResultScreenshotCard,
} from "@/features/competition/ResultScreenshotCard"
import { ACCESS_TOKEN_STORAGE_KEY } from "@/features/identity/auth"
import { UNSUPPORTED_SCREENSHOT_MESSAGE } from "@/features/registration/screenshot-file"
import { httpError } from "./helpers"
import { matchDetail, TEAM_A } from "./match-detail-fixture"
import { renderWithRouterContext } from "./render-router"

type DownloadResult = Awaited<
  ReturnType<typeof CompetitionService.downloadResultScreenshot>
>
type StateResult = Awaited<
  ReturnType<typeof CompetitionService.readResultScreenshotState>
>
type UploadResult = Awaited<
  ReturnType<typeof CompetitionService.uploadResultScreenshot>
>

const UPLOADED_AT = "2026-10-18T06:10:00Z"

/** 系列結果已送出、在申訴期的場次（A 隊獲勝） */
function submitted(overrides: Partial<PublicMatchDetail> = {}) {
  return matchDetail({
    status: "appeal_window",
    outcome: "played",
    winner_id: TEAM_A.id,
    wins_a: 2,
    wins_b: 0,
    result_screenshot_enabled: true,
    result_screenshot_at: null,
    ...overrides,
  })
}

function mockDownload() {
  return vi
    .spyOn(CompetitionService, "downloadResultScreenshot")
    .mockResolvedValue({
      data: new Blob(["image"], { type: "image/png" }),
    } as unknown as DownloadResult)
}

function mockState(state: ResultScreenshotState) {
  return vi
    .spyOn(CompetitionService, "readResultScreenshotState")
    .mockResolvedValue({ data: state } as unknown as StateResult)
}

function signIn() {
  window.localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, "token-1")
}

function pngFile(name = "result.png") {
  return new File(["x"], name, { type: "image/png" })
}

function fileInput(): HTMLInputElement {
  const input = document.querySelector<HTMLInputElement>("input[type=file]")
  if (!input) throw new Error("找不到檔案欄位")
  return input
}

/** 持有場次資料的外框：refresh 把資料換成 next（模擬重抓後伺服器回傳的新狀態） */
function renderScreenshot(
  initial: PublicMatchDetail,
  next?: () => PublicMatchDetail,
) {
  const refresh = vi.fn()
  function Harness() {
    const [detail, setDetail] = useState(initial)
    refresh.mockImplementation(async () => {
      if (next) setDetail(next())
    })
    return <MatchResultScreenshot detail={detail} refresh={refresh} />
  }
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  render(
    <QueryClientProvider client={queryClient}>
      <Harness />
    </QueryClientProvider>,
  )
  return { refresh }
}

let objectUrlCount = 0
const revokeObjectURL = vi.fn()

beforeEach(() => {
  objectUrlCount = 0
  revokeObjectURL.mockClear()
  URL.createObjectURL = vi.fn(() => {
    objectUrlCount += 1
    return `blob:shot-${objectUrlCount}`
  })
  URL.revokeObjectURL = revokeObjectURL
})

afterEach(() => {
  window.localStorage.clear()
  vi.restoreAllMocks()
  // @ts-expect-error jsdom 原本沒有這兩個函式
  delete URL.createObjectURL
  // @ts-expect-error jsdom 原本沒有這兩個函式
  delete URL.revokeObjectURL
})

describe("showsResultScreenshot", () => {
  it("只有系列結果已送出的場次顯示區塊", () => {
    expect(showsResultScreenshot(submitted())).toBe(true)
    expect(showsResultScreenshot(matchDetail({ status: "live" }))).toBe(false)
    // 判棄權：有勝隊但沒有送出系列結果
    expect(
      showsResultScreenshot(
        matchDetail({
          status: "confirmed",
          outcome: "forfeit",
          winner_id: TEAM_A.id,
          result_screenshot_enabled: false,
        }),
      ),
    ).toBe(false)
  })
})

describe("ResultScreenshotCard", () => {
  it("未上傳時顯示標題與「勝隊尚未上傳結算截圖」", () => {
    render(<ResultScreenshotCard hasScreenshot={false} imageUrl={null} />)

    expect(
      screen.getByRole("heading", { name: RESULT_SCREENSHOT_TITLE }),
    ).toBeInTheDocument()
    expect(screen.getByText(RESULT_SCREENSHOT_EMPTY_TEXT)).toBeInTheDocument()
    expect(screen.queryByRole("img")).not.toBeInTheDocument()
  })

  it("已上傳時顯示最大寬 320px 的縮圖，點擊以 Dialog 放大", async () => {
    const user = userEvent.setup()
    render(<ResultScreenshotCard hasScreenshot imageUrl="blob:shot" />)

    const thumbnail = screen.getByRole("button", { name: "放大結算截圖" })
    // max-w-80 = 20rem = 320px
    expect(thumbnail).toHaveClass("max-w-80")
    expect(within(thumbnail).getByRole("img")).toHaveAttribute(
      "src",
      "blob:shot",
    )
    expect(
      screen.queryByText(RESULT_SCREENSHOT_EMPTY_TEXT),
    ).not.toBeInTheDocument()
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()

    await user.click(thumbnail)

    const dialog = await screen.findByRole("dialog", {
      name: RESULT_SCREENSHOT_TITLE,
    })
    expect(within(dialog).getByRole("img")).toHaveAttribute("src", "blob:shot")
  })

  it("圖片下載中顯示佔位，失敗時顯示錯誤文字", () => {
    const { rerender, container } = render(
      <ResultScreenshotCard hasScreenshot imageUrl={null} />,
    )
    expect(
      container.querySelector("[data-slot=result-screenshot-loading]"),
    ).not.toBeNull()

    rerender(<ResultScreenshotCard hasScreenshot imageUrl={null} imageFailed />)
    expect(screen.getByRole("alert")).toHaveTextContent(
      RESULT_SCREENSHOT_FAILED_TEXT,
    )
  })
})

describe("MatchResultScreenshot", () => {
  it("系列結果送出前不顯示，也不呼叫任何 API", () => {
    const download = mockDownload()
    const state = mockState({ can_upload: false, reason: null })
    signIn()

    renderScreenshot(matchDetail({ status: "live" }))

    expect(
      screen.queryByRole("heading", { name: RESULT_SCREENSHOT_TITLE }),
    ).not.toBeInTheDocument()
    expect(download).not.toHaveBeenCalled()
    expect(state).not.toHaveBeenCalled()
  })

  it("未登入的觀眾看到截圖，不查詢能否上傳，也沒有上傳區", async () => {
    const download = mockDownload()
    const state = mockState({ can_upload: true, reason: null })

    renderScreenshot(submitted({ result_screenshot_at: UPLOADED_AT }))

    const image = await screen.findByRole("img", {
      name: RESULT_SCREENSHOT_TITLE,
    })
    expect(image).toHaveAttribute("src", "blob:shot-1")
    expect(download).toHaveBeenCalledWith({
      path: { tournament_id: "t1", match_id: "match-M3" },
    })
    expect(state).not.toHaveBeenCalled()
    expect(document.querySelector("input[type=file]")).toBeNull()
  })

  it("未上傳時不下載圖片", async () => {
    const download = mockDownload()

    renderScreenshot(submitted())

    expect(screen.getByText(RESULT_SCREENSHOT_EMPTY_TEXT)).toBeInTheDocument()
    expect(download).not.toHaveBeenCalled()
  })

  it("敗隊隊長、裁判、主辦方（can_upload 為 false）看不到上傳區", async () => {
    signIn()
    const state = mockState({
      can_upload: false,
      reason: "not_winning_captain",
    })

    renderScreenshot(submitted())

    await waitFor(() => expect(state).toHaveBeenCalled())
    // 等這次回應被元件處理完才斷言，否則「還沒載入」也會通過
    await act(async () => {
      await state.mock.results[0].value
    })
    await act(async () => {})
    expect(document.querySelector("input[type=file]")).toBeNull()
    expect(
      screen.queryByRole("button", { name: "選擇圖片" }),
    ).not.toBeInTheDocument()
  })

  it("勝隊隊長選檔後按「上傳截圖」送出，成功後重抓並顯示截圖", async () => {
    const user = userEvent.setup()
    signIn()
    mockState({ can_upload: true, reason: null })
    mockDownload()
    const upload = vi
      .spyOn(CompetitionService, "uploadResultScreenshot")
      .mockResolvedValue({
        data: { can_upload: true, reason: null },
      } as unknown as UploadResult)
    const { refresh } = renderScreenshot(submitted(), () =>
      submitted({ result_screenshot_at: UPLOADED_AT }),
    )

    expect(
      await screen.findByRole("button", { name: "選擇圖片" }),
    ).toBeInTheDocument()
    // 還沒選檔時沒有送出按鈕
    expect(
      screen.queryByRole("button", { name: UPLOAD_SCREENSHOT_TEXT }),
    ).not.toBeInTheDocument()

    const file = pngFile()
    await user.upload(fileInput(), file)
    await user.click(
      screen.getByRole("button", { name: UPLOAD_SCREENSHOT_TEXT }),
    )

    await waitFor(() => expect(refresh).toHaveBeenCalledTimes(1))
    expect(upload).toHaveBeenCalledTimes(1)
    const options = upload.mock.calls[0][0]
    expect(options.path).toEqual({ tournament_id: "t1", match_id: "match-M3" })
    expect(options.body).toEqual({ screenshot: file })
    // 重抓後顯示截圖，選取的檔案清掉、送出按鈕消失
    expect(
      await screen.findByRole("button", { name: "放大結算截圖" }),
    ).toBeInTheDocument()
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: REPLACE_SCREENSHOT_TEXT }),
      ).not.toBeInTheDocument(),
    )
  })

  it("已有截圖時勝隊隊長的送出按鈕是「更換截圖」", async () => {
    const user = userEvent.setup()
    signIn()
    mockState({ can_upload: true, reason: null })
    mockDownload()

    renderScreenshot(submitted({ result_screenshot_at: UPLOADED_AT }))

    await screen.findByRole("button", { name: "選擇圖片" })
    await user.upload(fileInput(), pngFile("new.png"))

    expect(
      screen.getByRole("button", { name: REPLACE_SCREENSHOT_TEXT }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: UPLOAD_SCREENSHOT_TEXT }),
    ).not.toBeInTheDocument()
  })

  it("選到不支援的格式時當下報錯，不出現送出按鈕", async () => {
    // applyAccept: false 才能把非圖片檔塞進有 accept 的欄位
    const user = userEvent.setup({ applyAccept: false })
    signIn()
    mockState({ can_upload: true, reason: null })

    renderScreenshot(submitted())

    await screen.findByRole("button", { name: "選擇圖片" })
    await user.upload(
      fileInput(),
      new File(["x"], "clip.gif", { type: "image/gif" }),
    )

    expect(screen.getByText(UNSUPPORTED_SCREENSHOT_MESSAGE)).toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: UPLOAD_SCREENSHOT_TEXT }),
    ).not.toBeInTheDocument()
  })

  it("伺服器拒絕時顯示錯誤訊息，保留選取的檔案", async () => {
    const user = userEvent.setup()
    signIn()
    mockState({ can_upload: true, reason: null })
    vi.spyOn(CompetitionService, "uploadResultScreenshot").mockRejectedValue(
      httpError(403, {
        detail: {
          code: "WINNING_CAPTAIN_REQUIRED",
          message: "只有勝隊隊長可以上傳結算截圖。",
        },
      }),
    )
    const { refresh } = renderScreenshot(submitted())

    await screen.findByRole("button", { name: "選擇圖片" })
    await user.upload(fileInput(), pngFile())
    await user.click(
      screen.getByRole("button", { name: UPLOAD_SCREENSHOT_TEXT }),
    )

    expect(
      await screen.findByText("只有勝隊隊長可以上傳結算截圖。"),
    ).toBeInTheDocument()
    expect(refresh).not.toHaveBeenCalled()
    expect(
      screen.getByRole("button", { name: UPLOAD_SCREENSHOT_TEXT }),
    ).toBeEnabled()
  })
})

describe("結算截圖圖片的查詢", () => {
  it("重抓這一場的資料（invalidate 場次前綴）不會重新下載圖片", async () => {
    const download = mockDownload()
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const detail = submitted({ result_screenshot_at: UPLOADED_AT })
    render(
      <QueryClientProvider client={queryClient}>
        <MatchResultScreenshot detail={detail} refresh={vi.fn()} />
      </QueryClientProvider>,
    )
    await screen.findByRole("img", { name: RESULT_SCREENSHOT_TITLE })
    expect(download).toHaveBeenCalledTimes(1)

    await act(async () => {
      await queryClient.invalidateQueries({
        queryKey: matchQueryKey(detail.tournament.id, detail.id),
      })
    })

    expect(download).toHaveBeenCalledTimes(1)
  })

  it("上傳時間改變（更換截圖）時重新下載", async () => {
    const download = mockDownload()
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const wrap = (detail: PublicMatchDetail) => (
      <QueryClientProvider client={queryClient}>
        <MatchResultScreenshot detail={detail} refresh={vi.fn()} />
      </QueryClientProvider>
    )
    const { rerender } = render(
      wrap(submitted({ result_screenshot_at: UPLOADED_AT })),
    )
    await waitFor(() => expect(download).toHaveBeenCalledTimes(1))

    rerender(wrap(submitted({ result_screenshot_at: "2026-10-18T06:20:00Z" })))

    await waitFor(() => expect(download).toHaveBeenCalledTimes(2))
  })
})

describe("MatchSpectatorView 的結算截圖插槽", () => {
  it("排在各局列表之後、同輪其他場次之前；沒有傳入時不渲染", () => {
    const detail = submitted({
      games: [{ game_no: 1, winner_side: "a", score_a: 13, score_b: 7 }],
    })
    const { container, rerender } = renderWithRouterContext(
      <MatchSpectatorView
        detail={detail}
        resultScreenshot={
          <ResultScreenshotCard hasScreenshot={false} imageUrl={null} />
        }
      />,
    )

    const main = container.querySelector("[data-slot=match-main]")
    const slots = Array.from(main?.children ?? []).map((el) =>
      el.getAttribute("data-slot"),
    )
    expect(slots.slice(-2)).toEqual(["game-list", "match-result-screenshot"])
    // < lg：與各局列表同一順位（DOM 順序在後），早於同輪其他場次（order-4）
    expect(
      container.querySelector("[data-slot=match-result-screenshot]"),
    ).toHaveClass("max-lg:order-3")

    rerender(<MatchSpectatorView detail={detail} />)
    expect(
      container.querySelector("[data-slot=match-result-screenshot]"),
    ).toBeNull()
  })
})
