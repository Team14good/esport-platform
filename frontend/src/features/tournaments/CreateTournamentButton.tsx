import { Link } from "@tanstack/react-router"
import { PlusIcon } from "lucide-react"

import { Button } from "@/components/ui/button"

export const CREATE_TOURNAMENT_TEXT = "建立賽事"

/** 前往 S26 建立賽事；S25 空狀態與標題列、S1 空狀態（主辦方）共用。 */
export function CreateTournamentButton() {
  return (
    <Button asChild>
      <Link to="/organizer/tournaments/new">
        <PlusIcon aria-hidden="true" />
        {CREATE_TOURNAMENT_TEXT}
      </Link>
    </Button>
  )
}
