# Evidence-backed content review

Kō treats generated prose as a draft, never as evidence. A newsletter may be
published only when its exact content hash passes two independent research
agents plus an adversarial verifier in `data/content_audit.json`.

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

1. Prepare a candidate without publishing it:

   ```bash
   python season_mailer.py --prepare-season 41
   ```

2. Generate a review inventory:

   ```bash
   python content_auditor.py inventory --season 41 > /tmp/season-41-review.json
   ```

3. Run the independent review quorum:

   ```bash
   python agent_content_reviewer.py --season 41
   ```

4. The command runs two independent web-search researchers and a separate
   adversarial verifier. Every claim requires unanimous status, confidence of
   at least 0.90 from all three runs, acceptable direct sources, and the
   deterministic date/region/category checks.
5. Rejected or uncertain claims remain blocked. Regenerate or correct them,
   then rerun the quorum until the content hash is stable.
6. Run the strict gate:

   ```bash
   python content_auditor.py audit --season 41 --strict
   ```

7. Rebuild both language archives. Any later content edit invalidates the
   approval hash and triggers a fresh agent review.

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
