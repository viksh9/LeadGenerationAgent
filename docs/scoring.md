"""How scoring, intent levels, and sales motions are derived."""

# Scoring and intelligence

## Signal types

| Type | Typical evidence | Weight |
| --- | --- | --- |
| `project` | RFP, migration, automation rollout | 28 |
| `funding` | Round announced | 22 |
| `hiring` | Roles that imply a delivery gap | 18 |
| `leadership` | New exec mandate | 14 |
| `expansion` | New sites or markets | 12 |
| `tech_stack` | Legacy / modernization talk | 10 |

Strength is clamped to 0–1, then boosted for recent events (≤30 / ≤90 days) and keyword matches (RFP, Series B, Head of, legacy, and similar).

## Account score

```
score = min(100, Σ type_weight × strength + diversity_bonus + corroboration_bonus)
```

- Diversity bonus: +8 for each extra signal *category*.
- Corroboration bonus: +10 if two or more signals have strength ≥ 0.8.

Intent levels: `low` < 40, `medium` < 65, `high` < 80, `critical` ≥ 80.

## Motions

Buying stage is taken from the strongest, most advanced signal (`evaluation` ahead of `awareness`). Motions range from an RFP workshop to nurture content.
