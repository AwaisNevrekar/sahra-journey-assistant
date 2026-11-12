# Value estimate — Sahra Journey Assistant

**Bottom line:** about **560 desk questions a day** answered without queueing, **~23 staff-hours a day** freed (≈ 3 desk shifts),
and **~1,300 missed boardings a year** avoided. Rough annual value: **≈ AED 1.3 million**.

All figures come from `sahra/value.py` and can be changed live in the dashboard (📈 Value tab). Inputs marked *assumption*
must be replaced with Sahra's own desk logs and gate data before any business case.

## 1. Desk questions handled

| Step | Input | Result |
|---|---|---|
| Passengers per day | 25,000 (brief) | |
| Share who ask the info desk | 4 % *(assumption)* | **1,000 questions/day** |
| Share that are repetitive (gate, delay, baggage belt, walking time, facilities, published rules) | 70 % *(assumption)* | 700 |
| Share of those the assistant fully resolves | 80 % *(assumption — in the test log, 9 of 21 cases need no human at all; the rest are deliberate hand-offs or approvals)* | **560/day handled** |

→ **56 % less desk load.** The remaining questions still reach staff — plus the ones the assistant deliberately hands over
(medical, assistance, conflicting data), which is the point.

## 2. Staff time saved

560 questions × 2.5 min average handling *(assumption)* = **1,400 min ≈ 23.3 staff-hours/day ≈ 2.9 eight-hour shifts.**
At AED 60/hour loaded cost *(assumption)* ≈ **AED 0.51 M/year**, better used for reduced-mobility passengers and real problems.

## 3. Desk queue

Busiest hour = 10 % of daily desk questions *(assumption)*, 5 agents at the counter *(assumption, from the 6 staff in the brief)*.
Standard M/M/c queue model:

| | Before | After |
|---|---|---|
| Peak arrivals / hour | 100 | 44 |
| Agent utilisation | 83 % | 37 % |
| Average people waiting | 3.1 | ~0 |

## 4. Missed boardings avoided

| Step | Input | Result |
|---|---|---|
| Departing passengers / day | 50 % of 25,000 | 12,500 |
| Miss boarding because of gate/timing information | 0.12 % *(assumption)* | **15/day** |
| Reachable (opted in to WhatsApp / SMS / app alerts) | 40 % *(assumption)* | 6 |
| Make boarding after gate-change broadcast or leave-now nudge | 60 % *(assumption)* | **3.6/day ≈ 1,314/year** |

At AED 600 per missed boarding (rebooking, bag re-handling, desk time, goodwill) *(assumption)* ≈ **AED 0.79 M/year**.

## How to prove it in a pilot (4 weeks, one pier)

1. Count desk questions by topic for 1 week before go-live (tally sheet or desk tablet).
2. Turn on the assistant for one pier; keep counting. Compare the topic mix and peak queue.
3. From the outbox, count gate-change broadcasts and nudges; from the airline, count no-shows at the gate for the same flights
   vs. the previous 4 weeks.
4. Replace every *assumption* above with the measured value in `sahra/value.py`.
