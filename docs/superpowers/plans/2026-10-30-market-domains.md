# Market domains and rates implementation plan

Approved inline execution; preserve existing SQLite tables and report snapshot.
Goal: three logical domains, separate prior estimates, four yield cards.
Architecture: additive SQL views over existing sources; estimates never overwrite
observations. Report cards read only frozen report rows. No invented source URLs.

- [ ] Add test_market_domains.py: category mapping, sparse DB migration, percent
  and bp inversion, invalid denominator, explicit prior-date requirements.
- [ ] Run `python -m unittest test_market_domains -q` red before implementation.
- [ ] Add market_domains.py: initialize additive views, separate estimates table,
  Decimal calculations with explicit current/prior dates and basis confirmation.
- [ ] Call schema setup after collection stages; include rate cards in HTML from
  report_context, retaining audit details. Test exact rates and missing placeholders.
- [ ] Run full regression. Public source acceptance for KR3Y and corporate AA-
  remains pending because Computer Use is disabled; do not claim live collection.
