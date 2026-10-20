import { useState } from "react";
import { apiRequest, formatMoney } from "../api.js";

// Statuses where the GP can still act on a transaction.
const OPEN_STATUSES = ["suggested", "needs_review"];

export default function TransactionTable({ organization, transactions, onChanged }) {
  // The button whose request is running, e.g. "approve-5". Used to disable it.
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  // Sends one action (approve / reject / ignore) and then refreshes the data.
  async function runAction(key, path) {
    setBusy(key);
    setError("");
    try {
      await apiRequest(path, organization, { method: "POST" });
      await onChanged();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  }

  return (
    <section className="card">
      <h2>Transactions</h2>
      {error && <p className="error">{error}</p>}

      {transactions.length === 0 ? (
        <p className="muted">No transactions yet. Upload a bank statement CSV above.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th>Description</th>
              <th className="num">Amount</th>
              <th>Status</th>
              <th>Suggested investor / reference</th>
              <th>Reason</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {transactions.map((txn) => {
              const canAct = OPEN_STATUSES.includes(txn.status);
              // Rejected matches are hidden; proposed and approved ones are shown.
              const matches = txn.matches.filter((m) => m.status !== "rejected");

              return (
                <tr key={txn.id}>
                  <td>{txn.date}</td>
                  <td>
                    {txn.description}
                    <div className="muted small">{txn.bank_reference}</div>
                  </td>
                  <td className="num">{formatMoney(txn.amount)}</td>
                  <td>
                    <span className={`badge ${txn.status}`}>{txn.status}</span>
                  </td>
                  <td>
                    {matches.length === 0 && <span className="muted">-</span>}
                    {matches.map((m) => (
                      <div key={m.id}>
                        {m.investor} ({m.line_item_reference})
                        {m.status === "approved" && " ✓"}
                      </div>
                    ))}
                  </td>
                  <td className="small">
                    {matches.map((m) => (
                      <div key={m.id}>{m.reason}</div>
                    ))}
                    {txn.reason && <div className="muted">{txn.reason}</div>}
                  </td>
                  <td>
                    {canAct &&
                      matches.map((m) => (
                        <div key={m.id} className="actions">
                          <button
                            disabled={busy === `approve-${m.id}`}
                            onClick={() => runAction(`approve-${m.id}`, `/matches/${m.id}/approve/`)}
                          >
                            Approve {m.line_item_reference}
                          </button>
                          <button
                            className="secondary"
                            disabled={busy === `reject-${m.id}`}
                            onClick={() => runAction(`reject-${m.id}`, `/matches/${m.id}/reject/`)}
                          >
                            Reject
                          </button>
                        </div>
                      ))}
                    {canAct && (
                      <button
                        className="secondary"
                        disabled={busy === `ignore-${txn.id}`}
                        onClick={() => runAction(`ignore-${txn.id}`, `/transactions/${txn.id}/ignore/`)}
                      >
                        Ignore
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
  );
}