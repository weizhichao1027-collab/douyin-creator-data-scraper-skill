# Douyin Account Traffic Diagnosis Checklist

Use this reference when the user asks why a Douyin account's recent traffic dropped, why videos are stuck around a threshold, or what content should be changed next. Prefer the latest CSV produced by the scraper over a fresh scrape unless the user explicitly wants fresh data.

## Build Comparison Groups First

- Recent low-traffic works: plays, completion/retention metrics when present, interactions, title, cover, publish time, topic type, comment feedback.
- Historical high-performing works: same fields, then identify structures that can be reused.
- Do not judge only from one weak recent video. State what the low-performing group lacks relative to the high-performing group.

## Extra Checks For Group Accounts

For multi-person creator accounts, inspect relationship structure in addition to normal content metrics:

- Can viewers understand each person's role within the first 3 seconds?
- Is there still conflict, contrast, complementarity, teasing, or professional division of labor?
- Did the account drift from relationship-driven content into generic teaching, recording, or daily-life content?
- Is one member's presence too weak?
- Do comments still discuss the people and their relationships, or only generic content feedback?

## Video Structure

Review the first 3-5 seconds of weak videos:

- Does the opening immediately show a result, conflict, suspense, contrast, or benefit?
- Is there too much setup, greeting, or slow entry?
- Does the first screen have a clear subject and emotion?
- Does the title/cover match the opening promise?

## Topic And Account Tag

- Are recent topics repetitive, too narrow, or missing a broad emotional entry point?
- Are videos over-serving existing fans while increasing the comprehension cost for new viewers?
- Did the account drift away from past breakout tags?
- Did ads, daily records, or off-position experiments dilute the account's core expectation?

## Title And Cover

Titles and covers should create a reason to stop and click:

- Make the conflict explicit: who versus who, and what contrast happened?
- Make the payoff explicit: what emotion, information, or result will the viewer get?
- Make the target viewer explicit: students, parents, music learners, general viewers, or old fans.
- Avoid jokes that only insiders understand.

## Monthly And Seasonal Review

When asked about low months or seasonal patterns:

- Parse `发布日期` by month.
- For each active month calculate `发布条数`, `总播放`, `均播`, `中位数`, and `最高播放`.
- Identify bottom months by both total plays and average plays.
- Mark launch months, incomplete current months, and tiny-sample months as caveats.
- Do not rank months only by total plays because low publishing volume can make totals misleading.

## Recommended Output

Deliver:

1. One-sentence diagnosis with the most likely 1-2 causes.
2. Common traits of recent low-traffic works.
3. Common traits of historical high-performing works.
4. A difference table covering topic, opening, title/cover, relationship structure, comment feedback, and publish timing.
5. Prioritized fixes with the reason for each priority.
6. 10-20 next video ideas, each with an opening hook, role split if relevant, and title/cover direction.

## Avoid Weak Conclusions

Do not stop at:

- "Content quality dropped"
- "Account weight dropped"
- "The traffic pool is not recommending it"
- "Improve completion rate"

Only use those claims when they are backed by evidence and converted into a specific next-video change.
