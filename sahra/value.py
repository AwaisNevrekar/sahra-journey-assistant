"""Value model shared by the dashboard and VALUE_ESTIMATE.md. Every input is an explicit, editable assumption."""
import math

DEFAULTS = {
    "pax_per_day": 25000,          # brief
    "departing_share": 0.50,       # half of terminal throughput are departures
    "desk_contact_rate": 0.04,     # 4% of passengers ask the info desk (assumption)
    "handle_min": 2.5,             # average desk handling time per question, minutes (assumption)
    "repetitive_share": 0.70,      # gate / delay / baggage / walking / facilities / published rules (assumption)
    "self_serve_rate": 0.80,       # of those, share fully answered by the assistant (assumption; T01-T21 basis)
    "desk_staff": 6,               # brief
    "agents_at_peak": 5,           # agents actually at the counter in the busiest hour (breaks, shifts) (assumption)
    "peak_hour_share": 0.10,       # share of daily desk questions in the busiest hour (assumption)
    "missed_rate": 0.0012,         # departing pax who miss boarding for gate/timing-information reasons (assumption)
    "opt_in": 0.40,                # pax who opt in to WhatsApp/SMS/app alerts (assumption)
    "nudge_effect": 0.60,          # of reached at-risk pax, share who then make boarding (assumption)
    "cost_missed_aed": 600,        # rebooking, re-handling bags, desk time, goodwill per missed boarding (assumption)
    "staff_cost_aed_hr": 60,       # loaded hourly cost of a desk agent (assumption)
}


def erlang_c_wait(lam, mu, c):
    """Mean queue wait (minutes) for an M/M/c desk. lam, mu per hour."""
    rho = lam / (c * mu)
    if rho >= 1:
        return float("inf")
    a = lam / mu
    s = sum(a ** k / math.factorial(k) for k in range(c))
    top = a ** c / math.factorial(c) / (1 - rho)
    pw = top / (s + top)
    return pw / (c * mu - lam) * 60


def estimate(**kw):
    p = {**DEFAULTS, **kw}
    desk_q = p["pax_per_day"] * p["desk_contact_rate"]
    handled = desk_q * p["repetitive_share"] * p["self_serve_rate"]
    staff_hours = handled * p["handle_min"] / 60
    mu = 60 / p["handle_min"]
    lam_before = desk_q * p["peak_hour_share"]
    lam_after = (desk_q - handled) * p["peak_hour_share"]
    departing = p["pax_per_day"] * p["departing_share"]
    missed = departing * p["missed_rate"]
    avoided = missed * p["opt_in"] * p["nudge_effect"]
    return {
        "desk_questions_per_day": round(desk_q),
        "handled_by_assistant_per_day": round(handled),
        "desk_load_reduction_pct": round(100 * handled / desk_q),
        "staff_hours_saved_per_day": round(staff_hours, 1),
        "staff_shifts_freed_per_day": round(staff_hours / 8, 1),
        "peak_wait_before_min": round(erlang_c_wait(lam_before, mu, p["agents_at_peak"]), 1),
        "peak_wait_after_min": round(erlang_c_wait(lam_after, mu, p["agents_at_peak"]), 1),
        "peak_queue_before_people": round(lam_before * erlang_c_wait(lam_before, mu, p["agents_at_peak"]) / 60, 1),
        "peak_queue_after_people": round(lam_after * erlang_c_wait(lam_after, mu, p["agents_at_peak"]) / 60, 1),
        "peak_utilisation_before_pct": round(100 * lam_before / (mu * p["agents_at_peak"])),
        "peak_utilisation_after_pct": round(100 * lam_after / (mu * p["agents_at_peak"])),
        "missed_boardings_per_day": round(missed, 1),
        "missed_boardings_avoided_per_day": round(avoided, 1),
        "missed_boardings_avoided_per_year": round(avoided * 365),
        "annual_staff_value_aed": round(staff_hours * 365 * p["staff_cost_aed_hr"], -3),
        "annual_missed_boarding_value_aed": round(avoided * 365 * p["cost_missed_aed"], -3),
        "inputs": p,
    }


if __name__ == "__main__":
    for k, v in estimate().items():
        if k != "inputs":
            print(f"{k:38} {v}")
