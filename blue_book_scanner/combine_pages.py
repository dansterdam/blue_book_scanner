import os
import argparse

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Process some files.")

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
    d = args.input
    combined_file_contents = {}
    for file in os.listdir(d):
        filename, page = file.split('.pdf')[0], file.split('.pdf')[1].split('.txt')[0]
        with open(d+file, 'r') as f:
            contents = f.read()
            contents = contents + '\n\n'+'- page '+page+' -'+'\n\n'
            if filename not in combined_file_contents:
                combined_file_contents[filename] = [(contents, page)]
            else:
                combined_file_contents[filename].append((contents, page))
    
    for file, pages in combined_file_contents.items():
        ordered_content = ''
        ordered_pages = sorted(pages, key=lambda x: x[1])
        for page in ordered_pages:
            ordered_content += page[0]

        with open(args.output+file+'.txt', 'w') as f:
            f.write(ordered_content) 