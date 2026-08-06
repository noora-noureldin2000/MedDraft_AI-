#!/usr/bin/env python3
import argparse
import sys
import os

# Ensure the journal_formatting directory is in the path
script_dir = os.path.dirname(os.path.abspath(__file__))
jf_dir = os.path.join(script_dir, "journal_formatting")
sys.path.insert(0, jf_dir)

from reader import read_manuscript
from formats import get_formats
from ris_parser import parse_ris

def main():
    parser = argparse.ArgumentParser(description="Headless CLI for journal_formatting")
    parser.add_argument("--input", required=True, help="Input .docx manuscript path")
    parser.add_argument("--output", required=True, help="Output .docx formatted path")
    parser.add_argument("--format", required=True, help="Target journal format (e.g., MDPI, Elsevier)")
    parser.add_argument("--ris", default=None, help="Optional .ris bibliography file")
    parser.add_argument("--zotero", action="store_true", help="Embed Zotero field codes")
    parser.add_argument("--crossref", action="store_true", help="Use CrossRef for unmatched references")
    
    args = parser.parse_args()
    
    formats = get_formats()
    if args.format not in formats:
        print(f"Error: Format '{args.format}' not found. Available formats: {list(formats.keys())}")
        sys.exit(1)
        
    plugin = formats[args.format]
    
    print(f"Reading manuscript from {args.input}...")
    try:
        items = read_manuscript(args.input)
    except Exception as e:
        print(f"Failed to read manuscript: {e}")
        sys.exit(1)
        
    ris_data = None
    if args.ris:
        print(f"Parsing bibliography from {args.ris}...")
        try:
            ris_data = parse_ris(args.ris)
        except Exception as e:
            print(f"Warning: Could not parse RIS file: {e}")
            
    print(f"Building {args.format} formatted document...")
    
    def progress_cb(current, total, message):
        pass # Optional: can print progress here
        
    try:
        plugin.build(
            items, 
            args.output,
            ris_data=ris_data,
            zotero_enabled=args.zotero,
            use_crossref=args.crossref,
            progress_callback=progress_cb
        )
    except Exception as e:
        print(f"Failed to build document: {e}")
        sys.exit(1)
        
    print(f"Success! Formatted manuscript saved to {args.output}")

if __name__ == "__main__":
    main()
