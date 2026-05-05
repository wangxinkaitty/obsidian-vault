---
created: 2026-05-06
last_updated: 2026-05-06
---

# Home

## Active projects

```dataview
TABLE status, priority, target_venue, deadline
FROM "Projects"
WHERE status = "active"
SORT priority desc, file.mtime desc
```

## Upcoming venue deadlines (next 60 days)

```dataview
TABLE deadline_dates as "Deadline", venue_type as "Type", priority
FROM "Venues"
WHERE deadline_dates AND date(deadline_dates) <= date(today) + dur(60 days) AND date(deadline_dates) >= date(today)
SORT deadline_dates asc
```

## Reading queue

```dataview
TABLE authors, year, venue
FROM "Notes/Papers"
WHERE read_status = "to-read"
SORT file.mtime desc
LIMIT 15
```

## High-priority researchers

```dataview
TABLE affiliation, h_index, fields_of_interest as "Fields"
FROM "Researchers"
WHERE priority = "high"
SORT file.mtime desc
```

## Recently updated

```dataview
LIST
FROM "Researchers" OR "Venues" OR "Projects" OR "Notes"
SORT file.mtime desc
LIMIT 10
```

## Open tasks

```tasks
not done
sort by due
limit 20
```

## Quick capture

(scratch space — anything you want to think about right now)