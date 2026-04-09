import { ColorRing } from "react-loader-spinner";
import { useState, useMemo } from "react";
import CollectionModal from "./CollectionModal";

const ECFR_URL = "https://www.ecfr.gov";
const MAX_VOLUME = 10000;
const RATIO_WEIGHT = 0.7;
const VOLUME_WEIGHT = 0.3;

const SORT_HINTS = {
  "": null,
  document_count:
    "Sorted by total documents in docket (highest first) on this page.",
  comment_count:
    "Sorted by total comments in docket (highest first) on this page.",
  modify_date: "Sorted by last modified (most recent first) on this page.",
};

function safeNumber(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

function docketKey(item) {
  return String(item?.docket_id ?? item?.id ?? "");
}

function compareDocket(a, b) {
  return docketKey(a).localeCompare(docketKey(b));
}

/** Most recent = larger timestamp first; missing dates last. */
function parseModifyMs(item) {
  const raw = item?.modify_date;
  if (raw == null || raw === "") return null;
  const s = String(raw).trim();
  if (!s) return null;
  let ms = Date.parse(s);
  if (!Number.isNaN(ms)) return ms;
  if (s.length >= 10) {
    ms = Date.parse(s.slice(0, 10));
    if (!Number.isNaN(ms)) return ms;
  }
  return null;
}

function scoreResult(item) {
  const num = (item.documentNumerator ?? 0) + (item.commentNumerator ?? 0);
  const total =
    (item.documentDenominator ?? 0) + (item.commentDenominator ?? 0);
  if (total === 0) return 0;
  const ratioScore = num / total;
  const volumeScore = Math.min(total / MAX_VOLUME, 1);
  return ratioScore * RATIO_WEIGHT + volumeScore * VOLUME_WEIGHT;
}

function sortSearchResultsForDisplay(results, sortBy) {
  if (!results?.length) return [];
  const copy = [...results];

  if (sortBy === "document_count") {
    copy.sort((a, b) => {
      const d =
        safeNumber(b.documentDenominator) - safeNumber(a.documentDenominator);
      return d !== 0 ? d : compareDocket(a, b);
    });
  } else if (sortBy === "comment_count") {
    copy.sort((a, b) => {
      const d =
        safeNumber(b.commentDenominator) - safeNumber(a.commentDenominator);
      return d !== 0 ? d : compareDocket(a, b);
    });
  } else if (sortBy === "modify_date") {
    copy.sort((a, b) => {
      const ta = parseModifyMs(a);
      const tb = parseModifyMs(b);
      if (ta == null && tb == null) return compareDocket(a, b);
      if (ta == null) return 1;
      if (tb == null) return -1;
      const diff = tb - ta;
      return diff !== 0 ? diff : compareDocket(a, b);
    });
  } else {
    copy.sort((a, b) => {
      const d = scoreResult(b) - scoreResult(a);
      return d !== 0 ? d : compareDocket(a, b);
    });
  }
  return copy;
}

export default function ResultsPanel({
  results,
  loading,
  hasSearched,
  query,
  unauthorized,
  sortBy = "",
}) {
  const [modalDocketId, setModalDocketId] = useState(null);

  const displayResults = useMemo(
    () => sortSearchResultsForDisplay(results, sortBy),
    [results, sortBy]
  );

  const sortHint = SORT_HINTS[sortBy] ?? null;

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
        {sortHint && (
          <>
            <br />
            <span className="results-sort-hint">{sortHint}</span>
          </>
        )}
      </p>
      {displayResults.map((item, index) => (
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
