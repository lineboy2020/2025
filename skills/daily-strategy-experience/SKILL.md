---
name: daily-strategy-experience
description: Daily strategy experience logging and synthesis for quantitative strategy research. Use when the user wants a daily routine that reviews backtest logs, strategy outputs, experiment notes, and recent results, then summarizes effective lessons into a persistent strategy experience library. Also use for daily strategy journals, strategy learning accumulation, and writing structured daily experience entries into Markdown/Obsidian notes.
---

# Daily Strategy Experience

Review the day's strategy artifacts and turn them into structured, reusable experience notes.

## Goal

Accumulate strategy knowledge day by day instead of leaving insights scattered across logs, scripts, backtests, and chat history.

Primary output:
- a concise daily strategy experience record
- extracted facts, hypotheses, and next-step applications
- updates to the long-term strategy knowledge base when useful

## Default workflow

For each daily run:
1. Check recent backtest outputs, logs, notes, and related reports
2. Identify the most important findings of the day
3. Separate:
   - facts
   - tentative hypotheses
   - candidate rules
4. Write a structured daily summary
5. Append or sync high-value learnings into the strategy experience library

## Preferred document set

Use these files when present:
- `策略成功经验模板.md`
- `策略迭代升级框架.md`
- `策略经验库索引.md`

Daily notes may also be written into:
- `memory/YYYY-MM-DD.md`
- a dedicated strategy daily note if the user prefers

## Writing rules

Always write with these layers clearly separated:
- statistical fact
- interpretation/hypothesis
- intended use next round

Do not convert a fresh observation directly into a core rule unless repeated evidence supports it.

## Suggested daily output structure

- Today's research focus
- Backtest/log sources reviewed
- Key statistical facts
- Today's strategy experience
- Whether the experience is observation / trial / formal rule
- How to apply it in the next iteration
- Risks or counterexamples

## Maintenance behavior

When asked to run routinely:
- prefer one short, high-quality daily entry over a long dump
- capture only the most decision-relevant lessons
- avoid duplicating raw logs into the experience library

## Safety / quality

If evidence is weak, mark the conclusion as observation.
If evidence conflicts with previous conclusions, explicitly note the conflict and keep both until revalidated.
