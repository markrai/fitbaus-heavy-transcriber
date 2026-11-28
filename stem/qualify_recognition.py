import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from types import MappingProxyType

from .corpus_model import ROOT, digest, load_corpus, mathematical_digest, read_json, recognition_digest, strict_object
from .dictionary import Dictionary, Entry, normalize_alias
from .matcher import MATCHER_VERSION, recognize

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
FIXTURE_SCHEMA = "fitbaus.stem.recitation-review-fixture/v1"
OBSERVED_SCHEMA = "fitbaus.stem.recognition-observations/v1"
REPORT_SCHEMA = "fitbaus.stem.recognition-qualification/v1"
HARNESS_VERSION = "2"
MAX_OBSERVED_BYTES = 16 * 1024 * 1024
MAX_CASES = 10000
MAX_TEXT = 32768
ROW_FIELDS = {"id", "mathematical_sha256", "latex", "aliases", "negative_phrases", "scope_review"}


@dataclass(frozen=True)
class Expected:
    id: str
    start: int
    end: int
    latex: str


@dataclass(frozen=True)
class Case:
    id: str
    group: str
    text: str
    expected: tuple[Expected, ...]


def fields(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError("Invalid fields: " + label)


def text_value(value, limit, label):
    if (not isinstance(value, str) or not value.strip() or len(value) > limit
            or any(0xD800 <= ord(char) <= 0xDFFF or char == "\x00" for char in value)):
        raise ValueError("Invalid text: " + label)
    return value


def build_review_dictionary(root=ROOT, fixtures=FIXTURES):
    concepts = load_corpus(root)
    representations = {
        concept["id"] + ":" + rep["id"]: (concept, rep)
        for concept in concepts for rep in concept["representations"]
    }
    paths = sorted(Path(fixtures).glob("stem_recitation_*.json"))
    if not paths:
        raise ValueError("No recitation review fixtures")
    rows, evidence, entries, aliases, ids = [], [], [], {}, set()
    for path in paths:
        if path.is_symlink():
            raise ValueError("Symlink review fixture: " + path.name)
        fixture = read_json(path)
        fields(fixture, {"schema", "qualification", "rows"}, path.name)
        if (fixture["schema"] != FIXTURE_SCHEMA or fixture["qualification"] != "scope_review_only"
                or not isinstance(fixture["rows"], list) or not fixture["rows"]):
            raise ValueError("Invalid review fixture: " + path.name)
        evidence.append({"file": path.name, "sha256": digest(fixture)})
        for row in fixture["rows"]:
            fields(row, ROW_FIELDS, path.name)
            key = row["id"]
            if not isinstance(key, str) or key not in representations or key in ids:
                raise ValueError("Unknown or duplicate representation in review fixture")
            concept, rep = representations[key]
            if (rep["mathematical_review"]["status"] != "approved"
                    or row["latex"] != rep["latex"]
                    or row["mathematical_sha256"] != mathematical_digest(concept, rep)
                    or not isinstance(row["aliases"], list) or not row["aliases"]
                    or sorted(row["aliases"]) != sorted(rep["spoken_aliases"])):
                raise ValueError("Stale or incomplete scope review: " + key)
            text_value(row["scope_review"], 4096, key)
            negatives = row["negative_phrases"]
            if not isinstance(negatives, list) or not negatives or len(negatives) > 256:
                raise ValueError("Missing or oversized negative examples: " + key)
            for phrase in negatives:
                text_value(phrase, 2048, key)
            if len(set(negatives)) != len(negatives):
                raise ValueError("Duplicate negative example: " + key)
            phrases = tuple(sorted(normalize_alias(alias) for alias in row["aliases"]))
            entry = Entry(key, concept["name"], concept["subject"], rep["latex"], phrases, "qualification-only")
            for phrase in phrases:
                if phrase in aliases:
                    raise ValueError("Ambiguous reviewed alias: " + phrase)
                aliases[phrase] = entry
            entries.append(entry)
            rows.append(row)
            ids.add(key)
    if ids != set(representations):
        raise ValueError("Scope review must cover the entire authoring corpus")
    entries.sort(key=lambda entry: entry.id)
    rows.sort(key=lambda row: row["id"])
    binding = {
        "authoring_sha256": digest(concepts),
        "source_registry_sha256": digest(read_json(Path(root) / "sources.json")),
        "fixtures": evidence,
        "recognition_digests": [
            {"id": key, "sha256": recognition_digest(*representations[key])} for key in sorted(ids)
        ],
    }
    dictionary = Dictionary(tuple(entries), MappingProxyType(aliases), digest(binding))
    return dictionary, rows, binding


def positive(case_id, group, entry, phrase, prefix="", suffix=""):
    return Case(case_id, group, prefix + phrase + suffix,
                (Expected(entry.id, len(prefix), len(prefix) + len(phrase), entry.latex),))


def synthetic_cases(dictionary, rows):
    entries = {entry.id: entry for entry in dictionary.entries}
    for row in rows:
        entry = entries[row["id"]]
        for index, alias in enumerate(entry.aliases):
            key = entry.id + ":alias:" + str(index)
            yield positive(key + ":plain", "authored_positive", entry, alias)
            yield positive(key + ":intro", "context_positive", entry, alias.upper(), "The formula is ", ".")
            yield positive(key + ":colon", "context_positive", entry, alias, "Equation: ", ".")
            yield positive(key + ":given_by", "context_positive", entry, alias, "The equation is given by ", ".")
            yield positive(key + ":unicode", "context_positive", entry, alias.replace(" ", "  "),
                           "Résumé of the chapter.  ", "! ")
            yield Case(key + ":prefix", "mutation_negative", "x plus " + alias, ())
            yield Case(key + ":suffix", "mutation_negative", alias + " plus one", ())
            yield Case(key + ":comma_suffix", "mutation_negative", alias + ", plus one.", ())
        for index, phrase in enumerate(row["negative_phrases"]):
            key = entry.id + ":negative:" + str(index)
            yield Case(key + ":plain", "authored_negative", phrase, ())
            yield Case(key + ":intro", "authored_negative", "The formula is " + phrase + ".", ())
    for first, second in zip(dictionary.entries, dictionary.entries[1:]):
        one, two = first.aliases[0], second.aliases[0]
        prefix = "The equation is "
        separator = ". The formula is "
        start_two = len(prefix) + len(one) + len(separator)
        yield Case(first.id + ":pair:" + second.id, "multi_match", prefix + one + separator + two + ".",
                   (Expected(first.id, len(prefix), len(prefix) + len(one), first.latex),
                    Expected(second.id, start_two, start_two + len(two), second.latex)))


def context_challenges(dictionary):
    for entry in dictionary.entries:
        alias = entry.aliases[0]
        for kind, text in (
            ("negated_intro", "It is not true that the formula is " + alias + "."),
            ("hypothetical_intro", "Suppose the incorrect formula is " + alias + "."),
            ("arbitrary_colon", "Unrelated text to ignore: " + alias + "."),
            ("nested_intro", "The formula is equation is " + alias + "."),
            ("negated_colon", "Incorrect equation: " + alias + "."),
            ("question", "The formula is " + alias + "?"),
            ("semicolon_suffix", alias + "; plus one."),
            ("newline_suffix", alias + "\nplus one."),
            ("period_continuation", alias + ". Plus one."),
            ("operator_continuation", alias + ". + one."),
            ("incomplete_prefix", "x plus. " + alias + "."),
            ("ellipsis", alias + "..."),
            ("attached_decimal", alias + ".5"),
            ("quoted", '"' + alias + '."'),
        ):
            yield Case(entry.id + ":challenge:" + kind, "conservative_abstention", text, ())


def load_observations(path, dictionary):
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_OBSERVED_BYTES + 1)
    if len(raw) > MAX_OBSERVED_BYTES:
        raise ValueError("Observation file size limit")
    value = json.loads(raw, object_pairs_hook=strict_object,
                       parse_constant=lambda token: (_ for _ in ()).throw(ValueError("Nonfinite JSON: " + token)))
    fields(value, {"schema", "provenance", "cases"}, "observations")
    if value["schema"] != OBSERVED_SCHEMA:
        raise ValueError("Unsupported observation schema")
    provenance = value["provenance"]
    fields(provenance, {"source", "transcriber", "labeling_method"}, "observation provenance")
    for key, item in provenance.items():
        text_value(item, 2048, key)
    cases = value["cases"]
    if not isinstance(cases, list) or not 1 <= len(cases) <= MAX_CASES:
        raise ValueError("Invalid observation case count")
    entries = {entry.id: entry for entry in dictionary.entries}
    result, ids = [], set()
    for row in cases:
        fields(row, {"id", "text", "expected"}, "observation case")
        key = text_value(row["id"], 128, "case ID")
        if key in ids:
            raise ValueError("Duplicate observation case ID")
        ids.add(key)
        text = text_value(row["text"], MAX_TEXT, "observation text")
        if not isinstance(row["expected"], list) or len(row["expected"]) > 256:
            raise ValueError("Invalid observation annotations")
        expected, previous_end = [], 0
        for match in row["expected"]:
            fields(match, {"id", "start", "end"}, "observation annotation")
            identity, start, end = match["id"], match["start"], match["end"]
            if (not isinstance(identity, str) or identity not in entries or type(start) is not int
                    or type(end) is not int or not previous_end <= start < end <= len(text)
                    or not text[start:end].strip()):
                raise ValueError("Invalid observation span or representation")
            expected.append(Expected(identity, start, end, entries[identity].latex))
            previous_end = end
        result.append(Case(key, "operator_labeled_observations", text, tuple(expected)))
    return result, {"sha256": hashlib.sha256(raw).hexdigest(), "provenance": provenance,
                    "provenance_verified": False}


