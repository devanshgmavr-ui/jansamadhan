"""Deterministic development provider. Rule-based, no network, no randomness.

Used whenever no real AI key is configured. Every decision path is fixed so
Stage 5 verification is repeatable. Replaceable via the AIProvider protocol.
"""

import re

from app.services.ai.provider import (
    AIChecks,
    AIDecision,
    AIArea,
    AIReviewInput,
    AIReviewOutput,
    AIScope,
    DupRelation,
    SimilarRef,
)

PERSONAL_PATTERNS = [
    r"\bi lost my\b",
    r"\blost my (phone|laptop|wallet|bag|keys|bike)\b",
    r"\bmy (phone|laptop|wallet|house|bike|car) (is|was|got|has)\b",
    r"\bforgot my password\b",
    r"\bmy salary\b",
    r"\bmy personal\b",
]

# Generalized personal-conflict signals (not exact-phrase blacklists).
CONFLICT_VERBS = {
    "fight", "fights", "fighting", "fought", "argue", "argues", "arguing",
    "argued", "argument", "arguments", "dispute", "disputes", "disputed",
    "quarrel", "quarrels", "complaint", "complain", "complaining",
    "revenge", "retaliation", "feud", "harass", "harassing", "threaten",
    "refuse", "refuses", "refused", "refusing", "borrow", "borrowed",
    "owe", "owes", "owed", "owing", "debt", "debts", "lend", "lent",
    "stole", "stolen", "steal", "stealing", "cheat", "cheated", "cheating",
    "betray", "betrayed", "scam", "scammed",
}
# Specific individual counterparties (singular persons, incl. possessives).
CONFLICT_PARTIES = {
    "neighbour", "neighbor", "friend", "relative", "brother", "sister",
    "mother", "father", "cousin", "colleague", "landlord", "tenant",
    "partner", "husband", "wife", "boyfriend", "girlfriend", "roommate",
    "boss", "in-law",
}
# Possessive-private construction: "my <personal-domain noun>". Generalized
# grammatical shape, not exact phrases. Exempt when collective framing shows
# a genuinely shared issue (checked by callers via COLLECTIVE/AFFECTED words).
POSSESSIVE_PRIVATE = {
    "scooter", "bike", "motorcycle", "moped", "car", "vehicle",
    "landlord", "rent", "room", "dog", "cat", "pet", "pets",
    "wallet", "salary", "house", "home", "phone", "laptop", "computer",
    "commute", "exam", "exams", "grade", "grades",
}
# Plural/collective framing that signals a community dimension instead.
COLLECTIVE_NOUNS = {
    "residents", "community", "communities", "villagers", "students",
    "children", "families", "farmers", "workers", "citizens", "population",
    "households", "patients", "commuters", "shoppers", "vendors", "public",
    "people of", "members of",
}

# Generalized impossibility signals: demands to command natural phenomena
# or physically impossible outcomes. Matched as verb-governs-target within a
# short window so varied phrasings are caught, not just one sentence.
IMPOSSIBLE_TARGETS = {
    "rain", "rainfall", "monsoon", "weather", "storm", "storms", "cyclone",
    "cloud", "clouds", "sun", "moon", "earthquake", "earthquakes", "gravity",
    "time", "season", "seasons", "ocean", "tide", "tides", "volcano",
    "lightning", "thunder", "floods",
}
CONTROL_VERBS = {
    "stop", "stops", "stopping", "control", "controls", "controlling",
    "redirect", "remove", "removes", "eliminate", "eliminates", "prevent",
    "prevents", "change", "changes", "move", "moves", "reverse", "reverses",
    "halt", "halts", "block", "blocks", "ban", "bans",
}
FANTASY_MARKERS = [
    "magic", "miracle", "miracles", "spell", "spells", "superpower",
    "superpowers", "time travel", "time machine", "resurrect",
    "back to life", "back from the dead", "immortal", "immortality",
    "invisible cloak",
]
# Concrete actionability signals: if the requested solution names any of
# these, the demand is treated as an ambitious-but-actionable framing and is
# NOT flagged as impossible (e.g. flood control through drainage).
ACTIONABLE_KEYWORDS = {
    "build", "install", "program", "system", "systems", "plan", "plans",
    "policy", "policies", "drainage", "monitoring", "repair", "repairs",
    "network", "training", "storage", "infrastructure", "campaign",
    "regulation", "regulations", "fund", "funding", "scheme", "clinic",
    "school", "shelter", "bridge", "filter", "filters", "treatment",
    "vaccine", "vaccination", "irrigation", "shelter", "embankment",
    "warning", "warnings", "relief", "rescue", "preparedness",
}

