"""Per-portal start URLs and natural-language goals for the TinyFish Agent API."""
from datetime import datetime, timedelta

from agents.schemas import IST

_COMMON = (
    "Today is {today}. Only keep bids closing on or after {min_close} (skip anything closing sooner). "
    "Relevance: keep a bid if its items/title name the same kind of product as '{category}', even when worded "
    "differently or more generally (for 'steel almirah' also keep 'Almirah', 'Steel Cupboard', "
    "'Almirah / Cabinets'; for 'storage rack' also keep 'Slotted Angle Rack', 'Metal Shelving Rack'); "
    "a later step ranks relevance, so when in doubt keep it. Skip only clearly different products, and "
    "never keep a bid just because the ministry, department or organisation name contains a search word. "
    "Return at most {limit} bids. "
    "If a captcha, OTP or login wall appears, do NOT try to solve it: stop immediately and "
    "return blocked=true with blocked_reason and an empty bids list. "
    "blocked is ONLY for captcha/login/site errors: if the site works but nothing relevant is found, "
    "return blocked=false and an empty bids list. "
    "This is read-only: never click submit, participate, or bid buttons. "
    "Copy values exactly as shown (end_date with its time, est_value in INR as shown); "
    "use absolute URLs for doc_url; use an empty string for anything not shown."
)

PORTALS = {
    "gem": {
        "url": "https://bidplus.gem.gov.in/all-bids",
        "goal": (
            "Type '{category}' into the bid search box and run the search once. "
            "If it returns no relevant bids, search once more using only the last word of '{category}' "
            "(e.g. 'rack'). Never run the same search twice, don't change the sort order, and don't open "
            "bid details or tooltips: read everything from the result cards. "
            "For each bid card read: bid_no (e.g. GEM/2026/B/1234567), "
            "title (the 'Items' text as shown on the card), item (the main product name), "
            "buyer (ministry and department), quantity, end_date (the 'End Date' value with time), "
            "doc_url (copy the exact href of the bid-number link, which opens the bid document and looks like "
            "https://bidplus.gem.gov.in/showbidDocument/1234567; never build or guess a URL, use an empty string "
            "if you can't read the href). "
            "Look through at most 2 result pages, then return what you have. " + _COMMON
        ),
    },
    "cppp": {
        "url": "https://eprocure.gov.in/eprocure/app",
        "goal": (
            "On the CPPP home page, read the 'Latest Tenders' box (it scrolls; wait for it to load) and find "
            "tenders related to '{category}' (match on title). Do NOT open 'Latest Active Tenders', "
            "'Tenders by Closing Date', 'Advanced Search' or any search box or form: they need a captcha. "
            "For each matching row read: bid_no (the tender reference number / tender ID), "
            "title, buyer (organisation name), end_date (bid submission closing date), "
            "doc_url (absolute link of the tender title). " + _COMMON
        ),
    },
    "haryana": {
        "url": "https://etenders.hry.nic.in/nicgep/app",
        "goal": (
            "On the Haryana e-procurement home page, open the 'Latest Tenders' list (use 'more' if shown) "
            "and find tenders related to '{category}' (match on title). Do NOT use any search box, "
            "'Advanced Search' or 'Tenders by Closing Date' form: they lead to a captcha. Use only the list's "
            "own next-page links, up to 3 pages. For each matching row read: "
            "bid_no (tender reference number or tender ID), title, buyer (department), "
            "end_date (closing date), doc_url (absolute link of the tender title). "
            + _COMMON
        ),
    },
}


# GeM lists closing-soonest first and the short goal doesn't re-sort (each sort costs steps), so a 2-day
# window dropped every card on pages 1-2 (live run 25 Oct: 686 results, 0 kept). Tomorrow onward still
# leaves a day to bid.
MIN_CLOSE_DAYS = 1


def goal_for(portal: str, category: str, limit: int = 10, min_days: int = MIN_CLOSE_DAYS) -> tuple[str, str]:
    p = PORTALS[portal]
    today = datetime.now(IST).date()
    goal = p["goal"].format(
        category=category, limit=limit, today=today.strftime("%d %b %Y"),
        min_close=(today + timedelta(days=min_days)).strftime("%d %b %Y"),
    )
    return p["url"], goal
