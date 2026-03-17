import { useMemo, useState,useEffect } from "react";
import "./styles/app.css";
import { searchDockets } from "./api/searchApi";
import AdvancedSidebar from "./components/AdvancedSidebar";
import SearchBar from "./components/SearchBar";
import ResultsPanel from "./components/ResultsPanel";
import { motion } from "motion/react"
import { ArrowLeftIcon,ArrowRightIcon } from "@phosphor-icons/react";


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
const [selectedCfrParts, setSelectedCfrParts] = useState(new Set());
const [page, setPage] = useState(1);
const [pagination, setPagination] = useState(null);
const [loading, setLoading] = useState(false);
const [hasSearched, setHasSearched] = useState(false);




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
    selectedCfrParts.size;

    const runSearch = async (newPage = 1) => {
      setLoading(true);
      setHasSearched(true);
    
      try {
        const selectedAgencyList = Array.from(selectedAgencies);
    
        const selectedCfrList = Array.from(selectedCfrParts);
    
        const data = await searchDockets(
          query,
          docType,
          selectedAgencyList,
          selectedCfrList,
          newPage,
          yearFrom,
          yearTo,   

        );
    
        setResults(data.results);
        setPagination(data.pagination);
        setPage(newPage);

      } catch (err) {
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
    setSelectedCfrParts(new Set());
  };


  useEffect(()=> {
    console.log(results)
    console.log("Sending filters:", {
  query,
  docType,
  yearFrom,
  yearTo,
});
  },[results])

return (
<div className="page">
<header className="topbar">
<div className="brand">Mirrulations</div>
{/*<button className="btn btn-primary">Log Out</button>*/}
</header>
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
<motion.h1 className="title"
initial={{ opacity: 0, y: -20 }}   
animate={{ opacity: 1, y: 0 }}     
transition={{ delay: 0.8 ,duration: 0.9, ease: "easeInOut" }}
>Mirrulations Explorer</motion.h1>
<SearchBar
query={query}
setQuery={setQuery}
onSubmit={(e) => {
              e.preventDefault();
              runSearch(1);
            }}
/>
<ResultsPanel
advancedPayload={advancedPayload}
results={results}
loading={loading}
hasSearched={hasSearched}

/>
<div className="pagination-div">
  <button className="page-button" disabled={!pagination?.hasPrev} onClick={() => runSearch(page - 1)}><ArrowLeftIcon color="white" size={32}/></button>

  <span className="page-info">
    Page {pagination?.page} of {pagination?.totalPages}
  </span>

  <button className="page-button" disabled={!pagination?.hasNext} onClick={() => runSearch(page + 1)}><ArrowRightIcon color="white" size={32}/></button>
</div>
</main>
</div>
</div>
  );
}