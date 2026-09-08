# Daily Sales Workflow

The intended daily workflow for a salesperson using the platform. Every step
operates on real, source-traceable data; the platform recommends, the human
decides, and no message is sent without explicit approval.

1. **Review high-intent opportunities.** Open the **Dashboard** and **Pipeline**;
   sort leads by priority (HOT/WARM) and lead score. Alerts (bell) surface new
   high-intent leads, hiring surges, new tenders/projects, and closing deadlines.

2. **Open the evidence.** From **Lead Details**, expand the evidence panel to see
   the source, published/observed dates, verification status, and confidence for
   every supporting fact. Trace lead → evidence → source URL.

3. **Verify company intelligence.** Open **Company Details** for hiring activity,
   technologies, signals, tenders, and the business timeline (system events vs
   human activities).

4. **Review target roles / contacts.** The stakeholder panel recommends target
   roles; verified business contacts (source-backed) appear where available.
   Contacts are never guessed.

5. **Review AI reasoning.** The AI Intelligence panel gives an evidence-grounded
   summary, explicitly separating FACT (cited to evidence) from INFERENCE and
   listing unknowns. AI confidence is shown separately from lead/evidence
   confidence — it never upgrades them.

6. **Edit / approve outreach.** In the **Outreach** workspace, generate a draft
   (grounded in the lead's evidence), edit it, and approve it. An ungrounded draft
   cannot be approved. Nothing is sent at this step.

7. **Send through the configured provider.** Send an APPROVED draft; it is marked
   SENT only when the email provider confirms. If no provider is configured, the
   draft stays approved and the UI says so — it is never shown as sent.

8. **Record the activity.** A SENT email creates a CRM activity and advances the
   lead to CONTACTED (only on real, provider-confirmed send).

9. **Track replies.** Real inbound replies (via webhook) are recorded as
   activities, classified (grounded in the message text), advance the lead to
   REPLIED, and create a "review reply" follow-up task. No reply is ever invented.

10. **Update the pipeline.** Move the sales opportunity through stages
    (Identified → … → Won/Lost) as real activity warrants; WON/LOST are gated
    behind explicit human confirmation.

11. **Follow up.** Work the **Follow-ups** list — tasks generated from real
    conditions (sent + no reply after the window, tender closing soon, priority
    increase).

12. **Review analytics.** The **Analytics** / **CRM analytics** views show real
    funnel/conversion metrics; where there aren't enough real events they show
    *Insufficient data*, and pipeline value shows *Not available* rather than a
    fabricated figure.

See also: [architecture-map.md](architecture-map.md),
[data-quality-and-validation.md](data-quality-and-validation.md),
[crm-outreach.md](crm-outreach.md).
