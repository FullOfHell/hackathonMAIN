# Organizer questions and answers

1. Should the resident be able to change their personal data (address, heater model, etc.)? Is their account/info given by you, do they have to make a request to change it, etc.?

   **Organizer answer.** Residents should ideally be able to edit most of their own information. The organizer left the rules for overwriting property records unspecified.

   **Team decision.** Residents can edit their own name, email, phone and contact preference in the demo through the profile API. IDs, move-in date, unit address, heating equipment and access details are read-only. The acting resident ID simulates identity. Partner sharing requires a separate approval. See the [profile API examples](assumptions.md#resident-profile-api).

2. In pdf at "user experience" it says "a sensible choice of channel". Could you elaborate on that? The way we see it we'd send notifications (sms/mail) to tenants/contractors when something happens like the heater being repaired/broken or the request being accepted, and to PM's when a problem happens (and is fixed). Did you have something else in mind?

   **Organizer answer.** Any sensible channel is acceptable, including WhatsApp or a centrix-style app.

   **Team decision.** Use the portal for P0. A simulated text-message outbox is a later channel.

3. 	Suppose HeatFix expects a €3,200 repair before starting work. Does it get auto-rejected or does it get flagged for the price?

   **Organizer answer.** The owner–manager agreement sets the spending limit. Above it, the owner approves. Three quotes are common and let the owner choose. The organizer did not require three quotes for every repair.

   **Team decision.** Use €3,000 as the demo example. The shipped API holds a high invoice after completion and records a simulated manager action. Advance owner authorization and quote collection are follow-up work.

4. If HeatFix never responds, when does someone take ownership? Is the next step another contractor or a manager follow-up?

   **Organizer answer.** The organizer left partner non-response to the team’s judgment and specified no timeout.

   **Team decision.** Retry uncertain delivery with the original idempotency key. Flag an acknowledged job that goes unanswered for manager follow-up. Automatic detection of unanswered jobs is follow-up work.

5. Since we shouldn't worry about authentication, should user roles be a concern? We were thinking of hard-coding them for the presentation (i.e. the presenter gets to choose upon opening the app if they are a PM or a tenant) but let us know if you had a different direction around it (like maybe having all the screens visible - i.e. all roles combined).

   **Organizer answer.** Authentication is unnecessary for this prototype.

   **Team decision.** A role switcher is our presentation choice. The current portal exposes resident, partner and manager views. Login and role-based access control are outside P0. Partner callbacks still use their connector credential.
