https://github.com/hardikpandya/stop-slop
# hardikpandya/stop-slop: A skill file for removing AI tells from prose
2026-08-11
## Stop Slop

A skill for removing AI tells from prose.

[![G-Yg4RVbIAAhVxW](https://private-user-images.githubusercontent.com/591262/534376264-902afc15-1f40-4a9d-af24-8cd67afb8ebf.png?jwt=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJnaXRodWIuY29tIiwiYXVkIjoicmF3LmdpdGh1YnVzZXJjb250ZW50LmNvbSIsImtleSI6ImtleTUiLCJleHAiOjE3ODY0NDcwOTcsIm5iZiI6MTc4NjQ0Njc5NywicGF0aCI6Ii81OTEyNjIvNTM0Mzc2MjY0LTkwMmFmYzE1LTFmNDAtNGE5ZC1hZjI0LThjZDY3YWZiOGViZi5wbmc_WC1BbXotQWxnb3JpdGhtPUFXUzQtSE1BQy1TSEEyNTYmWC1BbXotQ3JlZGVudGlhbD1BS0lBVkNPRFlMU0E1M1BRSzRaQSUyRjIwMjYwODExJTJGdXMtZWFzdC0xJTJGczMlMkZhd3M0X3JlcXVlc3QmWC1BbXotRGF0ZT0yMDI2MDgxMVQxMTEzMTdaJlgtQW16LUV4cGlyZXM9MzAwJlgtQW16LVNpZ25hdHVyZT1hOTgwNDA4ZDcxMWM1OWY0MWQ0NjQ0ZWQ1NzIwZGI4NmRkZjc4ODc1ODU3MTk1Zjc0M2I5MGIzZjYyZjUwM2ZiJlgtQW16LVNpZ25lZEhlYWRlcnM9aG9zdCZyZXNwb25zZS1jb250ZW50LXR5cGU9aW1hZ2UlMkZwbmcifQ.NT9LtP0_YW1RPakAp0pUdjjIWMQsB40OsJhJYZKoWr0)](https://private-user-images.githubusercontent.com/591262/534376264-902afc15-1f40-4a9d-af24-8cd67afb8ebf.png?jwt=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJnaXRodWIuY29tIiwiYXVkIjoicmF3LmdpdGh1YnVzZXJjb250ZW50LmNvbSIsImtleSI6ImtleTUiLCJleHAiOjE3ODY0NDcwOTcsIm5iZiI6MTc4NjQ0Njc5NywicGF0aCI6Ii81OTEyNjIvNTM0Mzc2MjY0LTkwMmFmYzE1LTFmNDAtNGE5ZC1hZjI0LThjZDY3YWZiOGViZi5wbmc_WC1BbXotQWxnb3JpdGhtPUFXUzQtSE1BQy1TSEEyNTYmWC1BbXotQ3JlZGVudGlhbD1BS0lBVkNPRFlMU0E1M1BRSzRaQSUyRjIwMjYwODExJTJGdXMtZWFzdC0xJTJGczMlMkZhd3M0X3JlcXVlc3QmWC1BbXotRGF0ZT0yMDI2MDgxMVQxMTEzMTdaJlgtQW16LUV4cGlyZXM9MzAwJlgtQW16LVNpZ25hdHVyZT1hOTgwNDA4ZDcxMWM1OWY0MWQ0NjQ0ZWQ1NzIwZGI4NmRkZjc4ODc1ODU3MTk1Zjc0M2I5MGIzZjYyZjUwM2ZiJlgtQW16LVNpZ25lZEhlYWRlcnM9aG9zdCZyZXNwb25zZS1jb250ZW50LXR5cGU9aW1hZ2UlMkZwbmcifQ.NT9LtP0_YW1RPakAp0pUdjjIWMQsB40OsJhJYZKoWr0)

## What this is

AI writing has patterns. Predictable phrases, structures, rhythms. This skill teaches Claude (or any LLM) to catch and remove them.

## Skill Structure

```
stop-slop/
├── SKILL.md              # Core instructions
├── references/
│   ├── phrases.md        # Phrases to remove
│   ├── structures.md     # Structural patterns to avoid
│   └── examples.md       # Before/after transformations
├── README.md
└── LICENSE
```

## Quick start

**Claude Code:** Add this folder as a skill.

**Claude Projects:** Upload `SKILL.md` and reference files to project knowledge.

**Custom instructions:** Copy core rules from `SKILL.md`.

**API calls:** Include `SKILL.md` in your system prompt. Reference files load on demand.

## What it catches

**Banned phrases** - Throat-clearing openers, emphasis crutches, business jargon, all adverbs, vague declaratives, meta-commentary. See `references/phrases.md`.

**Structural clichés** - Binary contrasts, negative listings, dramatic fragmentation, rhetorical setups, false agency, narrator-from-a-distance voice, passive voice. See `references/structures.md`.

**Sentence-level rules** - No Wh- sentence starters, no em dashes, no staccato fragmentation, no lazy extremes, active voice required.

## Scoring

Rate 1-10 on each dimension:

| Dimension | Question |
| --- | --- |
| Directness | Statements or announcements? |
| Rhythm | Varied or metronomic? |
| Trust | Respects reader intelligence? |
| Authenticity | Sounds human? |
| Density | Anything cuttable? |

Below 35/50: revise.

[Hardik Pandya](https://hvpandya.com/)

## License

MIT. Use freely, share widely.