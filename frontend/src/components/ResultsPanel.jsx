import { ColorRing } from "react-loader-spinner";
import { useState } from "react";
import CollectionModal from "./CollectionModal";

const ECFR_URL = "https://www.ecfr.gov";

/**
 * Renders `/search/` results in API order. Sort is chosen via GET sort_by; do not re-sort here
 * or you undo document_count / comment_count / modify_date from the server.
 */
export default function ResultsPanel({
  results,
  loading,
  hasSearched,
  query,
  unauthorized,
}) {
  const [modalDocketId, setModalDocketId] = useState(null);

  if (unauthorized) {
    return (
      <div className="results">
        <p>
          Please <a href="/login">log in</a> to search.
        </p>
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
  if (!results || results.length === 0) {
    return (
      <div className="results">
        <p>No results found.</p>
      </div>
    );
  }

  return (
    <div className="results">
      {modalDocketId && (
        <CollectionModal
          docketId={modalDocketId}
          onClose={() => setModalDocketId(null)}
        />
      )}
      <p className="results-summary">
        Showing results for &quot;<strong>{query}</strong>&quot; •{" "}
        {results.length} docket{results.length !== 1 ? "s" : ""} on this page
      </p>
      {results.map((item, index) => (
        <div key={item.docket_id || index} className="result-card">
          <div className="result-card-body">
            <div className="result-card-info">
              <h3 className="result-title">{item.docket_title}</h3>
              <div className="result-meta">
                <p>
                  <strong>Agency:</strong> {item.agency_id}
                </p>
                <p>
                  <strong>Docket-ID:</strong> {item.docket_id}
                </p>
                <p>
                  <strong>Docket type:</strong> {item.docket_type}
                </p>
                <p>
                  <strong>CFR:</strong>{" "}
                  {item.cfrPart && item.cfrPart.length > 0 ? (
                    item.cfrPart.map((p, idx) => (
                      <span key={idx}>
                        <a
                          href={p.link}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          {p.title != null ? `${p.title} Part ${p.part}` : p.part}
                        </a>
                        {idx < item.cfrPart.length - 1 && ", "}
                      </span>
                    ))
                  ) : (
                    <a
                      href={ECFR_URL}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      None
                    </a>
                  )}
                </p>
                <p>
                  <strong>Last modified date:</strong> {item.modify_date}
                </p>
                <p>
                  <strong>Documents:</strong> {item.documentNumerator ?? 0}/
                  {item.documentDenominator ?? 0}
                </p>
                <p>
                  <strong>Comments:</strong> {item.commentNumerator ?? 0}/
                  {item.commentDenominator ?? 0}
                </p>
              </div>
              {item.summary && (
                <p className="result-summary">{item.summary}</p>
              )}
            </div>
            <button
              type="button"
              className="btn-add-collection"
              onClick={() => setModalDocketId(item.docket_id)}
            >
              Add to Collection
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
