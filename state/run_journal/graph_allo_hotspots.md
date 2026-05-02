# ALLO Inflation Hotspots

- hotspot_families: `1`
- ordering: `highest cleanup payoff first`

## `ALLOCATION-FAMILY`
- cleanup_payoff: `65`
- action: `demote frontmatter`
- why: this is useful classification, but too granular for graph-node status
- candidates: `10`
- triage: `cheap_metadata=8, ignore_route=2`
- decisions: `demote_frontmatter=8, ignore_route=2`
- example notes:
  - `90-Archive\04 Archive\Misc 1\Q3-4 Mix\20225-08-30 PasteBin.md` -> `Translate this theoretical data framework into concrete research design for thesis methodology chapter` => `demote_frontmatter` (granular_allocation_sentence)
  - `90-Archive\04 Archive\Misc 1\Q3-4 Mix\2025-01-06 Reflection on Writing.md` -> `Practice writing passages that integrate table-like structure with cause-effect reasoning and emansipatory narrative` => `demote_frontmatter` (granular_allocation_sentence)
  - `90-Archive\04 Archive\Misc 1\Q3-4 Mix\2025-01-20 Daily Log.md` -> `Map the thesis argument connecting institutional history with Bhaskar's transcendental arguments` => `ignore_route` (route_like_low_reuse)
  - `90-Archive\04 Archive\Misc 1\Q3-4 Mix\2025-01-24 Tree Skripsi.md` -> `Populate each node with content, prioritizing the Krisis and Metakritik branches first` => `ignore_route` (route_like_low_reuse)
  - `90-Archive\04 Archive\Misc 1\Q3-4 Mix\2025-01-27 Kelahiran Ilmu Pengetahuan.md` -> `Develop this definitional chapter as the first building block, connecting to Bhaskar's critique of positivism` => `demote_frontmatter` (granular_allocation_sentence)
