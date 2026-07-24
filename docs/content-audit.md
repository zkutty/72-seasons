# Evidence-backed content review

Kō treats generated prose as a draft, never as evidence. A newsletter may be
published only when its exact content hash has a completed human review in
`data/content_audit.json`.

## Evidence policy

The editorial baseline is national Japan. A regional ingredient, dish, natural
event, or custom is valid only when the content identifies the region and the
review decision records the same `region_context`.

Evidence is accepted when it has either:

- one government or public-industry source; or
- two independent established culinary references.

The source must support the specific assertion and time window. A general page
about an ingredient does not prove that it is at peak in a particular
micro-season. Search snippets and model output are not sources.

## Review workflow

1. Add reviewed facts for the upcoming season to `data/fact_catalog.json`,
   then prepare a candidate without publishing it:

   ```bash
   python season_mailer.py --prepare-season 41
   ```

2. Generate a review inventory:

   ```bash
   python content_auditor.py inventory --season 41 > /tmp/season-41-review.json
   ```

3. Research each factual field. Add canonical facts and their sources to
   `data/fact_catalog.json`.
4. Copy the season entry into `data/content_audit.json`. Set every claim to
   `verified` with supporting `fact_ids`, or mark `summary`/`opening` as
   `non_factual` only when it contains no concrete assertion. Closings require
   the same explicit decision: purely poetic imagery may be non-factual, while
   a concrete natural or seasonal assertion needs evidence. Record the human
   reviewer and ISO review timestamp.
5. Correct unsupported content in both languages, regenerate the inventory,
   and repeat until the content hash is stable.
6. Run the strict gate:

   ```bash
   python content_auditor.py audit --season 41 --strict
   ```

7. Rebuild and review both language archives. Any later content edit invalidates
   the approval hash and requires another review.

## Finding severity

Hard failures include missing review decisions, invented or unverified facts,
insufficient sources, unsupported date/region combinations, and content changed
after approval. They block both sending and static publishing.

Warnings identify stale manifest paths and other cleanup that does not weaken
the evidence for current content.

## Blocked-send recovery

The evidence gate runs before lookup generation, archive writes, or email, so an
audit failure means no partial publication occurred. Read the field-specific
failure output, correct the catalog/content/manifest through the normal review
workflow, and rerun the strict audit.

If the scheduled season start has passed, inspect the workflow log and
`_sent_on` marker to confirm that no message was delivered. Only then use the
manual season-mailer workflow with its intentional force option. Never use
force to bypass an audit: it changes date/send guards, while the evidence gate
remains mandatory.
