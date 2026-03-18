import { useMemo, useState } from "react";
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
  agenciesToShow,
  selectedAgencies,
  setSelectedAgencies,
  docType,
  setDocType,
  //status,
  //setStatus,
  //selectedCfrParts,
  //setSelectedCfrParts,
  clearAdvanced,
  applyAdvanced,
  activeCount,
}) {
  const docTypes = ["Rulemaking", "Nonrulemaking"];
  //const statuses = ["Open", "Closed", "Pending"];
  const [agencyOrder, setAgencyOrder] = useState([]);
  /*const cfrParts = Array.from({ length: 200 }, (_, i) => i + 1);
  const [cfrSearch, setCfrSearch] = useState("");
  const [cfrOrder, setCfrOrder] = useState(cfrParts);*/
  const [value, setOnchange] = useState([new Date(), new Date()]);



  const orderedAgencies = useMemo(() => {
    const order =
      agencyOrder.length > 0 ? agencyOrder : agenciesToShow.map((a) => a.code);

    return order
      .map((code) => agenciesToShow.find((a) => a.code === code))
      .filter(Boolean);
  }, [agenciesToShow, agencyOrder]);

  const visibleAgencies = useMemo(() => {
    if (agencySearch.trim()) {
      return orderedAgencies;
    }

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

  /*const filteredCfrParts = useMemo(() => {
    const rawQuery = cfrSearch.trim().toLowerCase();
    if (!rawQuery) {
      return cfrOrder;
    }

    const numericQuery = rawQuery.replace(/[^0-9]/g, "");

    return cfrOrder.filter((part) => {
      const partText = String(part);

      if (numericQuery) {
        return partText.includes(numericQuery);
      }

      return (
        partText.includes(rawQuery) ||
        `part ${partText}`.includes(rawQuery) ||
        `cfr part ${partText}`.includes(rawQuery)
      );
    });
  }, [cfrSearch, cfrOrder]);

  const visibleCfrParts = useMemo(() => {
    if (cfrSearch.trim()) {
      return filteredCfrParts;
    }

    const minVisible = Math.max(5, selectedCfrParts.size);
    return filteredCfrParts.slice(0, minVisible);
  }, [cfrSearch, filteredCfrParts, selectedCfrParts.size]);

  const toggleCfrPart = (part) => {
    setSelectedCfrParts((prev) => {
      const next = new Set(prev);
      if (next.has(part)) {
        next.delete(part);
      } else {
        next.add(part);
      }
      return next;
    });

    setCfrOrder((prev) => [part, ...prev.filter((p) => p !== part)]);
  };*/

  return (
    <motion.aside className="sidebar"
      initial={{ opacity: 0, y: -20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.4, duration: 0.9, ease: "easeInOut" }}
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

    const format = (d) => d.toISOString().split("T")[0];
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

    const format = (d) => d.toISOString().split("T")[0];
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

        const format = (d) => d.toISOString().split("T")[0];

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

            {!agencySearch.trim() && selectedAgencies.size <= 5 && (
              <div className="hintText">
                Showing top 5 agencies. Selecting an agency moves it to the top.
              </div>
            )}
          </CollapsibleSection>

          {/* CFR Part
          <CollapsibleSection title="CFR Part">
            <input
              value={cfrSearch}
              onChange={(e) => setCfrSearch(e.target.value)}
              placeholder="Search CFR part number…"
            />

            <div className="agencyListStatic">
              {visibleCfrParts.map((part) => (
                <label key={part} className="check">
                  <input
                    type="checkbox"
                    checked={selectedCfrParts.has(part)}
                    onChange={() => toggleCfrPart(part)}
                  />
                  <span>Part {part}</span>
                </label>
              ))}
            </div>

            {!cfrSearch.trim() && selectedCfrParts.size <= 5 && (
              <div className="hintText">
                Showing top 5 parts. Selecting a part moves it to the top.
              </div>
            )}
          </CollapsibleSection> */}

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