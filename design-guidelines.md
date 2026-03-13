# Design Guidelines — Dashboard Output Standards

## Audience & Context

The dashboard is opened by:
1. **Paid ads manager** — weekly, needs operational detail and action items
2. **Marketing leadership** — occasional, needs a quick read on spend efficiency and pipeline

Design for the ads manager as primary. Leadership should be able to get what they need from the top of the page without scrolling.

---

## Visual Language

### Colour palette (defined in template.html)
| Use | Colour | Hex |
|-----|--------|-----|
| Background | Slate 100 | `#F1F5F9` |
| Card/panel | White | `#FFFFFF` |
| Primary text | Slate 800 | `#1E293B` |
| Secondary text | Slate 500 | `#64748B` |
| Muted text | Slate 400 | `#94A3B8` |
| Border | Slate 200 | `#E2E8F0` |
| Accent / interactive | Blue 500 | `#3B82F6` |
| Good / on-target | Green 600 | `#16A34A` |
| Warning | Amber 600 | `#D97706` |
| Bad / high priority | Red 600 | `#DC2626` |

### Severity coding (used in Optimizations tab)
| Severity | Meaning | Left border colour |
|----------|---------|-------------------|
| High | Priority 1 issue — spend wasted or 0 MQLs | Red `#DC2626` |
| Medium | Priority 2 — efficiency below benchmark | Amber `#D97706` |
| Low | Priority 3–4 — structural or minor issues | Blue `#3B82F6` |
| OK | No issues found | Green `#16A34A` |

### Rate colouring (MQL→SQL%)
- ≥ 30% → green (`rate-hi`)
- 15–29% → amber (`rate-mid`)
- < 15% → red (`rate-lo`)

---

## Layout Principles

### Information hierarchy
1. **KPI bar** (top) — total spend, MQL, SQL, MQL→SQL%, Cost/MQL, Cost/SQL for the selected period
2. **Tables** — breakdown by campaign type and region; always include a Total row
3. **Comparison** — Paid Search vs Paid Other side by side
4. **Detail tabs** — Ad Groups and Optimizations for drill-down

The top of the page must answer "how are we doing overall?" without any interaction. Period filter is available but defaults to Last 3M.

### Tables vs charts
- **Use tables** for: campaign breakdowns, ad group data, optimization issues — exact numbers matter
- **Use charts** for: trends over time, channel comparisons where relative size is the point
- Never use a pie chart. Use bar charts for comparisons, line charts for trends.
- Keep chart height modest (height: 80 on Chart.js) — they're supporting, not hero

### Number formatting
| Value type | Format | Example |
|-----------|--------|---------|
| Currency < $1k | `$XXX` | `$847` |
| Currency ≥ $1k | `$XX.Xk` | `$12.4k` |
| Large numbers | `XXk` or `XX.XM` | `45.2k`, `1.3M` |
| Percentages | `XX.X%` | `23.7%` |
| CPC/Cost/MQL | `$XX.XX` | `$18.42` |
| Counts (MQL, SQL) | Integer | `47` |

---

## Content Standards

### Executive summary (KPI bar)
- Max 6 metrics — don't overload
- Label every metric clearly (no abbreviations without explanation)
- Show the period in the header/meta line so leadership knows what they're looking at

### Tables
- Sort by most impactful metric (usually cost, then MQL)
- Always show a Total/footer row
- Exclude "Other" category from display — it adds noise without actionability
- Use TYPE_ORDER and REGION_ORDER for consistent sequencing across views

### Optimization recommendations (campaign cards)
- **One issue = one bullet** — no compound sentences
- **Lead with the data**: start with the metric value, then the interpretation
  - ✅ `CTR 0.8% is below 1% — test new RSA headlines`
  - ❌ `You should test new headlines because CTR is low`
- **Be specific**: name the ad group, give the actual cost, show the ratio
- Max 10 issues per campaign, ordered by priority (P1 first)
- If no issues: show "✓ No issues found for this period" in green — don't leave blank
- Period label on every card so leadership knows the data window

### Tone
- **Direct** — no padding, no "consider exploring the possibility of"
- **Metric-first** — lead with numbers, explain second
- **Actionable** — every issue should imply an obvious next step
- **Not alarmist** — "CTR is below benchmark" not "CTR is terrible"

---

## Tab Structure Guidelines

| Tab | Audience | Interaction | Data freshness |
|-----|----------|-------------|----------------|
| Overview | Both | Period filter | Regenerated weekly |
| Ad Groups | Ads manager | Period filter + search | Regenerated weekly |
| Optimizations | Both | None (static) | Always last 3 months |

### Period filter defaults
- Default: Last 3M
- Available presets: Last 1M, Last 3M, Last 6M, YTD, custom From/To
- Period filter applies immediately on change — no "apply" button needed

---

## What Not To Do

- **Don't add more KPI cards** — 6 is the max; any more and the bar loses scannability
- **Don't show raw campaign names** from the Looker export in the UI — they're unreadable (`SMB_Inbound_Google_PPC_SEM_GymMgmt_WW_010125`); use `make_display_name()` or the grouped campaign_type + region labels
- **Don't add interactivity for its own sake** — if a filter isn't answering a real question, cut it
- **Don't use colour as the only signal** — always pair colour with text (for accessibility and printing)
- **Don't show empty states without explanation** — always say why there's no data (wrong period, not yet connected, etc.)
