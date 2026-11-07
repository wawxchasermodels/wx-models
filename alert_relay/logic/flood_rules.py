# Copied unchanged from the box flood rules for the GitHub Actions relay.
"""USA page flood rules shared by watch.py, watch_quiet.py, post_alert.py and prepost_check.py.

10-24-26 10:50 PM PT (Benjamin): a USA Flash Flood Warning that mentions evacuations posts (FFW_EVAC=0 env turns it off).
10-25-26 11:48 AM PT (Benjamin): a USA regular Flood Warning (event "Flood Warning", river FL.W and areal FA.W) posts
  when it is forecast to reach MAJOR flood stage, or its text mentions catastrophic, emergency or evacuation language.
  Other USA Flood Warnings stay skipped. Washington page unchanged. FLOOD_USA=0 env turns it off.
10-26-26 11:40 AM PT (Benjamin): "If it is only minor flooding, skip and don't have the watcher wake you" (after the Rio Grande
  near Castolon minor Flood Warning posted because campers were told to prepare for evacuation). A USA Flood Warning whose
  text says MINOR flooding (WHAT line / "Flood Category: Minor") with NO moderate or major flooding occurring or forecast is
  skipped even if it mentions evacuation (minor_only()). Catastrophic or emergency wording still qualifies (treated as unclear),
  and mixed minor-now/moderate-or-major-forecast still qualifies. MINOR_SKIP=0 env turns this off.

api.weather.gov CAP has NO flood severity field for Flood Warnings (parameters are AWIPSidentifier, WMOidentifier,
NWSheadline, BLOCKCHANNEL, EAS-ORG, VTEC, expiredReferences; the H-VTEC severity code is not exposed, checked
10-25-26 on 15 live Flood Warnings), so major stage is read from the NWS text ("Major flooding is forecast",
"crest ... above major flood stage", "* WHAT...Major flooding ...", "Flood Category: Major")."""
import os, re

FLOOD_USA_ON = os.environ.get("FLOOD_USA", "1") != "0"
FFW_EVAC_ON = os.environ.get("FFW_EVAC", "1") != "0"
MINOR_SKIP_ON = os.environ.get("MINOR_SKIP", "1") != "0"

EVAC_RE = re.compile(r"EVACUAT", re.I)
CATA_RE = re.compile(r"CATASTROPHI", re.I)
# "emergency" counts except boilerplate: "emergency management/managers/services/officials/responders...",
# and NWS links like weather.gov/abq/EmergencyPrepFlood (URLs are stripped first).
EMERG_RE = re.compile(r"\bEMERGENC(?:Y|IES)\b(?!\s*(?:management|manager|managers|managment|mgmt|services?|officials?|responders?|"
                      r"personnel|crews?|operations?|ops|medical|vehicles?|prep\w*|alert system|broadcast|dispatch\w*|"
                      r"room|response|workers?|communications?))", re.I)
URL_RE = re.compile(r"\S*(?:https?://|www\.|\.gov/|\.com/|\.org/)\S*", re.I)

MAJOR_RE = re.compile(r"\bmajor\s+flood(?:ing|\s+stage|\s+category|\s+levels?)?\b|\bflood\s+category\W{0,3}major\b", re.I)
_NEG_BEFORE = re.compile(r"(?:\bbelow|\bunder|\bnot|\bno|\bnever|\bshort\s+of|\bapproach\w*|\bnear|\bnearing|\bwithout|\bnor|\bthan|"
                         r"\btowards?|\bfall\w*\s+(?:to|below|out\s+of)|\bdrop\w*\s+(?:to|below|out\s+of)|\bbelow)\W+(?:\w+\W+){0,3}$", re.I)
_DEF_AFTER = re.compile(r"^[ \t]*(?:stage[ \t]+)?(?:is|of)[ \t]+[\d.]+", re.I)   # "Major flood stage is 25.0 feet" (a definition, not a forecast)
_STAGE_IMPACT = re.compile(r"\bAt\s+[\d.]+\s+feet,[^\n]*", re.I)   # "* IMPACTS...At 25.0 feet, major flooding ..." stage table lines


def text_of(p):
    params = p.get("parameters") or {}
    parts = [p.get("headline") or "", p.get("description") or "", p.get("instruction") or ""]
    parts += params.get("NWSheadline") or []
    return " ".join(str(x) for x in parts)


def clean(text):
    return URL_RE.sub(" ", text or "")


def danger_words(text):
    """List of the matched catastrophic / emergency / evacuation words (boilerplate excluded)."""
    t = clean(text)
    out = []
    if CATA_RE.search(t): out.append("catastrophic")
    if EMERG_RE.search(t): out.append("emergency")
    if EVAC_RE.search(t): out.append("evacuation")
    return out


