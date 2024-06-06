const chunkCount = 11; // Updated batch count
let indexes = [];
let currentPage = 1;
const resultsPerPage = 20;
let allResults = [];

async function loadIndex(chunk) {
    try {
        const response = await fetch(`data/index${chunk}.json`);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        return lunr.Index.load(data);
    } catch (error) {
        console.error(`Error loading index chunk ${chunk}:`, error);
        return null;
    }
}

async function loadAllIndexes() {
    for (let i = 0; i < chunkCount; i++) {
        let idx = await loadIndex(i);
        if (idx) {
            indexes.push(idx);
        }
    }
}

async function search(query) {
    // Clear previous search results and reset current page
    allResults = [];
    currentPage = 1;

    // Clear results container
    const resultsList = document.getElementById('results');
    resultsList.innerHTML = '';

    // Perform new search
    indexes.forEach((index, indexIdx) => {
        const phraseRegex = /"([^"]+)"|(\S+)/g;
        let match;
        const processedQuery = [];
        while ((match = phraseRegex.exec(query)) !== null) {
            if (match[1]) {
                processedQuery.push(`"${match[1]}"`);
            } else {
                processedQuery.push(match[2]);
            }
        }
        const processedQueryString = processedQuery.join(' ');

        const results = index.search(processedQueryString);
        results.forEach(result => {
            allResults.push({ index: indexIdx, result: result });
        });
    });

    // Display first page of results
    paginateResults(1);
}


function paginateResults(page) {
    const resultsList = document.getElementById('results');
    // Keep track of current scroll position
    const scrollTop = resultsList.scrollTop;

    const start = (page - 1) * resultsPerPage;
    const end = start + resultsPerPage;

    const paginatedResults = allResults.slice(start, end);
    paginatedResults.forEach(item => {
        const result = item.result;
        const index = item.index;
        const li = document.createElement('li');
        const link = document.createElement('a');
        const fileName = result.ref;

        // Fetch content of the document to get a preview
        fetch(`data/full_case_set/${result.ref}`)
            .then(response => response.text())
            .then(text => {
                // Extract preview of 150 characters
                const preview = text.substring(0, 500);
                // Set the link text to the filename
                link.textContent = fileName;
                link.href = `data/full_case_set/${result.ref}`;
                link.target = "_blank";
                link.className = "result-link";
                li.appendChild(link);

                // Add a newline
                const newline = document.createElement('br');
                li.appendChild(newline);
                li.appendChild(newline);

                // Add the filename and preview text in smaller font size
                const fileNameAndPreview = document.createElement('span');
                fileNameAndPreview.innerHTML = `<br><small><i>${preview}</i></small>`;
                li.appendChild(fileNameAndPreview);

                resultsList.appendChild(li);
            })
            .catch(error => console.error('Error fetching document:', error));
    });

    updatePagination(page);

    // Restore scroll position
    resultsList.scrollTop = scrollTop;
}

function updatePagination(page) {
    const pageInfo = document.getElementById('pageInfo');
    const prevPageButton = document.getElementById('prevPage');
    const nextPageButton = document.getElementById('nextPage');
    const totalPages = Math.ceil(allResults.length / resultsPerPage);

    pageInfo.textContent = `Page ${page} of ${totalPages}`;
    prevPageButton.disabled = page <= 1;
    nextPageButton.disabled = page >= totalPages;

    prevPageButton.onclick = () => paginateResults(page - 1);
    nextPageButton.onclick = () => paginateResults(page + 1);
}

// Load indexes when the page loads
// Load all indexes and then show initial results
loadAllIndexes()
    .then(() => {
        // Hide loading animation
        document.getElementById('loading').style.display = 'none';
        
        // Call search with an empty query to show all initial results
        search('');
    })
    .catch(error => console.error('Error loading indexes:', error));

// Show loading animation while loading indexes
document.getElementById('loading').style.display = 'block';

// Event listener for the scroll event on the results container
document.getElementById('results').addEventListener('scroll', function() {
    const resultsContainer = this;
    const scrollPosition = resultsContainer.scrollTop;
    const scrollHeight = resultsContainer.scrollHeight;
    const clientHeight = resultsContainer.clientHeight;

    // Check if the user has scrolled near the bottom and load more results if needed
    if (scrollHeight - scrollPosition <= clientHeight + 50) {
        const totalPages = Math.ceil(allResults.length / resultsPerPage);
        if (currentPage < totalPages) {
            currentPage++; // Increment the current page
            paginateResults(currentPage);
        }
    }
});

// Event listener for the search button
document.getElementById('searchButton').addEventListener('click', function() {
    const query = document.getElementById('searchBox').value;
    search(query);
});

// Event listener for the search box for Enter key press
document.getElementById('searchBox').addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
        const query = document.getElementById('searchBox').value;
        search(query);
    }
});
