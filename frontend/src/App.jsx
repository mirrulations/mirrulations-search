import { useMemo, useState, useEffect } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import Login from "./pages/Login";
import Home from "./pages/Home";
import PrivacyPolicy from "./pages/PrivacyPolicy";
import Collections from "./pages/Collections";
import Admin from "./pages/Admin";
import "./styles/app.css";
import { searchDockets, getAuthStatus } from "./api/searchApi";
import AdvancedSidebar from "./components/AdvancedSidebar";
import SearchBar from "./components/SearchBar";
import ResultsPanel from "./components/ResultsPanel";
import { motion } from "motion/react";
import { ArrowLeftIcon, ArrowRightIcon } from "@phosphor-icons/react";
import SiteNavbar from "./components/SiteNavbar";
import DownloadStatusModal from "./components/DownloadStatusModal";

/**Test */

export default function App() {
  const [query, setQuery] = useState("");
  const [docType, setDocType] = useState("");
  const [results, setResults] = useState([]);
  const [advOpen, setAdvOpen] = useState(true);
  const [yearFrom, setYearFrom] = useState("");
  const [yearTo, setYearTo] = useState("");
  const [agencySearch, setAgencySearch] = useState("");
  const [selectedAgencies, setSelectedAgencies] = useState(new Set());
  const [status, setStatus] = useState(new Set());
  const [selectedCfrParts, setSelectedCfrParts] = useState({});
  const [page, setPage] = useState(1);
  const [pageInput, setPageInput] = useState("1");
  const [pagination, setPagination] = useState(null);
  const [loading, setLoading] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [unauthorized, setUnauthorized] = useState(false);
  const [user, setUser] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [openDownloadStatus, setOpenDownloadStatus] = useState(null);
  /** Passed as GET /search/?sort_by= (empty = server default relevance) */
  const [searchSortBy, setSearchSortBy] = useState("");
  const [error, setError] = useState(null);
  // Snapshot of the params that produced the currently displayed results.
  // Pagination clicks reuse this so typing in the search box without
  // re-submitting can't silently change the search behind the user's back.
  const [activeParams, setActiveParams] = useState(null);

  useEffect(() => {
    getAuthStatus().then((data) => {
      if (data.logged_in) {
        setUser({ name: data.name, email: data.email });
      }
      setAuthLoading(false);
    });
  }, []);

  const TOP_AGENCIES = [
    { code: "EPA", name: "Environmental Protection Agency" },
    { code: "HHS", name: "Health and Human Services" },
    { code: "FDA", name: "Food and Drug Administration" },
    { code: "CMS", name: "Centers for Medicare & Medicaid Services" },
    { code: "DOT", name: "Department of Transportation" },
    { code: "FCC", name: "Federal Communications Commission" },
  ];

  const agenciesToShow = useMemo(() => {
    const q = agencySearch.toLowerCase();
    return q
      ? TOP_AGENCIES.filter(
          (a) =>
            a.code.toLowerCase().includes(q) ||
            a.name.toLowerCase().includes(q)
        )
      : TOP_AGENCIES;
  }, [agencySearch]);

  const activeCount =
    (yearFrom ? 1 : 0) +
    (yearTo ? 1 : 0) +
    selectedAgencies.size +
    status.size +
    Object.values(selectedCfrParts).reduce((sum, set) => sum + set.size, 0);

  const buildParamsFromState = (sortByOverride) => ({
    query,
    docType,
    agencies: Array.from(selectedAgencies),
    cfrParts: Object.entries(selectedCfrParts).flatMap(([title, parts]) =>
      Array.from(parts).map((part) => ({
        title: Number(title),
        part,
      }))
    ),
    yearFrom,
    yearTo,
    sortBy: sortByOverride !== undefined ? sortByOverride : searchSortBy,
  });

  const runSearch = async (newPage = 1, sortByOverride, paramsOverride) => {
    const params = paramsOverride ?? buildParamsFromState(sortByOverride);
    setLoading(true);
    setHasSearched(true);
    setUnauthorized(false);
    setError(null);

    try {
      const data = await searchDockets(
        params.query,
        params.docType,
        params.agencies,
        params.cfrParts,
        newPage,
        params.yearFrom,
        params.yearTo,
        params.sortBy
      );

      setResults(data.results);
      const pag = data.pagination;
      if (pag && !pag.hasNext && pag.page > 0) {
        const corrected = (pag.page - 1) * pag.pageSize + data.results.length;
        if (corrected < pag.totalResults) {
          pag.totalResults = corrected;
          pag.totalPages = Math.max(1, Math.ceil(corrected / pag.pageSize));
        }
      }
      setPagination(pag);
      setPage(newPage);
      setPageInput(String(newPage));
      setActiveParams(params);
    } catch (err) {
      if (err.message === "UNAUTHORIZED") {
        setUnauthorized(true);
      } else {
        setError(err.message);
      }
      console.error("Search failed:", err);
    } finally {
      setLoading(false);
    }
  };

  const advancedPayload = {
    yearFrom,
    yearTo,
    agencies: Array.from(selectedAgencies),
    status: Array.from(status),
  };

  const clearAdvanced = () => {
    setYearFrom("");
    setYearTo("");
    setAgencySearch("");
    setSelectedAgencies(new Set());
    setStatus(new Set());
    setSelectedCfrParts({});
  };

  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/privacy" element={<PrivacyPolicy />} />

      <Route path="/login" element={<Login />} />
      <Route path="/admin" element={<Admin />} />
      <Route path="/admin/*" element={<Admin />} />
      <Route
        path="/collections"
        element={
          user === null && !authLoading ? (
            <Navigate to="/login" replace />
          ) : (
            <div className="page page--with-site-nav">
              <SiteNavbar theme="light" layout="app" onCheckDownloads={() => setOpenDownloadStatus(true)} />
              <div className="layout layout-single">
                <main className="main">
                  <Collections onOpenDownloadStatus={() => setOpenDownloadStatus(true)}/>
                </main>
              </div>
              {openDownloadStatus && (
              <DownloadStatusModal onClose={() => setOpenDownloadStatus(null)} />
              )}
            </div>
          )
        }
      />
      <Route
        path="/explorer"
        element={
          user === null && !authLoading ? (
            <Navigate to="/login" replace />
          ) : (
            <div className="page page--with-site-nav">
              <SiteNavbar theme="light" layout="app" showCollectionsLink onCheckDownloads={() => setOpenDownloadStatus(true)}/>
              <div className="layout">
                <AdvancedSidebar
                  advOpen={advOpen}
                  setAdvOpen={setAdvOpen}
                  yearFrom={yearFrom}
                  setYearFrom={setYearFrom}
                  yearTo={yearTo}
                  setYearTo={setYearTo}
                  agencySearch={agencySearch}
                  setAgencySearch={setAgencySearch}
                  agenciesToShow={agenciesToShow}
                  selectedAgencies={selectedAgencies}
                  setSelectedAgencies={setSelectedAgencies}
                  docType={docType}
                  setDocType={setDocType}
                  status={status}
                  setStatus={setStatus}
                  selectedCfrParts={selectedCfrParts}
                  setSelectedCfrParts={setSelectedCfrParts}
                  clearAdvanced={clearAdvanced}
                  applyAdvanced={() => runSearch(1)}
                  activeCount={activeCount}
                />
                <main className="main">
                  <motion.h1
                    className="title"
                    initial={{ opacity: 0, y: -20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.8, duration: 0.9, ease: "easeInOut" }}
                  >
                    Mirrulations Explorer
                  </motion.h1>
                  <SearchBar
                    query={query}
                    setQuery={setQuery}
                    onSubmit={(e) => {
                      e.preventDefault();
                      runSearch(1);
                    }}
                  />
                  <p className="search-disclaimer">
                    Results may occasionally be limited during peak load. Refresh in a moment if you don't see expected dockets.
                  </p>
                  <div className="search-sort-row">
                    <label htmlFor="search-sort-by" className="search-sort-label">
                      Sort by
                    </label>
                    <select
                      id="search-sort-by"
                      className="search-sort-select"
                      value={searchSortBy}
                      onChange={(e) => {
                        const v = e.target.value;
                        setSearchSortBy(v);
                        if (hasSearched) {
                          runSearch(1, v);
                        }
                      }}
                    >
                      <option value="">Relevance (default)</option>
                      <option value="document_count">Total documents in docket</option>
                      <option value="comment_count">Total comments in docket</option>
                      <option value="modify_date">Last modified date</option>
                    </select>
                  </div>
                  <ResultsPanel
                    advancedPayload={advancedPayload}
                    results={results}
                    loading={loading}
                    hasSearched={hasSearched}
                    query={query}
                    unauthorized={unauthorized}
                    totalResults={pagination?.totalResults}
                    error={error}
                    onOpenDownloadStatus={() => setOpenDownloadStatus(true)}
                  />
                  {pagination?.totalPages > 0 && (
                    <div className="pagination-div">
                      <button
                        className="page-btn"
                        disabled={!pagination?.hasPrev}
                        onClick={() => runSearch(1, undefined, activeParams)}
                        title="First page"
                      >
                        «
                      </button>
                      <button
                        className="page-btn"
                        disabled={!pagination?.hasPrev}
                        onClick={() => runSearch(page - 1, undefined, activeParams)}
                        title="Previous page"
                      >
                        <ArrowLeftIcon weight="bold" size={16} />
                      </button>
                      <span className="page-info">
                        Page{" "}
                        <input
                          type="number"
                          className="page-input"
                          min={1}
                          max={pagination?.totalPages ?? 1}
                          value={pageInput}
                          onChange={(e) => setPageInput(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") {
                              const val = Number(pageInput);
                              if (val >= 1 && val <= (pagination?.totalPages ?? 1)) {
                                runSearch(val, undefined, activeParams);
                              } else {
                                setPageInput(String(page));
                              }
                            }
                          }}
                          onBlur={() => {
                            const val = Number(pageInput);
                            if (val >= 1 && val <= (pagination?.totalPages ?? 1) && val !== page) {
                              runSearch(val, undefined, activeParams);
                            } else {
                              setPageInput(String(page));
                            }
                          }}
                        />{" "}
                        of {pagination?.totalPages}
                      </span>
                      <button
                        className="page-btn"
                        disabled={!pagination?.hasNext}
                        onClick={() => runSearch(page + 1, undefined, activeParams)}
                        title="Next page"
                      >
                        <ArrowRightIcon weight="bold" size={16} />
                      </button>
                      <button
                        className="page-btn"
                        disabled={!pagination?.hasNext}
                        onClick={() => runSearch(pagination?.totalPages, undefined, activeParams)}
                        title="Last page"
                      >
                        »
                      </button>
                    </div>
                  )}
                </main>
              </div>
              {openDownloadStatus && (
              <DownloadStatusModal onClose={() => setOpenDownloadStatus(null)} />
              )}
            </div>
            
          )
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
