export async function getCollections() { // Gets all the current collections
    const response = await fetch("/api/collections");
    if (response.status === 401) throw new Error("UNAUTHORIZED");
    if (!response.ok) throw new Error(`Failed to fetch collections: ${response.status}`);
    return response.json();
}

export async function createCollection(name) { // Creates a new collection with the given name
    const response = await fetch("/api/collections", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
    });
    if (response.status === 401) throw new Error("UNAUTHORIZED");
    if (!response.ok) throw new Error(`Failed to create collection: ${response.status}`);
    return response.json();
}

export async function addDocketToCollection(collectionId, docketId) { // Adds a docket to a specific collection
    const response = await fetch(`/api/collections/${collectionId}/dockets`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ docket_id: docketId }),
    });
    if (response.status === 401) throw new Error("UNAUTHORIZED");
    if (!response.ok) throw new Error(`Failed to add docket to collection: ${response.status}`);
}

export async function deleteCollection(collectionId) {
    const response = await fetch(`/api/collections/${collectionId}`, {
        method: "DELETE",
    });
    if (response.status === 401) throw new Error("UNAUTHORIZED");
    if (!response.ok) throw new Error(`Failed to delete collection: ${response.status}`);
}

export async function removeDocketFromCollection(collectionId, docketId) {
    const response = await fetch(`/api/collections/${collectionId}/dockets/${encodeURIComponent(docketId)}`, {
        method: "DELETE",
    });
    if (response.status === 401) throw new Error("UNAUTHORIZED");
    if (!response.ok) throw new Error(`Failed to remove docket from collection: ${response.status}`);
}

export async function getDocketsByIds(docketIds) {
    const params = new URLSearchParams();
    docketIds.forEach(id => params.append("docket_id", id));
    const response = await fetch(`/dockets?${params.toString()}`);
    if (response.status === 401) throw new Error("UNAUTHORIZED");
    if (!response.ok) throw new Error(`Failed to fetch dockets: ${response.status}`);
    return response.json();
}

export async function getCollectionDockets(collectionId, page = 1) {
    const params = new URLSearchParams();
    params.append("page", page);
    const response = await fetch(`/api/collections/${collectionId}/dockets?${params.toString()}`);
    if (response.status === 401) throw new Error("UNAUTHORIZED");
    if (!response.ok) throw new Error(`Failed to fetch collection dockets: ${response.status}`);

    const results = await response.json();
    const pagination = {
        page: Number(response.headers.get("X-Page")),
        pageSize: Number(response.headers.get("X-Page-Size")),
        totalResults: Number(response.headers.get("X-Total-Results")),
        totalPages: Number(response.headers.get("X-Total-Pages")),
        hasNext: response.headers.get("X-Has-Next") === "true",
        hasPrev: response.headers.get("X-Has-Prev") === "true",
    };
    return { results, pagination };
}

export async function getDownloadJobs() {
    const response = await fetch("/download/jobs");
    if (response.status === 401) throw new Error("UNAUTHORIZED");
    if (!response.ok) throw new Error(`Failed to fetch download jobs: ${response.status}`);
    return response.json();
}
