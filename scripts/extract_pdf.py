#!/usr/bin/env python3
"""Extract local PDF pages with MarkItDown; preserve physical page provenance."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import tempfile


def extract(source: Path, output: Path):
    from markitdown import MarkItDown
    from pypdf import PdfReader, PdfWriter

    source = source.resolve(strict=True)
    output = output.resolve()
    if not source.is_file() or source.suffix.lower() != '.pdf':
        raise ValueError('Input must be a local PDF file')
    if output.exists():
        raise FileExistsError('Output already exists; choose a new directory to preserve prior work')
    reader = PdfReader(str(source))
    if reader.is_encrypted:
        raise ValueError('Encrypted PDF: provide an accessible copy; do not bypass protection')
    if not len(reader.pages):
        raise ValueError('PDF has no pages')
    converter = MarkItDown(enable_plugins=False)
    pages = []
    with tempfile.TemporaryDirectory(prefix='pdf-reading-pages-') as temporary:
        for number, page in enumerate(reader.pages, 1):
            split = Path(temporary) / f'page-{number:05d}.pdf'
            writer = PdfWriter()
            writer.add_page(page)
            with split.open('wb') as handle:
                writer.write(handle)
            result = converter.convert_local(str(split))
            markdown = getattr(result, 'markdown', None)
            if markdown is None:
                markdown = getattr(result, 'text_content', None)
            if not isinstance(markdown, str):
                raise TypeError(f'Page {number}: converter returned no Markdown string')
            markdown = markdown.strip()
            chars = sum(not char.isspace() for char in markdown)
            pages.append({'pdf_page': number, 'printed_page': None,
                          'markdown': markdown, 'character_count': chars,
                          'review_status': 'needs_review',
                          'warnings': ['sparse_text_check_original_page'] if chars < 40 else []})
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    manifest = {'schema_version': 1, 'document_id': source_hash,
                'input_name': source.name, 'input_sha256': source_hash,
                'extractor': 'Microsoft MarkItDown',
                'extractor_version': importlib.metadata.version('markitdown'),
                'page_count': len(pages), 'status': 'extracted_needs_review',
                'ocr_performed': False, 'figures_extracted': False,
                'sparse_pages': [p['pdf_page'] for p in pages if p['warnings']]}
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.pdf-reading-', dir=output.parent))
    try:
        text = '\n\n'.join(f'<!-- pdf-page: {p["pdf_page"]} -->\n\n{p["markdown"]}' for p in pages) + '\n'
        (staging / 'source.md').write_text(text, encoding='utf-8')
        (staging / 'pages.json').write_text(json.dumps(pages, ensure_ascii=False, indent=2), encoding='utf-8')
        (staging / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        # Refuse replacement even if a different operation created the destination meanwhile.
        output.mkdir(exist_ok=False)
        for filename in ('source.md', 'pages.json', 'manifest.json'):
            shutil.move(str(staging / filename), str(output / filename))
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input_pdf', type=Path)
    parser.add_argument('output_directory', type=Path)
    args = parser.parse_args()
    try:
        result = extract(args.input_pdf, args.output_directory)
    except Exception as error:
        parser.exit(1, f'Extraction failed: {error}\n')
    print(json.dumps({'output_directory': str(args.output_directory.resolve()),
                      'page_count': result['page_count'],
                      'sparse_pages': result['sparse_pages'],
                      'status': result['status']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
