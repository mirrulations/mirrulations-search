import {ColorRing} from 'react-loader-spinner'
import { useState } from "react";
import CollectionModal from "./CollectionModal";
import DownloadModal from '../pages/DownloadModal';

const ECFR_URL = "https://www.ecfr.gov";
const MAX_VOLUME = 10000;
const RATIO_WEIGHT = 0.7;
const VOLUME_WEIGHT = 0.3;
const CFR_PREVIEW_LIMIT = 10;


function scoreResult(item) {
 const num = (item.documentNumerator ?? 0) + (item.commentNumerator ?? 0);
 const total = (item.documentDenominator ?? 0) + (item.commentDenominator ?? 0);


 if (total === 0) return 0;


 const ratioScore = num / total;
 const volumeScore = Math.min(total / MAX_VOLUME, 1);
 return (ratioScore * RATIO_WEIGHT) + (volumeScore * VOLUME_WEIGHT);
}

function getDocketTitle(item) {
 return item.docket_title || item.title;
}

function normalizeCfrParts(cfrPart) {
 if (Array.isArray(cfrPart)) {
   return cfrPart;
 }
 if (typeof cfrPart === "string" && cfrPart.trim()) {
   return [{ part: cfrPart, link: ECFR_URL }];
 }
 return [];
}

function CfrPartList({ parts, expanded, onToggle }) {
 if (parts.length === 0) {
   return (
     <a href={ECFR_URL} target="_blank" rel="noopener noreferrer">None</a>
   );
 }

 const hasMore = parts.length > CFR_PREVIEW_LIMIT;
 const visibleParts = expanded ? parts : parts.slice(0, CFR_PREVIEW_LIMIT);

 return (
   <>
     {visibleParts.map((p, idx) => (
       <span key={`${p.title ?? "cfr"}-${p.part}-${idx}`}>
         <a href={p.link || ECFR_URL} target="_blank" rel="noopener noreferrer">
           {p.title != null ? `${p.title} Part ${p.part}` : p.part}
         </a>
         {idx < visibleParts.length - 1 && ", "}
       </span>
     ))}
     {hasMore && (
       <>
         {" "}
         <button
           type="button"
           className="cfr-toggle-btn"
           onClick={onToggle}
           aria-expanded={expanded}
         >
           {expanded ? "Show less" : `Show all ${parts.length}`}
         </button>
       </>
     )}
   </>
 );
}


export default function ResultsPanel({ results, loading, hasSearched, query, unauthorized, totalResults, error, onOpenDownloadStatus }) {

 const [modalDocketId, setModalDocketId] = useState(null);
 const [downloadDocketId, setDownloadDocketId] = useState(null)
 const [expandedCfrDockets, setExpandedCfrDockets] = useState(new Set());

 if (unauthorized) {
   return (
     <div className="results">
       <p>Please <a href="/login">log in</a> to search.</p>
     </div>
   );
 }

 if (loading) {
   return (
     <div className="results">
       <ColorRing
         visible={true}
         height="80"
         width="80"
         ariaLabel="color-ring-loading"
         colors={["#3b82f6", "#2563eb", "#1d4ed8", "#1e40af", "#1e3a8a"]}
       />
     </div>
   );
 }
 if (!hasSearched) return null;

 if (error) {
  return (
    <div className="results">
      <p style={{ color: "red" }}>
        {error}
      </p>
    </div>
  );
 }

 if (!results || results.length === 0) {
   return (
     <div className="results">
       <p>No results found.</p>
     </div>
   );
 }


 // Always anchor an exact docket-id match at the top, regardless of score —
 // otherwise scoreResult below buries it under high-AOSS-count chatter dockets.
 const sortedResults = [...results].sort((a, b) => {
   if (a.isExactMatch && !b.isExactMatch) return -1;
   if (b.isExactMatch && !a.isExactMatch) return 1;
   return scoreResult(b) - scoreResult(a);
 });


 return (
   <div className="results">
    {modalDocketId && (
    <CollectionModal
      docketId={modalDocketId}
      onClose={() => setModalDocketId(null)}
    />
  )}

    {/* Download modal for a single docket */}
    {downloadDocketId && (
    <DownloadModal
        collectionName={null}
        docketIds={[downloadDocketId]}
        onClose={() => setDownloadDocketId(null)}
        onOpenDownloadStatus={onOpenDownloadStatus}
      />
    )}

     <p className="results-summary">
       Showing results for "<strong>{query}</strong>" • {(totalResults ?? results.length).toLocaleString()} docket{(totalResults ?? results.length) !== 1 ? "s" : ""} found
     </p>
     {sortedResults.map((item, index) => {
       const docketKey = item.docket_id || String(index);
       const cfrParts = normalizeCfrParts(item.cfrPart);
       const cfrExpanded = expandedCfrDockets.has(docketKey);

       return (
         <div
           key={docketKey}
           className={`result-card${item.isExactMatch ? " result-card--exact-match" : ""}`}
         >
           {item.isExactMatch && (
             <span className="result-card-exact-badge">Exact match</span>
           )}
           <div className="result-card-body">
              <div className="result-card-info">
                 <h3 className="result-title">{getDocketTitle(item)}</h3>
                 <div className="result-meta">
                   <p><strong>Agency:</strong> {item.agency_id}</p>
                   <p><strong>Docket-ID:</strong> {item.docket_id}</p>
                   <p><strong>Docket type:</strong> {item.docket_type || item.document_type}</p>
                   <p>
                     <strong>CFR:</strong>{" "}
                     <CfrPartList
                       parts={cfrParts}
                       expanded={cfrExpanded}
                       onToggle={() => {
                         setExpandedCfrDockets((prev) => {
                           const next = new Set(prev);
                           if (next.has(docketKey)) {
                             next.delete(docketKey);
                           } else {
                             next.add(docketKey);
                           }
                           return next;
                         });
                       }}
                     />
                   </p>
                   <p><strong>Last modified date:</strong> {item.modify_date}</p>
                   <p><strong>Documents:</strong> {item.documentNumerator ?? 0}/{item.documentDenominator ?? 0}</p>
                   <p><strong>Comments:</strong> {item.commentNumerator ?? 0}/{item.commentDenominator ?? 0}</p>
                 </div>
                 {item.summary && (
                   <p className="result-summary">{item.summary}</p>
                 )}
              </div>
              <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 8 }}>
                <button className="btn-add-collection" onClick={() => setModalDocketId(item.docket_id)}>
                  Add to Collection
                </button>
                <button className="btn-add-collection" onClick={() => setDownloadDocketId(item.docket_id)}>
                  Download
                </button>
              </div>
            </div>
          </div>
       );
     })}
   </div>
 );
}