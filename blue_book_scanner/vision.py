import anthropic
import base64
import os
import json
import io
import re
import PyPDF2
from PIL import Image
import argparse
import concurrent.futures
from time import sleep
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
        keys = json.load(f)
        openai_key = keys["openai_api_key"]
        anthropic_key = keys["anthropic_api_key"]
    #client = OpenAI(api_key=openai_key)
    client = anthropic.Anthropic(
    api_key=anthropic_key,
)
    # OpenAI API Key

    process_fileset(args.input, args.output, client)


def process_fileset(input_dir, output_dir, client):
    files = [i for i in os.listdir(input_dir)]
    # Define the maximum number of threads based on your system's capability and the nature of the task
    max_workers = 4  # Adjust this based on your needs and system's capabilities

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit each file to be processed in parallel
        futures = [
            executor.submit(process_single_file, file, input_dir, output_dir, client)
            for file in files
        ]


def process_single_file(file, input_dir, output_dir, client):
    file_path = os.path.join(input_dir, file)
    pages_in_pdf = get_pdf_page_count(file_path)

    # Retrieve pages already processed to avoid reprocessing
    pages_done = [int(re.search(r'pdf(\d+).txt', filename).group(1)) for filename in [i for i in os.listdir(output_dir) if file in i] if re.search(r'pdf(\d+).txt', filename)]
    max_workers = 2
    pages_not_done = [i for i in range(1, pages_in_pdf + 1) if i not in pages_done]
    # Using ThreadPoolExecutor to parallelize page processing
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all pages yet to be processed to the executor
        futures = [
            executor.submit(
                process_single_page, file_path, page_number, file, output_dir, client
            )
            for page_number in pages_not_done
        ]

        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
            except Exception as e:
                print(f"An error occurred: {e}")


def process_single_page(file_path, page_number, output_file_prefix, output_dir, client):
    image = convert_page_to_image(file_path, page_number)
    base64_image = encode_image_to_base64(image)
    output_filename = f"{output_file_prefix}{page_number}.txt"
    output_filepath = os.path.join(output_dir, output_filename)
    if not os.path.exists(output_filepath):
        print(
            f"processing file {output_filename}"
        )  # Avoid re-processing if already done
        process_image_and_extract_text(
            base64_image, output_filepath, client
        )  # Include retry parameters if necessary


def convert_page_to_image(pdf_path, page_number):
    pages = convert_from_path(pdf_path, first_page=page_number, last_page=page_number)
    return pages[0]  # Assuming convert_from_path returns a list of images


def encode_image_to_base64(image):
    img_byte_arr = io.BytesIO()
    image = image.resize((1024,768), Image.LANCZOS)
    image.save(img_byte_arr, format="JPEG", quality=85)
    
    return base64.b64encode(img_byte_arr.getvalue()).decode("utf-8")


def process_image_and_extract_text(
    base64_image, output_filepath, client, max_retries=3, retry_delay=5
):
    retries = 0
    while retries < max_retries:
        try:
            #response = gpt_ocr(base64_image, output_filepath, client)
            #gpt_output_text = response.choices[0].message.content
            response = anthropic_ocr(base64_image, output_filepath, client)
            anthropic_output_text = response.content[0].text
            with open(output_filepath, "w") as f:
                f.write(anthropic_output_text)
            break  # Success, break out of the retry loop
        except KeyError as e:
            print(f"Error processing {output_filepath}: {e}")
            retries += 1
            sleep(retry_delay)  # Wait before retrying
        except Exception as e:
            print(f"Unexpected error processing {output_filepath}: {e}")
            break  # Break on unexpected errors

    if retries == max_retries:
        print(f"Failed to process {output_filepath} after {max_retries} retries.")


def get_pdf_page_count(pdf_path):
    with open(pdf_path, "rb") as file:
        reader = PyPDF2.PdfReader(file)
        return len(reader.pages)


def encode_pdf_page_to_base64_image(page):
    # Convert image to bytes
    img_byte_arr = io.BytesIO()
    page.save(img_byte_arr, format="JPEG", quality=85)
    img_byte_arr = img_byte_arr.getvalue()

    # Encode to base64 and add to the list
    return base64.b64encode(img_byte_arr).decode("utf-8")

def anthropic_ocr(image, filename, client):

    response = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=2000,
        messages=[
            {
                "role": "user",
                "content": [
                        {
                        "type": "text",
                        "text": f"This is a page in an old UFO report document from project blue book. Please describe any photograph that is present. Not every image will contain a photograph. Then, please act as an OCR system and produce and output all the text found in the document and nothing else. For context: the filename including page number is {filename}"
                    },
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image,
                        },
                    }
                ],
            }
        ],
    )
    return response

def gpt_ocr(image, filename, client):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"This is a page in an old UFO report document from project blue book. Please describe any photograph that is present. Not every image will contain a photograph. Then, please act as an OCR system and produce and output all the text found in the document and nothing else. For context: the filename including page number is {filename}",
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
