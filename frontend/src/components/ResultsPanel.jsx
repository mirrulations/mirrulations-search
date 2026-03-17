import { ColorRing } from 'react-loader-spinner'
const ECFR_URL = "https://www.ecfr.gov";

export default function ResultsPanel({ results, loading, hasSearched }) {



  // This function down here basically turns Mon, "24 Nov 2025 16:44:12 GMT" to "Nov 24, 2025"

  function formatDate(dateStr) {
    if (!dateStr) return "Unknown";
    const date = new Date(dateStr);
    return date.toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
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
      {results.map((item, index) => (
        <div key={item.docket_id || index} className="result-card">
          <h3 className="result-title">{item.docket_title}
          </h3>

          <div className="result-meta">
            <p><strong>Agency:</strong> {item.agency_id}</p>
            <p><strong>Docket-ID:</strong> {item.docket_id}</p>
            <p><strong>Docket type:</strong> {item.docket_type}</p>
            <p>
              <strong>CFR:</strong>{" "}
              {item.cfrPart && item.cfrPart.length > 0 ? (
                item.cfrPart.map((p, idx) => (
                  <span key={idx}>
                    <a href={p.link} target="_blank" rel="noopener noreferrer">
                      {p.title != null ? `${p.title} Part ${p.part}` : p.part}
                    </a>
                    {idx < item.cfrPart.length - 1 && ", "}
                  </span>
                ))
              ) : (
                <a href={ECFR_URL} target="_blank" rel="noopener noreferrer">
                  None
                </a>
              )}
            </p>
            <p><strong>Last modified date:</strong> {formatDate(item.modify_date)}</p>
          </div>

          {item.summary && (
            <p className="result-summary">
              {item.summary}
            </p>
          )}

        </div>
      ))}
    </div>
  );
}