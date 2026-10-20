import { useState } from "react";
import { apiRequest } from "../api.js";

// Lets the GP choose a CSV file, uploads it and shows the import summary.
export default function UploadForm({ organization, onImported }) {
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState("");

  async function handleSubmit(event) {
    event.preventDefault(); // stop the browser from reloading the page
    setUploading(true);
    setError("");
    setSummary(null);

    // The file is sent as multipart form data in a field called "file".
    const formData = new FormData();
    formData.append("file", file);

    try {
      const result = await apiRequest("/transactions/import/", organization, {
        method: "POST",
        body: formData,
      });
      setSummary(result);
      onImported(); // refresh the tables
    } catch (err) {
      setError(err.message);
    } finally {
      setUploading(false);
    }
  }

  return (
    <section className="card">
      <h2>Import bank statement</h2>
      <form onSubmit={handleSubmit}>
        <input type="file" accept=".csv" onChange={(e) => setFile(e.target.files[0])} />
        <button type="submit" disabled={!file || uploading}>
          {uploading ? "Uploading..." : "Upload CSV"}
        </button>
      </form>

      {error && <p className="error">{error}</p>}

      {summary && (
        <div className="summary">
          <p>
            Imported: <b>{summary.imported}</b> &nbsp; Duplicates: <b>{summary.duplicates}</b>{" "}
            &nbsp; Errors: <b>{summary.errors.length}</b>
          </p>
          <ul>
            {summary.duplicate_rows.map((dup) => (
              <li key={`dup-${dup.line}`}>
                Line {dup.line}: duplicate bank reference {dup.reference}
              </li>
            ))}
            {summary.errors.map((err) => (
              <li key={`err-${err.line}`} className="error">
                Line {err.line}: {err.message}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}