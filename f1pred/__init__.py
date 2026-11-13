"""F1 race prediction pipeline (Phase 1: data layer).

Modules
-------
db         SQLite schema + connections
clean      team-name normalisation + row validation
fetch      FastF1: results, grid, qualifying, sprint race
openf1     OpenF1: practice laps (separate so the source can be swapped)
httpcache  cached, rate-limit-aware HTTP for OpenF1
"""
