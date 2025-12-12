from PIL import Image, ImageDraw, ImageColor
import time
import json
import logging
from google import genai
from google.genai.types import GenerateContentConfig, ThinkingConfig, Part
from django.conf import settings

gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)
logger = logging.getLogger(__name__)

def add_highlighter(img:Image, bounding_box:list[int], color:str="yellow", margin:list[int] = [5,10]):
    """
    Add a highlighting (transparent colored rectangle with rounded corners, for a "stabylo effect") to an image. A margin can also be added in x and y directions.

    Parameters
    ----------
    img : Image (PIL)
        The image in which we want to add the highlighting effect
    bounding_box : [int, int, int, int]
        Bounding box in the following format: [x0, y0, x1, y1]
    color : String
        The color of the highlighting, default: "yellow"
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


def find_text_in_image(text_to_find: str, img_bytes:bytes) -> dict:
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
Image: the image will be given on the side. If you don't receive an image, you must return an empty bounding box.
Text: You will receive it at the end of these instructions with the title "# Text to find". It will be formatted as plaintext with LaTeX notations, either inline with "$" or full-line with "$$".

# Output
You output will be a valid JSON format containing the following fields:
"bounding_box" : This is the 2d bounding box around the text. The list must contain the elements in this order: [y0, x0, y1, x1]
"comment" : This is a place for you to give us debug information:
- If you don't receive an image, return "ERROR: No Image" in this field.
- If you don't find the text in the image, return "ERROR: The text is not in the image" in this field.
- If there was no problem, simply return an empty "" in this field.

# Output Examples:
## The image contained the text
{{
	bounding_box : [1,10,40,100],
	comment: ""
}}

## the image didn't contain text
{{
	bounding_box : [];
	comment: "ERROR: The text is not in the image"
}}

# Text to find
{text_to_find}

# Your output
'''

    try:
        # type of the saved images
        mime_type = 'image/jpeg'

        # Create chat session using the existing gemini_client
        chat_config = GenerateContentConfig(
            response_mime_type="text/plain",
            # Google documentation (see https://ai.google.dev/gemini-api/docs/image-understanding?lang=node&hl=fr#segmentation) recommends no thinking budget:
            # "set thinking_budget to 0 for better results in object detection"
            thinking_config=ThinkingConfig(thinking_budget=0)
        )
        chat_session = gemini_client.chats.create(
            model="gemini-2.5-flash",
            config=chat_config,
        )

        # Create input with text and image
        image_part = Part.from_bytes(data=img_bytes, mime_type=mime_type)
        user_input = [Part(text=prompt), image_part]

        # Send message and get response
        start_time = time.time()
        gen_response = chat_session.send_message(user_input)
        elapsed_time = time.time() - start_time

        response_text = gen_response.text.strip()

        # Clean up markdown code fences if present
        clean_response = response_text
        if clean_response.startswith("```json"):
            clean_response = clean_response[7:]
        if clean_response.startswith("```"):
            clean_response = clean_response[3:]
        if clean_response.endswith("```"):
            clean_response = clean_response[:-3]

        # Parse JSON response
        try:
            json_response = json.loads(clean_response.strip())
            json_response["elapsed_time"] = round(elapsed_time, 2)
            return json_response
        except json.JSONDecodeError:
            logger.error(f"Failed to parse JSON from Gemini response: {clean_response}")
            return {
                "bounding_box": [],
                "comment": f"ERROR: Failed to parse response",
                "elapsed_time": round(elapsed_time, 2)
            }

    except Exception as e:
        logger.error(f"Error in find_text_in_image: {e}")
        return {
            "bounding_box": [],
            "comment": f"ERROR: {str(e)}",
            "elapsed_time": 0
        }