CATEGORY_KEYWORDS: list[tuple[str, list[str]]] = [
    ("Education", ["school", "student", "teacher", "college", "education", "classroom", "exam", "tuition", "literacy", "internship"]),
    ("Healthcare", ["health", "hospital", "clinic", "doctor", "patient", "disease", "medicine", "vaccine", "sanitation", "nutrition"]),
    ("Agriculture", ["farm", "crop", "farmer", "irrigation", "agriculture", "harvest", "soil", "monsoon"]),
    ("Environment", ["pollution", "waste", "plastic", "climate", "forest", "river", "environment", "garbage", "recycling"]),
    ("Water", ["water", "drinking", "groundwater", "rainwater", "tap", "borewell"]),
    ("Energy", ["electricity", "power", "solar", "energy", "outage", "grid"]),
    ("Transportation", ["traffic", "road", "bus", "transport", "commute", "railway", "footpath", "crossing"]),
    ("Employment", ["job", "employment", "unemployment", "livelihood", "wage", "worker"]),
    ("Accessibility", ["disability", "disabled", "wheelchair", "accessible", "accessibility", "braille"]),
    ("Infrastructure", ["bridge", "building", "drainage", "sewage", "infrastructure", "construction"]),
    ("Digital Services", ["internet", "digital", "mobile network", "connectivity", "online", "broadband"]),
    ("Safety", ["safety", "crime", "accident", "violence", "harassment", "theft", "unsafe"]),
]

TYPE_BY_CATEGORY = {
    "Education": "Access to Education",
    "Healthcare": "Public Health",
    "Agriculture": "Agricultural Livelihood",
    "Environment": "Environmental Quality",
    "Water": "Water Access",
    "Energy": "Energy Access",
    "Transportation": "Mobility",
    "Employment": "Livelihood",
    "Accessibility": "Inclusion",
    "Infrastructure": "Civic Infrastructure",
    "Digital Services": "Digital Access",
    "Safety": "Public Safety",
}

AFFECTED_KEYWORDS: list[tuple[str, list[str]]] = [
    ("Students", ["student", "school", "college", "exam", "internship"]),
    ("Farmers", ["farm", "crop", "farmer", "irrigation", "harvest"]),
    ("Children", ["child", "children", "kid", "playground"]),
    ("Senior Citizens", ["senior", "elderly", "old age", "pension"]),
    ("Persons with Disabilities", ["disability", "disabled", "wheelchair", "braille"]),
    ("Small Businesses", ["shop", "vendor", "small business", "market", "trader"]),
    ("Healthcare Workers", ["nurse", "doctor", "health worker", "asha"]),
]

TECH_KEYWORDS: list[tuple[str, list[str]]] = [
    ("Mobile", ["mobile", "app", "phone", "sms"]),
    ("Web", ["website", "web", "online", "portal", "internet"]),
    ("IoT", ["sensor", "iot", "meter", "monitoring"]),
    ("Data Analytics", ["data", "survey", "record", "tracking"]),
    ("AI/ML", ["ai", "machine learning", "prediction", "predict"]),
    ("Renewable Energy", ["solar", "wind", "biogas"]),
    ("Hardware", ["device", "hardware", "equipment", "machine"]),
]

STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
    "is", "are", "has", "have", "near", "every", "this", "that", "it",
}


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z]{3,}", text.lower())
    return {w for w in words if w not in STOPWORDS}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _kw_hit(text: str, keyword: str) -> bool:
    """Whole-word/phrase keyword hit on lowered text. Substring matching
    causes false anchors (e.g. 'farm' inside 'frameworks'), so boundaries
    are required. Generalized matching fix, not a phrase list."""
    return re.search(r"\b" + re.escape(keyword) + r"\b", text) is not None


