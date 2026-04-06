import { useEffect, useState, useRef,useMemo } from "react";

import {
  getCollections,
  createCollection,
  deleteCollection,
  removeDocketFromCollection,
  getCollectionDockets,
} from "../api/collectionsApi";
import DownloadModal from "./DownloadModal";
import "../styles/collections.css";
import { ArrowLeftIcon, ArrowRightIcon } from "@phosphor-icons/react";

const ECFR_URL = "https://www.ecfr.gov";
const MAX_DOCKETS = 10;
const SORT_MODIFIED = "modified";
const SORT_ALPHABETICAL = "alphabetical";

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
  const [dockets, setDockets] = useState([]);
  const [pagination, setPagination] = useState(null);
  const [page, setPage] = useState(1);
  const [docketsLoading, setDocketsLoading] = useState(false);
  const [showDownloadModal, setShowDownloadModal] = useState(false);
  const [sortMode, setSortMode] = useState(SORT_MODIFIED);
  const [sortMenuOpen, setSortMenuOpen] = useState(false);
  const sortMenuRef = useRef(null);

  useEffect(() => {
    function handlePointerDown(e) {
      if (!sortMenuRef.current?.contains(e.target)) {
        setSortMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("touchstart", handlePointerDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("touchstart", handlePointerDown);
    };
  }, []);

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

  const loadDockets = async (collectionId, pageNum, sort) => {
    setDocketsLoading(true);
    try {
      const { results, pagination: p } = await getCollectionDockets(collectionId, pageNum, sort);
      setDockets(results);
      setPagination(p);
    } catch (err) {
      if (err.message === "UNAUTHORIZED") setUnauthorized(true);
      else setError("Failed to load dockets.");
    } finally {
      setDocketsLoading(false);
    }
  };

  useEffect(() => {
    if (!selectedCollectionId) return;
    setPage(1);
    loadDockets(selectedCollectionId, 1, sortMode);
  }, [selectedCollectionId]);

  useEffect(() => {
    if (!selectedCollectionId) return;
    loadDockets(selectedCollectionId, page, sortMode);
  }, [page]);

  useEffect(() => {
    if (!selectedCollectionId) return;
    setPage(1);
    loadDockets(selectedCollectionId, 1, sortMode);
  }, [sortMode]);

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
      setCollections((prev) => [...prev, newCollection]);
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
      loadDockets(collectionId, page, sortMode);
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

  const selectedCollection = collections.find(
    (collection) => collection.collection_id === selectedCollectionId
  );
  const selectedDocketIds = selectedCollection?.docket_ids || [];
  const overLimit = selectedDocketIds.length > MAX_DOCKETS;
  const sortLabel = sortMode === SORT_ALPHABETICAL ? "Alphabetical" : "Last modified";

  const handleDownloadAll = () => {
    if (!selectedCollection || overLimit) return;
    setShowDownloadModal(true);
  };


  const sortedDockets = useMemo(() => {
    const arr = [...dockets];
  
    if (sortMode === SORT_ALPHABETICAL) {
      arr.sort((a, b) =>
        (a.docket_title || "").localeCompare(b.docket_title || "", undefined, {
          sensitivity: "base",
        })
      );
    } else {
      arr.sort((a, b) =>
        new Date(b.modify_date) - new Date(a.modify_date)
      );
    }
  
    return arr;
  }, [dockets, sortMode]);

  return (
    <section className="collections-page collections-layout">
      <aside className="collections-sidebar">
        <div className="collections-sidebar-header">
          <div>
            <h2>My Collections</h2>
            <p>Save and revisit dockets—stable reference, not live search data.</p>
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
                Showing dockets in "{selectedCollection.name}" • {pagination?.totalResults ?? 0}{" "}
                docket{(pagination?.totalResults ?? 0) === 1 ? "" : "s"} found
                {overLimit && (
                  <span style={{ color: "#c0392b", marginLeft: 8, fontWeight: 600 }}>
                    · Limit of {MAX_DOCKETS} reached — remove dockets to download
                  </span>
                )}
              </p>
              <div className="collections-toolbar-right">
                <div className="collections-sort-wrap" ref={sortMenuRef}>
                  <button
                    type="button"
                    className="collections-sort-trigger"
                    aria-expanded={sortMenuOpen}
                    aria-haspopup="listbox"
                    aria-label="Sort dockets"
                    onClick={() => setSortMenuOpen((o) => !o)}
                  >
                    Sort
                    <span className="collections-sort-trigger-value" aria-hidden>
                      {sortLabel}
                    </span>
                  </button>
                  {sortMenuOpen && (
                    <ul className="collections-sort-menu" role="listbox">
                      <li role="none">
                        <button
                          type="button"
                          role="option"
                          aria-selected={sortMode === SORT_MODIFIED}
                          className={`collections-sort-menu-item${sortMode === SORT_MODIFIED ? " is-active" : ""}`}
                          onClick={() => {
                            setSortMode(SORT_MODIFIED);
                            setSortMenuOpen(false);
                          }}
                        >
                          Last modified
                        </button>
                      </li>
                      <li role="none">
                        <button
                          type="button"
                          role="option"
                          aria-selected={sortMode === SORT_ALPHABETICAL}
                          className={`collections-sort-menu-item${sortMode === SORT_ALPHABETICAL ? " is-active" : ""}`}
                          onClick={() => {
                            setSortMode(SORT_ALPHABETICAL);
                            setSortMenuOpen(false);
                          }}
                        >
                          Alphabetical
                        </button>
                      </li>
                    </ul>
                  )}
                </div>
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
                    disabled={!pagination?.totalResults || overLimit}
                    title={overLimit ? `Collections are limited to ${MAX_DOCKETS} dockets for download` : ""}
                  >
                    Download All
                  </button>
                  {editMode && (
                    <button
                      type="button"
                      className="collection-delete"
                      onClick={() =>
                        handleDeleteCollection(selectedCollection.collection_id)
                      }
                    >
                      Delete Collection
                    </button>
                  )}
                </div>
              </div>
            </div>

            {docketsLoading ? (
              <p className="collections-muted">Loading dockets...</p>
            ) : dockets.length === 0 ? (
              <p className="collections-muted">No dockets in this collection.</p>
            ) : (
              <>
                <div className="collection-results">
                  {sortedDockets.map((item) => (
                    <article key={item.docket_id} className="result-card">
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
                        <button
                          className="collection-remove-docket"
                          onClick={() =>
                            handleRemoveDocket(selectedCollection.collection_id, item.docket_id)
                          }
                        >
                          Remove from Collection
                        </button>
                      )}
                    </article>
                  ))}
                </div>
                <div className="pagination-div">
                  <button
                    className="page-button"
                    disabled={!pagination?.hasPrev}
                    onClick={() => setPage((p) => p - 1)}
                  >
                    <ArrowLeftIcon color="white" size={32} />
                  </button>
                  <span className="page-info">
                    Page {pagination?.page} of {pagination?.totalPages}
                  </span>
                  <button
                    className="page-button"
                    disabled={!pagination?.hasNext}
                    onClick={() => setPage((p) => p + 1)}
                  >
                    <ArrowRightIcon color="white" size={32} />
                  </button>
                </div>
              </>
            )}
          </>
        )}
      </div>

      {showDownloadModal && (
        <DownloadModal
          collectionName={selectedCollection?.name}
          docketIds={selectedDocketIds}
          onClose={() => setShowDownloadModal(false)}
        />
      )}
    </section>
  );
}
