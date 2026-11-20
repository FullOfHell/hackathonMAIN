# Reltix mentor feedback (Friday ~19:20)

Source of truth for the product decisions below. If a plan section disagrees, this file and the official PDF win.

| Question | Mentor answer | Decision |
|---|---|---|
| Is building-wide detection realistic (≥2 units in one property reporting no heating → one central-heating job)? | Yes. | **P1, first differentiator.** Strongest "detect the moment" story. |
| What does the property manager know at report time (heating type, boiler, caretaker/key-safe access, past repairs, tenant phone for the craftsman)? | All of it. | Keep pre-filling all of it. Every field still needs the resident's explicit sharing approval; the key-safe code is never sent automatically. |
| Who pays and who approves cost? | The organizer clarified that the owner–manager agreement sets the limit and the owner approves spending above it. Three quotes commonly give the owner a choice. | Use €3,000 as a demo example. The shipped post-completion invoice hold records a manager action. Advance owner authorization and optional quote collection are follow-ups. |
| What makes the connector spec convincing? | Reltix must be able to add an **internet partner at a moment's notice**. | Connector v1 must work across categories, not just a second heating contractor. Spec shows how an internet provider plugs in (move-in → offer → signed contract → written back to the unit). Second heating provider is now lower priority. |
| Which channels do tenants use? | Mostly **texting and phone**. Younger tenants use the platform and are moving to it. Reltix **already has a voice agent** that auto-fills the app. | **Drop the ElevenLabs voice agent.** Resident channels: portal (P0) plus a **text-message channel** (P1): a simulated SMS/email outbox with one-click links to confirm a slot or follow the case. |
| What would make you mark us down? | Not asked. | Ask at the next mentor visit. |

## Resulting priority after the P0 loop

1. Building-wide outage detection.
2. Text-message channel with one-click slot confirmation (simulated outbox).
3. Demonstrate the post-completion invoice hold above the example €3,000 limit. Track the owner’s advance spending decision separately. See the [organizer answers](questions.md).
4. Internet partner plugged into the connector (capabilities registration + spec walkthrough; a minimal move-in offer flow only if time allows).
5. Previous-repair context and access details in the job (mostly done).
6. Second heating contractor (only if time remains).

Not doing: ElevenLabs voice agent, voice-to-portal continuity.
