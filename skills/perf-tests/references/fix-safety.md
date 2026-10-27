# Fix safety checklist

A fix that clears a finding but breaks another caller, changes the business result or slows another path is a failure. Propose one targeted fix at a time and walk these three lists for each one. The Perf Sentinel suggestion is a lead, not a verdict: it can be wrong.

## Before

- [ ] Find every caller of the code you are about to change, not only the entry point the test covers. Use the LSP if available, text search otherwise, and include listeners, jobs and other services that share the module.
- [ ] Check each classic trap with the check that catches it:
  - **Fetch join or eager join duplicates rows or breaks pagination.** Look for a `LIMIT`/`OFFSET` or page size applied to the joined query, and for collections joined twice. Check the row count and the page content on a parent with several children.
  - **Batch loading changes the order of results.** An `IN (...)` query or a batch loader returns rows in database order, not in input order. Check whether a caller relies on the order, and add an explicit sort or re-map by key if it does.
  - **Cache returns stale data.** A cache added to remove a redundant call must have a clear invalidation on every write path. List the writes to the same data and check each one evicts or updates the entry.
  - **Transaction boundary or lazy loading breaks another caller.** Moving a query, adding a fetch, or changing the transaction scope or the ORM session scope can leave another caller reading a lazy relation outside its transaction, or holding a transaction longer. Check each caller found above for access to relations after the call returns.
  - **Data loaded for nothing on another path.** An eager fetch added for the tested endpoint also runs for every other caller of the same query. Check whether those callers use the new data. If not, scope the fetch to this path (dedicated query, projection, fetch plan).

## After

- [ ] Same business result with fewer calls: the new test's business assertions still pass, and the Perf Sentinel run shows the finding gone.
- [ ] The existing tests that cover the touched code pass, unit and integration both.
- [ ] Re-run the capture for the other entry points that share the changed code when they have tests, and check that their query count did not grow.

## Decision

- [ ] Show the developer the fix, the callers checked, the tests run and their results.
- [ ] List every caller that no test covers.
- [ ] The developer decides whether to keep the fix. If they do not, propose the acknowledgment entry instead, always with an `expires_at` date.

Uncovered callers are reported, never assumed correct.