def _has_personal_conflict(title: str, description: str, affected: str) -> bool:
    """Interpersonal dispute with a specific individual and no community
    framing. Generalized over verbs/parties; collective nouns exempt. Also
    catches possessive-private complaints ("my <personal-domain noun>") with
    no collective framing, e.g. vehicle breakdowns, landlord/rent issues,
    sick pets, personal property trouble."""
    text = f"{title} {description}".lower()
    words = re.findall(r"[a-z]+", text)
    framing = f"{affected} {description}".lower()
    # Only genuine group nouns exempt (residents, students, workers, ...).
    # Domain keywords (exam, school, farm, shop, ...) are not collective
    # framing: "my exam grades" stays personal even though "exam" is an
    # education word.
    collective = any(_kw_hit(framing, noun) for noun in COLLECTIVE_NOUNS)
    if any(f"my {noun}" in text for noun in POSSESSIVE_PRIVATE):
        if not collective:
            return True
    has_verb = any(v in words for v in CONFLICT_VERBS)
    if not has_verb:
        return False
    party_hit = any(
        p in words or f"my {p}" in text or f"our {p}" in text
        for p in CONFLICT_PARTIES
    )
    if not party_hit:
        return False
    if collective:
        return False
    return True


def _demands_impossible(title: str, description: str, solution: str) -> bool:
    """Demand that a natural phenomenon / physical impossibility itself be
    commanded away, with no actionable framing. Generalized verb-governs-target
    proximity, not exact phrases. Returns False when the requested solution
    names concrete actionable measures (ambitious-but-possible stays)."""
    text = f"{title} {description}".lower()
    if any(marker in text for marker in FANTASY_MARKERS):
        return True
    words = re.findall(r"[a-z]+", text)
    demanded = False
    for i, word in enumerate(words):
        if word in CONTROL_VERBS and any(
            t in words[i + 1 : i + 7] for t in IMPOSSIBLE_TARGETS
        ):
            demanded = True
            break
        if word in IMPOSSIBLE_TARGETS and any(
            v in words[max(0, i - 6) : i] for v in CONTROL_VERBS
        ):
            demanded = True
            break
    if not demanded:
        return False
    actionable = f"{solution} {description}".lower()
    if any(keyword in actionable for keyword in ACTIONABLE_KEYWORDS):
        return False
    return True


def _substance_signals(title: str, description: str, affected: str, location: str) -> dict:
    """Content signals distinguishing a thin-but-real problem from vacuous text."""
    blob = f"{title} {description} {affected} {location}".lower()
    distinct = _tokens(blob)
    has_digit = bool(re.search(r"\d", blob))
    has_category = any(
        _kw_hit(blob, keyword)
        for _, keywords in CATEGORY_KEYWORDS
        for keyword in keywords
    )
    has_group = any(
        _kw_hit(blob, keyword)
        for _, keywords in AFFECTED_KEYWORDS
        for keyword in keywords
    )
    return {
        "distinct": len(distinct),
        "has_digit": has_digit,
        "has_category": has_category,
        "has_group": has_group,
    }


GENERIC_FILLER = {
    "things", "thing", "something", "stuff", "good", "bad", "nowadays",
    "soon", "many", "much", "very", "really", "quite", "here", "there",
    "our", "their", "his", "her", "its", "people", "area", "areas",
    "situation", "situations", "issue", "issues", "problem", "problems",
    "should", "done", "not",
}

# Causal/mechanism connectives signalling an explained problem.
CAUSAL_MARKERS = [
    "because", "since", "due to", "causes", "cause", "causing", "caused",
    "leads to", "lead to", "results in", "result in", "forces", "force",
    "forcing", "makes it", "make it", "leaving", "leaves",
]

# Concrete condition nouns: specific real-world problems. A text naming one
# of these is communicating *something* concrete even without other anchors.
CONCRETE_CONDITIONS = {
    "shortage", "shortages", "outage", "outages", "breakdown", "breakdowns",
    "flood", "floods", "flooding", "drought", "droughts", "accident",
    "accidents", "crime", "crimes", "disease", "diseases", "pollution",
    "traffic", "garbage", "leakage", "leakages", "collapse", "delay",
    "delays", "closure", "closures", "contamination", "erosion", "blackout",
    "congestion", "pothole", "potholes", "mosquito", "mosquitoes", "stray",
    "broken", "repair", "repairs", "drain", "drains", "drainage",
    "embankment", "landslide", "fire", "fires", "theft", "thefts",
    "violence", "harassment", "mosquitoes",
}

