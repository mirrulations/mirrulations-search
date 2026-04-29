"""Normalize docket-ID-shaped search queries to hyphen-uppercase form."""
import re

_RULE_STAGES = {"P", "F", "IFC", "N", "CN", "D"}

# Restricting years to 19xx/20xx is what lets CMS-9115-F parse as a rule
# code instead of being mistaken for a YYYY-prefixed regulations.gov ID.
_YEAR_RE = re.compile(r"^(19|20)\d{2}$")
_SEGMENT_RE = re.compile(r"^[A-Z0-9]{1,6}$")
_SPLIT_RE = re.compile(r"[-_\s]+")


def _split_segments(query):
    segments = [s for s in _SPLIT_RE.split(query.strip().upper()) if s]
    if len(segments) < 2 or len(segments) > 6:
        return None
    if not all(_SEGMENT_RE.match(s) for s in segments):
        return None
    if not segments[0].isalpha():
        return None
    return segments


def _is_regulations_gov_format(segments):
    return any(_YEAR_RE.match(s) for s in segments[1:])


def _is_rule_code_format(segments):
    if len(segments) == 2:
        return segments[1].isdigit()
    if len(segments) == 3:
        return segments[1].isdigit() and segments[2] in _RULE_STAGES
    return False


def normalize_docket_id(query):
    """Return canonical AGENCY-...-NNNN form, or None if not docket-shaped."""
    if not query:
        return None
    segments = _split_segments(query)
    if segments is None:
        return None
    if _is_regulations_gov_format(segments) or _is_rule_code_format(segments):
        return "-".join(segments)
    return None


def looks_like_docket_id(query):
    return normalize_docket_id(query) is not None
