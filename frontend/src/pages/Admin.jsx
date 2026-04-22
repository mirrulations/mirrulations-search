import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { motion, AnimatePresence } from "motion/react";
import { getAdminStatus, getAuthorizedUsers, addAuthorizedUser, removeAuthorizedUser, updateAuthorizedUserName } from "../api/adminApi";
import "../styles/Admin.css";

export default function Admin() {
    const navigate = useNavigate();
    const [searchParams] = useSearchParams();

    const [adminUser, setAdminUser] = useState(null);
    const [authLoading, setAuthLoading] = useState(true);
    const [accessError, setAccessError] = useState(
        searchParams.get("error") === "unauthorized" ? "Your account does not have admin access." : null
    );

    const [users, setUsers] = useState([]);
    const [usersLoading, setUsersLoading] = useState(false);
    const [usersError, setUsersError] = useState(null);

    const [newEmail, setNewEmail] = useState("");
    const [newName, setNewName] = useState("");
    const [addLoading, setAddLoading] = useState(false);
    const [addError, setAddError] = useState(null);
    const [addSuccess, setAddSuccess] = useState(null);

    const [removeTarget, setRemoveTarget] = useState(null);
    const [removeLoading, setRemoveLoading] = useState(false);

    const [editTarget, setEditTarget] = useState(null);   // email being edited
    const [editName, setEditName] = useState("");
    const [editLoading, setEditLoading] = useState(false);
    const [editError, setEditError] = useState(null);

    useEffect(() => {
        getAdminStatus().then((data) => {
            if (data.is_admin) {
                setAdminUser({ name: data.name, email: data.email });
            }
            setAuthLoading(false);
        });
    }, []);

    useEffect(() => {
        if (!adminUser) return;
        setUsersLoading(true);
        getAuthorizedUsers()
            .then(setUsers)
            .catch((err) => setUsersError(err.message))
            .finally(() => setUsersLoading(false));
    }, [adminUser]);

    function parseEmailInput(raw) {
        // Matches: Display Name <email@example.com>
        const match = raw.match(/^(.+?)\s*<([^>]+)>\s*$/);
        if (match) {
            return { name: match[1].trim(), email: match[2].trim().toLowerCase() };
        }
        return { name: null, email: raw.trim().toLowerCase() };
    }

    const handleAdd = async (e) => {
        e.preventDefault();
        setAddError(null);
        setAddSuccess(null);
        const parsed = parseEmailInput(newEmail);
        const email = parsed.email;
        const name = newName.trim() || parsed.name || "";
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!email || !emailRegex.test(email)) {
            setAddError("Please enter a valid email address.");
            return;
        }
        if (!email || !name) {
            setAddError("Both email and name are required.");
            return;
        }
        setAddLoading(true);
        try {
            await addAuthorizedUser(email, name);
            setUsers((prev) => {
                const filtered = prev.filter((u) => u.email !== email);
                return [{ email, name, authorized_at: new Date().toISOString() }, ...filtered];
            });
            setNewEmail("");
            setNewName("");
            setAddSuccess(`${email} has been authorized.`);
        } catch (err) {
            setAddError(err.message === "FORBIDDEN" ? "You don't have permission to do this." : err.message);
        } finally {
            setAddLoading(false);
        }
    };

    const handleRemove = async (email) => {
        setRemoveTarget(email);
        setRemoveLoading(true);
        try {
            await removeAuthorizedUser(email);
            setUsers((prev) => prev.filter((u) => u.email !== email));
        } catch (err) {
            setUsersError(err.message === "USER_NOT_FOUND" ? "User not found." : err.message);
        } finally {
            setRemoveLoading(false);
            setRemoveTarget(null);
        }
    };

    const handleEditSave = async (email) => {
        const name = editName.trim();
        if (!name) return;
        setEditLoading(true);
        setEditError(null);
        try {
            await updateAuthorizedUserName(email, name);
            setUsers((prev) =>
                prev.map((u) => (u.email === email ? { ...u, name } : u))
            );
            setEditTarget(null);
        } catch (err) {
            setEditError(err.message);
        } finally {
            setEditLoading(false);
        }
    };

    if (authLoading) {
        return (
            <div className="admin-page">
                <div className="admin-loading">Checking credentials…</div>
            </div>
        );
    }

    // Not an admin — show a clean access-denied screen
    if (!adminUser) {
        return (
            <div className="admin-page">
                <motion.div
                    className="admin-denied-box"
                    initial={{ opacity: 0, y: -24 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.5, ease: "easeOut" }}
                >
                    <div className="admin-denied-icon" aria-hidden>🔒</div>
                    <h1 className="admin-denied-title">Admin Access Required</h1>
                    {accessError ? (
                        <p className="admin-denied-message admin-denied-message--error">{accessError}</p>
                    ) : (
                        <p className="admin-denied-message">
                            You need to sign in with an admin account to view this page.
                        </p>
                    )}
                    <div className="admin-denied-actions">
                        <a href="/admin/login" className="admin-google-btn">
                            <span className="admin-google-icon" aria-hidden>
                                <svg viewBox="0 0 24 24" width={18} height={18}>
                                    <path fill="#EA4335" d="M12 5.04c1.55 0 2.96.54 4.07 1.6l3.03-3.03C17.5 2.32 14.9 1 12 1 7.58 1 3.84 3.47 2.1 7.05l3.51 2.72A6.98 6.98 0 0 1 12 5.04z" />
                                    <path fill="#4285F4" d="M22.5 12.23c0-.82-.07-1.6-.22-2.36H12v4.51h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.09-1.92 3.22-4.74 3.22-8.23z" />
                                    <path fill="#FBBC05" d="M5.61 14.08A7.02 7.02 0 0 1 5.04 12c0-.72.13-1.41.35-2.08L2.1 7.05A11.95 11.95 0 0 0 1 12c0 1.93.46 3.76 1.27 5.38l3.34-2.6z" />
                                    <path fill="#34A853" d="M12 23c3.24 0 5.97-1.08 7.96-2.93l-3.57-2.77c-.99.67-2.26 1.07-4.39 1.07-2.39 0-4.42-.81-5.89-2.18l-3.51 2.72C6.97 21.16 9.24 23 12 23z" />
                                </svg>
                            </span>
                            Sign in as Admin
                        </a>
                        <Link to="/" className="admin-back-link">← Back to home</Link>
                    </div>
                </motion.div>
            </div>
        );
    }

    return (
        <div className="admin-page">
            <motion.header
                className="admin-header"
                initial={{ opacity: 0, y: -20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4 }}
            >
                <Link to="/" className="admin-brand">Mirrulations</Link>
                <div className="admin-header-right">
                    <span className="admin-badge">Admin</span>
                    <span className="admin-user-name">{adminUser.name}</span>
                    <a href="/logout" className="admin-logout-btn">Sign out</a>
                </div>
            </motion.header>

            <motion.main
                className="admin-main"
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.15, duration: 0.45 }}
            >
                <h1 className="admin-page-title">Authorized Users</h1>
                <p className="admin-page-subtitle">
                    Only users listed here can sign in to Mirrulations Explorer.
                </p>

                {/* Add user form */}
                <section className="admin-card">
                    <h2 className="admin-card-title">Add Authorized User</h2>
                    <form className="admin-add-form" onSubmit={handleAdd}>
                        <div className="admin-form-row">
                            <div className="admin-form-field">
                                <label htmlFor="new-email" className="admin-label">Google Email</label>
                                <input
                                    id="new-email"
                                    type="text"
                                    className="admin-input"
                                    placeholder="user@example.com"
                                    value={newEmail}
                                    onChange={(e) => setNewEmail(e.target.value)}
                                    disabled={addLoading}
                                    autoComplete="off"
                                />
                            </div>
                            <div className="admin-form-field">
                                <label htmlFor="new-name" className="admin-label">Display Name</label>
                                <input
                                    id="new-name"
                                    type="text"
                                    className="admin-input"
                                    placeholder="Jane Smith"
                                    value={newName}
                                    onChange={(e) => setNewName(e.target.value)}
                                    disabled={addLoading}
                                    autoComplete="off"
                                />
                            </div>
                            <button
                                type="submit"
                                className="admin-add-btn"
                                disabled={addLoading}
                            >
                                {addLoading ? "Adding…" : "Add User"}
                            </button>
                        </div>
                        <AnimatePresence>
                            {addError && (
                                <motion.p
                                    className="admin-form-error"
                                    initial={{ opacity: 0, height: 0 }}
                                    animate={{ opacity: 1, height: "auto" }}
                                    exit={{ opacity: 0, height: 0 }}
                                >
                                    {addError}
                                </motion.p>
                            )}
                            {addSuccess && (
                                <motion.p
                                    className="admin-form-success"
                                    initial={{ opacity: 0, height: 0 }}
                                    animate={{ opacity: 1, height: "auto" }}
                                    exit={{ opacity: 0, height: 0 }}
                                >
                                    {addSuccess}
                                </motion.p>
                            )}
                        </AnimatePresence>
                    </form>
                </section>

                {/* Users list */}
                <section className="admin-card">
                <h2 className="admin-card-title">
                    Current Authorized Users
                    {!usersLoading && (
                        <span className="admin-user-count">{users.length}</span>
                    )}
                    {!usersLoading && users.length > 0 && (
                        <span className="admin-edit-hint">Click a user's name to edit it!</span>
                    )}
                </h2>

                    {usersLoading && <div className="admin-list-loading">Loading users…</div>}
                    {usersError && <p className="admin-form-error">{usersError}</p>}

                    {!usersLoading && !usersError && users.length === 0 && (
                        <p className="admin-empty">No authorized users yet. Add one above.</p>
                    )}

                    {!usersLoading && users.length > 0 && (
                        <ul className="admin-user-list">
                            <AnimatePresence initial={false}>
                                {users.map((u) => (
                                    <motion.li
                                        key={u.email}
                                        className="admin-user-item"
                                        initial={{ opacity: 0, x: -12 }}
                                        animate={{ opacity: 1, x: 0 }}
                                        exit={{ opacity: 0, x: 12, height: 0, marginBottom: 0 }}
                                        transition={{ duration: 0.22 }}
                                    >
                                        <div className="admin-user-info">
                                            {editTarget === u.email ? (
                                                <div className="admin-edit-row">
                                                    <input
                                                        className="admin-input"
                                                        value={editName}
                                                        onChange={(e) => setEditName(e.target.value)}
                                                        disabled={editLoading}
                                                        autoFocus
                                                    />
                                                    <button
                                                        className="admin-user-edit-btn"
                                                        onClick={() => handleEditSave(u.email)}
                                                        disabled={editLoading || !editName.trim()}
                                                    >
                                                        {editLoading ? "Saving…" : "Save"}
                                                    </button>
                                                    <button
                                                        className="admin-cancel-edit-btn"
                                                        onClick={() => setEditTarget(null)}
                                                        disabled={editLoading}
                                                    >
                                                        Cancel
                                                    </button>
                                                    {editError && <span className="admin-form-error">{editError}</span>}
                                                </div>
                                            ) : (
                                                <span
                                                    className="admin-user-item-name"
                                                    style={{ cursor: "pointer" }}
                                                    onClick={() => { setEditTarget(u.email); setEditName(u.name); setEditError(null); }}
                                                    title="Click to edit name"
                                                >
                                                    {u.name}
                                                </span>
                                            )}
                                            <span className="admin-user-item-email">{u.email}</span>
                                        </div>
                                        <div className="admin-user-meta">
                                            <span className="admin-user-date">
                                                Added {new Date(u.authorized_at).toLocaleDateString()}
                                            </span>
                                            <span className="admin-user-date">
                                                Last login: {u.last_login ? new Date(u.last_login).toLocaleDateString() : "Never"}
                                            </span>
                                            <button
                                                className="admin-remove-btn"
                                                onClick={() => handleRemove(u.email)}
                                                disabled={removeLoading && removeTarget === u.email}
                                                aria-label={`Remove ${u.name}`}
                                            >
                                                {removeLoading && removeTarget === u.email ? "Removing…" : "Remove"}
                                            </button>
                                        </div>
                                    </motion.li>
                                ))}
                            </AnimatePresence>
                        </ul>
                    )}
                </section>
            </motion.main>
        </div>
    );
}