def evaluate(cases, dictionary):
    groups, failures = {}, []
    covered = set()
    for case in cases:
        stats = groups.setdefault(case.group, Counter())
        matches = recognize(case.text, dictionary)
        actual = Counter(Expected(match.dictionary_id, match.start, match.end, match.latex) for match in matches)
        expected = Counter(case.expected)
        invalid_spans = sum(not (0 <= match.start < match.end <= len(case.text)
                                and case.text[match.start:match.end] == match.source_text)
                            for match in matches)
        tp, fp, fn = sum((actual & expected).values()), sum((actual - expected).values()), sum((expected - actual).values())
        stats.update(cases=1, true_positive=tp, false_positive=fp, false_negative=fn,
                     invalid_spans=invalid_spans, expected_matches=sum(expected.values()),
                     actual_matches=sum(actual.values()), passed=int(not (fp or fn or invalid_spans)))
        covered.update(match.id for match in expected)
        if fp or fn or invalid_spans:
            failures.append({"case_id": case.id, "group": case.group, "false_positive": fp,
                             "false_negative": fn, "invalid_spans": invalid_spans})
    total = Counter()
    for stats in groups.values():
        total.update(stats)

    def summarize(stats):
        return {**dict(stats), "precision": (stats["true_positive"] / (stats["true_positive"] + stats["false_positive"])
                                             if stats["true_positive"] + stats["false_positive"] else None),
                "recall": (stats["true_positive"] / stats["expected_matches"] if stats["expected_matches"] else None)}
    return {"groups": {key: summarize(stats) for key, stats in sorted(groups.items())},
            "total": summarize(total), "expected_representation_coverage": len(covered), "failures": failures,
            "pass": bool(total["cases"]) and not failures}


