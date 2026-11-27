import argparse
from dataclasses import asdict
import json

from .dictionary import load_dictionary
from .matcher import MATCHER_VERSION, recognize


def main():
    parser = argparse.ArgumentParser(description="Inspect the offline STEM dictionary")
    parser.add_argument("--dictionary")
    parser.add_argument("--text", help="Recognize expressions in a sample of narration")
    args = parser.parse_args()
    dictionary = load_dictionary(args.dictionary) if args.dictionary else load_dictionary()
    result = {"dictionary_sha256": dictionary.digest, "entries": len(dictionary.entries),
              "aliases": len(dictionary.aliases), "matcher": MATCHER_VERSION}
    if args.text is not None:
        result["matches"] = [asdict(match) for match in recognize(args.text, dictionary)]
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