# Shared structured guidance for submissions that need more information.
MISSING_INFO_GUIDANCE = [
    "What is the actual issue? Describe the concrete situation.",
    "Who is affected? Name the group and approximate numbers.",
    "Where does it occur? Give a specific place or area.",
    "What impact does it have on those affected?",
    "What evidence or context supports this (observations, reports)?",
    "What outcome is needed from a solution?",
]

# Locations too generic to count as context on their own.
GENERIC_PLACES = {
    "", "area", "here", "home", "our area", "our locality", "locality",
    "somewhere", "anywhere", "everywhere", "my area", "this place",
    "around here", "our town",
}

# Solution texts too generic to count as a desired outcome on their own.
GENERIC_SOLUTIONS = {
    "fix it", "help me", "make things better", "do something",
    "solve it", "fix them", "improve things", "take action",
}


def _concrete_condition_present(title: str, description: str) -> bool:
    blob = f"{title} {description}".lower()
    words = set(re.findall(r"[a-z]+", blob))
    return bool(words & CONCRETE_CONDITIONS)


def _causal_with_substance(title: str, description: str) -> bool:
    """A causal/mechanistic account whose effect names something concrete
    (digits, domain vocabulary, group vocabulary or a concrete condition).
    Bare 'causing dissatisfaction' does not count."""
    words = re.findall(r"[a-z]+", f"{title} {description}".lower())
    for i, word in enumerate(words):
        window = " ".join(words[i : i + 9])
        if not any(marker in window for marker in CAUSAL_MARKERS):
            continue
        effect = " ".join(words[i : i + 11])
        if re.search(r"\d", effect):
            return True
        effect_words = set(re.findall(r"[a-z]+", effect))
        if effect_words & CONCRETE_CONDITIONS:
            return True
        for _, keywords in list(CATEGORY_KEYWORDS) + list(AFFECTED_KEYWORDS):
            if any(_kw_hit(effect, keyword) for keyword in keywords):
                return True
    return False


def _has_problem_structure(
    title: str, description: str, affected: str, location: str, solution: str
) -> bool:
    """Does the submission communicate a recognizable problem: a concrete
    condition, a substantiated causal account, a specific place combined with
    a substantive desired outcome? Generalized structural signals, not phrases."""
    if _concrete_condition_present(title, description):
        return True
    if _causal_with_substance(title, description):
        return True
    if location.strip().lower() not in GENERIC_PLACES:
        meaningful = [
            word
            for word in re.findall(r"[a-z]{3,}", solution.lower())
            if word not in STOPWORDS and word not in GENERIC_FILLER
        ]
        if len(meaningful) >= 4 and solution.strip().lower() not in GENERIC_SOLUTIONS:
            return True
    return False


def _is_vacuous(
    title: str, description: str, affected: str, location: str, solution: str = ""
) -> bool:
    """Long enough to pass length checks but communicating no usable problem:
    no concrete anchors (digits, domain vocabulary, affected-group vocabulary)
    and (very few distinct words, filler-dominated text, or no recognizable
    problem structure at all)."""
    signals = _substance_signals(title, description, affected, location)
    if signals["has_digit"] or signals["has_category"] or signals["has_group"]:
        return False
    if signals["distinct"] < 14:
        return True
    blob = f"{title} {description} {affected} {location}".lower()
    words = re.findall(r"[a-z]{3,}", blob)
    if not words:
        return True
    filler = sum(1 for word in words if word in GENERIC_FILLER)
    if filler / len(words) >= 0.4:
        return True
    return not _has_problem_structure(title, description, affected, location, solution)


def _short_but_substantive(
    title: str, description: str, affected: str, location: str, solution: str
) -> bool:
    """Brief (40-99 chars) yet anchored description that already communicates
    a concrete problem structure (e.g. a substantiated causal account naming
    a real group or domain). Such shorts skip the thin-text path and go
    through normal classification instead of being bounced for length."""
    if not 40 <= len(description.strip()) < 100:
        return False
    signals = _substance_signals(title, description, affected, location)
    if not (signals["has_digit"] or signals["has_category"] or signals["has_group"]):
        return False
    return _has_problem_structure(title, description, affected, location, solution)


