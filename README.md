# blue_book_scanner
Welcome to the Project Blue Book UFO casefile scanning repository: Blue Book Scanner! This collection of scripts is dedicated to the ambitious task of transforming the once-inaccessible Project Blue Book case files into easily searchable and accessible text data. The Blue Book Scanner project aims to unlock the mysteries hidden within over 10,000 case files by leveraging cutting-edge generative AI technology.

<br/>

# Donate!


### Become a UFO Data Hero!

Our mission to uncover the secrets of Project Blue Book UFO files is an exciting adventure, but we can't do it without your support. By donating, you can be a crucial part of this extraordinary journey and help us bring this treasure trove of information to the world.

<a href="https://www.buymeacoffee.com/projectbluebook" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" style="height: 60px !important;width: 217px !important;" ></a>

### Why Donate?

Every donation contributes directly to parsing more case files and expanding our database.
You're not just supporting a project; you're becoming a UFO Data Hero, helping to reveal hidden mysteries.
Your generosity fuels progress, accelerating our quest to make this data accessible, comprehensible and most importantly, open to all.

### Join the Mission:

For more details, check out our Reddit post that showcases our progress and dedication. Then, take the plunge and click the link above to become a UFO Data Hero. Your contribution will make a significant impact, and together, we can uncover the truth behind these enigmatic files. Don't miss the chance to be part of history!

See our [terms and conditions.](https://github.com/dansterdam/blue_book_scanner/blob/main/terms_and_conditions.md)

<br/>


# Usage

Before you can use the provided scripts to scan and process the Project Blue Book UFO files, you need to ensure you have Python installed and install the required dependencies. Follow the steps below to set up your environment.

## Installation

### Step 1: Install Python

If you don't already have Python installed, you can download it from the official website: [Python Downloads](https://www.python.org/downloads/).

### Step 2: Clone this Repository

Clone this repository to your local machine using Git:

```bash
git clone https://github.com/dansterdam/blue_book_scanner.git
cd blue_book_scanner
pip install -r requirements.txt
```

### Original PDF data

The original pdf data to feed into the scripts can be found and downloaded here: https://archive.org/details/bluebook

Other pdf data in similar formats can also work, be sure to pay attention to the prompt in vision.py if you want to alter the script to your needs.

Download the zip files to the repo's base folder and run this command, for example with the 1950s data

```bash
mkdir -p data/orig/1950s
unzip 1950s.zip -d data/orig/1950s/
```


### Scan PDFs
The below command will scan all the original pdfs in the directory `data/orig/1950s` and output the data to `data/scanned/1950s_scanned`. It will make the output directory for you if not found

```bash 
python blue_book_scanner/vision.py --keyfile api_key.json --input data/orig/1950s/ --output data/scanned/1950s_scanned/
```

### Combine pages

Combine the scanned pages into full scanned casefiles after the above finishes running by using this command
```bash
python blue_book_scanner/combine_pages.py --input data/scanned/1950s_scanned --output data/scanned_casefiles/1950s_cases/
```
