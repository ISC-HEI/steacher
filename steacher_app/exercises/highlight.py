from PIL import Image, ImageDraw, ImageColor
import time
import json
import logging
from google import genai
from google.genai.types import GenerateContentConfig, ThinkingConfig, Part
from django.conf import settings
from .schemas import HighlightResponse
from .models import TraceImage
import io

gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)
logger = logging.getLogger(__name__)

HIGHLIGHT_MODEL = "gemini-3-flash-preview"  # previously "gemini-2.5-flash"

# TODO: Integrate Colorblind friendly palette for highlighting.
# The default has been changed to "#FFB000", one of the colors from the "IBM" palette (see https://davidmathlogic.com/colorblind/#%23648FFF-%23785EF0-%23DC267F-%23FE6100-%23FFB000)
# If multiple highlighting per images was to be implemented, here are the codes of the other IBM color palette:
# - #FE6100
# - #DC267F
# - #785EF0
# - #648FFF

def add_highlighter(img:Image, bounding_box:list[int], color:str="#FFB000", margin:list[int] = [5,10]):
    """
    Add a highlighting (transparent colored rectangle with rounded corners, for a "stabylo effect") to an image. A margin can also be added in x and y directions.

    Parameters
    ----------
    img : Image (PIL)
        The image in which we want to add the highlighting effect
    bounding_box : [int, int, int, int]
        Bounding box in the following format: [x0, y0, x1, y1]
    color : String
        The color of the highlighting, default: "#648FFF" (yellow color from the colorblind friendly "IBM" palette)
    margin : [int, int]
        Margin to add around the bounding box [margin_x, margin_y], default = [5, 10]
            
    Returns
    -------
    Image
        The inputed image "img" with a colored transparent rectangle placed on the bounding_box coordinates, with an optionnal additionnal margin
    """
    # Create a transparent overlay
    overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    # Extract coordinates from bounding_box [y0, x0, y1, x1] and add margin
    x0, y0, x1, y1 = bounding_box
    mar_x, mar_y = margin
    x0 = x0 - mar_x
    y0 = y0 - mar_y
    x1 = x1 + mar_x
    y1 = y1 + mar_y

    # Convert color name to RGB, then add alpha
    rgb = ImageColor.getrgb(color)
    rgba_color = rgb + (128,)  # Add alpha channel

    # Draw rounded rectangle
    corner_radius = 10
    draw.rounded_rectangle(
        [(x0, y0), (x1, y1)],
        radius=corner_radius,
        fill=rgba_color
    )
    
    # Composite the overlay onto the original image and turns it back into RGB for return
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    
    result = Image.alpha_composite(img, overlay)
    result = result.convert('RGB')

    return result


def treat_gemini_bbox(bbox, img_size):
    """
    The output bounding boxes of gemini are formatted according to the vision training for the model.
    https://ai.google.dev/gemini-api/docs/image-understanding?lang=node&hl=fr#segmentation
    The bounding box is stocked as a list of 4 numbers describing the coordinates of two corners of the rectangle: [y0, x0, y1, x1].
    The value is also normalized to be contained in a range, the value will always be in the range (0 to 1000): It needs to be adapted to the image size.

    Parameters
    ----------
    bbox : [int, int, int, int]
        bounding box in the gemini format: [y0, x0, y1, x1]
    img_size : (int, int)
        height and width of the image (in this order, so (height, width)). Can be obtained easily with "img.shape[:2]" on a cv2 loaded image

    Returns
    -------
    [int, int, int, int]
        The bounding box adapted to the size of the image and in a more intuitive format: [x0, y0, x1, y1]
    """
    height, width = img_size

    y0, x0, y1, x1 = bbox
    x0 = int(x0 / 1000 * width)
    y0 = int(y0 / 1000 * height)
    x1 = int(x1 / 1000 * width)
    y1 = int(y1 / 1000 * height)
    
    return x0,y0,x1,y1


