import argparse
import hashlib
import json
from pathlib import Path

from .corpus_model import ROOT, digest
from .hybrid import HYBRID_VERSION, RULES, build_hybrid
from .observation_labels import load_hybrid_observations
from .qualify_recognition import Case, Expected, FIXTURES, context_challenges, evaluate, synthetic_cases

SCHEMA = "fitbaus.stem.hybrid-qualification/v1"


def structural_cases():
    for identity, _, latex, phrase in RULES:
        for name, prefix in (("bare", ""), ("introduced", "The equation is ")):
            yield Case(identity + ":structural:" + name, "structural_positive", prefix + phrase + ".",
                       (Expected(identity, len(prefix), len(prefix) + len(phrase), latex),))
        for name, text in (("question", phrase + "?"), ("negation", "Not the formula: " + phrase + "."),
                           ("extension", phrase + " plus one."), ("continuation", phrase + ". Plus one.")):
            yield Case(identity + ":structural:" + name, "structural_abstention", text, ())


def qualify(root=ROOT, fixtures=FIXTURES, observed=None):
    hybrid, rows, binding = build_hybrid(root, fixtures)
    dictionary = hybrid.dictionary

    def recognize(text, unused_dictionary):
        return hybrid.recognize(text)

    regression = evaluate(synthetic_cases(dictionary, rows), dictionary, recognizer=recognize)
    challenges = evaluate(context_challenges(dictionary), dictionary, recognizer=recognize)
    structural = evaluate(structural_cases(), dictionary, recognizer=recognize)
    observations = None
    if observed is not None:
        cases, metadata = load_hybrid_observations(observed, dictionary)
        observations = {**metadata, "baseline": evaluate(cases, dictionary),
                        "hybrid": evaluate(cases, dictionary, recognizer=recognize)}
    payload = {
        "schema": SCHEMA, "hybrid_version": HYBRID_VERSION,
        "policy_sha256": hybrid.policy_sha256, "binding": binding,
        "implementation_sha256": {
            name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
            for name in ("hybrid.py", "qualify_hybrid.py", "qualify_recognition.py", "matcher.py",
                         "dictionary.py", "corpus_model.py", "tokenizer.py", "parser.py", "expression.py",
                         "identity_context.py", "observation_labels.py", "structural_rules.py", "prose_context.py")
        },
        "structural_rule_count": len(hybrid.rules), "regression": regression,
        "context_challenges": challenges, "structural": structural, "observations": observations,
        "recognition_qualified": False, "release_qualified": False,
    }
    return {**payload, "report_sha256": digest(payload)}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Compare the qualification-only identity pilot with the baseline")
    parser.add_argument("--observed", type=Path)
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = qualify(observed=args.observed)
        if args.summary:
            report = {key: value for key, value in report.items() if key != "binding"}
            for key in ("regression", "context_challenges", "structural"):
                report[key] = {k: v for k, v in report[key].items() if k != "failures"}
            if report["observations"] is not None:
                for key in ("baseline", "hybrid"):
                    report["observations"][key] = {
                        k: v for k, v in report["observations"][key].items() if k != "failures"}
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if all(report[key]["pass"] for key in ("regression", "context_challenges", "structural")) else 1
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.exit(1, "Hybrid qualification failed: " + str(error) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
