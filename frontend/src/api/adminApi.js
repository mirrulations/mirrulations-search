export async function getAdminStatus() {
    const response = await fetch("/admin/status");
    if (!response.ok) return { is_admin: false };
    return response.json();
}

export async function getAuthorizedUsers() {
    const response = await fetch("/api/authorized");
    if (response.status === 401) throw new Error("UNAUTHORIZED");
    if (response.status === 403) throw new Error("FORBIDDEN");
    if (!response.ok) throw new Error(`Failed to fetch authorized users: ${response.status}`);
    return response.json();
}

export async function addAuthorizedUser(email, name) {
    const response = await fetch("/api/authorized", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, name }),
    });
    if (response.status === 401) throw new Error("UNAUTHORIZED");
    if (response.status === 403) throw new Error("FORBIDDEN");
    if (!response.ok) throw new Error(`Failed to add authorized user: ${response.status}`);
    return response.json();
}

export async function removeAuthorizedUser(email) {
    const response = await fetch(`/api/authorized/${encodeURIComponent(email)}`, {
        method: "DELETE",
    });
    if (response.status === 401) throw new Error("UNAUTHORIZED");
    if (response.status === 403) throw new Error("FORBIDDEN");
    if (response.status === 404) throw new Error("USER_NOT_FOUND");
    if (!response.ok) throw new Error(`Failed to remove authorized user: ${response.status}`);
}

export async function updateAuthorizedUserName(email, name) {
    const response = await fetch(`/api/authorized/${encodeURIComponent(email)}/update-name`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
    });
    if (response.status === 401) throw new Error("UNAUTHORIZED");
    if (response.status === 403) throw new Error("FORBIDDEN");
    if (response.status === 404) throw new Error("USER_NOT_FOUND");
    if (!response.ok) throw new Error(`Failed to update user: ${response.status}`);
    return response.json();
}

