import { formatMoney } from "../api.js";

export default function LineItemPanel({ lineItems }) {
  return (
    <section className="card">
      <h2>Line items</h2>
      {lineItems.length === 0 ? (
        <p className="muted">No line items. Run python manage.py seed_demo.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Reference</th>
              <th>Investor</th>
              <th>Call</th>
              <th className="num">Called</th>
              <th className="num">Funded</th>
              <th className="num">Remaining</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {lineItems.map((item) => (
              <tr key={item.id}>
                <td>{item.reference}</td>
                <td>{item.investor}</td>
                <td>#{item.capital_call}</td>
                <td className="num">{formatMoney(item.amount_called)}</td>
                <td className="num">{formatMoney(item.amount_funded)}</td>
                <td className="num">{formatMoney(item.amount_remaining)}</td>
                <td>
                  <span className={`badge ${item.status}`}>{item.status}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}