import { useEffect, useState } from "react";
import { apiRequest } from "./api.js";
import UploadForm from "./components/UploadForm.jsx";
import TransactionTable from "./components/TransactionTable.jsx";
import LineItemPanel from "./components/LineItemPanel.jsx";

export default function App() {
  const [organizations, setOrganizations] = useState([]);
  const [organization, setOrganization] = useState("northwind");
  const [transactions, setTransactions] = useState([]);
  const [lineItems, setLineItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Load the list of organizations once, for the switcher.
  useEffect(() => {
    apiRequest("/organizations/", organization)
      .then(setOrganizations)
      .catch((err) => setError(err.message));
  }, []);

  // Reload transactions and line items for the chosen organization.
  // Called on page load, on organization change and after every action.
  async function loadData() {
    setError("");
    try {
      const [txns, items] = await Promise.all([
        apiRequest("/transactions/", organization),
        apiRequest("/line-items/", organization),
      ]);
      setTransactions(txns);
      setLineItems(items);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  // Runs on first load and every time the organization changes.
  // Only here do we show "Loading..." (refreshes after actions happen quietly).
  useEffect(() => {
    setLoading(true);
    loadData();
  }, [organization]);

  return (
    <div className="page">
      <header className="header">
        <h1>CallMatch</h1>
        <label>
          Organization{" "}
          <select value={organization} onChange={(e) => setOrganization(e.target.value)}>
            {organizations.map((org) => (
              <option key={org.slug} value={org.slug}>
                {org.name}
              </option>
            ))}
          </select>
        </label>
      </header>

      {error && <p className="error">Error: {error}</p>}

      {/* key={organization} resets the form (and its summary) when switching organization */}
      <UploadForm key={organization} organization={organization} onImported={loadData} />

      {loading ? (
        <p>Loading...</p>
      ) : (
        <div className="layout">
          <TransactionTable
            organization={organization}
            transactions={transactions}
            onChanged={loadData}
          />
          <LineItemPanel lineItems={lineItems} />
        </div>
      )}
    </div>
  );
}