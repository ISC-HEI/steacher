from pathlib import Path
from django.core.management.base import BaseCommand
from django.conf import settings
from google import genai
from google.genai.types import Part, GenerateContentConfig
import fitz  # PyMuPDF


class Command(BaseCommand):
    help = 'Convert PDF files to Markdown using Gemini'

    def add_arguments(self, parser):
        parser.add_argument(
            'directory',
            type=str,
            help='Path to directory containing PDF files'
        )
        parser.add_argument(
            '--dpi',
            type=int,
            default=150,
            help='DPI for PDF rendering (default: 150)'
        )
        parser.add_argument(
            '--model',
            type=str,
            default='gemini-3-pro-preview',
            help='Gemini model to use (default: gemini-3-pro-preview)'
        )

    def handle(self, *args, **options):
        directory = Path(options['directory'])
        dpi = options['dpi']
        model = options['model']

        if not directory.exists():
            self.stderr.write(self.style.ERROR(f"Directory not found: {directory}"))
            return

        # Initialize Gemini client
        gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)

        # Find all PDF files
        pdf_files = list(directory.glob("*.pdf"))

        if not pdf_files:
            self.stdout.write(self.style.WARNING(f"No PDF files found in {directory}"))
            return

        self.stdout.write(f"Found {len(pdf_files)} PDF files to process")
        self.stdout.write("-" * 60)

        for pdf_path in pdf_files:
            self.stdout.write(f"Processing: {pdf_path.name}")

            try:
                # Convert PDF pages to images
                self.stdout.write(f"  Converting pages to images...")
                images = self.pdf_to_images(pdf_path, dpi)
                self.stdout.write(f"  Converted {len(images)} pages")

                # Send to Gemini for markdown conversion
                self.stdout.write(f"  Sending to Gemini...")
                markdown_content = self.convert_images_to_markdown(images, gemini_client, model)

                # Save markdown file
                md_path = pdf_path.with_suffix('.md')
                with open(md_path, 'w', encoding='utf-8') as f:
                    f.write(markdown_content)

                self.stdout.write(self.style.SUCCESS(f"  ✓ Saved to: {md_path.name}"))

            except Exception as e:
                self.stderr.write(self.style.ERROR(f"  ✗ Error: {str(e)}"))

            self.stdout.write("")

        self.stdout.write("-" * 60)
        self.stdout.write(self.style.SUCCESS("Processing complete!"))

    def pdf_to_images(self, pdf_path, dpi=150):
        """
        Convert all pages of a PDF to images.

        Args:
            pdf_path: Path to the PDF file
            dpi: Resolution for rendering (default 150)

        Returns:
            List of image bytes (PNG format)
        """
        doc = fitz.open(pdf_path)
        images = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            # Render page to pixmap at specified DPI
            # zoom factor: dpi/72 (72 is the default DPI)
            zoom = dpi / 72
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)

            # Convert to PNG bytes
            img_bytes = pix.pil_tobytes(format="PNG")
            images.append(img_bytes)

        doc.close()
        return images

    def convert_images_to_markdown(self, image_bytes_list, gemini_client, model):
        """
        Send images to Gemini and get markdown conversion.

        Args:
            image_bytes_list: List of image bytes (PNG format)
            gemini_client: Gemini client instance
            model: Model name to use

        Returns:
            Markdown string
        """
        # prompt and chat setup
        prompt = '''Convert this document to clean Markdown format. Use LaTeX notation 
for mathematical formulas (wrap inline math in $ and display math in $$). 
Preserve the document structure and hierarchy. Ignore page headers and footers. Ignore illustrations.'''
        
        chat_config = GenerateContentConfig(
            system_instruction=prompt,
            response_mime_type="text/plain",
            thinking_config=genai.types.ThinkingConfig(include_thoughts=True, thinking_level="low"),
        )
        
        chat_session = gemini_client.chats.create(
            model=model,
            config=chat_config,
        )

        # input creation
        user_complete_input = [Part(text=prompt)]
        for img_bytes in image_bytes_list:
            image_part = genai.types.Part.from_bytes(data=img_bytes, mime_type='image/png')
            user_complete_input.append(image_part)

        # query to the LLM
        gen_response = chat_session.send_message(user_complete_input)
        text_out = gen_response.text.strip()

        # removing fences if there's any
        text_out = text_out.strip()
        if text_out.startswith("```"):
            # Find the first newline
            first_newline = text_out.find('\n')
            if first_newline != -1:
                text_out = text_out[first_newline + 1:]
            else:
                text_out = text_out.lstrip('`')
        if text_out.endswith("```"):
            text_out = text_out[:-3].strip()

        return text_out
