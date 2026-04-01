import { useEffect, useMemo, useState } from "react";
import {
  getCollections,
  createCollection,
  deleteCollection,
  removeDocketFromCollection,
  getDocketsByIds,
} from "../api/collectionsApi";
import "../styles/collections.css";
const ECFR_URL = "https://www.ecfr.gov";

export default function Collections() {
  const [collections, setCollections] = useState([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [newCollectionName, setNewCollectionName] = useState("");
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [selectedCollectionId, setSelectedCollectionId] = useState(null);
  const [editMode, setEditMode] = useState(false);
  const [error, setError] = useState("");
  const [unauthorized, setUnauthorized] = useState(false);
  const [docketDetails, setDocketDetails] = useState({});
  const [docketSearch, setDocketSearch] = useState("");

  const selectedCollection = collections.find(
    (collection) => collection.collection_id === selectedCollectionId
  );
  const selectedDocketIds = selectedCollection?.docket_ids || [];


  const loadCollections = async () => {
    setLoading(true);
    setError("");
    try {
      const data = await getCollections();
      setCollections(Array.isArray(data) ? data : []);
    } catch (err) {
      if (err.message === "UNAUTHORIZED") {
        setUnauthorized(true);
      } else {
        setError("Failed to load collections.");
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadCollections();
  }, []);

  useEffect(() => {
    if (collections.length === 0) {
      setSelectedCollectionId(null);
      return;
    }
    const hasSelected = collections.some(
      (collection) => collection.collection_id === selectedCollectionId
    );
    if (!hasSelected) {
      setSelectedCollectionId(collections[0].collection_id);
    }
  }, [collections, selectedCollectionId]);

  useEffect(() => {
    if (!selectedDocketIds.length) return;
    getDocketsByIds(selectedDocketIds).then(results => {
        setDocketDetails(prev => {
            const next = { ...prev };
            results.forEach(d => { next[d.docket_id] = d; });
            return next;
        });
    });
  }, [selectedCollectionId]);

  useEffect(() => {
    setDocketSearch("");
  }, [selectedCollectionId]);

  const handleCreate = async (e) => {
    e.preventDefault();
    const trimmedName = newCollectionName.trim();
    if (!trimmedName) return;

    setSubmitting(true);
    setError("");
    try {
      const created = await createCollection(trimmedName);
      const newCollection = {
        collection_id: created.collection_id,
        name: trimmedName,
        docket_ids: [],
      };
      setCollections((prev) => [
        ...prev,
        newCollection,
      ]);
      setSelectedCollectionId(created.collection_id);
      setShowCreateForm(false);
      setNewCollectionName("");
    } catch (err) {
      if (err.message === "UNAUTHORIZED") {
        setUnauthorized(true);
      } else {
        setError("Failed to create collection.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeleteCollection = async (collectionId) => {
    setError("");
    try {
      await deleteCollection(collectionId);
      setCollections((prev) =>
        prev.filter((col) => col.collection_id !== collectionId)
      );
      setEditMode(false);
    } catch (err) {
      if (err.message === "UNAUTHORIZED") {
        setUnauthorized(true);
      } else {
        setError("Failed to delete collection.");
      }
    }
  };

  const handleRemoveDocket = async (collectionId, docketId) => {
    setError("");
    try {
      await removeDocketFromCollection(collectionId, docketId);
      setCollections((prev) =>
        prev.map((col) =>
          col.collection_id === collectionId
            ? {
                ...col,
                docket_ids: (col.docket_ids || []).filter((id) => id !== docketId),
              }
            : col
        )
      );
    } catch (err) {
      if (err.message === "UNAUTHORIZED") {
        setUnauthorized(true);
      } else {
        setError("Failed to remove docket from collection.");
      }
    }
  };

  if (unauthorized) {
    return (
      <section className="collections-page">
        <h1 className="collections-title">My Collections</h1>
        <p>Please <a href="/login">log in</a> to view collections.</p>
      </section>
    );
  }

  const filteredDocketIds = useMemo(() => {
    const query = docketSearch.trim().toLowerCase();
    if (!query) return selectedDocketIds;

    return selectedDocketIds.filter((docketId) => {
      const item = docketDetails[docketId];
      if (!item) {
        return docketId.toLowerCase().includes(query);
      }

      return [
        item.docket_id,
        item.docket_title,
        item.agency_id,
        item.docket_type,
      ].some((value) => (value || "").toLowerCase().includes(query));
    });
  }, [docketDetails, docketSearch, selectedDocketIds]);

  const handleDownloadAll = () => {
    if (!selectedCollection) return;
    const lines = [
      `Collection: ${selectedCollection.name}`,
      "",
      ...selectedDocketIds.map((docketId) => docketId),
    ];
    const blob = new Blob([lines.join("\n")], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${selectedCollection.name.replace(/\s+/g, "-").toLowerCase()}-dockets.txt`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <section className="collections-page collections-layout">
      <aside className="collections-sidebar">
        <div className="collections-sidebar-header">
          <div>
            <h2>My Collections</h2>
            <p>All your saved dockets in one place!</p>
          </div>
          <button
            type="button"
            className="collections-plus"
            onClick={() => setShowCreateForm((prev) => !prev)}
          >
            +
          </button>
        </div>

        {showCreateForm && (
          <form className="collections-create-inline" onSubmit={handleCreate}>
            <input
              type="text"
              placeholder="New collection name"
              value={newCollectionName}
              onChange={(e) => setNewCollectionName(e.target.value)}
            />
            <button
              type="submit"
              className="btn btn-primary"
              disabled={submitting || !newCollectionName.trim()}
            >
              {submitting ? "Creating..." : "Create"}
            </button>
          </form>
        )}

        {loading ? (
          <p className="collections-muted">Loading collections...</p>
        ) : collections.length === 0 ? (
          <p className="collections-muted">No collections yet.</p>
        ) : (
          <div className="collections-nav-list">
            {collections.map((collection) => (
              <button
                key={collection.collection_id}
                type="button"
                className={`collections-nav-item ${
                  selectedCollectionId === collection.collection_id ? "is-active" : ""
                }`}
                onClick={() => {
                  setSelectedCollectionId(collection.collection_id);
                  setEditMode(false);
                }}
              >
                {collection.name}
              </button>
            ))}
          </div>
        )}
      </aside>

      <div className="collections-content">
        {error && <p className="collections-error">{error}</p>}

        {!selectedCollection ? (
          <p className="collections-muted">Select or create a collection to continue.</p>
        ) : (
          <>
            <h1 className="collections-title">{selectedCollection.name}</h1>
            <div className="collections-toolbar">
              <p className="collections-summary">
                Showing dockets in "{selectedCollection.name}" • {filteredDocketIds.length}{" "}
                docket{filteredDocketIds.length === 1 ? "" : "s"} found
              </p>
              <div className="collections-actions">
                <button
                  type="button"
                  className="collections-action-btn collections-action-btn-secondary"
                  onClick={() => setEditMode((prev) => !prev)}
                >
                  {editMode ? "Done" : "Edit"}
                </button>
                <button
                  type="button"
                  className="collections-action-btn"
                  onClick={handleDownloadAll}
                  disabled={selectedDocketIds.length === 0}
                >
                  Download All
                </button>
                {editMode && (
                  <button
                    type="button"
                    className="collection-delete"
                    onClick={() => handleDeleteCollection(selectedCollection.collection_id)}
                  >
                    Delete Collection
                  </button>
                )}
              </div>
            </div>

            {selectedDocketIds.length > 0 && (
              <div className="collections-docket-search-wrap">
                <input
                  type="text"
                  className="collections-docket-search"
                  placeholder="Search this collection's dockets..."
                  value={docketSearch}
                  onChange={(e) => setDocketSearch(e.target.value)}
                />
              </div>
            )}

            {selectedDocketIds.length === 0 ? (
              <p className="collections-muted">No dockets in this collection.</p>
            ) : filteredDocketIds.length === 0 ? (
              <p className="collections-muted">
                No dockets in this collection match "{docketSearch}".
              </p>
            ) : (
              <div className="collection-results">
                {filteredDocketIds.map((docketId) => {
                  const item = docketDetails[docketId];
                  if (!item) return <div key={docketId} className="result-card"><p>Loading...</p></div>;
                  return (
                      <article key={docketId} className="result-card">
                          <h3 className="result-title">{item.docket_title}</h3>
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
                                      <a href={ECFR_URL} target="_blank" rel="noopener noreferrer">None</a>
                                  )}
                              </p>
                              <p><strong>Last modified date:</strong> {item.modify_date}</p>
                          </div>
                          {editMode && (
                              <button className="collection-remove-docket"
                                  onClick={() => handleRemoveDocket(selectedCollection.collection_id, docketId)}>
                                  Remove from Collection
                              </button>
                          )}
                      </article>
                  );
              })}
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}
