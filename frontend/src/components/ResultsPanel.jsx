import {ColorRing} from 'react-loader-spinner'
const ECFR_URL = "https://www.ecfr.gov";

function getCfrTitle(link) {
  const match = link.match(/title-(\d+)/);
  return match ? match[1] : null;
}

export default function ResultsPanel({ results, loading, hasSearched }) {

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
              item.cfrPart.map((p, idx) => {
                const title = getCfrTitle(p.link);

                return (
                  <span key={idx}>
                    {title} Part{" "}
                    <a href={p.link} target="_blank" rel="noopener noreferrer">
                      {p.part}
                    </a>
                    {idx < item.cfrPart.length - 1 && ", "}
                  </span>
                );
              })
            ) : (
              <a href={ECFR_URL} target="_blank" rel="noopener noreferrer">
                None
              </a>
            )}
          </p>
            <p><strong>Last modified date:</strong> {item.modify_date}</p>
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