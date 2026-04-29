import { useState, useEffect } from "react";
import "../styles/collections.css";
import { getDownloadJobs, deleteDownloadJob } from "../api/collectionsApi";

const STATUS_STYLES = {
  pending:    { color: "#856404", background: "#fff8e1", border: "1px solid #ffe082" },
  processing: { color: "#0d47a1", background: "#e3f2fd", border: "1px solid #90caf9" },
  ready:      { color: "#2e7d32", background: "#e8f5e9", border: "1px solid #a5d6a7" },
  failed:     { color: "#c0392b", background: "#fdecea", border: "1px solid #f5c6cb" },
};

const triggerDownload = (jobId) => {
  const a = document.createElement("a");
  a.href = `/download/${jobId}`;
  a.download = "download.zip";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
};

export default function DownloadStatusModal({ onClose }) {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Initial load
  useEffect(() => {
    let cancelled = false;
    getDownloadJobs()
      .then((data) => { if (!cancelled) setJobs(data); })
      .catch((err) => { if (!cancelled) setError(err.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  // Poll only while active jobs exist
  const hasActive = jobs.some(
    (j) => j.status === "pending" || j.status === "processing"
  );
  useEffect(() => {
    if (!hasActive) return;
    const pollId = setInterval(() => {
      getDownloadJobs().then(setJobs).catch(() => {});
    }, 5000);
    return () => clearInterval(pollId);
  }, [hasActive]);

  const handleRemove = async (jobId) => {
    try {
      await deleteDownloadJob(jobId);
      setJobs((prev) => prev.filter((j) => j.job_id !== jobId));
    } catch {
      // silently ignore
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", color: "#aaa", fontSize: 20, lineHeight: 1, padding: "2px 4px" }} aria-label="Close">✕</button>
        </div>

        <h2 className="modal-title">Your Downloads</h2>

        {loading && <p className="modal-loading">Loading…</p>}
        {error && <p className="modal-loading" style={{ color: "#c0392b" }}>{error}</p>}
        {!loading && !error && jobs.length === 0 && <p className="modal-loading">No downloads yet.</p>}

        {!loading && jobs.length > 0 && (
          <div className="modal-collection-list">
            {jobs.map((job) => {
              const style = STATUS_STYLES[job.status] || STATUS_STYLES.pending;
              return (
                <div key={job.job_id} className="modal-collection-row" style={{ flexDirection: "column", alignItems: "flex-start", gap: 6 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", width: "100%", alignItems: "center" }}>
                    <span style={{ fontWeight: 600, fontSize: 14, color: "#1a1a1a" }}>
                      {job.docket_ids.length > 0
                        ? `${job.docket_ids.length} docket${job.docket_ids.length !== 1 ? "s" : ""}`
                        : "All dockets"}
                    </span>
                    <span style={{ fontSize: 12, padding: "3px 10px", borderRadius: 99, fontWeight: 600, ...style }}>
                      {job.status.charAt(0).toUpperCase() + job.status.slice(1)}
                    </span>
                    <button onClick={() => handleRemove(job.job_id)} title="Remove" style={{ background: "none", border: "none", cursor: "pointer", color: "#aaa", fontSize: 16, lineHeight: 1, padding: "2px 4px" }}>✕</button>
                  </div>
                  <div style={{ fontSize: 12, color: "#888" }}>
                    Format: {job.format.toUpperCase()} · Requested: {new Date(job.created_at).toLocaleString()}
                  </div>
                  {job.status === "ready" && (
                    <button className="modal-btn-add-small" style={{ marginTop: 4 }} onClick={() => triggerDownload(job.job_id)}>
                      Download
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        )}

        <div className="modal-actions">
          <button className="modal-btn-back" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}