def qualify(root=ROOT, fixtures=FIXTURES, observed=None):
    dictionary, rows, binding = build_review_dictionary(root, fixtures)
    regression = evaluate(synthetic_cases(dictionary, rows), dictionary)
    challenges = evaluate(context_challenges(dictionary), dictionary)
    observations = None
    if observed is not None:
        cases, metadata = load_observations(observed, dictionary)
        observations = {**metadata, "results": evaluate(cases, dictionary)}
    payload = {
        "schema": REPORT_SCHEMA, "harness_version": HARNESS_VERSION,
        "matcher_version": MATCHER_VERSION,
        "implementation_sha256": {
            name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
            for name in ("matcher.py", "dictionary.py", "qualify_recognition.py")
        },
        "review_dictionary_sha256": dictionary.digest, "binding": binding,
        "representations": len(dictionary.entries), "aliases": len(dictionary.aliases),
        "regression": regression, "context_challenges": challenges,
        "observations": observations,
        "recognition_qualified": False, "release_qualified": False,
        "blockers": [
            *([] if regression["pass"] else ["synthetic_regression_failure"]),
            *([] if challenges["pass"] else ["context_abstention_gaps"]),
            *([] if observations is not None else ["no_operator_labeled_observations"]),
            "independent_recognition_evidence_and_admission_policy_pending",
        ],
    }
    return {**payload, "report_sha256": digest(payload)}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Evaluate STEM recognition without admitting candidates")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--fixtures", type=Path, default=FIXTURES)
    parser.add_argument("--observed", type=Path, help="Optional locally labeled transcription observations")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = qualify(args.root, args.fixtures, args.observed)
        if args.summary:
            report = {key: value for key, value in report.items() if key not in ("binding", "regression", "context_challenges", "observations")} | {
                "regression": {key: value for key, value in report["regression"].items() if key != "failures"},
                "context_challenges": {key: value for key, value in report["context_challenges"].items() if key != "failures"},
                "observations": None if report["observations"] is None else {
                    "sha256": report["observations"]["sha256"],
                    "provenance_verified": False,
                    "results": {key: value for key, value in report["observations"]["results"].items() if key != "failures"},
                },
            }
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["regression"]["pass"] and report["context_challenges"]["pass"] else 1
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.exit(1, "Recognition qualification failed: " + str(error) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