def find_text_in_image(text_to_find: str, img_bytes:bytes, mime_type: str) -> dict:
    """
    Finds text text_to_find in the img image using Gemini API and returns a dict with the important informations:
    - The bounding box of the found text (or empty list if not found)
    - A comment with any errors that occured, should be empty most of the time
    - The time the request took for debugging/improvement purposes

    Parameters
    ----------
    text_to_find : str
        The text extract that needs to be found in the image
    img : bytes
        The image the text needs to be found in, already in bytes since it should be loaded from fetch_ai_guidance
    mime_type : str     
        The input image mime_type (typically 'image/[format]', like this 'image/jpeg')

    Returns
    -------
    dict (with following keys:)
        - bounding_box ([int, int, int, int]): list [y0, x0, y1, x1] or empty list if not found
        - comment (str): error message or empty string if successful
        - elapsed_time (float): time taken for the API call in seconds
    """

    prompt = f'''# Task
You will receive an image of a student math exercise and a piece of LaTeX formatted text. Your task is to find the inputed text into the image and return a bounding box that goes around it.

# Input
Text to find: {text_to_find}

# Instructions
- Return the bounding box as [y0, x0, y1, x1].
- If the text is not found, return an empty bounding box and explain why in the comment.
- If no image is provided, return an empty bounding box and "ERROR: No Image" in the comment.
'''

    try:
        # Create chat session using the existing gemini_client
        chat_config = GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=HighlightResponse.model_json_schema(),
            # Google documentation (see https://ai.google.dev/gemini-api/docs/image-understanding?lang=node&hl=fr#segmentation) recommends no thinking budget:
            # "set thinking_budget to 0 for better results in object detection"
            thinking_config=ThinkingConfig(thinking_budget=0)
        )
        chat_session = gemini_client.chats.create(
            model=HIGHLIGHT_MODEL,
            config=chat_config,
        )

        # Create input with text and image
        image_part = Part.from_bytes(data=img_bytes, mime_type=mime_type)
        user_input = [Part(text=prompt), image_part]

        # Send message and get response
        start_time = time.time()
        gen_response = chat_session.send_message(user_input)
        elapsed_time = time.time() - start_time

        # Parse response using HighlightResponse model
        highlight_response = HighlightResponse.from_gemini_response(
            gen_response,
            elapsed_time=round(elapsed_time, 2)
        )
        
        return highlight_response.model_dump()

    except Exception as e:
        logger.error(f"Error in find_text_in_image: {e}")
        error_response = HighlightResponse(
            bounding_box=[],
            comment=f"ERROR: {str(e)}",
            elapsed_time=0.0
        )
        return error_response.model_dump()


def highlight(trace_image_object: TraceImage, text_to_highlight: str):
    """
    Main highlighting pipeline, called from logic.py. Tries to find the text_to_highlight in the image and saves
    its bounding box in the current trace_image if successful.

    Parameters
    ----------
    trace_image_object : TraceImage
        The TraceImage object in which to save the bounding box if found
    text_to_highlight : str
        The text that should be found in the image
    """

    logger.info(f"Processing image highlight, text to be highlighted: {text_to_highlight}")
    # Get the image bytes from the first uploaded image
    img_bytes = trace_image_object.image_bytes
    img_mim_type =  trace_image_object.image_type

    # Find the text in the image using Gemini API
    found_text = find_text_in_image(text_to_highlight, img_bytes, img_mim_type)
    logger.info(f"Found text result: {found_text}")
    returned_bbox = found_text["bounding_box"]

    # Load image bytes into PIL Image and get its size for bbox normalization
    im_pil = Image.open(io.BytesIO(img_bytes))
    img_size = (im_pil.height, im_pil.width)

    # Treat the bounding box coordinates
    treated_bbox = treat_gemini_bbox(returned_bbox, img_size)
    logger.info(f"Treated bbox: {treated_bbox}")

    # Save bbox to TraceImage for frontend rendering
    if returned_bbox and returned_bbox != []:  # Only save if bbox was found
        trace_image_obj = trace_image_object
        bbox_entry = {
            'bbox': list(treated_bbox),
            'color': '#FFB000'  # Default color matching add_highlighter default
        }
        if not trace_image_obj.highlight_bboxes:
            trace_image_obj.highlight_bboxes = []
        trace_image_obj.highlight_bboxes.append(bbox_entry)
        trace_image_obj.save(update_fields=['highlight_bboxes'])
        logger.info(f"Saved highlight bbox to TraceImage {trace_image_obj.id}: {bbox_entry}")