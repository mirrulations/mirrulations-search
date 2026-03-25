import { useMemo, useState, useEffect } from "react";
import { motion } from "motion/react"
import Calendar from 'react-calendar';
import 'react-calendar/dist/Calendar.css';

function CollapsibleSection({ title, defaultOpen = true, children, right }) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <section className="section">
      <button
        type="button"
        className="sectionHeader"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="sectionTitle">{title}</span>
        <span className="sectionRight">
          {right}
          <span className="sectionChev">{open ? "▾" : "▸"}</span>
        </span>
      </button>

      {open && <div className="sectionBody">{children}</div>}
    </section>
  );
}

export default function AdvancedSidebar({
  advOpen,
  setAdvOpen,
  yearFrom,
  setYearFrom,
  yearTo,
  setYearTo,
  agencySearch,
  setAgencySearch,
  // agenciesToShow is now fetched internally — removed from props
  selectedAgencies,
  setSelectedAgencies,
  docType,
  setDocType,
  //status,
  //setStatus,
  selectedCfrParts,
  setSelectedCfrParts,
  clearAdvanced,
  applyAdvanced,
  activeCount,
}) {
  const docTypes = ["Rulemaking", "Nonrulemaking"];
  const [value, setOnchange] = useState([new Date(), new Date()]);
  //const statuses = ["Open", "Closed", "Pending"];
  const [agencyOrder, setAgencyOrder] = useState([]);
  const [selectedTitle, setSelectedTitle] = useState("");

  // FIX: agenciesToShow is now local state, fetched from /agencies endpoint
  const [agenciesToShow, setAgenciesToShow] = useState([]);
  const [agenciesLoading, setAgenciesLoading] = useState(false);
  const [agenciesError, setAgenciesError] = useState(null);

  const titles = Array.from({ length: 50 }, (_, i) => i + 1);

  // Fetch agencies from the /agencies endpoint
  useEffect(() => {
    setAgenciesLoading(true);
    setAgenciesError(null);

    fetch("/agencies")
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((ids) => {
        // Endpoint returns plain strings like ["EPA", "DOT", ...]
        // Sidebar expects { code, name } shape
        setAgenciesToShow(ids.map((id) => ({ code: id, name: id })));
        console.log("agencies from API:", ids);
        console.log("total agencies:", ids.length);
      })
      .catch((err) => {
        console.error("Failed to load agencies:", err);
        setAgenciesError("Could not load agencies.");
      })
      .finally(() => setAgenciesLoading(false));
  }, []);

  const selectedCfrList = useMemo(() => {
    return Object.entries(selectedCfrParts).flatMap(([title, parts]) =>
      Array.from(parts).map((part) => ({
        title: Number(title),
        part
      }))
    );
  }, [selectedCfrParts]);

  const CFR_STRUCTURE = {
    1: { min: 1, max: 603 },
    2: { min: 1, max: 6099 },
    3: { min: 1, max: 102 },
    4: { min: 1, max: 83 },
    5: { min: 1, max: 10400 },
    6: { min: 1, max: 1003 },
    7: { min: 1, max: 5099 },
    8: { min: 1, max: 1399 },
    9: { min: 1, max: 599 },
    10: { min: 1, max: 1800 },
    11: { min: 1, max: 9430 },
    12: { min: 1, max: 1899 },
    13: { min: 1, max: 500 },
    14: { min: 1, max: 1399 },
    15: { min: 1, max: 2099 },
    16: { min: 1, max: 1799 },
    17: { min: 1, max: 499 },
    18: { min: 1, max: 1399 },
    19: { min: 1, max: 362 },
    20: { min: 1, max: 1099 },
    21: { min: 1, max: 1402 },
    22: { min: 1, max: 1701 },
    23: { min: 1, max: 1340 },
    24: { min: 1, max: 4199 },
    25: { min: 1, max: 1200 },
    26: { min: 1, max: 899 },
    27: { min: 1, max: 799 },
    28: { min: 1, max: 1100 },
    29: { min: 1, max: 4999 },
    30: { min: 1, max: 1299 },
    31: { min: 1, max: 1099 },
    32: { min: 1, max: 2899 },
    33: { min: 1, max: 403 },
    34: { min: 1, max: 1299 }, // Title 35 is reserved and doesn't appear to have any publically available parts
    36: { min: 1, max: 1600 },
    37: { min: 1, max: 501 },
    38: { min: 1, max: 200 },
    39: { min: 1, max: 3099 },
    40: { min: 1, max: 1900 },
    41: { min: 1, max: 304 },
    42: { min: 1, max: 1099 },
    43: { min: 1, max: 10099 },
    44: { min: 1, max: 402 },
    45: { min: 1, max: 2599 },
    46: { min: 1, max: 599 },
    47: { min: 1, max: 550 },
    48: { min: 1, max: 9999 },
    49: { min: 1, max: 1699 },
    50: { min: 1, max: 699 }
  };

  function generatePartsForTitle(title) {
    const range = CFR_STRUCTURE[title];
    if (!range) return [];
  
    return Array.from(
      { length: range.max - range.min + 1 },
      (_, i) => i + range.min
    );
  }

  // Because different titles have differing amount of CFR Parts, the following structure
  // Uses information from ecfr.gov to build the appropriate amount of parts per title

  // FIX: useMemo prevents new array reference on every render (was causing infinite loop)
  const cfrParts = useMemo(
    () => (selectedTitle ? generatePartsForTitle(selectedTitle) : []),
    [selectedTitle]
  );

  const [cfrSearch, setCfrSearch] = useState("");
  const [cfrOrder, setCfrOrder] = useState([]);

  // FIX: depend on selectedTitle not the array itself (array ref changed every render)
  useEffect(() => {
    setCfrOrder(cfrParts);
  }, [selectedTitle]);

  const orderedAgencies = useMemo(() => {
    const order =
      agencyOrder.length > 0 ? agencyOrder : agenciesToShow.map((a) => a.code);

    return order
      .map((code) => agenciesToShow.find((a) => a.code === code))
      .filter(Boolean);
  }, [agenciesToShow, agencyOrder]);

  const visibleAgencies = useMemo(() => {
    const q = agencySearch.trim().toLowerCase();
  
    // If user typed something, filter by their query
    if (q) {
      return orderedAgencies.filter(
        a => a.code.toLowerCase().includes(q) || a.name.toLowerCase().includes(q)
      );
    }
  
    // If nothing is in the search bar, show atleast 5 agencies
    const minVisible = Math.max(5, selectedAgencies.size);
    return orderedAgencies.slice(0, minVisible);
  }, [agencySearch, orderedAgencies, selectedAgencies.size]);

  const toggleAgency = (code) => {
    setSelectedAgencies((prev) => {
      const next = new Set(prev);
      if (next.has(code)) {
        next.delete(code);
      } else {
        next.add(code);
      }
      return next;
    });

    setAgencyOrder((prev) => {
      const base = prev.length > 0 ? prev : agenciesToShow.map((a) => a.code);
      return [code, ...base.filter((item) => item !== code)];
    });
  };

  const normalizeDate = (val, isEnd = false) => {
    const yearOnly = /^\d{4}$/.test(val.trim());
    if (yearOnly) {
      return isEnd ? `${val.trim()}-12-31` : `${val.trim()}-01-01`;
    }
    return val;
  };

  const filteredCfrParts = useMemo(() => {
    const rawQuery = cfrSearch.trim();
    if (!rawQuery) return cfrOrder;
  
    // The below code checks to make sure the string is just numbers
    // /d+ means "match a string that consists of one or more digits from start to end"
    // ^ and $ are anchors that assert the start and end of the string, ensuring that the entire string is made up of digits.
    if (!/^\d+$/.test(rawQuery)) return [];
  
    // Exact match!
    return cfrOrder.filter((part) => String(part) === rawQuery);
  }, [cfrSearch, cfrOrder]);

  const visibleCfrParts = useMemo(() => {
    if (cfrSearch.trim()) {
      return filteredCfrParts;
    }

  const selectedCount = Object.values(selectedCfrParts).reduce((sum, set) => sum + set.size, 0);

  const minVisible = Math.max(5, selectedCount);
  
    return filteredCfrParts.slice(0, minVisible);
  }, [cfrSearch, filteredCfrParts, selectedCfrParts]);

  const toggleCfrPart = (title, part) => {
    setSelectedCfrParts((prev) => {
      const next = { ...prev };
  
      if (!next[title]) {
        next[title] = new Set();
      }
  
      if (next[title].has(part)) {
        next[title].delete(part);
        if (next[title].size === 0) delete next[title];
      } else {
        next[title].add(part);
      }
  
      return next;
    });
  
    setCfrOrder((prev) => [part, ...prev.filter((p) => p !== part)]);
  };

  return (
    <motion.aside className="sidebar"
    initial={{ opacity: 0, y: -20 }}   
    animate={{ opacity: 1, y: 0 }}     
    transition={{ delay: 0.4 ,duration: 0.9, ease: "easeInOut" }}
    >
      <button
        className="advHeader"
        onClick={() => setAdvOpen((v) => !v)}
        aria-expanded={advOpen}
        type="button"
      >
        <div className="advHeaderText">
          <div className="advTitle">Advanced Search</div>
          <div className="advSub">
            Filters are the fastest way to narrow results.
          </div>
        </div>
        <div className="advHeaderRight">
          <span className="pill">{activeCount} active</span>
          <span className="chev">{advOpen ? "▾" : "▸"}</span>
        </div>
      </button>

      {advOpen && (
        <div className="advBody">

          {/**Date Section */}

          <section className="section">
            <h3>Date Range</h3>

            <div className="chipRow">
              <button
                type="button"
                className="chip"
                onClick={() => {
                  setYearFrom("");
                  setYearTo("");
                  setOnchange([null, null]);
                }}
              >
                All time
              </button>
              <button
            type="button"
            className="chip"
            onClick={() => {
              const end = new Date();
              const start = new Date();
              start.setFullYear(start.getFullYear() - 1);

              const format = (d) => d.toLocaleDateString("en-CA");
              setYearFrom(format(start));
              setYearTo(format(end));
              setOnchange([start, end]);
            }}
          >
            Past Year
          </button>

          <button
            type="button"
            className="chip"
            onClick={() => {
              const end = new Date();
              const start = new Date();
              start.setMonth(start.getMonth() - 6);

              const format = (d) => d.toLocaleDateString("en-CA");
              setYearFrom(format(start));
              setYearTo(format(end));
              setOnchange([start, end]);
            }}
          >
            Past 6 Months
          </button>

            </div>

            <div className="row">
            <input
            value={yearFrom}
            onChange={(e) => {
              const raw = e.target.value;
              setYearFrom(raw);

              // Only normalize + sync calendar once it looks complete
              const normalized = normalizeDate(raw, false);
              const isYearOnly = /^\d{4}$/.test(raw.trim());

              if (isYearOnly) {
                const endNorm = `${raw.trim()}-12-31`;
                setYearTo(endNorm);                          // auto-fill To
                setOnchange([new Date(normalized), new Date(endNorm)]);
              } else if (normalized && yearTo) {
                setOnchange([new Date(normalized), new Date(yearTo)]);
              }
            }}
            placeholder="YYYY or YYYY-MM-DD"
          />

          <input
            value={yearTo}
            onChange={(e) => {
              const raw = e.target.value;
              setYearTo(raw);

              const normalized = normalizeDate(raw, true);
              const isYearOnly = /^\d{4}$/.test(raw.trim());

              if (isYearOnly) {
                const startNorm = yearFrom || `${raw.trim()}-01-01`;
                setOnchange([new Date(startNorm), new Date(normalized)]);
              } else if (yearFrom && normalized) {
                setOnchange([new Date(yearFrom), new Date(normalized)]);
              }
            }}
            placeholder="YYYY or YYYY-MM-DD"
          />
            </div>

            <div className="calendar-div">
              <Calendar
                selectRange={true}
                onChange={(range) => {
                  if (!Array.isArray(range)) return;

                  let [start, end] = range;

                  // Handle first click (no end yet)
                  if (!end) {
                    setOnchange([start, null]);
                    setYearFrom(start.toISOString().split("T")[0]);
                    return;
                  }

                  // Auto-swap if user selects backwards
                  if (start > end) {
                    [start, end] = [end, start];
                  }

                  const format = (d) => d.toLocaleDateString("en-CA");

                  setOnchange([start, end]);
                  setYearFrom(format(start));
                  setYearTo(format(end));
                }}
                value={value}
              />
            </div>
          </section>

          {/* Agency */}
          <CollapsibleSection title="Agency">
            <input
              value={agencySearch}
              onChange={(e) => setAgencySearch(e.target.value)}
              placeholder="Search agencies…"
            />

            {agenciesLoading && (
              <div className="hintText">Loading agencies…</div>
            )}

            {agenciesError && (
              <div className="hintText" style={{ color: "red" }}>
                {agenciesError}
              </div>
            )}

            {!agenciesLoading && !agenciesError && (
              <div className="agencyListStatic">
                {visibleAgencies.map((a) => (
                  <label key={a.code} className="check">
                    <input
                      type="checkbox"
                      checked={selectedAgencies.has(a.code)}
                      onChange={() => toggleAgency(a.code)}
                    />
                    <span>
                      {a.code} — {a.name}
                    </span>
                  </label>
                ))}
              </div>
            )}

            {!agencySearch.trim() && selectedAgencies.size <= 5 && !agenciesLoading && (
              <div className="hintText">
                Showing top 5 agencies. Selecting an agency moves it to the top.
              </div>
            )}
          </CollapsibleSection>

          {/* CFR Part */}
          <CollapsibleSection title="CFR Title">
            <select
              value={selectedTitle}
              onChange={(e) => setSelectedTitle(Number(e.target.value))}
            >
              <option value="">Select Title</option>
              {titles.map((t) => (
                <option key={t} value={t}>
                  Title {t}
                </option>
              ))}
            </select>
          </CollapsibleSection>

          {selectedTitle && (
          <CollapsibleSection title={`Title ${selectedTitle} Parts`}>
            <input
              value={cfrSearch}
              onChange={(e) => setCfrSearch(e.target.value)}
              placeholder="Search CFR part…"
            />

            {visibleCfrParts.map((part) => (
              <label key={part} className="check">
                <input
                  type="checkbox"
                  checked={selectedCfrParts[selectedTitle]?.has(part) || false}
                  onChange={() => toggleCfrPart(selectedTitle, part)}
                />
                <span>Part {part}</span>
              </label>
            ))}
          </CollapsibleSection>
          )}
          
          {selectedCfrList.length > 0 && (
          <CollapsibleSection title="Selected CFR Filters">
            {selectedCfrList.map(({ title, part }) => (
              <label key={`${title}-${part}`} className="check">
                <input
                  type="checkbox"
                  checked={true}
                  onChange={() => toggleCfrPart(title, part)}
                />
                <span>
                  Title {title} Part {part}
                </span>
              </label>
            ))}
          </CollapsibleSection>
          )}

          {/* Doc type */}
          <section className="section">
            <h3>Docket Type</h3>
            {docTypes.map((t) => (
              <label key={t} className="check">
                <input
                  type="checkbox"
                  checked={docType === t}
                  onChange={() => setDocType(docType === t ? "" : t)}
                />
                <span>{t}</span>
              </label>
            ))}
          </section>

          <div className="actions">
            <button className="btn btn-ghost" onClick={clearAdvanced}>
              Clear
            </button>
            <button className="btn btn-primary" onClick={applyAdvanced}>
              Apply
            </button>
          </div>
        </div>
      )}
    </motion.aside>
  );
}
