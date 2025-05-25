import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css'; // Optional: for global styles

// Dummy markdown content for example
const DUMMY_MARKDOWN = `
# Welcome to the AEP Demo Document

This is a paragraph to test dwell time. Scroll down to see more content.

## Section Two

Another paragraph here. We are tracking how long you look at this.

- List item 1
- List item 2
- List item 3

## Section Three

Final paragraph. Hope this works!
`;

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App documentId="dummy_doc_01" initialMarkdownContent={DUMMY_MARKDOWN} />
  </React.StrictMode>,
); 