from bisect import bisect_right
from collections import Counter, defaultdict

from epub_alignment import AlignmentError, match_anchors, read_sections
from epub_assets import extract_assets


SCHEMA = "fitbaus.epub-visual-timing-preview/v1"
POLICY = "exact-anchor-bounds/v1"
MAX_INTERVAL_MS = 30000
MAX_SIDE_WORDS = 24
MIN_INSIDE_WORDS = 4


def evidence_for(position, anchors, starts):
    index = bisect_right(starts, position)
    left = anchors[index - 1] if index else None
    right = anchors[index] if index < len(anchors) else None
    if left is not None and left["ebook_word_start"] < position < left["ebook_word_end"]:
        before = position - left["ebook_word_start"]
        after = left["ebook_word_end"] - position
        if min(before, after) < MIN_INSIDE_WORDS:
            return None, "weak_inside_anchor"
        selected = [left]
        method = "within_exact_cue"
    else:
        if left is not None and left["ebook_word_start"] == position:
            right = left
            left = anchors[index - 2] if index >= 2 else None
        if left is None or right is None:
            return None, "missing_two_sided_anchor"
        if left["ebook_word_end"] > position or right["ebook_word_start"] < position:
            return None, "overlapping_anchor"
        if (position - left["ebook_word_end"] > MAX_SIDE_WORDS
                or right["ebook_word_start"] - position > MAX_SIDE_WORDS):
            return None, "distant_anchor"
        if right["cue_index"] != left["cue_index"] + 1:
            return None, "nonadjacent_cues"
        if left["end_ms"] > right["start_ms"]:
            return None, "invalid_anchor_order"
        selected = [left, right]
        method = "between_adjacent_exact_cues"
    start, end = selected[0]["start_ms"], selected[-1]["end_ms"]
    if not 0 <= start < end or end - start > MAX_INTERVAL_MS:
        return None, "wide_time_interval"
    return {"method": method, "earliest_ms": start, "latest_ms": end,
            "cue_indices": [anchor["cue_index"] for anchor in selected],
            "anchor_word_ranges": [[anchor["ebook_word_start"], anchor["ebook_word_end"]]
                                   for anchor in selected]}, None


def associate(catalogue, sections, alignment):
    section_map = {section.spine_index: section for section in sections}
    anchors_by_section = defaultdict(list)
    for anchor in alignment["anchors"]:
        section = section_map.get(anchor["spine_index"])
        if (section is None or anchor["path"] != section.path
                or not 0 <= anchor["ebook_word_start"] < anchor["ebook_word_end"] <= len(section.words)):
            raise AlignmentError("Anchor does not match reading-order projection")
        group = anchors_by_section[section.spine_index]
        if group and (group[-1]["ebook_word_end"] > anchor["ebook_word_start"]
                      or group[-1]["cue_index"] >= anchor["cue_index"]
                      or group[-1]["end_ms"] > anchor["start_ms"]):
            raise AlignmentError("Anchor order is invalid")
        group.append(anchor)
    starts = {index: [anchor["ebook_word_start"] for anchor in group]
              for index, group in anchors_by_section.items()}
    rows, reasons, methods = [], Counter(), Counter()
    for occurrence_index, occurrence in enumerate(catalogue["occurrences"]):
        index = occurrence["spine_index"]
        section = section_map.get(index)
        path = tuple(occurrence["figure_path"] if occurrence["figure_path"] is not None
                     else occurrence["node_path"])
        position = None
        if section is not None:
            if section.path != occurrence["document"]:
                raise AlignmentError("Visual does not match reading-order document")
            position = section.positions.get(path)
        if position is None:
            evidence, reason = None, "no_text_coordinate"
        else:
            evidence, reason = evidence_for(position, anchors_by_section[index], starts.get(index, []))
        row = {**occurrence, "occurrence_index": occurrence_index, "ebook_word_position": position,
               "evidence": evidence, "untimed_reason": reason}
        rows.append(row)
        if evidence is None:
            reasons[reason] += 1
        else:
            methods[evidence["method"]] += 1
    return {"occurrences": rows, "timed_count": sum(methods.values()),
            "untimed_count": sum(reasons.values()), "timing_methods": dict(methods),
            "untimed_reasons": dict(reasons)}


def collect_timing(stream, windows):
    catalogue = extract_assets(stream)
    locations = defaultdict(set)
    for occurrence in catalogue["occurrences"]:
        path = occurrence["figure_path"] if occurrence["figure_path"] is not None else occurrence["node_path"]
        locations[occurrence["spine_index"]].add(tuple(path))
    inventory, sections = read_sections(stream, locations=locations)
    if inventory["sha256"] != catalogue["epub_sha256"]:
        raise AlignmentError("EPUB changed during timing preview")
    alignment = match_anchors(sections, windows)
    result = associate(catalogue, sections, alignment)
    return {"schema": SCHEMA, "policy": POLICY, "epub_sha256": inventory["sha256"],
            "transcript_sha256": alignment["transcript_sha256"],
            "edition_verified": False, "render_qualified": False, "playback_qualified": False,
            "cue_count": alignment["cue_count"], "matched_cue_count": alignment["matched_cue_count"],
            "occurrence_count": catalogue["occurrence_count"], "unique_asset_count": catalogue["unique_asset_count"],
            "skipped_count": catalogue["skipped_count"], "assets": catalogue["assets"], **result}


def preview_timing(stream, windows):
    result = collect_timing(stream, windows)
    result.pop("assets")
    return result
