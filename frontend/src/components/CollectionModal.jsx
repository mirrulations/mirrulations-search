import { useState, useEffect } from "react";
import { getCollections, createCollection, addDocketToCollection } from "../api/collectionsApi";
import "../styles/collections.css";

function collectionAlreadyHasDocket(collection, docketId) {
  if (docketId == null || docketId === "") return false;
  const ids = collection?.docket_ids;
  if (!Array.isArray(ids)) return false;
  const target = String(docketId).trim();
  return ids.some((id) => String(id).trim() === target);
}

export default function CollectionModal({ docketId, onClose }) {
  const [collections, setCollections] = useState([]);
  const [selected, setSelected] = useState(new Set());
  const [view, setView] = useState("select");
  const [newName, setNewName] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    getCollections()
      .then(setCollections)
      .catch(() => setError("Failed to load collections."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    setSelected((prev) => {
      const next = new Set(prev);
      let changed = false;
      for (const collectionId of prev) {
        const col = collections.find((c) => c.collection_id === collectionId);
        if (col && collectionAlreadyHasDocket(col, docketId)) {
          next.delete(collectionId);
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [collections, docketId]);

  const toggleSelected = (id, alreadyIn) => {
    if (alreadyIn) return;
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const handleAdd = async () => {
    if (selected.size === 0) return;
    setSubmitting(true);
    setError(null);
    try {
      await Promise.all(
        Array.from(selected).map((id) => addDocketToCollection(id, docketId))
      );
      onClose();
    } catch {
      setError("Failed to add to collection(s). Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleCreate = async () => {
    const trimmed = newName.trim();
    if (!trimmed) return;
    setSubmitting(true);
    setError(null);
    try {
      const created = await createCollection(trimmed);
      await addDocketToCollection(created.collection_id, docketId);
      onClose();
    } catch {
      setError("Failed to create collection. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        {view === "select" ? (
          <>
            <div className="modal-header">
              <button
                type="button"
                className="modal-btn-create"
                onClick={() => {
                  setView("create");
                  setError(null);
                }}
              >
                +
              </button>
            </div>
            <h2 className="modal-title">Which Collections would you like to add to?</h2>
            {loading && <p className="modal-loading">Loading...</p>}
            {error && <p className="modal-error">{error}</p>}
            <div className="modal-collection-list">
              {collections.map((col) => {
                const alreadyIn = collectionAlreadyHasDocket(col, docketId);
                return (
                  <label
                    key={col.collection_id}
                    className={
                      alreadyIn
                        ? "modal-collection-row modal-collection-row--disabled"
                        : "modal-collection-row"
                    }
                  >
                    <span className="modal-collection-name">
                      {col.name}
                      {alreadyIn && (
                        <span className="modal-collection-badge">
                          Already in this collection
                        </span>
                      )}
                    </span>
                    <input
                      type="checkbox"
                      disabled={alreadyIn}
                      checked={alreadyIn ? false : selected.has(col.collection_id)}
                      onChange={() => toggleSelected(col.collection_id, alreadyIn)}
                    />
                  </label>
                );
              })}
            </div>
            <div className="modal-actions">
              <button
                type="button"
                className="modal-btn-add"
                disabled={selected.size === 0 || submitting}
                onClick={handleAdd}
              >
                {submitting ? "Adding..." : "Add"}
              </button>
            </div>
          </>
        ) : (
          <>
            <h2 className="modal-title">Name your new collection</h2>
            {error && <p className="modal-error">{error}</p>}
            <input
              className="modal-input"
              type="text"
              placeholder="Collection name"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleCreate()}
              autoFocus
            />
            <div className="modal-actions">
              <button
                type="button"
                className="modal-btn-back"
                onClick={() => {
                  setView("select");
                  setError(null);
                }}
              >
                Back
              </button>
              <button
                type="button"
                className="modal-btn-add"
                disabled={!newName.trim() || submitting}
                onClick={handleCreate}
              >
                {submitting ? "Creating..." : "Create & Add"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
