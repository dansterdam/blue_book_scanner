import os
import shutil

JOBS = [
    ('data/scanned/1940s_scanned/', 'data/scanned_casefiles/1940s_cases/'),
    ('data/scanned/1950s_scanned/', 'data/scanned_casefiles/1950s_cases/'),
    ('data/scanned/1960s_scanned/', 'data/scanned_casefiles/1960s_cases/'),
    ('data/scanned/19XXs_scanned/', 'data/scanned_casefiles/19XXs_cases/'),
]

def combine_pages(input_dir, output_dir):
    combined_file_contents = {}
    for file in os.listdir(input_dir):
        if '.pdf' not in file or not file.endswith('.txt'):
            continue
        filename, page = file.split('.pdf')[0], file.split('.pdf')[1].split('.txt')[0]
        with open(input_dir + file, 'r') as f:
            contents = f.read()
            contents = contents + '\n\n' + '- page ' + page + ' -' + '\n\n'
            if filename not in combined_file_contents:
                combined_file_contents[filename] = [(contents, page)]
            else:
                combined_file_contents[filename].append((contents, page))

    for file, pages in combined_file_contents.items():
        ordered_content = ''
        ordered_pages = sorted(pages, key=lambda x: int(x[1]))
        for page in ordered_pages:
            ordered_content += page[0]

        with open(output_dir + file + '.txt', 'w') as f:
            f.write(ordered_content)

if __name__ == '__main__':
    for input_dir, output_dir in JOBS:
        print(f'Processing {input_dir} -> {output_dir}')
        combine_pages(input_dir, output_dir)
        shutil.make_archive(output_dir.rstrip('/'), 'zip', output_dir)
        print(f'  Done.')
