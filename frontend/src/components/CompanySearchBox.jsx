import { useEffect, useRef, useState } from "react";
import { searchCompanies } from "../api/company";

const MIN_QUERY_LENGTH = 2;
const DEBOUNCE_MS = 300;

export default function CompanySearchBox({ onSelect, placeholder = "Search any listed company..." }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const containerRef = useRef(null);
  const debounceRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(event) {
      if (containerRef.current && !containerRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  function handleChange(event) {
    const value = event.target.value;
    setQuery(value);
    setError("");

    if (debounceRef.current) clearTimeout(debounceRef.current);

    if (value.trim().length < MIN_QUERY_LENGTH) {
      setResults([]);
      setIsOpen(false);
      return;
    }

    debounceRef.current = setTimeout(async () => {
      setIsLoading(true);
      try {
        const matches = await searchCompanies(value.trim());
        setResults(matches);
        setIsOpen(true);
      } catch {
        setError("Could not search companies right now.");
      } finally {
        setIsLoading(false);
      }
    }, DEBOUNCE_MS);
  }

  function handleSelect(company) {
    setQuery(company.name);
    setIsOpen(false);
    setResults([]);
    onSelect(company);
  }

  return (
    <div className="company-search" ref={containerRef}>
      <input
        type="text"
        value={query}
        onChange={handleChange}
        onFocus={() => results.length > 0 && setIsOpen(true)}
        placeholder={placeholder}
        className="company-search-input"
      />
      {isLoading && <span className="company-search-spinner">Searching...</span>}
      {error && <p className="error-banner">{error}</p>}
      {isOpen && results.length > 0 && (
        <ul className="company-search-results">
          {results.map((company) => (
            <li key={company.url}>
              <button type="button" onClick={() => handleSelect(company)}>
                {company.name}
              </button>
            </li>
          ))}
        </ul>
      )}
      {isOpen && !isLoading && results.length === 0 && (
        <ul className="company-search-results">
          <li className="company-search-empty">No matching companies</li>
        </ul>
      )}
    </div>
  );
}