MODERATE_RE = re.compile(r"\bmoderate\s+flood(?:ing|\s+stage|\s+category|\s+levels?)?\b|\bflood\s+category\W{0,3}moderate\b", re.I)
MINOR_RE = re.compile(r"\bminor\s+flood(?:ing|\s+stage|\s+category|\s+levels?)?\b|\bflood\s+category\W{0,3}minor\b", re.I)
_WHAT_RE = re.compile(r"\*\s*WHAT\.\.\.(.*?)(?=\n\s*\n|\n\s*\*|$)", re.I | re.S)


def _stage_hit(text, rx):
    """True when rx (major/moderate/minor flooding wording) appears as occurring/forecast: stage-table lines
    ("At 25.0 feet, major flooding ..."), definitions ("Major flood stage is 25.0 feet") and negations are ignored."""
    t = _STAGE_IMPACT.sub(" ", clean(text))
    for m in rx.finditer(t):
        before = t[max(0, m.start() - 45):m.start()]
        after = t[m.end():m.end() + 30]
        if _NEG_BEFORE.search(before):
            continue
        if _DEF_AFTER.search(after) or re.match(r"\s+stage\s+(?:is|of)\s", after, re.I):
            continue
        return True
    return False


def major_stage(text):
    """True when the text says major flooding / major flood stage is occurring or forecast (negated mentions ignored)."""
    return _stage_hit(text, MAJOR_RE)


def moderate_stage(text):
    return _stage_hit(text, MODERATE_RE)


def minor_only(text):
    """10-26-26: True when the NWS severity is clearly MINOR only: the * WHAT... line (or "Flood Category: Minor") says minor
    flooding, and nothing anywhere says moderate or major flooding is occurring/forecast. Unclear or mixed -> False."""
    t = clean(text)
    whats = [m.group(1) for m in _WHAT_RE.finditer(t)]
    minor = any(MINOR_RE.search(w) for w in whats) or bool(re.search(r"\bflood\s+category\W{0,3}minor\b", t, re.I))
    if not minor:
        return False
    if any(re.search(r"\b(?:moderate|major)\s+flood", w, re.I) for w in whats):
        return False
    return not (major_stage(t) or moderate_stage(t))


def minor_skip_reason(p):
    """10-26-26 (Benjamin): reason string when a USA Flood Warning that would otherwise qualify (evacuation language) is
    skipped because it is only minor flooding; None otherwise. Catastrophic/emergency wording is never skipped here."""
    if not MINOR_SKIP_ON or (p.get("event") or "") != "Flood Warning":
        return None
    text = text_of(p)
    words = danger_words(text)
    if not words or not set(words) <= {"evacuation"} or major_stage(text):
        return None
    if minor_only(text):
        return "minor flooding only (evacuation language ignored, 10-26-26 rule)"
    return None


def flood_usa_reason(p, force=False):
    """Reason string if a regular Flood Warning qualifies for the USA page, else None. Does not look at WA scope."""
    if not (FLOOD_USA_ON or force):
        return None
    if (p.get("event") or "") != "Flood Warning":
        return None
    text = text_of(p)
    words = danger_words(text)
    if words and minor_skip_reason(p):
        return None    # 10-26-26 (Benjamin): only minor flooding -> skip even with evacuation language
    if words:
        return "Flood Warning with %s language" % "/".join(words)
    if major_stage(text):
        return "Flood Warning forecast to reach major flood stage"
    return None


def flood_usa_urgent(reason):
    """Catastrophic / emergency / evacuation Flood Warnings post any hour (like the FFW evacuation rule);
    major-stage-only ones wait out the USA overnight hold (9 PM to 2 AM PT)."""
    return bool(reason) and "language" in reason


def ffw_evac(p, force=False):
    if not (FFW_EVAC_ON or force):
        return False
    if (p.get("event") or "") != "Flash Flood Warning":
        return False
    return bool(EVAC_RE.search(clean(text_of(p))))


def vtec_key(p):
    """'KABQ.FL.W.0017' style event key from the P-VTEC string, or None."""
    for v in (p.get("parameters") or {}).get("VTEC") or []:
        m = re.search(r"/[OTEX]\.([A-Z]{3})\.([A-Z]{4})\.([A-Z]{2})\.([A-Z])\.(\d{4})\.", v)
        if m:
            return "%s.%s.%s.%s" % (m.group(2), m.group(3), m.group(4), m.group(5))
    return None


def vtec_action(p):
    for v in (p.get("parameters") or {}).get("VTEC") or []:
        m = re.search(r"/[OTEX]\.([A-Z]{3})\.", v)
        if m:
            return m.group(1)
    return None
