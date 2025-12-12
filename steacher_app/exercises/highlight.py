from PIL import Image, ImageDraw, ImageColor

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