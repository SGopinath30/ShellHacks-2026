# Requirements audit — 2026-09-26

The workspace contains the organizer's `ShellHacks_Challenge_Gridlock.docx` and companion `Finding_Real_Locations_Guide.docx`, but no separate file labeled PRD. This audit compares those documents with this repo and the ASUS handoff.

## Ownership update

Dell's current task is complete: the two source-backed, one-object JSON files were delivered to ASUS, with evidence and explicit `NEEDS_REVIEW` location flags. ASUS owns coordinate verification, Big Ogeechee current-status confirmation, identification of a real DESC–Georgia Power pair within 25 miles, and upload. These are open product checks, not unfinished Dell handoff steps.

| Requirement | Current state | Owner / next action |
| --- | --- | --- |
| Public future project data from at least two utilities | Two source-backed JSON records exist, one DESC and one GPC. The organizer workbook is isolated as fixture data. | ASUS confirms Georgia Power Big Ogeechee's present status; its June 2026 source anticipated summer completion. |
| Correct real-world project locations | Both records carry reference coordinates, explicitly `UNRESOLVED` and `NEEDS_REVIEW`. DESC uses Winnsboro town center; GPC uses the nearby Little Ogeechee substation. | ASUS replaces each proxy with a project-specific, independently checked coordinate and retains the supporting map/GIS citation before spatial matching. |
| Geographic overlap within **strictly under 25 miles** | No verified pair is available in the Dell handoff. The two reference points are about 164 miles apart, which is not a valid project-to-project distance. | ASUS finds and verifies a DESC/GPC pair near the South Carolina–Georgia border, then calculates the actual project distance. |
| Timeline overlap in the construction window | Current JSON schedules are `UNKNOWN`; neither cited source gives a confirmed construction start/end pair. | ASUS checks actual build windows where published. An in-service date is `IN_SERVICE_GAP`, not a construction window. |
| Interactive UI of both utilities' plans and highlighted overlap | This Dell repo has ingestion and handoff code, no UI. | ASUS integrates validated records into the interactive UI. |
| Ranked coordination opportunities | No verified overlap pair or ranking is produced in this Dell repo. | ASUS calculates and ranks opportunities from validated project versions. |
| Rough cost/impact estimate | Bonus requirement, not yet done in this Dell repo. | Product team may add this after a real opportunity has been verified. |
| API handoff | Two one-object JSON files plus ten separate fixtures pass the saved `ProjectInput` schema. The two source-backed files were given to ASUS. | Dell handoff complete; ASUS checks and uploads. |

The companion guide explicitly says to confirm every coordinate against project descriptions, region, and landmarks before keeping a match. The current source-backed records do not pass that location gate. The supplied Georgia Power IRP PDF includes pages marked CEII/confidential and should not be used for a public-data handoff solely because its filename says public disclosure.
