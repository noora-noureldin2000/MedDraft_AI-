import os
import sys
import tempfile
import argparse
import shutil
import zipfile
from pathlib import Path

# Configure console encoding on Windows to support UTF-8 characters if possible
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

def detect_file_type(file_path: Path) -> str:
    """
    Detects the true file format based on magic number/signature bytes.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
        
    with open(file_path, 'rb') as f:
        header = f.read(2048)
        
    if header.startswith(b'%PDF'):
        return 'pdf'
    elif header.startswith(b'PK\x03\x04'):
        # Check zip contents to distinguish Office Open XML formats (docx, xlsx, pptx)
        try:
            with zipfile.ZipFile(file_path, 'r') as z:
                names = z.namelist()
                if any(n.startswith('word/') for n in names):
                    return 'docx'
                elif any(n.startswith('xl/') for n in names):
                    return 'xlsx'
                elif any(n.startswith('ppt/') for n in names):
                    return 'pptx'
        except Exception:
            pass
        return 'zip'
    elif header.startswith(b'{\\rtf'):
        return 'rtf'
    elif header.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'png'
    elif header.startswith(b'\xff\xd8\xff'):
        return 'jpg'
    
    # Generic check for binary (presence of null bytes)
    if b'\x00' in header:
        return 'binary'
        
    return 'text'

def fallback_conversion(input_path: Path, output_path: Path, file_type: str) -> bool:
    """
    Fallback conversion using standard/installed libraries if MarkItDown fails.
    """
    print(f"[Fallback] Attempting fallback parsing for type '{file_type}'...")
    try:
        if file_type == 'pdf':
            import pdfplumber
            print("[Fallback] Extracting PDF pages using pdfplumber...")
            text_pages = []
            with pdfplumber.open(input_path) as pdf:
                for i, page in enumerate(pdf.pages):
                    text = page.extract_text()
                    text_pages.append(f"## Page {i+1}\n\n{text or '[No text extracted]'}\n")
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write("\n".join(text_pages))
            print("[Fallback] PDF extraction completed successfully.")
            return True
        elif file_type == 'docx':
            import docx
            print("[Fallback] Extracting DOCX paragraphs using python-docx...")
            doc = docx.Document(input_path)
            text_lines = [p.text for p in doc.paragraphs if p.text.strip()]
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write("\n\n".join(text_lines))
            print("[Fallback] DOCX extraction completed successfully.")
            return True
    except Exception as e:
        print(f"[Fallback] Fallback conversion failed: {e}")
    return False

def convert_file(input_path: Path, output_path: Path) -> bool:
    """
    Detects if the file is binary and converts it to markdown.
    """
    file_type = detect_file_type(input_path)
    
    if file_type == 'text':
        print(f"File '{input_path.name}' is already a plain text file. No conversion needed.")
        if input_path != output_path:
            shutil.copy2(input_path, output_path)
            print(f"Copied original file to: {output_path}")
        return True
        
    print(f"Detected true format: {file_type.upper()}")
    
    # We copy the file to a temp file with the true extension so markitdown knows which parser to use.
    suffix = f".{file_type}" if file_type != 'binary' else input_path.suffix
    
    try:
        from markitdown import MarkItDown
        md = MarkItDown()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_file_path = Path(temp_dir) / f"temp_source{suffix}"
            shutil.copy2(input_path, temp_file_path)
            
            print(f"Converting binary file via MarkItDown...")
            result = md.convert(str(temp_file_path))
            markdown_content = result.text_content
            
        if not markdown_content or not markdown_content.strip():
            raise ValueError("Conversion returned empty content.")
            
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
        print(f"Successfully parsed and saved markdown to: {output_path}")
        return True
        
    except Exception as e:
        print(f"Warning: MarkItDown failed: {e}")
        # Try fallback
        success = fallback_conversion(input_path, output_path, file_type)
        if not success:
            raise RuntimeError(f"All parsing attempts failed for file format '{file_type}'.")
        return True

def main():
    parser = argparse.ArgumentParser(
        description="Binary File Auto-Recovery & Markdown Converter Skill CLI"
    )
    parser.add_argument(
        '-i', '--input',
        required=True,
        help="Path to the input file (which may be a binary file misnamed as markdown)."
    )
    parser.add_argument(
        '-o', '--output',
        help="Path to save the extracted markdown text. If not provided, it will write to <input_name>_recovered.md."
    )
    parser.add_argument(
        '--overwrite',
        action='store_true',
        help="Overwrite the input file directly (useful if repairing a misnamed .md file in-place)."
    )
    
    args = parser.parse_args()
    
    input_path = Path(args.input).resolve()
    if not input_path.exists():
        print(f"Error: Input file '{input_path}' does not exist.")
        sys.exit(1)
        
    if args.overwrite:
        output_path = input_path
    elif args.output:
        output_path = Path(args.output).resolve()
    else:
        # Generate default recovered path
        output_path = input_path.parent / f"{input_path.stem}_recovered.md"
        
    try:
        convert_file(input_path, output_path)
    except Exception as e:
        print(f"Execution failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
