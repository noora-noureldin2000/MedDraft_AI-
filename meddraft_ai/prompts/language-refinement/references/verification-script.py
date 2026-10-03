#!/usr/bin/env python3
"""Fidelity checker for language-refinement edits.

Compares an ORIGINAL file against an EDITED file and fails on:
  1. Any citation tag present in the original but missing in the edited text.
  2. Any number present in the original but missing in the edited text.
  3. Banned vocabulary, em-dashes, or semicolons introduced by the edit.

Usage:
    python verification-script.py original.md edited.md [--latex]

Exit code 0 = pass, 1 = fail (lists every mismatch).
"""
import re
import sys
import unicodedata

BANNED = ["delve", "crucial", "tapestry", "multifaceted", "nuanced",
          "groundbreaking", "paramount", "a myriad of", "landscape",
          "leverage", "pivotal", "foster", "harness", "testament",
          "commendable", "it is worth noting that"]


def normalize(text):
    text = unicodedata.normalize("NFKD", text)
    return text.lower()


def extract_citations(text, latex=False):
    found = set()
    # Harvard author-date: (Author et al., 2020) and narrative Author et al. (2020)
    for m in re.finditer(r"\(([A-Z][A-Za-z\-]+(?:\s+et\s+al\.?)?(?:,?\s*&?\s*[A-Z][A-Za-z\-]+)*),?\s*(\d{4}[a-z]?)\)", text):
        found.add("paren:" + m.group(0))
    for m in re.finditer(r"[A-Z][A-Za-z\-]+(?:\s+et\s+al\.?)?\s*\(\d{4}[a-z]?\)", text):
        found.add("narr:" + m.group(0))
    # Vancouver / AMA bracket numerals
    for m in re.finditer(r"\[\d+(?:[\-,]\d+)*\]", text):
        found.add("bracket:" + m.group(0))
    if latex:
        for m in re.finditer(r"\\cite\{[^}]*\}", text):
            found.add("latex:" + m.group(0))
    return found


def extract_numbers(text, latex=False):
    # Strip LaTeX commands so macro names are not counted as content
    if latex:
        text = re.sub(r"\\[a-zA-Z]+\{?", " ", text)
    nums = set()
    for m in re.finditer(r"\d[\d,]*(?:\.\d+)?", text):
        nums.add(m.group(0))
    return nums


def main():
    if len(sys.argv) < 3:
        print("Usage: python verification-script.py original.md edited.md [--latex]")
        sys.exit(2)
    latex = "--latex" in sys.argv
    original = open(sys.argv[1], encoding="utf-8").read()
    edited = open(sys.argv[2], encoding="utf-8").read()

    errors = []

    for cite in sorted(extract_citations(original, latex)):
        if cite not in extract_citations(edited, latex):
            # narrative and parenthetical forms of the same work count as kept
            core = re.sub(r"^(paren|narr|bracket|latex):", "", cite)
            if not any(core in e for e in extract_citations(edited, latex)):
                errors.append("CITATION LOST: " + cite)

    for num in sorted(extract_numbers(original, latex)):
        if num not in extract_numbers(edited, latex):
            errors.append("NUMBER LOST: " + num)

    norm_edited = normalize(edited)
    for word in BANNED:
        if word in norm_edited and word not in normalize(original):
            errors.append("BANNED TERM INTRODUCED: " + word)
    if "—" in edited and "—" not in original:
        errors.append("EM-DASH INTRODUCED")
    sema_o, sema_e = original.count(";"), edited.count(";")
    if sema_e > sema_o:
        errors.append("SEMICOLONS INTRODUCED (%d -> %d)" % (sema_o, sema_e))

    if errors:
        print("FAIL:")
        for e in errors:
            print("  " + e)
        sys.exit(1)
    print("PASS: all citations and numbers preserved, no banned terms introduced.")


if __name__ == "__main__":
    main()
