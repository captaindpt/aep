import React, { useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import './App.css'; // You can create this for basic styling

// Configuration
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''; // Fallback to empty string for same-origin
const COLLECT_ENDPOINT_PATH = '/collect'; 
const MIN_DWELL_MS = 1000; // Minimum time in ms to consider as valid dwell
const THROTTLE_INTERVAL_MS = 500; // How often to update dwell time in state

interface DwellEntry {
  docSource: string; // Identifier for the content/document section
  dwellMs: number;
  startTime: number; // Timestamp when element became visible
}

interface AppProps {
  // Example: markdownContent could be fetched or passed as a prop
  // For this example, we'll use a hardcoded markdown string.
  // In a real app, this might be fetched based on a URL or document ID.
  documentId: string; 
  initialMarkdownContent: string;
}

const App: React.FC<AppProps> = ({ documentId, initialMarkdownContent }) => {
  const [markdownContent, setMarkdownContent] = useState(initialMarkdownContent);
  // For a real app, you might fetch markdown based on documentId:
  // useEffect(() => {
  //   fetch(`/api/document/${documentId}`)
  //     .then(res => res.text())
  //     .then(text => setMarkdownContent(text));
  // }, [documentId]);

  const observedElementsRef = useRef<Map<Element, DwellEntry>>(new Map());
  const contentRef = useRef<HTMLDivElement>(null); // Ref for the markdown content area
  const sessionIDRef = useRef<string>(crypto.randomUUID()); // Unique ID for this user session

  // Function to send AEP data via Beacon API
  const sendAEPData = (docSource: string, dwellTimeMs: number) => {
    if (dwellTimeMs < MIN_DWELL_MS) return; // Ignore brief dwells

    const eventData = {
      focus_ms: Math.round(dwellTimeMs),
      payload: { doc_source: docSource },
      focus_kind: 'human_dwell',
      session_id: sessionIDRef.current,
    };

    const collectUrl = `${API_BASE_URL}${COLLECT_ENDPOINT_PATH}`;

    try {
      // Use sendBeacon for reliability on page unload
      const success = navigator.sendBeacon(collectUrl, JSON.stringify(eventData));
      if (success) {
        console.log('AEP Beacon sent:', eventData, 'to', collectUrl);
      } else {
        console.error('AEP Beacon failed to send:', eventData, 'to', collectUrl);
        // Fallback for browsers that failed sendBeacon immediately (rare)
        // Or if you want to try XHR for active page logging
      }
    } catch (e) {
      console.error('Error sending AEP Beacon:', e);
    }
  };

  useEffect(() => {
    const currentObservedElements = observedElementsRef.current;
    
    const observer = new IntersectionObserver(
      (entries) => {
        const now = performance.now();
        entries.forEach((entry) => {
          const element = entry.target;
          const docSource = element.getAttribute('data-doc-source') || documentId;

          if (entry.isIntersecting) {
            // Element became visible
            if (!currentObservedElements.has(element)) {
              currentObservedElements.set(element, {
                docSource: docSource,
                dwellMs: 0,
                startTime: now,
              });
              // console.log('Observing:', docSource);
            }
          } else {
            // Element became hidden
            if (currentObservedElements.has(element)) {
              const dwellEntry = currentObservedElements.get(element)!;
              const accumulatedDwell = dwellEntry.dwellMs + (now - dwellEntry.startTime);
              // Send data when it becomes hidden
              sendAEPData(dwellEntry.docSource, accumulatedDwell);
              currentObservedElements.delete(element);
              // console.log('Stopped observing:', dwellEntry.docSource, 'Dwell:', accumulatedDwell);
            }
          }
        });
      },
      { threshold: 0.5 } // Trigger when 50% of the element is visible
    );

    // Attach observer to relevant elements after markdown is rendered
    // This is a simplified way; for dynamic content, might need MutationObserver or re-scan
    if (contentRef.current) {
      // Example: observe all paragraph elements, or elements with a specific class/attribute
      // For this demo, let's assume each paragraph is a trackable "document section"
      // In a real app, you'd assign meaningful `data-doc-source` to elements.
      const elementsToObserve = contentRef.current.querySelectorAll('p, h1, h2, h3, li');
      elementsToObserve.forEach((el, index) => {
        // Assign a unique doc-source if not already present
        if (!el.getAttribute('data-doc-source')) {
          el.setAttribute('data-doc-source', `${documentId}_section_${index}`);
        }
        observer.observe(el);
      });
    }

    // Interval to update dwell times for currently visible items (optional)
    // This is more for live display or more frequent (non-beacon) logging if needed
    const intervalId = setInterval(() => {
      const now = performance.now();
      currentObservedElements.forEach((entry, element) => {
        if (document.visibilityState === 'visible') { // Only accumulate if page is visible
            entry.dwellMs += (now - entry.startTime);
            entry.startTime = now;
            // console.log(`Active Dwell - ${entry.docSource}: ${entry.dwellMs.toFixed(0)}ms`);
        }
      });
    }, THROTTLE_INTERVAL_MS);

    // Cleanup function for when component unmounts or before re-running effect
    return () => {
      clearInterval(intervalId);
      observer.disconnect();
      // Send any pending dwell times for elements that were visible on unmount/cleanup
      const now = performance.now();
      currentObservedElements.forEach((entry) => {
        const accumulatedDwell = entry.dwellMs + (now - entry.startTime);
        sendAEPData(entry.docSource, accumulatedDwell);
      });
      currentObservedElements.clear();
    };
  }, [markdownContent, documentId]); // Re-run if markdown content or documentId changes

  // Handler for page visibility changes (tab switch, minimize) and unload
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'hidden') {
        const now = performance.now();
        observedElementsRef.current.forEach((entry, element) => {
          // Element was visible and is now hidden due to tab switch or page unload
          const accumulatedDwell = entry.dwellMs + (now - entry.startTime);
          sendAEPData(entry.docSource, accumulatedDwell);
          // No need to delete from map here as the main observer cleanup will handle it,
          // or if it becomes visible again, observer will pick it up.
          // For page unload, sendBeacon is the key.
        });
        // Important: Clear the map after sending, as their visibility session ends.
        // However, IntersectionObserver already handles removal when not intersecting.
        // This is more of a final flush.
        // observedElementsRef.current.clear(); 
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    // `pagehide` is more reliable for unload than `beforeunload` for sendBeacon
    window.addEventListener('pagehide', handleVisibilityChange); 

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('pagehide', handleVisibilityChange);
    };
  }, []); // Empty dependency array, so it runs once on mount and cleans up on unmount

  return (
    <div className="App">
      <header className="App-header">
        <h1>Document View: {documentId}</h1>
      </header>
      <div ref={contentRef} className="markdown-body">
        {markdownContent ? (
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {markdownContent}
          </ReactMarkdown>
        ) : (
          <p>Loading content...</p>
        )}
      </div>
    </div>
  );
}

export default App; 