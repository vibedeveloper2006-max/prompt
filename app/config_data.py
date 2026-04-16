"""
config_data.py
--------------
Structured ground-truth data for the Event Assistant chatbot.

Design rule: If an event policy or venue detail is NOT listed here, the
chatbot must not invent it.  Gemini is used only to phrase the answer.
"""

EVENT_INFO = {
    "event_name": "StadiumChecker Cup 2026",
    "sport": "Football",
    "venue": "National Stadium",
    "date": "Saturday, 12 September 2026",
    "gates_open_time": "17:00",
    "kick_off_time": "19:30",
    "estimated_end_time": "21:30",
    "key_phases": [
        "Gates open: 17:00 – 19:00 (pre-match entry)",
        "Kick-off: 19:30 (live match begins)",
        "Half-time: approx. 20:15 – 20:30 (15 min interval)",
        "Full-time: approx. 21:30",
        "Post-match exit: 21:30 – 22:30 (staggered exit by zone)",
    ],
    "home_team": "City FC",
    "away_team": "United Rangers",
    "capacity": 50000,
}

VENUE_POLICY = {
    "prohibited_items": [
        "Weapons or sharp objects of any kind",
        "Glass bottles or containers",
        "Alcohol (stadium operates under a dry policy for this fixture)",
        "Flares, fireworks, smoke bombs, or pyrotechnics",
        "Flag poles or banner poles longer than 1 metre",
        "Laser pointers or strobe devices",
        "Drones or remotely piloted aircraft",
        "Large umbrellas (compact collapsible umbrellas are permitted)",
        "Selfie sticks or monopods",
        "Outside food or hot beverages",
        "Professional camera equipment (no detachable lenses above 100 mm)",
    ],
    "allowed_items": [
        "Clear plastic bags up to 30 cm × 20 cm × 10 cm",
        "One small clutch bag or purse (max A4 size)",
        "Sealed, factory-capped plastic water bottles (up to 500 ml)",
        "Medical equipment and prescription medication (with letter from GP)",
        "Compact collapsible umbrella",
        "Hearing aids and cochlear implants",
        "Baby changing supplies in a clear bag",
        "Fan scarves, hats, and replica shirts",
    ],
    "bag_policy": (
        "A strict clear bag policy is in effect. You may bring one clear plastic, "
        "vinyl, or PVC bag no larger than 30 cm × 20 cm × 10 cm, plus one small "
        "clutch bag or purse the size of an A4 sheet. All bags are subject to search "
        "at the gate. Non-compliant bags will not be stored — they must be returned "
        "to your vehicle or handed to someone outside the ground."
    ),
    "re_entry_rules": (
        "Re-entry is NOT permitted once you have exited the stadium during the match. "
        "If you have a medical emergency or operational need, speak to a steward at "
        "the nearest gate before exiting. Re-entry tokens are available only in "
        "extraordinary circumstances at the discretion of the duty manager."
    ),
    "restricted_areas": (
        "Away supporters are allocated the North Stand (Gate C). Home supporters "
        "must not enter the North Stand. The Media Zone near Corridor 2 is restricted "
        "to accredited press only. Hospitality boxes require a printed hospitality "
        "pass in addition to your match ticket. Pitch-side areas are strictly "
        "restricted to match officials and club staff."
    ),
    "accessibility_services": [
        "Wheelchair spaces and companion seats are available in all four stands — "
        "book in advance via the accessibility team (access@nationalstadium.example.com).",
        "Ambulant disabled seating is located on rows 1–3 of each stand with step-free access.",
        "Sensory-friendly quiet areas are available inside Gate A and Gate B concourses.",
        "Assistive listening loop systems cover the main public address areas.",
        "Sign language interpretation is available on request — contact the stadium "
        "at least 72 hours in advance.",
        "All gates, concourses, restrooms, and the Food Court are wheelchair-accessible.",
        "Mobility scooters may be used in designated areas — ask a steward on arrival.",
        "Personal assistance dogs are welcome throughout the venue.",
        "Large-print and audio programmes are available from the Information Desk near Gate A.",
    ],
    "ticket_guidance": (
        "Match tickets are digital only. Have your QR code ready on your phone before "
        "joining the gate queue. Paper print-outs are accepted only if pre-arranged "
        "with the box office. Season ticket holders use their membership card."
    ),
    "first_aid": (
        "First-aid stations are located at the Gate A concourse, Gate B concourse, "
        "and pitch-side near Corridor 3. Defibrillators are positioned at every gate "
        "entrance and at the Main Restroom block. For emergencies, flag down any "
        "steward — they can summon medical staff within 90 seconds."
    ),
    "lost_property": (
        "Lost property found before the match is held at the Information Desk near "
        "Gate A. Items found after the match are logged and held for 28 days. "
        "Contact lost.property@nationalstadium.example.com to report or claim items."
    ),
}
