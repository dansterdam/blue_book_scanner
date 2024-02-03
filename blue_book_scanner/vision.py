import base64
import os
import json
import io
import PyPDF2
import argparse
from pdf2image import convert_from_path
from openai import OpenAI


def main():
    parser = argparse.ArgumentParser(description="Process some files.")

    parser.add_argument(
        "--keyfile",
        metavar="filepath",
        type=str,
        help="the path to the json with your api key",
    )
    parser.add_argument(
        "--input",
        metavar="dir",
        type=str,
        help="the path to the directory of files to be processed",
    )
    parser.add_argument(
        "--output",
        metavar="dir",
        type=str,
        help="the directory where to output the scanned file",
    )
    args = parser.parse_args()
    os.makedirs(args.output, exist_ok=True)

    with open(args.keyfile) as f:
        key = json.load(f)["api_key"]
    client = OpenAI(api_key=key)
    # OpenAI API Key

    process_fileset(args.input, args.output, client)


def process_fileset(input, output, client):
    for file in os.listdir(input):
        pages_in_pdf = get_pdf_page_count(input + file)
        # Getting the base64 string
        counter = 0
        if file + str(pages_in_pdf) + ".txt" not in os.listdir(output):
            pages_done = len([i for i in os.listdir(output) if file in i])
            counter = pages_done
            for i in range(counter, pages_in_pdf, 20):
                end_page = min(pages_in_pdf, counter + i + 20)
                start_page = counter + i
                pages = convert_from_path(
                    input + file, first_page=start_page, last_page=end_page
                )
                for page in pages:
                    counter += 1
                    image = encode_pdf_page_to_base64_image(page)
                    output_filename = output + file + str(counter) + ".txt"
                    print(f"processing {output_filename}")

                    response = gpt_ocr(image, output_filename, client)

                    try:
                        gpt_output_text = response.choices[0].message.content
                        with open(output_filename, "w") as f:
                            f.write(gpt_output_text)
                    except KeyError:
                        os.remove(output_filename)
                        print(response.json())
                        exit()


def get_pdf_page_count(pdf_path):
    with open(pdf_path, "rb") as file:
        reader = PyPDF2.PdfReader(file)
        return len(reader.pages)


def encode_pdf_page_to_base64_image(page):
    # Convert image to bytes
    img_byte_arr = io.BytesIO()
    page.save(img_byte_arr, format="PNG")
    img_byte_arr = img_byte_arr.getvalue()

    # Encode to base64 and add to the list
    return base64.b64encode(img_byte_arr).decode("utf-8")


def gpt_ocr(image, filename, client):
    response = client.chat.completions.create(
        model="gpt-4-vision-preview",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f'This is a page in an old UFO report document from project blue book. Please describe any photograph that is present. Not every image will contain a photograph. Then, please act as an OCR system and produce and output all the text found in the document and nothing else. For context: the filename including page number is {filename}',
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image}"},
                    },
                ],
            }
        ],
        max_tokens=2000,
    )

    return response


if __name__ == "__main__":
    main()
