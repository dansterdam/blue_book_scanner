const fs = require('fs');
const lunr = require('lunr');

let documents = [];
const textDir = './data/full_case_set';
const chunkSize = 1000; // Define the size of each chunk

fs.readdirSync(textDir).forEach(file => {
    const content = fs.readFileSync(`${textDir}/${file}`, 'utf-8');
    documents.push({ id: file, text: content });
});

let chunkedDocs = [];
for (let i = 0; i < documents.length; i += chunkSize) {
    chunkedDocs.push(documents.slice(i, i + chunkSize));
}

chunkedDocs.forEach((chunk, index) => {
    const idx = lunr(function () {
        this.ref('id');
        this.field('text');
        
        chunk.forEach(doc => {
            this.add(doc);
        });
    });

    fs.writeFileSync(`./data/index${index}.json`, JSON.stringify(idx));
});