class MockAIProvider:
    name = "mock"

    def review(self, data: AIReviewInput) -> AIReviewOutput:
        blob = " ".join([
            data.title, data.description, data.affected_group,
            data.desired_solution_type, data.supporting_info or "",
        ])
        low = blob.lower()

        for pattern in PERSONAL_PATTERNS:
            if re.search(pattern, low):
                return AIReviewOutput(
                    checks=AIChecks(
                        understandable=True,
                        sufficient_info=len(data.description.strip()) >= 40,
                        solvable=False,
                        duplicate_status=DupRelation.DISTINCT,
                        problem_type="Personal Issue",
                        affected_group="Individual",
                        geo_context=AIArea.GENERAL,
                        category="Other",
                        tags=["personal", "not-societal"],
                    ),
                    decision=AIDecision.NOT_SOCIETAL,
                    reason=(
                        "The submission describes a personal or private issue "
                        "affecting one individual rather than a societal problem "
                        "suitable for collaborative problem solving."
                    ),
                    scope=AIScope.INDIVIDUAL,
                    tech_areas=[],
                )

        if _has_personal_conflict(
            data.title, data.description, data.affected_group
        ):
            return AIReviewOutput(
                checks=AIChecks(
                    understandable=True,
                    sufficient_info=True,
                    solvable=False,
                    duplicate_status=DupRelation.DISTINCT,
                    problem_type="Interpersonal Dispute",
                    affected_group="Individual",
                    geo_context=AIArea.GENERAL,
                    category="Other",
                    tags=["personal", "not-societal"],
                ),
                decision=AIDecision.NOT_SOCIETAL,
                reason=(
                    "The submission describes a dispute between specific "
                    "individuals rather than a societal problem. If the same "
                    "issue affects a wider community (for example, many "
                    "residents facing unorganized parking), please resubmit "
                    "describing the community-level problem."
                ),
                scope=AIScope.INDIVIDUAL,
                tech_areas=[],
            )

        if _demands_impossible(
            data.title, data.description, data.desired_solution_type
        ):
            return AIReviewOutput(
                checks=AIChecks(
                    understandable=True,
                    sufficient_info=True,
                    solvable=False,
                    duplicate_status=DupRelation.DISTINCT,
                    problem_type="Inactionable Demand",
                    affected_group=data.affected_group.strip()[:120] or "Unknown",
                    geo_context=AIArea.GENERAL,
                    category=data.category.strip()[:60] or "Other",
                    tags=["needs-information"],
                ),
                decision=AIDecision.NEEDS_INFORMATION,
                reason=(
                    "The submission asks for an outcome that cannot be achieved "
                    "through problem-solving (such as commanding natural "
                    "phenomena). Please reframe it around actions people, "
                    "institutions or technology can realistically take."
                ),
                missing_info=[
                    "Describe what can realistically be done about this issue "
                    "(for example: protection, early warning, infrastructure, "
                    "planning or relief measures) instead of the impossible outcome.",
                    "Describe who is affected and the approximate number of people.",
                ],
                scope=AIScope.COMMUNITY,
                tech_areas=[],
            )

        missing: list[str] = []
        if len(data.description.strip()) < 100:
            missing.append(
                "The description is too brief. Please describe the current "
                "situation, who is affected and the expected outcome in detail."
            )
        if len(data.affected_group.strip()) < 5:
            missing.append(
                "The affected group is unclear. Please describe who is affected "
                "and the approximate number of people."
            )
        if len(data.title.strip()) < 15:
            missing.append(
                "The title is too short. Please give a clear, specific title."
            )
        if missing and not _short_but_substantive(
            data.title,
            data.description,
            data.affected_group,
            data.location,
            data.desired_solution_type,
        ):
            return AIReviewOutput(
                checks=AIChecks(
                    understandable=len(data.description.strip()) >= 40,
                    sufficient_info=False,
                    solvable=True,
                    duplicate_status=DupRelation.DISTINCT,
                    problem_type="Under-specified",
                    affected_group=data.affected_group.strip()[:120] or "Unknown",
                    geo_context=AIArea.GENERAL,
                    category=data.category.strip()[:60] or "Other",
                    tags=["needs-information"],
                ),
                decision=AIDecision.NEEDS_INFORMATION,
                reason=(
                    "The submission is understandable but lacks the information "
                    "needed to classify it and open it for solutions."
                ),
                missing_info=missing + MISSING_INFO_GUIDANCE,
                scope=AIScope.COMMUNITY,
                tech_areas=[],
            )

        if _is_vacuous(
            data.title,
            data.description,
            data.affected_group,
            data.location,
            data.desired_solution_type,
        ):
            return AIReviewOutput(
                checks=AIChecks(
                    understandable=False,
                    sufficient_info=False,
                    solvable=True,
                    duplicate_status=DupRelation.DISTINCT,
                    problem_type="Under-specified",
                    affected_group=data.affected_group.strip()[:120] or "Unknown",
                    geo_context=AIArea.GENERAL,
                    category=data.category.strip()[:60] or "Other",
                    tags=["needs-information"],
                ),
                decision=AIDecision.NEEDS_INFORMATION,
                reason=(
                    "The submission does not communicate a usable problem yet."
                ),
                missing_info=[
                    "What is the actual issue? Describe the concrete situation.",
                    "Who is affected? Name the group and approximate numbers.",
                    "Where does it occur? Give a specific place or area.",
                    "What impact does it have on those affected?",
                    "What evidence or context supports this (observations, reports)?",
                    "What outcome is needed from a solution?",
                ],
                scope=AIScope.COMMUNITY,
                tech_areas=[],
            )

        category = "Other"
        for cat, keywords in CATEGORY_KEYWORDS:
            if any(_kw_hit(low, k) for k in keywords):
                category = cat
                break
        affected = "General Public"
        for group, keywords in AFFECTED_KEYWORDS:
            if any(_kw_hit(low, k) for k in keywords):
                affected = group
                break
        if _kw_hit(low, "rural") or _kw_hit(low, "village"):
            area = AIArea.RURAL
        elif _kw_hit(low, "urban") or _kw_hit(low, "city"):
            area = AIArea.URBAN
        elif _kw_hit(low, "semi-urban") or _kw_hit(low, "town"):
            area = AIArea.SEMI_URBAN
        else:
            area = AIArea.GENERAL
        if any(_kw_hit(low, k) for k in ("school", "college", "hospital")):
            scope = AIScope.INSTITUTION
        elif any(_kw_hit(low, k) for k in ("district", "region", "state")):
            scope = AIScope.REGIONAL
        elif any(_kw_hit(low, k) for k in ("country", "national", "india")):
            scope = AIScope.NATIONAL
        elif any(_kw_hit(low, k) for k in ("family", "families", "household")):
            scope = AIScope.FAMILY
        else:
            scope = AIScope.COMMUNITY
        techs = [t for t, keywords in TECH_KEYWORDS if any(_kw_hit(low, k) for k in keywords)][:4]
        if not techs:
            techs = ["Web"]
        tag_words = sorted(_tokens(data.title + " " + data.category))[:6]
        tags = tag_words or [category.lower()]

        mine_title = _tokens(data.title)
        mine_desc = _tokens(data.description)
        similar: list[SimilarRef] = []
        scored = []
        for cand in data.candidates:
            if cand.get("ticket") == data.ticket:
                continue
            score = max(
                _jaccard(mine_title, _tokens(cand.get("title", ""))),
                _jaccard(mine_desc, _tokens(cand.get("description", ""))),
            )
            if cand.get("category") == category:
                score += 0.15
            scored.append((score, cand))
        scored.sort(key=lambda x: x[0], reverse=True)
        for score, cand in scored[:3]:
            if score >= 0.8:
                rel = DupRelation.DUPLICATE
            elif score >= 0.45:
                rel = DupRelation.SIMILAR
            else:
                continue
            similar.append(SimilarRef(ticket=cand["ticket"], relation=rel))
        dup_status = similar[0].relation if similar else DupRelation.DISTINCT

        return AIReviewOutput(
            checks=AIChecks(
                understandable=True,
                sufficient_info=True,
                solvable=True,
                duplicate_status=dup_status,
                problem_type=TYPE_BY_CATEGORY.get(category, "General"),
                affected_group=affected,
                geo_context=area,
                category=category,
                tags=tags,
            ),
            decision=AIDecision.APPROVED,
            reason=(
                f"The submission describes a clear societal problem in {category} "
                f"affecting {affected}, with enough detail to classify and open "
                "it for collaborative solutions."
            ),
            scope=scope,
            tech_areas=techs,
            similar=similar,
        )
